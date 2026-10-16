# Evaluación de las combinaciones de riesgo

Bedrock `us.anthropic.claude-sonnet-5` · 45 casos escritos a mano (35 con combinación, 10 trampa: negaciones, base ausente, eventos banales) · `lambda/combinaciones.py` (3 lecturas, citas verificadas, base contra el registro, 2 de 3).

- **Urgencias detectadas:** 26 de 26 (lo más importante: no dejar pasar un riesgo vital).
- **Combinación esperada detectada:** 34 de 35.
- **Casos trampa sin detección falsa:** 10 de 10.
- Detecciones adicionales a la esperada en casos con combinación: 2.

| Caso | Esperado | Obtenido |
|---|---|---|
| dm_una | pie_diabetico_lesion | pie_diabetico_lesion |
| dm_ulcera_infectada | pie_diabetico_infeccion | pie_diabetico_infeccion, pie_diabetico_lesion |
| dm_gangrena | pie_diabetico_infeccion | pie_diabetico_infeccion |
| dm_cad | dm_cetoacidosis | dm_cetoacidosis |
| dm_hipo | dm_hipoglucemia_grave | dm_hipoglucemia_grave |
| tac_caida | anticoagulado_tec | anticoagulado_tec |
| tac_doac | anticoagulado_tec | anticoagulado_tec |
| tac_sangrado | anticoagulado_sangrado | anticoagulado_sangrado |
| quimio_fiebre | inmunosuprimido_fiebre | inmunosuprimido_fiebre |
| trasplante_fiebre | inmunosuprimido_fiebre | inmunosuprimido_fiebre |
| cancer_medular | cancer_compresion_medular | cancer_compresion_medular, lumbago_cauda_equina |
| cancer_dolor_espalda | cancer_dolor_espalda | cancer_dolor_espalda |
| cauda | lumbago_cauda_equina | lumbago_cauda_equina |
| cadera | adulto_mayor_caida_cadera | adulto_mayor_caida_cadera |
| delirium | adulto_mayor_confusion | adulto_mayor_confusion |
| preeclampsia | embarazo_hipertension | embarazo_hipertension |
| valproato | embarazo_teratogeno | embarazo_teratogeno |
| hiperk | erc_hiperkalemia | erc_hiperkalemia |
| cirrosis_sangre | cirrosis_hemorragia | cirrosis_hemorragia |
| cirrosis_pbe | cirrosis_infeccion_encefalopatia | cirrosis_infeccion_encefalopatia |
| cirrosis_encefalo | cirrosis_infeccion_encefalopatia | cirrosis_infeccion_encefalopatia |
| ic_neumonia | ic_infeccion | ic_infeccion |
| sca | coronario_dolor_reposo | coronario_dolor_reposo |
| acv | neuro_deficit_subito | neuro_deficit_subito |
| trueno | cefalea_alarma | cefalea_alarma |
| status | epilepsia_crisis_prolongada | epilepsia_crisis_prolongada |
| glaucoma | glaucoma_agudo | glaucoma_agudo |
| tormenta | tiroides_crisis | tiroides_crisis |
| hipercalcemia | cancer_hipercalcemia | cancer_hipercalcemia |
| septica | articulacion_septica | articulacion_septica |
| suicida | riesgo_suicida | riesgo_suicida |
| depre_alcohol | depresion_alcohol_perdida | depresion_alcohol_perdida |
| asma | asma_epoc_grave | asma_epoc_grave |
| peso | erge_alarma, perdida_peso_inexplicada | perdida_peso_inexplicada ✗ |
| dm_base_en_texto | pie_diabetico_lesion | pie_diabetico_lesion |
| no_dm_una | — | — |
| neg_tec | — | — |
| neg_fiebre | — | — |
| neg_dolor | — | — |
| banal | — | — |
| joven_caida | — | — |
| dedo | — | — |
| aspirina_sola | — | — |
| dm_pie_sano | — | — |
| no_embarazo | — | — |

Alertas de combinaciones no listadas (red de seguridad):

