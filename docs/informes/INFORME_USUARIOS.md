# Ambulatorio Dinámico HLF — Informe para usuarios

Para quien recibe la herramienta sin formación técnica: equipo clínico, gestión de la lista, jefaturas y el equipo de
AWS que acompañará la integración con el hospital. Explica para qué sirve, cómo funciona, qué hace la inteligencia
artificial (IA) y qué hace el especialista, y trae una **guía paso a paso** para probarla y comprobar que funciona.

> Todos los datos son **sintéticos**: no corresponden a pacientes reales. La versión de este informe corre en un
> computador, sin necesidad de una cuenta de AWS.

---

## 1. Para qué sirve

En el Hospital Clínico Dra. Eloísa Díaz La Florida, cuando llega una interconsulta a una especialidad, un especialista
le asigna una prioridad (alta, media o baja) y el paciente queda esperando con esa prioridad. **Si después empeora**
(va a urgencia, se hospitaliza, sale un examen alterado), nadie lo ve hasta que le toca su turno.

> "La lista de espera es una foto; la salud de las personas, una película."

Esta herramienta mantiene la lista **viva**:

1. **Recibe** cada evento clínico nuevo, venga de donde venga (la app, una planilla Excel, otro sistema del hospital).
2. **Decide** si ese evento cambia la prioridad del paciente, usando los criterios oficiales que definió el equipo
   médico (tabla de priorización del hospital, normas del Ministerio de Salud, garantías GES).
3. **Documenta** cada decisión: qué cambió, por qué, con qué información y qué fuente (con su versión).
4. **Un especialista revisa** las decisiones y dice si fueron adecuadas o incorrectas, con su motivo.
5. **El sistema aprende** de esas revisiones, siempre con aprobación de una jefatura.

## 2. Cómo funciona, en simple

| Paso | Qué pasa | Quién lo hace |
|---|---|---|
| Llega un evento | Una urgencia, hospitalización, examen o informe entra al sistema | Personal o sistemas del hospital |
| Se lee | Si es texto (un informe), la IA lo lee y **copia la frase exacta** que respalda cada hallazgo; el sistema comprueba que esa frase exista | IA + sistema |
| Se decide | El sistema aplica los criterios oficiales. **Solo puede subir una prioridad, nunca bajarla** | Sistema |
| Se documenta | Queda una "decisión del sistema" con su explicación y sus fuentes | Sistema |
| Se revisa | El especialista dice "adecuada" o "incorrecta", corrige si hace falta y explica por qué | Especialista |
| Se aprende | Si falta un criterio, el sistema lo **propone**; una jefatura lo aprueba y desde entonces se aplica a los casos parecidos | Jefatura |

### Qué hace la IA y qué no

- **Sí:** lee textos clínicos (informes, epicrisis, la historia del paciente) y responde preguntas cerradas,
  **copiando la frase exacta** en que se basa. El sistema verifica cada frase antes de usarla.
- **No:** no decide la prioridad. Cuando se probó dejar que la IA decidiera sola, coincidió muy poco con la tabla
  oficial. La prioridad la deciden **reglas escritas, con fuente**, que cualquiera puede revisar.
- **Si la IA falla o duda,** rigen las reglas y queda anotado. Si su lectura **bajaría** a un paciente, no lo hace:
  se lo pasa al especialista.
- **A la IA no se le envía el nombre ni el RUT** del paciente.
- En esta demostración la IA corre en **modo simulado** (un lector automático sin conexión a AWS), y así aparece rotulado.

### Qué hace el especialista

- Revisa las decisiones que el sistema le deja en su cola ("Decisiones").
- Para cada una dice **"la decisión es adecuada"** o **"la decisión es incorrecta"**; si es incorrecta, indica la
  prioridad que corresponde, el motivo (de una lista) y una explicación.
- Puede **corregir un evento** mal registrado (anularlo o marcar que no tiene relación con la enfermedad por la que
  espera), sin borrarlo.
- Todo queda a su nombre, con fecha y motivo.

### Cómo aprende el sistema (sin perder el control)

1. Cada revisión queda como **antecedente** para los casos parecidos ("en 3 casos así, los especialistas dijeron…").
2. Si un especialista dice "faltaba un criterio", el sistema **propone** una regla nueva. **Mientras está propuesta no
   cambia a nadie**: solo avisa en los casos que calzan.
3. Una **jefatura la aprueba** (o la rechaza). Desde ese día, la regla se aplica y cada decisión dice qué regla usó,
   quién la aprobó y en cuántas revisiones se basa.
4. Las correcciones "hacia abajo" (bajar una prioridad) **nunca** se vuelven regla automática: quedan para que el equipo
   médico revise la fuente oficial.

## 3. Guía paso a paso para probarla

### 3.1 Requisitos

| Necesita | Para qué | Cómo obtenerlo |
|---|---|---|
| Un computador con Windows, Mac o Linux | Correr la demostración | — |
| Python 3.11 o superior | El "motor" de la herramienta | https://www.python.org/downloads (en Windows, marcar "Add Python to PATH") |
| Node.js 20 o superior | La página web | https://nodejs.org (versión LTS) |
| La carpeta del proyecto | Código y datos sintéticos | Copia del repositorio |
| Conexión a internet la primera vez | Instalar componentes | — |

**No necesita** cuenta de AWS, usuario ni contraseña: en la demostración cada persona escribe su nombre y elige su rol
en la parte de arriba de la página.

### 3.2 Iniciar

1. Abra una terminal en la carpeta del proyecto (en Windows: clic derecho sobre la carpeta → "Abrir en Terminal").
2. Solo la primera vez, instale el componente de Python:
   ```
   python -m pip install -r lambda/requirements.txt
   ```
3. Inicie la herramienta:
   ```
   python scripts/demo.py
   ```
   La primera vez tarda unos minutos (instala la página). Luego se abre el navegador en **http://localhost:5174**.
   La terminal muestra un recuadro con la dirección de la página y el modo ("IA SIMULADA").
4. Para detenerla: en la terminal, **Ctrl + C**. Al volver a iniciarla, todo vuelve al estado inicial.

> Si algo falla, el mensaje de la terminal dice qué falta (por ejemplo, instalar Node.js). Si el puerto está ocupado,
> cierre otra copia de la herramienta que esté abierta.

### 3.3 Cargar los datos de ejemplo

La lista ya viene cargada con **500 pacientes sintéticos** de 7 especialidades (409 en espera al 13-10-2026). Para
probar la recepción de eventos, genere los archivos de ejemplo (en otra terminal, en la carpeta del proyecto):

```
python scripts/generar_escenarios.py
```

Quedan en la carpeta `data/demo`: un export de urgencia (`eventos_urgencia.csv`), un envío de otro sistema
(`eventos_api.json`), mediciones de laboratorio (`mediciones_laboratorio.csv`) e informes de texto (`informes/`).
El archivo `data/demo/ESPERADO.md` dice qué debe pasar con cada uno.

### 3.4 Qué hacer y qué debería ver

Arriba a la derecha, escriba **su nombre y cargo** y elija el **rol** que corresponda a cada paso. Para registrar
eventos de prueba ("Simular evento") se marca **"Explorar fechas anteriores"**: así la herramienta deja claro que es una
demostración. La revisión de la prioridad en la ficha se ve con esa opción desmarcada; la pantalla "Decisiones" funciona
siempre.

| N° | Acción | Qué debería ver |
|---|---|---|
| 1 | En **"Lista de espera"**, elija Cardiología. | La lista ordenada, con N°, nombre, diagnóstico, prioridad y días de espera. |
| 2 | Arriba, marque **"Explorar fechas anteriores"** (deje la fecha en la última). Busque **"Amapola 027"** (PAC-HLF-00027, hipertensión, prioridad baja) y ábralo. Pestaña **Registrar** → **Simular evento** → elija una **urgencia grave** (triage ESI 2) y confírmela. Luego desmarque "Explorar fechas anteriores". | Sigue en prioridad **baja**: la tabla del hospital no define qué hacer con la hipertensión descompensada. El sistema lo dice y lo deja **para revisión del especialista**. |
| 3 | Vaya a **"Decisiones"** (rol: especialista). | Aparece la decisión: qué la gatilló, la explicación, "en qué se basó" (antecedentes usados, fuentes y su versión). |
| 4 | Marque **"La decisión es incorrecta"** → prioridad **alta** → motivo **"Falta un criterio"** → explique (ej. "Hipertensión con urgencia grave requiere prioridad alta"). Guarde. | El paciente pasa a alta. El sistema informa que **propuso un criterio local** para "hipertensión + urgencia grave" y que **no cambia a nadie** hasta que una jefatura lo apruebe. |
| 5 | Vaya a **"Aprendizaje"** (rol: jefatura). Apruebe el criterio propuesto con un motivo. | El criterio pasa a **vigente**, con quién lo aprobó, desde cuándo y a cuántos pacientes aplica hoy. Cada paciente al que le cambia algo queda con su decisión documentada. La concordancia con los especialistas se actualiza (con pocos casos, marcada "solo orientativo"). |
| 6 | Con "Explorar fechas anteriores" marcado, abra otro paciente con **hipertensión y prioridad baja** (ej. **"Hortensia 181"**, PAC-HLF-00181) y simule la misma urgencia. | **Sube solo a alta**, y el fundamento cita el criterio local: quién lo aprobó y en cuántas revisiones se basa. |
| 7 | Vaya a **"Recepción de datos"** (rol: gestión). Cargue `data/demo/eventos_urgencia.csv`: primero **Revisar**, luego **Cargar**. | Antes de cargar, qué le pasará a cada paciente. Después, el **lote recibido**: 38 filas, 28 registradas, 3 repetidas, 2 rechazadas (con el motivo) y 5 de personas fuera de la lista. 6 pacientes suben de prioridad. |
| 8 | Cargue el mismo archivo otra vez. | Nada se duplica: todo aparece como **repetido**. |
| 9 | Abra un paciente con alerta (pestaña **"Empeoraron"**) → pestaña **Decisiones** de su ficha. | La historia de decisiones del paciente, cada una con su revisión. |
| 10 | Vaya a **"Criterios"** → **Fuentes y versiones**, y consulte un diagnóstico (ej. I20, angina). | Cada fuente oficial con su versión y estado de verificación, y todo lo que el sistema aplica para ese diagnóstico. |
| 11 | Vaya a **"Indicadores"**. | Decisiones registradas, pendientes, adecuadas/incorrectas, concordancia con los especialistas (con el número de casos) y el tiempo desde que llega un evento hasta que el sistema decide. |
| 12 | Todo se puede **exportar a Excel** desde cada pantalla. | Un archivo .xlsx con lo que está viendo. |

Otros casos del registro para mostrar:

| Paciente | Qué muestra |
|---|---|
| PAC-HLF-00002 (angina) | Sube de baja a alta tras una urgencia y una hospitalización (tabla del hospital, pág. 85) |
| PAC-HLF-00001 (depresión) | Deterioro progresivo: PHQ-9 de 4 a 19, con alerta clínica |
| PAC-HLF-00028 (ansiedad) | Mejora y el sistema **no** le baja la prioridad solo |
| PAC-HLF-00020 (angina) | 2 inasistencias: aviso para la gestión, sin bajar su prioridad |
| PAC-HLF-00009 (hipotiroidismo) | Fallece y sale de la lista |

## 4. Qué queda claro con la prueba

- La lista **reacciona el mismo día** a un evento grave, con una explicación que cita la fuente.
- **Ninguna prioridad baja sin una persona.**
- **Cada decisión queda documentada**: qué información se usó, de qué fuente y con qué versión.
- El especialista **juzga** cada decisión y el sistema **aprende con aprobación**, de forma visible y reversible.
- Los datos pueden llegar **por varias vías** (archivo, otro sistema, informe) y nunca se duplican.

## 5. Límites de esta versión

- **Datos sintéticos** y **sin conexión a AWS**: la IA corre simulada. La versión en AWS está escrita y revisada, pero
  aún no se ha instalado en una cuenta.
- En la demostración **el rol se elige** en pantalla; en el hospital vendrá del inicio de sesión (Amazon Cognito).
- La herramienta **no predice** quién va a empeorar: reacciona a lo que ya pasó.
- Antes de usar datos reales faltan pasos legales y de seguridad del hospital (evaluación de impacto de la Ley 21.719,
  contrato con AWS, inicio de sesión real).

## 6. Glosario

| Término | Significado |
|---|---|
| Interconsulta (SIC) | Solicitud de atención con un especialista |
| Prioridad | Alta, media o baja: qué tan pronto debe atenderse |
| Decisión del sistema | Registro de cada vez que el sistema evaluó a un paciente, con su explicación y fuentes |
| Veredicto | Lo que dice el especialista de una decisión: adecuada o incorrecta |
| Criterio local | Regla nueva que nace de las revisiones y aprueba una jefatura |
| Fuente | Documento oficial que respalda una regla (tabla del hospital, norma del Ministerio, guía clínica) |
| Lote | Un envío de datos (un archivo, un mensaje de otro sistema) |
| Descompensación grave | Empeoramiento importante de la enfermedad por la que espera; el médico debe revisarlo en 72 horas |
