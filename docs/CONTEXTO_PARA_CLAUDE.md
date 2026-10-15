# Contexto del proyecto — Ambulatorio Dinámico HLF

> Pega este archivo al inicio de una conversación con Claude (o déjalo en la raíz del repo) para que entienda el proyecto
> sin tener que explorarlo desde cero. Estado al 14-10-2026.

## 1. Qué es
Proyecto para la hackatón **AWS Breaking Barriers Chile 2026** (14 al 16 de octubre, FCFM UChile). Responde al desafío del
**Hospital Clínico Dra. Eloísa Díaz Inzunza (La Florida, HLF)**: la **priorización clínica evolutiva** de la lista de espera
de consultas de especialidad.

- **Problema:** la prioridad se asigna una vez, al leer la interconsulta (SIC), y queda congelada aunque el paciente empeore
  mientras espera (urgencias, hospitalizaciones, exámenes alterados).
- **Frase del hospital:** "La lista de espera es una foto; la salud de las personas, una película."
- **Qué hace la app:**
  - recalcula la lista con cada evento clínico y explica por qué cada paciente está en su lugar;
  - avisa qué descompensaciones graves requieren evaluación médica (plazo de 72 h);
  - propone cómo llenar las horas libres de los box;
  - mide indicadores de resultado.
- **Usuarios:** enfermería y administrativos (a quién llamar, gestión de box), médicos (horas libres, decisión clínica)
  y jefatura (indicadores).

## 1b. La solución, explicada en simple
**Antes (lista congelada):** al paciente le asignan una prioridad cuando llega la interconsulta y espera en ese lugar,
aunque después termine en urgencia u hospitalizado. Nadie se entera hasta que le toca su turno.

**Con Ambulatorio Dinámico:**
1. **Detecta el cambio.** Cada evento clínico nuevo entra al sistema: urgencia, hospitalización, examen alterado o cambio
   de fármaco. Puede llegar del registro, de un Excel/CSV importado o de la foto de un informe, que se lee con Textract y
   reglas y luego se confirma a mano.
2. **Recalcula la lista en milisegundos** con reglas oficiales: Tabla de priorización SSMSO 2025 del HLF y criterios
   MINSAL Ord. 536/2025. Si el diagnóstico empeoró, el paciente sube a la prioridad que indica la tabla para ese diagnóstico
   descompensado.
3. **Explica el porqué.** Cada paciente muestra el camino de su prioridad con la fuente de cada paso (interconsulta → evento
   → fila de la tabla → lugar en la lista). Bedrock puede redactarlo en lenguaje simple, pero no decide nada.
4. **Pide una acción con plazo.** Una descompensación grave genera "requiere evaluación médica en 72 h" (KPI del hospital).
   La alerta solo se cierra con una decisión clínica registrada (con responsable), una cita o una derivación. Si pasan
   más de 72 h, queda "atrasada".
5. **Convierte la prioridad en una hora real.** Propone a quién citar en cada hora libre de los box, en el orden de la
   lista. Sigue la cita en todos sus estados (propuesta → reservada → confirmada → atendida o no asistió) y no permite
   reservar la misma hora dos veces. Un médico con tiempo libre ve a quiénes atender.
6. **El equipo clínico decide y queda registro.** El especialista confirma o ajusta la prioridad con un motivo. Esas
   revisiones alimentan el kappa de concordancia con el experto.
7. **Mide si funciona:** tiempo del evento a la evaluación, citas por estado, horas recuperadas, contactabilidad, kappa
   (con su n) y cobertura del 100 % de la lista con el mismo criterio.

**Impacto medido en el dataset sintético** (al 13-10-2026, lista completa):
- hay 17 pacientes con descompensación grave sin estabilizar;
- en la lista congelada, su lugar mediano era el **N° 171**, y 16 de ellos estaban fuera de los primeros 50;
- en la lista dinámica, su lugar mediano es el **N° 9**.

**Por qué es confiable:**
- no hay "caja negra": son reglas con fuente que se pueden auditar;
- el sistema nunca baja la prioridad de nadie por sí solo;
- las inasistencias no castigan la prioridad clínica;
- los fallecidos salen de la lista;
- todo es reproducible a cualquier fecha de corte.

**Por qué escala:** la tabla de priorización es un diccionario en `puntaje.py` (`FILA_DESCOMPENSADO`), así que adaptarla
a otro hospital del SSMSO es cambiar ese diccionario, sin tocar el resto. Además importa
Excel/CSV del sistema del hospital y corre sin servidores propios en AWS (Lambda, API Gateway, DynamoDB, S3, Textract,
Bedrock y Amplify).

## 2. Plazos (no negociables)
- Miércoles 21:00: todo desplegado de punta a punta. **Hecho.**
- **Jueves 15:00: congelamiento de funcionalidades.** Después solo se pule, se ensaya y se graba un video de respaldo.
- Viernes 10:15: cierre del código. 12:00: pre-evaluación técnica. 15:00: pitch de los finalistas.
- Prioridad absoluta: **que la demo funcione**, por sobre cualquier funcionalidad nueva.

**Rúbrica:** innovación técnica 25 % · impacto social 25 % · factibilidad 20 % · escalabilidad 15 % · presentación 15 %.

**Indicadores (KPI) del hospital:**
- reevaluación < 72 h tras un evento;
- concordancia con el experto, kappa ≥ 0,70;
- 100 % de la lista con un criterio común.

## 3. Principios de diseño (obligatorios; el usuario insiste mucho en esto)
1. **Las reglas explicables y con fuente oficial ordenan la lista, no un modelo de IA.** Nada de pesos inventados: cada razón
   lleva su `fuente`. El LLM (Amazon Bedrock) solo redacta explicaciones en lenguaje simple.
2. **La herramienta propone y explica; el equipo clínico decide** (confirmar o ajustar, con motivo y trazabilidad).
3. Fallecidos: salen de la lista (causal 9). Atendidos: salen desde su fecha de atención.
4. Las inasistencias **no** bajan la prioridad: solo encienden la bandera `riesgo_inasistencia` (posible causal 8).
5. Todo se calcula a una `fecha_corte`, usando solo registros con fecha anterior o igual.
6. **Fotos de informes sin IA generativa** (decisión del usuario: "un error en el hospital puede ser crítico"). El flujo es
   Amazon Textract (OCR) → reglas con detección de negaciones → validación con Pydantic → confirmación humana con
   verificación de identidad. Bedrock queda solo como respaldo opcional.

## 4. Modelo de priorización (`lambda/puntaje.py`)
- **Categoría alta, media o baja:** parte de la `prioridad_inicial` de la SIC. Si después hay una descompensación (evento
  grave), sube a la fila "descompensado / no controlado" de la **Tabla de priorización SSMSO 2025 del HLF** (págs. 84 a 111),
  definida en `FILA_DESCOMPENSADO`:
  - pasan a alta: I50, I20, J44, J45 y K70;
  - pasan a media: E11, E03 y G40.

  **El sistema nunca baja una categoría por sí solo.** Las equivalencias K70, I20 y G40 están marcadas "a validar".
- **Orden** (MINSAL Ord. 536/2025), en `clave_orden`:
  1. categoría;
  2. descompensación grave (`riesgo_vital`);
  3. grupo de especial protección;
  4. antigüedad mayor a 1 año;
  5. **LACE** (experimental, solo desempata);
  6. días de espera;
  7. id del paciente.
- **Descompensación grave (`riesgo_vital`, nombre interno):** un evento grave sin estabilización posterior, en un diagnóstico
  cuya fila de la tabla es alta. Requiere evaluación médica en **72 h**: `evaluacion.estado` puede ser `pendiente`,
  `atrasada` o `evaluada`. El sistema **no** declara "riesgo vital": eso lo decide el médico.

  La alerta (`contactar_hoy`) se cierra solo con una de estas cuatro cosas (llamar no basta):
  - una decisión clínica (`/decision`);
  - una revisión del especialista;
  - una cita reservada;
  - una derivación a urgencia.
- **Banderas** (no cambian el orden):
  - GES "posible incumplimiento: verificar": el plazo se cuenta desde el ingreso a la lista, porque el registro no trae el
    hito real;
  - 2 inasistencias consecutivas;
  - medición fuera de rango;
  - revisión sugerida (exámenes alterados, aumento de dosis).
- **Vigencia de la revisión:** un evento posterior invalida la confirmación o el ajuste y el paciente pasa a `requiere_revision`.
- Las fuentes están en `docs/criterios_oficiales.md`.

## 5. Arquitectura (todo en AWS)
- `front/`: React + Vite + framer-motion + Tailwind (por CDN), con el logo y los colores del HLF. Se publica en
  **AWS Amplify** (deploy manual con zip mediante el script). Sin `VITE_API_URL`, funciona en modo mock con `front/src/mock.json`.
- `lambda/`: Python 3.12 (arm64), una sola Lambda detrás de **API Gateway HTTP API**. Se despliega con CloudFormation/SAM
  (`template.yaml`).
  - Datos: `perfiles.json` y `box.json` en **S3**.
  - Registros del equipo (eventos, revisiones, contactos, decisiones, citas, novedades e importaciones) en **DynamoDB**,
    con `pk=id_paciente` y `sk=tipo#fecha`.
  - **Textract** lee fotos; **Bedrock** (`us.anthropic.claude-sonnet-5`) redacta explicaciones. No enviar `temperature`:
    el modelo lo rechaza.
- **Fecha:** la variable `FECHA_REFERENCIA=hoy` usa la fecha real de Chile (así está publicado). Con `AAAA-MM-DD` se simula
  una fecha; por defecto es 2026-10-13, que es la fecha del dataset.

**Archivos clave**

| Archivo | Qué contiene |
|---|---|
| `lambda/app.py` | Todas las rutas y la lógica de negocio: enriquecer pacientes, box, citas, KPIs, informes |
| `lambda/puntaje.py` | Motor de reglas |
| `lambda/informe.py`, `lambda/modelos.py` | Lectura de informes (Textract + reglas) y modelos Pydantic |
| `lambda/importar.py` | Importación de Excel/CSV solo con la librería estándar |
| `lambda/explicar.py` | Explicación con Bedrock, o con plantilla si no hay modelo |
| `lambda/local_server.py` | Servidor local (puerto 3001) |
| `front/src/App.jsx` | Toda la interfaz |
| `front/src/api.js` | Llamadas a la API |
| `contrato.md` | **Contrato de la API y del JSON. No cambiar campos sin avisar al equipo.** |
| `tests/test_api.py` | 47 tests (estilo pytest) |
| `scripts/deploy_aws.ps1` | Publica backend, datos y página |
| `scripts/generar_mock.py` | Regenera `mock.json` |

## 6. Rutas principales de la API (el detalle está en `contrato.md`)

| Método y ruta | Qué hace |
|---|---|
| `GET /pacientes?fecha_corte=&especialidad=` | Lista priorizada, con `excluidos` |
| `GET /pacientes/{id}` | Detalle del paciente |
| `GET /pacientes/{id}/historia` | Posición del paciente cada 14 días |
| `POST /eventos` | Registra un evento clínico y recalcula la lista |
| `POST /pacientes/{id}/informe` | Lee texto o foto y **propone** eventos; no guarda nada |
| `POST /pacientes/{id}/revision` | Confirmar o ajustar la categoría, con motivo |
| `POST /pacientes/{id}/contacto` | Llamada: `citado`, `derivado_urgencia`, `contactado` o `no_contesta`. Con `citado` + hora, reserva la hora; si ya estaba tomada responde **409** |
| `POST /pacientes/{id}/decision` | Decisión clínica: `citar_prioritario`, `derivar_urgencia`, `adelantar_control` o `mantener`. `responsable` es obligatorio |
| `POST /pacientes/{id}/cita` | Cambia el estado de la cita: `confirmada`, `atendida`, `no_asistio` o `cancelada` (cancelar libera la hora) |
| `POST /pacientes/{id}/novedad` | Comorbilidad, cambio de diagnóstico, datos de riesgo, fallecimiento o atendido |
| `GET /boxes` | Horas libres de cada box, propuestas en el orden de la lista. Cada fila trae `estado_cita` |
| `GET /disponible` | Para un médico con horas libres: a quiénes atender |
| `GET /kpis` | Horas del evento a la evaluación, citas por estado, horas recuperadas, contactabilidad y kappa con su n |
| `POST /importar`, `GET /plantillas/{tabla}` | Carga de Excel/CSV |
| `GET /catalogo` | Diagnósticos, comunas, previsiones y otros valores para los formularios |
| `GET /health` | Estado de la API: `fecha_hoy`, `modo`, `datos: "sinteticos"` |

**Estados de una cita:** propuesta (no bloquea la hora) → reservada → confirmada → atendida o no asistió. Si se cancela,
la hora queda libre.

## 7. Pantallas del front
- **Hoy:** tiene un selector de especialidad. "Todas" es la vista de coordinación; si se elige una, el especialista ve
  solo lo suyo. Muestra:
  - las descompensaciones graves con evaluación pendiente, **agrupadas por especialidad**, con los días desde el evento,
    la marca de atrasada, las horas libres de esa especialidad y los botones de llamada;
  - "Avisar al especialista", también agrupado por especialidad (descompensados cuyo diagnóstico no tiene fila en la tabla).
- Arriba a la derecha, cada usuario escribe **su nombre y cargo**. Se guarda en el navegador y queda registrado en cada
  acción (trazabilidad).
- La agenda sintética de los box llega solo hasta el 13-10. Después de esa fecha se usa como "agenda de referencia" y la
  pantalla lo dice.
- **Gestión de box:** propuestas y citas con sus estados, y el mapa de los box.
- **Tengo horas libres:** el médico indica su horario y la app le dice a quiénes atender.
- **Lista de espera:** tabla con filtros. La ficha del paciente tiene cuatro pestañas:
  - *Resumen:* cómo se decidió su lugar, decisión médica, llamada y resumen generado con IA;
  - *Puntaje:* desglose LACE y fundamento de la prioridad con fuentes;
  - *Registrar:* informe con cámara, novedades y simulación de eventos;
  - *Historia:* línea de tiempo.
- **Indicadores**, **Cargar datos** (Excel/CSV) y **Criterios** (fuentes con enlaces).
- **Modo demostración:** un control deslizante permite ver la lista en fechas anteriores (cada 14 días, desde abril).
- Arriba hay una franja fija: "Datos sintéticos de demostración".

## 8. Datos
- Dataset **sintético** del hospital: 500 pacientes, 7 especialidades, eventos hasta el 2026-10-13. El archivo principal es
  `data/perfiles.json`, con un objeto por paciente que incluye `lista_espera`, `eventos_clinicos`, `mediciones` y `citaciones`.
- **`data/` nunca va al repo** (está en `.gitignore`), igual que los CSV, `box.json` y `.env`.
- La app publicada **no tiene autenticación**: no se deben subir datos reales de pacientes.
- **Pacientes de demo:**
  - 00002: angina; sube a alta tras una urgencia y una hospitalización;
  - 00001: deterioro progresivo; PHQ-9 de 4 a 19;
  - 00028: mejora; el sistema no le baja la prioridad solo;
  - 00020: 2 inasistencias;
  - 00009: fallece y sale de la lista.
- Con la fecha real aparecen unas 17 descompensaciones graves, todas "atrasadas", porque el dataset no trae evaluaciones.
  Para mostrar el plazo de 72 h en la demo, conviene simular un evento nuevo.

## 9. Cómo correrlo
```powershell
# API local (desde ambulatorio-dinamico/)
$env:LOCAL="1"; $env:DATA_DIR="$PWD\data"; $env:FECHA_REFERENCIA="hoy"   # opcional: AWS_PROFILE, MODEL_ID, BEDROCK_REGION
python -X utf8 lambda\local_server.py          # http://localhost:3001

# Front
cd front; $env:VITE_API_URL="http://localhost:3001"; npm run dev -- --port 5174

# Tests (pytest no está instalado: las funciones test_* se pueden correr con un runner simple o instalando pytest)
python -X utf8 -m pytest tests -q

# Publicar en AWS (perfil "hack" con credenciales temporales vigentes)
powershell -ExecutionPolicy Bypass -File scripts\deploy_aws.ps1           # backend + datos + página
powershell -ExecutionPolicy Bypass -File scripts\deploy_aws.ps1 -SoloFront

# Dejar la demo publicada en su estado inicial (borra lo registrado desde la app en DynamoDB)
python scripts\limpiar_demo.py            # solo muestra cuántos registros hay
python scripts\limpiar_demo.py --borrar   # borra todo
```
- **Producción:** página en https://main.d2jvqnf67i4lks.amplifyapp.com y API en https://prpq37get4.execute-api.us-east-1.amazonaws.com
  (región us-east-1, cuenta del evento).
- **Credenciales:** son temporales y se renuevan en el portal SSO del evento (Access keys → "Option 2"). Se guardan en
  `~/.aws/credentials` como perfil `[hack]`. **Nunca se pegan en el chat ni se suben al repo.**
- El script de deploy arma siempre un paquete limpio de la Lambda (incluye Pydantic para Linux ARM). No reutilices carpetas
  viejas: una vez faltó `typing_extensions` y la Lambda dejó de funcionar.

## 10. Reglas para trabajar en el código
- Responde en **español chileno**, directo y sin relleno.
- Haz cambios chicos que no rompan lo que funciona. Si propones algo grande, avisa antes.
- **No agregues librerías nuevas sin preguntar.**
- Explica brevemente cada cambio: el equipo tiene que poder defender el código en la pre-evaluación técnica.
- No cambies los campos de `contrato.md` sin avisar.
- Después de cambiar algo: corre los tests y compila el front (`npx vite build`). Si cambió el motor, regenera el mock
  (`python scripts/generar_mock.py data`).
- Para PowerShell 5.1: no uses `&&`; escribe el YAML **sin BOM**; arma los zip con `/` y no con `\`.

## 11. Historial reciente
Una revisión externa criticó la primera versión y se corrigió todo (commit `6d07669`):
- fecha real de Chile y franja de datos sintéticos;
- "riesgo vital" cambiado a "descompensación grave: requiere evaluación", con plazo de 72 h;
- la llamada separada de la decisión clínica;
- estados explícitos de cita;
- GES como "verificar";
- LACE experimental y solo para desempatar;
- equivalencias de la tabla marcadas "a validar";
- indicadores que miden resultados en vez de afirmar "Cumple";
- capacidad por especialidad y pestaña "Gestión de box".

**Cambio de contrato:** el resultado de llamada `se_mantiene` ya no existe; ahora es la decisión `mantener` en `/decision`.

## 12. Pendiente
1. Guion de la demo de punta a punta para el pitch:
   1. llega un informe y se resalta la frase clave;
   2. el equipo valida el evento y cambia la prioridad;
   3. se busca una hora compatible y se confirma la cita;
   4. la agenda, la historia y los indicadores se actualizan.
2. Grabar el video de respaldo y ensayar.
3. Solo pulido visual después del jueves a las 15:00. Nada de funcionalidades nuevas.
