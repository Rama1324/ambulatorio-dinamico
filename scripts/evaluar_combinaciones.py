"""Evaluación de las combinaciones de riesgo (lambda/combinaciones.py) con Bedrock real, con casos escritos a mano.

Cada caso: lo que se sabe del paciente (CIE-10 de la SIC, comorbilidades, edad) + un texto + las combinaciones que DEBEN
detectarse (vacío = ninguna). Incluye casos trampa: negaciones, base ausente, base solo en el texto, eventos banales.
Mide: sensibilidad para urgencias (lo más importante: no dejar pasar un riesgo vital), detecciones falsas y exactitud.
Uso: $env:AWS_PROFILE="hack"; python -X utf8 scripts/evaluar_combinaciones.py   (escribe docs/algoritmo/EVALUACION_COMBINACIONES.md)
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import combinaciones  # noqa: E402
import rubrica  # noqa: E402


def P(cie, texto_dx, edad=55, sexo="F", comorb=()):
    return {"paciente": {"edad": edad, "sexo": sexo, "comorbilidades": [{"cie10": c, "nombre": n} for c, n in comorb]},
            "lista_espera": {"diagnostico_cie10": cie, "diagnostico_texto": texto_dx}}


DM = P("E11", "Diabetes mellitus tipo 2", 62)
CASOS = [
    # --- deben detectarse ---
    ("dm_una", DM, "Control CESFAM. Presenta uña encarnada del ortejo mayor izquierdo, con dolor y enrojecimiento leve.", {"pie_diabetico_lesion"}),
    ("dm_ulcera_infectada", DM, "Úlcera en talón derecho de 3 semanas, hoy con secreción purulenta, mal olor y celulitis que sube al tobillo.", {"pie_diabetico_infeccion"}),
    ("dm_gangrena", DM, "Ortejo del pie derecho de color negro, frío, con zona necrótica.", {"pie_diabetico_infeccion"}),
    ("dm_cad", DM, "Consulta por vómitos persistentes desde ayer, respiración rápida y profunda, glicemia capilar 480 mg/dl con cetonuria positiva.", {"dm_cetoacidosis"}),
    ("dm_hipo", DM, "Familiar refiere dos episodios este mes de hipoglucemia con pérdida de conciencia que requirieron ayuda de terceros.", {"dm_hipoglucemia_grave"}),
    ("tac_caida", P("I48", "Fibrilación auricular", 78, comorb=[("Z92", "Usuario de anticoagulante oral")]),
     "Usuario de acenocumarol. Ayer se cayó en el baño y se golpeó la cabeza; hoy está asintomático.", {"anticoagulado_tec"}),
    ("tac_doac", P("I10", "Hipertensión esencial", 70), "Paciente en tratamiento con apixaban. Sufrió caída de su altura con golpe frontal.", {"anticoagulado_tec"}),
    ("tac_sangrado", P("I10", "Hipertensión esencial", 74), "Usuaria de warfarina. Refiere deposiciones negras desde hace dos días y mareos.", {"anticoagulado_sangrado"}),
    ("quimio_fiebre", P("C50", "Cáncer de mama", 48), "Paciente en quimioterapia (último ciclo hace 8 días) consulta por fiebre de 38,7 °C y calofríos.", {"inmunosuprimido_fiebre"}),
    ("trasplante_fiebre", P("N18", "Enfermedad renal crónica", 52), "Trasplantado renal en tratamiento con tacrolimus e inmunosupresores, hoy con fiebre de 38,5.", {"inmunosuprimido_fiebre"}),
    ("cancer_medular", P("C61", "Cáncer de próstata", 71, "M"), "Dolor lumbar intenso hace 2 semanas, desde ayer con debilidad en ambas piernas y dificultad para orinar.", {"cancer_compresion_medular"}),
    ("cancer_dolor_espalda", P("C50", "Cáncer de mama operado", 63), "Dolor dorsal progresivo de 6 semanas, que la despierta de noche y empeora al toser. Sin déficit motor.", {"cancer_dolor_espalda"}),
    ("cauda", P("M54", "Lumbago", 45, "M"), "Lumbago con ciática bilateral, desde ayer adormecimiento en la zona genital y no logra controlar la orina.", {"lumbago_cauda_equina"}),
    ("cadera", P("M17", "Gonartrosis", 82), "Se cayó en la calle, presenta dolor intenso en la cadera izquierda y no puede apoyar la pierna.", {"adulto_mayor_caida_cadera"}),
    ("delirium", P("I10", "Hipertensión esencial", 86), "Hija refiere que desde hace dos días está confusa, desorientada y somnolienta, lo que no es habitual en ella.", {"adulto_mayor_confusion"}),
    ("preeclampsia", P("O24", "Diabetes gestacional", 31), "Embarazo de 32 semanas, presión 150/100, cefalea intensa y visión con puntos luminosos.", {"embarazo_hipertension"}),
    ("valproato", P("G40", "Epilepsia", 27), "Usuaria de ácido valproico por epilepsia, refiere test de embarazo positivo, cursando 6 semanas.", {"embarazo_teratogeno"}),
    ("hiperk", P("N18", "Enfermedad renal crónica etapa 4", 69, "M"), "Examen de control: potasio 6,8 mEq/L, refiere debilidad muscular.", {"erc_hiperkalemia"}),
    ("cirrosis_sangre", P("K70", "Enfermedad hepática alcohólica", 58, "M"), "Paciente con cirrosis presenta vómito con sangre roja abundante esta mañana.", {"cirrosis_hemorragia"}),
    ("cirrosis_pbe", P("K70", "Enfermedad hepática alcohólica", 60, "M"), "Cirrótico con ascitis, ahora con fiebre y dolor abdominal difuso.", {"cirrosis_infeccion_encefalopatia"}),
    ("cirrosis_encefalo", P("K70", "Enfermedad hepática alcohólica", 64, "M"), "Esposa refiere que está confuso, somnoliento y con conducta extraña desde ayer.", {"cirrosis_infeccion_encefalopatia"}),
    ("ic_neumonia", P("I50", "Insuficiencia cardíaca", 77), "Cursa con neumonía tratada con amoxicilina, con aumento de la disnea y edema de piernas.", {"ic_infeccion"}),
    ("sca", P("I20", "Angina de pecho", 66, "M"), "Refiere dolor opresivo en el pecho en reposo, de 30 minutos, que se irradia al brazo izquierdo.", {"coronario_dolor_reposo"}),
    ("acv", P("I10", "Hipertensión esencial", 72, "M"), "Desde hace una hora presenta debilidad brusca del brazo derecho y dificultad para hablar.", {"neuro_deficit_subito"}),
    ("trueno", P("G43", "Migraña", 39), "Cefalea súbita, la peor de su vida, que llegó al máximo en un minuto, distinta a su migraña habitual.", {"cefalea_alarma"}),
    ("status", P("G40", "Epilepsia", 33, "M"), "Hoy presentó una crisis convulsiva de más de 10 minutos que no cedía.", {"epilepsia_crisis_prolongada"}),
    ("glaucoma", P("H40", "Glaucoma", 68), "Dolor intenso en el ojo derecho, ojo rojo, visión borrosa con halos y vómitos.", {"glaucoma_agudo"}),
    ("tormenta", P("E05", "Hipertiroidismo", 41), "Con hipertiroidismo mal controlado presenta fiebre, agitación y taquicardia marcada.", {"tiroides_crisis"}),
    ("hipercalcemia", P("C34", "Cáncer de pulmón", 69, "M"), "Calcio sérico 13,8 mg/dl, con confusión y vómitos.", {"cancer_hipercalcemia"}),
    ("septica", P("M17", "Gonartrosis", 70), "Rodilla derecha roja, caliente, muy hinchada y dolorosa desde ayer, con fiebre.", {"articulacion_septica"}),
    ("suicida", P("F32", "Episodio depresivo", 35), "Refiere ideación suicida con plan: ha pensado en tomar todas sus pastillas este fin de semana.", {"riesgo_suicida"}),
    ("depre_alcohol", P("F32", "Episodio depresivo", 50, "M"), "Desde la muerte de su esposa hace un mes ha aumentado el consumo de alcohol a diario.", {"depresion_alcohol_perdida"}),
    ("asma", P("J45", "Asma", 28), "Tres consultas en urgencia en el último mes por crisis asmática, una con hospitalización.", {"asma_epoc_grave"}),
    ("peso", P("K21", "Reflujo gastroesofágico", 61, "M"), "Baja de peso de 8 kg en 3 meses sin buscarlo, con dificultad progresiva para tragar sólidos.", {"erge_alarma", "perdida_peso_inexplicada"}),
    ("dm_base_en_texto", P("M75", "Síndrome de hombro doloroso", 59), "Paciente diabético insulinorrequirente. Presenta herida en la planta del pie que no cicatriza.", {"pie_diabetico_lesion"}),
    # --- NO deben detectarse (casos trampa) ---
    ("no_dm_una", P("M17", "Gonartrosis", 50), "Presenta uña encarnada del ortejo mayor, con leve dolor.", set()),
    ("neg_tec", P("I10", "Hipertensión esencial", 75), "Usuario de warfarina. Niega caídas ni golpes en la cabeza.", set()),
    ("neg_fiebre", P("C50", "Cáncer de mama", 50), "En quimioterapia, afebril, sin calofríos, buena tolerancia.", set()),
    ("neg_dolor", P("I20", "Angina de pecho", 64, "M"), "Control: sin dolor torácico desde hace meses, asintomático.", set()),
    ("banal", P("E66", "Obesidad", 40), "Consulta por resfrío común de 3 días, sin fiebre.", set()),
    ("joven_caida", P("M75", "Síndrome de hombro doloroso", 30, "M"), "Se cayó jugando fútbol, con dolor leve de tobillo, camina normal.", set()),
    ("dedo", P("I50", "Insuficiencia cardíaca", 60), "Consulta en urgencia por dolor en dedo índice tras golpe con puerta. Alta con paracetamol.", set()),
    ("aspirina_sola", P("I25", "Cardiopatía isquémica", 70, "M"), "Toma solo aspirina 100 mg. Se golpeó la cabeza levemente, sin síntomas.", set()),
    ("dm_pie_sano", DM, "Examen de pies normal, sin lesiones, buena sensibilidad.", set()),
    ("no_embarazo", P("G40", "Epilepsia", 30), "Usuaria de valproato, test de embarazo negativo, usa anticonceptivo.", set()),
]


def correr(caso, real):
    nombre, perfil, texto, esperado = caso
    d = combinaciones.detectar(texto, perfil, real)
    obtenido = {a["id"] for a in d["aplicadas"]}
    efectos = {c["id"]: c["efecto"] for c in combinaciones.cargar()["kb"]["combinaciones"]}
    return {"caso": nombre, "texto": texto, "esperado": esperado, "obtenido": obtenido, "errores": d["errores"],
            "urg_esperada": any(efectos[i] == "urgencia" for i in esperado), "urg_obtenida": any(efectos[i] == "urgencia" for i in obtenido),
            "alertas": d["alertas"]}


def main():
    real = rubrica.ClienteBedrock(timeout_s=40, reintentos=6)
    with ThreadPoolExecutor(max_workers=5) as ex:
        res = list(ex.map(lambda c: correr(c, real), CASOS))
    pos = [r for r in res if r["esperado"]]
    neg = [r for r in res if not r["esperado"]]
    exactos = sum(r["esperado"] <= r["obtenido"] for r in pos)
    urg = [r for r in pos if r["urg_esperada"]]
    urg_ok = sum(r["urg_obtenida"] for r in urg)
    falsos = [r for r in neg if r["obtenido"]]
    extra = [r for r in pos if r["obtenido"] - r["esperado"]]
    lineas = [
        "# Evaluación de las combinaciones de riesgo", "",
        f"Bedrock `{real.model_id}` · {len(res)} casos escritos a mano ({len(pos)} con combinación, {len(neg)} trampa: negaciones, base "
        "ausente, eventos banales) · `lambda/combinaciones.py` (3 lecturas, citas verificadas, base contra el registro, 2 de 3).", "",
        f"- **Urgencias detectadas:** {urg_ok} de {len(urg)} (lo más importante: no dejar pasar un riesgo vital).",
        f"- **Combinación esperada detectada:** {exactos} de {len(pos)}.",
        f"- **Casos trampa sin detección falsa:** {len(neg) - len(falsos)} de {len(neg)}.",
        f"- Detecciones adicionales a la esperada en casos con combinación: {len(extra)}.", "",
        "| Caso | Esperado | Obtenido |", "|---|---|---|",
        *[f"| {r['caso']} | {', '.join(sorted(r['esperado'])) or '—'} | {', '.join(sorted(r['obtenido'])) or '—'}"
          f"{' ✗' if (r['esperado'] and not r['esperado'] <= r['obtenido']) or (not r['esperado'] and r['obtenido']) else ''} |" for r in res], "",
        "Alertas de combinaciones no listadas (red de seguridad):", "",
        *[f"- {r['caso']}: {a['descripcion']}" for r in res for a in r["alertas"]], "",
    ]
    with open(os.path.join(RAIZ, "docs", "algoritmo", "EVALUACION_COMBINACIONES.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lineas))
    print("\n".join(lineas[:8]))
    for r in res:
        if (r["esperado"] and not r["esperado"] <= r["obtenido"]) or (not r["esperado"] and r["obtenido"]) or r["errores"]:
            print("  ✗", r["caso"], "esperado", r["esperado"], "obtenido", r["obtenido"], r["errores"][:1])


if __name__ == "__main__":
    main()
