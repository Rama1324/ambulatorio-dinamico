import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as api from "./api";

const ESPECIALIDADES = ["Todas", "Cardiología", "Traumatología", "Endocrinología", "Salud Mental", "Broncopulmonar", "Neurología", "Gastroenterología"];
const ETIQUETA = { alta: "Alta", media: "Media", baja: "Baja" };
const COLOR_CAT = {
  alta: "bg-error-container text-on-error-container border-error/40",
  media: "bg-ambar-container text-ambar border-ambar/40",
  baja: "bg-verde-container text-verde border-verde/40",
};
const EVENTOS = {
  urgencia: { label: "Consulta en urgencia (ESI 2)", tipo_evento: "visita_urgencia", subtipo: "triage ESI 2", severidad: "grave" },
  hospitalizacion: { label: "Hospitalización", tipo_evento: "hospitalizacion", subtipo: "ingreso hospitalario", severidad: "grave" },
  examen: { label: "Examen alterado", tipo_evento: "examen_alterado", subtipo: "resultado alterado", severidad: "moderada" },
  mejora: { label: "Buena respuesta en APS", tipo_evento: "control_aps", subtipo: "buena respuesta", severidad: "leve" },
};
const FACTOR = {
  riesgo_vital: "Atención hoy", prioridad_inicial: "Priorización de la interconsulta", evento: "Evento posterior a la interconsulta",
  tabla_oficial: "Tabla de priorización HLF", dias_espera: "Tiempo de espera", ges: "Garantía GES", medicion: "Última medición",
};
const TIPO_EVENTO = { visita_urgencia: "Urgencia", hospitalizacion: "Hospitalización", examen_alterado: "Examen alterado", cambio_farmaco: "Cambio de fármaco", control_aps: "Control APS" };
const POR_PAGINA = 25;

const fmt = (iso) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");
const Icono = ({ n, className = "" }) => <span className={`material-symbols-outlined align-middle ${className}`}>{n}</span>;
const Prioridad = ({ cat }) => (
  <span className={`inline-block min-w-[58px] text-center px-2 py-0.5 rounded border text-[13px] font-semibold ${COLOR_CAT[cat]}`}>{ETIQUETA[cat]}</span>
);
const Marca = ({ children, tono = "gris", title }) => {
  const t = { rojo: "text-error border-error/40 bg-error-container/50", ambar: "text-ambar border-ambar/40 bg-ambar-container/50", gris: "text-on-surface-variant border-outline-variant bg-surface-container-low", azul: "text-primary border-primary/30 bg-primary/5" }[tono];
  return <span title={title} className={`inline-block px-1.5 py-px rounded border text-[12px] whitespace-nowrap ${t}`}>{children}</span>;
};
const Caja = ({ titulo, accion, children, className = "" }) => (
  <section className={`bg-surface-container-lowest border border-outline-variant rounded ${className}`}>
    {titulo && <div className="px-4 py-2.5 border-b border-outline-variant flex items-center justify-between"><h2 className="text-[15px] font-semibold">{titulo}</h2>{accion}</div>}
    <div className="p-4">{children}</div>
  </section>
);

export default function App() {
  const fechas = api.fechas();
  const esApi = api.MODO === "api";
  const [demo, setDemo] = useState(!esApi);
  const [iFecha, setIFecha] = useState(fechas.length - 1);
  const [esp, setEsp] = useState("Todas");
  const [vista, setVista] = useState(esApi ? "hoy" : "lista");
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
  const fecha = demo ? fechas[iFecha] : fechas[fechas.length - 1];

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
  const abrir = (id) => { setSel(id); setVista("lista"); };

  if (!data) return <div className="p-10 text-lg">{error ? `No se pudo cargar la lista: ${error}` : "Cargando lista de espera…"}</div>;
  const paciente = sel && data.pacientes.find((p) => p.id_paciente === sel);
  const vitales = data.pacientes.filter((p) => p.riesgo_vital);
  const altas = data.pacientes.filter((p) => p.categoria === "alta").length;
  const gesVenc = data.pacientes.filter((p) => p.ges?.vencida).length;
  const pendientes = data.pacientes.filter((p) => p.estado_revision === "pendiente" && p.estado_clinico === "descompensado").length;
  const pag = filtrados.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA);
  const paginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-surface-container-lowest border-b border-outline-variant">
        <div className="max-w-[1400px] mx-auto px-6 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded bg-primary text-on-primary flex items-center justify-center"><Icono n="local_hospital" className="text-[22px]" /></div>
            <div className="leading-tight">
              <div className="text-[17px] font-semibold text-primary">Lista de espera dinámica · Consultas de especialidad</div>
              <div className="text-[13px] text-on-surface-variant">Hospital Clínico Dra. Eloísa Díaz Inzunza · La Florida · SSMSO</div>
            </div>
          </div>
          <div className="flex items-center gap-3 text-[13px]">
            <span className="text-on-surface-variant">Lista al <b className="text-on-surface">{fmt(fecha)}</b></span>
            <label className="flex items-center gap-1.5 text-on-surface-variant cursor-pointer select-none border-l border-outline-variant pl-3">
              <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} className="accent-[#0b4f8a]" />Modo demostración
            </label>
          </div>
        </div>
        <nav className="max-w-[1400px] mx-auto px-6 flex gap-6 text-[14px]">
          {[["hoy", "Hoy", vitales.length], ["lista", "Lista de espera", null], ["criterios", "Criterios de priorización", null]].map(([k, t, n]) => (
            <button key={k} onClick={() => setVista(k)}
              className={`py-2.5 border-b-2 -mb-px ${vista === k ? "border-primary text-primary font-semibold" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}>
              {t}{n ? <span className="ml-1.5 px-1.5 rounded-full bg-error text-on-error text-[12px] font-semibold">{n}</span> : null}
            </button>
          ))}
        </nav>
      </header>

      {demo && (
        <div className="bg-ambar-container/60 border-b border-ambar/30">
          <div className="max-w-[1400px] mx-auto px-6 py-2 flex flex-wrap items-center gap-4 text-[13px]">
            <span className="font-semibold text-ambar flex items-center gap-1"><Icono n="science" className="text-[18px]" />Modo demostración{!esApi && " (datos precalculados, sin API)"}</span>
            <label className="flex items-center gap-2 flex-1 min-w-[280px]">
              Ver la lista como estaba el <b>{fmt(fechas[iFecha])}</b>
              <input type="range" min={0} max={fechas.length - 1} value={iFecha} onChange={(e) => setIFecha(+e.target.value)} className="flex-1 accent-[#8a5100]" />
            </label>
            <span className="text-on-surface-variant">Solo se usan registros con fecha anterior o igual.</span>
          </div>
        </div>
      )}

      <AnimatePresence>
        {aviso && (
          <motion.div initial={{ y: -8, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed top-4 left-1/2 -translate-x-1/2 z-50 bg-on-surface text-white px-4 py-2.5 rounded shadow-lg text-[14px] flex items-center gap-2">
            <Icono n="check_circle" className="text-[20px]" />{aviso.titulo}
            {aviso.antes != null && <span className="opacity-90">· posición {aviso.antes} → <b>{aviso.despues}</b>{aviso.cat && ` · prioridad ${ETIQUETA[aviso.cat]}`}</span>}
          </motion.div>
        )}
      </AnimatePresence>

      <main className="flex-1 max-w-[1400px] w-full mx-auto px-6 py-5">
        {error && <div className="bg-error-container text-on-error-container p-3 mb-4 rounded">{error}</div>}

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
          <Indicador n={data.total} t="Pacientes en espera" />
          <Indicador n={vitales.length} t="Contactar hoy" tono="rojo" onClick={() => setVista("hoy")} />
          <Indicador n={altas} t="Prioridad alta" />
          <Indicador n={pendientes} t="Descompensados sin revisar" tono={pendientes ? "ambar" : null} onClick={() => { setVista("lista"); setSoloPend(true); setFiltroCat("todas"); }} />
          <Indicador n={gesVenc} t="Garantías GES vencidas" />
        </div>

        {vista === "hoy" && <Hoy vitales={vitales} fecha={fecha} esp={esp} setEsp={setEsp} onVer={abrir} esApi={esApi} />}
        {vista === "criterios" && <Criterios />}
        {vista === "lista" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            <div className="lg:col-span-7 xl:col-span-8 flex flex-col gap-4">
              <div className="bg-surface-container-lowest border border-outline-variant rounded p-3 flex flex-wrap items-end gap-3 text-[13px]">
                <Filtro label="Especialidad">
                  <select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-white">{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select>
                </Filtro>
                <Filtro label="Buscar paciente">
                  <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nombre, ID o diagnóstico" className="h-9 px-2 w-56 border border-outline-variant rounded" />
                </Filtro>
                <Filtro label="Prioridad">
                  <select value={filtroCat} onChange={(e) => setFiltroCat(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-white">
                    <option value="todas">Todas</option><option value="vital">Contactar hoy</option><option value="alta">Alta</option><option value="media">Media</option><option value="baja">Baja</option>
                  </select>
                </Filtro>
                <label className="flex items-center gap-2 h-9 cursor-pointer select-none"><input type="checkbox" checked={soloPend} onChange={(e) => setSoloPend(e.target.checked)} className="w-4 h-4 accent-[#0b4f8a]" />Solo pendientes de revisión</label>
              </div>

              <section className="bg-surface-container-lowest border border-outline-variant rounded overflow-hidden">
                <table className="w-full text-left border-collapse text-[14px]">
                  <thead>
                    <tr className="bg-surface-container-low text-[13px] text-on-surface-variant border-b border-outline-variant">
                      <th className="py-2 px-3 font-semibold w-16">N°</th><th className="py-2 px-2 font-semibold">Prioridad</th>
                      <th className="py-2 px-3 font-semibold">Paciente / diagnóstico</th><th className="py-2 px-2 font-semibold">Observaciones</th>
                      <th className="py-2 px-3 font-semibold text-right">Espera</th><th className="py-2 px-3 font-semibold">Revisión</th>
                    </tr>
                  </thead>
                  <tbody>
                    <AnimatePresence initial={false}>
                      {pag.map((p) => {
                        const delta = p.posicion_anterior ? p.posicion_anterior - p.posicion : 0;
                        const activo = sel === p.id_paciente;
                        return (
                          <motion.tr key={p.id_paciente} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                            transition={{ type: "spring", stiffness: 300, damping: 32 }} onClick={() => setSel(p.id_paciente)}
                            className={`cursor-pointer border-b border-outline-variant/60 ${activo ? "bg-primary/10" : destacado === p.id_paciente ? "bg-ambar-container/60" : "hover:bg-surface-container-low"}`}>
                            <td className={`py-2.5 px-3 align-top ${p.riesgo_vital ? "border-l-4 border-l-error" : "border-l-4 border-l-transparent"}`}>
                              <div className="font-semibold">{p.posicion}</div>
                              {demo && delta !== 0 && <div className={`text-[12px] ${delta > 0 ? "text-error" : "text-on-surface-variant"}`}>{delta > 0 ? `▲ ${delta}` : `▼ ${-delta}`}</div>}
                            </td>
                            <td className="py-2.5 px-2 align-top"><Prioridad cat={p.categoria} /></td>
                            <td className="py-2.5 px-3 align-top">
                              <div className="font-semibold">{p.nombre_fantasia} <span className="font-normal text-on-surface-variant text-[13px]">· {p.edad} años</span></div>
                              <div className="text-[13px] text-on-surface-variant">{p.especialidad} · {p.diagnostico_cie10} {p.diagnostico_texto}</div>
                            </td>
                            <td className="py-2.5 px-2 align-top">
                              <div className="flex flex-wrap gap-1">
                                {p.riesgo_vital && <Marca tono="rojo">Contactar hoy</Marca>}
                                {!p.riesgo_vital && p.estado_clinico === "descompensado" && <Marca tono="rojo">Descompensado</Marca>}
                                {p.estado_clinico === "estabilizado" && <Marca>Estabilizado</Marca>}
                                {p.ges?.vencida && <Marca tono="azul" title={`GES N°${p.ges.problema}: plazo ${p.ges.plazo_dias} días`}>GES vencida</Marca>}
                                {p.riesgo_inasistencia && <Marca tono="ambar" title="2 inasistencias consecutivas (causal 8)">2 inasistencias</Marca>}
                              </div>
                            </td>
                            <td className="py-2.5 px-3 align-top text-right whitespace-nowrap">{p.dias_espera} días{p.antiguedad_mayor_1_anio && <div className="text-[12px] text-on-surface-variant">más de 1 año</div>}</td>
                            <td className="py-2.5 px-3 align-top text-[13px] whitespace-nowrap">
                              {p.estado_revision === "pendiente" ? <span className="text-on-surface-variant">Pendiente</span>
                                : <span className="text-verde font-semibold"><Icono n="check" className="text-[16px]" /> {p.estado_revision === "ajustado" ? "Ajustada" : "Confirmada"}</span>}
                            </td>
                          </motion.tr>
                        );
                      })}
                    </AnimatePresence>
                  </tbody>
                </table>
                {filtrados.length === 0 && <p className="p-6 text-on-surface-variant">No hay pacientes con esos filtros.</p>}
                <div className="px-3 py-2 flex items-center justify-between text-[13px] text-on-surface-variant bg-surface-container-low">
                  <span>{filtrados.length} pacientes · orden: prioridad, contactar hoy, más de 1 año en espera, fecha de ingreso</span>
                  <div className="flex items-center gap-2">
                    <button disabled={pagina === 0} onClick={() => setPagina(pagina - 1)} className="px-2 py-1 border border-outline-variant rounded bg-white disabled:opacity-40">Anterior</button>
                    <span>{pagina + 1} / {paginas}</span>
                    <button disabled={pagina >= paginas - 1} onClick={() => setPagina(pagina + 1)} className="px-2 py-1 border border-outline-variant rounded bg-white disabled:opacity-40">Siguiente</button>
                  </div>
                </div>
              </section>

              {data.excluidos.length > 0 && (
                <details className="bg-surface-container-lowest border border-outline-variant rounded">
                  <summary className="px-4 py-2.5 cursor-pointer text-[14px] font-semibold">Egresados de la lista por fallecimiento ({data.excluidos.length})</summary>
                  <ul className="px-4 pb-3 text-[13px] text-on-surface-variant">
                    {data.excluidos.map((e) => <li key={e.id_paciente} className="py-1 border-t border-outline-variant/60">{e.id_paciente} · fallecimiento {fmt(e.fecha_defuncion)} · causal de egreso 9</li>)}
                  </ul>
                </details>
              )}
            </div>

            <aside className="lg:col-span-5 xl:col-span-4 lg:sticky lg:top-4 flex flex-col gap-3 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
              {!paciente ? <Caja><p className="text-on-surface-variant">Seleccione un paciente para ver el detalle.</p></Caja> : (
                <Ficha key={paciente.id_paciente} p={paciente} detalle={detalle} fecha={fecha} esApi={esApi} demo={demo} onCambio={cargar} onAviso={mostrarAviso}
                  onDestacar={(id) => { setDestacado(id); setTimeout(() => setDestacado(null), 3000); }} />
              )}
            </aside>
          </div>
        )}
      </main>

      <footer className="border-t border-outline-variant bg-surface-container-lowest">
        <div className="max-w-[1400px] mx-auto px-6 py-3 text-[12px] text-on-surface-variant flex flex-wrap justify-between gap-2">
          <span>Prioridad según Tabla de priorización SSMSO 2025 (HLF) y criterios MINSAL. La herramienta propone; el equipo clínico decide.</span>
          <span>Datos sintéticos de demostración</span>
        </div>
      </footer>
    </div>
  );
}

const Indicador = ({ n, t, tono, onClick }) => {
  const c = tono === "rojo" ? "border-l-error text-error" : tono === "ambar" ? "border-l-ambar text-ambar" : "border-l-primary text-on-surface";
  return (
    <button onClick={onClick} disabled={!onClick} className={`text-left bg-surface-container-lowest border border-outline-variant border-l-4 rounded px-3 py-2 ${c} ${onClick ? "hover:bg-surface-container-low" : "cursor-default"}`}>
      <div className="text-[24px] font-semibold leading-tight">{n}</div><div className="text-[13px] text-on-surface-variant">{t}</div>
    </button>
  );
};
const Filtro = ({ label, children }) => <label className="flex flex-col gap-1"><span className="text-on-surface-variant">{label}</span>{children}</label>;

function Ficha({ p, detalle, fecha, esApi, demo, onCambio, onAviso, onDestacar }) {
  const [resumen, setResumen] = useState(null);
  const [cargando, setCargando] = useState(null);
  const [ajuste, setAjuste] = useState(null);
  const [tipoEv, setTipoEv] = useState("hospitalizacion");
  useEffect(() => { setResumen(null); }, [p.categoria, p.estado_clinico, fecha]);

  const correr = async (nombre, fn) => {
    setCargando(nombre);
    try { await fn(); } catch (e) { onAviso({ titulo: "No se pudo completar: " + e.message }); } finally { setCargando(null); }
  };
  const registrarEvento = (ev, origen) => correr("evento", async () => {
    const r = await api.postEvento({ id_paciente: p.id_paciente, fecha_corte: fecha, fecha_evento: ev.fecha_evento || fecha,
      tipo_evento: ev.tipo_evento, subtipo: ev.subtipo, severidad: ev.severidad, detalle: ev.detalle });
    await onCambio(); onDestacar(p.id_paciente);
    onAviso({ titulo: `${origen}. Lista actualizada`, antes: r.posicion_antes, despues: r.posicion_despues, cat: r.paciente?.categoria });
  });
  const confirmar = () => correr("rev", async () => { await api.postRevision(p.id_paciente, { accion: "confirmar" }); await onCambio(); onAviso({ titulo: "Prioridad confirmada" }); });
  const guardarAjuste = () => correr("rev", async () => {
    await api.postRevision(p.id_paciente, { accion: "ajustar", categoria_ajustada: ajuste.categoria, motivo: ajuste.motivo });
    setAjuste(null); await onCambio(); onAviso({ titulo: "Cambio de prioridad registrado" });
  });
  const pedirResumen = () => correr("ia", async () => setResumen(await api.postExplicar(p.id_paciente, fecha)));

  const timeline = detalle ? [
    ...detalle.eventos_clinicos.map((e) => ({ f: e.fecha_evento, t: `${TIPO_EVENTO[e.tipo_evento] || e.tipo_evento}: ${e.subtipo}`, d: e.detalle?.startsWith("Informe") ? e.detalle : null, rojo: e.severidad === "grave", nuevo: e.id_evento?.startsWith("EV-DEMO") })),
    ...detalle.mediciones.map((m) => ({ f: m.fecha_medicion, t: `${m.tipo_medicion.replace("_", " ")}: ${m.valor} ${m.unidad}`, d: m.fuera_de_rango ? "fuera de rango" : null, ambar: m.fuera_de_rango })),
    ...(detalle.citaciones || []).map((c) => ({ f: c.fecha_cita, t: `Citación ${c.id_box}: ${c.estado_cita.replace("_", " ")}`, ambar: c.estado_cita === "no_asistio" })),
    { f: p.fecha_ingreso_lista, t: "Ingreso de la interconsulta", d: `prioridad inicial ${p.prioridad_inicial}` },
  ].sort((a, b) => b.f.localeCompare(a.f)) : [];

  return (
    <>
      <Caja>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[18px] font-semibold">{p.nombre_fantasia}</div>
            <div className="text-[13px] text-on-surface-variant">{p.edad} años · {p.sexo === "F" ? "Femenino" : "Masculino"} · {p.comuna} · {p.id_paciente}</div>
          </div>
          <Prioridad cat={p.categoria} />
        </div>
        {p.riesgo_vital && <div className="mt-3 p-2.5 rounded bg-error-container text-on-error-container text-[14px] flex gap-2"><Icono n="warning" className="text-[20px]" /><span><b>Contactar hoy.</b> Evaluar derivación a urgencia según criterio médico.</span></div>}
        <dl className="mt-3 grid grid-cols-[130px_1fr] gap-y-1 text-[14px]">
          <dt className="text-on-surface-variant">Especialidad</dt><dd>{p.especialidad}</dd>
          <dt className="text-on-surface-variant">Diagnóstico</dt><dd>{p.diagnostico_cie10} · {p.diagnostico_texto}</dd>
          <dt className="text-on-surface-variant">Ingreso a lista</dt><dd>{fmt(p.fecha_ingreso_lista)} ({p.dias_espera} días)</dd>
          <dt className="text-on-surface-variant">Prioridad inicial</dt><dd className="capitalize">{p.prioridad_inicial}</dd>
          <dt className="text-on-surface-variant">N° en la lista</dt><dd>{p.posicion}</dd>
          <dt className="text-on-surface-variant">Revisión</dt><dd>{p.estado_revision === "pendiente" ? "Pendiente" : p.estado_revision === "ajustado" ? "Ajustada" : "Confirmada"}</dd>
        </dl>
        {p.categoria !== p.categoria_sistema && <p className="mt-2 text-[13px] text-on-surface-variant">El sistema proponía prioridad {p.categoria_sistema}; el equipo clínico la cambió a {p.categoria}. Motivo: {p.revision?.motivo}</p>}
      </Caja>

      <Caja titulo={`Fundamento de la prioridad ${ETIQUETA[p.categoria].toLowerCase()}`}>
        <ul className="space-y-2.5 text-[14px]">
          {p.razones.map((r, i) => (
            <li key={i} className={r.factor === "tabla_oficial" || r.factor === "riesgo_vital" ? "pl-2 border-l-4 border-error" : "pl-2 border-l-4 border-outline-variant"}>
              <div className="text-[12px] text-on-surface-variant">{FACTOR[r.factor] || r.factor}</div>
              <div>{r.valor}</div>
              <div className="text-[12px] text-on-surface-variant italic">Fuente: {r.fuente}</div>
            </li>
          ))}
        </ul>
      </Caja>

      {esApi ? (
        <>
          <Caja titulo="Decisión clínica">
            <div className="flex gap-2">
              <button onClick={confirmar} disabled={cargando} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-50">Confirmar prioridad</button>
              <button onClick={() => setAjuste(ajuste ? null : { categoria: p.categoria, motivo: "" })} className="flex-1 py-2 rounded border border-primary text-primary font-semibold">Cambiar prioridad</button>
            </div>
            {ajuste && (
              <div className="mt-3 flex flex-col gap-2">
                <select value={ajuste.categoria} onChange={(e) => setAjuste({ ...ajuste, categoria: e.target.value })} className="h-9 px-2 border border-outline-variant rounded bg-white">
                  {Object.entries(ETIQUETA).map(([k, v]) => <option key={k} value={k}>Prioridad {v.toLowerCase()}</option>)}
                </select>
                <input placeholder="Motivo clínico (obligatorio)" value={ajuste.motivo} onChange={(e) => setAjuste({ ...ajuste, motivo: e.target.value })} className="h-9 px-2 border border-outline-variant rounded" />
                <button disabled={!ajuste.motivo} onClick={guardarAjuste} className="py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Guardar cambio</button>
              </div>
            )}
          </Caja>

          <Informe p={p} fecha={fecha} cargando={cargando} onConfirmar={(ev) => registrarEvento(ev, "Evento del informe registrado")} onAviso={onAviso} />

          <Caja titulo="Resumen para el equipo" accion={<button onClick={pedirResumen} disabled={cargando} className="text-[13px] text-primary font-semibold disabled:opacity-50">{cargando === "ia" ? "Redactando…" : resumen ? "Actualizar" : "Generar"}</button>}>
            {resumen ? <>
              <p className="text-[14px] leading-relaxed">{resumen.explicacion_ia}</p>
              <p className="text-[12px] text-on-surface-variant mt-2">Texto redactado automáticamente a partir del fundamento ({resumen.fuente === "bedrock" ? "Amazon Bedrock" : "plantilla"}). No modifica la prioridad.</p>
            </> : <p className="text-[13px] text-on-surface-variant">Redacta en lenguaje simple el fundamento de arriba, por ejemplo para contactar al paciente.</p>}
          </Caja>

          {demo && (
            <Caja titulo="Simular evento (demostración)" className="border-ambar/50">
              <div className="flex gap-2">
                <select value={tipoEv} onChange={(e) => setTipoEv(e.target.value)} className="flex-1 h-9 px-2 border border-outline-variant rounded bg-white">
                  {Object.entries(EVENTOS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
                <button onClick={() => registrarEvento(EVENTOS[tipoEv], "Evento simulado")} disabled={cargando} className="px-4 rounded bg-ambar text-white font-semibold disabled:opacity-50">Simular</button>
              </div>
            </Caja>
          )}
        </>
      ) : <Caja><p className="text-on-surface-variant text-[13px]">Sin conexión al servidor: se muestra la lista precalculada. Registrar informes y decisiones requiere la API.</p></Caja>}

      <Caja titulo="Historia mientras espera">
        <ol className="text-[14px]">
          {timeline.map((x, i) => (
            <li key={i} className={`grid grid-cols-[88px_1fr] gap-2 py-1.5 border-b border-outline-variant/50 ${x.nuevo ? "bg-ambar-container/50" : ""}`}>
              <span className="text-on-surface-variant text-[13px]">{fmt(x.f)}</span>
              <span className={x.rojo ? "text-error font-semibold" : x.ambar ? "text-ambar" : ""}>{x.t}{x.d && <span className="text-on-surface-variant font-normal"> · {x.d}</span>}</span>
            </li>
          ))}
          {!detalle && <li className="text-on-surface-variant">Cargando…</li>}
        </ol>
      </Caja>
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
    catch (e) { onAviso({ titulo: "No se pudo leer el informe: " + e.message }); }
    finally { setLeyendo(false); }
  };
  const foto = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (f) analizar({ imagen_base64: await fotoABase64(f), media_type: "image/jpeg" });
  };
  const ev = res?.evento;
  return (
    <Caja titulo="Registrar informe recibido">
      <p className="text-[13px] text-on-surface-variant mb-2">Epicrisis, DAU de urgencia o nota clínica. Se propone el evento y usted confirma antes de actualizar la lista.</p>
      <textarea rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Ej.: Consulta en urgencia por dolor torácico en reposo. Se hospitaliza en cardiología."
        className="w-full p-2 border border-outline-variant rounded focus:outline-none focus:border-primary resize-y text-[14px]" />
      <div className="flex gap-2 mt-2">
        <button disabled={!texto.trim() || leyendo} onClick={() => analizar({ texto })} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{leyendo ? "Leyendo…" : "Revisar informe"}</button>
        <button disabled={leyendo} onClick={() => archivo.current.click()} className="flex-1 py-2 rounded border border-outline-variant font-semibold flex items-center justify-center gap-1"><Icono n="photo_camera" className="text-[18px]" />Foto del documento</button>
        <input ref={archivo} type="file" accept="image/*" capture="environment" hidden onChange={foto} />
      </div>
      {res && !ev && <p className="mt-2 text-[13px] text-on-surface-variant">{res.mensaje}</p>}
      {res?.transcripcion && <details className="mt-2 text-[13px]"><summary className="cursor-pointer text-on-surface-variant">Texto leído del documento</summary><p className="whitespace-pre-wrap mt-1">{res.transcripcion}</p></details>}
      {ev && (
        <div className="mt-3 border border-outline-variant rounded p-3 space-y-2 text-[14px]">
          <div><span className="text-on-surface-variant">Evento:</span> <b>{TIPO_EVENTO[ev.tipo_evento]}</b> · {ev.subtipo} · {fmt(ev.fecha_evento)}</div>
          <blockquote className="border-l-4 border-ambar bg-ambar-container/40 px-2 py-1 italic">“{ev.evidencia}”</blockquote>
          <div className="flex items-center gap-2"><span className="text-on-surface-variant">Prioridad:</span><Prioridad cat={res.categoria_actual} /><span>→</span><Prioridad cat={res.categoria_propuesta} /></div>
          {res.razones_propuestas?.map((r, i) => <div key={i} className="text-[13px] text-on-surface-variant">{r.valor} · {r.fuente}</div>)}
          <div className="flex gap-2 pt-1">
            <button disabled={cargando} onClick={async () => { await onConfirmar({ ...ev, detalle: `Informe: ${ev.evidencia}` }); setRes(null); setTexto(""); }}
              className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-50">Confirmar y actualizar lista</button>
            <button onClick={() => setRes(null)} className="flex-1 py-2 rounded border border-outline-variant font-semibold">Descartar</button>
          </div>
          <p className="text-[12px] text-on-surface-variant">Lectura {res.fuente === "bedrock" ? "automática (Amazon Bedrock)" : "por palabras clave"}; verifique antes de confirmar.</p>
        </div>
      )}
    </Caja>
  );
}

function Hoy({ vitales, fecha, esp, setEsp, onVer, esApi }) {
  const [b, setB] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    if (!esApi) return setErr("La agenda de box requiere conexión al servidor.");
    setB(null);
    api.getBoxes(fecha, esp === "Todas" ? null : esp).then(setB).catch((e) => setErr(e.message));
  }, [fecha, esp, esApi]);

  return (
    <div className="grid gap-5 lg:grid-cols-12 items-start">
      <Caja titulo={`Contactar hoy (${vitales.length})`} className="lg:col-span-4 border-l-4 border-l-error">
        <p className="text-[13px] text-on-surface-variant mb-3">Descompensación grave después de la interconsulta, sin estabilización posterior, en un diagnóstico de prioridad alta según la tabla del HLF. No esperar cupo: contactar y evaluar derivación a urgencia según criterio médico.</p>
        {vitales.length === 0 && <p className="text-on-surface-variant">Sin pacientes en esta condición.</p>}
        <ul className="divide-y divide-outline-variant/60">
          {vitales.map((p) => (
            <li key={p.id_paciente}>
              <button onClick={() => onVer(p.id_paciente)} className="w-full text-left py-2 hover:bg-surface-container-low">
                <div className="font-semibold">{p.nombre_fantasia} <span className="font-normal text-on-surface-variant text-[13px]">· {p.edad} años · N° {p.posicion}</span></div>
                <div className="text-[13px] text-on-surface-variant">{p.especialidad} · {p.diagnostico_texto}</div>
              </button>
            </li>
          ))}
        </ul>
      </Caja>

      <div className="lg:col-span-8 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-[17px] font-semibold">Agenda de box{b?.dia_agenda && ` · ${fmt(b.dia_agenda)}`}</h2>
          <select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-white text-[14px]">{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select>
        </div>
        {err && <Caja><p className="text-on-surface-variant">{err}</p></Caja>}
        {!err && !b && <p className="text-on-surface-variant">Cargando agenda…</p>}
        {b?.especialidades.map((e) => (
          <Caja key={e.especialidad} titulo={e.especialidad} accion={<span className="text-[13px] text-on-surface-variant">Inasistencia histórica {e.inasistencia_pct ?? "—"}%</span>}>
            {e.asignaciones.length === 0 && <p className="text-on-surface-variant text-[14px]">Sin box asignado a esta especialidad.</p>}
            {e.asignaciones.map((a) => (
              <div key={a.id_box} className="mb-3">
                <div className="text-[14px] font-semibold mb-1">{a.id_box} · {a.bloque} · {a.libres} cupo{a.libres !== 1 ? "s" : ""} disponible{a.libres !== 1 ? "s" : ""}</div>
                <table className="w-full text-[14px]">
                  <tbody>
                    {a.pacientes.map((p, i) => (
                      <tr key={p.id_paciente} onClick={() => onVer(p.id_paciente)} className={`cursor-pointer border-t border-outline-variant/60 hover:bg-surface-container-low ${p.riesgo_vital ? "bg-error-container/40" : ""}`}>
                        <td className="py-2 pr-2 align-top w-6 text-on-surface-variant">{i + 1}</td>
                        <td className="py-2 pr-2 align-top w-20"><Prioridad cat={p.categoria} /></td>
                        <td className="py-2 align-top">
                          <div className="font-semibold">{p.nombre_fantasia} <span className="font-normal text-[13px] text-on-surface-variant">· {p.diagnostico_texto} · {p.dias_espera} días</span></div>
                          <div className="text-[13px]">{p.motivo}</div>
                          <div className={`text-[13px] font-semibold ${p.riesgo_vital ? "text-error" : p.riesgo_inasistencia ? "text-ambar" : "text-primary"}`}>Acción: {p.accion}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
            {e.alternativa && (
              <div onClick={() => onVer(e.alternativa.id_paciente)} className="cursor-pointer border border-dashed border-outline rounded p-2 text-[14px] hover:bg-surface-container-low">
                <div className="text-[13px] text-on-surface-variant">Siguiente en la lista, si un paciente no confirma:</div>
                <div className="font-semibold">{e.alternativa.nombre_fantasia} <span className="font-normal text-[13px] text-on-surface-variant">· prioridad {e.alternativa.categoria} · N° {e.alternativa.posicion}</span></div>
                <div className="text-[13px]">Va después porque: {e.alternativa.por_que_despues}</div>
              </div>
            )}
          </Caja>
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
    <div className="grid gap-5 lg:grid-cols-2 text-[14px] leading-relaxed">
      <Caja titulo="Cómo se ordena la lista">
        <ol className="list-decimal pl-5 space-y-2">
          <li><b>Prioridad (alta, media, baja).</b> Se parte de la prioridad asignada por el especialista al revisar la interconsulta. Si después el paciente presenta una descompensación (urgencia, hospitalización o evento grave) que no estaba en la interconsulta, la prioridad sube a la que indica la <i>Tabla de priorización SSMSO 2025, Hospital Dra. Eloísa Díaz</i> (págs. 84–111) para ese diagnóstico descompensado. El sistema nunca baja una prioridad por sí solo.</li>
          <li><b>Contactar hoy.</b> Descompensación grave sin estabilización posterior en un diagnóstico de prioridad alta. Corresponde al criterio de criticidad / riesgo vital de MINSAL (SSMSO 2025, pág. 4).</li>
          <li><b>Orden dentro de cada prioridad</b> (MINSAL, Ord. 536 del 21-03-2025): criterio médico, grupos de especial protección (sin datos en este registro), antigüedad en lista mayor a 1 año y, finalmente, fecha de ingreso.</li>
          <li><b>Observaciones</b> que no cambian el orden: garantía GES vencida; 2 inasistencias consecutivas (posible causal de egreso 8); última medición fuera de rango.</li>
          <li><b>Egreso por fallecimiento</b> (causal 9, Manual de Gestión de la Demanda SSMSO).</li>
        </ol>
      </Caja>
      <Caja titulo="Tabla HLF usada para pacientes descompensados">
        <table className="w-full text-[14px]">
          <thead><tr className="text-left text-on-surface-variant text-[13px] border-b border-outline-variant"><th className="py-1">CIE-10</th><th>Fila de la tabla</th><th>Prioridad</th><th>Pág.</th></tr></thead>
          <tbody>{filas.map(([c, f, pr, pg]) => <tr key={c} className="border-b border-outline-variant/50"><td className="py-1 font-semibold">{c}</td><td>{f}</td><td>{pr}</td><td>{pg}</td></tr>)}</tbody>
        </table>
        <p className="text-[13px] text-on-surface-variant mt-2">I10, K21, F32, F41, G43, E66, M17, M54 y M75 no tienen fila de "descompensado" en la tabla del HLF: mantienen su prioridad y el evento queda visible para revisión clínica.</p>
      </Caja>
      <Caja titulo="Garantías GES · atención por especialista">
        <p>Depresión (N°34): 30 días · Hipertensión (N°21): 45 · EPOC (N°38): 45 · Diabetes tipo 2 (N°7): 60 · Asma (N°61): 60 · Epilepsia (N°60): 60 · Artrosis de rodilla, 55 años o más (N°41): 120.</p>
      </Caja>
      <Caja titulo="Lectura automática de informes">
        <p>Los informes escritos o fotografiados se leen automáticamente (Amazon Bedrock) solo para proponer el evento, citando la frase del documento. Ninguna prioridad cambia sin confirmación del equipo clínico. No se hacen predicciones: las alertas se basan en eventos ya registrados.</p>
      </Caja>
    </div>
  );
}
