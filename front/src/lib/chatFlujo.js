// Chat de seguimiento del paciente: árbol de decisión puro (sin IA, funciona sin conexión).
// Cada respuesta queda como dato estructurado con el vocabulario del registro del HLF. El equipo clínico valida
// antes de que algo cambie la prioridad. Nunca diagnostica ni promete una hora.
//
// Punto de integración futuro con un LLM (Amazon Bedrock / Claude) para entender texto libre. Desactivado:
// el texto libre se envía tal cual y el backend lo lee con las mismas reglas de palabras clave y negación de informe.py.
// export async function responderConIA(mensaje, contexto) { /* POST /chat → Bedrock Converse */ }

export const LINEAS_AYUDA = [
  { label: "SAMU (emergencias)", num: "131" },
  { label: "Salud Responde (24 h)", num: "600 360 7777" },
  { label: "Prevención del suicidio", num: "*4141" },
];

const PHQ9 = [
  "Poco interés o placer en hacer las cosas",
  "Se ha sentido decaído(a), deprimido(a) o sin esperanza",
  "Dificultad para dormir o mantenerse dormido(a), o ha dormido demasiado",
  "Se ha sentido cansado(a) o con poca energía",
  "Poco apetito o ha comido en exceso",
  "Se ha sentido mal con usted mismo(a), o siente que es un fracaso o que ha quedado mal con su familia",
  "Dificultad para concentrarse, por ejemplo al leer o ver televisión",
  "Se ha movido o hablado tan lento que otros lo notan, o al revés: muy inquieto(a)",
  "Ha pensado que estaría mejor muerto(a) o en hacerse daño de alguna manera",
];
const FRECUENCIA = [
  { label: "Nunca", valor: 0 }, { label: "Varios días", valor: 1 },
  { label: "Más de la mitad de los días", valor: 2 }, { label: "Casi todos los días", valor: 3 },
];
const SI_NO = [{ label: "Sí", valor: true }, { label: "No", valor: false }];

// Texto libre que nunca debe esperar al final del flujo
const ALARMA_TEXTO = [
  [/suicid|matarme|quitarme la vida|hacerme da[ñn]o|no quiero vivir/i, "ideacion_suicida"],
  [/dolor (de|en el) pecho|dolor tor[aá]cico|me aprieta el pecho/i, "dolor_pecho"],
  [/no puedo respirar|me ahogo|me falta (mucho )?el aire/i, "disnea_reposo"],
];
const TEXTO_BANDERA = {
  ideacion_suicida: "Usted nos contó que ha tenido ideas de hacerse daño. No está solo(a): llame ahora a la línea *4141 o al SAMU 131.",
  dolor_pecho: "El dolor de pecho en reposo o con poco esfuerzo puede ser grave. Llame al SAMU 131 o vaya a la urgencia más cercana.",
  disnea_reposo: "La falta de aire en reposo puede ser grave. Llame al SAMU 131 o vaya a la urgencia más cercana.",
};

export const restarDias = (iso, n) => {
  const d = new Date(iso + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
};

const medicionPorEspecialidad = (esp) => ({
  "Salud Mental": "phq1", "Traumatología": "eva", "Neurología": "eva", "Cardiología": "pecho",
  "Endocrinología": "gluc_tiene", "Gastroenterología": "gastro", "Broncopulmonar": "disnea",
}[esp] || "funcional");

export function estadoInicial() {
  return { paso: "id", paciente: null, r: {}, eventos: [], mediciones: [], bandera: null, textos: [], resumen: [], fin: false };
}

// Pregunta del paso actual: { texto, opciones?, escala?, entrada? ("texto" | "numero" | "presion") }
export function pregunta(e) {
  const p = e.paciente;
  switch (e.paso) {
    case "id": return { texto: "Hola. Soy el asistente de seguimiento del Hospital Dra. Eloísa Díaz. Escriba su número de paciente (por ejemplo PAC-HLF-00001) o elija uno en el modo demo.", entrada: "texto" };
    case "vigencia": return { texto: `Hola, ${p.nombre_fantasia}. Usted está en la lista de espera de ${p.especialidad}. ¿Sigue necesitando esa hora?`,
      opciones: [{ label: "Sí, la sigo necesitando", valor: "si" }, { label: "Ya me atendí en otro lugar", valor: "atendido" }, { label: "No sé", valor: "no_se" }] };
    case "estado": return { texto: "Comparado con cuando lo derivaron, ¿cómo se siente?",
      opciones: [{ label: "Mejor", valor: -1 }, { label: "Igual", valor: 0 }, { label: "Peor", valor: 1 }, { label: "Mucho peor", valor: 2 }] };
    case "urgencia": return { texto: "¿Ha ido a un servicio de urgencia desde que está esperando?", opciones: SI_NO };
    case "urg_cuando": return { texto: "¿Cuándo fue la última vez?",
      opciones: [{ label: "Esta semana", valor: 3 }, { label: "Este mes", valor: 15 }, { label: "Hace más de un mes", valor: 45 }] };
    case "urg_hosp": return { texto: "¿Quedó hospitalizado(a)?", opciones: SI_NO };
    case "farmaco": return { texto: "¿Le cambiaron los remedios o la dosis?",
      opciones: [{ label: "Me aumentaron la dosis", valor: "aumento" }, { label: "Me la disminuyeron", valor: "reduccion" }, { label: "No", valor: "no" }] };
    case "phq1": return { texto: `En las últimas 2 semanas, ¿con qué frecuencia ha tenido: ${PHQ9[0].toLowerCase()}?`, opciones: FRECUENCIA };
    case "phq2": return { texto: `¿Y con qué frecuencia: ${PHQ9[1].toLowerCase()}?`, opciones: FRECUENCIA };
    case "phq": return { texto: `Pregunta ${e.r.phqI + 1} de 9. En las últimas 2 semanas: ${PHQ9[e.r.phqI].toLowerCase()}.`, opciones: FRECUENCIA };
    case "eva": return { texto: "En una escala de 0 a 10, ¿cuánto dolor ha tenido esta semana?", escala: true };
    case "pecho": return { texto: "¿Tiene dolor de pecho en reposo o con poco esfuerzo?", opciones: SI_NO };
    case "pa_tiene": return { texto: "¿Se ha medido la presión en casa en los últimos días?", opciones: [{ label: "Sí, la anoto", valor: true }, { label: "No", valor: false }] };
    case "pa": return { texto: "Escriba su presión como aparece en el aparato, por ejemplo 135/85.", entrada: "presion" };
    case "gluc_tiene": return { texto: "¿Tiene glucómetro y se midió la glicemia hace poco?", opciones: [{ label: "Sí, la anoto", valor: true }, { label: "No", valor: false }] };
    case "gluc": return { texto: "Escriba el valor de su glicemia (mg/dL), por ejemplo 180.", entrada: "numero" };
    case "gluc_sintomas": return { texto: "¿Ha tenido mucha sed, orina mucho o ha bajado de peso sin explicación?", opciones: SI_NO };
    case "gastro": return { texto: "¿Ha tenido vómitos con sangre, deposiciones negras o el abdomen más hinchado?", opciones: SI_NO };
    case "disnea": return { texto: "¿Le falta el aire estando en reposo?", opciones: SI_NO };
    case "sat_tiene": return { texto: "¿Tiene oxímetro (el aparato que se pone en el dedo)?", opciones: [{ label: "Sí, lo anoto", valor: true }, { label: "No", valor: false }] };
    case "sat": return { texto: "Escriba su saturación (%), por ejemplo 94.", entrada: "numero" };
    case "funcional": return { texto: "¿Puede hacer sus actividades diarias?",
      opciones: [{ label: "Sin problema", valor: 0 }, { label: "Con dificultad", valor: 1 }, { label: "No puedo", valor: 2 }] };
    case "asistencia": return { texto: "Si le avisamos de una hora con 48 horas de anticipación, ¿podría asistir?",
      opciones: [{ label: "Sí", valor: "si" }, { label: "Depende del día", valor: "depende" }, { label: "No", valor: "no" }] };
    case "horario": return { texto: "¿Qué horario le acomoda más?",
      opciones: [{ label: "Mañana", valor: "mañana" }, { label: "Tarde", valor: "tarde" }, { label: "Me da lo mismo", valor: "indiferente" }] };
    default: return { texto: "" };
  }
}

const med = (tipo, valor, unidad, fecha) => ({ tipo_medicion: tipo, valor, unidad, fecha_medicion: fecha });

// Avanza el flujo. Devuelve { estado, alerta? } — alerta = texto de la tarjeta roja si apareció una bandera roja.
export function responder(e, valor, { pacientes, fechaCorte }) {
  const s = { ...e, r: { ...e.r }, eventos: [...e.eventos], mediciones: [...e.mediciones], resumen: [...e.resumen], textos: [...e.textos] };
  const ir = (paso) => { s.paso = paso; return { estado: s }; };
  const bandera = (tipo, siguiente) => {
    s.bandera = s.bandera || tipo;
    s.resumen.push(`Señal de alarma: ${{ ideacion_suicida: "ideas de hacerse daño", dolor_pecho: "dolor de pecho", disnea_reposo: "falta de aire en reposo" }[tipo]}`);
    s.paso = siguiente;
    return { estado: s, alerta: TEXTO_BANDERA[tipo] };
  };
  switch (e.paso) {
    case "id": {
      const t = String(valor).trim().toUpperCase();
      const num = t.match(/(\d{1,5})$/)?.[1];
      const id = num ? `PAC-HLF-${num.padStart(5, "0")}` : t;
      const p = pacientes.find((x) => x.id_paciente === id);
      if (!p) return { estado: s, error: "No encontramos ese número en la lista de espera. Revise el número o pida ayuda en el SOME." };
      s.paciente = p;
      return ir("vigencia");
    }
    case "vigencia":
      s.r.vigencia = valor;
      if (valor === "atendido") { s.r.egreso_propuesto = true; s.resumen.push("Dice que ya se atendió en otro lugar (el equipo confirmará el egreso)"); return ir("funcional"); }
      return ir("estado");
    case "estado":
      s.r.tendencia_autoreporte = valor;
      s.resumen.push(`Se siente ${{ "-1": "mejor", 0: "igual", 1: "peor", 2: "mucho peor" }[valor]} que al ser derivado(a)`);
      return ir("urgencia");
    case "urgencia": return ir(valor ? "urg_cuando" : "farmaco");
    case "urg_cuando": s.r.urg_dias = valor; return ir("urg_hosp");
    case "urg_hosp": {
      const fecha = restarDias(fechaCorte, s.r.urg_dias);
      s.eventos.push(valor
        ? { tipo_evento: "hospitalizacion", subtipo: "ingreso hospitalario", fecha_evento: fecha, evidencia: "Paciente reporta urgencia con hospitalización" }
        : { tipo_evento: "visita_urgencia", subtipo: "descompensación", fecha_evento: fecha, evidencia: "Paciente reporta consulta en urgencia" });
      s.resumen.push(valor ? "Fue a urgencia y quedó hospitalizado(a)" : "Fue a urgencia, sin hospitalización");
      return ir("farmaco");
    }
    case "farmaco":
      if (valor !== "no") {
        s.eventos.push({ tipo_evento: "cambio_farmaco", subtipo: valor === "aumento" ? "aumento dosis" : "reducción dosis", fecha_evento: fechaCorte,
          evidencia: valor === "aumento" ? "Paciente reporta aumento de dosis" : "Paciente reporta reducción de dosis" });
        s.resumen.push(valor === "aumento" ? "Le aumentaron la dosis de un remedio" : "Le disminuyeron la dosis de un remedio");
      }
      return ir(medicionPorEspecialidad(s.paciente.especialidad));
    case "phq1": s.r.phq = [valor]; return ir("phq2");
    case "phq2":
      s.r.phq = [...s.r.phq, valor];
      if (s.r.phq[0] + s.r.phq[1] >= 3) { s.r.phqI = 2; return ir("phq"); }
      s.resumen.push(`Ánimo (PHQ-2): ${s.r.phq[0] + s.r.phq[1]} de 6, sin indicación de seguir`);
      return ir("funcional");
    case "phq": {
      s.r.phq = [...s.r.phq, valor];
      const i = s.r.phqI;
      if (i === 8 && valor > 0) {
        const total = s.r.phq.reduce((a, b) => a + b, 0);
        s.mediciones.push(med("PHQ9", total, "pts", fechaCorte)); s.resumen.push(`PHQ-9: ${total} puntos`);
        return bandera("ideacion_suicida", "funcional");
      }
      if (i === 8) {
        const total = s.r.phq.reduce((a, b) => a + b, 0);
        s.mediciones.push(med("PHQ9", total, "pts", fechaCorte)); s.resumen.push(`PHQ-9: ${total} puntos`);
        return ir("funcional");
      }
      s.r.phqI = i + 1;
      return ir("phq");
    }
    case "eva":
      s.mediciones.push(med("escala_dolor_eva", valor, "pts", fechaCorte)); s.resumen.push(`Dolor: ${valor} de 10`);
      return ir("funcional");
    case "pecho":
      if (valor) return bandera("dolor_pecho", "pa_tiene");
      return ir("pa_tiene");
    case "pa_tiene": return ir(valor ? "pa" : "funcional");
    case "pa": {
      const m = String(valor).match(/(\d{2,3})\s*[/\-\s]\s*(\d{2,3})/);
      if (!m || +m[1] < 60 || +m[1] > 260 || +m[2] < 30 || +m[2] > 160) return { estado: s, error: "No entendí el valor. Escríbalo como 135/85." };
      s.mediciones.push(med("presion_sistolica", +m[1], "mmHg", fechaCorte), med("presion_diastolica", +m[2], "mmHg", fechaCorte));
      s.resumen.push(`Presión en casa: ${m[1]}/${m[2]} mmHg`);
      return ir("funcional");
    }
    case "gluc_tiene": return ir(valor ? "gluc" : "gluc_sintomas");
    case "gluc": {
      const v = Number(String(valor).replace(",", "."));
      if (!(v >= 20 && v <= 700)) return { estado: s, error: "No entendí el valor. Escriba solo el número, por ejemplo 180." };
      s.mediciones.push(med("glicemia", v, "mg/dL", fechaCorte)); s.resumen.push(`Glicemia capilar: ${v} mg/dL`);
      return ir("gluc_sintomas");
    }
    case "gluc_sintomas":
      s.r.sintomas_hiperglicemia = valor;
      if (valor) s.resumen.push("Tiene mucha sed, orina mucho o baja de peso");
      return ir("funcional");
    case "gastro":
      s.r.sintomas_alarma_digestivos = valor;
      if (valor) s.resumen.push("Reporta sangrado digestivo o abdomen más hinchado");
      if (valor) { s.paso = "funcional"; return { estado: s, alerta: "Vómitos con sangre o deposiciones negras pueden ser graves. Vaya a la urgencia más cercana o llame al SAMU 131." }; }
      return ir("funcional");
    case "disnea":
      if (valor) return bandera("disnea_reposo", "sat_tiene");
      return ir("sat_tiene");
    case "sat_tiene": return ir(valor ? "sat" : "funcional");
    case "sat": {
      const v = Number(String(valor).replace(",", ".").replace("%", ""));
      if (!(v >= 50 && v <= 100)) return { estado: s, error: "No entendí el valor. Escriba solo el número, por ejemplo 94." };
      s.mediciones.push(med("saturacion_o2", v, "%", fechaCorte)); s.resumen.push(`Saturación: ${v} %`);
      return ir("funcional");
    }
    case "funcional":
      s.r.limitacion_funcional = valor;
      s.resumen.push(`Actividades diarias: ${["sin problema", "con dificultad", "no puede"][valor]}`);
      return ir("asistencia");
    case "asistencia": s.r.confirma_asistencia = valor; return ir("horario");
    case "horario":
      s.r.preferencia_horario = valor;
      s.resumen.push(`Puede asistir con 48 h de aviso: ${s.r.confirma_asistencia}; horario: ${valor}`);
      s.paso = "cierre"; s.fin = true;
      return { estado: s };
    default: return { estado: s };
  }
}

// Texto libre del paciente en cualquier paso: alarma inmediata o se guarda para que el backend lo lea.
export function textoLibre(e, texto) {
  const hit = ALARMA_TEXTO.find(([re]) => re.test(texto));
  const s = { ...e, textos: [...e.textos, texto], resumen: [...e.resumen] };
  if (hit) {
    s.bandera = s.bandera || hit[1];
    s.resumen.push("Escribió una señal de alarma en el chat");
    return { estado: s, alerta: TEXTO_BANDERA[hit[1]] };
  }
  return { estado: s };
}

// Cuerpo para POST /pacientes/{id}/autoreporte (lo que se ve en "Datos capturados")
export function payload(e, fechaCorte) {
  return {
    id_paciente: e.paciente?.id_paciente ?? null,
    fecha_corte: fechaCorte,
    fuente: "autoreporte",
    estado: "por_validar",
    tendencia_autoreporte: e.r.tendencia_autoreporte ?? null,
    limitacion_funcional: e.r.limitacion_funcional ?? null,
    egreso_propuesto: !!e.r.egreso_propuesto,
    confirma_asistencia: e.r.confirma_asistencia ?? null,
    preferencia_horario: e.r.preferencia_horario ?? null,
    bandera_roja: e.bandera,
    eventos: e.eventos,
    mediciones: e.mediciones,
    texto_libre: e.textos.join(" · ") || undefined,
    resumen: e.resumen,
  };
}
