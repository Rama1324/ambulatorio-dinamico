# Evaluación de los criterios clínicos por enfermedad

Bedrock `us.anthropic.claude-sonnet-5` · 46 enfermedades · 138 notas de nivel + 16 notas de urgencia, escritas por Claude parafraseando el primer criterio de cada nivel (no copia sus palabras). Clasificación con `lambda/criterios.py` (3 lecturas, citas verificadas, 2 de 3).

| Resultado | Notas | % |
|---|---|---|
| correcto | 135 | 97.8 |
| sobre | 1 | 0.7 |
| sub | 0 | 0.0 |
| no_determinable | 2 | 1.4 |

| Nivel esperado | Correcto | Sobretriage | Subtriage | No determinable |
|---|---|---|---|---|
| alta | 46 | 0 | 0 | 0 |
| media | 45 | 0 | 0 | 1 |
| baja | 44 | 1 | 0 | 1 |

- **Urgencias detectadas:** 16 de 16.
- **Urgencias falsas** en notas de nivel media o baja: 0.
- Recordatorio: en la app el criterio **solo sube** la prioridad; un subtriage aquí significa que el paciente se queda con la prioridad que ya tenía (no baja). Un 'no determinable' tampoco cambia nada.

## Casos que no coinciden

- `oftalmologia_02.baja` esperado **baja**, obtuvo **media** · Paciente con hallazgo incidental de degeneración lattice periférica bilateral, asintomático, detectado en fondo de ojo de control. Se solicita evaluación por oftalmología para seguimiento y confirmación de que no requier
- `otorrinolaringologia_07.media` esperado **media**, obtuvo **no determinable** · Paciente con diagnóstico confirmado de colesteatoma, actualmente asintomático y sin signos de complicación en la evaluación otoscópica. Se encuentra clínicamente estable, por lo que se solicita evaluación por Otorrinolar
- `urologia_07.baja` esperado **baja**, obtuvo **no determinable** · Paciente sin antecedentes relevantes, que en examen de orina de rutina presentó eritrocitos aislados, sin síntomas urinarios asociados. Se solicitó control con nuevo sedimento urinario, el cual resultó normal, por lo que
