# Ambulatorio Dinámico HLF

**AWS Breaking Barriers Chile 2026 · Desafío Hospital Clínico Dra. Eloísa Díaz La Florida**

> "La lista de espera es una foto; la salud de las personas, una película."

Sistema de **priorización clínica evolutiva**: cada evento clínico (urgencia, hospitalización, examen alterado, mejora) **reevalúa en milisegundos** la prioridad del paciente en la lista de espera, **explica por qué** (reglas trazables + redacción con Amazon Bedrock) y deja que **el equipo clínico confirme o ajuste**. Incluye la vista de **uso de box** para llenar cupos libres con los pacientes de mayor necesidad.

- Arquitectura: [docs/arquitectura.md](docs/arquitectura.md)
- API: [contrato.md](contrato.md)
- Correr y deployar: [DEPLOY.md](DEPLOY.md)

| KPI del hospital | Cómo lo cubrimos |
|---|---|
| Reevaluación < 72 h tras un evento | `POST /eventos` recalcula en < 1 s |
| Cobertura 100% con criterio común | Toda la lista se recalcula con las mismas reglas |
| Concordancia κ ≥ 0,70 con experto | Pesos configurables; botón Ajustar registra el criterio clínico para calibrar |
| Trazabilidad | Cada puntaje trae su desglose; cada revisión queda con motivo y fecha |

Datos: dataset sintético entregado por el HLF (500 pacientes, sin RUT ni nombres reales).
