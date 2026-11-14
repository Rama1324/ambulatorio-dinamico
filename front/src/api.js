// Cliente de la API (AWS o lambda/local_server.py). La URL viene de VITE_API_URL (front/.env.local en local).
import * as auth from "./auth.js";

export { auth };
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

// Rol declarado en la demo (AUTH=ninguna): viaja en la cabecera X-Rol y es solo informativo (la API no lo verifica).
// Con inicio de sesión (Cognito) el rol sale de los grupos del token y esta cabecera no cuenta.
let rol = "";
try { rol = localStorage.getItem("hlf_rol") || ""; } catch { /* sin almacenamiento */ }
export const getRol = () => rol;
export function setRol(r) {
  rol = (r || "").trim();
  try { localStorage.setItem("hlf_rol", rol); } catch { /* sin almacenamiento */ }
}

async function req(method, path, body, reintento = true) {
  const b = body && method === "POST" && usuario && !body.usuario ? { ...body, usuario } : body;
  const token = await auth.token(); // null en la demo; con Cognito, el token vigente (o lleva al inicio de sesión)
  const headers = { "content-type": "application/json", ...(rol ? { "x-rol": rol } : {}),
    ...(token ? { authorization: `Bearer ${token}` } : {}) };
  const r = await fetch(API_URL + path, { method, headers, ...(b ? { body: JSON.stringify(b) } : {}) });
  if (r.status === 401 && token && reintento && (await auth.noAutorizado())) return req(method, path, body, false);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.error || `Error ${r.status}`), { status: r.status, codigo: data.codigo, datos: data });
  return data;
}
export const getInfo = () => info;
const conFecha = (fechaCorte, especialidad) =>
  new URLSearchParams({ fecha_corte: fechaCorte, ...(especialidad ? { especialidad } : {}) });

// Lectura
export const getPacientes = (fechaCorte, especialidad) => req("GET", `/pacientes?${conFecha(fechaCorte, especialidad)}`);
export const getPaciente = (id, fechaCorte) => req("GET", `/pacientes/${id}?${conFecha(fechaCorte)}`);
export const getHistoria = (id, fechaCorte, especialidad) => req("GET", `/pacientes/${id}/historia?${conFecha(fechaCorte, especialidad)}`);
export const getKpis = (fechaCorte, especialidad) => req("GET", `/kpis?${conFecha(fechaCorte, especialidad)}`);
export const getEstadisticas = (fechaCorte, especialidad) => req("GET", `/estadisticas?${conFecha(fechaCorte, especialidad)}`);
export const getCatalogo = () => req("GET", "/catalogo");
// Quién está conectado, con qué roles y qué puede hacer: {usuario, roles, origen, auth, se_exige, permisos, aviso?}
export const getYo = () => req("GET", "/yo");
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

// Catálogo (diagnósticos, motivos de veredicto…): cambia poco, se pide una vez por sesión.
let catalogo = null;
export const catalogoCache = () => (catalogo ??= getCatalogo().catch((e) => { catalogo = null; throw e; }));

// Decisiones del sistema (dictámenes), veredicto del especialista y aprendizaje
export const getDecisiones = (estado = "pendiente", especialidad, limite = 200) =>
  req("GET", `/decisiones?${new URLSearchParams({ estado, limite, ...(especialidad ? { especialidad } : {}) })}`);
export const getDecisionesPaciente = (id) => req("GET", `/pacientes/${id}/decisiones`);
export const getAprendizaje = (especialidad) => req("GET", `/aprendizaje${especialidad ? `?especialidad=${encodeURIComponent(especialidad)}` : ""}`);
export const postResolverCriterio = (id, body) => req("POST", `/criterios-locales/${id}/resolver`, body);
export const postEnmienda = (id, idEvento, body) => req("POST", `/pacientes/${id}/eventos/${idEvento}/enmienda`, body);

// Recepción de datos y base de conocimiento
export const getLotes = (limite = 30) => req("GET", `/ingesta/lotes?limite=${limite}`);
export const getLote = (id) => req("GET", `/ingesta/lotes/${id}`);
export const getConocimiento = () => req("GET", "/conocimiento");
export const getConocimientoDx = (cie10) => req("GET", `/conocimiento/diagnostico/${encodeURIComponent(cie10)}`);
