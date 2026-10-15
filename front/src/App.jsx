import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as api from "./api";
import { ETIQUETA, POR_PAGINA, fmt } from "./lib/constantes";
import { Caja, Icono, Indicador, Logo } from "./components/ui";
import { Ficha } from "./pantallas/Ficha";
import { Hoy } from "./pantallas/Hoy";
import { Lista } from "./pantallas/Lista";
import { NuevoPaciente } from "./pantallas/NuevoPaciente";

const VISTAS = [["box", "Box del día", "meeting_room"], ["lista", "Lista de espera", "format_list_numbered"]];
const desdeHash = () => { const h = window.location.hash.slice(1); return VISTAS.some(([k]) => k === h) ? h : null; };
const DIA_SEMANA = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const diaSemana = (iso) => DIA_SEMANA[new Date(iso + "T12:00:00Z").getUTCDay()];

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

// Fecha de operación: solo días hábiles con agenda de box. Todo (lista, ficha, box) usa datos con fecha ≤ ese día.
function SelectorDia({ dias, fecha, setFecha }) {
  const i = dias.indexOf(fecha);
  const elegir = (v) => { const d = [...dias].reverse().find((x) => x <= v) || dias[0]; setFecha(d); };
  return (
    <div className="flex items-center gap-1.5" role="group" aria-label="Fecha de operación">
      <button onClick={() => setFecha(dias[i - 1])} disabled={i <= 0} aria-label="Día hábil anterior" className="w-11 h-11 border-2 border-outline-variant flex items-center justify-center disabled:opacity-30"><Icono n="chevron_left" /></button>
      <label className="flex flex-col leading-tight">
        <span className="text-[12px] text-on-surface-variant">Día de operación</span>
        <span className="flex items-center gap-1.5">
          <span className="text-[13px] text-on-surface-variant w-7">{diaSemana(fecha)}</span>
          <input type="date" value={fecha} min={dias[0]} max={dias[dias.length - 1]} onChange={(e) => e.target.value && elegir(e.target.value)}
            className="h-9 px-1.5 border border-outline-variant text-[15px] font-semibold min-h-0" />
        </span>
      </label>
      <button onClick={() => setFecha(dias[i + 1])} disabled={i >= dias.length - 1} aria-label="Día hábil siguiente" className="w-11 h-11 border-2 border-outline-variant flex items-center justify-center disabled:opacity-30"><Icono n="chevron_right" /></button>
    </div>
  );
}

export default function App() {
  const esApi = api.MODO === "api";
  const escritorio = useEscritorio();
  const [oscuro, cambiarTema] = useTema();
  const [dias, setDias] = useState(null);
  const [fecha, setFecha] = useState(null);
  const [esp, setEsp] = useState("Todas");
  const [vista, setVistaState] = useState(() => desdeHash() || "lista");
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

  const setVista = (v) => { if (window.location.hash !== `#${v}`) window.location.hash = v; setVistaState(v); };
  useEffect(() => { const f = () => desdeHash() && setVistaState(desdeHash()); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  useEffect(() => { api.getDias().then((d) => { setDias(d); setFecha(d[d.length - 1]); }).catch((e) => setError(e.message)); }, []);

  const cargar = useCallback(async () => {
    if (!fecha) return;
    try { setError(null); setData(await api.getPacientes(fecha, esp === "Todas" ? null : esp)); }
    catch (e) { setError(e.message); }
  }, [fecha, esp]);
  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    if (!sel || !fecha) return setDetalle(null);
    api.getPaciente(sel, fecha).then(setDetalle).catch(() => setDetalle(null));
  }, [sel, fecha, data]);
  useEffect(() => setMostrar(POR_PAGINA), [busca, filtroCat, soloPend, esp]);

  const filtrados = useMemo(() => {
    if (!data) return [];
    const q = busca.trim().toLowerCase();
    return data.pacientes.filter((p) =>
      (filtroCat === "todas" || (filtroCat === "vital" ? p.contactar_hoy : filtroCat === "citados" ? !!p.cita : filtroCat === "revisar" ? p.revision_sugerida?.length > 0 : p.categoria === filtroCat)) &&
      (!soloPend || p.estado_revision === "pendiente" || p.estado_revision === "requiere_revision") &&
      (!q || p.nombre_fantasia.toLowerCase().includes(q) || p.id_paciente.toLowerCase().includes(q) || p.diagnostico_texto.toLowerCase().includes(q)));
  }, [data, busca, filtroCat, soloPend]);
  // al seleccionar (p. ej. un paciente recién ingresado o desde el box) asegurar que su fila esté visible
  useEffect(() => {
    const i = filtrados.findIndex((p) => p.id_paciente === sel);
    if (i >= mostrar) setMostrar(Math.ceil((i + 1) / POR_PAGINA) * POR_PAGINA);
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps
  // la hoja inferior bloquea el scroll del fondo
  const hoja = !escritorio && vista === "lista" && !!sel;
  useEffect(() => { document.body.style.overflow = hoja ? "hidden" : ""; return () => { document.body.style.overflow = ""; }; }, [hoja]);

  const mostrarAviso = (a) => { setAviso(a); setTimeout(() => setAviso(null), 6000); };
  const abrir = (id) => { setBusca(""); setFiltroCat("todas"); setSoloPend(false); setSel(id); setVista("lista"); };

  if (!data || !fecha) return <div className="p-10 text-lg">{error ? `No se pudo cargar la lista: ${error}` : "Cargando lista de espera…"}</div>;
  const paciente = sel && data.pacientes.find((p) => p.id_paciente === sel);
  const vitales = data.pacientes.filter((p) => p.riesgo_vital);
  const porContactar = vitales.filter((p) => p.contactar_hoy);
  const altas = data.pacientes.filter((p) => p.categoria === "alta").length;
  const citados = data.pacientes.filter((p) => p.cita).length;
  const pendientes = data.pacientes.filter((p) => p.revision_sugerida?.length > 0).length;
  const badge = { box: porContactar.length };
  const ficha = paciente && (
    <Ficha key={paciente.id_paciente} p={paciente} total={data.total} detalle={detalle} fecha={fecha} esApi={esApi} demo onCambio={cargar} onAviso={mostrarAviso}
      onDestacar={(id) => { setDestacado(id); setTimeout(() => setDestacado(null), 3000); }} />
  );

  return (
    <div className={`min-h-screen flex flex-col ${escritorio ? "" : "con-nav-inferior"}`}>
      <a href="#contenido" className="salto">Saltar al contenido</a>
      <header className="bg-surface-container-lowest border-b-2 border-outline-variant">
        <div className="flex h-1.5"><div className="w-1/3 bg-primary" /><div className="w-2/3 bg-gob-rojo" /></div>
        <div className="max-w-[1400px] mx-auto px-4 lg:px-6 py-2 lg:min-h-[72px] flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <div className="flex items-center gap-3 min-w-0">
            <Logo />
            <div className="leading-tight border-l-2 border-outline-variant pl-3 min-w-0">
              <div className="hidden sm:block text-[16px] font-bold text-primary-container truncate">Hospital Clínico Dra. Eloísa Díaz Inzunza</div>
              <div className="sm:hidden text-[16px] font-bold text-primary-container">HLF</div>
              <div className="hidden lg:block text-[14px] text-on-surface-variant">La Florida · Servicio de Salud Metropolitano Sur Oriente</div>
              <div className="text-[14px] font-semibold text-hlf truncate">Lista de espera dinámica<span className="hidden sm:inline"> · Consultas de especialidad</span></div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <SelectorDia dias={dias} fecha={fecha} setFecha={setFecha} />
            <button onClick={cambiarTema} aria-label={oscuro ? "Usar tema claro" : "Usar tema oscuro"} title={oscuro ? "Tema claro" : "Tema oscuro"}
              className="w-11 h-11 flex items-center justify-center border-2 border-outline-variant text-on-surface-variant hover:text-on-surface"><Icono n={oscuro ? "light_mode" : "dark_mode"} /></button>
          </div>
        </div>
        {escritorio && (
          <nav aria-label="Secciones" className="max-w-[1400px] mx-auto px-6 flex gap-1 text-[15px]">
            {VISTAS.map(([k, t]) => (
              <a key={k} href={`#${k}`} onClick={(e) => { e.preventDefault(); setVista(k); }} aria-current={vista === k ? "page" : undefined}
                className={`px-3 py-3 border-b-4 -mb-[2px] ${vista === k ? "border-primary text-primary font-semibold" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}>
                {t}{badge[k] ? <span className="ml-1.5 px-1.5 rounded-full text-[13px] font-semibold bg-error text-on-error">{badge[k]}</span> : null}
              </a>
            ))}
          </nav>
        )}
      </header>

      {!esApi && (
        <div className="bg-ambar-container/60 border-b border-ambar/30">
          <div className="max-w-[1400px] mx-auto px-4 lg:px-6 py-2 text-[14px] font-semibold text-ambar flex items-center gap-1"><Icono n="science" className="text-[18px]" />Sin conexión al servidor: lista precalculada cada 14 días, solo lectura.</div>
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

        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 md:gap-3 mb-5">
          <Indicador n={data.total} t={`En espera al ${fmt(fecha)}`} />
          <Indicador n={porContactar.length} t={`Contactar hoy (de ${vitales.length} con riesgo vital)`} tono={porContactar.length ? "rojo" : null} onClick={() => setVista("box")} />
          <Indicador n={citados} t="Con cupo de box asignado" tono={citados ? "azul" : null} onClick={() => { setVista("lista"); setFiltroCat("citados"); setSoloPend(false); }} />
          <Indicador n={pendientes} t="Requieren revisión del especialista" tono={pendientes ? "ambar" : null} onClick={() => { setVista("lista"); setFiltroCat("revisar"); setSoloPend(false); }} />
          <div className="col-span-2 md:col-span-1"><Indicador n={altas} t="Prioridad alta" /></div>
        </div>

        {vista === "box" && <Hoy vitales={vitales} fecha={fecha} esp={esp} setEsp={setEsp} onVer={abrir} esApi={esApi} onCambio={cargar} onAviso={mostrarAviso} />}
        {vista === "lista" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            <div className="lg:col-span-7 xl:col-span-8 min-w-0">
              <Lista data={data} filtrados={filtrados} fecha={fecha} esp={esp} setEsp={setEsp} busca={busca} setBusca={setBusca} filtroCat={filtroCat} setFiltroCat={setFiltroCat}
                soloPend={soloPend} setSoloPend={setSoloPend} mostrar={mostrar} setMostrar={setMostrar} sel={sel} setSel={setSel} destacado={destacado} demo esApi={esApi}
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
        <nav aria-label="Secciones" className="nav-inferior fixed inset-x-0 bottom-0 z-30 bg-surface-container-lowest border-t-2 border-outline-variant grid grid-cols-2">
          {VISTAS.map(([k, t, ic]) => (
            <button key={k} onClick={() => setVista(k)} aria-current={vista === k ? "page" : undefined}
              className={`relative h-16 flex flex-col items-center justify-center gap-0.5 text-[14px] ${vista === k ? "text-primary font-semibold shadow-[inset_0_3px_0_rgb(var(--c-primary))]" : "text-on-surface-variant"}`}>
              <Icono n={ic} className="text-[24px]" />{t}
              {badge[k] ? <span className="absolute top-1.5 left-1/2 ml-3 min-w-[20px] h-5 px-1 rounded-full text-[12px] font-semibold flex items-center justify-center bg-error text-on-error">{badge[k]}</span> : null}
            </button>
          ))}
        </nav>
      )}

      <footer className="border-t-2 border-outline-variant bg-surface-container-lowest">
        <div className="max-w-[1400px] mx-auto px-4 lg:px-6 py-3 text-[13px] text-on-surface-variant flex flex-wrap justify-between gap-2">
          <span>Prioridad según Tabla de priorización SSMSO 2025 (HLF) y criterios MINSAL. La herramienta propone; el equipo clínico decide.</span>
          <span>Datos sintéticos del HLF · solo registros con fecha ≤ día de operación</span>
        </div>
      </footer>
    </div>
  );
}
