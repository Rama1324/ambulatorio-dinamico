import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as api from "./api";
import { ETIQUETA, POR_PAGINA, fmt } from "./lib/constantes";
import { Caja, Icono, Indicador, Logo } from "./components/ui";
import { CargarDatos } from "./pantallas/CargarDatos";
import { Chat } from "./pantallas/Chat";
import { Criterios } from "./pantallas/Criterios";
import { Ficha } from "./pantallas/Ficha";
import { Hoy } from "./pantallas/Hoy";
import { Indicadores } from "./pantallas/Indicadores";
import { Lista } from "./pantallas/Lista";
import { NuevoPaciente } from "./pantallas/NuevoPaciente";

const VISTAS = [
  ["hoy", "Hoy", "today"], ["chat", "Chat", "chat"], ["lista", "Lista", "format_list_numbered"], ["datos", "Datos", "upload_file"],
  ["indicadores", "Indicadores", "monitoring"], ["criterios", "Criterios", "gavel"],
];
const NOMBRE = { hoy: "Hoy", chat: "Chat del paciente", lista: "Lista de espera", datos: "Cargar datos", indicadores: "Indicadores", criterios: "Criterios" };
const desdeHash = () => { const h = window.location.hash.slice(1); return VISTAS.some(([k]) => k === h) ? h : null; };

// Escritorio = ≥ 1024 px (lg): ficha al costado. Debajo: ficha como hoja inferior y barra de pestañas abajo.
function useEscritorio() {
  const mq = "(min-width: 1024px)";
  const [ok, setOk] = useState(() => window.matchMedia(mq).matches);
  useEffect(() => { const m = window.matchMedia(mq); const f = () => setOk(m.matches); m.addEventListener("change", f); return () => m.removeEventListener("change", f); }, []);
  return ok;
}
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
  const fechas = api.fechas();
  const esApi = api.MODO === "api";
  const escritorio = useEscritorio();
  const [oscuro, cambiarTema] = useTema();
  const [demo, setDemo] = useState(!esApi);
  const [iFecha, setIFecha] = useState(fechas.length - 1);
  const [esp, setEsp] = useState("Todas");
  const [vista, setVistaState] = useState(() => desdeHash() || (esApi ? "hoy" : "lista"));
  const [data, setData] = useState(null);
  const [sel, setSel] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [destacado, setDestacado] = useState(null);
  const [error, setError] = useState(null);
  const [busca, setBusca] = useState("");
  const [filtroCat, setFiltroCat] = useState("todas");
  const [soloPend, setSoloPend] = useState(false);
  const [mostrar, setMostrar] = useState(POR_PAGINA);
  const [nuevo, setNuevo] = useState(false);
  const [mas, setMas] = useState(false);
  const fecha = demo ? fechas[iFecha] : fechas[fechas.length - 1];

  const setVista = (v) => { setMas(false); if (window.location.hash !== `#${v}`) window.location.hash = v; setVistaState(v); };
  useEffect(() => { const f = () => desdeHash() && setVistaState(desdeHash()); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);

  const cargar = useCallback(async () => {
    try { setError(null); setData(await api.getPacientes(fecha, esp === "Todas" ? null : esp)); }
    catch (e) { setError(e.message); }
  }, [fecha, esp]);
  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    if (!sel) return setDetalle(null);
    api.getPaciente(sel, fecha).then(setDetalle).catch(() => setDetalle(null));
  }, [sel, fecha, data]);
  useEffect(() => setMostrar(POR_PAGINA), [busca, filtroCat, soloPend, esp]);

  const filtrados = useMemo(() => {
    if (!data) return [];
    const q = busca.trim().toLowerCase();
    return data.pacientes.filter((p) =>
      (filtroCat === "todas" || (filtroCat === "vital" ? p.contactar_hoy : filtroCat === "chat" ? !!p.autoreporte : filtroCat === "revisar" ? p.revision_sugerida?.length > 0 : p.categoria === filtroCat)) &&
      (!soloPend || p.estado_revision === "pendiente" || p.estado_revision === "requiere_revision") &&
      (!q || p.nombre_fantasia.toLowerCase().includes(q) || p.id_paciente.toLowerCase().includes(q) || p.diagnostico_texto.toLowerCase().includes(q)));
  }, [data, busca, filtroCat, soloPend]);
  // al seleccionar (p. ej. un paciente recién ingresado o desde el chat) asegurar que su fila esté visible
  useEffect(() => {
    const i = filtrados.findIndex((p) => p.id_paciente === sel);
    if (i >= mostrar) setMostrar(Math.ceil((i + 1) / POR_PAGINA) * POR_PAGINA);
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps
  // la hoja inferior bloquea el scroll del fondo
  const hoja = !escritorio && vista === "lista" && !!sel;
  useEffect(() => { document.body.style.overflow = hoja ? "hidden" : ""; return () => { document.body.style.overflow = ""; }; }, [hoja]);

  const mostrarAviso = (a) => { setAviso(a); setTimeout(() => setAviso(null), 6000); };
  const abrir = (id) => { setBusca(""); setFiltroCat("todas"); setSoloPend(false); setSel(id); setVista("lista"); };

  if (!data) return <div className="p-10 text-lg">{error ? `No se pudo cargar la lista: ${error}` : "Cargando lista de espera…"}</div>;
  const paciente = sel && data.pacientes.find((p) => p.id_paciente === sel);
  const vitales = data.pacientes.filter((p) => p.riesgo_vital || p.alerta_chat);
  const porContactar = vitales.filter((p) => p.contactar_hoy);
  const altas = data.pacientes.filter((p) => p.categoria === "alta").length;
  const chatPend = data.pacientes.filter((p) => p.autoreporte).length;
  const pendientes = data.pacientes.filter((p) => p.revision_sugerida?.length > 0).length;
  const badge = { hoy: porContactar.length, lista: chatPend };
  const ficha = paciente && (
    <Ficha key={paciente.id_paciente} p={paciente} total={data.total} detalle={detalle} fecha={fecha} esApi={esApi} demo={demo} onCambio={cargar} onAviso={mostrarAviso}
      onDestacar={(id) => { setDestacado(id); setTimeout(() => setDestacado(null), 3000); }} />
  );

  return (
    <div className={`min-h-screen flex flex-col ${escritorio ? "" : "con-nav-inferior"}`}>
      <a href="#contenido" className="salto">Saltar al contenido</a>
      <header className="bg-surface-container-lowest border-b-2 border-outline-variant">
        <div className="flex h-1.5"><div className="w-1/3 bg-primary" /><div className="w-2/3 bg-gob-rojo" /></div>
        <div className="max-w-[1400px] mx-auto px-4 lg:px-6 h-16 lg:h-[72px] flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <Logo />
            <div className="leading-tight border-l-2 border-outline-variant pl-3 min-w-0">
              <div className="hidden sm:block text-[16px] font-bold text-primary-container truncate">Hospital Clínico Dra. Eloísa Díaz Inzunza</div>
              <div className="sm:hidden text-[16px] font-bold text-primary-container">HLF · {NOMBRE[vista]}</div>
              <div className="hidden lg:block text-[14px] text-on-surface-variant">La Florida · Servicio de Salud Metropolitano Sur Oriente</div>
              <div className="text-[14px] font-semibold text-hlf truncate">Lista de espera dinámica<span className="hidden sm:inline"> · Consultas de especialidad</span></div>
            </div>
          </div>
          <div className="flex items-center gap-3 text-[14px] shrink-0">
            <span className="hidden md:inline text-on-surface-variant">Lista al <b className="text-on-surface">{fmt(fecha)}</b></span>
            <label className="hidden lg:flex items-center gap-1.5 text-on-surface-variant cursor-pointer select-none border-l-2 border-outline-variant pl-3">
              <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} className="w-4 h-4 accent-primary" />Modo demostración
            </label>
            <button onClick={cambiarTema} aria-label={oscuro ? "Usar tema claro" : "Usar tema oscuro"} title={oscuro ? "Tema claro" : "Tema oscuro"}
              className="w-11 h-11 flex items-center justify-center border-2 border-outline-variant text-on-surface-variant hover:text-on-surface"><Icono n={oscuro ? "light_mode" : "dark_mode"} /></button>
          </div>
        </div>
        {escritorio && (
          <nav aria-label="Secciones" className="max-w-[1400px] mx-auto px-6 flex gap-1 text-[15px]">
            {VISTAS.map(([k, t]) => (
              <a key={k} href={`#${k}`} onClick={(e) => { e.preventDefault(); setVista(k); }} aria-current={vista === k ? "page" : undefined}
                className={`px-3 py-3 border-b-4 -mb-[2px] ${vista === k ? "border-primary text-primary font-semibold" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}>
                {t === "Chat" ? "Chat del paciente" : t === "Lista" ? "Lista de espera" : t === "Datos" ? "Cargar datos" : t}
                {badge[k] ? <span className={`ml-1.5 px-1.5 rounded-full text-[13px] font-semibold ${k === "hoy" ? "bg-error text-on-error" : "bg-primary text-on-primary"}`}>{badge[k]}</span> : null}
              </a>
            ))}
          </nav>
        )}
      </header>

      {demo && (
        <div className="bg-ambar-container/60 border-b border-ambar/30">
          <div className="max-w-[1400px] mx-auto px-4 lg:px-6 py-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[14px]">
            <span className="font-semibold text-ambar flex items-center gap-1"><Icono n="science" className="text-[18px]" />Modo demostración{!esApi && " (datos precalculados, sin API)"}</span>
            <label className="flex items-center gap-2 flex-1 min-w-[240px]">
              <span>Ver la lista como estaba el <b>{fmt(fechas[iFecha])}</b></span>
              <input type="range" min={0} max={fechas.length - 1} value={iFecha} onChange={(e) => setIFecha(+e.target.value)} className="flex-1 accent-ambar min-h-0" />
            </label>
            <span className="hidden md:inline text-on-surface-variant">Solo se usan registros con fecha anterior o igual.</span>
          </div>
        </div>
      )}

      <AnimatePresence>
        {aviso && (
          <div className="fixed top-4 inset-x-4 z-[60] flex justify-center pointer-events-none">
            <motion.div role="status" initial={{ y: -8, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ opacity: 0 }}
              className="max-w-full bg-on-surface text-background px-4 py-2.5 shadow-lg text-[15px] flex flex-wrap items-center gap-2 pointer-events-auto">
              <Icono n="check_circle" className="text-[20px]" />{aviso.titulo}
              {aviso.antes != null && <span className="opacity-90">· posición {aviso.antes} → <b>{aviso.despues}</b>{aviso.cat && ` · prioridad ${ETIQUETA[aviso.cat]}`}</span>}
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <main id="contenido" tabIndex={-1} className="flex-1 max-w-[1400px] w-full mx-auto px-4 lg:px-6 py-5 outline-none">
        {error && <div className="bg-error-container text-on-error-container p-3 mb-4">{error}</div>}

        {(vista === "hoy" || vista === "lista") && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 md:gap-3 mb-5">
            <Indicador n={data.total} t="Pacientes en espera" />
            <Indicador n={porContactar.length} t={`Contactar hoy (de ${vitales.length} con riesgo vital o alerta)`} tono={porContactar.length ? "rojo" : null} onClick={() => setVista("hoy")} />
            <Indicador n={chatPend} t="Datos del chat por validar" tono={chatPend ? "azul" : null} onClick={() => { setVista("lista"); setFiltroCat("chat"); setSoloPend(false); }} />
            <Indicador n={pendientes} t="Requieren revisión del especialista" tono={pendientes ? "ambar" : null} onClick={() => { setVista("lista"); setFiltroCat("revisar"); setSoloPend(false); }} />
            <div className="col-span-2 md:col-span-1"><Indicador n={altas} t="Prioridad alta" /></div>
          </div>
        )}

        {vista === "hoy" && <Hoy vitales={vitales} fecha={fecha} esp={esp} setEsp={setEsp} onVer={abrir} esApi={esApi} />}
        {vista === "chat" && <Chat pacientes={data.pacientes} fecha={fecha} onVerLista={() => sel && abrir(sel)}
          onEnviado={async (r) => { await cargar(); setSel(r.id_paciente); mostrarAviso({ titulo: `Chat ${r.autoreporte.id_autoreporte} recibido: queda por validar en la ficha del paciente` }); }} />}
        {vista === "criterios" && <Criterios />}
        {vista === "indicadores" && <Indicadores fecha={fecha} esApi={esApi} data={data} />}
        {vista === "datos" && <CargarDatos esApi={esApi} onListo={async (r) => {
          await cargar();
          mostrarAviso({ titulo: `Datos cargados: ${r.resumen.pacientes_nuevos} pacientes nuevos, ${r.resumen.pacientes_actualizados} actualizados, ${r.resumen.eventos} eventos` });
        }} />}
        {vista === "lista" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            <div className="lg:col-span-7 xl:col-span-8 min-w-0">
              <Lista data={data} filtrados={filtrados} fecha={fecha} esp={esp} setEsp={setEsp} busca={busca} setBusca={setBusca} filtroCat={filtroCat} setFiltroCat={setFiltroCat}
                soloPend={soloPend} setSoloPend={setSoloPend} mostrar={mostrar} setMostrar={setMostrar} sel={sel} setSel={setSel} destacado={destacado} demo={demo} esApi={esApi}
                onNuevo={() => setNuevo(true)} />
              {nuevo && <NuevoPaciente fecha={fecha} onCerrar={() => setNuevo(false)} onListo={async (r) => {
                setNuevo(false); setBusca(""); setFiltroCat("todas"); setSoloPend(false); await cargar(); setSel(r.id_paciente);
                mostrarAviso({ titulo: `${r.paciente?.nombre_fantasia} ingresado a la lista`, despues: r.paciente?.posicion, antes: "—", cat: r.paciente?.categoria });
              }} />}
            </div>
            {escritorio && (
              <aside aria-label="Detalle del paciente" className="lg:col-span-5 xl:col-span-4 lg:sticky lg:top-4 flex flex-col gap-3 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
                {ficha || <Caja><p className="text-on-surface-variant">Seleccione un paciente para ver por qué está en esa posición.</p></Caja>}
              </aside>
            )}
          </div>
        )}
      </main>

      {hoja && ficha && (
        <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label={`Detalle de ${paciente.nombre_fantasia}`}>
          <div className="absolute inset-0 bg-black/45" onClick={() => setSel(null)} />
          <div className="absolute inset-x-0 bottom-0 max-h-[90vh] overflow-y-auto bg-background border-t-2 border-outline-variant" style={{ paddingBottom: "env(safe-area-inset-bottom)", "--ficha-top": "62px" }}>
            <div className="sticky top-0 z-20 bg-background border-b-2 border-outline-variant flex items-center gap-2 px-4 py-2">
              <span className="flex-1 text-[14px] text-on-surface-variant">N° {paciente.posicion} de {data.total} · {paciente.id_paciente}</span>
              <button onClick={() => setSel(null)} aria-label="Cerrar detalle" className="w-11 h-11 flex items-center justify-center"><Icono n="close" /></button>
            </div>
            <div className="p-3 flex flex-col gap-3">{ficha}</div>
          </div>
        </div>
      )}

      {!escritorio && (
        <nav aria-label="Secciones" className="nav-inferior fixed inset-x-0 bottom-0 z-30 bg-surface-container-lowest border-t-2 border-outline-variant grid grid-cols-5">
          {[...VISTAS.slice(0, 4), ["mas", "Más", "menu"]].map(([k, t, ic]) => {
            const activo = k === "mas" ? mas || vista === "indicadores" || vista === "criterios" : vista === k && !mas;
            return (
              <button key={k} onClick={() => (k === "mas" ? setMas(!mas) : setVista(k))} aria-current={activo ? "page" : undefined} aria-expanded={k === "mas" ? mas : undefined}
                className={`relative h-16 flex flex-col items-center justify-center gap-0.5 text-[13px] ${activo ? "text-primary font-semibold shadow-[inset_0_3px_0_rgb(var(--c-primary))]" : "text-on-surface-variant"}`}>
                <Icono n={ic} className="text-[24px]" />{t}
                {badge[k] ? <span className={`absolute top-1.5 left-1/2 ml-2 min-w-[20px] h-5 px-1 rounded-full text-[12px] font-semibold flex items-center justify-center ${k === "hoy" ? "bg-error text-on-error" : "bg-primary text-on-primary"}`}>{badge[k]}</span> : null}
              </button>
            );
          })}
        </nav>
      )}
      {!escritorio && mas && (
        <div className="fixed inset-0 z-[35]" onClick={() => setMas(false)}>
          <div className="absolute inset-x-0 bottom-[calc(64px+env(safe-area-inset-bottom))] bg-surface-container-lowest border-t-2 border-outline-variant p-2 flex flex-col" onClick={(e) => e.stopPropagation()}>
            {VISTAS.slice(4).map(([k, t, ic]) => (
              <button key={k} onClick={() => setVista(k)} className="h-12 px-3 flex items-center gap-3 text-[16px] text-left"><Icono n={ic} />{t}</button>
            ))}
            <label className="h-12 px-3 flex items-center gap-3 text-[16px] border-t border-outline-variant"><input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} className="w-5 h-5 accent-primary" />Modo demostración</label>
          </div>
        </div>
      )}

      <footer className="border-t-2 border-outline-variant bg-surface-container-lowest">
        <div className="max-w-[1400px] mx-auto px-4 lg:px-6 py-3 text-[13px] text-on-surface-variant flex flex-wrap justify-between gap-2">
          <span>Prioridad según Tabla de priorización SSMSO 2025 (HLF) y criterios MINSAL. La herramienta propone; el equipo clínico decide.</span>
          <span>Datos sintéticos de demostración</span>
        </div>
      </footer>
    </div>
  );
}
