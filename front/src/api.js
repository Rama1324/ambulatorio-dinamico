// Cliente de la API (AWS o lambda/local_server.py). La URL viene de VITE_API_URL (front/.env.local en local).
export const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

// Fechas del control "Explorar fechas anteriores": cada 14 días desde abril hasta la fecha del registro.
const FECHAS_SLIDER = (() => {
  const out = [];
  const d = new Date("2026-04-01T12:00:00");
  while (d < new Date("2026-10-13T00:00:00")) { out.push(d.toISOString().slice(0, 10)); d.setDate(d.getDate() + 14); }
  out.push("2026-10-13");
  return out;
})();
// Fecha de trabajo y modo que informa la API (/health): "tiempo_real" usa la fecha de hoy en Chile.
let info = { fecha_hoy: "2026-10-13", modo: "simulacion", datos: "sinteticos" };
export async function cargarInfo() {
  try { info = { ...info, ...(await req("GET", "/health")) }; } catch { /* sin API: simulación */ }
  return info;
}
export const fechas = () => (info.fecha_hoy > FECHAS_SLIDER[FECHAS_SLIDER.length - 1] ? [...FECHAS_SLIDER, info.fecha_hoy] : FECHAS_SLIDER);

// Trazabilidad: el nombre de quien usa la app (guardado en este navegador) viaja como `usuario` en cada registro.
let usuario = "";
try { usuario = localStorage.getItem("hlf_usuario") || ""; } catch { /* sin almacenamiento */ }
export const getUsuario = () => usuario;
export function setUsuario(nombre) {
  usuario = nombre.trim();
  try { localStorage.setItem("hlf_usuario", usuario); } catch { /* sin almacenamiento */ }
}

async function req(method, path, body) {
  const b = body && method === "POST" && usuario && !body.usuario ? { ...body, usuario } : body;
  const r = await fetch(API_URL + path, {
    method, headers: { "content-type": "application/json" }, ...(b ? { body: JSON.stringify(b) } : {}),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `Error ${r.status}`);
  return data;
}
const conFecha = (fechaCorte, especialidad) =>
  new URLSearchParams({ fecha_corte: fechaCorte, ...(especialidad ? { especialidad } : {}) });

// Lectura
export const getPacientes = (fechaCorte, especialidad) => req("GET", `/pacientes?${conFecha(fechaCorte, especialidad)}`);
export const getPaciente = (id, fechaCorte) => req("GET", `/pacientes/${id}?${conFecha(fechaCorte)}`);
export const getHistoria = (id, fechaCorte, especialidad) => req("GET", `/pacientes/${id}/historia?${conFecha(fechaCorte, especialidad)}`);
export const getKpis = (fechaCorte, especialidad) => req("GET", `/kpis?${conFecha(fechaCorte, especialidad)}`);
export const getEstadisticas = (fechaCorte, especialidad) => req("GET", `/estadisticas?${conFecha(fechaCorte, especialidad)}`);
export const getCatalogo = () => req("GET", "/catalogo");
export const urlPlantilla = (tabla) => `${API_URL}/plantillas/${tabla}`;

// Registros del equipo clínico (cada uno queda con usuario y fecha)
export const postEvento = (evento) => req("POST", "/eventos", evento);
export const postRevision = (id, body) => req("POST", `/pacientes/${id}/revision`, body);
export const postContacto = (id, body) => req("POST", `/pacientes/${id}/contacto`, body);
export const postDecision = (id, body) => req("POST", `/pacientes/${id}/decision`, body);
export const postOrden = (id, body) => req("POST", `/pacientes/${id}/orden`, body);
export const postGestion = (id, body) => req("POST", `/pacientes/${id}/gestion`, body);
export const postNovedad = (id, body) => req("POST", `/pacientes/${id}/novedad`, body);
export const postPaciente = (body) => req("POST", "/pacientes", body);
export const postImportar = (archivos, confirmar) => req("POST", "/importar", { archivos, confirmar });
export const postInforme = (id, body) => req("POST", `/pacientes/${id}/informe`, body);
export const postExplicar = (id, fechaCorte) => req("POST", `/pacientes/${id}/explicar`, { fecha_corte: fechaCorte });
