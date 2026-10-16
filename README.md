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

## Estructura
```
ambulatorio-dinamico/
├── lambda/                API (una Lambda Python; única dependencia: pydantic)
│   ├── app.py             enrutador HTTP (solo decide qué función atiende cada ruta)
│   ├── datos.py           fecha de trabajo, registro del hospital (S3) y registros del equipo (DynamoDB)
│   ├── catalogo.py        vocabularios cerrados (contacto, decisión, ajuste, gestión) y catálogo del front
│   ├── lista.py           lista priorizada, ficha, historia y estadísticas
│   ├── acciones.py        lo que registra el equipo: eventos, revisiones, contactos, decisiones, gestión, ajustes
│   ├── ingreso.py         ingreso de pacientes y carga de Excel/CSV (con el impacto de la carga)
│   ├── lectura_informe.py lectura de informes (texto o foto) con IA
│   ├── indicadores.py     KPIs (kappa, cobertura, espera, contactabilidad)
│   ├── evaluacion_ia.py   algoritmo con rúbrica (ALGORITMO=rubrica) y barrido nocturno
│   ├── puntaje.py         motor de priorización (reglas oficiales)
│   ├── criterios.py · combinaciones.py · lector_documento.py   la IA lee y cita; el código verifica y decide
│   ├── informe.py · modelos.py · explicar.py · importar.py
│   └── local_server.py    corre la API en localhost:3001 sin AWS
├── front/src/             React + Vite + Tailwind
│   ├── App.jsx            encabezado, navegación y estado compartido (fecha, especialidad, filtros)
│   ├── pantallas/         ListaSimple · ListaDetallada · Alertas · Indicadores · CargarDatos · Criterios · NuevoPaciente
│   ├── ficha/             Ficha del paciente: Acciones (contacto, gestión, ajuste, decisión, novedad) · Evolucion · Informe
│   ├── componentes/       comunes.jsx (Caja, Icono, Prioridad, Indicador, Filtro)
│   └── api.js · excel.js · constantes.js · util.js
├── tests/                 131 pruebas (API de punta a punta, criterios, combinaciones, lector, evidencia)
├── scripts/               deploy_aws.ps1 · iniciar_demo.ps1 · limpiar_demo.py · evaluar_*.py (evaluaciones con Claude)
├── docs/                  criterios_oficiales.md (todas las fuentes) · arquitectura.md · prompts_bedrock.md
├── data/                  perfiles.json y CSV (NO van a git)
├── template.yaml          infraestructura AWS (SAM): Lambda, API Gateway, S3, DynamoDB, permisos Bedrock
├── amplify.yml            build del front en AWS Amplify
├── contrato.md            contrato de la API
└── DEPLOY.md              cómo correr en local y deployar
```

## Probar en local
```powershell
python -m pytest -q tests
$env:LOCAL="1"; $env:DATA_DIR="data"; python lambda/local_server.py      # API en localhost:3001
cd front; npm install; npm run dev                                         # app en localhost:5173
```
(con `front/.env.local` → `VITE_API_URL=http://localhost:3001`)

## KPIs del hospital
| KPI | Cómo se cubre |
|---|---|
| Reevaluación < 72 h tras un evento | Cada evento recalcula la lista al registrarse (~0,1 s) |
| Cobertura 100% con criterio común | Toda la lista con la misma tabla oficial y el mismo orden MINSAL |
| Concordancia κ ≥ 0,70 | Kappa calculado en vivo entre la propuesta y las revisiones del especialista (pestaña Indicadores) |

Datos: dataset sintético entregado por el HLF (500 pacientes, sin RUT ni nombres reales).
