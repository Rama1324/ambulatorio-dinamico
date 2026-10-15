import { motion, AnimatePresence } from "framer-motion";
import { ESPECIALIDADES, POR_PAGINA, fmt } from "../lib/constantes";
import { exportarCsv } from "../lib/exportar";
import { Filtro, Icono, Marca, Prioridad } from "../components/ui";

const BORDE = { alta: "border-l-error", media: "border-l-ambar", baja: "border-l-verde" };

// Observaciones que no cambian el orden (banderas). Mismo set en la tabla y en las tarjetas.
export function Observaciones({ p }) {
  return (
    <div className="flex flex-wrap gap-1">
      {p.contactar_hoy && <Marca tono="rojo">Contactar hoy</Marca>}
      {p.riesgo_vital && !p.contactar_hoy && <Marca tono="azul" title={p.contacto?.texto}>Contactado</Marca>}
      {p.cita && <Marca tono="azul" title={p.cita.pendiente_resultado ? "La cita aún no tiene resultado: registrarlo en Box del día" : "Cupo asignado desde el Box del día"}><Icono n="event_available" className="text-[14px]" /> {p.cita.pendiente_resultado ? "Cita sin resultado" : "Citado"} {p.cita.id_box} · {fmt(p.cita.fecha).slice(0, 5)}</Marca>}
      {!p.riesgo_vital && p.estado_clinico === "descompensado" && <Marca tono="rojo">Descompensado</Marca>}
      {p.senal_temprana && <Marca tono="ambar" title="La medición principal viene empeorando: revisar antes de que llegue el evento">Mediciones empeorando</Marca>}
      {p.revision_sugerida?.length > 0 && !p.senal_temprana && <Marca tono="ambar" title={[...new Set(p.revision_sugerida.map((s) => s.motivo))].join(" · ")}>Revisar</Marca>}
      {p.grupo_proteccion && <Marca tono="azul">{p.grupo_proteccion}</Marca>}
      {p.estado_clinico === "estabilizado" && <Marca>Estabilizado</Marca>}
      {p.ges?.vencida && <Marca tono="azul" title={`GES N°${p.ges.problema}: plazo ${p.ges.plazo_dias} días`}>GES vencida</Marca>}
      {p.riesgo_inasistencia && <Marca tono="ambar" title="2 inasistencias consecutivas (causal 8): confirmar asistencia; no baja la prioridad">2 inasistencias</Marca>}
    </div>
  );
}

const Revision = ({ p }) => p.estado_revision === "pendiente" ? <span className="text-on-surface-variant">Pendiente</span>
  : p.estado_revision === "requiere_revision" ? <span className="text-ambar font-semibold" title={p.revision_vencida_por}><Icono n="update" className="text-[16px]" /> Revisar de nuevo</span>
  : <span className="text-verde font-semibold"><Icono n="check" className="text-[16px]" /> {p.estado_revision === "ajustado" ? "Ajustada" : "Confirmada"}</span>;

const Cambio = ({ p, demo }) => {
  const delta = p.posicion_anterior ? p.posicion_anterior - p.posicion : 0;
  if (!demo || !delta) return null;
  return <span className={`text-[13px] font-semibold ${delta > 0 ? "text-error" : "text-on-surface-variant"}`} title="Cambio respecto del día hábil anterior">{delta > 0 ? `▲ ${delta}` : `▼ ${-delta}`}</span>;
};

export function Lista({ data, filtrados, fecha, esp, setEsp, busca, setBusca, filtroCat, setFiltroCat, soloPend, setSoloPend,
  mostrar, setMostrar, sel, setSel, destacado, demo, esApi, onNuevo }) {
  const visibles = filtrados.slice(0, mostrar);
  const fondo = (p) => sel === p.id_paciente ? "bg-primary/10" : destacado === p.id_paciente ? "bg-ambar-container/60" : "hover:bg-surface-container-low";
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <div className="bg-surface-container-lowest border-2 border-outline-variant p-3 grid grid-cols-2 md:flex md:flex-wrap items-end gap-3 text-[14px]">
        <Filtro label="Especialidad">
          <select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-11 px-2 border border-outline-variant w-full">{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select>
        </Filtro>
        <Filtro label="Prioridad">
          <select value={filtroCat} onChange={(e) => setFiltroCat(e.target.value)} className="h-11 px-2 border border-outline-variant w-full">
            <option value="todas">Todas</option><option value="vital">Contactar hoy</option><option value="citados">Con cupo de box</option><option value="revisar">Requieren revisión</option><option value="alta">Alta</option><option value="media">Media</option><option value="baja">Baja</option>
          </select>
        </Filtro>
        <div className="col-span-2 md:col-span-1"><Filtro label="Buscar paciente">
          <input type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nombre, ID o diagnóstico" className="h-11 px-2 w-full md:w-56 border border-outline-variant" />
        </Filtro></div>
        <label className="col-span-2 md:col-span-1 flex items-center gap-2 h-11 cursor-pointer select-none"><input type="checkbox" checked={soloPend} onChange={(e) => setSoloPend(e.target.checked)} className="w-5 h-5 accent-primary" />Solo pendientes de revisión</label>
        <div className="col-span-2 flex gap-2 md:ml-auto">
          <button onClick={() => exportarCsv(filtrados, fecha)} className="flex-1 md:flex-none h-11 px-3 border border-outline-variant bg-surface-container-lowest font-semibold flex items-center justify-center gap-1"><Icono n="download" className="text-[18px]" />Descargar Excel</button>
          {esApi && <button onClick={onNuevo} className="flex-1 md:flex-none h-11 px-3 bg-primary text-on-primary font-semibold flex items-center justify-center gap-1"><Icono n="person_add" className="text-[18px]" />Ingresar paciente</button>}
        </div>
      </div>

      {/* Escritorio: tabla */}
      <section className="hidden md:block bg-surface-container-lowest border-2 border-outline-variant overflow-hidden">
        <table className="w-full text-left border-collapse text-[15px]">
          <thead>
            <tr className="text-[13px] uppercase tracking-wide text-on-surface-variant border-b-2 border-outline-variant">
              <th className="py-2.5 px-3 font-semibold w-16">N°</th><th className="py-2.5 px-2 font-semibold">Prioridad</th>
              <th className="py-2.5 px-3 font-semibold">Paciente / diagnóstico</th><th className="py-2.5 px-2 font-semibold">Observaciones</th>
              <th className="py-2.5 px-2 font-semibold text-center" title="Índice LACE (van Walraven 2010): ordena dentro de la prioridad">LACE</th>
              <th className="py-2.5 px-3 font-semibold text-right">Espera</th><th className="py-2.5 px-3 font-semibold">Revisión</th>
            </tr>
          </thead>
          <tbody>
            <AnimatePresence initial={false}>
              {visibles.map((p) => (
                <motion.tr key={p.id_paciente} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 32 }} onClick={() => setSel(p.id_paciente)}
                  onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setSel(p.id_paciente))} tabIndex={0}
                  aria-label={`N° ${p.posicion}, ${p.nombre_fantasia}, prioridad ${p.categoria}`}
                  className={`cursor-pointer border-b border-outline-variant/60 ${fondo(p)}`}>
                  <td className={`py-3 px-3 align-top border-l-[6px] ${BORDE[p.categoria]}`}>
                    <div className="font-semibold text-[17px]">{p.posicion}</div>
                    <Cambio p={p} demo={demo} />
                  </td>
                  <td className="py-3 px-2 align-top"><Prioridad cat={p.categoria} /></td>
                  <td className="py-3 px-3 align-top">
                    <div className="font-semibold">{p.nombre_fantasia} <span className="font-normal text-on-surface-variant text-[14px]">· {p.edad} años</span></div>
                    <div className="text-[14px] text-on-surface-variant">{p.especialidad} · {p.diagnostico_cie10} {p.diagnostico_texto}</div>
                  </td>
                  <td className="py-3 px-2 align-top"><Observaciones p={p} /></td>
                  <td className="py-3 px-2 align-top text-center">
                    <span className={`inline-block min-w-[28px] px-1.5 py-px font-semibold ${p.lace?.total ? "bg-primary/10 text-primary-container" : "text-on-surface-variant"}`}>{p.lace?.total ?? "—"}</span>
                  </td>
                  <td className="py-3 px-3 align-top text-right whitespace-nowrap">{p.dias_espera} días{p.antiguedad_mayor_1_anio && <div className="text-[13px] text-error font-semibold">más de 1 año</div>}</td>
                  <td className="py-3 px-3 align-top text-[14px] whitespace-nowrap"><Revision p={p} /></td>
                </motion.tr>
              ))}
            </AnimatePresence>
          </tbody>
        </table>
      </section>

      {/* Móvil: tarjetas */}
      <ul className="md:hidden flex flex-col border-t-2 border-outline-variant" aria-label="Lista priorizada">
        {visibles.map((p) => (
          <li key={p.id_paciente}>
            <button onClick={() => setSel(p.id_paciente)} className={`w-full text-left flex flex-col gap-1.5 px-3 py-3.5 border-l-[6px] ${BORDE[p.categoria]} border-b border-outline-variant bg-surface-container-lowest ${fondo(p)}`}
              aria-label={`N° ${p.posicion}, ${p.nombre_fantasia}, prioridad ${p.categoria}`}>
              <span className="flex items-center gap-2.5 w-full">
                <span className="font-semibold text-[20px] min-w-[2.5ch]">{p.posicion}</span>
                <Prioridad cat={p.categoria} />
                <span className="ml-auto flex items-center gap-2"><Cambio p={p} demo={demo} /><span className={`text-[14px] ${p.antiguedad_mayor_1_anio ? "text-error font-semibold" : "text-on-surface-variant"}`}>{p.dias_espera} d</span></span>
              </span>
              <span className="font-semibold text-[17px] leading-tight">{p.nombre_fantasia} <span className="font-normal text-[14px] text-on-surface-variant">· {p.edad} años</span></span>
              <span className="text-[14px] text-on-surface-variant">{p.especialidad} · {p.diagnostico_cie10} {p.diagnostico_texto}</span>
              <Observaciones p={p} />
            </button>
          </li>
        ))}
      </ul>

      {filtrados.length === 0 && <p className="p-6 text-on-surface-variant">No hay pacientes con esos filtros.</p>}
      <div className="flex flex-wrap items-center justify-between gap-3 text-[14px] text-on-surface-variant">
        <span>Mostrando {visibles.length} de {filtrados.length} · orden: prioridad, contactar hoy, LACE, grupo de protección, más de 1 año, fecha de ingreso</span>
        {visibles.length < filtrados.length && (
          <button onClick={() => setMostrar(mostrar + POR_PAGINA)} className="h-11 px-4 border-2 border-outline-variant bg-surface-container-lowest font-semibold text-on-surface">Mostrar {Math.min(POR_PAGINA, filtrados.length - visibles.length)} más</button>
        )}
      </div>

      {data.excluidos.length > 0 && (
        <details className="bg-surface-container-lowest border-2 border-outline-variant">
          <summary className="px-4 py-3 cursor-pointer text-[15px] font-semibold">
            Egresados de la lista ({data.excluidos.length}): {data.excluidos.filter((e) => e.motivo === "fallecido").length} por fallecimiento · {data.excluidos.filter((e) => e.motivo === "atendido").length} atendidos
          </summary>
          <ul className="px-4 pb-3 text-[14px] text-on-surface-variant">
            {[...data.excluidos].sort((a, b) => (b.fecha || "").localeCompare(a.fecha || "")).map((e) => (
              <li key={e.id_paciente} className="py-1.5 border-t border-outline-variant/60 flex flex-wrap justify-between gap-x-2">
                <span>{e.nombre_fantasia || e.id_paciente} · {e.especialidad}</span>
                <span>{e.motivo === "fallecido" ? `Fallecimiento ${fmt(e.fecha)} · causal 9` : `Atendido en consulta nueva ${fmt(e.fecha)}`}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
