import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as api from "./api";

const ESPECIALIDADES = ["Todas", "Cardiología", "Traumatología", "Endocrinología", "Salud Mental", "Broncopulmonar", "Neurología", "Gastroenterología"];
const ETIQUETA = { alta: "Alta", media: "Media", baja: "Baja" };
const COLOR_CAT = {
  alta: "bg-error-container text-on-error-container",
  media: "bg-ambar-container text-ambar",
  baja: "bg-verde-container text-verde",
};
const EVENTOS = {
  urgencia: { label: "Urgencia (triage ESI 2)", tipo_evento: "visita_urgencia", subtipo: "triage ESI 2", severidad: "grave" },
  hospitalizacion: { label: "Nueva hospitalización", tipo_evento: "hospitalizacion", subtipo: "ingreso hospitalario", severidad: "grave" },
  examen: { label: "Examen alterado", tipo_evento: "examen_alterado", subtipo: "resultado alterado", severidad: "moderada" },
  mejora: { label: "Buena respuesta en APS", tipo_evento: "control_aps", subtipo: "buena respuesta", severidad: "leve" },
};
const FACTOR = {
  riesgo_vital: "Riesgo vital", prioridad_inicial: "Prioridad inicial", evento: "Evento posterior a la SIC",
  tabla_oficial: "Tabla oficial HLF", dias_espera: "Tiempo en lista", ges: "Garantía GES", medicion: "Medición",
};
const POR_PAGINA = 25;

const Icono = ({ n, className = "" }) => <span className={`material-symbols-outlined align-middle ${className}`}>{n}</span>;
const Badge = ({ cat, grande }) => (
  <span className={`inline-flex items-center gap-1 ${grande ? "px-2.5 py-1" : "px-2 py-0.5"} font-bold uppercase text-[10px] tracking-wider ${COLOR_CAT[cat]}`}>
    {cat === "alta" && <Icono n="priority_high" className="text-[13px]" />}{ETIQUETA[cat]}
  </span>
);
const Chip = ({ icon, children, tono = "neutro", title }) => {
  const t = { rojo: "bg-error-container text-on-error-container", ambar: "bg-ambar-container text-ambar", neutro: "bg-surface-container-high text-on-surface-variant", lila: "bg-tertiary-fixed text-on-tertiary-fixed-variant" }[tono];
  return <span title={title} className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-bold whitespace-nowrap ${t}`}>{icon && <Icono n={icon} className="text-[13px]" />}{children}</span>;
};

export default function App() {
  const fechas = api.fechas();
  const [iFecha, setIFecha] = useState(fechas.length - 1);
  const [esp, setEsp] = useState("Todas");
  const [vista, setVista] = useState("lista");
  const [data, setData] = useState(null);
  const [sel, setSel] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [destacado, setDestacado] = useState(null);
  const [error, setError] = useState(null);
  const [busca, setBusca] = useState("");
  const [filtroCat, setFiltroCat] = useState("todas");
  const [soloPend, setSoloPend] = useState(false);
  const [pagina, setPagina] = useState(0);
  const fecha = fechas[iFecha];
  const esApi = api.MODO === "api";

  const cargar = useCallback(async () => {
    try { setError(null); setData(await api.getPacientes(fecha, esp === "Todas" ? null : esp)); }
    catch (e) { setError(e.message); }
  }, [fecha, esp]);
  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    if (!sel) return setDetalle(null);
    api.getPaciente(sel, fecha).then(setDetalle).catch(() => setDetalle(null));
  }, [sel, fecha, data]);
  useEffect(() => setPagina(0), [busca, filtroCat, soloPend, esp]);

  const filtrados = useMemo(() => {
    if (!data) return [];
    const q = busca.trim().toLowerCase();
    return data.pacientes.filter((p) =>
      (filtroCat === "todas" || (filtroCat === "vital" ? p.riesgo_vital : p.categoria === filtroCat)) &&
      (!soloPend || p.estado_revision === "pendiente") &&
      (!q || p.nombre_fantasia.toLowerCase().includes(q) || p.id_paciente.toLowerCase().includes(q) || p.diagnostico_texto.toLowerCase().includes(q)));
  }, [data, busca, filtroCat, soloPend]);

  const mostrarAviso = (a) => { setAviso(a); setTimeout(() => setAviso(null), 6000); };

  if (!data) return <div className="p-10 font-head text-lg">{error ? `Error: ${error}` : "Cargando…"}</div>;
  const paciente = sel && data.pacientes.find((p) => p.id_paciente === sel);
  const vitales = data.pacientes.filter((p) => p.riesgo_vital);
  const kpi = {
    alta: data.pacientes.filter((p) => p.categoria === "alta").length,
    ges: data.pacientes.filter((p) => p.ges?.vencida).length,
  };
  const pagina_ = filtrados.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA);
  const paginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));

  return (
    <>
      <header className="fixed top-0 inset-x-0 z-50 bg-surface-container-lowest border-b border-outline-variant shadow-[0_1px_8px_rgba(0,0,0,0.04)]">
        <div className="h-20 max-w-[1440px] mx-auto px-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4 shrink-0">
            <div className="w-9 h-9 bg-primary flex items-center justify-center"><Icono n="ecg_heart" className="text-on-primary text-[22px]" /></div>
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <span className="font-head text-[20px] font-semibold text-primary tracking-tight">Ambulatorio Dinámico</span>
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 border border-primary/20 bg-surface-container-low text-primary text-[9px] font-bold tracking-wider uppercase">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${esApi ? "bg-primary-container animate-pulse" : "bg-outline"}`} />{esApi ? "API conectada" : "modo demo (mock)"}
                </span>
              </div>
              <span className="text-[11px] text-on-surface-variant">Hospital Clínico Dra. Eloísa Díaz La Florida</span>
            </div>
          </div>
          <span className="hidden xl:block text-[11px] italic text-secondary">«La lista de espera es una foto; la salud de las personas, una película»</span>
          <div className="flex items-center gap-1 text-[11px] font-semibold flex-wrap justify-end">
            <Pill color="bg-surface-container-low" dot="bg-secondary">{data.total} en espera</Pill>
            <Pill color="bg-error text-on-error border-error" dot="bg-on-error">{vitales.length} riesgo vital</Pill>
            <Pill color="bg-error-container text-on-error-container border-error/30" dot="bg-error">{kpi.alta} prioridad alta</Pill>
            <Pill color="bg-surface-container" dot="bg-tertiary">{kpi.ges} GES vencidas</Pill>
            <Pill color="bg-surface-container text-on-surface-variant" dot="bg-outline">{data.excluidos.length} excluidos</Pill>
          </div>
        </div>
        <div className="border-t border-outline-variant">
          <nav className="max-w-[1440px] mx-auto px-6 flex gap-1 text-[11px] font-semibold uppercase tracking-wider">
            {[["lista", "Lista priorizada"], ["box", "Asignación de box"], ["criterios", "Criterios y fuentes"]].map(([k, t]) => (
              <button key={k} onClick={() => setVista(k)}
                className={`px-4 py-2.5 border-b-2 ${vista === k ? "border-primary text-primary font-bold bg-surface-container-low" : "border-transparent text-on-surface-variant hover:bg-surface-container"}`}>{t}</button>
            ))}
          </nav>
        </div>
      </header>

      <main className="max-w-[1440px] mx-auto px-6 pt-32 pb-8">
        <AnimatePresence>
          {aviso && (
            <motion.aside initial={{ y: -10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ opacity: 0 }} className="fixed top-24 inset-x-0 z-40 flex justify-center pointer-events-none">
              <div className="inline-flex items-center gap-3 px-4 py-2 bg-surface-container-lowest shadow-lg text-[11px] font-semibold">
                <span className="text-primary uppercase tracking-wider flex items-center gap-1"><Icono n="bolt" className="text-[18px]" />{aviso.titulo}</span>
                {aviso.antes != null && <>
                  <span className="w-1.5 h-1.5 bg-outline-variant" />
                  <span className="bg-surface-container-high px-1.5 py-0.5 font-bold">#{aviso.antes}</span>
                  <Icono n="arrow_forward" className="text-[16px] text-error" />
                  <span className="bg-error-container text-on-error-container px-1.5 py-0.5 font-bold">#{aviso.despues}</span>
                  {aviso.cat && <Badge cat={aviso.cat} />}
                </>}
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
        {error && <div className="bg-error-container text-on-error-container p-3 mb-3">{error}</div>}

        {vista !== "criterios" && (
          <section className="bg-surface-container-lowest p-4 shadow-sm mb-4 flex flex-col xl:flex-row xl:items-center gap-4">
            <div className="flex-1 bg-surface-container-low p-3">
              <div className="flex items-center justify-between text-[11px] font-semibold">
                <div className="flex items-center gap-2 text-primary font-bold uppercase tracking-wider">
                  <Icono n="history" className="text-[18px]" />Fecha de corte:
                  <span className="bg-primary text-on-primary px-2 py-0.5 text-[12px]">{fecha}</span>
                </div>
                <span className="text-secondary text-[9px] hidden md:flex items-center gap-1"><Icono n="info" className="text-[14px]" />Solo se usan registros con fecha ≤ corte</span>
              </div>
              <input type="range" min={0} max={fechas.length - 1} value={iFecha} onChange={(e) => setIFecha(+e.target.value)} className="w-full mt-2 accent-[#004c60]" />
              <div className="flex justify-between text-[9px] uppercase tracking-wider text-on-surface-variant">
                <span>{fechas[0]}</span><span className="font-bold text-primary">{fechas[fechas.length - 1]} (actual)</span>
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <Campo label="Especialidad">
                <select value={esp} onChange={(e) => setEsp(e.target.value)} className="bg-transparent px-2 h-9 font-semibold focus:outline-none">
                  {ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}
                </select>
              </Campo>
              {vista === "lista" && <>
                <Campo label="Búsqueda directa">
                  <Icono n="search" className="text-secondary text-[18px] ml-2" />
                  <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nombre, ID o diagnóstico…" className="bg-transparent px-2 h-9 w-48 focus:outline-none" />
                </Campo>
                <Campo label="Prioridad">
                  <select value={filtroCat} onChange={(e) => setFiltroCat(e.target.value)} className="bg-transparent px-2 h-9 focus:outline-none">
                    <option value="todas">Todas</option><option value="vital">Riesgo vital</option>
                    <option value="alta">Alta</option><option value="media">Media</option><option value="baja">Baja</option>
                  </select>
                </Campo>
                <Campo label="Validación">
                  <label className="inline-flex items-center gap-2 px-3 h-9 cursor-pointer select-none bg-surface-container-low">
                    <input type="checkbox" checked={soloPend} onChange={(e) => setSoloPend(e.target.checked)} className="w-4 h-4 accent-[#004c60]" />
                    <span className="text-[11px] font-semibold uppercase">Solo pendientes</span>
                  </label>
                </Campo>
              </>}
            </div>
          </section>
        )}

        {vista === "lista" && vitales.length > 0 && (
          <section className="bg-error text-on-error p-3 mb-4 flex items-start gap-3 shadow-sm">
            <Icono n="emergency" className="text-[24px]" />
            <div className="flex-1">
              <div className="font-head font-bold text-[15px]">Atención hoy: {vitales.length} paciente{vitales.length > 1 ? "s" : ""} con riesgo vital</div>
              <div className="text-[11px] opacity-90">Descompensación grave sin estabilización posterior, en un diagnóstico que la tabla oficial del HLF clasifica como Alta. No esperar cupo: contactar hoy y evaluar derivación a urgencia según criterio médico.</div>
              <div className="flex flex-wrap gap-1 mt-2">
                {vitales.slice(0, 12).map((p) => (
                  <button key={p.id_paciente} onClick={() => setSel(p.id_paciente)} className="bg-on-error/15 hover:bg-on-error/30 px-2 py-0.5 text-[11px] font-semibold">
                    #{p.posicion} {p.nombre_fantasia} · {p.diagnostico_texto}
                  </button>
                ))}
                {vitales.length > 12 && <span className="text-[11px] px-2">+{vitales.length - 12} más (filtro "Riesgo vital")</span>}
              </div>
            </div>
          </section>
        )}

        {vista === "box" && <Boxes fecha={fecha} esp={esp === "Todas" ? null : esp} onVer={(id) => { setSel(id); setVista("lista"); }} />}
        {vista === "criterios" && <Criterios />}
        {vista === "lista" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
            <div className="lg:col-span-8 flex flex-col gap-4">
              <section className="bg-surface-container-lowest shadow-sm overflow-hidden">
                <div className="px-3 py-2.5 bg-surface-container-high flex items-center justify-between">
                  <div className="flex items-center gap-2 font-head text-[16px] font-semibold text-primary uppercase tracking-tight"><Icono n="format_list_numbered" className="text-[20px]" />Lista priorizada</div>
                  <span className="text-[9px] text-secondary uppercase tracking-widest font-bold">Muestra {pagina_.length} de {filtrados.length}</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-surface-container text-[10px] font-semibold text-secondary uppercase tracking-wider">
                        <th className="py-2.5 px-3">Pos. y mov.</th><th className="py-2.5 px-2">Prioridad</th>
                        <th className="py-2.5 px-3">Paciente y diagnóstico CIE-10</th><th className="py-2.5 px-2">Alertas</th>
                        <th className="py-2.5 px-3 text-right">En lista</th><th className="py-2.5 px-3">Revisión</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-container-high text-[11px]">
                      <AnimatePresence initial={false}>
                        {pagina_.map((p) => {
                          const delta = p.posicion_anterior ? p.posicion_anterior - p.posicion : 0;
                          const activo = sel === p.id_paciente;
                          return (
                            <motion.tr key={p.id_paciente} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                              transition={{ type: "spring", stiffness: 300, damping: 30 }} onClick={() => setSel(p.id_paciente)}
                              className={`cursor-pointer transition-colors ${activo ? "bg-surface-container-low outline outline-2 outline-primary" : "hover:bg-surface-container"} ${destacado === p.id_paciente ? "bg-ambar-container" : ""} ${p.riesgo_vital ? "border-l-4 border-l-error" : ""}`}>
                              <td className="py-2.5 px-3 whitespace-nowrap">
                                <div className="flex items-center gap-2">
                                  <span className={`font-bold ${activo ? "text-primary text-[18px]" : "text-[14px]"}`}>#{p.posicion}</span>
                                  <span className={`text-[9px] px-1.5 py-0.5 font-bold ${delta > 0 ? "bg-error-container text-on-error-container" : delta < 0 ? "bg-surface-container-high text-primary" : "bg-surface-container-high text-on-surface-variant"}`}>
                                    {delta > 0 ? `▲ ${delta}` : delta < 0 ? `▼ ${-delta}` : "— 0"}
                                  </span>
                                </div>
                              </td>
                              <td className="py-2.5 px-2 whitespace-nowrap"><Badge cat={p.categoria} /></td>
                              <td className="py-2.5 px-3">
                                <div className="font-head text-[14px] font-semibold">{p.nombre_fantasia}{p.estado_revision !== "pendiente" && <Icono n="check_circle" className="text-primary text-[16px] ml-1" />}</div>
                                <div className="text-secondary truncate max-w-[340px]">{p.especialidad} · {p.diagnostico_cie10} {p.diagnostico_texto}</div>
                              </td>
                              <td className="py-2.5 px-2">
                                <div className="flex flex-wrap gap-1">
                                  {p.riesgo_vital && <Chip icon="emergency" tono="rojo">Riesgo vital</Chip>}
                                  {!p.riesgo_vital && p.estado_clinico === "descompensado" && <Chip icon="trending_up" tono="rojo">Descompensado</Chip>}
                                  {p.ges?.vencida && <Chip icon="gavel" tono="lila" title={`GES N°${p.ges.problema}: ${p.ges.plazo_dias} días`}>GES vencida</Chip>}
                                  {p.riesgo_inasistencia && <Chip icon="event_busy" tono="ambar" title="2 inasistencias consecutivas (causal 8)">Inasistencia</Chip>}
                                  {p.estado_clinico === "estabilizado" && <Chip icon="trending_down">Estabilizado</Chip>}
                                  {!p.riesgo_vital && p.estado_clinico === "sin_cambios" && !p.ges?.vencida && !p.riesgo_inasistencia && <span className="text-secondary">—</span>}
                                </div>
                              </td>
                              <td className="py-2.5 px-3 text-right whitespace-nowrap">
                                <span className="font-bold">{p.dias_espera} d</span>{p.antiguedad_mayor_1_anio && <div className="text-[9px] text-tertiary font-bold">+1 AÑO</div>}
                              </td>
                              <td className="py-2.5 px-3 whitespace-nowrap">
                                {p.estado_revision === "pendiente"
                                  ? <span className="inline-flex items-center gap-1 text-[9px] text-secondary font-bold uppercase bg-surface-container px-2 py-1"><Icono n="schedule" className="text-[15px]" />Pendiente</span>
                                  : <span className="inline-flex items-center gap-1 text-[9px] text-primary font-bold uppercase bg-surface-container-low px-2 py-1"><Icono n="check_circle" className="text-[15px]" />{p.estado_revision}</span>}
                              </td>
                            </motion.tr>
                          );
                        })}
                      </AnimatePresence>
                    </tbody>
                  </table>
                  {filtrados.length === 0 && <p className="p-6 text-secondary">Sin pacientes con esos filtros.</p>}
                </div>
                <div className="bg-surface-container-low px-3 py-2 flex items-center justify-between text-[9px] text-secondary uppercase font-bold">
                  <span>Orden: categoría → riesgo vital → antigüedad &gt; 1 año → llegada (MINSAL Ord. 536/2025)</span>
                  <div className="flex items-center gap-2">
                    <button disabled={pagina === 0} onClick={() => setPagina(pagina - 1)} className="px-2 py-1 bg-surface-container-lowest disabled:opacity-40">Anterior</button>
                    <span className="text-on-surface">Página {pagina + 1} de {paginas}</span>
                    <button disabled={pagina >= paginas - 1} onClick={() => setPagina(pagina + 1)} className="px-2 py-1 bg-surface-container-lowest disabled:opacity-40">Siguiente</button>
                  </div>
                </div>
              </section>

              {data.excluidos.length > 0 && (
                <section className="bg-surface-container-low shadow-sm">
                  <details className="group">
                    <summary className="px-3 py-2 bg-surface-container flex items-center justify-between cursor-pointer select-none">
                      <span className="flex items-center gap-2 font-head text-[15px] font-bold text-secondary"><Icono n="expand_more" className="text-[18px] transition-transform group-open:rotate-180" />Excluidos de la lista activa ({data.excluidos.length})</span>
                      <span className="text-[9px] uppercase bg-surface-container-high px-2 py-0.5 text-secondary font-bold">Causal 9 · Manual SSMSO</span>
                    </summary>
                    <div className="p-3 divide-y divide-surface-container">
                      {data.excluidos.map((e) => (
                        <div key={e.id_paciente} className="py-2 flex items-center justify-between">
                          <span className="flex items-center gap-2"><Icono n="person_off" className="text-outline text-[18px]" /><b>{e.id_paciente}</b> — {e.motivo}{e.fecha_defuncion && ` (${e.fecha_defuncion})`}</span>
                          <span className="text-[9px] bg-surface-container-high px-2 py-1 uppercase font-bold">Egreso</span>
                        </div>
                      ))}
                    </div>
                  </details>
                </section>
              )}
            </div>

            <aside className="lg:col-span-4 lg:sticky lg:top-28 flex flex-col gap-3 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto">
              {!paciente ? <section className="bg-surface-container-lowest p-6 shadow-sm text-secondary">Selecciona un paciente de la lista.</section> : (
                <Panel key={paciente.id_paciente} p={paciente} detalle={detalle} fecha={fecha} esApi={esApi} onCambio={cargar} onAviso={mostrarAviso}
                  onDestacar={(id) => { setDestacado(id); setTimeout(() => setDestacado(null), 3000); }} />
              )}
            </aside>
          </div>
        )}
      </main>
      <footer className="w-full bg-surface-container-low border-t border-outline-variant">
        <div className="max-w-[1440px] mx-auto px-6 py-3 flex flex-col md:flex-row justify-between gap-2 text-[9px] text-on-surface-variant uppercase tracking-wider font-bold">
          <span className="flex items-center gap-1"><Icono n="verified" className="text-primary text-[14px]" />Priorización según tabla SSMSO 2025 (HLF) y criterios MINSAL · la herramienta propone, el equipo clínico decide</span>
          <span>Datos 100% sintéticos · Hackatón AWS Breaking Barriers 2026</span>
        </div>
      </footer>
    </>
  );
}

const Pill = ({ color, dot, children }) => (
  <div className={`flex items-center gap-1.5 px-2 py-1 border border-outline-variant ${color}`}><span className={`w-1.5 h-1.5 ${dot}`} /><span>{children}</span></div>
);
const Campo = ({ label, children }) => (
  <div className="flex flex-col">
    <label className="text-[9px] font-bold uppercase tracking-wider text-secondary mb-0.5">{label}</label>
    <div className="relative inline-flex items-center bg-surface-container-lowest shadow-sm h-9 border border-outline-variant/60">{children}</div>
  </div>
);
const Tarjeta = ({ titulo, icon, children, className = "" }) => (
  <section className={`bg-surface-container-lowest p-3 shadow-sm ${className}`}>
    {titulo && <div className="flex items-center justify-between mb-2 bg-surface-container px-2 py-1 text-[11px] font-bold uppercase tracking-wider text-primary"><span>{titulo}</span>{icon && <Icono n={icon} className="text-[16px]" />}</div>}
    {children}
  </section>
);

function Panel({ p, detalle, fecha, esApi, onCambio, onAviso, onDestacar }) {
  const [explicacion, setExplicacion] = useState(null);
  const [cargando, setCargando] = useState(null);
  const [ajuste, setAjuste] = useState(null);
  const [tipoEv, setTipoEv] = useState("hospitalizacion");
  useEffect(() => { setExplicacion(null); }, [p.categoria, p.estado_clinico, fecha]);

  const correr = async (nombre, fn) => {
    setCargando(nombre);
    try { await fn(); } catch (e) { onAviso({ titulo: "Error: " + e.message }); } finally { setCargando(null); }
  };
  const registrarEvento = (ev, origen) => correr("evento", async () => {
    const r = await api.postEvento({ id_paciente: p.id_paciente, fecha_corte: fecha, fecha_evento: ev.fecha_evento || fecha,
      tipo_evento: ev.tipo_evento, subtipo: ev.subtipo, severidad: ev.severidad, detalle: ev.detalle });
    await onCambio(); onDestacar(p.id_paciente);
    onAviso({ titulo: `${origen} · reevaluado en ${r.reevaluado_en_ms} ms`, antes: r.posicion_antes, despues: r.posicion_despues, cat: r.paciente?.categoria });
  });
  const confirmar = () => correr("rev", async () => { await api.postRevision(p.id_paciente, { accion: "confirmar" }); await onCambio(); onAviso({ titulo: "Prioridad confirmada por el equipo clínico" }); });
  const guardarAjuste = () => correr("rev", async () => {
    await api.postRevision(p.id_paciente, { accion: "ajustar", categoria_ajustada: ajuste.categoria, motivo: ajuste.motivo });
    setAjuste(null); await onCambio(); onAviso({ titulo: "Ajuste registrado con su motivo" });
  });
  const pedirExplicacion = () => correr("ia", async () => setExplicacion(await api.postExplicar(p.id_paciente, fecha)));

  const timeline = detalle ? [
    ...detalle.eventos_clinicos.map((e) => ({ f: e.fecha_evento, t: `${e.tipo_evento.replace("_", " ")}: ${e.subtipo}`, d: e.detalle, tipo: e.severidad === "grave" ? "rojo" : "azul", nuevo: e.id_evento?.startsWith("EV-DEMO") })),
    ...detalle.mediciones.map((m) => ({ f: m.fecha_medicion, t: `${m.tipo_medicion} = ${m.valor} ${m.unidad}`, d: m.fuera_de_rango ? "Fuera de rango" : "En rango", tipo: m.fuera_de_rango ? "ambar" : "gris" })),
    ...(detalle.citaciones || []).map((c) => ({ f: c.fecha_cita, t: `Cita ${c.id_box}`, d: c.estado_cita.replace("_", " "), tipo: c.estado_cita === "no_asistio" ? "ambar" : "gris" })),
    { f: p.fecha_ingreso_lista, t: "Ingreso interconsulta", d: `Prioridad inicial ${p.prioridad_inicial}`, tipo: "gris" },
  ].sort((a, b) => b.f.localeCompare(a.f)) : [];
  const punto = { rojo: "bg-error", azul: "bg-primary", ambar: "bg-ambar", gris: "bg-outline" };

  return (
    <>
      <section className="bg-surface-container-lowest p-3 shadow-sm">
        <div className="flex items-start justify-between mb-2">
          <div>
            <div className="font-head text-[20px] font-semibold text-primary">{p.nombre_fantasia}</div>
            <div className="text-[11px] text-secondary">{p.edad} años · {p.sexo === "F" ? "Femenino" : "Masculino"} · {p.comuna} · {p.id_paciente}</div>
          </div>
          {p.riesgo_vital ? <span className="bg-error text-on-error px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider">Riesgo vital</span>
            : <Badge cat={p.categoria} grande />}
        </div>
        <div className="bg-surface-container-low p-2 mb-2">
          <div className="text-[9px] text-secondary uppercase tracking-wider font-bold">Diagnóstico de la interconsulta · {p.especialidad}</div>
          <div className="text-[14px] font-bold">{p.diagnostico_cie10} {p.diagnostico_texto}</div>
        </div>
        <div className="flex items-center justify-between text-[11px] font-semibold">
          <span className="text-secondary">Prioridad inicial: <b className="text-on-surface uppercase">{p.prioridad_inicial}</b> · #{p.posicion} · {p.dias_espera} días</span>
          <span className="px-2 py-0.5 bg-secondary-container text-on-secondary-container uppercase font-bold text-[9px]">{p.estado_revision}</span>
        </div>
        {p.categoria !== p.categoria_sistema && <p className="mt-2 text-[11px] text-tertiary">El sistema proponía {p.categoria_sistema}; el equipo clínico ajustó a {p.categoria}: {p.revision?.motivo}</p>}
      </section>

      <Tarjeta titulo={`Por qué está en prioridad ${ETIQUETA[p.categoria]}`} icon="receipt_long">
        <div className="space-y-1.5">
          {p.razones.map((r, i) => (
            <div key={i} className={`p-1.5 ${r.factor === "riesgo_vital" ? "bg-error text-on-error" : r.factor === "tabla_oficial" ? "bg-error-container text-on-error-container" : ""}`}>
              <div><b>{FACTOR[r.factor] || r.factor}:</b> {r.valor}</div>
              <div className={`text-[9px] italic ${r.factor === "riesgo_vital" ? "opacity-90" : "text-secondary"}`}>{r.fuente}</div>
            </div>
          ))}
        </div>
      </Tarjeta>

      {esApi ? (
        <>
          <Informe p={p} fecha={fecha} cargando={cargando} onConfirmar={(ev) => registrarEvento(ev, "Informe confirmado")} onAviso={onAviso} />

          <section className="bg-tertiary-fixed p-3 shadow-sm outline outline-1 outline-tertiary">
            <div className="flex items-center justify-between mb-2">
              <span className="flex items-center gap-1.5 text-on-tertiary-fixed text-[11px] font-bold uppercase tracking-wider"><Icono n="psychology" className="text-[16px]" />Explicación IA</span>
              <button onClick={pedirExplicacion} disabled={cargando} className="bg-tertiary text-on-primary px-2 py-0.5 text-[9px] uppercase tracking-wider font-bold disabled:opacity-50">{cargando === "ia" ? "Generando…" : "Explicar"}</button>
            </div>
            {explicacion ? <>
              <p className="text-[11px] text-on-tertiary-fixed-variant leading-relaxed bg-surface-container-lowest p-2">{explicacion.explicacion_ia}</p>
              <div className="text-[9px] text-on-tertiary-fixed-variant mt-1 uppercase flex items-center gap-1"><Icono n="verified_user" className="text-[12px]" />{explicacion.fuente === "bedrock" ? "Amazon Bedrock" : "Plantilla (Bedrock no configurado)"} · la IA solo redacta, no prioriza</div>
            </> : <p className="text-[11px] text-on-tertiary-fixed-variant">Redacta en lenguaje claro las razones de arriba. No cambia la prioridad.</p>}
          </section>

          <div className="flex flex-col gap-2">
            <button onClick={confirmar} disabled={cargando} className="w-full py-2.5 bg-primary hover:bg-primary-container text-on-primary text-[11px] uppercase tracking-wider font-bold flex items-center justify-center gap-2 disabled:opacity-50"><Icono n="verified" className="text-[18px]" />Confirmar prioridad #{p.posicion}</button>
            <button onClick={() => setAjuste(ajuste ? null : { categoria: p.categoria, motivo: "" })} className="w-full py-2 bg-surface-container-lowest hover:bg-surface-container text-primary text-[11px] uppercase tracking-wider font-bold shadow-sm">Ajustar prioridad (con motivo)</button>
            {ajuste && (
              <div className="bg-surface-container-lowest p-2 shadow-sm flex flex-col gap-2">
                <select value={ajuste.categoria} onChange={(e) => setAjuste({ ...ajuste, categoria: e.target.value })} className="bg-surface-container-low px-2 py-1.5">
                  {Object.entries(ETIQUETA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <input placeholder="Motivo clínico (obligatorio)" value={ajuste.motivo} onChange={(e) => setAjuste({ ...ajuste, motivo: e.target.value })} className="bg-surface-container-low px-2 py-1.5" />
                <button disabled={!ajuste.motivo} onClick={guardarAjuste} className="bg-primary text-on-primary py-1.5 font-bold uppercase text-[11px] disabled:opacity-40">Guardar ajuste</button>
              </div>
            )}
          </div>

          <Tarjeta titulo="Simular evento clínico" icon="science">
            <div className="flex items-center gap-2">
              <select value={tipoEv} onChange={(e) => setTipoEv(e.target.value)} className="flex-1 bg-surface-container-low px-2 py-1.5">
                {Object.entries(EVENTOS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
              <button onClick={() => registrarEvento(EVENTOS[tipoEv], "Evento simulado")} disabled={cargando} className="bg-error text-on-error px-3 py-1.5 text-[11px] uppercase font-bold disabled:opacity-50">{cargando === "evento" ? "…" : "Simular"}</button>
            </div>
          </Tarjeta>
        </>
      ) : <Tarjeta><p className="text-secondary">Conecta la API (VITE_API_URL) para leer informes, confirmar, simular eventos y explicar con IA.</p></Tarjeta>}

      <Tarjeta titulo="Línea de tiempo clínica" icon="timeline">
        <div className="relative pl-4 space-y-3">
          <div className="absolute left-1.5 top-2 bottom-2 w-0.5 bg-surface-container-high" />
          {timeline.map((x, i) => (
            <div key={i} className="relative flex items-start gap-2.5">
              <div className={`w-3 h-3 shrink-0 mt-0.5 ${punto[x.tipo]}`} />
              <div className={`flex-1 p-2 ${x.nuevo ? "bg-ambar-container" : "bg-surface-container-low"}`}>
                <div className={`text-[9px] font-bold uppercase ${x.tipo === "rojo" ? "text-error" : "text-secondary"}`}>{x.f}</div>
                <div className="font-bold">{x.t}</div>
                {x.d && <div className="text-secondary">{x.d}</div>}
              </div>
            </div>
          ))}
          {!detalle && <p className="text-secondary">Cargando…</p>}
        </div>
      </Tarjeta>
    </>
  );
}

// Achica la foto en el navegador para no superar el límite de la Lambda (6 MB) y la devuelve en base64.
function fotoABase64(archivo, lado = 1600) {
  return new Promise((ok, mal) => {
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, lado / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      ok(c.toDataURL("image/jpeg", 0.85).split(",")[1]);
    };
    img.onerror = () => mal(new Error("No se pudo abrir la imagen"));
    img.src = URL.createObjectURL(archivo);
  });
}

function Informe({ p, fecha, cargando, onConfirmar, onAviso }) {
  const [texto, setTexto] = useState("");
  const [res, setRes] = useState(null);
  const [leyendo, setLeyendo] = useState(false);
  const archivo = useRef(null);
  const analizar = async (body) => {
    setLeyendo(true); setRes(null);
    try { setRes(await api.postInforme(p.id_paciente, { ...body, fecha_corte: fecha })); }
    catch (e) { onAviso({ titulo: "Error: " + e.message }); }
    finally { setLeyendo(false); }
  };
  const foto = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (f) analizar({ imagen_base64: await fotoABase64(f), media_type: "image/jpeg" });
  };
  const ev = res?.evento;
  return (
    <Tarjeta titulo="Informe médico (chat)" icon="chat">
      <p className="text-[10px] text-secondary mb-2">Escribe, pega o fotografía la epicrisis, el DAU o la nota clínica. El sistema propone el evento y tú confirmas.</p>
      <textarea rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Ej: Consulta en urgencia por dolor torácico en reposo, ESI 2. Se hospitaliza en cardiología…"
        className="w-full bg-surface-container-low p-2 border border-outline-variant/60 focus:outline-none focus:border-primary resize-y" />
      <div className="flex gap-2 mt-2">
        <button disabled={!texto.trim() || leyendo} onClick={() => analizar({ texto })} className="flex-1 bg-primary text-on-primary py-1.5 text-[11px] font-bold uppercase disabled:opacity-40 flex items-center justify-center gap-1"><Icono n="send" className="text-[16px]" />{leyendo ? "Leyendo…" : "Analizar"}</button>
        <button disabled={leyendo} onClick={() => archivo.current.click()} className="flex-1 bg-surface-container-high py-1.5 text-[11px] font-bold uppercase flex items-center justify-center gap-1"><Icono n="photo_camera" className="text-[16px]" />Foto del papel</button>
        <input ref={archivo} type="file" accept="image/*" capture="environment" hidden onChange={foto} />
      </div>
      {res && !ev && <p className="mt-2 text-secondary">{res.mensaje}</p>}
      {res?.transcripcion && <details className="mt-2 text-[10px] text-secondary"><summary className="cursor-pointer">Texto leído de la foto</summary><p className="whitespace-pre-wrap">{res.transcripcion}</p></details>}
      {ev && (
        <div className="mt-2 border border-outline-variant p-2 space-y-1.5">
          <div><b>Evento detectado:</b> {ev.tipo_evento.replace("_", " ")} — {ev.subtipo} ({ev.severidad}) · {ev.fecha_evento}</div>
          <div className="bg-ambar-container border-l-4 border-ambar px-2 py-1 italic">“{ev.evidencia}”</div>
          <div className="flex items-center gap-2"><b>Prioridad:</b> <Badge cat={res.categoria_actual} /> <Icono n="arrow_forward" className="text-[16px]" /> <Badge cat={res.categoria_propuesta} /></div>
          {res.razones_propuestas?.map((r, i) => <div key={i} className="text-[10px] text-secondary italic">{r.valor} — {r.fuente}</div>)}
          <div className="text-[9px] text-secondary uppercase">Leído por: {res.fuente === "bedrock" ? "Amazon Bedrock" : "reglas de palabras clave"}</div>
          <div className="flex gap-2">
            <button disabled={cargando} onClick={async () => { await onConfirmar({ ...ev, detalle: `Informe: ${ev.evidencia}` }); setRes(null); setTexto(""); }}
              className="flex-1 bg-error text-on-error py-1.5 text-[11px] font-bold uppercase disabled:opacity-50">Confirmar y recalcular</button>
            <button onClick={() => setRes(null)} className="flex-1 bg-surface-container-high py-1.5 text-[11px] font-bold uppercase">Descartar</button>
          </div>
        </div>
      )}
    </Tarjeta>
  );
}

function Boxes({ fecha, esp, onVer }) {
  const [b, setB] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    if (api.MODO !== "api") return setErr("La asignación de box requiere la API (VITE_API_URL).");
    api.getBoxes(fecha, esp).then(setB).catch((e) => setErr(e.message));
  }, [fecha, esp]);
  if (err) return <Tarjeta><p className="text-secondary">{err}</p></Tarjeta>;
  if (!b) return <div className="p-6">Cargando box…</div>;
  const r = b.resumen;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Pill color="bg-surface-container-lowest" dot="bg-primary">Agenda del {b.dia_agenda}</Pill>
        <Pill color="bg-surface-container-lowest" dot="bg-secondary">Ocupación histórica {r.ocupacion_pct}%</Pill>
        <Pill color="bg-surface-container-lowest" dot="bg-ambar">{Math.round((r.inasistencias / r.citas) * 100)}% inasistencias</Pill>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {b.especialidades.map((e) => (
          <section key={e.especialidad} className="bg-surface-container-lowest shadow-sm">
            <div className="px-3 py-2 bg-surface-container-high flex items-center justify-between">
              <span className="font-head text-[15px] font-semibold text-primary">{e.especialidad}</span>
              <span className="text-[9px] text-secondary uppercase font-bold">{e.ocupacion_pct}% ocupación · {e.inasistencia_pct ?? "—"}% inasist.</span>
            </div>
            <div className="p-3 space-y-3">
              {e.asignaciones.length === 0 && <p className="text-secondary">Sin box asignado a esta especialidad ese día.</p>}
              {e.asignaciones.map((a) => (
                <div key={a.id_box}>
                  <div className="flex items-center justify-between text-[11px] font-bold uppercase text-secondary mb-1">
                    <span className="flex items-center gap-1"><Icono n="meeting_room" className="text-[16px] text-primary" />{a.id_box} · {a.bloque}</span>
                    <span>{a.libres} cupo{a.libres !== 1 ? "s" : ""} libre{a.libres !== 1 ? "s" : ""}</span>
                  </div>
                  {a.pacientes.map((p, i) => (
                    <button key={p.id_paciente} onClick={() => onVer(p.id_paciente)}
                      className={`w-full text-left p-2 mb-1 ${p.riesgo_vital ? "bg-error-container border-l-4 border-error" : "bg-surface-container-low"} hover:outline hover:outline-1 hover:outline-primary`}>
                      <div className="flex items-center justify-between">
                        <span className="font-bold">{i + 1}. {p.nombre_fantasia} <span className="text-secondary font-normal">#{p.posicion}</span></span>
                        <Badge cat={p.categoria} />
                      </div>
                      <div className="text-[10px] text-secondary">{p.diagnostico_texto} · {p.dias_espera} días</div>
                      <div className="text-[10px] mt-0.5"><b>Por qué:</b> {p.motivo}</div>
                      <div className={`text-[10px] font-bold uppercase mt-0.5 ${p.riesgo_vital ? "text-error" : p.riesgo_inasistencia ? "text-ambar" : "text-primary"}`}>→ {p.accion}</div>
                    </button>
                  ))}
                </div>
              ))}
              {e.alternativa && (
                <button onClick={() => onVer(e.alternativa.id_paciente)} className="w-full text-left p-2 border border-dashed border-outline hover:bg-surface-container">
                  <div className="text-[9px] uppercase font-bold text-secondary mb-0.5">Alternativa si alguien no confirma</div>
                  <div className="flex items-center justify-between"><span className="font-bold">{e.alternativa.nombre_fantasia} <span className="text-secondary font-normal">#{e.alternativa.posicion}</span></span><Badge cat={e.alternativa.categoria} /></div>
                  <div className="text-[10px] mt-0.5"><b>Va después porque:</b> {e.alternativa.por_que_despues}</div>
                </button>
              )}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function Criterios() {
  const filas = [["I50", "Insuficiencia cardíaca descompensada", "Alta", 85], ["I20", "Angina inestable", "Alta", 85],
    ["J44", "EPOC grave no controlado", "Alta", 95], ["J45", "Asma grave no controlada", "Alta", 95],
    ["K70", "Cirrosis hepática descompensada", "Alta", 95], ["E11", "DM2 descontrolada", "Media", 101],
    ["E03", "Hipotiroidismo sintomático", "Media", 94], ["G40", "Epilepsia con crisis mensuales", "Media", 103]];
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Tarjeta titulo="Cómo se ordena la lista" icon="rule">
        <ol className="list-decimal pl-5 space-y-2 text-[12px] leading-relaxed">
          <li><b>Categoría (Alta / Media / Baja).</b> Parte de la prioridad que asignó el especialista al leer la SIC. Si después el paciente se descompensa (evento que el especialista no vio), sube a la fila "descompensada / no controlada" de la <i>Tabla de priorización SSMSO 2025, Hospital Dra. Eloísa Díaz</i> (págs. 84–111). El sistema nunca baja una categoría solo.</li>
          <li><b>Riesgo vital.</b> Descompensación grave sin estabilización posterior en un diagnóstico cuya fila oficial es Alta → va primero y se avisa "contactar hoy". MINSAL: criticidad / riesgo vital (SSMSO 2025, pág. 4).</li>
          <li><b>Dentro de la categoría:</b> MINSAL Ord. 536 (21-03-2025): criterio médico → grupos de especial protección (sin datos en el dataset) → antigüedad en lista mayor a 1 año → orden de llegada.</li>
          <li><b>Banderas (no cambian el orden):</b> garantía GES vencida (auge.minsal.cl) · 2 inasistencias consecutivas = posible causal 8 (Manual SSMSO, Anexo 4) · última medición fuera de rango.</li>
          <li><b>Exclusión:</b> fallecimiento = causal 9 (Manual SSMSO, Anexo 4).</li>
        </ol>
      </Tarjeta>
      <Tarjeta titulo='Filas oficiales usadas para "descompensado"' icon="table">
        <table className="w-full text-[11px]">
          <thead><tr className="text-left text-secondary uppercase text-[9px]"><th className="py-1">CIE-10</th><th>Fila de la tabla HLF</th><th>Prioridad</th><th>Pág.</th></tr></thead>
          <tbody className="divide-y divide-surface-container-high">{filas.map(([c, f, pr, pg]) => <tr key={c}><td className="py-1 font-bold">{c}</td><td>{f}</td><td>{pr}</td><td>{pg}</td></tr>)}</tbody>
        </table>
        <p className="text-[10px] text-secondary mt-2">I10, K21, F32, F41, G43, E66, M17, M54 y M75 no tienen en la tabla del HLF una fila de "descompensado": mantienen su prioridad y el evento queda visible para revisión clínica.</p>
      </Tarjeta>
      <Tarjeta titulo="Garantías GES (atención por especialista)" icon="gavel">
        <p>Depresión N°34: 30 días · Hipertensión N°21: 45 · EPOC N°38: 45 · Diabetes tipo 2 N°7: 60 · Asma N°61: 60 · Epilepsia N°60: 60 · Artrosis de rodilla (55+) N°41: 120.</p>
      </Tarjeta>
      <Tarjeta titulo="Informes, fotos e IA" icon="psychology">
        <p>Amazon Bedrock solo transcribe fotos, extrae el evento con el vocabulario del registro citando la frase del informe, y redacta explicaciones. El equipo clínico confirma; la prioridad la calculan las reglas de arriba. No se predice el futuro de un paciente: se avisa con lo que ya ocurrió.</p>
      </Tarjeta>
    </div>
  );
}
