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
  lace: "Puntaje de riesgo LACE",
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
  const [nuevo, setNuevo] = useState(false);
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
  // al seleccionar (p. ej. un paciente recién ingresado) saltar a la página donde está
  useEffect(() => {
    const i = filtrados.findIndex((p) => p.id_paciente === sel);
    if (i >= 0) setPagina(Math.floor(i / POR_PAGINA));
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtrados = useMemo(() => {
    if (!data) return [];
    const q = busca.trim().toLowerCase();
    return data.pacientes.filter((p) =>
      (filtroCat === "todas" || (filtroCat === "vital" ? p.contactar_hoy : filtroCat === "revisar" ? p.revision_sugerida?.length > 0 : p.categoria === filtroCat)) &&
      (!soloPend || p.estado_revision === "pendiente" || p.estado_revision === "requiere_revision") &&
      (!q || p.nombre_fantasia.toLowerCase().includes(q) || p.id_paciente.toLowerCase().includes(q) || p.diagnostico_texto.toLowerCase().includes(q)));
  }, [data, busca, filtroCat, soloPend]);

  const mostrarAviso = (a) => { setAviso(a); setTimeout(() => setAviso(null), 6000); };
  const abrir = (id) => { setSel(id); setVista("lista"); };

  if (!data) return <div className="p-10 text-lg">{error ? `No se pudo cargar la lista: ${error}` : "Cargando lista de espera…"}</div>;
  const paciente = sel && data.pacientes.find((p) => p.id_paciente === sel);
  const vitales = data.pacientes.filter((p) => p.riesgo_vital);
  const porContactar = vitales.filter((p) => p.contactar_hoy);
  const altas = data.pacientes.filter((p) => p.categoria === "alta").length;
  const gesVenc = data.pacientes.filter((p) => p.ges?.vencida).length;
  const pendientes = data.pacientes.filter((p) => p.revision_sugerida?.length > 0).length;
  const pag = filtrados.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA);
  const paginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-surface-container-lowest border-b border-outline-variant">
        <div className="flex h-1.5"><div className="w-1/3 bg-primary" /><div className="w-2/3 bg-gob-rojo" /></div>
        <div className="max-w-[1400px] mx-auto px-6 h-[72px] flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Logo />
            <div className="leading-tight border-l border-outline-variant pl-3">
              <div className="text-[16px] font-bold text-primary-container">Hospital Clínico Dra. Eloísa Díaz Inzunza</div>
              <div className="text-[13px] text-on-surface-variant">La Florida · Servicio de Salud Metropolitano Sur Oriente</div>
              <div className="text-[13px] font-semibold text-hlf">Lista de espera dinámica · Consultas de especialidad</div>
            </div>
          </div>
          <div className="flex items-center gap-3 text-[13px]">
            <span className="text-on-surface-variant">Lista al <b className="text-on-surface">{fmt(fecha)}</b></span>
            <label className="flex items-center gap-1.5 text-on-surface-variant cursor-pointer select-none border-l border-outline-variant pl-3">
              <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} className="accent-[#0f69b4]" />Modo demostración
            </label>
          </div>
        </div>
        <nav className="max-w-[1400px] mx-auto px-6 flex gap-6 text-[14px]">
          {[["hoy", "Hoy", porContactar.length], ["medico", "Tengo horas libres", null], ["lista", "Lista de espera", null], ["indicadores", "Indicadores", null], ["cargar", "Cargar datos", null], ["criterios", "Criterios", null]].map(([k, t, n]) => (
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
          <Indicador n={porContactar.length} t={`Contactar hoy (de ${vitales.length} con riesgo vital)`} tono={porContactar.length ? "rojo" : null} onClick={() => setVista("hoy")} />
          <Indicador n={altas} t="Prioridad alta" />
          <Indicador n={pendientes} t="Requieren revisión del especialista" tono={pendientes ? "ambar" : null} onClick={() => { setVista("lista"); setFiltroCat("revisar"); setSoloPend(false); }} />
          <Indicador n={gesVenc} t="Garantías GES vencidas" />
        </div>

        {vista === "hoy" && <Hoy vitales={vitales} todosPacientes={data.pacientes} fecha={fecha} esp={esp} setEsp={setEsp} onVer={abrir} esApi={esApi} onCambio={cargar} onAviso={mostrarAviso} />}
        {vista === "criterios" && <Criterios />}
        {vista === "medico" && <MedicoDisponible fecha={fecha} esApi={esApi} espInicial={esp} onVer={abrir} onCambio={cargar} onAviso={mostrarAviso} />}
        {vista === "indicadores" && <Indicadores fecha={fecha} esApi={esApi} data={data} />}
        {vista === "cargar" && <CargarDatos esApi={esApi} onListo={async (r) => {
          await cargar();
          mostrarAviso({ titulo: `Datos cargados: ${r.resumen.pacientes_nuevos} pacientes nuevos, ${r.resumen.pacientes_actualizados} actualizados, ${r.resumen.eventos} eventos` });
        }} />}
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
                    <option value="todas">Todas</option><option value="vital">Contactar hoy</option><option value="revisar">Requieren revisión</option><option value="alta">Alta</option><option value="media">Media</option><option value="baja">Baja</option>
                  </select>
                </Filtro>
                <label className="flex items-center gap-2 h-9 cursor-pointer select-none"><input type="checkbox" checked={soloPend} onChange={(e) => setSoloPend(e.target.checked)} className="w-4 h-4 accent-[#0f69b4]" />Solo pendientes de revisión</label>
                <button onClick={() => exportarCsv(filtrados, fecha)} className="ml-auto h-9 px-3 rounded border border-outline-variant bg-white font-semibold flex items-center gap-1"><Icono n="download" className="text-[18px]" />Descargar Excel</button>
                {esApi && <button onClick={() => setNuevo(true)} className="h-9 px-3 rounded bg-primary text-on-primary font-semibold flex items-center gap-1"><Icono n="person_add" className="text-[18px]" />Ingresar paciente</button>}
              </div>
              {nuevo && <NuevoPaciente fecha={fecha} onCerrar={() => setNuevo(false)} onListo={async (r) => {
                setNuevo(false); setBusca(""); setFiltroCat("todas"); setSoloPend(false); await cargar(); setSel(r.id_paciente);
                mostrarAviso({ titulo: `${r.paciente?.nombre_fantasia} ingresado a la lista`, despues: r.paciente?.posicion, antes: "—", cat: r.paciente?.categoria });
              }} />}

              <section className="bg-surface-container-lowest border border-outline-variant rounded overflow-hidden">
                <table className="w-full text-left border-collapse text-[14px]">
                  <thead>
                    <tr className="bg-surface-container-low text-[13px] text-on-surface-variant border-b border-outline-variant">
                      <th className="py-2 px-3 font-semibold w-16">N°</th><th className="py-2 px-2 font-semibold">Prioridad</th>
                      <th className="py-2 px-3 font-semibold">Paciente / diagnóstico</th><th className="py-2 px-2 font-semibold">Observaciones</th>
                      <th className="py-2 px-2 font-semibold text-center" title="Índice LACE (van Walraven 2010)">LACE</th>
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
                                {p.contactar_hoy && <Marca tono="rojo">Contactar hoy</Marca>}
                                {p.contacto?.resultado === "citado" && p.contacto?.hora && p.contacto.fecha_corte === fecha
                                  ? <Marca tono="azul" title={p.contacto.texto}>Citado {p.contacto.hora}</Marca>
                                  : p.riesgo_vital && !p.contactar_hoy && <Marca tono="azul" title={p.contacto?.texto}>Contactado</Marca>}
                                {!p.riesgo_vital && p.estado_clinico === "descompensado" && <Marca tono="rojo">Descompensado</Marca>}
                                {p.revision_sugerida?.length > 0 && <Marca tono="ambar" title={[...new Set(p.revision_sugerida.map((s) => s.motivo))].join(" · ")}>Revisar</Marca>}
                                {p.grupo_proteccion && <Marca tono="azul">{p.grupo_proteccion}</Marca>}
                                {p.estado_clinico === "estabilizado" && <Marca>Estabilizado</Marca>}
                                {p.ges?.vencida && <Marca tono="azul" title={`GES N°${p.ges.problema}: plazo ${p.ges.plazo_dias} días`}>GES vencida</Marca>}
                                {p.riesgo_inasistencia && <Marca tono="ambar" title="2 inasistencias consecutivas (causal 8)">2 inasistencias</Marca>}
                              </div>
                            </td>
                            <td className="py-2.5 px-2 align-top text-center">
                              <span className={`inline-block min-w-[28px] px-1.5 py-px rounded font-semibold ${p.lace?.total ? "bg-primary/10 text-primary-container" : "text-on-surface-variant"}`}>{p.lace?.total ?? "—"}</span>
                            </td>
                            <td className="py-2.5 px-3 align-top text-right whitespace-nowrap">{p.dias_espera} días{p.antiguedad_mayor_1_anio && <div className="text-[12px] text-on-surface-variant">más de 1 año</div>}</td>
                            <td className="py-2.5 px-3 align-top text-[13px] whitespace-nowrap">
                              {p.estado_revision === "pendiente" ? <span className="text-on-surface-variant">Pendiente</span>
                                : p.estado_revision === "requiere_revision" ? <span className="text-ambar font-semibold" title={p.revision_vencida_por}><Icono n="update" className="text-[16px]" /> Revisar de nuevo</span>
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
                  <span>{filtrados.length} pacientes · orden: prioridad, contactar hoy, puntaje LACE, más de 1 año en espera, fecha de ingreso</span>
                  <div className="flex items-center gap-2">
                    <button disabled={pagina === 0} onClick={() => setPagina(pagina - 1)} className="px-2 py-1 border border-outline-variant rounded bg-white disabled:opacity-40">Anterior</button>
                    <span>{pagina + 1} / {paginas}</span>
                    <button disabled={pagina >= paginas - 1} onClick={() => setPagina(pagina + 1)} className="px-2 py-1 border border-outline-variant rounded bg-white disabled:opacity-40">Siguiente</button>
                  </div>
                </div>
              </section>

              {data.excluidos.length > 0 && (
                <details className="bg-surface-container-lowest border border-outline-variant rounded">
                  <summary className="px-4 py-2.5 cursor-pointer text-[14px] font-semibold">
                    Egresados de la lista ({data.excluidos.length}): {data.excluidos.filter((e) => e.motivo === "fallecido").length} por fallecimiento · {data.excluidos.filter((e) => e.motivo === "atendido").length} atendidos
                  </summary>
                  <ul className="px-4 pb-3 text-[13px] text-on-surface-variant">
                    {[...data.excluidos].sort((a, b) => (b.fecha || "").localeCompare(a.fecha || "")).map((e) => (
                      <li key={e.id_paciente} className="py-1 border-t border-outline-variant/60 flex justify-between gap-2">
                        <span>{e.nombre_fantasia || e.id_paciente} · {e.especialidad}</span>
                        <span>{e.motivo === "fallecido" ? `Fallecimiento ${fmt(e.fecha)} · causal 9` : `Atendido en consulta nueva ${fmt(e.fecha)}`}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>

            <aside className="lg:col-span-5 xl:col-span-4 lg:sticky lg:top-4 flex flex-col gap-3 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
              {!paciente ? <Caja><p className="text-on-surface-variant">Seleccione un paciente para ver el detalle.</p></Caja> : (
                <Ficha key={paciente.id_paciente} p={paciente} total={data.total} detalle={detalle} fecha={fecha} esApi={esApi} demo={demo} onCambio={cargar} onAviso={mostrarAviso}
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

// Logo oficial del hospital: poner el archivo en front/public/logo-hlf.png. Si no está, se muestra el ícono.
function Logo() {
  const [ok, setOk] = useState(true);
  return ok
    ? <img src="/logo-hlf.png" alt="Hospital Clínico Dra. Eloísa Díaz Inzunza" className="h-14 w-auto object-contain" onError={() => setOk(false)} />
    : <div className="w-9 h-9 rounded bg-primary text-on-primary flex items-center justify-center"><Icono n="local_hospital" className="text-[22px]" /></div>;
}

// Novedades que registra el equipo: comorbilidad (pondera en Charlson/LACE), cambio de diagnóstico y egresos.
function Novedad({ p, fecha, onListo, onAviso }) {
  const [tipo, setTipo] = useState(null);
  const [cat, setCat] = useState(null);
  const [v, setV] = useState({ condicion: "", cie10: "", fecha });
  const [confirma, setConfirma] = useState(false);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => { if (tipo && !cat) api.getCatalogo().then(setCat).catch((e) => onAviso({ titulo: e.message })); }, [tipo]); // eslint-disable-line react-hooks/exhaustive-deps
  const abrir = (t) => { setTipo(tipo === t ? null : t); setV({ condicion: "", cie10: "", fecha }); setConfirma(false); };
  const enviar = async () => {
    setEnviando(true);
    try {
      const body = { tipo, fecha_corte: fecha, fecha: v.fecha };
      if (tipo === "comorbilidad") Object.assign(body, v.condicion.startsWith("cie:") ? { cie10: v.condicion.slice(4) } : { condicion: v.condicion });
      if (tipo === "diagnostico") body.cie10 = v.cie10;
      if (tipo === "riesgo") Object.assign(body, { grupo_proteccion: (v.grupo ?? p.grupo_proteccion) || null, acg: (v.acg ?? p.acg) || null });
      const r = await api.postNovedad(p.id_paciente, body);
      setTipo(null); onListo(r);
    } catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(false); }
  };
  const peso = cat?.charlson.find((c) => c.condicion === v.condicion)?.peso;
  const campo = "h-9 px-2 border border-outline-variant rounded bg-white w-full";
  const btn = (t, icono, texto, rojo) => (
    <button onClick={() => abrir(t)} className={`flex-1 min-w-[120px] py-2 rounded border font-semibold text-[13px] flex items-center justify-center gap-1 ${tipo === t ? (rojo ? "bg-error text-on-error border-error" : "bg-primary text-on-primary border-primary") : "border-outline-variant hover:bg-surface-container-low"}`}>
      <Icono n={icono} className="text-[18px]" />{texto}
    </button>
  );
  return (
    <Caja titulo="Registrar novedad del paciente">
      {p.comorbilidades?.length > 0 && <p className="text-[13px] mb-2">Comorbilidades registradas: {p.comorbilidades.map((c) => c.nombre).join(", ")}</p>}
      <div className="flex flex-wrap gap-2">
        {btn("comorbilidad", "add_circle", "Condición / comorbilidad")}
        {btn("diagnostico", "edit_note", "Cambiar diagnóstico")}
        {btn("riesgo", "shield_person", "Grupo protección / ACG")}
        {btn("atendido", "how_to_reg", "Atendido")}
        {btn("fallecimiento", "heart_minus", "Fallecimiento", true)}
      </div>

      {tipo === "comorbilidad" && (
        <div className="mt-3 space-y-2 text-[14px]">
          <select value={v.condicion} onChange={(e) => setV({ ...v, condicion: e.target.value })} className={campo}>
            <option value="">Seleccione la condición…</option>
            <optgroup label="Condiciones de Charlson (suman al LACE)">
              {cat?.charlson.map((c) => <option key={c.condicion} value={c.condicion}>{c.condicion} · peso {c.peso}</option>)}
            </optgroup>
            <optgroup label="Otros diagnósticos (se registran, no suman en Charlson)">
              {cat?.diagnosticos.filter((d) => !["I50", "J44", "J45", "K70", "E11"].includes(d.diagnostico_cie10)).map((d) =>
                <option key={d.diagnostico_cie10} value={`cie:${d.diagnostico_cie10}`}>{d.diagnostico_cie10} · {d.diagnostico_texto}</option>)}
            </optgroup>
          </select>
          {v.condicion && <p className={`text-[13px] ${peso ? "text-primary-container font-semibold" : "text-on-surface-variant"}`}>
            {peso ? `Suma ${peso} al índice de Charlson (van Walraven 2010). El puntaje LACE se recalcula.` : "Queda registrada en la ficha; no tiene peso en el índice de Charlson, no cambia el puntaje."}</p>}
          <button disabled={!v.condicion || enviando} onClick={enviar} className="w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Registrar y recalcular</button>
        </div>
      )}

      {tipo === "diagnostico" && (
        <div className="mt-3 space-y-2 text-[14px]">
          <select value={v.cie10} onChange={(e) => setV({ ...v, cie10: e.target.value })} className={campo}>
            <option value="">Nuevo diagnóstico de la interconsulta…</option>
            {cat?.diagnosticos.map((d) => <option key={d.diagnostico_cie10} value={d.diagnostico_cie10}>{d.especialidad} · {d.diagnostico_cie10} {d.diagnostico_texto}</option>)}
          </select>
          <p className="text-[13px] text-on-surface-variant">Se vuelve a aplicar la tabla del HLF, el puntaje LACE y la garantía GES del nuevo diagnóstico. Si cambia la especialidad, el paciente pasa a esa lista.</p>
          <button disabled={!v.cie10 || enviando} onClick={enviar} className="w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Cambiar y recalcular</button>
        </div>
      )}

      {tipo === "riesgo" && (
        <div className="mt-3 space-y-2 text-[14px]">
          <Filtro label="Grupo de especial protección (MINSAL, criterio 2 de orden)">
            <select value={v.grupo ?? p.grupo_proteccion ?? ""} onChange={(e) => setV({ ...v, grupo: e.target.value })} className={campo}>
              <option value="">Ninguno</option>{cat?.grupos_proteccion.map((g) => <option key={g}>{g}</option>)}
            </select>
          </Filtro>
          <Filtro label="Estratificación de riesgo ACG (ficha Rayen)">
            <select value={v.acg ?? p.acg ?? ""} onChange={(e) => setV({ ...v, acg: e.target.value })} className={campo}>
              <option value="">Sin dato</option>{cat?.acg.map((a) => <option key={a.nivel} value={a.nivel}>{a.nivel} · {a.texto}</option>)}
            </select>
          </Filtro>
          <p className="text-[13px] text-on-surface-variant">El grupo de protección ordena dentro de la misma prioridad (MINSAL Ord. 536/2025). El ACG se muestra como dato de riesgo del SSMSO.</p>
          <button disabled={enviando} onClick={enviar} className="w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Guardar y recalcular</button>
        </div>
      )}

      {(tipo === "fallecimiento" || tipo === "atendido") && (
        <div className="mt-3 space-y-2 text-[14px]">
          <Filtro label={tipo === "fallecimiento" ? "Fecha de defunción" : "Fecha de la consulta nueva de especialidad"}>
            <input type="date" value={v.fecha} max={fecha} onChange={(e) => setV({ ...v, fecha: e.target.value })} className={campo} />
          </Filtro>
          <p className="text-[13px] text-on-surface-variant">{tipo === "fallecimiento"
            ? "Egreso por causal 9 (fallecimiento, Manual SSMSO). El paciente sale de la lista y no recibe nuevas citaciones."
            : "La lista se resuelve cuando el especialista atiende la consulta nueva (CNE). El paciente sale de la lista."}</p>
          <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={confirma} onChange={(e) => setConfirma(e.target.checked)} />
            Confirmo que {p.nombre_fantasia} {tipo === "fallecimiento" ? "falleció" : "fue atendido(a)"} (verificado en {tipo === "fallecimiento" ? "Registro Civil / ficha" : "la ficha clínica"}).</label>
          <button disabled={!confirma || !v.fecha || enviando} onClick={enviar} className={`w-full py-2 rounded font-semibold disabled:opacity-40 ${tipo === "fallecimiento" ? "bg-error text-on-error" : "bg-primary text-on-primary"}`}>
            {tipo === "fallecimiento" ? "Registrar fallecimiento y egresar" : "Registrar atención y egresar"}</button>
        </div>
      )}
    </Caja>
  );
}

// Exporta la lista priorizada (con los filtros actuales) a CSV separado por ";" con BOM: Excel en español lo abre en columnas.
function exportarCsv(pacientes, fecha) {
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

const leerBase64 = (f) => new Promise((ok, mal) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result).split(",")[1]);
  r.onerror = () => mal(new Error(`No se pudo leer ${f.name}`));
  r.readAsDataURL(f);
});

const TABLAS_IMPORT = [
  ["pacientes", "Pacientes", "id_paciente, edad, sexo"],
  ["lista_espera", "Lista de espera", "id_paciente, diagnostico_cie10, prioridad_inicial, fecha_ingreso_lista"],
  ["eventos_clinicos", "Eventos clínicos", "id_paciente, fecha_evento, tipo_evento"],
  ["mediciones", "Mediciones", "id_paciente, fecha_medicion, tipo_medicion, valor"],
  ["citaciones", "Citaciones", "id_paciente, fecha_cita, estado_cita"],
  ["agenda_box", "Agenda de box", "id_box, fecha, especialidad, capacidad_cupos"],
];

function CargarDatos({ esApi, onListo }) {
  const [archivos, setArchivos] = useState([]);
  const [rev, setRev] = useState(null);
  const [estado, setEstado] = useState(null);
  const [error, setError] = useState(null);
  const [arrastrando, setArrastrando] = useState(false);
  const input = useRef(null);

  const agregar = (lista) => {
    const nuevos = [...lista].filter((f) => /\.(xlsx|xlsm|csv|txt)$/i.test(f.name));
    if (nuevos.length < lista.length) setError("Solo se aceptan archivos .xlsx o .csv (en Excel: Guardar como → Libro de Excel o CSV).");
    else setError(null);
    setArchivos((a) => [...a.filter((x) => !nuevos.some((n) => n.name === x.name)), ...nuevos]);
    setRev(null);
  };
  const enviar = async (confirmar) => {
    setEstado(confirmar ? "cargando" : "revisando"); setError(null);
    try {
      const datos = await Promise.all(archivos.map(async (f) => ({ nombre: f.name, contenido_base64: await leerBase64(f) })));
      const r = await api.postImportar(datos, confirmar);
      setRev(r);
      if (confirmar) { setArchivos([]); onListo(r); }
    } catch (e) { setError(e.message); } finally { setEstado(null); }
  };
  if (!esApi) return <Caja><p className="text-on-surface-variant">Cargar datos requiere conexión al servidor.</p></Caja>;
  const validas = rev?.informe.reduce((s, i) => s + (i.validas || 0), 0) || 0;

  return (
    <div className="grid gap-5 lg:grid-cols-12 items-start">
      <div className="lg:col-span-8 flex flex-col gap-4">
        <Caja titulo="Cargar planillas del hospital">
          <div onDragOver={(e) => { e.preventDefault(); setArrastrando(true); }} onDragLeave={() => setArrastrando(false)}
            onDrop={(e) => { e.preventDefault(); setArrastrando(false); agregar(e.dataTransfer.files); }}
            onClick={() => input.current.click()}
            className={`cursor-pointer rounded border-2 border-dashed p-8 text-center ${arrastrando ? "border-primary bg-primary/5" : "border-outline-variant hover:bg-surface-container-low"}`}>
            <Icono n="upload_file" className="text-[40px] text-primary" />
            <p className="font-semibold mt-1">Arrastre aquí archivos Excel (.xlsx) o CSV, o haga clic para elegirlos</p>
            <p className="text-[13px] text-on-surface-variant">Puede subir varios a la vez. Cada hoja de un Excel se lee como una tabla distinta.</p>
            <input ref={input} type="file" multiple accept=".xlsx,.xlsm,.csv,.txt" hidden onChange={(e) => { agregar(e.target.files); e.target.value = ""; }} />
          </div>
          {archivos.length > 0 && (
            <ul className="mt-3 divide-y divide-outline-variant/60 text-[14px]">
              {archivos.map((f) => (
                <li key={f.name} className="py-1.5 flex items-center justify-between">
                  <span className="flex items-center gap-2"><Icono n={f.name.toLowerCase().endsWith("csv") ? "description" : "table_view"} className="text-[18px] text-hlf" />{f.name}<span className="text-[12px] text-on-surface-variant">{Math.round(f.size / 1024)} KB</span></span>
                  <button onClick={() => { setArchivos(archivos.filter((x) => x !== f)); setRev(null); }} className="text-on-surface-variant"><Icono n="close" className="text-[18px]" /></button>
                </li>
              ))}
            </ul>
          )}
          {error && <p className="mt-2 text-error text-[14px]">{error}</p>}
          <div className="flex gap-2 mt-3">
            <button disabled={!archivos.length || estado} onClick={() => enviar(false)} className="flex-1 py-2 rounded border border-primary text-primary font-semibold disabled:opacity-40">{estado === "revisando" ? "Revisando…" : "1. Revisar archivos"}</button>
            <button disabled={!rev || rev.cargado || !validas || estado} onClick={() => enviar(true)} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{estado === "cargando" ? "Cargando…" : "2. Cargar al sistema"}</button>
          </div>
          <p className="text-[12px] text-on-surface-variant mt-2">Nada se guarda hasta el paso 2. Los pacientes que ya existen se actualizan y los eventos repetidos no se duplican.</p>
        </Caja>

        {rev && (
          <Caja titulo={rev.cargado ? "Carga completada" : "Revisión de los archivos"}>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-4 text-center">
              {[["pacientes_nuevos", "Pacientes nuevos"], ["pacientes_actualizados", "Actualizados"], ["eventos", "Eventos"],
                ["mediciones", "Mediciones"], ["citaciones", "Citaciones"], ["bloques_agenda", "Bloques de box"]].map(([k, t]) => (
                <div key={k} className="rounded bg-surface-container-low p-2"><div className="text-[20px] font-semibold text-primary-container">{rev.resumen[k]}</div><div className="text-[12px] text-on-surface-variant">{t}</div></div>
              ))}
            </div>
            {rev.avisos.length > 0 && <div className="mb-3 rounded bg-ambar-container/50 p-2 text-[13px]">{rev.avisos.map((a, i) => <div key={i}>⚠ {a}</div>)}</div>}
            <div className="space-y-3">
              {rev.informe.map((i, k) => (
                <div key={k} className="rounded border border-outline-variant p-3 text-[14px]">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold">{i.archivo}{i.hoja && i.hoja !== "hoja" ? ` · hoja "${i.hoja}"` : ""}</span>
                    {i.tabla ? <span className="rounded bg-hlf-claro text-hlf px-2 py-0.5 text-[13px] font-semibold">Detectado: {i.nombre_tabla}</span>
                      : <span className="rounded bg-error-container text-on-error-container px-2 py-0.5 text-[13px] font-semibold">No reconocido</span>}
                  </div>
                  {i.error && <p className="text-error text-[13px] mt-1">{i.error}</p>}
                  {i.tabla && <>
                    <div className="mt-1 flex items-center gap-2">
                      <div className="flex-1 h-2 rounded bg-error-container overflow-hidden"><div className="h-full bg-hlf" style={{ width: `${i.filas ? (i.validas / i.filas) * 100 : 0}%` }} /></div>
                      <span className="text-[13px] whitespace-nowrap"><b>{i.validas}</b> de {i.filas} filas correctas</span>
                    </div>
                    <details className="mt-2"><summary className="cursor-pointer text-[13px] text-primary">Cómo se leyeron las columnas</summary>
                      <div className="flex flex-wrap gap-1 mt-1">{i.columnas.map((c) => <span key={c.campo} className="rounded bg-surface-container-low px-1.5 py-0.5 text-[12px]">{c.original} → <b>{c.campo}</b></span>)}</div>
                      {i.ignoradas.length > 0 && <p className="text-[12px] text-on-surface-variant mt-1">No usadas: {i.ignoradas.join(", ")}</p>}
                    </details>
                    {i.errores.length > 0 && (
                      <table className="w-full mt-2 text-[13px]">
                        <thead><tr className="text-left text-on-surface-variant"><th className="w-16">Fila</th><th>Problema</th></tr></thead>
                        <tbody>{i.errores.map((e) => <tr key={e.fila} className="border-t border-outline-variant/50"><td className="py-0.5">{e.fila}</td><td className="text-error">{e.motivo}</td></tr>)}</tbody>
                      </table>
                    )}
                    {i.n_errores > i.errores.length && <p className="text-[12px] text-on-surface-variant">… y {i.n_errores - i.errores.length} filas más con problemas.</p>}
                  </>}
                </div>
              ))}
            </div>
          </Caja>
        )}
      </div>

      <div className="lg:col-span-4 flex flex-col gap-4">
        <Caja titulo="Plantillas">
          <p className="text-[13px] text-on-surface-variant mb-2">Columnas mínimas de cada tabla. Los nombres pueden variar (p. ej. "RUT", "Fecha ingreso", "CIE10", "Prioridad"): el sistema los reconoce.</p>
          <ul className="divide-y divide-outline-variant/60 text-[14px]">
            {TABLAS_IMPORT.map(([t, n, req]) => (
              <li key={t} className="py-2">
                <div className="flex items-center justify-between"><span className="font-semibold">{n}</span>
                  <a href={api.urlPlantilla(t)} className="text-primary text-[13px] font-semibold flex items-center gap-0.5"><Icono n="download" className="text-[16px]" />Plantilla</a></div>
                <div className="text-[12px] text-on-surface-variant">{req}</div>
              </li>
            ))}
          </ul>
        </Caja>
        <Caja titulo="Qué se convierte solo">
          <ul className="list-disc pl-5 text-[13px] space-y-1">
            <li>Fechas en dd-mm-aaaa, dd/mm/aaaa, aaaa-mm-dd o fecha interna de Excel.</li>
            <li>Prioridad "ALTA", "Alta", "1", "Inmediata" → alta (igual media y baja).</li>
            <li>Sexo "Femenino", "Mujer", "F" → F. Sí/No, 1/0, X → verdadero/falso.</li>
            <li>CIE-10 "I50.9" → I50; la especialidad y el diagnóstico se completan desde el catálogo.</li>
            <li>Si una medición no trae "fuera de rango", se calcula con los rangos del diccionario de datos.</li>
            <li>CSV separado por coma, punto y coma o tabulación; UTF-8 o Latin-1.</li>
          </ul>
        </Caja>
      </div>
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

function Ficha({ p, total, detalle, fecha, esApi, demo, onCambio, onAviso, onDestacar }) {
  const [historia, setHistoria] = useState(null);
  useEffect(() => { api.getHistoria(p.id_paciente, fecha).then(setHistoria).catch(() => setHistoria(null)); }, [p.id_paciente, fecha, p.categoria, p.posicion]);
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
  const [tab, setTab] = useState("resumen");
  const confirmar = () => correr("rev", async () => { await api.postRevision(p.id_paciente, { accion: "confirmar", fecha_corte: fecha }); await onCambio(); onAviso({ titulo: "Prioridad confirmada" }); });
  const guardarAjuste = () => correr("rev", async () => {
    await api.postRevision(p.id_paciente, { accion: "ajustar", categoria_ajustada: ajuste.categoria, motivo: ajuste.motivo, fecha_corte: fecha });
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
        {p.contactar_hoy && <div className="mt-3 p-2.5 rounded bg-error-container text-on-error-container text-[14px] flex gap-2"><Icono n="call" className="text-[20px]" /><span><b>Contactar hoy.</b> Evaluar sobrecupo o derivación a urgencia según criterio médico.</span></div>}
        {p.riesgo_vital && !p.contactar_hoy && p.contacto && <div className="mt-3 p-2.5 rounded bg-hlf-claro text-hlf text-[14px] flex gap-2"><Icono n="task_alt" className="text-[20px]" /><span><b>{p.contacto.texto}</b> · {p.contacto.usuario}{p.contacto.nota && ` · ${p.contacto.nota}`}</span></div>}
        {p.estado_revision === "requiere_revision" && <div className="mt-2 p-2.5 rounded bg-ambar-container text-ambar text-[14px] flex gap-2"><Icono n="rate_review" className="text-[20px]" /><span><b>Requiere nueva revisión:</b> {p.revision_vencida_por} después de la última revisión.</span></div>}
        {p.estado_revision === "pendiente" && p.revision_sugerida?.length > 0 && <div className="mt-2 p-2.5 rounded bg-ambar-container/60 text-ambar text-[14px] flex gap-2"><Icono n="rate_review" className="text-[20px]" /><span><b>Revisión sugerida:</b> {[...new Set(p.revision_sugerida.map((s) => s.motivo))].join(" · ")}</span></div>}
        <dl className="mt-3 grid grid-cols-[130px_1fr] gap-y-1 text-[14px]">
          <dt className="text-on-surface-variant">Especialidad</dt><dd>{p.especialidad}</dd>
          <dt className="text-on-surface-variant">Diagnóstico</dt><dd>{p.diagnostico_cie10} · {p.diagnostico_texto}</dd>
          <dt className="text-on-surface-variant">Ingreso a lista</dt><dd>{fmt(p.fecha_ingreso_lista)} ({p.dias_espera} días)</dd>
          <dt className="text-on-surface-variant">Prioridad inicial</dt><dd className="capitalize">{p.prioridad_inicial}</dd>
          <dt className="text-on-surface-variant">N° en la lista</dt><dd>{p.posicion} de {total}</dd>
          <dt className="text-on-surface-variant">Revisión</dt><dd><EstadoRevision p={p} /></dd>
          {(p.grupo_proteccion || p.acg) && <><dt className="text-on-surface-variant">Riesgo social</dt><dd>{[p.grupo_proteccion && `Grupo ${p.grupo_proteccion}`, p.acg && `ACG ${p.acg}`].filter(Boolean).join(" · ")}</dd></>}
          {p.comorbilidades?.length > 0 && <><dt className="text-on-surface-variant">Comorbilidades</dt><dd>{p.comorbilidades.map((c) => c.nombre).join(", ")}</dd></>}
        </dl>
        {p.categoria !== p.categoria_sistema && <p className="mt-2 text-[13px] text-on-surface-variant">El sistema proponía prioridad {p.categoria_sistema}; el equipo clínico la cambió a {p.categoria}. Motivo: {p.revision?.motivo}</p>}
      </Caja>

      <div className="flex border-b border-outline-variant bg-surface-container-lowest rounded-t text-[14px] sticky top-0 z-10">
        {[["resumen", "Resumen"], ["puntaje", "Puntaje"], ["registrar", "Registrar"], ["historia", "Historia"]].map(([k, t]) => (
          <button key={k} onClick={() => setTab(k)} className={`flex-1 py-2 border-b-2 -mb-px ${tab === k ? "border-primary text-primary font-semibold" : "border-transparent text-on-surface-variant"}`}>{t}</button>
        ))}
      </div>

      {tab === "resumen" && <>
      <Caja titulo="Cómo se decidió su lugar en la lista">
        <Camino p={p} total={total} />
      </Caja>
      {esApi && p.riesgo_vital && <Contacto p={p} fecha={fecha} onListo={async (r) => { await onCambio(); onAviso({ titulo: `${p.nombre_fantasia}: ${r.contacto.texto}` }); }} onAviso={onAviso} />}
      </>}

      {tab === "puntaje" && <>
      <Caja titulo="Puntaje de riesgo clínico (LACE)">
        <BoletaLace lace={p.lace} />
      </Caja>

      <Caja titulo="Evolución en la lista">
        {historia ? <GraficoPosicion h={historia} /> : <p className="text-[13px] text-on-surface-variant">Cargando…</p>}
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
      </>}

      {tab === "resumen" && (esApi ? (
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

          <Caja titulo="Resumen para el equipo" accion={<button onClick={pedirResumen} disabled={cargando} className="text-[13px] text-primary font-semibold disabled:opacity-50">{cargando === "ia" ? "Redactando…" : resumen ? "Actualizar" : "Generar"}</button>}>
            {resumen ? <>
              <p className="text-[14px] leading-relaxed">{resumen.explicacion_ia}</p>
              <p className="text-[12px] text-on-surface-variant mt-2">Texto redactado automáticamente a partir del fundamento ({resumen.fuente === "bedrock" ? "Amazon Bedrock" : "plantilla"}). No modifica la prioridad.</p>
            </> : <p className="text-[13px] text-on-surface-variant">Redacta en lenguaje simple el fundamento, por ejemplo para contactar al paciente.</p>}
          </Caja>
        </>
      ) : <Caja><p className="text-on-surface-variant text-[13px]">Sin conexión al servidor: se muestra la lista precalculada. Registrar decisiones requiere la API.</p></Caja>)}

      {tab === "registrar" && (esApi ? (
        <>
          <Informe p={p} fecha={fecha} cargando={cargando} onConfirmar={(ev) => registrarEvento(ev, "Evento del informe registrado")} onAviso={onAviso} />

          <Novedad p={p} fecha={fecha} onListo={async (r) => {
            await onCambio();
            onAviso(r.en_lista ? { titulo: `Registrado: ${r.mensaje}`, despues: r.paciente?.posicion, antes: p.posicion, cat: r.paciente?.categoria }
              : { titulo: `${p.nombre_fantasia}: ${r.mensaje}` });
          }} onAviso={onAviso} />

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
      ) : <Caja><p className="text-on-surface-variant text-[13px]">Registrar informes y novedades requiere conexión al servidor.</p></Caja>)}

      {tab === "historia" && <Caja titulo="Historia mientras espera">
        <ol className="text-[14px]">
          {timeline.map((x, i) => (
            <li key={i} className={`grid grid-cols-[88px_1fr] gap-2 py-1.5 border-b border-outline-variant/50 ${x.nuevo ? "bg-ambar-container/50" : ""}`}>
              <span className="text-on-surface-variant text-[13px]">{fmt(x.f)}</span>
              <span className={x.rojo ? "text-error font-semibold" : x.ambar ? "text-ambar" : ""}>{x.t}{x.d && <span className="text-on-surface-variant font-normal"> · {x.d}</span>}</span>
            </li>
          ))}
          {!detalle && <li className="text-on-surface-variant">Cargando…</li>}
        </ol>
      </Caja>}
    </>
  );
}

// KPIs fijados por el hospital: reevaluación < 72 h tras un evento · concordancia con experto kappa ≥ 0,70 · cobertura 100%.
function Indicadores({ fecha, esApi, data }) {
  const [k, setK] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { if (esApi) api.getKpis(fecha).then(setK).catch((e) => setErr(e.message)); }, [fecha, esApi, data]);
  if (!esApi) return <Caja><p className="text-on-surface-variant">Los indicadores requieren conexión al servidor.</p></Caja>;
  if (err) return <Caja><p className="text-error">{err}</p></Caja>;
  if (!k) return <p className="text-on-surface-variant">Calculando indicadores…</p>;
  const kap = k.concordancia.kappa;
  const Kpi = ({ titulo, valor, meta, ok, detalle, pct }) => (
    <section className={`bg-surface-container-lowest border rounded p-4 border-l-4 ${ok === null ? "border-l-outline" : ok ? "border-l-hlf" : "border-l-ambar"} border-outline-variant`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-[15px]">{titulo}</h3>
        <span className={`text-[12px] font-semibold rounded px-2 py-0.5 ${ok === null ? "bg-surface-container text-on-surface-variant" : ok ? "bg-hlf-claro text-hlf" : "bg-ambar-container text-ambar"}`}>
          {ok === null ? "Sin datos suficientes" : ok ? "Cumple" : "Bajo la meta"}</span>
      </div>
      <div className="text-[32px] font-bold text-primary-container mt-1">{valor}</div>
      <div className="text-[13px] text-on-surface-variant">Meta del hospital: {meta}</div>
      {pct != null && <div className="h-2 rounded bg-surface-container-high overflow-hidden mt-2"><div className="h-full bg-hlf" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} /></div>}
      <p className="text-[13px] mt-2">{detalle}</p>
    </section>
  );
  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-4 md:grid-cols-3">
        <Kpi titulo="Cobertura con criterio común" valor={`${k.cobertura.pct}%`} meta="100% de la lista" ok={k.cobertura.pct === 100} pct={k.cobertura.pct}
          detalle={`${k.cobertura.evaluados} de ${k.cobertura.en_espera} pacientes evaluados con: ${k.cobertura.criterio}.`} />
        <Kpi titulo="Reevaluación tras un evento" valor={k.reevaluacion.eventos_registrados ? `${k.reevaluacion.reevaluados_menos_72h}/${k.reevaluacion.eventos_registrados}` : "Inmediata"}
          meta="< 72 horas" ok={true} pct={100} detalle={k.reevaluacion.detalle} />
        <Kpi titulo="Concordancia con el especialista (kappa)" valor={kap == null ? "—" : kap.toFixed(2).replace(".", ",")} meta="kappa ≥ 0,70"
          ok={!k.concordancia.suficiente ? null : kap >= k.concordancia.meta} pct={kap == null ? null : kap * 100}
          detalle={`${k.concordancia.acuerdos} acuerdos en ${k.concordancia.revisiones} revisiones (confirmar = acuerdo; cambiar prioridad = desacuerdo). ${k.concordancia.suficiente ? "" : "Se necesitan al menos 10 revisiones para un valor confiable."}`} />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Caja titulo="Alertas de riesgo vital">
          <div className="text-[14px] space-y-1">
            <div className="flex justify-between"><span>Pacientes con riesgo vital</span><b>{k.alertas.riesgo_vital}</b></div>
            <div className="flex justify-between"><span>Ya contactados</span><b className="text-hlf">{k.alertas.contactados}</b></div>
            <div className="flex justify-between"><span>Pendientes de contacto</span><b className={k.alertas.pendientes ? "text-error" : ""}>{k.alertas.pendientes}</b></div>
          </div>
        </Caja>
        <Caja titulo="Revisión del especialista">
          <div className="text-[14px] space-y-1">
            <div className="flex justify-between"><span>Pacientes que requieren revisión</span><b className="text-ambar">{k.alertas.revision_sugerida}</b></div>
            <p className="text-[12px] text-on-surface-variant">Descompensaciones, exámenes alterados o aumentos de dosis posteriores a la interconsulta o a la última revisión.</p>
          </div>
        </Caja>
        <Caja titulo="Egresos de la lista">
          <div className="text-[14px] space-y-1">
            <div className="flex justify-between"><span>Por fallecimiento (causal 9)</span><b>{k.egresos.fallecidos}</b></div>
            <div className="flex justify-between"><span>Atendidos en consulta nueva</span><b>{k.egresos.atendidos}</b></div>
          </div>
        </Caja>
      </div>
      <p className="text-[12px] text-on-surface-variant">Kappa de Cohen entre la prioridad que propone el sistema y la decisión del especialista al revisar (Alta / Media / Baja). Indicadores al {fmt(k.fecha_corte)}.</p>
    </div>
  );
}

function EstadoRevision({ p }) {
  if (p.estado_revision === "requiere_revision") return <span className="text-ambar font-semibold">Requiere nueva revisión</span>;
  if (p.estado_revision === "pendiente") return <span className="text-on-surface-variant">Pendiente{p.revision_sugerida?.length ? " · revisión sugerida" : ""}</span>;
  return <span className="text-verde font-semibold">{p.estado_revision === "ajustado" ? "Ajustada" : "Confirmada"}{p.revision?.usuario && ` · ${p.revision.usuario}`}</span>;
}

// Registro del contacto con un paciente 'contactar hoy': reconoce la alerta con un resultado (evita la fatiga de alertas).
function Contacto({ p, fecha, onListo, onAviso }) {
  const [nota, setNota] = useState("");
  const [enviando, setEnviando] = useState(null);
  const enviar = async (resultado) => {
    setEnviando(resultado);
    try { onListo(await api.postContacto(p.id_paciente, { resultado, nota, fecha_corte: fecha })); setNota(""); }
    catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(null); }
  };
  const ops = [["citado", "Citado (sobrecupo)", "bg-primary text-on-primary"], ["derivado_urgencia", "Derivado a urgencia", "bg-error text-on-error"],
    ["se_mantiene", "Se mantiene en lista", "border border-outline-variant"], ["no_contesta", "No contesta", "border border-outline-variant"]];
  return (
    <Caja titulo="Registrar contacto">
      {p.contacto && <p className="text-[13px] mb-2">Último: <b>{p.contacto.texto}</b> · {p.contacto.usuario}</p>}
      <input value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Nota (opcional): p. ej. hora citada, quién contestó" className="w-full h-9 px-2 border border-outline-variant rounded mb-2 text-[14px]" />
      <div className="grid grid-cols-2 gap-2 text-[13px]">
        {ops.map(([k, t, c]) => <button key={k} disabled={enviando} onClick={() => enviar(k)} className={`py-2 rounded font-semibold disabled:opacity-50 ${c}`}>{enviando === k ? "…" : t}</button>)}
      </div>
      <p className="text-[12px] text-on-surface-variant mt-2">Al registrar el contacto la alerta "contactar hoy" se apaga (salvo "no contesta"). El paciente sigue priorizado.</p>
    </Caja>
  );
}

const COLOR_HEX = { alta: "#ba1a1a", media: "#8a5100", baja: "#1f6b35" };

// Boleta del puntaje LACE: cada línea con sus puntos publicados (van Walraven et al., CMAJ 2010, Tabla 3).
function BoletaLace({ lace }) {
  const max = { L: 7, A: 3, C: 5, E: 4 };
  return (
    <div>
      <table className="w-full text-[14px]">
        <tbody>
          {lace.partes.map((x) => (
            <tr key={x.letra} className="border-b border-outline-variant/60">
              <td className="py-1.5 w-8"><span className="inline-flex w-6 h-6 items-center justify-center rounded bg-primary/10 text-primary font-bold">{x.letra}</span></td>
              <td className="py-1.5">
                <div>{x.nombre}</div>
                <div className="text-[12px] text-on-surface-variant">{x.valor}</div>
              </td>
              <td className="py-1.5 w-28">
                <div className="h-2 rounded bg-surface-container-high overflow-hidden"><div className="h-full bg-primary" style={{ width: `${(x.puntos / max[x.letra]) * 100}%` }} /></div>
              </td>
              <td className={`py-1.5 w-14 text-right font-semibold ${x.puntos ? "" : "text-on-surface-variant"}`}>+{x.puntos}</td>
            </tr>
          ))}
          <tr>
            <td colSpan={3} className="pt-2 font-bold text-primary-container">Puntaje LACE total</td>
            <td className="pt-2 text-right text-[22px] font-bold text-primary-container">{lace.total}</td>
          </tr>
        </tbody>
      </table>
      <p className="text-[12px] text-on-surface-variant mt-2">
        Puntos según {lace.fuente}. Ordena a los pacientes dentro de la misma prioridad (más puntos, antes). L queda en 0 porque el registro no trae los días de estada.
      </p>
    </div>
  );
}

// Camino de la decisión: cada paso con su fuente (sin puntos ni pesos).
function Camino({ p, total }) {
  const rz = Object.fromEntries(p.razones.map((r) => [r.factor, r]));
  const subio = rz.tabla_oficial && rz.tabla_oficial.valor.startsWith('"') && !rz.tabla_oficial.valor.includes("no supera");
  const pasos = [{ t: "Interconsulta", v: `Prioridad ${p.prioridad_inicial}`, f: "Especialista al priorizar la SIC", cat: p.prioridad_inicial }];
  if (p.estado_clinico === "descompensado" && rz.evento) pasos.push({ t: "Evento posterior", v: rz.evento.valor, f: "Registro clínico", icon: "emergency" });
  if (p.estado_clinico === "estabilizado" && rz.evento) pasos.push({ t: "Evolución", v: rz.evento.valor.split(":")[0], f: "Registro clínico", icon: "trending_down" });
  if (subio) pasos.push({ t: "Tabla de priorización HLF", v: rz.tabla_oficial.valor.split("→")[0].replaceAll('"', "").trim(), f: rz.tabla_oficial.fuente.replace("Tabla SSMSO 2025, HLF, ", "SSMSO 2025, "), cat: p.categoria_sistema });
  else if (rz.tabla_oficial) pasos.push({ t: "Tabla de priorización HLF", v: "Sin cambio de prioridad", f: "Revisión clínica sugerida", icon: "rate_review" });
  if (p.categoria !== p.categoria_sistema) pasos.push({ t: "Decisión clínica", v: `Prioridad ${p.categoria}`, f: p.revision?.motivo, cat: p.categoria });
  if (p.riesgo_vital) pasos.push(p.contactar_hoy ? { t: "Contactar hoy", v: "Riesgo vital", f: "Criterio MINSAL", icon: "call", rojo: true }
    : { t: "Riesgo vital", v: "Contactado", f: p.contacto?.texto, icon: "task_alt", cat: "alta" });
  if (p.grupo_proteccion) pasos.push({ t: "Grupo de especial protección", v: p.grupo_proteccion, f: "MINSAL criterio 2", icon: "shield_person" });
  pasos.push({ t: "Lugar en la lista", v: `N° ${p.posicion} de ${total}`, f: p.antiguedad_mayor_1_anio ? "Más de 1 año en espera" : `${p.dias_espera} días en espera`, final: true });
  return (
    <div className="flex flex-wrap items-stretch gap-1">
      {pasos.map((s, i) => (
        <div key={i} className="flex items-center gap-1">
          <div className={`rounded border px-2.5 py-1.5 min-w-[96px] max-w-[160px] ${s.rojo ? "bg-error text-on-error border-error" : s.final ? "bg-primary text-on-primary border-primary" : "bg-surface-container-lowest border-outline-variant"}`}
            style={s.cat && !s.rojo && !s.final ? { borderTop: `4px solid ${COLOR_HEX[s.cat]}` } : undefined}>
            <div className={`text-[11px] ${s.rojo || s.final ? "opacity-90" : "text-on-surface-variant"}`}>{s.icon && <Icono n={s.icon} className="text-[14px] mr-0.5" />}{s.t}</div>
            <div className="text-[14px] font-semibold leading-tight">{s.v}</div>
            {s.f && <div className={`text-[11px] leading-tight mt-0.5 ${s.rojo || s.final ? "opacity-80" : "text-on-surface-variant"}`}>{s.f}</div>}
          </div>
          {i < pasos.length - 1 && <Icono n="arrow_forward" className="text-[18px] text-outline" />}
        </div>
      ))}
    </div>
  );
}

// Posición en la lista a lo largo del tiempo (N° 1 arriba). Una sola serie: sin leyenda; el color del punto es la prioridad.
function GraficoPosicion({ h }) {
  const [hover, setHover] = useState(null);
  const pts = h.puntos.filter((x) => !x.excluido);
  if (pts.length < 2) return <p className="text-[13px] text-on-surface-variant">Aún no hay suficiente historia en la lista.</p>;
  const W = 380, H = 190, m = { l: 40, r: 12, t: 12, b: 26 };
  const t = (f) => new Date(f + "T12:00:00").getTime();
  const x0 = t(pts[0].fecha), x1 = t(pts[pts.length - 1].fecha);
  const ymax = Math.max(...pts.map((p) => p.total));
  const X = (f) => m.l + ((t(f) - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
  const Y = (pos) => m.t + ((pos - 1) / (ymax - 1)) * (H - m.t - m.b);
  const ticks = [1, Math.round(ymax / 2), ymax];
  const meses = [...new Set(pts.map((p) => p.fecha.slice(0, 7)))];
  const nombreMes = (ym) => ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"][+ym.slice(5, 7) - 1];
  const linea = pts.map((p, i) => `${i ? "L" : "M"}${X(p.fecha).toFixed(1)},${Y(p.posicion).toFixed(1)}`).join(" ");
  const evs = h.eventos.filter((e) => e.fecha_evento >= pts[0].fecha);
  const hp = hover != null ? pts[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Posición del paciente en la lista a lo largo del tiempo">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke="#dfe5eb" strokeWidth="1" />
            <text x={m.l - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="#3d4650">N° {v}</text>
          </g>
        ))}
        {meses.map((ym) => { const xx = X(`${ym}-01` < pts[0].fecha ? pts[0].fecha : `${ym}-01`); return <text key={ym} x={xx} y={H - 8} fontSize="11" fill="#3d4650" textAnchor="middle">{nombreMes(ym)}</text>; })}
        {evs.map((e, i) => {
          const xx = Math.min(Math.max(X(e.fecha_evento), m.l), W - m.r);
          const grave = e.severidad === "grave" || e.subtipo.includes("descompensaci");
          return (
            <g key={i}>
              <line x1={xx} x2={xx} y1={m.t} y2={H - m.b} stroke={grave ? "#ba1a1a" : "#1f6b35"} strokeWidth="1" strokeDasharray="3 3" />
              <circle cx={xx} cy={m.t} r="4" fill={grave ? "#ba1a1a" : "#1f6b35"}><title>{fmt(e.fecha_evento)}: {e.subtipo}</title></circle>
            </g>
          );
        })}
        <path d={linea} fill="none" stroke="#0f69b4" strokeWidth="2" strokeLinejoin="round" />
        {pts.map((p, i) => (
          <g key={p.fecha} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <circle cx={X(p.fecha)} cy={Y(p.posicion)} r="12" fill="transparent" />
            <circle cx={X(p.fecha)} cy={Y(p.posicion)} r={hover === i ? 6 : 4.5} fill={COLOR_HEX[p.categoria]} stroke="#fff" strokeWidth="2" />
          </g>
        ))}
        {(() => { const u = pts[pts.length - 1]; return <text x={X(u.fecha) - 8} y={Y(u.posicion) + (Y(u.posicion) < 30 ? 16 : -8)} textAnchor="end" fontSize="12" fontWeight="600" fill="#1a1f24">N° {u.posicion}</text>; })()}
      </svg>
      {hp && (
        <div className="absolute pointer-events-none bg-on-surface text-white text-[12px] rounded px-2 py-1 shadow"
          style={{ left: `${(X(hp.fecha) / W) * 100}%`, top: `${(Y(hp.posicion) / H) * 100}%`, transform: "translate(-50%, -120%)" }}>
          {fmt(hp.fecha)} · N° {hp.posicion} de {hp.total} · {ETIQUETA[hp.categoria]}{hp.riesgo_vital ? " · contactar hoy" : ""}
        </div>
      )}
      <div className="flex flex-wrap gap-3 text-[12px] text-on-surface-variant mt-1">
        {["alta", "media", "baja"].map((c) => <span key={c} className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: COLOR_HEX[c] }} />Prioridad {ETIQUETA[c].toLowerCase()}</span>)}
        <span className="flex items-center gap-1"><span className="w-3 border-t border-dashed border-error" />Descompensación</span>
        <span className="flex items-center gap-1"><span className="w-3 border-t border-dashed border-verde" />Estabilización</span>
      </div>
    </div>
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

// Cámara en vivo dentro de la app: vista previa + botón para tomar la foto.
function Camara({ onFoto, onCerrar }) {
  const video = useRef(null);
  const archivo = useRef(null);
  const [error, setError] = useState(null);
  const [listo, setListo] = useState(false);
  useEffect(() => {
    let stream;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } }, audio: false });
        video.current.srcObject = stream;
        await video.current.play();
        setListo(true);
      } catch (e) {
        setError(e.name === "NotAllowedError" ? "No se dio permiso para usar la cámara." : "No se encontró una cámara disponible.");
      }
    })();
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);
  const tomar = () => {
    const v = video.current, lado = 1600, k = Math.min(1, lado / Math.max(v.videoWidth, v.videoHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(v.videoWidth * k); c.height = Math.round(v.videoHeight * k);
    c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    onFoto(c.toDataURL("image/jpeg", 0.85).split(",")[1]);
  };
  const subir = async (e) => { const f = e.target.files?.[0]; if (f) onFoto(await fotoABase64(f)); };
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onCerrar}>
      <div className="bg-surface-container-lowest rounded max-w-2xl w-full" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-2.5 border-b border-outline-variant flex justify-between items-center">
          <h2 className="font-semibold">Fotografiar documento</h2>
          <button onClick={onCerrar} className="text-on-surface-variant"><Icono n="close" /></button>
        </div>
        <div className="p-4">
          {error ? <p className="text-on-surface-variant mb-3">{error} Puede subir una imagen en su lugar.</p> : (
            <div className="relative bg-black rounded overflow-hidden">
              <video ref={video} playsInline muted className="w-full max-h-[60vh] object-contain" />
              <div className="absolute inset-6 border-2 border-white/70 border-dashed rounded pointer-events-none" />
              {!listo && <p className="absolute inset-0 flex items-center justify-center text-white">Abriendo cámara…</p>}
            </div>
          )}
          <p className="text-[13px] text-on-surface-variant mt-2">Encuadre el documento completo dentro del recuadro, con buena luz.</p>
          <div className="flex gap-2 mt-3">
            {!error && <button disabled={!listo} onClick={tomar} className="flex-1 py-2.5 rounded bg-primary text-on-primary font-semibold flex items-center justify-center gap-1 disabled:opacity-40"><Icono n="photo_camera" />Tomar foto</button>}
            <button onClick={() => archivo.current.click()} className="flex-1 py-2.5 rounded border border-outline-variant font-semibold">Subir imagen</button>
            <input ref={archivo} type="file" accept="image/*" hidden onChange={subir} />
          </div>
        </div>
      </div>
    </div>
  );
}

function NuevoPaciente({ fecha, onCerrar, onListo }) {
  const [cat, setCat] = useState(null);
  const [f, setF] = useState({ nombre: "", edad: "", sexo: "F", comuna: "La Florida", prevision: "FONASA B", especialidad: "", diagnostico_cie10: "", prioridad_inicial: "media", origen_derivacion: "CESFAM/APS", grupo_proteccion: "", acg: "" });
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => { api.getCatalogo().then(setCat).catch((e) => setError(e.message)); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value, ...(k === "especialidad" ? { diagnostico_cie10: "" } : {}) });
  const especialidades = cat ? [...new Set(cat.diagnosticos.map((d) => d.especialidad))] : [];
  const dxs = cat ? cat.diagnosticos.filter((d) => d.especialidad === f.especialidad) : [];
  const valido = f.nombre.trim() && f.edad !== "" && f.diagnostico_cie10;
  const guardar = async () => {
    setEnviando(true); setError(null);
    try { onListo(await api.postPaciente({ ...f, edad: Number(f.edad), fecha_corte: fecha })); }
    catch (e) { setError(e.message); setEnviando(false); }
  };
  const campo = "h-9 px-2 border border-outline-variant rounded bg-white w-full";
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onCerrar}>
      <div className="bg-surface-container-lowest rounded max-w-xl w-full" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-2.5 border-b border-outline-variant flex justify-between items-center">
          <h2 className="font-semibold">Ingresar interconsulta a la lista de espera</h2>
          <button onClick={onCerrar} className="text-on-surface-variant"><Icono n="close" /></button>
        </div>
        <div className="p-4 grid grid-cols-2 gap-3 text-[14px]">
          <Filtro label="Nombre del paciente"><input value={f.nombre} onChange={set("nombre")} className={campo} autoFocus /></Filtro>
          <div className="grid grid-cols-2 gap-2">
            <Filtro label="Edad"><input type="number" min={0} max={120} value={f.edad} onChange={set("edad")} className={campo} /></Filtro>
            <Filtro label="Sexo"><select value={f.sexo} onChange={set("sexo")} className={campo}><option value="F">Femenino</option><option value="M">Masculino</option></select></Filtro>
          </div>
          <Filtro label="Comuna"><select value={f.comuna} onChange={set("comuna")} className={campo}>{cat?.comunas.map((c) => <option key={c}>{c}</option>)}</select></Filtro>
          <Filtro label="Previsión"><select value={f.prevision} onChange={set("prevision")} className={campo}>{cat?.previsiones.map((c) => <option key={c}>{c}</option>)}</select></Filtro>
          <Filtro label="Especialidad"><select value={f.especialidad} onChange={set("especialidad")} className={campo}><option value="">Seleccione…</option>{especialidades.map((e) => <option key={e}>{e}</option>)}</select></Filtro>
          <Filtro label="Diagnóstico (CIE-10)"><select value={f.diagnostico_cie10} onChange={set("diagnostico_cie10")} disabled={!f.especialidad} className={campo}><option value="">Seleccione…</option>{dxs.map((d) => <option key={d.diagnostico_cie10} value={d.diagnostico_cie10}>{d.diagnostico_cie10} · {d.diagnostico_texto}</option>)}</select></Filtro>
          <Filtro label="Prioridad asignada al revisar la SIC">
            <div className="flex gap-1">{["alta", "media", "baja"].map((c) => (
              <button key={c} type="button" onClick={() => setF({ ...f, prioridad_inicial: c })} className={`flex-1 h-9 rounded border font-semibold ${f.prioridad_inicial === c ? COLOR_CAT[c] : "border-outline-variant text-on-surface-variant"}`}>{ETIQUETA[c]}</button>
            ))}</div>
          </Filtro>
          <Filtro label="Origen de la derivación"><select value={f.origen_derivacion} onChange={set("origen_derivacion")} className={campo}>{cat?.origenes.map((c) => <option key={c}>{c}</option>)}</select></Filtro>
          <Filtro label="Grupo de especial protección"><select value={f.grupo_proteccion} onChange={set("grupo_proteccion")} className={campo}><option value="">Ninguno</option>{cat?.grupos_proteccion.map((g) => <option key={g}>{g}</option>)}</select></Filtro>
          <Filtro label="Riesgo ACG (si se conoce)"><select value={f.acg} onChange={set("acg")} className={campo}><option value="">Sin dato</option>{cat?.acg.map((a) => <option key={a.nivel} value={a.nivel}>{a.nivel} · {a.texto}</option>)}</select></Filtro>
        </div>
        {error && <p className="px-4 text-error text-[13px]">{error}</p>}
        <div className="px-4 py-3 border-t border-outline-variant flex justify-end gap-2">
          <button onClick={onCerrar} className="px-4 py-2 rounded border border-outline-variant font-semibold">Cancelar</button>
          <button disabled={!valido || enviando} onClick={guardar} className="px-4 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{enviando ? "Ingresando…" : "Ingresar y priorizar"}</button>
        </div>
      </div>
    </div>
  );
}

function Informe({ p, fecha, cargando, onConfirmar, onAviso }) {
  const [texto, setTexto] = useState("");
  const [res, setRes] = useState(null);
  const [leyendo, setLeyendo] = useState(false);
  const [camara, setCamara] = useState(false);
  const [elegido, setElegido] = useState(0);
  const [esDelPaciente, setEsDelPaciente] = useState(false);
  const analizar = async (body) => {
    setLeyendo(true); setRes(null); setElegido(0); setEsDelPaciente(false);
    try { setRes(await api.postInforme(p.id_paciente, { ...body, fecha_corte: fecha })); }
    catch (e) { onAviso({ titulo: "No se pudo leer el informe: " + e.message }); }
    finally { setLeyendo(false); }
  };
  const foto = (b64) => { setCamara(false); analizar({ imagen_base64: b64, media_type: "image/jpeg" }); };
  const eventos = res?.eventos || [];
  const ev = eventos[elegido];
  const dudosas = new Set((res?.lectura?.lineas_dudosas || []).map((l) => l.texto));
  const bloqueado = res?.otro_paciente || (res?.lectura && !res.lectura.legible);
  return (
    <Caja titulo="Registrar informe recibido">
      <p className="text-[13px] text-on-surface-variant mb-2">Epicrisis, DAU de urgencia o nota clínica. Se propone el evento y usted confirma antes de actualizar la lista.</p>
      <textarea rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Ej.: Consulta en urgencia por dolor torácico en reposo. Se hospitaliza en cardiología."
        className="w-full p-2 border border-outline-variant rounded focus:outline-none focus:border-primary resize-y text-[14px]" />
      <div className="flex gap-2 mt-2">
        <button disabled={!texto.trim() || leyendo} onClick={() => analizar({ texto })} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{leyendo ? "Leyendo…" : "Revisar informe"}</button>
        <button disabled={leyendo} onClick={() => setCamara(true)} className="flex-1 py-2 rounded border border-outline-variant font-semibold flex items-center justify-center gap-1"><Icono n="photo_camera" className="text-[18px]" />Foto del documento</button>
      </div>
      {camara && <Camara onFoto={foto} onCerrar={() => setCamara(false)} />}
      {leyendo && <p className="mt-2 text-[13px] text-on-surface-variant flex items-center gap-1"><Icono n="hourglass_top" className="text-[16px] animate-spin" />Leyendo el documento…</p>}
      {res?.advertencias?.length > 0 && (
        <div className="mt-3 space-y-1">
          {res.advertencias.map((a, i) => (
            <div key={i} className={`rounded p-2 text-[13px] flex gap-1.5 ${res.otro_paciente && i === 0 ? "bg-error text-on-error font-semibold" : "bg-ambar-container text-ambar"}`}>
              <Icono n="warning" className="text-[18px]" /><span>{a}</span></div>
          ))}
        </div>
      )}
      {res && !ev && <p className="mt-2 text-[13px] text-on-surface-variant">{res.mensaje}</p>}
      {res?.transcripcion && (
        <details className="mt-2 text-[13px]" open={dudosas.size > 0}>
          <summary className="cursor-pointer text-on-surface-variant">
            Texto leído del documento (Amazon Textract{res.lectura?.confianza_media != null && ` · confianza ${res.lectura.confianza_media}%`})
          </summary>
          <div className="mt-1 rounded border border-outline-variant p-2 font-mono text-[12px]">
            {res.transcripcion.split("\n").map((l, i) => <div key={i} className={dudosas.has(l) ? "bg-ambar-container text-ambar" : ""} title={dudosas.has(l) ? "Leída con baja confianza: verifique" : ""}>{l}</div>)}
          </div>
        </details>
      )}
      {res?.descartados?.length > 0 && <p className="mt-1 text-[12px] text-on-surface-variant">Descartados por la validación: {res.descartados.map((d) => `${d.subtipo} (${d.motivo})`).join("; ")}</p>}
      {ev && (
        <div className="mt-3 border border-outline-variant rounded p-3 space-y-2 text-[14px]">
          {eventos.length > 1 && <p className="text-[13px] font-semibold">Se encontraron {eventos.length} eventos en el documento. Elija cuál registrar:</p>}
          <div className="space-y-1">
            {eventos.map((e, i) => (
              <label key={i} className={`flex items-start gap-2 rounded p-1.5 cursor-pointer ${i === elegido ? "bg-primary/10" : "hover:bg-surface-container-low"}`}>
                {eventos.length > 1 && <input type="radio" checked={i === elegido} onChange={() => setElegido(i)} className="mt-1" />}
                <span>
                  <b>{TIPO_EVENTO[e.tipo_evento]}</b> · {e.subtipo} · {fmt(e.fecha_evento)}
                  {!e.fecha_en_documento && <span className="text-ambar text-[12px]"> (fecha no encontrada: verificar)</span>}
                  {e.detectado_por === "bedrock" && <span className="ml-1 text-[11px] rounded bg-tertiary-fixed text-on-tertiary-fixed-variant px-1">sugerido por IA</span>}
                </span>
              </label>
            ))}
          </div>
          <blockquote className="border-l-4 border-ambar bg-ambar-container/40 px-2 py-1 italic">“{ev.evidencia}”</blockquote>
          <div className="flex items-center gap-2"><span className="text-on-surface-variant">Prioridad:</span><Prioridad cat={res.categoria_actual} /><span>→</span><Prioridad cat={ev.categoria_propuesta} /></div>
          {ev.razones_propuestas?.map((r, i) => <div key={i} className="text-[13px] text-on-surface-variant">{r.valor} · {r.fuente}</div>)}
          <label className={`flex items-start gap-2 rounded p-2 text-[13px] ${bloqueado ? "opacity-50" : "bg-surface-container-low"}`}>
            <input type="checkbox" checked={esDelPaciente} disabled={bloqueado} onChange={(e) => setEsDelPaciente(e.target.checked)} className="mt-0.5" />
            <span>Confirmo que el documento corresponde a <b>{p.nombre_fantasia}</b> ({p.id_paciente}) y que el evento está bien leído.</span>
          </label>
          <div className="flex gap-2 pt-1">
            <button disabled={cargando || !esDelPaciente || bloqueado} onClick={async () => { await onConfirmar({ ...ev, detalle: `Informe: ${ev.evidencia}` }); setRes(null); setTexto(""); }}
              className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Confirmar y actualizar lista</button>
            <button onClick={() => setRes(null)} className="flex-1 py-2 rounded border border-outline-variant font-semibold">Descartar</button>
          </div>
          <p className="text-[12px] text-on-surface-variant">
            {res.transcripcion ? "Leído con Amazon Textract (OCR). " : ""}Evento detectado por {ev.detectado_por === "bedrock" ? "IA (respaldo)" : "reglas"} y validado (Pydantic): tipo y severidad del registro, frase presente en el documento, fecha no futura.
          </p>
        </div>
      )}
    </Caja>
  );
}

// Pantalla "Hoy": lista de tareas del día en dos pasos, con una sola forma de decir cada cosa ("hora libre").
//   Paso 1: a quién llamar hoy (riesgo vital) y qué ofrecerle.  Paso 2: cómo llenar las horas libres de cada box.
function Hoy({ vitales, todosPacientes, fecha, esp, setEsp, onVer, esApi, onCambio, onAviso }) {
  const [b, setB] = useState(null);
  const [err, setErr] = useState(null);
  const [enviando, setEnviando] = useState(null);
  useEffect(() => {
    if (!esApi) return setErr("La agenda de box requiere conexión al servidor.");
    setB(null);
    api.getBoxes(fecha, esp === "Todas" ? null : esp).then(setB).catch((e) => setErr(e.message));
  }, [fecha, esp, esApi, vitales]);

  const todos = vitales.filter((p) => esp === "Todas" || p.especialidad === esp);
  const pendientes = todos.filter((p) => p.contactar_hoy);
  // Se descompensaron pero su diagnóstico no tiene fila de "descompensado" en la tabla HLF: no suben solos,
  // pero no pueden quedar invisibles → avisar al especialista para que los revise.
  const aRevisar = (todosPacientes || []).filter((p) => (esp === "Todas" || p.especialidad === esp) && !p.riesgo_vital &&
    p.estado_clinico === "descompensado" && p.estado_revision !== "confirmado" && p.estado_revision !== "ajustado");
  const listos = todos.filter((p) => !p.contactar_hoy);
  const hora = b?.cupo_por_paciente || {};
  const box = Object.fromEntries((b?.mapa || []).map((x) => [x.id_box, x]));
  const horasLibres = (b?.especialidades || []).reduce((s, e) => s + e.cupos_libres_hoy, 0);
  const conHora = todos.filter((p) => hora[p.id_paciente]).length;
  const nombreBox = (id) => id?.replace("BOX-", "Box ");

  const registrar = async (p, resultado) => {
    setEnviando(p.id_paciente + resultado);
    const h = hora[p.id_paciente];
    try {
      const r = await api.postContacto(p.id_paciente, { resultado, fecha_corte: fecha,
        ...(resultado === "citado" && h ? { hora: h.hora, hora_fin: h.hora_fin, id_box: h.id_box } : {}) });
      await onCambio(); onAviso({ titulo: `${p.nombre_fantasia}: ${r.contacto.texto}` });
    } catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(null); }
  };

  const Ofrecer = ({ p }) => hora[p.id_paciente]
    ? <span className="text-hlf font-semibold">Ofrecer hora hoy: {hora[p.id_paciente].hora} – {hora[p.id_paciente].hora_fin} h · {nombreBox(hora[p.id_paciente].id_box)}</span>
    : <span className="text-error font-semibold">No queda hora hoy en {p.especialidad}: evaluar sobrecupo o derivación a urgencia</span>;

  return (
    <div className="flex flex-col gap-5">
      {b && (
        <section className="rounded border border-primary/30 bg-primary/5 p-4 text-[15px] leading-relaxed">
          <b>Resumen del día ({fmt(b.dia_agenda)}{esp !== "Todas" ? ` · ${esp}` : ""}):</b> quedan <b>{horasLibres} horas libres</b> en los box.
          {" "}{todos.length ? <>Hay <b>{todos.length} pacientes con riesgo vital</b>: <b className="text-hlf">{conHora} tienen hora hoy</b>
            {todos.length - conHora > 0 && <> y <b className="text-error">{todos.length - conHora} no alcanzan hora</b></>}.
            {" "}{pendientes.length ? <>Faltan <b>{pendientes.length} llamadas</b>.</> : <>Ya se llamó a todos.</>}</> : "No hay pacientes con riesgo vital."}
        </section>
      )}
      {b && b.especialidades.some((e) => e.vitales_sin_cupo.length > 0) && (
        <section className="rounded border-2 border-error bg-error-container/50 p-4 text-[14px]">
          <div className="font-semibold text-on-error-container text-[15px] flex items-center gap-1"><Icono n="crisis_alert" className="text-[20px]" />
            Capacidad insuficiente hoy: hay más pacientes con riesgo vital que horas libres</div>
          <ul className="mt-1 space-y-0.5">
            {b.especialidades.filter((e) => e.vitales_sin_cupo.length > 0).map((e) => (
              <li key={e.especialidad}><b>{e.especialidad}:</b> {e.vitales_sin_cupo.length} paciente{e.vitales_sin_cupo.length !== 1 ? "s" : ""} con riesgo vital sin hora · {e.cupos_libres_hoy} hora{e.cupos_libres_hoy !== 1 ? "s" : ""} libre{e.cupos_libres_hoy !== 1 ? "s" : ""}</li>
            ))}
          </ul>
          <p className="mt-2">Escalar a la jefatura: habilitar sobrecupos, pedir horas a médicos con tiempo libre (pestaña <i>Tengo horas libres</i>) o derivar a urgencia según criterio médico. Llamar en el orden de la lista (N°).</p>
        </section>
      )}
      {err && <Caja><p className="text-on-surface-variant">{err}</p></Caja>}
      {!err && !b && <p className="text-on-surface-variant">Cargando el día…</p>}

      <div className="grid gap-5 lg:grid-cols-12 items-start">
        <Caja titulo={`Paso 1 · Llamar hoy (${pendientes.length} pendiente${pendientes.length !== 1 ? "s" : ""})`} className="lg:col-span-5 border-l-4 border-l-error">
          <p className="text-[13px] text-on-surface-variant mb-3">Pacientes que se descompensaron de forma grave después de la interconsulta y no se han estabilizado. No esperan su turno: se llaman hoy y se les ofrece lo que indica cada uno.</p>
          {todos.length === 0 && <p className="text-on-surface-variant">Nadie para llamar hoy{esp !== "Todas" && ` en ${esp}`}.</p>}
          <ul className="divide-y divide-outline-variant/60">
            {pendientes.map((p) => (
              <li key={p.id_paciente} className="py-2.5 text-[14px]">
                <button onClick={() => onVer(p.id_paciente)} className="text-left hover:underline">
                  <span className="text-on-surface-variant text-[13px] mr-1">N° {p.posicion}</span>
                  <b>{p.nombre_fantasia}</b> <span className="text-on-surface-variant text-[13px]">· {p.edad} años · {p.especialidad} · {p.diagnostico_texto}</span>
                </button>
                <div className="text-[13px] mt-0.5">{b ? <Ofrecer p={p} /> : null}</div>
                {p.contacto?.intentos_sin_respuesta > 0 && <div className="text-[12px] text-ambar font-semibold">{p.contacto.intentos_sin_respuesta} intento{p.contacto.intentos_sin_respuesta > 1 ? "s" : ""} sin respuesta{p.contacto.intentos_sin_respuesta >= 3 ? ": evaluar visita domiciliaria o derivación" : ""}</div>}
                <div className="flex flex-wrap gap-1 mt-1.5 text-[12px]">
                  {[["citado", "Citado"], ["derivado_urgencia", "Derivado a urgencia"], ["se_mantiene", "Se mantiene"], ["no_contesta", "No contesta"]].map(([k, t]) => (
                    <button key={k} disabled={enviando} onClick={() => registrar(p, k)}
                      className={`px-2 py-1 rounded border font-semibold disabled:opacity-40 ${k === "derivado_urgencia" ? "border-error text-error" : k === "citado" ? "border-primary text-primary" : "border-outline-variant text-on-surface-variant"}`}>
                      {enviando === p.id_paciente + k ? "…" : t}</button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
          {listos.length > 0 && (
            <details className="mt-2 text-[13px]">
              <summary className="cursor-pointer text-on-surface-variant">Ya llamados hoy ({listos.length})</summary>
              <ul className="mt-1 space-y-1">
                {listos.map((p) => <li key={p.id_paciente}><button onClick={() => onVer(p.id_paciente)} className="hover:underline">{p.nombre_fantasia}</button> · <span className="text-hlf">{p.contacto?.texto}</span></li>)}
              </ul>
            </details>
          )}

          <div className="mt-4 pt-3 border-t border-outline-variant">
            <h3 className="text-[15px] font-semibold text-ambar flex items-center gap-1"><Icono n="rate_review" className="text-[18px]" />Avisar al especialista ({aRevisar.length})</h3>
            <p className="text-[13px] text-on-surface-variant mb-2">Se descompensaron después de la interconsulta, pero la tabla del HLF no define cuánto sube su prioridad. No se les cambia solo: el especialista debe revisarlos y confirmar o cambiar su prioridad.</p>
            {aRevisar.length === 0 && <p className="text-[13px] text-on-surface-variant">Nadie pendiente de revisión{esp !== "Todas" && ` en ${esp}`}.</p>}
            <ul className="divide-y divide-outline-variant/60">
              {aRevisar.map((p) => {
                const ev = p.razones.find((r) => r.factor === "evento");
                return (
                  <li key={p.id_paciente} className="py-2 text-[14px]">
                    <button onClick={() => onVer(p.id_paciente)} className="text-left hover:underline">
                      <b>{p.nombre_fantasia}</b> <span className="text-on-surface-variant text-[13px]">· {p.especialidad} · {p.diagnostico_texto} · prioridad {p.categoria}</span>
                    </button>
                    {ev && <div className="text-[13px] text-ambar">{ev.valor}</div>}
                  </li>
                );
              })}
            </ul>
          </div>
        </Caja>

        <div className="lg:col-span-7 flex flex-col gap-4">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h2 className="text-[17px] font-semibold">Paso 2 · Llenar las horas libres de hoy</h2>
              <p className="text-[13px] text-on-surface-variant">Cada hora libre se propone al siguiente paciente de la lista de su especialidad, en su turno. "Alta / Media / Baja" es la prioridad clínica de la lista, no una urgencia de hoy: las urgencias de hoy están en el Paso 1. Es una propuesta: se confirma al llamar.</p>
            </div>
            <select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-white text-[14px]">{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select>
          </div>
          {b?.especialidades.filter((e) => e.asignaciones.length).map((e) => (
            <Caja key={e.especialidad} titulo={e.especialidad} accion={<span className="text-[13px] text-on-surface-variant">{e.cupos_libres_hoy} hora{e.cupos_libres_hoy !== 1 ? "s" : ""} libre{e.cupos_libres_hoy !== 1 ? "s" : ""} hoy</span>}>
              {e.asignaciones.map((a) => (
                <div key={a.id_box} className="mb-3">
                  <div className="text-[14px] font-semibold mb-1">
                    {nombreBox(a.id_box)} (atiende {a.bloque.replace("-", " a ")} h) · {a.libres === 0 ? "sin horas libres" : `${a.libres} hora${a.libres !== 1 ? "s" : ""} libre${a.libres !== 1 ? "s" : ""}${a.libres !== a.libres_sin_citar ? ` (${a.libres - a.libres_sin_citar} ya citada${a.libres - a.libres_sin_citar > 1 ? "s" : ""})` : ""} → propuesta:`}
                  </div>
                  {a.minutos_por_hora && a.pacientes.length > 0 && <p className="text-[12px] text-on-surface-variant mb-1">Horas sugeridas: bloque dividido en {a.capacidad} atenciones de {a.minutos_por_hora} min; se proponen las últimas libres del bloque.</p>}
                  <ol className="text-[14px]">
                    {a.pacientes.map((p, i) => (
                      <li key={p.id_paciente} onClick={() => onVer(p.id_paciente)} className={`cursor-pointer border-t border-outline-variant/60 py-2 hover:bg-surface-container-low flex gap-2 ${p.riesgo_vital ? "bg-error-container/30" : ""}`}>
                        <span className="shrink-0 w-28 font-semibold text-primary-container text-[14px]">{p.hora ? `${p.hora} – ${p.hora_fin} h` : `${i + 1}.`}</span>
                        <span className="shrink-0"><Prioridad cat={p.categoria} /></span>
                        <span>
                          <b>{p.nombre_fantasia}</b> <span className="text-[13px] text-on-surface-variant">· {p.diagnostico_texto} · {p.dias_espera} días esperando</span>
                          <span className="block text-[13px]">Por qué: {p.motivo}</span>
                          {p.citado && <span className="inline-flex items-center gap-1 text-[13px] text-hlf font-semibold"><Icono n="event_available" className="text-[16px]" />Citado: hora reservada</span>}
                          {!p.citado && p.riesgo_vital && <span className="block text-[13px] text-error font-semibold">{p.contactar_hoy ? "Está en el Paso 1: llamarlo hoy" : `Ya llamado: ${p.contacto?.texto}`}</span>}
                          {!p.riesgo_vital && p.riesgo_inasistencia && <span className="block text-[13px] text-ambar font-semibold">Faltó 2 veces seguidas: confirmar asistencia por teléfono</span>}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
              {e.alternativa && (
                <div onClick={() => onVer(e.alternativa.id_paciente)} className="cursor-pointer border border-dashed border-outline rounded p-2 text-[14px] hover:bg-surface-container-low">
                  <span className="text-on-surface-variant text-[13px]">Si alguien no confirma, ofrecer la hora a:</span> <b>{e.alternativa.nombre_fantasia}</b>
                  <span className="block text-[13px]">Va después porque {e.alternativa.por_que_despues}.</span>
                </div>
              )}
            </Caja>
          ))}
          {b && b.especialidades.every((e) => !e.asignaciones.length) && <Caja><p className="text-on-surface-variant">No hay box con agenda hoy{esp !== "Todas" && ` para ${esp}`}.</p></Caja>}
        </div>
      </div>

      {b?.mapa && (
        <details className="bg-surface-container-lowest border border-outline-variant rounded">
          <summary className="px-4 py-2.5 cursor-pointer text-[14px] font-semibold">Ver ocupación de los 20 box hoy</summary>
          <div className="p-2"><MapaBox mapa={b.mapa} dia={b.dia_agenda} esp={esp} setEsp={setEsp} /></div>
        </details>
      )}
    </div>
  );
}

// Médico con tiempo libre: le dice a quiénes atender, en orden, con hora sugerida y motivo.
function MedicoDisponible({ fecha, esApi, espInicial, onVer, onCambio, onAviso }) {
  const [esp, setEsp] = useState(espInicial && espInicial !== "Todas" ? espInicial : "Cardiología");
  const [modo, setModo] = useState("horario");
  const [desde, setDesde] = useState("14:00");
  const [hasta, setHasta] = useState("17:00");
  const [cupos, setCupos] = useState(5);
  const [r, setR] = useState(null);
  const [buscando, setBuscando] = useState(false);
  const [citados, setCitados] = useState({});
  const buscar = async () => {
    setBuscando(true); setCitados({});
    try { setR(await api.getDisponible(fecha, modo === "horario" ? { especialidad: esp, desde, hasta } : { especialidad: esp, cupos })); }
    catch (e) { onAviso({ titulo: "No se pudo buscar: " + e.message }); } finally { setBuscando(false); }
  };
  const marcar = async (p, resultado) => {
    try {
      await api.postContacto(p.id_paciente, { resultado, fecha_corte: fecha, nota: "Médico con horas libres",
        ...(resultado === "citado" && p.hora ? { hora: p.hora, hora_fin: p.hora_fin, id_box: `Consulta ${r.especialidad}` } : {}) });
      setCitados({ ...citados, [p.id_paciente]: resultado }); await onCambio();
    } catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); }
  };
  if (!esApi) return <Caja><p className="text-on-surface-variant">Esta función requiere conexión al servidor.</p></Caja>;
  const campo = "h-9 px-2 border border-outline-variant rounded bg-white";
  return (
    <div className="grid gap-5 lg:grid-cols-12 items-start">
      <Caja titulo="¿Tiene horas libres hoy?" className="lg:col-span-4">
        <p className="text-[13px] text-on-surface-variant mb-3">Indique su especialidad y su tiempo disponible. Se proponen los pacientes de la lista que más lo necesitan, sin repetir a quienes ya tienen hora hoy en un box.</p>
        <div className="space-y-3 text-[14px]">
          <Filtro label="Especialidad">
            <select value={esp} onChange={(e) => setEsp(e.target.value)} className={campo}>{ESPECIALIDADES.filter((e) => e !== "Todas").map((e) => <option key={e}>{e}</option>)}</select>
          </Filtro>
          <div className="flex gap-1">
            {[["horario", "Por horario"], ["cantidad", "Por cantidad"]].map(([k, t]) => (
              <button key={k} onClick={() => setModo(k)} className={`flex-1 h-9 rounded border font-semibold ${modo === k ? "bg-primary text-on-primary border-primary" : "border-outline-variant"}`}>{t}</button>
            ))}
          </div>
          {modo === "horario" ? (
            <div className="grid grid-cols-2 gap-2">
              <Filtro label="Desde"><input type="time" value={desde} onChange={(e) => setDesde(e.target.value)} className={campo} /></Filtro>
              <Filtro label="Hasta"><input type="time" value={hasta} onChange={(e) => setHasta(e.target.value)} className={campo} /></Filtro>
            </div>
          ) : (
            <Filtro label="¿Cuántos pacientes puede ver?"><input type="number" min={1} max={40} value={cupos} onChange={(e) => setCupos(e.target.value)} className={campo} /></Filtro>
          )}
          <button disabled={buscando} onClick={buscar} className="w-full py-2.5 rounded bg-primary text-on-primary font-semibold disabled:opacity-50 flex items-center justify-center gap-1">
            <Icono n="person_search" className="text-[18px]" />{buscando ? "Buscando…" : "¿A quiénes atiendo?"}</button>
        </div>
      </Caja>

      <div className="lg:col-span-8">
        {!r ? <Caja><p className="text-on-surface-variant">Complete el formulario para ver a quiénes atender.</p></Caja> : (
          <Caja titulo={`${r.pacientes.length} paciente${r.pacientes.length !== 1 ? "s" : ""} para atender · ${r.especialidad}`}
            accion={<button onClick={() => window.print()} className="text-[13px] text-primary font-semibold flex items-center gap-1"><Icono n="print" className="text-[16px]" />Imprimir</button>}>
            <p className="text-[14px] mb-3">
              {modo === "horario" ? <>Con su horario de <b>{desde} a {hasta}</b> y consultas de <b>~{r.duracion_min} min</b> ({r.duracion_fuente} de {r.especialidad}) alcanza a ver <b>{r.cupos} pacientes</b>.</>
                : <>Los <b>{r.cupos} pacientes</b> que más lo necesitan hoy.</>}
              {r.excluidos_con_hora_hoy > 0 && <span className="text-on-surface-variant"> Se omiten {r.excluidos_con_hora_hoy} que ya tienen hora hoy en un box.</span>}
            </p>
            <ol className="divide-y divide-outline-variant/60">
              {r.pacientes.map((p, i) => (
                <li key={p.id_paciente} className={`py-2.5 flex gap-3 ${p.riesgo_vital ? "bg-error-container/30 -mx-4 px-4" : ""}`}>
                  <span className="shrink-0 w-28 text-[15px] font-semibold text-primary-container">{p.hora ? `${p.hora} – ${p.hora_fin} h` : `${i + 1}.`}</span>
                  <span className="shrink-0"><Prioridad cat={p.categoria} /></span>
                  <div className="flex-1 text-[14px]">
                    <button onClick={() => onVer(p.id_paciente)} className="font-semibold hover:underline text-left">{p.nombre_fantasia}</button>
                    <span className="text-[13px] text-on-surface-variant"> · {p.diagnostico_texto} · {p.dias_espera} días esperando</span>
                    <div className="text-[13px]">Por qué: {p.motivo}</div>
                    {p.riesgo_inasistencia && <div className="text-[13px] text-ambar font-semibold">Faltó 2 veces seguidas: confirmar por teléfono</div>}
                    <div className="flex gap-1 mt-1.5 text-[12px]">
                      {citados[p.id_paciente]
                        ? <span className="text-hlf font-semibold flex items-center gap-1"><Icono n="task_alt" className="text-[14px]" />{citados[p.id_paciente] === "citado" ? "Citado" : "No contesta: llamar a una reserva"}</span>
                        : <>
                          <button onClick={() => marcar(p, "citado")} className="px-2 py-1 rounded border border-primary text-primary font-semibold">Citar</button>
                          <button onClick={() => marcar(p, "no_contesta")} className="px-2 py-1 rounded border border-outline-variant text-on-surface-variant font-semibold">No contesta</button>
                        </>}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
            {r.reservas.length > 0 && (
              <div className="mt-3 rounded border border-dashed border-outline p-3 text-[14px]">
                <div className="font-semibold mb-1">Reservas, si alguien no contesta:</div>
                <ol className="space-y-1">
                  {r.reservas.map((p) => (
                    <li key={p.id_paciente}><button onClick={() => onVer(p.id_paciente)} className="hover:underline font-semibold">{p.nombre_fantasia}</button>
                      <span className="text-[13px] text-on-surface-variant"> · {p.diagnostico_texto} · va después porque {p.por_que_despues}</span></li>
                  ))}
                </ol>
              </div>
            )}
          </Caja>
        )}
      </div>
    </div>
  );
}

// Mapa de todos los box del día: especialidad, cupos usados/libres y sobretiempo (agenda_box del registro).
function MapaBox({ mapa, dia, esp, setEsp }) {
  const activos = mapa.filter((x) => x.especialidad);
  const libres = activos.reduce((s, x) => s + x.libres, 0);
  const capacidad = activos.reduce((s, x) => s + x.capacidad, 0);
  return (
    <Caja titulo={`Box del día · ${fmt(dia)}`} accion={
      <span className="text-[13px] text-on-surface-variant">{activos.length} de {mapa.length} box con agenda · <b className="text-hlf">{libres}</b> horas libres de {capacidad}</span>}>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-10 gap-2">
        {mapa.map((x) => {
          if (!x.especialidad) return (
            <div key={x.id_box} className="rounded border border-dashed border-outline-variant p-2 text-on-surface-variant">
              <div className="font-semibold text-[14px]">{x.id_box.replace("BOX-", "Box ")}</div>
              <div className="text-[12px]">Sin agenda hoy</div>
            </div>
          );
          const pct = Math.round(((x.usados + (x.citadas || 0)) / x.capacidad) * 100);
          const sel = esp === x.especialidad;
          return (
            <button key={x.id_box} onClick={() => setEsp(sel ? "Todas" : x.especialidad)} title={`${x.especialidad} · ${x.bloque} · ${x.usados}/${x.capacidad} cupos usados · sobretiempo ${x.sobretiempo_min} min`}
              className={`text-left rounded border p-2 transition ${sel ? "border-primary ring-2 ring-primary/30 bg-primary/5" : "border-outline-variant hover:bg-surface-container-low"}`}>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-[14px]">{x.id_box.replace("BOX-", "Box ")}</span>
                <span className={`text-[12px] font-bold ${x.libres ? "text-hlf" : "text-on-surface-variant"}`}>{x.libres ? `${x.libres} hora${x.libres !== 1 ? "s" : ""} libre${x.libres !== 1 ? "s" : ""}` : "completo"}</span>
              </div>
              <div className="text-[12px] text-on-surface-variant truncate">{x.especialidad}</div>
              <div className="h-1.5 rounded bg-hlf-claro overflow-hidden mt-1.5" aria-label={`${pct}% ocupado`}>
                <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
              </div>
              <div className="flex justify-between text-[11px] text-on-surface-variant mt-1">
                <span>{x.usados + (x.citadas || 0)} de {x.capacidad} ocupadas{x.citadas ? ` (${x.citadas} citada${x.citadas > 1 ? "s" : ""} hoy)` : ""}</span>
                {x.sobretiempo_min > 0 && <span title="Sobretiempo del bloque">+{x.sobretiempo_min} min</span>}
              </div>
            </button>
          );
        })}
      </div>
      <p className="text-[12px] text-on-surface-variant mt-2">Barra azul: horas ya ocupadas · verde: horas libres, que se proponen en el Paso 2. Haga clic en un box para ver solo su especialidad.</p>
    </Caja>
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
          <li><b>Orden dentro de cada prioridad</b> (MINSAL, Ord. 536 del 21-03-2025): criterio médico, grupos de especial protección (sin datos en este registro), antigüedad en lista mayor a 1 año y, finalmente, fecha de ingreso. Como criterio médico se usa además el <b>puntaje LACE</b> (más puntos, antes).</li>
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
      <Caja titulo="Puntaje de riesgo LACE (puntos publicados)">
        <p className="mb-2">Índice validado para riesgo de muerte o reingreso no planificado (van Walraven et al., <i>CMAJ</i> 2010;182(6):551-7). Estadístico C 0,68–0,71 en Ontario.</p>
        <table className="w-full text-[14px]">
          <tbody className="divide-y divide-outline-variant/60">
            <tr><td className="py-1 font-semibold w-8">L</td><td>Días de estada: &lt;1 = 0 · 1 = 1 · 2 = 2 · 3 = 3 · 4–6 = 4 · 7–13 = 5 · ≥14 = 7 <span className="text-on-surface-variant">(sin dato en el registro → 0)</span></td></tr>
            <tr><td className="py-1 font-semibold">A</td><td>Ingreso de urgencia = 3 (hospitalización en los últimos 6 meses)</td></tr>
            <tr><td className="py-1 font-semibold">C</td><td>Charlson: 0 = 0 · 1 = 1 · 2 = 2 · 3 = 3 · ≥4 = 5. Pesos: insuficiencia cardíaca 2 · enfermedad pulmonar crónica 2 · hepática leve 2 · diabetes sin complicaciones 1 (CIE-10 según Quan 2005)</td></tr>
            <tr><td className="py-1 font-semibold">E</td><td>Consultas en urgencia en 6 meses: 0–3 = mismo número · ≥4 = 4</td></tr>
          </tbody>
        </table>
        <p className="text-[13px] text-on-surface-variant mt-2">Validación en este registro (datos sintéticos): a más puntos, más eventos en los 90 días siguientes (LACE 0: 11% · 2: 14% · 3: 17%), con discriminación baja (AUC 0,54). Debe recalibrarse con datos reales del HLF.</p>
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
