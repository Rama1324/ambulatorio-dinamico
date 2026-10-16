import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as api from "../api";
import { descargarExcel } from "../excel";
import { Filtro, Icono, Prioridad } from "../componentes/comunes";
import { ESPECIALIDADES, ETIQUETA, ESTILO_GESTION, EVAL_TXT, FACTOR } from "../constantes";
import { fmt, fmtHace, hace } from "../util";

const POR_PAGINA = 25;

const FILTRO_CAT = { todas: "Todas", alta: "Alta", media: "Media", baja: "Baja", vital: "Descompensación grave", ges: "GES: verificar plazo" };

const FILTRO_GESTION = { todos: "Todos", pendiente_revision: "Decisión del especialista", pendiente_contacto: "Pendiente de contacto",
  pendiente_cita: "Pendiente de cita", cita_reservada: "Cita reservada",
  sin_responsable: "Sin responsable", seguimiento_vencido: "Seguimiento vencido" };

// Prioridad propuesta por el sistema vs. confirmada por el equipo (quién y cuándo)
function EstadoPrioridad({ p }) {
  const r = p.revision;
  if (p.estado_revision === "confirmado") return <div className="text-[11px] text-verde mt-0.5 whitespace-nowrap" title={r && `${r.usuario} · ${fmt(r.fecha)}`}>✓ confirmada</div>;
  if (p.estado_revision === "ajustado") return <div className="text-[11px] text-verde mt-0.5 whitespace-nowrap" title={r && `${r.usuario} · ${fmt(r.fecha)}: ${r.motivo}`}>✓ ajustada</div>;
  if (p.estado_revision === "requiere_revision") return <div className="text-[11px] text-ambar mt-0.5 whitespace-nowrap">cambió tras la revisión</div>;
  return p.categoria_sistema !== p.prioridad_inicial
    ? <div className="text-[11px] text-ambar mt-0.5 whitespace-nowrap" title={`La SIC tenía prioridad ${p.prioridad_inicial}. Rige desde ya; el especialista puede cambiarla.`}>actualizada por el sistema</div>
    : <div className="text-[11px] text-on-surface-variant mt-0.5 whitespace-nowrap">asignada en la SIC</div>;
}

const Marca = ({ children, tono = "gris", title }) => {
  const t = { rojo: "text-error border-error/40 bg-error-container/50", ambar: "text-ambar border-ambar/40 bg-ambar-container/50", gris: "text-on-surface-variant border-outline-variant bg-surface-container-low", azul: "text-primary border-primary/30 bg-primary/5" }[tono];
  return <span title={title} className={`inline-block px-1.5 py-px rounded border text-[12px] whitespace-nowrap ${t}`}>{children}</span>;
};

export const FILTROS_VACIOS = { busca: "", cat: "todas", gestion: "todos", esperaLarga: false, dias: 365 };

// Lista detallada: filtros, tabla con estado de gestión y egresados. Los filtros viven en App porque los
// indicadores de arriba los fijan (por ejemplo, "Prioridad alta" abre esta lista ya filtrada).
export function ListaDetallada({ data, fecha, esp, setEsp, filtros, setFiltros, sel, setSel, destacado, demo, actualizando, onIngresar, children }) {
  const { busca, cat: filtroCat, gestion: filtroGestion, esperaLarga, dias: diasEspera } = filtros;
  const fijar = (k) => (v) => setFiltros((f) => ({ ...f, [k]: v }));
  const [setBusca, setFiltroCat, setFiltroGestion, setEsperaLarga, setDiasEspera] = ["busca", "cat", "gestion", "esperaLarga", "dias"].map(fijar);
  const [pagina, setPagina] = useState(0);

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    const g = (p) => p.gestion || {};
    return data.pacientes.filter((p) =>
      (filtroCat === "todas" || (filtroCat === "vital" ? p.riesgo_vital : filtroCat === "ges" ? p.ges?.vencida : p.categoria === filtroCat)) &&
      (filtroGestion === "todos" || (filtroGestion === "sin_responsable" ? !g(p).responsable
        : filtroGestion === "seguimiento_vencido" ? g(p).seguimiento_vencido : g(p).estado === filtroGestion)) &&
      (!esperaLarga || p.dias_espera > (Number(diasEspera) || 0)) &&
      (!q || p.nombre_fantasia.toLowerCase().includes(q) || p.id_paciente.toLowerCase().includes(q) || p.diagnostico_texto.toLowerCase().includes(q)));
  }, [data, busca, filtroCat, filtroGestion, esperaLarga, diasEspera]);
  useEffect(() => setPagina(0), [filtros, esp]);
  // al seleccionar (p. ej. un paciente recién ingresado) saltar a la página donde está
  useEffect(() => {
    const i = filtrados.findIndex((p) => p.id_paciente === sel);
    if (i >= 0) setPagina(Math.floor(i / POR_PAGINA));
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  const hayFiltros = busca || filtroCat !== "todas" || filtroGestion !== "todos" || esperaLarga || esp !== "Todas";
  const limpiarFiltros = () => { setFiltros(FILTROS_VACIOS); setEsp("Todas"); };
  const pag = filtrados.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA);
  const paginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));

  return (
    <>
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
      <label className="flex items-center gap-2 h-9 cursor-pointer select-none" title="Pacientes que llevan más de esa cantidad de días en lista">
        <input type="checkbox" checked={esperaLarga} onChange={(e) => setEsperaLarga(e.target.checked)} className="w-4 h-4 accent-primary" />Espera de más de
        <input type="number" min={0} step={30} value={diasEspera} onChange={(e) => { setDiasEspera(e.target.value); setEsperaLarga(true); }} aria-label="Días mínimos de espera"
          className="h-8 w-20 px-2 border border-outline-variant rounded" />días</label>
      {hayFiltros && <button onClick={limpiarFiltros} className="h-9 px-2 text-primary font-semibold flex items-center gap-1"><Icono n="filter_alt_off" className="text-[18px]" />Limpiar filtros</button>}
      <button onClick={() => exportarExcel(filtrados, fecha, { excluidos: data.excluidos, filtros: [["Especialidad", esp], ["Búsqueda", busca || "(ninguna)"],
        ["Prioridad", FILTRO_CAT[filtroCat]], ["Estado de gestión", FILTRO_GESTION[filtroGestion]],
        ["Espera mínima", esperaLarga ? `${diasEspera} días` : "(sin filtro)"]] })} className="ml-auto h-9 px-3 rounded border border-outline-variant bg-surface-container-lowest font-semibold flex items-center gap-1"><Icono n="download" className="text-[18px]" />Exportar a Excel</button>
      <button onClick={onIngresar} className="h-9 px-3 rounded bg-primary text-on-primary font-semibold flex items-center gap-1"><Icono n="person_add" className="text-[18px]" />Ingresar paciente</button>
    </div>
    {children}

    <section className="bg-surface-container-lowest border border-outline-variant rounded relative max-lg:overflow-x-auto" aria-busy={actualizando}>
      {actualizando && <div className="absolute inset-x-0 top-0 z-20 flex justify-center pt-12 pointer-events-none">
        <span className="bg-on-surface text-background text-[13px] px-3 py-1.5 rounded shadow flex items-center gap-1"><Icono n="progress_activity" className="text-[16px] animate-spin" />Actualizando…</span></div>}
      <table className={`w-full max-lg:min-w-[820px] text-left border-collapse text-[14px] ${actualizando ? "opacity-40 pointer-events-none" : ""}`}>
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
                      {p.urgencia_hoy && <Marca tono="rojo" title="Cumple una excepción de urgencia de los criterios clínicos: no debe esperar cita electiva">Derivar hoy a urgencia</Marca>}
                      {p.contactar_hoy && p.riesgo_vital && <Marca tono="rojo" title={`Descompensación grave del ${fmtHace(p.evaluacion?.fecha_evento, fecha)}: la prioridad ya se actualizó; contactar al paciente`}>
                        Descompensación grave</Marca>}
                      {p.riesgo_vital && p.evaluacion?.fecha_evento && <span className="text-[12px] text-error font-semibold self-center">evento grave {hace(p.evaluacion.fecha_evento, fecha)}</span>}
                      {p.riesgo_vital && !p.contactar_hoy && p.evaluacion?.cierre && <Marca tono="azul" title={p.evaluacion.cierre.texto}>Prioridad revisada</Marca>}
                      {p.riesgo_vital && !p.contactar_hoy && !p.evaluacion?.cierre && p.contactado && <Marca tono="azul" title={`${p.contactado.texto} · ${p.contactado.usuario || ""}`}>Contactado</Marca>}
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
    </>
  );
}

const REV_TXT = { pendiente: "Pendiente", confirmado: "Confirmada", ajustado: "Ajustada", requiere_revision: "Requiere nueva revisión" };

function exportarExcel(pacientes, fecha, { excluidos = [], filtros = [] } = {}) {
  const lista = [["N°", "N° en su especialidad", "Prioridad", "Prioridad inicial (SIC)", "Paciente", "RUT / ID", "Edad", "Sexo", "Comuna", "Especialidad",
    "CIE-10", "Diagnóstico", "Fecha ingreso", "Días de espera", "Más de 1 año", "Estado clínico", "Descompensación grave: evaluación",
    "Días desde el evento", "Revisión de la prioridad", "Revisión sugerida por", "Ajuste manual", "Posición según el sistema", "GES: verificar plazo",
    "2 inasistencias seguidas", "LACE (experimental)"],
    ...pacientes.map((p) => [p.posicion, p.posicion_especialidad ?? "", ETIQUETA[p.categoria], p.prioridad_inicial, p.nombre_fantasia, p.rut || p.id_paciente,
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
