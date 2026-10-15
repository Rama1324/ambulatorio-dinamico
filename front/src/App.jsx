import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as api from "./api";
import { descargarExcel } from "./excel";

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
  riesgo_vital: "Descompensación grave: evaluar", prioridad_inicial: "Priorización de la interconsulta", evento: "Evento posterior a la interconsulta",
  tabla_oficial: "Tabla de priorización HLF", dias_espera: "Tiempo de espera", ges: "Garantía GES", medicion: "Última medición",
  lace: "Puntaje LACE (experimental)",
};
const TIPO_EVENTO = { visita_urgencia: "Urgencia", hospitalizacion: "Hospitalización", examen_alterado: "Examen alterado", cambio_farmaco: "Cambio de fármaco", control_aps: "Control APS" };
const POR_PAGINA = 25;
const FILTRO_CAT = { todas: "Todas", alta: "Alta", media: "Media", baja: "Baja", vital: "Descompensación grave: revisar", ges: "GES: verificar plazo" };
const FILTRO_GESTION = { todos: "Todos", pendiente_revision: "Pendiente de revisión", pendiente_contacto: "Pendiente de contacto",
  pendiente_cita: "Pendiente de cita", cita_reservada: "Cita reservada", atendido: "Atendido: registrar egreso",
  sin_responsable: "Sin responsable", seguimiento_vencido: "Seguimiento vencido" };
const ESTILO_GESTION = { pendiente_revision: "text-ambar", pendiente_contacto: "text-ambar", pendiente_cita: "text-on-surface",
  cita_reservada: "text-hlf", atendido: "text-hlf" };
// Prioridad propuesta por el sistema vs. confirmada por el equipo (quién y cuándo)
function EstadoPrioridad({ p }) {
  const r = p.revision;
  if (p.estado_revision === "confirmado") return <div className="text-[11px] text-verde mt-0.5 whitespace-nowrap" title={r && `${r.usuario} · ${fmt(r.fecha)}`}>✓ confirmada</div>;
  if (p.estado_revision === "ajustado") return <div className="text-[11px] text-verde mt-0.5 whitespace-nowrap" title={r && `${r.usuario} · ${fmt(r.fecha)}: ${r.motivo}`}>✓ ajustada</div>;
  if (p.estado_revision === "requiere_revision") return <div className="text-[11px] text-ambar mt-0.5 whitespace-nowrap">revisar de nuevo</div>;
  return p.categoria_sistema !== p.prioridad_inicial
    ? <div className="text-[11px] text-ambar mt-0.5 whitespace-nowrap" title={`La SIC tenía prioridad ${p.prioridad_inicial}`}>propuesta del sistema</div>
    : <div className="text-[11px] text-on-surface-variant mt-0.5 whitespace-nowrap">asignada en la SIC</div>;
}

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

// Tema claro/oscuro (del PR #1): por defecto sigue al sistema; el botón lo fija y se recuerda en este navegador.
function useTema() {
  const [tema, setTema] = useState(() => { try { return localStorage.getItem("hlf-tema"); } catch { return null; } });
  useEffect(() => {
    if (tema) document.documentElement.dataset.theme = tema; else delete document.documentElement.dataset.theme;
    try { if (tema) localStorage.setItem("hlf-tema", tema); else localStorage.removeItem("hlf-tema"); } catch { /* sin almacenamiento */ }
  }, [tema]);
  const oscuro = tema ? tema === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  return [oscuro, () => setTema(oscuro ? "light" : "dark")];
}

export default function App() {
  const [oscuro, cambiarTema] = useTema();
  const [info, setInfo] = useState(null);
  useEffect(() => { api.cargarInfo().then(setInfo); }, []);
  const fechas = api.fechas();
  const esApi = api.MODO === "api";
  const [demo, setDemo] = useState(!esApi);
  const [iFechaSel, setIFecha] = useState(null);
  const iFecha = iFechaSel ?? fechas.length - 1;
  const [esp, setEsp] = useState("Todas");
  const [vista, setVista] = useState("simple");  // página principal: la lista de espera simple, como una planilla
  const [data, setData] = useState(null);
  const [sel, setSel] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [destacado, setDestacado] = useState(null);
  const [error, setError] = useState(null);
  const [busca, setBusca] = useState("");
  const [filtroCat, setFiltroCat] = useState("todas");
  const [filtroGestion, setFiltroGestion] = useState("todos");
  const [esperaLarga, setEsperaLarga] = useState(false);
  const [diasEspera, setDiasEspera] = useState(365);
  const [actualizando, setActualizando] = useState(false);
  const [pagina, setPagina] = useState(0);
  const [nuevo, setNuevo] = useState(false);
  const [usuario, setUsuarioLocal] = useState(api.getUsuario());
  const fecha = demo ? fechas[iFecha] : fechas[fechas.length - 1];

  const cargar = useCallback(async () => {
    if (!info) return;
    setActualizando(true);
    try { setError(null); setData(await api.getPacientes(fecha, esp === "Todas" ? null : esp)); }
    catch (e) { setError(e.message); } finally { setActualizando(false); }
  }, [fecha, esp, info]);
  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    if (!sel) return setDetalle(null);
    api.getPaciente(sel, fecha).then(setDetalle).catch(() => setDetalle(null));
  }, [sel, fecha, data]);
  useEffect(() => setPagina(0), [busca, filtroCat, filtroGestion, esperaLarga, diasEspera, esp]);
  // al seleccionar (p. ej. un paciente recién ingresado) saltar a la página donde está
  useEffect(() => {
    const i = filtrados.findIndex((p) => p.id_paciente === sel);
    if (i >= 0) setPagina(Math.floor(i / POR_PAGINA));
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtrados = useMemo(() => {
    if (!data) return [];
    const q = busca.trim().toLowerCase();
    const g = (p) => p.gestion || {};
    return data.pacientes.filter((p) =>
      (filtroCat === "todas" || (filtroCat === "vital" ? p.contactar_hoy : filtroCat === "ges" ? p.ges?.vencida : p.categoria === filtroCat)) &&
      (filtroGestion === "todos" || (filtroGestion === "sin_responsable" ? !g(p).responsable
        : filtroGestion === "seguimiento_vencido" ? g(p).seguimiento_vencido : g(p).estado === filtroGestion)) &&
      (!esperaLarga || p.dias_espera >= (Number(diasEspera) || 0)) &&
      (!q || p.nombre_fantasia.toLowerCase().includes(q) || p.id_paciente.toLowerCase().includes(q) || p.diagnostico_texto.toLowerCase().includes(q)));
  }, [data, busca, filtroCat, filtroGestion, esperaLarga, diasEspera]);
  const hayFiltros = busca || filtroCat !== "todas" || filtroGestion !== "todos" || esperaLarga || esp !== "Todas";
  const limpiarFiltros = () => { setBusca(""); setFiltroCat("todas"); setFiltroGestion("todos"); setEsperaLarga(false); setEsp("Todas"); };
  const verLista = (cambios) => { limpiarFiltros(); cambios?.(); setVista("lista"); };

  const mostrarAviso = (a) => { setAviso(a); setTimeout(() => setAviso(null), 6000); };
  const abrir = (id) => { setSel(id); setVista("lista"); };

  if (!data) return <div className="p-10 text-lg">{error ? `No se pudo cargar la lista: ${error}` : "Cargando lista de espera…"}</div>;
  const paciente = sel && data.pacientes.find((p) => p.id_paciente === sel);
  const vitales = data.pacientes.filter((p) => p.riesgo_vital);
  const porContactar = vitales.filter((p) => p.contactar_hoy);
  const atrasadas = vitales.filter((p) => p.evaluacion?.estado === "atrasada").length;
  const altas = data.pacientes.filter((p) => p.categoria === "alta").length;
  const gesVenc = data.pacientes.filter((p) => p.ges?.vencida).length;
  const tiempoReal = info?.modo === "tiempo_real" && !demo;
  const pendientes = data.pacientes.filter((p) => p.gestion?.estado === "pendiente_revision").length;
  const masDeUnAnio = data.pacientes.filter((p) => p.dias_espera > 365).length;
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
            {esApi && <label className="flex items-center gap-1.5 text-on-surface-variant" title="Queda registrado en cada acción (trazabilidad)">
              <Icono n="badge" className="text-[18px]" />
              <input value={usuario} onChange={(e) => { setUsuarioLocal(e.target.value); api.setUsuario(e.target.value); }} placeholder="Su nombre y cargo"
                className={`h-8 w-44 px-2 border rounded text-on-surface ${usuario.trim() ? "border-outline-variant" : "border-ambar bg-ambar-container/40"}`} />
            </label>}
            <span className="text-on-surface-variant border-l border-outline-variant pl-3">Lista al <b className="text-on-surface">{fmt(fecha)}</b></span>
            <button onClick={cambiarTema} aria-label={oscuro ? "Usar tema claro" : "Usar tema oscuro"} title={oscuro ? "Tema claro" : "Tema oscuro"}
              className="w-9 h-9 flex items-center justify-center rounded border border-outline-variant text-on-surface-variant hover:text-on-surface">
              <Icono n={oscuro ? "light_mode" : "dark_mode"} className="text-[20px]" /></button>
            <label className="flex items-center gap-1.5 text-on-surface-variant cursor-pointer select-none border-l border-outline-variant pl-3">
              <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} className="accent-primary" />Explorar fechas anteriores
            </label>
          </div>
        </div>
        <nav className="max-w-[1400px] mx-auto px-6 flex gap-6 text-[14px]">
          {[["simple", "Lista de espera", null], ["lista", "Lista detallada", null], ["hoy", "Alertas pendientes", porContactar.length], ["indicadores", "Indicadores", null], ["cargar", "Cargar datos", null], ["criterios", "Criterios", null]].map(([k, t, n]) => (
            <button key={k} onClick={() => setVista(k)}
              className={`py-2.5 border-b-2 -mb-px ${vista === k ? "border-primary text-primary font-semibold" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}>
              {t}{n ? <span className="ml-1.5 px-1.5 rounded-full bg-error text-on-error text-[12px] font-semibold">{n}</span> : null}
            </button>
          ))}
        </nav>
      </header>

      <div className="bg-surface-container-high border-b border-outline-variant">
        <div className="max-w-[1400px] mx-auto px-6 py-1.5 text-[13px] flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-semibold flex items-center gap-1"><Icono n="database" className="text-[16px]" />Datos sintéticos de demostración: no son pacientes reales</span>
          <span className="text-on-surface-variant">·</span>
          <span>{tiempoReal ? <>Lista calculada al <b>{fmt(fecha)}</b> (hoy en Chile) · registro del hospital al <b>{fmt(info?.registro_al || "2026-10-13")}</b>
            {info?.datos_hasta && <> (último dato clínico: {fmt(info.datos_hasta)})</>} + lo registrado en la herramienta</>
            : <>Fecha anterior: lista calculada al <b>{fmt(fecha)}</b>, solo con registros hasta esa fecha.</>}</span>
        </div>
      </div>

      {demo && (
        <div className="bg-ambar-container/60 border-b border-ambar/30">
          <div className="max-w-[1400px] mx-auto px-6 py-2 flex flex-wrap items-center gap-4 text-[13px]">
            <span className="font-semibold text-ambar flex items-center gap-1"><Icono n="history" className="text-[18px]" />Explorando fechas anteriores{!esApi && " (datos precalculados, sin API)"}</span>
            <label className="flex items-center gap-2 flex-1 min-w-[280px]">
              Ver la lista como estaba el <b>{fmt(fechas[iFecha])}</b>
              <input type="range" min={0} max={fechas.length - 1} value={iFecha} onChange={(e) => setIFecha(+e.target.value)} className="flex-1 accent-ambar" />
            </label>
            <span className="text-on-surface-variant">Solo se usan registros con fecha anterior o igual.</span>
          </div>
        </div>
      )}

      <AnimatePresence>
        {aviso && (
          <motion.div initial={{ y: -8, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed top-4 left-1/2 -translate-x-1/2 z-50 bg-on-surface text-background px-4 py-2.5 rounded shadow-lg text-[14px] flex items-center gap-2">
            <Icono n="check_circle" className="text-[20px]" />{aviso.titulo}
            {aviso.antes != null && <span className="opacity-90">· posición {aviso.antes} → <b>{aviso.despues}</b>{aviso.cat && ` · prioridad ${ETIQUETA[aviso.cat]}`}</span>}
          </motion.div>
        )}
      </AnimatePresence>

      <main className="flex-1 max-w-[1400px] w-full mx-auto px-6 py-5">
        {error && <div className="bg-error-container text-on-error-container p-3 mb-4 rounded">{error}</div>}

        {vista !== "simple" && <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-5">
          <Indicador n={data.total} t="Pacientes en espera · ver todos" onClick={() => verLista()} />
          <Indicador n={porContactar.length} t={`Descompensación grave: revisar prioridad${atrasadas ? ` (${atrasadas} con más de 72 h)` : ""}`} tono={porContactar.length ? "rojo" : null} onClick={() => setVista("hoy")} />
          <Indicador n={altas} t="Prioridad alta" onClick={() => verLista(() => setFiltroCat("alta"))} />
          <Indicador n={pendientes} t="Pendientes de revisión del especialista" tono={pendientes ? "ambar" : null} onClick={() => verLista(() => setFiltroGestion("pendiente_revision"))} />
          <Indicador n={masDeUnAnio} t="Esperan más de 1 año" onClick={() => verLista(() => { setEsperaLarga(true); setDiasEspera(365); })} />
          <Indicador n={gesVenc} t="GES: posible incumplimiento, verificar" onClick={() => verLista(() => setFiltroCat("ges"))} />
        </div>}

        {vista === "simple" && <ListaSimple data={data} fecha={fecha} esp={esp} setEsp={setEsp} actualizando={actualizando} onVer={abrir} />}

        {(vista === "hoy" || vista === "box") && <Hoy parte={vista} vitales={vitales} todosPacientes={data.pacientes} fecha={fecha} esp={esp} setEsp={setEsp} onVer={abrir} esApi={esApi} onCambio={cargar} onAviso={mostrarAviso} />}
        {vista === "criterios" && <Criterios />}
        {vista === "medico" && <MedicoDisponible fecha={fecha} esApi={esApi} espInicial={esp} onVer={abrir} onCambio={cargar} onAviso={mostrarAviso} />}
        {vista === "indicadores" && <Indicadores fecha={fecha} esApi={esApi} data={data} />}
        {vista === "cargar" && <CargarDatos esApi={esApi} onListo={async (r) => {
          await cargar();
          mostrarAviso({ titulo: `Datos cargados: ${r.resumen.pacientes_nuevos} pacientes nuevos, ${r.resumen.pacientes_actualizados} actualizados, ${r.resumen.eventos} eventos` });
        }} />}
        {vista === "lista" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            <div className={`${paciente ? "lg:col-span-7 xl:col-span-8" : "lg:col-span-12"} flex flex-col gap-4`}>
              <div className="bg-surface-container-lowest border border-outline-variant rounded p-3 flex flex-wrap items-end gap-3 text-[13px]">
                <Filtro label="Especialidad">
                  <select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select>
                </Filtro>
                <Filtro label="Buscar paciente">
                  <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nombre, ID o diagnóstico" className="h-9 px-2 w-56 border border-outline-variant rounded" />
                </Filtro>
                <Filtro label="Prioridad">
                  <select value={filtroCat} onChange={(e) => setFiltroCat(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">
                    {Object.entries(FILTRO_CAT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </Filtro>
                <Filtro label="Estado de gestión">
                  <select value={filtroGestion} onChange={(e) => setFiltroGestion(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">
                    {Object.entries(FILTRO_GESTION).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </Filtro>
                <label className="flex items-center gap-2 h-9 cursor-pointer select-none" title="Pacientes que llevan al menos esa cantidad de días en lista">
                  <input type="checkbox" checked={esperaLarga} onChange={(e) => setEsperaLarga(e.target.checked)} className="w-4 h-4 accent-primary" />Espera de
                  <input type="number" min={0} step={30} value={diasEspera} onChange={(e) => { setDiasEspera(e.target.value); setEsperaLarga(true); }} aria-label="Días mínimos de espera"
                    className="h-8 w-20 px-2 border border-outline-variant rounded" />días o más</label>
                {hayFiltros && <button onClick={limpiarFiltros} className="h-9 px-2 text-primary font-semibold flex items-center gap-1"><Icono n="filter_alt_off" className="text-[18px]" />Limpiar filtros</button>}
                <button onClick={() => exportarExcel(filtrados, fecha, { excluidos: data.excluidos, filtros: [["Especialidad", esp], ["Búsqueda", busca || "(ninguna)"],
                  ["Prioridad", FILTRO_CAT[filtroCat]], ["Estado de gestión", FILTRO_GESTION[filtroGestion]],
                  ["Espera mínima", esperaLarga ? `${diasEspera} días` : "(sin filtro)"]] })} className="ml-auto h-9 px-3 rounded border border-outline-variant bg-surface-container-lowest font-semibold flex items-center gap-1"><Icono n="download" className="text-[18px]" />Exportar a Excel</button>
                {esApi && <button onClick={() => setNuevo(true)} className="h-9 px-3 rounded bg-primary text-on-primary font-semibold flex items-center gap-1"><Icono n="person_add" className="text-[18px]" />Ingresar paciente</button>}
              </div>
              {nuevo && <NuevoPaciente fecha={fecha} onCerrar={() => setNuevo(false)} onListo={async (r) => {
                setNuevo(false); limpiarFiltros(); await cargar(); setSel(r.id_paciente);
                mostrarAviso({ titulo: `${r.paciente?.nombre_fantasia} ingresado a la lista`, despues: r.paciente?.posicion, antes: "—", cat: r.paciente?.categoria });
              }} />}

              <section className="bg-surface-container-lowest border border-outline-variant rounded relative" aria-busy={actualizando}>
                {actualizando && <div className="absolute inset-x-0 top-0 z-20 flex justify-center pt-12 pointer-events-none">
                  <span className="bg-on-surface text-background text-[13px] px-3 py-1.5 rounded shadow flex items-center gap-1"><Icono n="progress_activity" className="text-[16px] animate-spin" />Actualizando…</span></div>}
                <table className={`w-full text-left border-collapse text-[14px] ${actualizando ? "opacity-40 pointer-events-none" : ""}`}>
                  <thead className="sticky top-0 z-10">
                    <tr className="bg-surface-container-low text-[13px] text-on-surface-variant border-b border-outline-variant">
                      <th className="py-2 px-3 font-semibold w-14">N°</th><th className="py-2 px-2 font-semibold">Prioridad</th>
                      <th className="py-2 px-3 font-semibold">Paciente / diagnóstico</th><th className="py-2 px-3 font-semibold text-right">Espera</th>
                      <th className="py-2 px-3 font-semibold">Estado de gestión</th><th className="py-2 px-3 font-semibold">Próxima acción · responsable</th>
                      <th className="py-2 px-2"><span className="sr-only">Detalle</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    <AnimatePresence initial={false}>
                      {pag.map((p) => {
                        const delta = p.posicion_anterior ? p.posicion_anterior - p.posicion : 0;
                        const activo = sel === p.id_paciente;
                        const g = p.gestion || {};
                        return (
                          <motion.tr key={p.id_paciente} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                            transition={{ type: "spring", stiffness: 300, damping: 32 }} onClick={() => setSel(p.id_paciente)}
                            tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSel(p.id_paciente); } }}
                            aria-selected={activo} aria-label={`${p.nombre_fantasia}, N° ${p.posicion}, ${p.dias_espera} días de espera`}
                            className={`cursor-pointer border-b border-outline-variant/60 ${activo ? "bg-primary/10 outline outline-2 -outline-offset-2 outline-primary" : destacado === p.id_paciente ? "bg-ambar-container/60" : "hover:bg-surface-container-low"}`}>
                            <td className={`py-2 px-3 align-top ${p.riesgo_vital ? "border-l-4 border-l-error" : "border-l-4 border-l-transparent"}`}>
                              <div className="font-semibold">{p.posicion}</div>
                              {p.ajuste_manual && p.posicion_sistema !== p.posicion && <div className="text-[11px] text-on-surface-variant whitespace-nowrap" title="Posición que le daban las reglas">sistema: {p.posicion_sistema}</div>}
                              {demo && delta !== 0 && <div className={`text-[12px] ${delta > 0 ? "text-error" : "text-on-surface-variant"}`}>{delta > 0 ? `▲ ${delta}` : `▼ ${-delta}`}</div>}
                            </td>
                            <td className="py-2 px-2 align-top"><Prioridad cat={p.categoria} /><EstadoPrioridad p={p} /></td>
                            <td className="py-2 px-3 align-top">
                              <div className="font-semibold">{p.nombre_fantasia} <span className="font-normal text-on-surface-variant text-[13px]">· {p.edad} años · {p.especialidad}</span></div>
                              <div className="text-[13px] text-on-surface-variant">{p.diagnostico_cie10} {p.diagnostico_texto}</div>
                              <div className="flex flex-wrap gap-1 mt-0.5">
                                {p.contactar_hoy && <Marca tono="rojo" title={`Descompensación grave del ${fmt(p.evaluacion?.fecha_evento)}: su prioridad debe revisarse dentro de 72 h desde que el evento llegó al sistema`}>
                                  {p.evaluacion?.estado === "atrasada" ? `Revisión atrasada · ${p.evaluacion.dias_en_revision} d` : "Revisar prioridad ≤ 72 h"}</Marca>}
                                {p.riesgo_vital && !p.contactar_hoy && <Marca tono="azul" title={p.evaluacion?.cierre?.texto}>Prioridad revisada</Marca>}
                                {!p.riesgo_vital && p.estado_clinico === "descompensado" && <Marca tono="rojo">Descompensado</Marca>}
                                {p.ajuste_manual && <Marca tono="azul" title={`${p.ajuste_manual.motivo_texto}: ${p.ajuste_manual.explicacion} (${p.ajuste_manual.usuario})`}>Ajuste manual</Marca>}
                                {p.ajuste_manual_vencido && <Marca tono="ambar" title={`Evento nuevo: ${p.ajuste_manual_vencido.vencido_por}`}>Ajuste sin efecto: revisar</Marca>}
                                {p.grupo_proteccion && <Marca tono="azul">{p.grupo_proteccion}</Marca>}
                                {p.estado_clinico === "estabilizado" && <Marca>Estabilizado</Marca>}
                                {p.ges?.vencida && <Marca tono="azul" title={`GES N°${p.ges.problema}: plazo ${p.ges.plazo_dias} días desde la derivación. Se calcula desde el ingreso a la lista: verificar el hito real.`}>GES: verificar</Marca>}
                                {p.riesgo_inasistencia && <Marca tono="ambar" title="2 inasistencias consecutivas (causal 8)">2 inasistencias</Marca>}
                              </div>
                            </td>
                            <td className="py-2 px-3 align-top text-right whitespace-nowrap">
                              <div className={`text-[17px] font-bold leading-tight ${p.dias_espera > 365 ? "text-error" : ""}`}>{p.dias_espera} días</div>
                              <div className="text-[12px] text-on-surface-variant">desde {fmt(p.fecha_ingreso_lista)}</div>
                            </td>
                            <td className="py-2 px-3 align-top text-[13px]">
                              <div className={`font-semibold ${ESTILO_GESTION[g.estado] || ""}`}>{g.texto || "—"}</div>
                              {g.motivo_texto && <div className="text-on-surface-variant">Motivo: {g.motivo_texto}</div>}
                            </td>
                            <td className="py-2 px-3 align-top text-[13px]">
                              <div>{g.proxima_accion || "—"}</div>
                              <div className={g.responsable ? "text-on-surface-variant" : "text-ambar"}>{g.responsable || "Sin responsable"}
                                {g.seguimiento && <span className={g.seguimiento_vencido ? "text-error font-semibold" : ""}> · {g.seguimiento_vencido ? "seguimiento vencido" : "seguimiento"} {fmt(g.seguimiento)}</span>}</div>
                            </td>
                            <td className="py-2 px-2 align-top text-right">
                              <button onClick={(e) => { e.stopPropagation(); setSel(p.id_paciente); }} className="text-[13px] text-primary font-semibold whitespace-nowrap hover:underline">Ver detalle</button>
                            </td>
                          </motion.tr>
                        );
                      })}
                    </AnimatePresence>
                  </tbody>
                </table>
                {filtrados.length === 0 && <p className="p-6 text-on-surface-variant">No hay pacientes con esos filtros.</p>}
                <div className="px-3 py-2 flex items-center justify-between text-[13px] text-on-surface-variant bg-surface-container-low">
                  <span>{actualizando ? "Actualizando…" : `${filtrados.length} pacientes`} · orden: prioridad, descompensación grave, grupo de protección, más de 1 año en espera, LACE (desempate experimental), fecha de ingreso, ajustes manuales</span>
                  <div className="flex items-center gap-2">
                    <button disabled={pagina === 0} onClick={() => setPagina(pagina - 1)} className="px-2 py-1 border border-outline-variant rounded bg-surface-container-lowest disabled:opacity-40">Anterior</button>
                    <span>{pagina + 1} / {paginas}</span>
                    <button disabled={pagina >= paginas - 1} onClick={() => setPagina(pagina + 1)} className="px-2 py-1 border border-outline-variant rounded bg-surface-container-lowest disabled:opacity-40">Siguiente</button>
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

            {paciente && <aside className="lg:col-span-5 xl:col-span-4 lg:sticky lg:top-4 flex flex-col gap-3 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:overflow-x-hidden" aria-label="Detalle del paciente">
              <button onClick={() => setSel(null)} className="self-end text-[13px] text-on-surface-variant hover:text-on-surface flex items-center gap-1"><Icono n="close" className="text-[18px]" />Cerrar detalle</button>
              <Ficha key={paciente.id_paciente} p={paciente} total={data.total} detalle={detalle} fecha={fecha} esApi={esApi} demo={demo} onCambio={cargar} onAviso={mostrarAviso}
                onDestacar={(id) => { setDestacado(id); setTimeout(() => setDestacado(null), 3000); }} />
            </aside>}
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
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest w-full";
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

// Excel (.xlsx) de la lista tal como se está viendo (mismos filtros), con el fundamento de cada paciente,
// los ajustes manuales, los egresados y los filtros usados. Ver src/excel.js.
const EVAL_TXT = { pendiente: "Pendiente (≤ 72 h)", atrasada: "Atrasada (> 72 h)", evaluada: "Evaluada" };
const REV_TXT = { pendiente: "Pendiente", confirmado: "Confirmada", ajustado: "Ajustada", requiere_revision: "Requiere nueva revisión" };
function exportarExcel(pacientes, fecha, { excluidos = [], filtros = [] } = {}) {
  const lista = [["N°", "N° en su especialidad", "Prioridad", "Prioridad inicial (SIC)", "Paciente", "ID", "Edad", "Sexo", "Comuna", "Especialidad",
    "CIE-10", "Diagnóstico", "Fecha ingreso", "Días de espera", "Más de 1 año", "Estado clínico", "Descompensación grave: evaluación",
    "Días desde el evento", "Revisión de la prioridad", "Revisión sugerida por", "Ajuste manual", "Posición según el sistema", "GES: verificar plazo",
    "2 inasistencias seguidas", "LACE (experimental)"],
    ...pacientes.map((p) => [p.posicion, p.posicion_especialidad ?? "", ETIQUETA[p.categoria], p.prioridad_inicial, p.nombre_fantasia, p.id_paciente,
      p.edad, p.sexo, p.comuna, p.especialidad, p.diagnostico_cie10, p.diagnostico_texto, fmt(p.fecha_ingreso_lista), p.dias_espera,
      p.antiguedad_mayor_1_anio ? "Sí" : "", (p.estado_clinico || "").replace("_", " "), p.riesgo_vital ? EVAL_TXT[p.evaluacion?.estado] || "Pendiente" : "",
      p.evaluacion?.dias_desde_evento ?? "", REV_TXT[p.estado_revision] || p.estado_revision,
      [...new Set((p.revision_sugerida || []).map((s) => s.motivo))].join("; "),
      p.ajuste_manual ? `N° ${p.ajuste_manual.posicion} · ${p.ajuste_manual.motivo_texto}` : p.ajuste_manual_vencido ? "Sin efecto por evento nuevo" : "",
      p.posicion_sistema ?? "", p.ges?.vencida ? `GES N°${p.ges.problema} ${p.ges.nombre}` : "", p.riesgo_inasistencia ? "Sí" : "", p.lace?.total ?? ""])];
  const fundamento = [["N°", "Paciente", "ID", "Factor", "Detalle", "Fuente"],
    ...pacientes.flatMap((p) => p.razones.map((r) => [p.posicion, p.nombre_fantasia, p.id_paciente, FACTOR[r.factor] || r.factor, r.valor, r.fuente]))];
  const ajustes = [["N°", "Paciente", "ID", "Especialidad", "Movido al N°", "El sistema lo ponía en", "Motivo", "Explicación", "Responsable", "Fecha"],
    ...pacientes.filter((p) => p.ajuste_manual).map((p) => { const a = p.ajuste_manual;
      return [p.posicion, p.nombre_fantasia, p.id_paciente, a.especialidad, a.posicion, a.posicion_anterior, a.motivo_texto, a.explicacion, a.usuario, fmt(a.fecha)]; })];
  const egresados = [["Paciente", "ID", "Especialidad", "Motivo", "Fecha"],
    ...excluidos.map((e) => [e.nombre_fantasia || e.id_paciente, e.id_paciente, e.especialidad, e.motivo === "fallecido" ? "Fallecimiento (causal 9)" : "Atendido en consulta nueva", fmt(e.fecha)])];
  const info = [["Dato", "Valor"], ["Lista al", fmt(fecha)], ["Pacientes exportados", pacientes.length], ...filtros,
    ["Generado por", api.getUsuario() || "(sin nombre)"], ["Generado el", new Date().toLocaleString("es-CL")],
    ["Datos", "Sintéticos de demostración: no son pacientes reales"],
    ["Criterio", "Tabla de priorización SSMSO 2025 (HLF) y orden MINSAL Ord. 536/2025. La herramienta propone; el equipo clínico decide."]];
  descargarExcel(`lista_espera_HLF_${fecha}.xlsx`, [{ nombre: "Lista de espera", filas: lista }, { nombre: "Fundamento", filas: fundamento },
    { nombre: "Ajustes manuales", filas: ajustes }, { nombre: "Egresados", filas: egresados }, { nombre: "Filtros e información", filas: info }]);
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
        {p.contactar_hoy && <div className="mt-3 p-2.5 rounded bg-error-container text-on-error-container text-[14px] flex gap-2"><Icono n="call" className="text-[20px]" /><span>
          <b>Descompensación grave: revisar su prioridad.</b> Evento del {fmt(p.evaluacion?.fecha_evento)}, en el sistema desde el {fmt(p.evaluacion?.llego_al_sistema)}.
          {p.evaluacion?.estado === "atrasada" ? <b> Atrasada: pasaron más de 72 h sin revisión.</b> : " Plazo: 72 h."} No hay registro posterior de estabilización ni de evaluación; el especialista decide.</span></div>}
        {p.riesgo_vital && !p.contactar_hoy && p.evaluacion?.cierre && <div className="mt-3 p-2.5 rounded bg-hlf-claro text-hlf text-[14px] flex gap-2"><Icono n="task_alt" className="text-[20px]" /><span>
          <b>Prioridad revisada: {p.evaluacion.cierre.texto}</b>{p.evaluacion.cierre.responsable && ` · ${p.evaluacion.cierre.responsable}`}{p.decision?.seguimiento && ` · seguimiento ${fmt(p.decision.seguimiento)}`}</span></div>}
        {p.estado_revision === "requiere_revision" && <div className="mt-2 p-2.5 rounded bg-ambar-container text-ambar text-[14px] flex gap-2"><Icono n="rate_review" className="text-[20px]" /><span><b>Requiere nueva revisión:</b> {p.revision_vencida_por} después de la última revisión.</span></div>}
        {p.estado_revision === "pendiente" && p.revision_sugerida?.length > 0 && <div className="mt-2 p-2.5 rounded bg-ambar-container/60 text-ambar text-[14px] flex gap-2"><Icono n="rate_review" className="text-[20px]" /><span><b>Revisión sugerida:</b> {[...new Set(p.revision_sugerida.map((s) => s.motivo))].join(" · ")}</span></div>}
        <dl className="mt-3 grid grid-cols-[130px_1fr] gap-y-1 text-[14px]">
          <dt className="text-on-surface-variant">Especialidad</dt><dd>{p.especialidad}</dd>
          <dt className="text-on-surface-variant">Diagnóstico</dt><dd>{p.diagnostico_cie10} · {p.diagnostico_texto}</dd>
          <dt className="text-on-surface-variant">Ingreso a lista</dt><dd>{fmt(p.fecha_ingreso_lista)} ({p.dias_espera} días)</dd>
          <dt className="text-on-surface-variant">Prioridad inicial</dt><dd className="capitalize">{p.prioridad_inicial}</dd>
          <dt className="text-on-surface-variant">N° en la lista</dt><dd>{p.posicion} de {total}</dd>
          <dt className="text-on-surface-variant">Prioridad</dt><dd><EstadoRevision p={p} /></dd>
          {p.gestion && <><dt className="text-on-surface-variant">Gestión</dt><dd><b className={ESTILO_GESTION[p.gestion.estado]}>{p.gestion.texto}</b>{p.gestion.motivo_texto && ` · ${p.gestion.motivo_texto}`}</dd>
            <dt className="text-on-surface-variant">Próxima acción</dt><dd>{p.gestion.proxima_accion}{p.gestion.seguimiento && <span className={p.gestion.seguimiento_vencido ? "text-error font-semibold" : ""}> · seguimiento {fmt(p.gestion.seguimiento)}{p.gestion.seguimiento_vencido && " (vencido)"}</span>}</dd>
            <dt className="text-on-surface-variant">Responsable</dt><dd className={p.gestion.responsable ? "" : "text-ambar"}>{p.gestion.responsable || "Sin responsable asignado"}</dd></>}
          {(p.grupo_proteccion || p.acg) && <><dt className="text-on-surface-variant">Riesgo social</dt><dd>{[p.grupo_proteccion && `Grupo ${p.grupo_proteccion}`, p.acg && `ACG ${p.acg}`].filter(Boolean).join(" · ")}</dd></>}
          {p.comorbilidades?.length > 0 && <><dt className="text-on-surface-variant">Comorbilidades</dt><dd>{p.comorbilidades.map((c) => c.nombre).join(", ")}</dd></>}
        </dl>
        {p.categoria !== p.categoria_sistema && <p className="mt-2 text-[13px] text-on-surface-variant">El sistema proponía prioridad {p.categoria_sistema}; el equipo clínico la cambió a {p.categoria}. Motivo: {p.revision?.motivo}</p>}
      </Caja>

      <div className="flex border-b border-outline-variant bg-surface-container-lowest rounded-t text-[14px] sticky top-0 z-10">
        {[["resumen", "Resumen"], ["gestion", "Gestión"], ["registrar", "Registrar"], ["puntaje", "Fundamento"], ["historia", "Historia"]].map(([k, t]) => (
          <button key={k} onClick={() => setTab(k)} className={`flex-1 py-2 border-b-2 -mb-px ${tab === k ? "border-primary text-primary font-semibold" : "border-transparent text-on-surface-variant"}`}>{t}</button>
        ))}
      </div>

      {tab === "resumen" && <>
      <Caja titulo="Cómo se decidió su lugar en la lista">
        <Camino p={p} total={total} />
      </Caja>
      </>}

      {tab === "gestion" && (esApi ? <>
        <GestionCaso p={p} fecha={fecha} onListo={async () => { await onCambio(); onDestacar(p.id_paciente); onAviso({ titulo: `${p.nombre_fantasia}: gestión actualizada` }); }} onAviso={onAviso} />
        {p.riesgo_vital && <DecisionClinica p={p} fecha={fecha} onListo={async (r) => { await onCambio(); onAviso({ titulo: `${p.nombre_fantasia}: ${r.decision.texto} (${r.decision.responsable})` }); }} onAviso={onAviso} />}
        <Contacto p={p} fecha={fecha} onListo={async (r) => { await onCambio(); onAviso({ titulo: `${p.nombre_fantasia}: ${r.contacto.texto}` }); }} onAviso={onAviso} />
        <AjusteManual p={p} fecha={fecha} onListo={async (r, quitar) => {
          await onCambio(); onDestacar(p.id_paciente);
          onAviso(quitar ? { titulo: `${p.nombre_fantasia}: ajuste manual deshecho, vuelve al orden del sistema` }
            : { titulo: `${p.nombre_fantasia} movido a mano`, antes: r.ajuste.posicion_anterior, despues: r.paciente?.posicion_especialidad });
        }} onAviso={onAviso} />
      </> : <Caja><p className="text-on-surface-variant text-[13px]">Gestionar pacientes requiere conexión al servidor.</p></Caja>)}

      {tab === "puntaje" && <>
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
      <Caja titulo="Puntaje LACE (experimental, solo desempate)">
        <BoletaLace lace={p.lace} />
      </Caja>
      </>}

      {tab === "resumen" && (esApi ? (
        <>
          <Caja titulo="Revisión de la prioridad (especialista)">
            <p className="text-[13px] text-on-surface-variant mb-2">¿Está de acuerdo con la prioridad {ETIQUETA[p.categoria].toLowerCase()} que propone el sistema? Su respuesta se usa para medir la concordancia (kappa).</p>
            <div className="flex gap-2">
              <button onClick={confirmar} disabled={cargando} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-50">Confirmar prioridad</button>
              <button onClick={() => setAjuste(ajuste ? null : { categoria: p.categoria, motivo: "" })} className="flex-1 py-2 rounded border border-primary text-primary font-semibold">Cambiar prioridad</button>
            </div>
            {ajuste && (
              <div className="mt-3 flex flex-col gap-2">
                <select value={ajuste.categoria} onChange={(e) => setAjuste({ ...ajuste, categoria: e.target.value })} className="h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">
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
                <select value={tipoEv} onChange={(e) => setTipoEv(e.target.value)} className="flex-1 h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">
                  {Object.entries(EVENTOS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
                <button onClick={() => registrarEvento(EVENTOS[tipoEv], "Evento simulado")} disabled={cargando} className="px-4 rounded bg-ambar text-background font-semibold disabled:opacity-50">Simular</button>
              </div>
            </Caja>
          )}
        </>
      ) : <Caja><p className="text-on-surface-variant text-[13px]">Registrar informes y novedades requiere conexión al servidor.</p></Caja>)}

      {tab === "historia" && <Caja titulo="Evolución en la lista">
        {historia ? <GraficoPosicion h={historia} /> : <p className="text-[13px] text-on-surface-variant">Cargando…</p>}
      </Caja>}
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
  const re = k.reevaluacion, ci = k.citas, co = k.contactabilidad, cc = k.concordancia;
  const num = (x, d = 1) => (x == null ? "—" : String(Math.round(x * 10 ** d) / 10 ** d).replace(".", ","));
  // Cada tarjeta muestra el valor medido y su n; "Sin datos" cuando aún no hay registros para medirlo.
  const Kpi = ({ titulo, valor, meta, estado, detalle }) => (
    <section className={`bg-surface-container-lowest border rounded p-4 border-l-4 ${estado === "ok" ? "border-l-hlf" : estado === "mal" ? "border-l-ambar" : "border-l-outline"} border-outline-variant`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-[15px]">{titulo}</h3>
        <span className={`text-[12px] font-semibold rounded px-2 py-0.5 ${estado === "ok" ? "bg-hlf-claro text-hlf" : estado === "mal" ? "bg-ambar-container text-ambar" : "bg-surface-container text-on-surface-variant"}`}>
          {estado === "ok" ? "En meta" : estado === "mal" ? "Bajo la meta" : estado === "info" ? "Sin meta oficial" : "Sin datos suficientes"}</span>
      </div>
      <div className="text-[32px] font-bold text-primary-container mt-1">{valor}</div>
      <div className="text-[13px] text-on-surface-variant">Meta del hospital: {meta}</div>
      <p className="text-[13px] mt-2">{detalle}</p>
    </section>
  );
  const Fila = ({ t, v, c = "" }) => <div className="flex justify-between"><span>{t}</span><b className={c}>{v}</b></div>;
  const pendientesEval = re.evaluacion_pendiente + re.evaluacion_atrasada;
  const exportar = () => descargarExcel(`indicadores_HLF_${k.fecha_corte}.xlsx`, [{ nombre: "Indicadores", filas: [["Grupo", "Indicador", "Valor", "Meta"],
    ["Cobertura", "Pacientes ordenados con criterio común", `${k.cobertura.evaluados} de ${k.cobertura.en_espera} (${k.cobertura.pct}%)`, "100%"],
    ["Reevaluación", "Mediana de horas evento → revisión de la prioridad", re.mediana_horas ?? "", "< 72 h"],
    ["Reevaluación", "Eventos graves evaluados en menos de 72 h", `${re.evaluados_menos_72h} de ${re.evaluados}`, ""],
    ["Reevaluación", "Eventos graves sin evaluar", re.sin_evaluar, ""],
    ["Descompensaciones", "En la lista", re.descompensados_en_lista, ""], ["Descompensaciones", "Evaluadas", re.evaluacion_hecha, ""],
    ["Descompensaciones", "Pendientes (≤ 72 h)", re.evaluacion_pendiente, ""], ["Descompensaciones", "Atrasadas (> 72 h)", re.evaluacion_atrasada, ""],
    ["Concordancia", "Revisiones (n)", cc.revisiones, `≥ ${cc.n_recomendado}`], ["Concordancia", "Acuerdo", cc.acuerdo_pct == null ? "" : `${cc.acuerdo_pct}%`, ""],
    ["Concordancia", "Kappa de Cohen", kap ?? "", "≥ 0,70"],
    ...(k.ajustes_manuales ? [["Ajustes manuales", "Vigentes", k.ajustes_manuales.vigentes, ""], ["Ajustes manuales", "Sin efecto por evento nuevo", k.ajustes_manuales.sin_efecto_por_evento, ""]] : []),
    ["Revisión", "Pacientes que requieren revisión del especialista", k.alertas.revision_sugerida, ""],
    ["Contactabilidad", "Llamadas registradas", co.intentos, ""], ["Contactabilidad", "Con respuesta", co.efectivos, ""],
    ["Egresos", "Por fallecimiento (causal 9)", k.egresos.fallecidos, ""], ["Egresos", "Atendidos en consulta nueva", k.egresos.atendidos, ""],
    ["Información", "Indicadores al", fmt(k.fecha_corte), ""], ["Información", "Datos", "Sintéticos de demostración", ""]] }]);
  return (
    <div className="flex flex-col gap-5">
      <div className="flex justify-end"><button onClick={exportar} className="h-9 px-3 rounded border border-outline-variant bg-surface-container-lowest font-semibold flex items-center gap-1 text-[14px]"><Icono n="download" className="text-[18px]" />Exportar a Excel</button></div>
      <div className="grid gap-4 md:grid-cols-3">
        <Kpi titulo="Reevaluación tras un evento grave" valor={re.evaluados ? `${num(re.mediana_horas)} h` : "—"} meta="< 72 horas"
          estado={!re.evaluados ? null : re.evaluados_menos_72h === re.evaluados ? "ok" : "mal"}
          detalle={<>Solo eventos registrados en la herramienta: {re.eventos_graves_registrados} en total; {re.evaluados} con la prioridad revisada ({re.evaluados_menos_72h} en menos de 72 h) y {re.sin_evaluar} todavía sin revisar. El valor es la mediana de horas entre el registro y la revisión.</>} />
        <Kpi titulo="Concordancia con el especialista" valor={cc.revisiones ? `${cc.acuerdo_pct}% de acuerdo` : "—"} meta={`kappa ≥ 0,70 (con n ≥ ${cc.n_recomendado})`}
          estado={!cc.suficiente ? null : kap >= cc.meta ? "ok" : "mal"}
          detalle={<>{cc.acuerdos} acuerdos en n = {cc.revisiones} revisiones (confirmar = acuerdo; cambiar prioridad = desacuerdo). Kappa de Cohen: <b>{kap == null ? "—" : num(kap, 2)}</b>.
            {!cc.suficiente && ` Con menos de ${cc.n_recomendado} revisiones el kappa es solo orientativo.`}</>} />
        <Kpi titulo="Espera prolongada" valor={`${k.espera?.mas_de_1_anio ?? "—"}`} meta="no definida (indicador de gestión)" estado="info"
          detalle={<>Pacientes que siguen esperando más de 1 año ({k.espera?.mas_de_500_dias} con más de 500 días; máxima {k.espera?.maxima_dias} días). Mediana de espera: {k.espera?.mediana_dias} días.</>} />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Caja titulo="Trabajo pendiente">
          <div className="text-[14px] space-y-1">
            {k.trabajo_pendiente && <>
            <Fila t="Pendientes de revisión" v={k.trabajo_pendiente.por_estado.pendiente_revision} c="text-ambar" />
            <Fila t="Pendientes de contacto" v={k.trabajo_pendiente.por_estado.pendiente_contacto} />
            <Fila t="Pendientes de cita" v={k.trabajo_pendiente.por_estado.pendiente_cita} />
            <Fila t="Con cita reservada" v={k.trabajo_pendiente.por_estado.cita_reservada} c="text-hlf" />
            <Fila t="Sin responsable" v={k.trabajo_pendiente.sin_responsable} c="text-ambar" />
            <Fila t="Seguimiento vencido" v={k.trabajo_pendiente.seguimiento_vencido} c={k.trabajo_pendiente.seguimiento_vencido ? "text-error" : ""} />
            </>}
          </div>
        </Caja>
        <Caja titulo="Citas de hoy por estado">
          <div className="text-[14px] space-y-1">
            <Fila t="Cupos reservados (aún no prueban atención)" v={ci.horas_recuperadas} />
            <Fila t="Propuestas (sin llamar)" v={ci.propuestas_sin_reservar} />
            <Fila t="Reservadas" v={ci.reservada} />
            <Fila t="Confirmadas por el paciente" v={ci.confirmada} c="text-hlf" />
            <Fila t="Atendidas" v={ci.atendida} c="text-hlf" />
            <Fila t="No asistió" v={ci.no_asistio} c={ci.no_asistio ? "text-ambar" : ""} />
            <Fila t="Canceladas (hora liberada)" v={ci.cancelada} />
          </div>
        </Caja>
        <Caja titulo="Contactabilidad">
          <div className="text-[14px] space-y-1">
            <Fila t="Llamadas registradas" v={co.intentos} />
            <Fila t="Con respuesta" v={co.pct == null ? "—" : `${co.efectivos} (${co.pct}%)`} />
            <Fila t="Pacientes con reintentos" v={co.pacientes_con_reintentos} c={co.pacientes_con_reintentos ? "text-ambar" : ""} />
          </div>
        </Caja>
        <Caja titulo="Descompensaciones graves">
          <div className="text-[14px] space-y-1">
            <Fila t="En la lista" v={re.descompensados_en_lista} />
            <Fila t="Prioridad revisada" v={re.evaluacion_hecha} c="text-hlf" />
            <Fila t="Nuevas, en plazo (≤ 72 h)" v={re.evaluacion_pendiente} />
            <Fila t="Atrasadas (> 72 h)" v={re.evaluacion_atrasada} c={re.evaluacion_atrasada ? "text-error" : ""} />
            <p className="text-[12px] text-on-surface-variant">{pendientesEval} sin revisión del especialista. El plazo cuenta desde que el evento llegó al sistema.</p>
          </div>
        </Caja>
        <Caja titulo="Revisión del especialista">
          <div className="text-[14px] space-y-1">
            <div className="flex justify-between"><span>Pacientes que requieren revisión</span><b className="text-ambar">{k.alertas.revision_sugerida}</b></div>
            <p className="text-[12px] text-on-surface-variant">Descompensaciones, exámenes alterados o aumentos de dosis posteriores a la interconsulta o a la última revisión.</p>
            {k.ajustes_manuales && <div className="pt-2 mt-1 border-t border-outline-variant/60 space-y-1">
              <div className="flex justify-between"><span>Ajustes manuales vigentes</span><b>{k.ajustes_manuales.vigentes}</b></div>
              <div className="flex justify-between"><span>Sin efecto por un evento nuevo</span><b className={k.ajustes_manuales.sin_efecto_por_evento ? "text-ambar" : ""}>{k.ajustes_manuales.sin_efecto_por_evento}</b></div>
            </div>}
          </div>
        </Caja>
        <Caja titulo="Egresos de la lista">
          <div className="text-[14px] space-y-1">
            <div className="flex justify-between"><span>Por fallecimiento (causal 9)</span><b>{k.egresos.fallecidos}</b></div>
            <div className="flex justify-between"><span>Atendidos en consulta nueva</span><b>{k.egresos.atendidos}</b></div>
          </div>
        </Caja>
      </div>
      <p className="text-[12px] text-on-surface-variant">Cobertura: {k.cobertura.evaluados} de {k.cobertura.en_espera} pacientes ordenados con el mismo criterio ({k.cobertura.criterio}). Kappa de Cohen entre la prioridad que propone el sistema y la decisión del especialista (Alta / Media / Baja). Indicadores al {fmt(k.fecha_corte)} · todo el hospital (todas las especialidades) · medidos sobre lo registrado en la herramienta.</p>
    </div>
  );
}

function EstadoRevision({ p }) {
  if (p.estado_revision === "requiere_revision") return <span className="text-ambar font-semibold">Requiere nueva revisión</span>;
  if (p.estado_revision === "pendiente") return <span className="text-on-surface-variant">Pendiente{p.revision_sugerida?.length ? " · revisión sugerida" : ""}</span>;
  return <span className="text-verde font-semibold">{p.estado_revision === "ajustado" ? "Ajustada" : "Confirmada"}{p.revision?.usuario && ` · ${p.revision.usuario}`}</span>;
}

// Contacto = lo que hace quien llama (no decide). Solo cierran la alerta: cita reservada o derivación a urgencia.
function Contacto({ p, fecha, onListo, onAviso }) {
  const [nota, setNota] = useState("");
  const [enviando, setEnviando] = useState(null);
  const enviar = async (resultado) => {
    setEnviando(resultado);
    try { onListo(await api.postContacto(p.id_paciente, { resultado, nota, fecha_corte: fecha })); setNota(""); }
    catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(null); }
  };
  const ops = [["citado", "Citado (sobrecupo)", "bg-primary text-on-primary"], ["derivado_urgencia", "Derivado a urgencia", "bg-error text-on-error"],
    ["contactado", "Informado, sin decisión aún", "border border-outline-variant"], ["no_contesta", "No contesta", "border border-outline-variant"]];
  return (
    <Caja titulo="Registrar llamada">
      {p.contacto && <p className="text-[13px] mb-2">Última: <b>{p.contacto.texto}</b> · {p.contacto.usuario}{p.contacto.intentos_sin_respuesta > 0 && ` · ${p.contacto.intentos_sin_respuesta} intento(s) sin respuesta`}</p>}
      <input value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Nota (opcional): p. ej. quién contestó" className="w-full h-9 px-2 border border-outline-variant rounded mb-2 text-[14px]" />
      <div className="grid grid-cols-2 gap-2 text-[13px]">
        {ops.map(([k, t, c]) => <button key={k} disabled={enviando} onClick={() => enviar(k)} className={`py-2 rounded font-semibold disabled:opacity-50 ${c}`}>{enviando === k ? "…" : t}</button>)}
      </div>
      <p className="text-[12px] text-on-surface-variant mt-2">Llamar, citar o derivar quedan registrados por separado. La alerta de descompensación se cierra solo cuando el especialista revisa la prioridad (decisión, confirmar o ajustar).</p>
    </Caja>
  );
}

// Decisión clínica ante una descompensación grave: la registra un profesional identificado, con seguimiento.
// Lista de espera simple: como una planilla, sin términos técnicos. Un clic abre todo el detalle en "Lista detallada".
const POR_PAGINA_SIMPLE = 50;
function ListaSimple({ data, fecha, esp, setEsp, actualizando, onVer }) {
  const [busca, setBusca] = useState("");
  const [prioridad, setPrioridad] = useState("todas");
  const [pagina, setPagina] = useState(0);
  useEffect(() => setPagina(0), [busca, prioridad, esp]);
  const q = busca.trim().toLowerCase();
  const filas = data.pacientes.filter((p) => (prioridad === "todas" || p.categoria === prioridad) &&
    (!q || [p.nombre_fantasia, p.id_paciente, p.diagnostico_texto, p.comuna].some((x) => (x || "").toLowerCase().includes(q))));
  const pag = filas.slice(pagina * POR_PAGINA_SIMPLE, (pagina + 1) * POR_PAGINA_SIMPLE);
  const paginas = Math.max(1, Math.ceil(filas.length / POR_PAGINA_SIMPLE));
  const SEXO = { F: "Femenino", M: "Masculino" };
  const columnas = ["N°", "Nombre", "RUT / ID", "Edad", "Sexo", "Comuna", "Previsión", "Especialidad", "Diagnóstico", "Prioridad", "Ingreso a la lista", "Días de espera"];
  const exportar = () => descargarExcel(`lista_espera_HLF_${fecha}.xlsx`, [{ nombre: "Lista de espera", filas: [columnas,
    ...filas.map((p) => [p.posicion, p.nombre_fantasia, p.id_paciente, p.edad, SEXO[p.sexo] || p.sexo, p.comuna, p.prevision || "", p.especialidad,
      `${p.diagnostico_cie10} ${p.diagnostico_texto}`, ETIQUETA[p.categoria], fmt(p.fecha_ingreso_lista), p.dias_espera])] }]);
  const campo = "h-10 px-3 border border-outline-variant rounded bg-surface-container-lowest text-[15px]";
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-[22px] font-bold">Lista de espera</h1>
        <p className="text-[15px] text-on-surface-variant">Ordenada desde quien debe atenderse primero. Haga clic en un paciente para ver todo su detalle.</p>
      </div>
      <div className="flex flex-wrap items-end gap-3 text-[14px]">
        <Filtro label="Buscar"><input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nombre, RUT o diagnóstico" className={`${campo} w-64`} /></Filtro>
        <Filtro label="Especialidad"><select value={esp} onChange={(e) => setEsp(e.target.value)} className={campo}>{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select></Filtro>
        <Filtro label="Prioridad"><select value={prioridad} onChange={(e) => setPrioridad(e.target.value)} className={campo}>
          <option value="todas">Todas</option><option value="alta">Alta</option><option value="media">Media</option><option value="baja">Baja</option></select></Filtro>
        <button onClick={exportar} className="ml-auto h-10 px-4 rounded bg-primary text-on-primary font-semibold flex items-center gap-1"><Icono n="download" className="text-[18px]" />Descargar en Excel</button>
      </div>
      <section className="bg-surface-container-lowest border border-outline-variant rounded overflow-x-auto relative" aria-busy={actualizando}>
        <table className={`w-full text-left border-collapse text-[14px] ${actualizando ? "opacity-40" : ""}`}>
          <thead><tr className="bg-surface-container-low text-on-surface-variant border-b border-outline-variant">
            {columnas.map((c) => <th key={c} className={`py-2 px-3 font-semibold whitespace-nowrap ${["N°", "Edad", "Días de espera"].includes(c) ? "text-right" : ""}`}>{c}</th>)}
          </tr></thead>
          <tbody>
            {pag.map((p) => (
              <tr key={p.id_paciente} onClick={() => onVer(p.id_paciente)} tabIndex={0} title="Ver todo el detalle"
                onKeyDown={(e) => { if (e.key === "Enter") onVer(p.id_paciente); }}
                className="cursor-pointer border-b border-outline-variant/60 hover:bg-primary/5 focus:bg-primary/10">
                <td className="py-2 px-3 text-right font-semibold">{p.posicion}</td>
                <td className="py-2 px-3 font-semibold text-primary whitespace-nowrap">{p.nombre_fantasia}</td>
                <td className="py-2 px-3 whitespace-nowrap">{p.id_paciente}</td>
                <td className="py-2 px-3 text-right">{p.edad}</td>
                <td className="py-2 px-3">{SEXO[p.sexo] || p.sexo}</td>
                <td className="py-2 px-3 whitespace-nowrap">{p.comuna}</td>
                <td className="py-2 px-3 whitespace-nowrap">{p.prevision}</td>
                <td className="py-2 px-3 whitespace-nowrap">{p.especialidad}</td>
                <td className="py-2 px-3">{p.diagnostico_texto}</td>
                <td className="py-2 px-3"><Prioridad cat={p.categoria} /></td>
                <td className="py-2 px-3 whitespace-nowrap">{fmt(p.fecha_ingreso_lista)}</td>
                <td className="py-2 px-3 text-right font-semibold whitespace-nowrap">{p.dias_espera}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {filas.length === 0 && <p className="p-6 text-on-surface-variant">No hay pacientes con esa búsqueda.</p>}
      </section>
      <div className="flex flex-wrap items-center justify-between gap-2 text-[14px] text-on-surface-variant">
        <span>{actualizando ? "Actualizando…" : `${filas.length} pacientes`} · lista al {fmt(fecha)}</span>
        <div className="flex items-center gap-2">
          <button disabled={pagina === 0} onClick={() => setPagina(pagina - 1)} className="px-3 py-1.5 border border-outline-variant rounded bg-surface-container-lowest disabled:opacity-40">Anterior</button>
          <span>Página {pagina + 1} de {paginas}</span>
          <button disabled={pagina >= paginas - 1} onClick={() => setPagina(pagina + 1)} className="px-3 py-1.5 border border-outline-variant rounded bg-surface-container-lowest disabled:opacity-40">Siguiente</button>
        </div>
      </div>
      <p className="text-[12px] text-on-surface-variant">Datos sintéticos: el registro de prueba no trae RUT, por eso se muestra el ID del paciente. Con las planillas del hospital, esta columna muestra el RUT.</p>
    </div>
  );
}

// Gestión del caso: qué falta (estado calculado), quién se encarga, qué se hace y cuándo se vuelve a mirar.
const MOTIVOS_PENDIENTE = [["falta_cupo", "Falta de cupo"], ["contacto", "No se ha podido contactar"], ["antecedentes", "Faltan antecedentes o exámenes"],
  ["revision", "Espera revisión del especialista"], ["paciente", "Decisión o disponibilidad del paciente"], ["otro", "Otro (documentado)"]];
function GestionCaso({ p, fecha, onListo, onAviso }) {
  const g = p.gestion || {};
  const [f, setF] = useState({ responsable: g.responsable || api.getUsuario(), proxima_accion: g.accion_asignada ? g.proxima_accion : "",
    seguimiento: g.seguimiento || "", motivo_pendiente: g.motivo_pendiente || "", nota: g.nota || "" });
  const [enviando, setEnviando] = useState(false);
  const usuario = api.getUsuario();
  const notaCorta = f.motivo_pendiente === "otro" && f.nota.trim().length < MIN_EXPLICACION;
  const guardar = async () => {
    setEnviando(true);
    try { await api.postGestion(p.id_paciente, { ...f, fecha_corte: fecha }); onListo(); }
    catch (e) { onAviso({ titulo: "No se pudo guardar: " + e.message }); } finally { setEnviando(false); }
  };
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest text-[14px] w-full";
  return (
    <Caja titulo="Gestión del caso">
      <div className="text-[14px] mb-2">Estado: <b className={ESTILO_GESTION[g.estado]}>{g.texto}</b>
        <span className="text-[12px] text-on-surface-variant"> (se calcula con lo registrado: revisión, llamadas y citas)</span></div>
      {g.actualizado_por && <p className="text-[12px] text-on-surface-variant mb-2">Última actualización: {g.actualizado_por} · {fmt(g.actualizado)}</p>}
      <div className="grid grid-cols-2 gap-2 text-[13px]">
        <Filtro label="Responsable"><input value={f.responsable} onChange={(e) => setF({ ...f, responsable: e.target.value })} placeholder="Nombre y cargo" className={campo} /></Filtro>
        <Filtro label="Fecha de seguimiento"><input type="date" min={fecha} value={f.seguimiento} onChange={(e) => setF({ ...f, seguimiento: e.target.value })} className={campo} /></Filtro>
        <div className="col-span-2"><Filtro label={`Próxima acción (si se deja vacía: "${ESTADO_ACCION[g.estado] || g.proxima_accion}")`}>
          <input value={f.proxima_accion} onChange={(e) => setF({ ...f, proxima_accion: e.target.value })} placeholder="Ej.: pedir ecografía a APS antes de citar" className={campo} /></Filtro></div>
        <div className="col-span-2"><Filtro label="Motivo del pendiente (qué bloquea la atención)">
          <select value={f.motivo_pendiente} onChange={(e) => setF({ ...f, motivo_pendiente: e.target.value })} className={campo}>
            <option value="">Sin motivo registrado</option>{MOTIVOS_PENDIENTE.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select></Filtro></div>
        <div className="col-span-2"><Filtro label={f.motivo_pendiente === "otro" ? `Nota (obligatoria, mínimo ${MIN_EXPLICACION} caracteres)` : "Nota (opcional)"}>
          <input value={f.nota} onChange={(e) => setF({ ...f, nota: e.target.value })} className={campo} /></Filtro></div>
      </div>
      {!usuario && <p className="text-[12px] text-ambar font-semibold mt-2">Escriba su nombre y cargo arriba a la derecha: la gestión queda registrada a su nombre.</p>}
      <button disabled={enviando || !usuario || notaCorta} onClick={guardar} className="mt-2 w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{enviando ? "Guardando…" : "Guardar gestión"}</button>
    </Caja>
  );
}
const ESTADO_ACCION = { pendiente_revision: "Revisar la prioridad (especialista)", pendiente_contacto: "Volver a llamar", pendiente_cita: "Buscar cupo y citar",
  cita_reservada: "Confirmar asistencia", atendido: "Registrar la atención (egreso)" };

// Ajuste manual de la posición en la lista: siempre con un motivo previo, explicado y a nombre de quien lo hace.
const MOTIVOS_AJUSTE = [["criterio_clinico", "Criterio clínico del especialista"], ["informacion_no_registrada", "Información clínica que no está en el registro"],
  ["comite", "Decisión de comité o jefatura"], ["error_registro", "Corrección de un error de registro"], ["otro", "Otro motivo (explicado)"]];
const MIN_EXPLICACION = 20;
function AjusteManual({ p, fecha, onListo, onAviso }) {
  const [abierto, setAbierto] = useState(false);
  const [f, setF] = useState({ posicion: "", motivo: "", explicacion: "" });
  const [enviando, setEnviando] = useState(false);
  const usuario = api.getUsuario();
  const a = p.ajuste_manual;
  const faltan = MIN_EXPLICACION - f.explicacion.trim().length;
  const enviar = async (quitar) => {
    setEnviando(true);
    try {
      const body = quitar ? { quitar: true, explicacion: f.explicacion, fecha_corte: fecha }
        : { posicion: Number(f.posicion), motivo: f.motivo, explicacion: f.explicacion, fecha_corte: fecha };
      const r = await api.postOrden(p.id_paciente, body);
      setAbierto(false); setF({ posicion: "", motivo: "", explicacion: "" }); onListo(r, quitar);
    } catch (e) { onAviso({ titulo: "No se pudo guardar: " + e.message }); } finally { setEnviando(false); }
  };
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest text-[14px]";
  return (
    <Caja titulo="Mover en la lista (ajuste manual)" accion={!abierto && <button onClick={() => setAbierto(true)} className="text-[13px] text-primary font-semibold">{a ? "Cambiar o deshacer" : "Mover"}</button>}>
      {a ? <div className="text-[14px] rounded bg-primary/5 border border-primary/30 p-2">
          <b>Movido a mano al N° {a.posicion} de {a.especialidad}</b> (el sistema lo ponía en el N° {a.posicion_anterior}).
          <div className="text-[13px] mt-0.5">Motivo: {a.motivo_texto}. «{a.explicacion}»</div>
          <div className="text-[12px] text-on-surface-variant">{a.usuario} · {fmt(a.fecha)}</div>
        </div>
        : <p className="text-[13px] text-on-surface-variant">N° {p.posicion_especialidad} en la lista de {p.especialidad}. Si el equipo necesita cambiar su lugar, debe dejar el motivo explicado: queda registrado a su nombre.</p>}
      {p.ajuste_manual_vencido && <p className="mt-2 text-[13px] text-ambar font-semibold">El ajuste manual anterior dejó de aplicarse por un evento nuevo ({p.ajuste_manual_vencido.vencido_por}): revise su lugar en la lista.</p>}
      {abierto && (
        <div className="mt-3 flex flex-col gap-2 text-[14px]">
          {!usuario && <p className="text-[13px] text-ambar font-semibold">Escriba su nombre y cargo arriba a la derecha: el ajuste queda registrado a su nombre.</p>}
          {a && <p className="text-[13px] text-on-surface-variant">Para deshacer el ajuste, explique por qué y presione "Deshacer". Para cambiarlo, complete todo.</p>}
          <label className="flex items-center gap-2">Mover al N°
            <input type="number" min={1} value={f.posicion} onChange={(e) => setF({ ...f, posicion: e.target.value })} className={`${campo} w-24`} />
            <span className="text-on-surface-variant text-[13px]">de la lista de {p.especialidad}</span></label>
          <select value={f.motivo} onChange={(e) => setF({ ...f, motivo: e.target.value })} className={campo}>
            <option value="">Motivo del ajuste…</option>{MOTIVOS_AJUSTE.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
          <textarea rows={3} value={f.explicacion} onChange={(e) => setF({ ...f, explicacion: e.target.value })}
            placeholder="Explique el motivo (obligatorio). Ej.: la familia informa crisis semanales que no están registradas; evaluado por el Dr. X."
            className="p-2 border border-outline-variant rounded bg-surface-container-lowest resize-y" />
          <span className={`text-[12px] ${faltan > 0 ? "text-ambar" : "text-on-surface-variant"}`}>{faltan > 0 ? `Faltan ${faltan} caracteres para explicar el motivo.` : "Explicación suficiente."}</span>
          <div className="flex gap-2">
            <button disabled={enviando || !usuario || faltan > 0 || !f.motivo || !(Number(f.posicion) >= 1)} onClick={() => enviar(false)}
              className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{enviando ? "Guardando…" : "Mover"}</button>
            {a && <button disabled={enviando || !usuario || faltan > 0} onClick={() => enviar(true)} className="flex-1 py-2 rounded border border-primary text-primary font-semibold disabled:opacity-40">Deshacer</button>}
            <button onClick={() => setAbierto(false)} className="px-3 py-2 rounded border border-outline-variant font-semibold">Cancelar</button>
          </div>
          <p className="text-[12px] text-on-surface-variant">Si después llega un evento clínico nuevo (urgencia, hospitalización, examen alterado), el ajuste deja de aplicarse y el paciente vuelve al orden del sistema para que se revise.</p>
        </div>
      )}
    </Caja>
  );
}

function DecisionClinica({ p, fecha, onListo, onAviso }) {
  const [f, setF] = useState({ decision: "citar_prioritario", responsable: api.getUsuario(), nota: "", seguimiento: "" });
  const [enviando, setEnviando] = useState(false);
  const enviar = async () => {
    setEnviando(true);
    try { onListo(await api.postDecision(p.id_paciente, { ...f, seguimiento: f.seguimiento || null, fecha_corte: fecha })); }
    catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(false); }
  };
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest text-[14px]";
  return (
    <Caja titulo="Decisión del especialista ante la descompensación" className={p.contactar_hoy ? "border-l-4 border-l-error" : ""}>
      {p.decision && <p className="text-[13px] mb-2">Última: <b>{p.decision.texto}</b> · {p.decision.responsable}{p.decision.nota && ` · ${p.decision.nota}`}</p>}
      <div className="grid grid-cols-2 gap-2">
        <select value={f.decision} onChange={(e) => setF({ ...f, decision: e.target.value })} className={`${campo} col-span-2`}>
          <option value="citar_prioritario">Citar en forma prioritaria</option><option value="derivar_urgencia">Derivar a urgencia</option>
          <option value="adelantar_control">Adelantar control o teleconsulta</option><option value="mantener">Se mantiene en lista con su prioridad</option>
        </select>
        <input value={f.responsable} onChange={(e) => setF({ ...f, responsable: e.target.value })} placeholder="Profesional responsable" className={campo} />
        <label className="flex items-center gap-1 text-[12px] text-on-surface-variant">Seguimiento
          <input type="date" min={fecha} value={f.seguimiento} onChange={(e) => setF({ ...f, seguimiento: e.target.value })} className={`${campo} flex-1`} /></label>
        <input value={f.nota} onChange={(e) => setF({ ...f, nota: e.target.value })} placeholder="Fundamento (opcional)" className={`${campo} col-span-2`} />
      </div>
      <button disabled={enviando || !f.responsable.trim()} onClick={enviar} className="mt-2 w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{enviando ? "Guardando…" : "Registrar decisión"}</button>
    </Caja>
  );
}

// Colores por variable CSS: siguen el tema claro/oscuro (también dentro del gráfico SVG)
const COLOR_HEX = { alta: "rgb(var(--c-error))", media: "rgb(var(--c-ambar))", baja: "rgb(var(--c-verde))" };

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
        <b>Experimental.</b> Puntos según {lace.fuente}. Solo desempata pacientes con la misma prioridad y antigüedad; no es un puntaje validado para listas de espera.
      </p>
      {lace.datos_faltantes?.length > 0 && <p className="text-[12px] text-ambar mt-1">Datos faltantes: {lace.datos_faltantes.join(" · ")}.</p>}
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
  if (p.riesgo_vital) pasos.push(p.contactar_hoy ? { t: "Descompensación grave", v: p.evaluacion?.estado === "atrasada" ? "Evaluación atrasada" : "Evaluar ≤ 72 h", f: "Criterio médico MINSAL", icon: "call", rojo: true }
    : { t: "Descompensación grave", v: "Evaluada", f: p.evaluacion?.cierre?.texto, icon: "task_alt", cat: "alta" });
  if (p.ajuste_manual) pasos.push({ t: "Ajuste manual", v: `N° ${p.ajuste_manual.posicion} en ${p.ajuste_manual.especialidad}`, f: `${p.ajuste_manual.motivo_texto} · ${p.ajuste_manual.usuario}`, icon: "swap_vert" });
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
            <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke="rgb(var(--c-divider))" strokeWidth="1" />
            <text x={m.l - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="rgb(var(--c-muted))">N° {v}</text>
          </g>
        ))}
        {meses.map((ym) => { const xx = X(`${ym}-01` < pts[0].fecha ? pts[0].fecha : `${ym}-01`); return <text key={ym} x={xx} y={H - 8} fontSize="11" fill="rgb(var(--c-muted))" textAnchor="middle">{nombreMes(ym)}</text>; })}
        {evs.map((e, i) => {
          const xx = Math.min(Math.max(X(e.fecha_evento), m.l), W - m.r);
          const grave = e.severidad === "grave" || e.subtipo.includes("descompensaci");
          return (
            <g key={i}>
              <line x1={xx} x2={xx} y1={m.t} y2={H - m.b} stroke={grave ? "rgb(var(--c-error))" : "rgb(var(--c-verde))"} strokeWidth="1" strokeDasharray="3 3" />
              <circle cx={xx} cy={m.t} r="4" fill={grave ? "rgb(var(--c-error))" : "rgb(var(--c-verde))"}><title>{fmt(e.fecha_evento)}: {e.subtipo}</title></circle>
            </g>
          );
        })}
        <path d={linea} fill="none" stroke="rgb(var(--c-primary))" strokeWidth="2" strokeLinejoin="round" />
        {pts.map((p, i) => (
          <g key={p.fecha} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <circle cx={X(p.fecha)} cy={Y(p.posicion)} r="12" fill="transparent" />
            <circle cx={X(p.fecha)} cy={Y(p.posicion)} r={hover === i ? 6 : 4.5} fill={COLOR_HEX[p.categoria]} stroke="rgb(var(--c-raised))" strokeWidth="2" />
          </g>
        ))}
        {(() => { const u = pts[pts.length - 1]; return <text x={X(u.fecha) - 8} y={Y(u.posicion) + (Y(u.posicion) < 30 ? 16 : -8)} textAnchor="end" fontSize="12" fontWeight="600" fill="rgb(var(--c-text))">N° {u.posicion}</text>; })()}
      </svg>
      {hp && (
        <div className="absolute pointer-events-none bg-on-surface text-background text-[12px] rounded px-2 py-1 shadow"
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
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest w-full";
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

// Dos pestañas con los mismos datos del día:
//   "Hoy": descompensaciones graves que requieren evaluación médica (plazo 72 h) y a quién llamar.
//   "Gestión de box": cómo llenar las horas libres; propuesta → reservada → confirmada → atendida / no asistió / cancelada.
const ESTADO_CITA = { propuesta: ["Propuesta", "gris"], reservada: ["Reservada", "azul"], confirmada: ["Confirmada", "azul"],
  atendida: ["Atendida", "azul"], no_asistio: ["No asistió", "ambar"], cancelada: ["Cancelada", "gris"] };
function Hoy({ parte, vitales, todosPacientes, fecha, esp, setEsp, onVer, esApi, onCambio, onAviso }) {
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
  const horasLibres = (b?.especialidades || []).reduce((s, e) => s + e.cupos_libres_hoy, 0);
  const nombreBox = (id) => id?.replace("BOX-", "Box ");

  const registrar = async (p, resultado) => {
    setEnviando(p.id_paciente + resultado);
    const h = parte === "box" && hora[p.id_paciente];  // en Alertas no se reservan horas de box
    try {
      const r = await api.postContacto(p.id_paciente, { resultado, fecha_corte: fecha,
        ...(resultado === "citado" && h ? { hora: h.hora, hora_fin: h.hora_fin, id_box: h.id_box } : {}) });
      await onCambio(); onAviso({ titulo: `${p.nombre_fantasia}: ${r.contacto.texto}` });
    } catch (e) {
      onAviso({ titulo: e.message.includes("ya fue reservada") ? `Hora no disponible: ${e.message}. Se actualizó la agenda.` : "No se pudo registrar: " + e.message });
      if (e.message.includes("ya fue reservada")) await onCambio();
    } finally { setEnviando(null); }
  };
  const cambiarCita = async (p, estado) => {
    setEnviando(p.id_paciente + estado);
    try { const r = await api.postCita(p.id_paciente, { estado, fecha_corte: fecha }); await onCambio(); onAviso({ titulo: `${p.nombre_fantasia}: cita ${ESTADO_CITA[r.cita.estado_cita][0].toLowerCase()}` }); }
    catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(null); }
  };

  const Evaluacion = ({ p }) => p.evaluacion && (
    <div className={`text-[12px] font-semibold ${p.evaluacion.estado === "atrasada" ? "text-error" : "text-on-surface-variant"}`}>
      Evento grave del {fmt(p.evaluacion.fecha_evento)} · en el sistema desde el {fmt(p.evaluacion.llego_al_sistema)} ({p.evaluacion.dias_en_revision} día{p.evaluacion.dias_en_revision !== 1 ? "s" : ""})
      {p.evaluacion.estado === "atrasada" ? " · REVISIÓN ATRASADA (> 72 h)" : " · nueva, dentro del plazo de 72 h"}</div>
  );
  const conteo = (b?.especialidades || []).reduce((s, e) => {
    Object.entries(e.conteo_citas || {}).forEach(([k, v]) => { s[k] = (s[k] || 0) + v; }); return s;
  }, {});
  const citasHechas = (conteo.reservada || 0) + (conteo.confirmada || 0) + (conteo.atendida || 0);

  // Agrupa por especialidad (la que tiene más pacientes primero): cada especialista ve lo suyo
  const agrupar = (xs) => Object.entries(xs.reduce((m, p) => ((m[p.especialidad] ||= []).push(p), m), {})).sort((x, y) => y[1].length - x[1].length);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2 text-[14px]">
        <span className="text-on-surface-variant">Especialidad:</span>
        <select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select>
        <span className="text-[13px] text-on-surface-variant">{esp === "Todas" ? "Vista de coordinación: todo el hospital, agrupado por especialidad." : `Solo ${esp}.`}</span>
        {parte === "hoy" && <button onClick={() => {
          const fila = (p) => [p.posicion, p.nombre_fantasia, p.id_paciente, p.edad, p.especialidad, p.diagnostico_cie10, p.diagnostico_texto, ETIQUETA[p.categoria]];
          const ev = (p) => p.razones.find((r) => r.factor === "evento")?.valor || "";
          descargarExcel(`alertas_HLF_${fecha}.xlsx`, [
            { nombre: "Descompensaciones graves", filas: [["N°", "Paciente", "ID", "Edad", "Especialidad", "CIE-10", "Diagnóstico", "Prioridad", "Evento", "Fecha del evento",
              "Días desde el evento", "Evaluación", "Cerrada por", "Responsable", "Última llamada", "Intentos sin respuesta"],
              ...todos.map((p) => [...fila(p), ev(p), fmt(p.evaluacion?.fecha_evento), p.evaluacion?.dias_desde_evento ?? "", EVAL_TXT[p.evaluacion?.estado] || "",
                p.evaluacion?.cierre?.texto || "", p.evaluacion?.cierre?.responsable || "", p.contacto?.texto || "", p.contacto?.intentos_sin_respuesta || ""])] },
            { nombre: "Avisar al especialista", filas: [["N°", "Paciente", "ID", "Edad", "Especialidad", "CIE-10", "Diagnóstico", "Prioridad", "Evento"],
              ...aRevisar.map((p) => [...fila(p), ev(p)])] },
            { nombre: "Información", filas: [["Dato", "Valor"], ["Fecha", fmt(fecha)], ["Especialidad", esp], ["Generado por", api.getUsuario() || "(sin nombre)"],
              ["Datos", "Sintéticos de demostración: no son pacientes reales"]] }]);
        }} className="ml-auto h-9 px-3 rounded border border-outline-variant bg-surface-container-lowest font-semibold flex items-center gap-1"><Icono n="download" className="text-[18px]" />Exportar a Excel</button>}
      </div>
      {b && (
        <section className="rounded border border-primary/30 bg-primary/5 p-4 text-[15px] leading-relaxed">
          <b>Resumen del {fmt(fecha)}{esp !== "Todas" ? ` · ${esp}` : ""}:</b>{" "}
          {parte === "hoy"
            ? <>{todos.length ? <>Hay <b>{todos.length} pacientes con descompensación grave</b>: <b className="text-hlf">{todos.length - pendientes.length} con la prioridad ya revisada</b>
                {pendientes.length > 0 && <>, <b className="text-error">{pendientes.length} esperan revisión de su prioridad</b>{todos.filter((p) => p.evaluacion?.estado === "atrasada").length > 0 && <> ({todos.filter((p) => p.evaluacion?.estado === "atrasada").length} con más de 72 h)</>}</>}.
                </> : "No hay descompensaciones graves pendientes de revisión."}</>
            : <>quedan <b>{horasLibres} horas libres</b> en los box. <b>{conteo.propuesta || 0} propuestas</b> (aún no son citas) · <b className="text-hlf">{citasHechas} citas reservadas</b>
                {conteo.confirmada ? <> ({conteo.confirmada} confirmadas)</> : null}{conteo.no_asistio ? <> · {conteo.no_asistio} no asistieron</> : null}.</>}
          {parte === "box" && b.agenda_referencia && <div className="mt-1 text-[13px] text-on-surface-variant">Agenda de box: el registro sintético trae agenda hasta el {fmt(b.dia_agenda)}; se usa esa como agenda de referencia para hoy.</div>}
        </section>
      )}
      {err && <Caja><p className="text-on-surface-variant">{err}</p></Caja>}
      {!err && !b && <p className="text-on-surface-variant">Cargando el día…</p>}

      <div className="grid gap-5 lg:grid-cols-12 items-start">
        {parte === "hoy" && <>
        <Caja titulo={`Descompensaciones graves: revisar prioridad (${pendientes.length}: ${pendientes.filter((p) => p.evaluacion?.estado !== "atrasada").length} nuevas · ${pendientes.filter((p) => p.evaluacion?.estado === "atrasada").length} atrasadas)`} className="lg:col-span-7 border-l-4 border-l-error">
          <p className="text-[13px] text-on-surface-variant mb-3">Tuvieron un evento grave después de la interconsulta y no hay registro posterior de estabilización ni de evaluación. Su prioridad debe revisarla el especialista dentro de 72 h desde que el evento llegó al sistema (KPI del hospital). Llamar o citar no cierra la alerta.</p>
          {todos.length === 0 && <p className="text-on-surface-variant">Nadie pendiente{esp !== "Todas" && ` en ${esp}`}.</p>}
          {agrupar(pendientes).map(([nombreEsp, grupo]) => {
            return (
          <div key={nombreEsp} className="mb-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2 bg-surface-container-low rounded px-2 py-1.5 text-[14px]">
              <b>{nombreEsp} · {grupo.length} por revisar</b>
            </div>
          <ul className="divide-y divide-outline-variant/60">
            {grupo.map((p) => (
              <li key={p.id_paciente} className="py-2.5 text-[14px]">
                <button onClick={() => onVer(p.id_paciente)} className="text-left hover:underline">
                  <span className="text-on-surface-variant text-[13px] mr-1">N° {p.posicion}</span>
                  <b>{p.nombre_fantasia}</b> <span className="text-on-surface-variant text-[13px]">· {p.edad} años · {p.especialidad} · {p.diagnostico_texto}</span>
                </button>
                <Evaluacion p={p} />
                
                {p.contacto?.intentos_sin_respuesta > 0 && <div className="text-[12px] text-ambar font-semibold">{p.contacto.intentos_sin_respuesta} intento{p.contacto.intentos_sin_respuesta > 1 ? "s" : ""} sin respuesta{p.contacto.intentos_sin_respuesta >= 3 ? ": evaluar visita domiciliaria o derivación" : ""}</div>}
                {p.contacto?.resultado === "contactado" && <div className="text-[12px] text-on-surface-variant">Informado por teléfono: falta la decisión médica.</div>}
                <div className="flex flex-wrap items-center gap-1 mt-1.5 text-[12px]">
                  <span className="text-on-surface-variant mr-1">Llamada:</span>
                  {[["citado", "Citado"], ["derivado_urgencia", "Derivado a urgencia"], ["contactado", "Informado"], ["no_contesta", "No contesta"]].map(([k, t]) => (
                    <button key={k} disabled={enviando} onClick={() => registrar(p, k)}
                      className={`px-2 py-1 rounded border font-semibold disabled:opacity-40 ${k === "derivado_urgencia" ? "border-error text-error" : k === "citado" ? "border-primary text-primary" : "border-outline-variant text-on-surface-variant"}`}>
                      {enviando === p.id_paciente + k ? "…" : t}</button>
                  ))}
                  <button onClick={() => onVer(p.id_paciente)} className="px-2 py-1 rounded bg-primary text-on-primary font-semibold">Decisión médica →</button>
                </div>
              </li>
            ))}
          </ul>
          </div>
            );
          })}
          {listos.length > 0 && (
            <details className="mt-2 text-[13px]">
              <summary className="cursor-pointer text-on-surface-variant">Prioridad ya revisada ({listos.length})</summary>
              <ul className="mt-1 space-y-1">
                {listos.map((p) => <li key={p.id_paciente}><button onClick={() => onVer(p.id_paciente)} className="hover:underline">{p.nombre_fantasia}</button> · <span className="text-hlf">{p.evaluacion?.cierre?.texto}{p.evaluacion?.cierre?.responsable && ` · ${p.evaluacion.cierre.responsable}`}</span></li>)}
              </ul>
            </details>
          )}
        </Caja>

        <Caja titulo={`Avisar al especialista (${aRevisar.length})`} className="lg:col-span-5 border-l-4 border-l-ambar">
          <div>
            <p className="text-[13px] text-on-surface-variant mb-2">Se descompensaron después de la interconsulta, pero la tabla del HLF no define cuánto sube su prioridad. No se les cambia solo: el especialista debe revisarlos y confirmar o cambiar su prioridad.</p>
            {aRevisar.length === 0 && <p className="text-[13px] text-on-surface-variant">Nadie pendiente de revisión{esp !== "Todas" && ` en ${esp}`}.</p>}
            {agrupar(aRevisar).map(([nombreEsp, grupo]) => (
              <details key={nombreEsp} open={esp !== "Todas"} className="border-t border-outline-variant/60">
                <summary className="cursor-pointer py-1.5 text-[14px] font-semibold">{nombreEsp} · {grupo.length} para revisar</summary>
                <ul className="divide-y divide-outline-variant/60 pl-3">
                  {grupo.map((p) => {
                    const ev = p.razones.find((r) => r.factor === "evento");
                    return (
                      <li key={p.id_paciente} className="py-2 text-[14px]">
                        <button onClick={() => onVer(p.id_paciente)} className="text-left hover:underline">
                          <b>{p.nombre_fantasia}</b> <span className="text-on-surface-variant text-[13px]">· {p.diagnostico_texto} · prioridad {p.categoria}</span>
                        </button>
                        {ev && <div className="text-[13px] text-ambar">{ev.valor}</div>}
                      </li>
                    );
                  })}
                </ul>
              </details>
            ))}
          </div>
        </Caja>
        </>}

        {parte === "box" && <div className="lg:col-span-12 flex flex-col gap-4">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h2 className="text-[17px] font-semibold">Llenar las horas libres de hoy</h2>
              <p className="text-[13px] text-on-surface-variant">Cada hora libre se propone al siguiente paciente de la lista de su especialidad. Una <b>propuesta</b> no es una cita: no bloquea la hora hasta que se <b>reserva</b> al llamar. Una hora no se puede reservar dos veces (el sistema lo rechaza).</p>
              <details className="text-[13px] text-on-surface-variant mt-1"><summary className="cursor-pointer">¿Qué significa cada cosa?</summary>
                <p className="mt-1">"Alta / Media / Baja" es la prioridad clínica de la lista, no una urgencia de hoy; las descompensaciones graves están en la pestaña <i>Hoy</i>. Estados de una cita: propuesta → reservada → confirmada por el paciente → atendida o no asistió; si se cancela, la hora vuelve a quedar libre. Las horas se calculan dividiendo el bloque del box por su capacidad (por ejemplo, 08:30–13:30 con 10 cupos = una hora cada 30 min); en <i>Tengo horas libres</i> se usa en cambio la duración promedio de las consultas de la especialidad, porque ahí el médico informa su propio horario.</p>
              </details>
            </div>
          </div>
          {b?.especialidades.filter((e) => e.asignaciones.length).map((e) => (
            <Caja key={e.especialidad} titulo={e.especialidad} accion={<span className="text-[13px] text-on-surface-variant">{e.cupos_libres_hoy} hora{e.cupos_libres_hoy !== 1 ? "s" : ""} libre{e.cupos_libres_hoy !== 1 ? "s" : ""} hoy · {e.conteo_citas?.propuesta || 0} propuestas · {(e.conteo_citas?.reservada || 0) + (e.conteo_citas?.confirmada || 0) + (e.conteo_citas?.atendida || 0)} citas</span>}>
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
                          {p.riesgo_vital && p.contactar_hoy && <span className="block text-[13px] text-error font-semibold">Descompensación grave: también requiere evaluación médica (pestaña Hoy)</span>}
                          {!p.riesgo_vital && p.riesgo_inasistencia && <span className="block text-[13px] text-ambar font-semibold">Faltó 2 veces seguidas: confirmar asistencia por teléfono</span>}
                          <span className="flex flex-wrap items-center gap-1 mt-1 text-[12px]" onClick={(ev) => ev.stopPropagation()}>
                            <Marca tono={ESTADO_CITA[p.estado_cita || "propuesta"][1]}>{ESTADO_CITA[p.estado_cita || "propuesta"][0]}</Marca>
                            {(p.estado_cita || "propuesta") === "propuesta" && <>
                              <button disabled={enviando} onClick={() => registrar(p, "citado")} className="px-2 py-0.5 rounded border border-primary text-primary font-semibold disabled:opacity-40">{enviando === p.id_paciente + "citado" ? "…" : "Reservar (contestó)"}</button>
                              <button disabled={enviando} onClick={() => registrar(p, "no_contesta")} className="px-2 py-0.5 rounded border border-outline-variant text-on-surface-variant font-semibold disabled:opacity-40">No contesta</button>
                            </>}
                            {p.estado_cita === "reservada" && <button disabled={enviando} onClick={() => cambiarCita(p, "confirmada")} className="px-2 py-0.5 rounded border border-primary text-primary font-semibold disabled:opacity-40">Confirmó</button>}
                            {["reservada", "confirmada"].includes(p.estado_cita) && <>
                              <button disabled={enviando} onClick={() => cambiarCita(p, "atendida")} className="px-2 py-0.5 rounded border border-hlf text-hlf font-semibold disabled:opacity-40">Atendida</button>
                              <button disabled={enviando} onClick={() => cambiarCita(p, "no_asistio")} className="px-2 py-0.5 rounded border border-ambar text-ambar font-semibold disabled:opacity-40">No asistió</button>
                              <button disabled={enviando} onClick={() => cambiarCita(p, "cancelada")} className="px-2 py-0.5 rounded border border-outline-variant text-on-surface-variant font-semibold disabled:opacity-40">Cancelar</button>
                            </>}
                          </span>
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
        </div>}
      </div>

      {parte === "box" && b?.mapa && <MapaBox mapa={b.mapa} dia={b.dia_agenda} esp={esp} setEsp={setEsp} />}
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
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest";
  return (
    <div className="grid gap-5 lg:grid-cols-12 items-start">
      <Caja titulo="¿Tiene horas libres hoy?" className="lg:col-span-4">
        <p className="text-[13px] text-on-surface-variant mb-3">Indique su especialidad y su tiempo disponible. Se proponen los pacientes de la lista que más lo necesitan, sin repetir a quienes ya tienen una cita reservada hoy. La duración de cada consulta es el promedio de la especialidad en el registro (distinta a la de los box, que dividen su bloque por la capacidad).</p>
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
              {r.excluidos_con_hora_hoy > 0 && <span className="text-on-surface-variant"> Se omiten {r.excluidos_con_hora_hoy} que ya tienen una cita reservada hoy.</span>}
              {r.propuestos_en_box > 0 && <span className="text-on-surface-variant"> {r.propuestos_en_box} también aparecen propuestos en un box (aún sin reservar): coordine para no llamarlos dos veces.</span>}
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
                    {p.propuesto_en_box && <div className="text-[13px] text-on-surface-variant"><Marca>Propuesto también en box {p.propuesto_en_box}</Marca></div>}
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
    <Caja titulo={`Ocupación de los box · agenda del ${fmt(dia)}`} accion={
      <span className="text-[13px] text-on-surface-variant">{activos.length} de {mapa.length} box con agenda · <b className="text-hlf">{libres}</b> horas libres de {capacidad}</span>}>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-10 gap-2">
        {mapa.map((x) => {
          if (!x.especialidad) return (
            <div key={x.id_box} className="rounded border border-dashed border-outline-variant p-2 text-on-surface-variant">
              <div className="font-semibold text-[14px]">{x.id_box.replace("BOX-", "Box ")}</div>
              <div className="text-[12px]">Sin bloque asignado hoy en la agenda</div>
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
      <p className="text-[12px] text-on-surface-variant mt-2">Barra azul: horas ya ocupadas (incluye las citas reservadas hoy) · verde: horas libres, que se proponen arriba. Los box punteados no tienen bloque en la agenda de ese día. Haga clic en un box para ver solo su especialidad.</p>
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
          <li><b>Descompensación grave: requiere evaluación.</b> Evento grave sin estabilización posterior en un diagnóstico cuya fila de la tabla es prioridad alta. Va primero dentro de su prioridad y pide evaluación médica dentro de 72 h (KPI del hospital). El sistema no declara "riesgo vital": eso lo decide el médico. La alerta se cierra con una decisión clínica registrada, una cita o una derivación; si pasan más de 72 h, queda "atrasada".</li>
          <li><b>Orden dentro de cada prioridad</b> (MINSAL, Ord. 536 del 21-03-2025): criterio médico, grupos de especial protección, antigüedad en lista mayor a 1 año y fecha de ingreso. El <b>puntaje LACE</b> es experimental: solo desempata a pacientes con la misma prioridad y antigüedad.</li>
          <li><b>Observaciones</b> que no cambian el orden: posible incumplimiento GES (a verificar, porque el plazo corre desde un hito que el registro no trae); 2 inasistencias consecutivas (posible causal de egreso 8); última medición fuera de rango.</li>
          <li><b>Egreso por fallecimiento</b> (causal 9, Manual de Gestión de la Demanda SSMSO).</li>
        </ol>
      </Caja>
      <Caja titulo="Tabla HLF usada para pacientes descompensados">
        <table className="w-full text-[14px]">
          <thead><tr className="text-left text-on-surface-variant text-[13px] border-b border-outline-variant"><th className="py-1">CIE-10</th><th>Fila de la tabla</th><th>Prioridad</th><th>Pág.</th></tr></thead>
          <tbody>{filas.map(([c, f, pr, pg]) => <tr key={c} className="border-b border-outline-variant/50"><td className="py-1 font-semibold">{c}</td><td>{f}</td><td>{pr}</td><td>{pg}</td></tr>)}</tbody>
        </table>
        <p className="text-[13px] text-on-surface-variant mt-2">I10, K21, F32, F41, G43, E66, M17, M54 y M75 no tienen fila de "descompensado" en la tabla del HLF: mantienen su prioridad y el evento queda visible para revisión clínica.</p>
        <p className="text-[13px] text-ambar mt-1"><b>Equivalencias a validar con los especialistas:</b> K70 (enfermedad hepática alcohólica) se asimila a la fila de cirrosis; I20 incluye toda angina, la fila es solo angina inestable; G40 usa la fila "crisis mensuales" porque no hay fila de epilepsia descompensada.</p>
        <p className="text-[13px] mt-1">Fuente: <a className="text-primary underline" target="_blank" rel="noreferrer" href="https://redsalud.ssmso.cl/wp-content/uploads/2025/07/PRIORIZACION-SSMSO-02.07.2025-I-ETAPA.pdf">Priorización SSMSO 2025 (PDF)</a></p>
      </Caja>
      <Caja titulo="Puntaje LACE (experimental, solo desempate)">
        <p className="mb-2">Índice validado para riesgo de muerte o reingreso no planificado tras un alta hospitalaria (<a className="text-primary underline" target="_blank" rel="noreferrer" href="https://pmc.ncbi.nlm.nih.gov/articles/PMC2845681/">van Walraven et al., <i>CMAJ</i> 2010;182(6):551-7</a>). Estadístico C 0,68–0,71 en Ontario. <b>No está validado para listas de espera</b>: por eso aquí solo desempata.</p>
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
        <p className="text-[13px] text-on-surface-variant mt-1">El plazo corre desde la derivación con sospecha o confirmación diagnóstica; el registro solo trae el ingreso a la lista, así que la herramienta marca "posible incumplimiento: verificar". Fuente: <a className="text-primary underline" target="_blank" rel="noreferrer" href="https://auge.minsal.cl">auge.minsal.cl</a></p>
      </Caja>
      <Caja titulo="Lectura automática de informes">
        <p>Las fotos de informes se leen con Amazon Textract (OCR). Reglas con detección de negaciones buscan urgencias, hospitalizaciones, exámenes alterados y cambios de fármaco, y cada propuesta se valida con Pydantic, citando la frase exacta del documento. Se verifica que el documento sea del paciente. Ninguna prioridad cambia sin confirmación del equipo clínico. No se hacen predicciones: las alertas se basan en eventos ya registrados.</p>
      </Caja>
      <Caja titulo="Datos de esta demostración">
        <p>Registro sintético entregado por el hospital: 500 pacientes, 7 especialidades, eventos hasta el 13-10-2026. No contiene pacientes reales. La versión publicada trabaja con la fecha de hoy en Chile; el modo demostración permite ver la lista en fechas anteriores.</p>
      </Caja>
    </div>
  );
}
