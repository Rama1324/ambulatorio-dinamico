// Si existe VITE_API_URL usa la API real (AWS o local_server.py). Si no, usa mock.json (solo lectura).
export const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
export const MODO = API_URL ? "api" : "mock";

// Fecha de operación = días hábiles con agenda de box (GET /dias). Sin API: los cortes precalculados de mock.json.
export async function getDias() {
  if (MODO === "api") return (await req("GET", "/dias")).dias;
  return (await mock()).fechas;
}

let mockCache = null;
async function mock() {
  if (!mockCache) mockCache = (await import("./mock.json")).default;
  return mockCache;
}

async function req(method, path, body) {
  const r = await fetch(API_URL + path, {
    method, headers: { "content-type": "application/json" }, ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `Error ${r.status}`);
  return data;
}

export async function getPacientes(fechaCorte, especialidad) {
  if (MODO === "api") {
    const q = new URLSearchParams({ fecha_corte: fechaCorte });
    if (especialidad) q.set("especialidad", especialidad);
    return req("GET", `/pacientes?${q}`);
  }
  // mock.json lo genera scripts/generar_mock.py con el mismo motor de reglas que la API
  const m = await mock();
  const corte = m.cortes[fechaCorte] || m.cortes[m.fechas[m.fechas.length - 1]];
  const idx = m.fechas.indexOf(fechaCorte);
  const ant = idx > 0 ? Object.fromEntries(m.cortes[m.fechas[idx - 1]].pacientes.map((r) => [r.id_paciente, r.posicion])) : {};
  let pacientes = corte.pacientes.map((r) => ({
    ...m.pacientes[r.id_paciente], ...r, posicion_anterior: ant[r.id_paciente] ?? null, estado_revision: "pendiente",
  }));
  if (especialidad) pacientes = pacientes.filter((p) => p.especialidad === especialidad);
  return { fecha_corte: fechaCorte, total: pacientes.length, pacientes, excluidos: corte.excluidos };
}

export async function getPaciente(id, fechaCorte) {
  if (MODO === "api") return req("GET", `/pacientes/${id}?fecha_corte=${fechaCorte}`);
  const m = await mock();
  const t = m.timeline[id];
  return {
    eventos_clinicos: t.eventos.filter((e) => e.fecha_evento <= fechaCorte),
    mediciones: t.mediciones.filter((x) => x.fecha_medicion <= fechaCorte),
    citaciones: t.citaciones.filter((c) => c.fecha_cita <= fechaCorte),
  };
}

export const postEvento = (evento) => req("POST", "/eventos", evento);
export const postRevision = (id, body) => req("POST", `/pacientes/${id}/revision`, body);
export async function getHistoria(id, fechaCorte) {
  if (MODO === "api") return req("GET", `/pacientes/${id}/historia?fecha_corte=${fechaCorte}`);
  const m = await mock();
  const puntos = m.fechas.filter((f) => f <= fechaCorte).flatMap((f) => {
    const c = m.cortes[f];
    const r = c.pacientes.find((x) => x.id_paciente === id);
    if (r) return [{ fecha: f, posicion: r.posicion, total: c.pacientes.length, categoria: r.categoria, riesgo_vital: r.riesgo_vital }];
    return c.excluidos.some((x) => x.id_paciente === id) ? [{ fecha: f, excluido: true }] : [];
  });
  const eventos = (m.timeline[id]?.eventos || []).filter((e) => e.fecha_evento <= fechaCorte &&
    (e.severidad === "grave" || e.subtipo.includes("descompensaci") || ["estabilización", "buena respuesta"].includes(e.subtipo)));
  return { id_paciente: id, puntos, eventos };
}
export const postContacto = (id, body) => req("POST", `/pacientes/${id}/contacto`, body);
export const postNovedad = (id, body) => req("POST", `/pacientes/${id}/novedad`, body);
export const getCatalogo = () => req("GET", "/catalogo");
export const postPaciente = (body) => req("POST", "/pacientes", body);
export const postInforme = (id, body) => req("POST", `/pacientes/${id}/informe`, body);
export const postExplicar = (id, fechaCorte) => req("POST", `/pacientes/${id}/explicar`, { fecha_corte: fechaCorte });
export const getBoxes = (fechaCorte, especialidad) =>
  req("GET", `/boxes?${new URLSearchParams({ fecha_corte: fechaCorte, ...(especialidad ? { especialidad } : {}) })}`);

// Box del día: asignar un cupo libre (al siguiente de la lista o a un paciente) y registrar el resultado de la cita.
export const postAsignar = (body) => req("POST", "/boxes/asignar", body);
export const postEstadoCita = (idCita, estado) => req("POST", `/citas/${idCita}/estado`, { estado });
