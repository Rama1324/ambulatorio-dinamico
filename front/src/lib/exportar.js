import { ETIQUETA, fmt } from "./constantes";

// Exporta la lista priorizada (con los filtros actuales) a CSV separado por ";" con BOM: Excel en español lo abre en columnas.
export function exportarCsv(pacientes, fecha) {
  const col = ["N°", "Prioridad", "Contactar hoy", "Paciente", "ID", "Edad", "Especialidad", "CIE-10", "Diagnóstico",
    "Fecha ingreso", "Días de espera", "Más de 1 año", "Puntaje LACE", "GES vencida", "2 inasistencias", "Estado clínico", "Revisión"];
  const filas = pacientes.map((p) => [p.posicion, ETIQUETA[p.categoria], p.riesgo_vital ? "Sí" : "", p.nombre_fantasia, p.id_paciente, p.edad,
    p.especialidad, p.diagnostico_cie10, p.diagnostico_texto, fmt(p.fecha_ingreso_lista), p.dias_espera, p.antiguedad_mayor_1_anio ? "Sí" : "",
    p.lace?.total ?? "", p.ges?.vencida ? `Sí (GES N°${p.ges.problema})` : "", p.riesgo_inasistencia ? "Sí" : "", p.estado_clinico.replace("_", " "), p.estado_revision]);
  const esc = (v) => { const s = String(v ?? ""); return /[;"\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s; };
  const csv = "﻿" + [col, ...filas].map((f) => f.map(esc).join(";")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `lista_priorizada_HLF_${fecha}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}
