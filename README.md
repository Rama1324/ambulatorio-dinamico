# Ambulatorio Dinámico HLF

**AWS Breaking Barriers Chile 2026 · Desafío Hospital Clínico Dra. Eloísa Díaz Inzunza (La Florida)**

> "La lista de espera es una foto; la salud de las personas, una película."

Lista de espera de consultas de especialidad que **se reprioriza sola cuando el paciente empeora** (urgencias,
hospitalizaciones, exámenes alterados) usando **solo reglas oficiales**: tabla de priorización SSMSO 2025 del HLF,
criterios MINSAL Ord. 536/2025 y garantías GES (LACE solo como desempate experimental). Las fotos de informes se leen
con Amazon Textract + reglas + Pydantic; Bedrock solo redacta. **El equipo clínico decide** y todo queda trazado.

En el dataset del hospital (13-10-2026): los 17 pacientes con descompensación grave estaban en la **posición mediana
N° 171** de la lista congelada (16 fuera de los primeros 50); con este sistema quedan en la **mediana N° 9** y la lista se
actualiza en el momento en que entra el dato.

## MVP (noviembre 2026): lista activa, decisiones documentadas y aprendizaje con el especialista
Cada evento clínico que llega (app, Excel/CSV, API para sistemas, zona de carga S3, informe) se evalúa con criterios con
fuente y la IA (Bedrock) que **lee y cita**; cada decisión queda **documentada** con la información, fuentes y versiones
usadas; un especialista dice si fue **adecuada o incorrecta** y el sistema **aprende** (criterio local propuesto →
aprobado por jefatura → aplicado y citado). Nunca baja una prioridad sola.

| Documento | Para quién |
|---|---|
| [`docs/informes/INFORME_USUARIOS.md`](docs/informes/INFORME_USUARIOS.md) | Propósito, IA y especialista, guía paso a paso para probarla |
| [`docs/informes/INFORME_TECNICO.md`](docs/informes/INFORME_TECNICO.md) | Arquitectura, AWS, integraciones, priorización, verificación, diferencias con el anexo técnico |
| [`docs/DECISIONES.md`](docs/DECISIONES.md) | 12 decisiones de arquitectura con alternativas, mediciones y costos |
| [`DEPLOY.md`](DEPLOY.md) · [`docs/operacion/RUNBOOK.md`](docs/operacion/RUNBOOK.md) | Despliegue en AWS y operación |
| [`contrato.md`](contrato.md) | Contrato de la API |

**Probarlo en un comando** (sin AWS, IA simulada): `python scripts/demo.py` → http://localhost:5174

## Estructura
```
ambulatorio-dinamico/
├── lambda/                API (Lambda Python 3.12; única dependencia: pydantic)
│   ├── app.py             enrutador HTTP: identidad y permisos, CORS, gzip; delega en el rutear() de cada módulo
│   ├── seguridad.py       identidad desde el JWT de Cognito, permisos por ruta y rol
│   ├── datos.py           almacén: ítems por paciente en DynamoDB (almacen_dynamo.py) o en memoria en local
│   ├── ingesta.py         una sola tubería de entrada: app, Excel/CSV, API para sistemas, zona de carga S3, cola SQS
│   ├── bitacora.py        cada decisión documentada (dictamen) y la cola de revisión del especialista
│   ├── aprendizaje.py     veredictos, precedentes, criterios locales con aprobación, enmiendas
│   ├── base_conocimiento.py  fuentes médicas con versión y huella (manifiesto en conocimiento/)
│   ├── puntaje.py         motor de priorización (reglas oficiales con fuente)
│   ├── rubrica.py · decisor.py · controles.py · algoritmo.py · evaluacion_ia.py · cliente_ia.py   la IA lee y cita; el código decide
│   ├── criterios.py · combinaciones.py · lector_documento.py · informe.py · lectura_informe.py      lectura de textos e informes
│   ├── lista.py · indicadores.py · catalogo.py · acciones.py · ingreso.py · importar.py · explicar.py · privacidad.py
│   └── local_server.py    corre la API en localhost:3001 sin AWS
├── front/src/             React + Vite + Tailwind
│   ├── pantallas/         Lista · Lista detallada · Empeoraron · Decisiones · Aprendizaje · Recepción de datos · Indicadores · Criterios y fuentes
│   ├── ficha/             ficha del paciente (resumen, gestión, registrar, decisiones, fundamento, historia)
│   └── api.js · auth.js · permisos.js · excel.js · componentes/
├── tests/                 327 pruebas (pytest)
├── scripts/               demo.py · generar_escenarios.py · cargar_registro.py · desplegar.py/.sh · deploy_aws.ps1 · validar_plantilla.py · empaquetar_conocimiento.py · medir_escala.py
├── docs/                  informes/ · DECISIONES.md · diseno/ · operacion/RUNBOOK.md · conocimiento/ · investigacion/
├── data/                  dataset sintético del hospital: perfiles.json y CSV (NO van a git, ver abajo)
├── template.yaml · samconfig.toml   infraestructura AWS (SAM): ambientes prueba y prod
├── contrato.md            contrato de la API
└── DEPLOY.md              despliegue en AWS
```

## Datos de prueba
La demo usa el **dataset sintético que entregó el hospital** (500 pacientes, sin personas reales), incluido en
`docs/Datasets de ejemplo/` junto a su diccionario de datos. `python scripts/demo.py` lo copia a `data/` la primera vez.
Las guías y escenarios citan pacientes concretos de ese registro.

## Probar en local
```bash
python scripts/demo.py                 # API (3001) + página (5174), IA simulada; --reglas, --bedrock <perfil>, --hoy
python -m pytest -q tests              # 327 pruebas
python scripts/generar_escenarios.py   # archivos de ejemplo en data/demo (con ESPERADO.md)
```

## KPIs del hospital
| KPI | Cómo se cubre |
|---|---|
| Reevaluación < 72 h tras un evento | Cada evento recalcula la lista al registrarse (~0,1 s) |
| Cobertura 100% con criterio común | Toda la lista con la misma tabla oficial y el mismo orden MINSAL |
| Concordancia κ ≥ 0,70 | Kappa calculado en vivo entre la propuesta y las revisiones del especialista (pestaña Indicadores) |

Datos: dataset sintético entregado por el HLF (500 pacientes, sin RUT ni nombres reales).
