

export const ESPECIALIDADES = ["Todas", "Cardiología", "Traumatología", "Endocrinología", "Salud Mental", "Broncopulmonar", "Neurología", "Gastroenterología"];

export const ETIQUETA = { alta: "Alta", media: "Media", baja: "Baja" };

export const COLOR_CAT = {
  alta: "bg-error-container text-on-error-container border-error/40",
  media: "bg-ambar-container text-ambar border-ambar/40",
  baja: "bg-verde-container text-verde border-verde/40",
};

export const FACTOR = {
  riesgo_vital: "Descompensación grave: evaluar", prioridad_inicial: "Priorización de la interconsulta", evento: "Evento posterior a la interconsulta",
  tabla_oficial: "Tabla de priorización HLF", dias_espera: "Tiempo de espera", ges: "Garantía GES", medicion: "Medición sostenida (no signo vital)",
  lace: "Puntaje LACE (experimental)", oncologico: "Hallazgo oncológico (informe)", ventana: "Vigencia del evento",
  urgencia: "URGENCIA: derivar hoy", criterio_clinico: "Criterio clínico de su enfermedad",
  combinacion: "Combinación de riesgo", alerta_combinacion: "Posible combinación de riesgo (revisar)",
  criterio_registro: "Criterio oficial de su diagnóstico", plazo: "Plazo de referencia",
  alerta_clinica: "Alerta clínica",
};

export const TIPO_EVENTO = { visita_urgencia: "Urgencia", hospitalizacion: "Hospitalización", examen_alterado: "Examen alterado", cambio_farmaco: "Cambio de fármaco", control_aps: "Control APS", hallazgo_oncologico: "Hallazgo oncológico", criterio_clinico: "Criterio clínico", combinacion_riesgo: "Combinación de riesgo" };

export const ESTILO_GESTION = { pendiente_revision: "text-ambar", pendiente_contacto: "text-ambar", pendiente_cita: "text-on-surface",
  cita_reservada: "text-hlf" };

// Excel (.xlsx) de la lista tal como se está viendo (mismos filtros), con el fundamento de cada paciente,
// los ajustes manuales, los egresados y los filtros usados. Ver src/excel.js.
export const EVAL_TXT = { pendiente: "Aviso abierto", evaluada: "Visto por especialista" };

// Colores por variable CSS: siguen el tema claro/oscuro (también dentro del gráfico SVG)
export const COLOR_HEX = { alta: "rgb(var(--c-error))", media: "rgb(var(--c-ambar))", baja: "rgb(var(--c-verde))" };

// La única descripción del orden de la lista (la misma que aplica el motor: puntaje.clave_orden / decisor.clave_orden_536).
// El LACE (hospitalizaciones y urgencias recientes) desempata en ambos modos, antes de los días de espera.
export const ordenLista = () => "Orden (MINSAL Ord. 536/2025): prioridad → «derivar hoy» → descompensación grave → mortalidad del cuadro → " +
  "gravedad del último evento → descompensado → grupo de especial protección → más de 1 año esperando → " +
  "reingresos y urgencias recientes (índice LACE, desempate) → días de espera.";
export const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
