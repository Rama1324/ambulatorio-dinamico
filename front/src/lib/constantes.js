
export const ESPECIALIDADES = ["Todas", "Cardiología", "Traumatología", "Endocrinología", "Salud Mental", "Broncopulmonar", "Neurología", "Gastroenterología"];
export const ETIQUETA = { alta: "Alta", media: "Media", baja: "Baja" };
export const COLOR_CAT = {
  alta: "bg-error-container text-on-error-container border-error/40",
  media: "bg-ambar-container text-ambar border-ambar/40",
  baja: "bg-verde-container text-verde border-verde/40",
};
export const EVENTOS = {
  urgencia: { label: "Consulta en urgencia (ESI 2)", tipo_evento: "visita_urgencia", subtipo: "triage ESI 2", severidad: "grave" },
  hospitalizacion: { label: "Hospitalización", tipo_evento: "hospitalizacion", subtipo: "ingreso hospitalario", severidad: "grave" },
  examen: { label: "Examen alterado", tipo_evento: "examen_alterado", subtipo: "resultado alterado", severidad: "moderada" },
  mejora: { label: "Buena respuesta en APS", tipo_evento: "control_aps", subtipo: "buena respuesta", severidad: "leve" },
};
export const FACTOR = {
  riesgo_vital: "Atención hoy", prioridad_inicial: "Priorización de la interconsulta", evento: "Evento posterior a la interconsulta",
  tabla_oficial: "Tabla de priorización HLF", dias_espera: "Tiempo de espera", ges: "Garantía GES", medicion: "Última medición",
  lace: "Puntaje de riesgo LACE",
};
export const TIPO_EVENTO = { visita_urgencia: "Urgencia", hospitalizacion: "Hospitalización", examen_alterado: "Examen alterado", cambio_farmaco: "Cambio de fármaco", control_aps: "Control APS" };
export const POR_PAGINA = 25;

export const fmt = (iso) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
export const COLOR_HEX = { alta: "#ba1a1a", media: "#8a5100", baja: "#1f6b35" };
