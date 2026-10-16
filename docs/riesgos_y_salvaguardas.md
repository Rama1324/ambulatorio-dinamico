# Riesgos legales y salvaguardas (para la slide de factibilidad)

Hospital Clínico Dra. Eloísa Díaz Inzunza (La Florida). Al 16-10-2026. No es asesoría legal.

| Riesgo | Norma | Salvaguarda que ya funciona (se puede mostrar en la demo) | Antes de usar datos reales |
|---|---|---|---|
| Decisión automatizada sobre el paciente | Ley 21.719, art. 8 bis | El sistema solo **sube**; bajar siempre lo decide una persona. Cada cambio muestra su regla y su fuente (pestaña Fundamento). El paciente puede **pedir revisión humana**: queda registrado y pasa a "Decisión del especialista". Confirmar o cambiar exige nombre y motivo. | Informar a los pacientes que existe el sistema. |
| Datos de salud fuera de Chile | Ley 21.719, arts. 27–28 | La IA **no recibe nombre ni RUT**: se ocultan antes de enviar el texto a Bedrock. | Cláusulas contractuales tipo con AWS, o la región AWS Chile cuando exista; opt-out de servicios de IA para Textract. |
| Acceso sin autorización | Ley 20.584; Ley 21.719, arts. 14 quinquies y sexies | Datos 100 % sintéticos; aviso visible en la página. | Login con roles (Amazon Cognito), registro de accesos y cifrado. |
| Paciente que empeora y no sube | Responsabilidad del servicio | Recalcula al instante con cada evento; aviso de descompensación grave hasta que revisa el especialista; trazabilidad completa. | Integración automática con urgencia, hospitalización y laboratorio. |
| Discriminación indirecta | Ley 21.719 (licitud, no discriminación) | La inasistencia solo genera una bandera de gestión; no cambia la prioridad clínica. El nivel socioeconómico no se usa. | — |
| Garantías GES | Ley 19.966 | Bandera "GES: verificar plazo". | GES como restricción del orden, con la fecha real del hito (hoy el cálculo es aproximado). |
| Trámites previos | Ley 21.719, art. 15 ter | — | Evaluación de impacto, a cargo del hospital. |
| Ciberseguridad | Ley 21.663 | — | Exigencias contractuales y reporte de incidentes. |

**Frase para el jurado:** "El hospital sigue siendo responsable. El sistema propone y explica cada cambio con su fuente,
nunca baja a nadie solo, y el paciente puede pedir que una persona revise su prioridad."
