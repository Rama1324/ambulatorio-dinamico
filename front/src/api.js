// Si existe VITE_API_URL usa la API real (AWS o local_server.py). Si no, usa mock.json (solo lectura).
export const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
export const MODO = API_URL ? "api" : "mock";

const FECHAS_SLIDER = (() => {
  const out = [];
  const d = new Date("2026-04-01T12:00:00");
  while (d < new Date("2026-10-13T00:00:00")) { out.push(d.toISOString().slice(0, 10)); d.setDate(d.getDate() + 14); }
  out.push("2026-10-13");
  return out;
})();
export const fechas = () => FECHAS_SLIDER;

let mockCache = null;
async function mock() {
  if (!mockCache) mockCache = (await import("./mock.json")).default;
  return mockCache;
}

async function req(method, path, body) {
  const r = await fetch(API_URL + path, {
    method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
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
  const m = await mock();
  const corte = m.cortes[fechaCorte] || m.cortes[m.fechas[m.fechas.length - 1]];
  const idx = m.fechas.indexOf(fechaCorte);
  const ant = idx > 0 ? Object.fromEntries(m.cortes[m.fechas[idx - 1]].pacientes.map((r) => [r.id, r.pos])) : {};
  let pacientes = corte.pacientes.map((r) => ({
    ...m.pacientes[r.id], puntaje: r.p, categoria: r.c, posicion: r.pos, posicion_anterior: ant[r.id] ?? null,
    riesgo_inasistencia: r.ri, razones: r.r, estado_revision: "pendiente",
  }));
  if (especialidad) pacientes = pacientes.filter((p) => p.especialidad === especialidad);
  return { fecha_corte: fechaCorte, total: pacientes.length, pacientes,
           excluidos: corte.excluidos.map((id) => ({ id_paciente: id, motivo: "fallecido" })) };
}

export async function getPaciente(id, fechaCorte) {
  if (MODO === "api") return req("GET", `/pacientes/${id}?fecha_corte=${fechaCorte}`);
  const m = await mock();
  const p = m.pacientes[id];
  return {
    eventos_clinicos: p.eventos.filter((e) => e.fecha_evento <= fechaCorte),
    mediciones: p.mediciones.filter((x) => x.fecha_medicion <= fechaCorte),
    citaciones: [],
  };
}

export const postEvento = (evento) => req("POST", "/eventos", evento);
export const postRevision = (id, body) => req("POST", `/pacientes/${id}/revision`, body);
export const postExplicar = (id, fechaCorte) => req("POST", `/pacientes/${id}/explicar`, { fecha_corte: fechaCorte });
export const getBoxes = (fechaCorte) => req("GET", `/boxes?fecha_corte=${fechaCorte}`);
