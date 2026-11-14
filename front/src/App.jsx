import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as api from "./api";
import { Icono, Indicador } from "./componentes/comunes";
import { ETIQUETA } from "./constantes";
import { Ficha } from "./ficha/Ficha";
import { Alertas } from "./pantallas/Alertas";
import { Recepcion } from "./pantallas/Recepcion";
import { Decisiones } from "./pantallas/Decisiones";
import { Aprendizaje } from "./pantallas/Aprendizaje";
import { Permisos, ROLES, ROL_TXT, crearPuede, rolesEfectivos } from "./permisos";
import { Criterios } from "./pantallas/Criterios";
import { Indicadores } from "./pantallas/Indicadores";
import { ListaSimple } from "./pantallas/ListaSimple";
import { FILTROS_VACIOS, ListaDetallada } from "./pantallas/ListaDetallada";
import { NuevoPaciente } from "./pantallas/NuevoPaciente";
import { CarrilGES } from "./pantallas/CarrilGES";
import { fmt } from "./util";

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
  const [demo, setDemo] = useState(false);
  const [iFechaSel, setIFecha] = useState(null);
  const iFecha = iFechaSel ?? fechas.length - 1;
  const [esp, setEsp] = useState("Cardiología");  // los especialistas atienden por especialidad: se parte en Cardiología
  const [vista, setVista] = useState("simple");  // página principal: la lista de espera simple, como una planilla
  const [data, setData] = useState(null);
  const [sel, setSel] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [destacado, setDestacado] = useState(null);
  const [error, setError] = useState(null);
  const [filtros, setFiltros] = useState(FILTROS_VACIOS);
  const [actualizando, setActualizando] = useState(false);
  const [nuevo, setNuevo] = useState(false);
  const [usuario, setUsuarioLocal] = useState(api.getUsuario());
  const [rol, setRolLocal] = useState(api.getRol());
  const [yo, setYo] = useState(null);  // GET /yo: con inicio de sesión real trae el nombre y los roles del token
  useEffect(() => { api.getYo().then(setYo).catch(() => setYo(null)); }, []);
  const sesion = yo?.origen === "token";
  const roles = rolesEfectivos(yo, rol);
  const puede = useMemo(() => crearPuede(roles), [roles.join()]); // eslint-disable-line react-hooks/exhaustive-deps
  const [lote, setLote] = useState(null);  // "Recepción de datos" → ver las decisiones de un lote
  const [nPendientes, setNPendientes] = useState(null);
  const fecha = demo ? fechas[iFecha] : fechas[fechas.length - 1];

  const pedido = useRef(0);  // si llegan respuestas en desorden (cambio rápido de especialidad o fecha), vale solo la última
  const cargar = useCallback(async () => {
    if (!info) return;
    const n = ++pedido.current;
    setActualizando(true);
    try { setError(null); const d = await api.getPacientes(fecha, esp === "Todas" ? null : esp); if (n === pedido.current) setData(d); }
    catch (e) { if (n === pedido.current) setError(e.message); } finally { if (n === pedido.current) setActualizando(false); }
  }, [fecha, esp, info]);
  useEffect(() => { cargar(); }, [cargar]);
  // número de decisiones del sistema que esperan revisión (menú "Decisiones"), en la especialidad elegida
  useEffect(() => {
    if (!data) return;
    let vivo = true;
    api.getDecisiones("pendiente", esp === "Todas" ? null : esp, 1000).then((r) => vivo && setNPendientes(r.total)).catch(() => vivo && setNPendientes(null));
    return () => { vivo = false; };
  }, [data, esp]);
  useEffect(() => {
    if (!sel) return setDetalle(null);
    let vigente = true;  // no mostrar la historia de otro paciente si la respuesta llega tarde
    api.getPaciente(sel, fecha).then((d) => vigente && setDetalle(d)).catch(() => vigente && setDetalle(null));
    return () => { vigente = false; };
  }, [sel, fecha, data]);
  // los indicadores de arriba abren la lista detallada con un filtro puesto
  const verLista = (filtro = {}) => { setFiltros({ ...FILTROS_VACIOS, ...filtro }); setVista("lista"); };

  const mostrarAviso = (a) => { setAviso(a); setTimeout(() => setAviso(null), 6000); };
  // un paciente de otra especialidad (p. ej. desde un lote o un criterio) se abre con la lista de todo el hospital
  const abrir = (id) => { if (data && !data.pacientes.some((p) => p.id_paciente === id)) setEsp("Todas"); setSel(id); setVista("lista"); };
  // en pantallas chicas la ficha queda debajo de la lista: bajar hasta ella al elegir un paciente
  useEffect(() => {
    if (sel && window.innerWidth < 1024) setTimeout(() => document.getElementById("ficha")?.scrollIntoView({ behavior: "smooth" }), 150);
  }, [sel]);

  if (!data) return <div className="p-10 text-lg">{error ? `No se pudo cargar la lista: ${error}` : "Cargando lista de espera…"}</div>;
  const paciente = sel && data.pacientes.find((p) => p.id_paciente === sel);
  const vitales = data.pacientes.filter((p) => p.riesgo_vital);
  const porContactar = vitales.filter((p) => p.contactar_hoy);
  const altas = data.pacientes.filter((p) => p.categoria === "alta").length;
  const gesVenc = data.pacientes.filter((p) => p.ges?.vencida).length;
  const tiempoReal = info?.modo === "tiempo_real" && !demo;
  const pendientes = data.pacientes.filter((p) => p.gestion?.estado === "pendiente_revision").length;
  const masDeUnAnio = data.pacientes.filter((p) => p.dias_espera > 365).length;
  // modo de decisión: /health trae el algoritmo; que la IA sea simulada se sabe por el modelo registrado en las evaluaciones
  const modelo = data.pacientes.find((p) => p.rubrica?.modelo)?.rubrica?.modelo;
  const modoDecision = info?.algoritmo === "rubrica" ? (modelo === "simulado" ? ["IA simulada (demostración, sin Amazon Bedrock) + criterios con fuente", "text-ambar"]
    : ["IA con Amazon Bedrock + criterios con fuente", ""]) : ["Solo reglas con fuente (sin IA)", ""];
  const irDecisionesLote = (id) => { setLote(id); setVista("decisiones"); };

  return (
    <Permisos.Provider value={puede}>
    <div className="min-h-screen flex flex-col">
      <header className="bg-surface-container-lowest border-b border-outline-variant">
        <div className="flex h-1.5"><div className="w-1/3 bg-primary" /><div className="w-2/3 bg-gob-rojo" /></div>
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-2 min-h-[72px] flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex items-center gap-3">
            <Logo />
            <div className="leading-tight border-l border-outline-variant pl-3">
              <div className="text-[15px] sm:text-[16px] font-bold text-primary-container">Hospital Clínico Dra. Eloísa Díaz Inzunza</div>
              <div className="hidden sm:block text-[13px] text-on-surface-variant">La Florida · Servicio de Salud Metropolitano Sur Oriente</div>
              <div className="text-[13px] font-semibold text-hlf">Lista de espera dinámica · Consultas de especialidad</div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-[13px]">
            {sesion ? <span className="flex items-center gap-1.5 text-on-surface-variant" title="Identidad del inicio de sesión">
              <Icono n="verified_user" className="text-[18px]" /><b className="text-on-surface">{yo.usuario}</b>
              {(yo.roles || []).map((r) => <span key={r} className="px-1.5 rounded border border-outline-variant text-[12px]">{ROL_TXT[r] || r}</span>)}
              <button onClick={() => api.auth.cerrarSesion()} className="text-primary font-semibold ml-1">Salir</button></span>
              : <>
              <label className="flex items-center gap-1.5 text-on-surface-variant" title="Queda registrado en cada acción (trazabilidad)">
                <Icono n="badge" className="text-[18px]" />
                <input value={usuario} onChange={(e) => { setUsuarioLocal(e.target.value); api.setUsuario(e.target.value); }} placeholder="Su nombre y cargo"
                  className={`h-8 w-40 sm:w-44 px-2 border rounded text-on-surface ${usuario.trim() ? "border-outline-variant" : "border-ambar bg-ambar-container/40"}`} />
              </label>
              <label className="flex items-center gap-1.5 text-on-surface-variant" title="En la demo el rol se elige; en producción viene del inicio de sesión">
                <span className="sr-only sm:not-sr-only">Rol</span>
                <select value={rol} onChange={(e) => { setRolLocal(e.target.value); api.setRol(e.target.value); }} aria-label="Rol"
                  className="h-8 px-1 border border-outline-variant rounded bg-surface-container-lowest text-on-surface">
                  <option value="">Todos (demostración)</option>
                  {ROLES.map((r) => <option key={r} value={r}>{ROL_TXT[r]}</option>)}
                </select>
              </label></>}
            <span className="hidden sm:inline text-on-surface-variant border-l border-outline-variant pl-3">Lista al <b className="text-on-surface">{fmt(fecha)}</b></span>
            <button onClick={cambiarTema} aria-label={oscuro ? "Usar tema claro" : "Usar tema oscuro"} title={oscuro ? "Tema claro" : "Tema oscuro"}
              className="w-9 h-9 flex items-center justify-center rounded border border-outline-variant text-on-surface-variant hover:text-on-surface">
              <Icono n={oscuro ? "light_mode" : "dark_mode"} className="text-[20px]" /></button>
            <label className="flex items-center gap-1.5 text-on-surface-variant cursor-pointer select-none border-l border-outline-variant pl-3">
              <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} className="accent-primary" />Explorar fechas anteriores
            </label>
          </div>
        </div>
        <nav className="max-w-[1400px] mx-auto px-4 sm:px-6 flex gap-5 sm:gap-6 text-[14px] overflow-x-auto whitespace-nowrap" aria-label="Secciones">
          {[["simple", "Lista de espera", null], ["lista", "Lista detallada", null], ["hoy", "Empeoraron", porContactar.length], ["decisiones", "Decisiones", nPendientes],
            ["ges", "Garantías GES", null], ["indicadores", "Indicadores", null], ["aprendizaje", "Aprendizaje", null], ["cargar", "Recepción de datos", null], ["criterios", "Criterios", null]].map(([k, t, n]) => (
            <button key={k} onClick={() => { setVista(k); if (k === "decisiones") setLote(null); }} aria-current={vista === k ? "page" : undefined}
              className={`shrink-0 py-2.5 border-b-2 -mb-px ${vista === k ? "border-primary text-primary font-semibold" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}>
              {t}{n ? <span className={`ml-1.5 px-1.5 rounded-full text-[12px] font-semibold ${k === "decisiones" ? "bg-ambar text-background" : "bg-error text-on-error"}`}
                title={k === "decisiones" ? "Decisiones del sistema que esperan la revisión del especialista" : undefined}>{n}</span> : null}
            </button>
          ))}
        </nav>
      </header>

      <div className="bg-surface-container-high border-b border-outline-variant">
        <div className="max-w-[1400px] mx-auto px-6 py-1.5 text-[13px] flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-semibold flex items-center gap-1"><Icono n="database" className="text-[16px]" />Demo · Datos sintéticos</span>
          <span className="text-on-surface-variant">·</span>
          <span className={`flex items-center gap-1 ${modoDecision[1]}`} title="Cómo decide el sistema la prioridad. La IA solo lee y cita; el sistema decide con criterios con fuente.">
            <Icono n={info?.algoritmo === "rubrica" ? "smart_toy" : "rule"} className="text-[16px]" />Decide: {modoDecision[0]}</span>
          {!sesion && <span className="text-on-surface-variant" title="La API no verifica el rol en la demo">· {rol ? `Rol: ${ROL_TXT[rol]}` : "Todos los roles"} (en la demo el rol se elige; en producción viene del inicio de sesión)</span>}
          <span className="text-on-surface-variant">·</span>
          <span>{tiempoReal ? <>Lista al <b>{fmt(fecha)}</b></> : <>Fecha anterior: lista al <b>{fmt(fecha)}</b>, solo con registros hasta esa fecha</>}</span>
          {tiempoReal && <details className="relative"><summary className="cursor-pointer text-primary">Información de los datos</summary>
            <div className="absolute z-30 mt-1 w-[420px] max-w-[90vw] p-3 rounded border border-outline-variant bg-surface-container-lowest shadow text-[13px]">
              No son pacientes reales. Registro del hospital al <b>{fmt(info?.registro_al || "2026-10-13")}</b>{info?.datos_hasta && <> (último dato clínico: {fmt(info.datos_hasta)})</>}, más lo registrado en esta herramienta. La lista se calcula con la fecha de hoy en Chile.</div></details>}
        </div>
      </div>

      {demo && (
        <div className="bg-ambar-container/60 border-b border-ambar/30">
          <div className="max-w-[1400px] mx-auto px-6 py-2 flex flex-wrap items-center gap-4 text-[13px]">
            <span className="font-semibold text-ambar flex items-center gap-1"><Icono n="history" className="text-[18px]" />Explorando fechas anteriores</span>
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

      <main className="flex-1 max-w-[1400px] w-full mx-auto px-4 sm:px-6 py-5">
        {error && <div className="bg-error-container text-on-error-container p-3 mb-4 rounded">{error}</div>}

        {["lista", "hoy", "cargar", "criterios"].includes(vista) && <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-5">
          <Indicador n={data.total} t="Pacientes en espera · ver todos" onClick={() => verLista()} />
          <Indicador n={porContactar.length} t="Descompensación grave: contactar" tono={porContactar.length ? "rojo" : null} onClick={() => setVista("hoy")} />
          <Indicador n={altas} t="Prioridad alta" onClick={() => verLista({ cat: "alta" })} />
          <Indicador n={pendientes} t="Requieren decisión del especialista" tono={pendientes ? "ambar" : null} onClick={() => verLista({ gestion: "pendiente_revision" })} />
          <Indicador n={masDeUnAnio} t="Esperan más de 1 año" onClick={() => verLista({ esperaLarga: true })} />
          <Indicador n={gesVenc} t="GES: plazo legal superado (ver garantías)" onClick={() => setVista("ges")} />
        </div>}

        {vista === "simple" && <ListaSimple data={data} fecha={fecha} esp={esp} setEsp={setEsp} actualizando={actualizando} onVer={abrir} />}

        {vista === "hoy" && <Alertas vitales={vitales} todosPacientes={data.pacientes} fecha={fecha} esp={esp} setEsp={setEsp} onVer={abrir} onCambio={cargar} onAviso={mostrarAviso} />}
        {vista === "ges" && <CarrilGES data={data} esp={esp} setEsp={setEsp} onVer={abrir} />}
        {vista === "criterios" && <Criterios ia={data.pacientes.some((p) => p.algoritmo === "rubrica")} />}
        {vista === "indicadores" && <Indicadores fecha={fecha} data={data} esp={esp} setEsp={setEsp} onVer={abrir} />}
        {vista === "cargar" && <Recepcion onVerLote={irDecisionesLote} onListo={async (r) => {
          await cargar();
          mostrarAviso({ titulo: `Datos cargados: ${r.resumen.pacientes_nuevos} pacientes nuevos, ${r.resumen.pacientes_actualizados} actualizados, ${r.resumen.eventos} eventos` });
        }} />}
        {vista === "decisiones" && <Decisiones data={data} esp={esp} setEsp={setEsp} fecha={fecha} lote={lote} onQuitarLote={() => setLote(null)} onVer={abrir}
          onCambio={cargar} onAviso={mostrarAviso} onIrAprendizaje={() => setVista("aprendizaje")} />}
        {vista === "aprendizaje" && <Aprendizaje data={data} esp={esp} setEsp={setEsp} fecha={fecha} onVer={abrir} onCambio={cargar} onAviso={mostrarAviso} />}
        {vista === "lista" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            <div className={`${paciente ? "lg:col-span-6 xl:col-span-7" : "lg:col-span-12"} flex flex-col gap-4`}>
              <ListaDetallada data={data} fecha={fecha} esp={esp} setEsp={setEsp} filtros={filtros} setFiltros={setFiltros} sel={sel} setSel={setSel}
                destacado={destacado} demo={demo} actualizando={actualizando} onIngresar={() => setNuevo(true)}>
                {nuevo && <NuevoPaciente fecha={fecha} esp={esp} onCerrar={() => setNuevo(false)} onListo={async (r) => {
                  setNuevo(false); setFiltros(FILTROS_VACIOS); setEsp(r.paciente?.especialidad || esp); await cargar(); setSel(r.id_paciente);
                  mostrarAviso({ titulo: `${r.paciente?.nombre_fantasia} ingresado a la lista` + (r.criterio?.urgencia ? " · DERIVAR HOY A URGENCIA" : r.criterio?.nivel ? ` · criterio clínico: ${r.criterio.nivel}` : ""),
                    despues: r.paciente?.posicion, antes: "—", cat: r.paciente?.categoria });
                }} />}
              </ListaDetallada>
            </div>

            {paciente && <aside className="lg:col-span-6 xl:col-span-5 lg:sticky lg:top-4 flex flex-col gap-3 [&>*]:shrink-0 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:overflow-x-hidden" aria-label="Detalle del paciente" id="ficha">
              <button onClick={() => setSel(null)} className="self-end text-[13px] text-on-surface-variant hover:text-on-surface flex items-center gap-1"><Icono n="close" className="text-[18px]" />Cerrar detalle</button>
              <Ficha key={paciente.id_paciente} p={paciente} total={data.total} detalle={detalle} fecha={fecha} demo={demo} esp={esp} onCambio={cargar} onAviso={mostrarAviso} onVer={setSel}
                onIrAprendizaje={() => setVista("aprendizaje")}
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
    </Permisos.Provider>
  );
}

// Logo oficial del hospital: poner el archivo en front/public/logo-hlf.png. Si no está, se muestra el ícono.
function Logo() {
  const [ok, setOk] = useState(true);
  return ok
    ? <img src="/logo-hlf.png" alt="Hospital Clínico Dra. Eloísa Díaz Inzunza" className="h-14 w-auto object-contain" onError={() => setOk(false)} />
    : <div className="w-9 h-9 rounded bg-primary text-on-primary flex items-center justify-center"><Icono n="local_hospital" className="text-[22px]" /></div>;
}
