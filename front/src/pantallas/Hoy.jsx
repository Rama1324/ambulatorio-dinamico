import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../api";
import { ESPECIALIDADES, fmt } from "../lib/constantes";
import { Caja, Icono, Prioridad } from "../components/ui";

const ESTADO = { citado: "Citado", confirmado: "Confirmó", asistio: "Asistió", no_asistio: "No asistió", cancelo: "Canceló" };
const TONO = { citado: "text-primary", confirmado: "text-primary", asistio: "text-verde", no_asistio: "text-ambar", cancelo: "text-on-surface-variant" };

// Box del día: disponibilidad real = capacidad − cupos usados en la agenda − citas activas del sistema.
// Asignar ocupa un cupo; "no asistió" o "canceló" lo liberan y el siguiente de la lista queda sugerido.
export function Hoy({ vitales, fecha, esp, setEsp, onVer, esApi, onCambio, onAviso }) {
  const [b, setB] = useState(null);
  const [err, setErr] = useState(null);
  const [sel, setSel] = useState(null);
  const [ocupado, setOcupado] = useState(null);
  const panel = useRef(null);

  const cargar = useCallback(() => {
    if (!esApi) return setErr("La agenda de box requiere conexión al servidor.");
    setErr(null);
    api.getBoxes(fecha).then(setB).catch((e) => setErr(e.message));
  }, [fecha, esApi]);
  useEffect(() => { setB(null); cargar(); }, [cargar]);

  const accion = async (clave, fn, aviso) => {
    setOcupado(clave);
    try { const r = await fn(); setB(r.boxes); await onCambio(); onAviso(aviso(r)); }
    catch (e) { onAviso({ titulo: "No se pudo completar: " + e.message }); }
    finally { setOcupado(null); }
  };
  const asignar = (id_box, id_paciente) => accion(`a-${id_box}-${id_paciente || ""}`,
    () => api.postAsignar({ fecha: b.dia_agenda, id_box, id_paciente }),
    (r) => ({ titulo: `Cupo en ${r.cita.id_box} asignado a ${r.cita.nombre_fantasia} (N° ${r.cita.posicion_al_citar}). Contactar para confirmar.` }));
  const estado = (c, e) => accion(`e-${c.id_cita}-${e}`, () => api.postEstadoCita(c.id_cita, e),
    (r) => ({ titulo: `${c.nombre_fantasia}: ${r.texto}` }));
  const abrirBox = (id) => { setSel(id); setTimeout(() => panel.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50); };

  if (err) return <Caja><p className="text-on-surface-variant">{err}</p></Caja>;
  if (!b) return <p className="text-on-surface-variant">Cargando agenda del día…</p>;

  const filtra = (e) => esp === "Todas" || e === esp;
  const asigs = b.especialidades.flatMap((e) => e.asignaciones.map((a) => ({ ...a, esp: e })));
  const libresPorEsp = (e) => asigs.filter((a) => a.especialidad === e && a.libres > 0).sort((x, y) => y.libres - x.libres)[0];
  const box = sel && asigs.find((a) => a.id_box === sel);
  const contactar = vitales.filter((p) => filtra(p.especialidad)).sort((x, y) => (y.contactar_hoy - x.contactar_hoy) || x.posicion - y.posicion);
  const mapa = b.mapa.filter((x) => !x.especialidad || filtra(x.especialidad));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-bold leading-tight">Box del día · {fmt(b.dia_agenda)}</h1>
          <p className="text-[15px] text-on-surface-variant">Bloque 08:30–13:30 · <b className="text-hlf">{b.totales.libres}</b> cupos libres de {b.totales.capacidad} · {b.totales.citas_sistema} cita{b.totales.citas_sistema === 1 ? "" : "s"} asignada{b.totales.citas_sistema === 1 ? "" : "s"} desde la lista</p>
        </div>
        <label className="flex flex-col gap-1 text-[14px] text-on-surface-variant">Especialidad
          <select value={esp} onChange={(e) => { setEsp(e.target.value); setSel(null); }} className="h-11 px-2 border border-outline-variant text-on-surface">{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select>
        </label>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 items-start">
        <Caja titulo={`Contactar hoy (${contactar.filter((p) => p.contactar_hoy).length} pendientes)`} className="lg:col-span-4 border-l-4 border-l-error min-w-0">
          <p className="text-[14px] text-on-surface-variant mb-2">Riesgo vital: descompensación grave sin estabilización en un diagnóstico de prioridad alta. Llamar hoy, tengan o no cupo.</p>
          {contactar.length === 0 && <p className="text-on-surface-variant">Sin pacientes en esta condición{esp !== "Todas" && ` en ${esp}`}.</p>}
          <ul className="divide-y divide-outline-variant/60 lg:max-h-[70vh] lg:overflow-y-auto lg:pr-1">
            {contactar.map((p) => {
              const libre = libresPorEsp(p.especialidad);
              return (
                <li key={p.id_paciente} className={`py-2.5 ${p.contactar_hoy ? "" : "opacity-70"}`}>
                  <button onClick={() => onVer(p.id_paciente)} className="w-full text-left">
                    <div className="font-semibold">{p.nombre_fantasia} <span className="font-normal text-on-surface-variant text-[14px]">· N° {p.posicion}</span></div>
                    <div className="text-[14px] text-on-surface-variant">{p.especialidad} · {p.diagnostico_texto}</div>
                  </button>
                  <div className="mt-1.5">
                    {p.cita ? <span className="text-[14px] font-semibold text-primary"><Icono n="event_available" className="text-[16px]" /> Citado en {p.cita.id_box} · {fmt(p.cita.fecha)}</span>
                      : libre ? <button disabled={!!ocupado} onClick={() => asignar(libre.id_box, p.id_paciente)} className="h-10 px-3 bg-primary text-on-primary font-semibold text-[14px] disabled:opacity-50">Asignar cupo en {libre.id_box}</button>
                      : <span className="text-[14px] text-error font-semibold">Sin cupo hoy · evaluar sobrecupo o derivación a urgencia</span>}
                  </div>
                </li>
              );
            })}
          </ul>
        </Caja>

        <div className="lg:col-span-8 flex flex-col gap-4 min-w-0">
          <section aria-label="Mapa de box" className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-5 gap-2">
            {mapa.map((x) => {
              if (!x.especialidad) return (
                <div key={x.id_box} className="border border-dashed border-outline-variant p-2.5 text-on-surface-variant">
                  <div className="font-semibold">{x.id_box.replace("BOX-", "Box ")}</div><div className="text-[13px]">Sin agenda este día</div>
                </div>
              );
              const pAg = (x.usados_agenda / x.capacidad) * 100, pSis = ((x.ocupados - x.usados_agenda) / x.capacidad) * 100;
              return (
                <button key={x.id_box} onClick={() => abrirBox(x.id_box)} aria-pressed={sel === x.id_box}
                  className={`text-left border-2 p-2.5 bg-surface-container-lowest ${sel === x.id_box ? "border-primary" : "border-outline-variant hover:border-outline"}`}>
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-semibold">{x.id_box.replace("BOX-", "Box ")}</span>
                    <span className={`text-[13px] font-bold ${x.libres ? "text-hlf" : "text-on-surface-variant"}`}>{x.libres ? `${x.libres} libre${x.libres > 1 ? "s" : ""}` : "lleno"}</span>
                  </div>
                  <div className="text-[13px] text-on-surface-variant truncate">{x.especialidad}</div>
                  <div className="h-2 bg-hlf/30 mt-1.5 flex" aria-label={`${x.ocupados} de ${x.capacidad} cupos ocupados`}>
                    <div className="h-full bg-outline" style={{ width: `${pAg}%` }} /><div className="h-full bg-primary" style={{ width: `${pSis}%` }} />
                  </div>
                  <div className="text-[12px] text-on-surface-variant mt-1">{x.ocupados}/{x.capacidad} ocupados{x.citas?.length ? ` · ${x.citas.length} desde la lista` : ""}</div>
                </button>
              );
            })}
          </section>
          <p className="text-[13px] text-on-surface-variant -mt-2 flex flex-wrap gap-x-4 gap-y-1">
            <span className="flex items-center gap-1"><span className="w-3 h-2 bg-outline" />Agenda del día</span>
            <span className="flex items-center gap-1"><span className="w-3 h-2 bg-primary" />Citado desde la lista</span>
            <span className="flex items-center gap-1"><span className="w-3 h-2 bg-hlf/30" />Libre</span>
            <span>Toque un box para asignar cupos o registrar el resultado de la cita.</span>
          </p>

          <div ref={panel} className="scroll-mt-4">
            {box ? (
              <Caja titulo={`${box.id_box} · ${box.especialidad} · ${box.bloque || "08:30-13:30"}`} className="border-2 border-primary"
                accion={<button onClick={() => setSel(null)} aria-label="Cerrar box" className="w-10 h-10 flex items-center justify-center"><Icono n="close" /></button>}>
                <div className="grid grid-cols-3 gap-2 text-center mb-4">
                  {[["Agenda", box.usados_agenda], ["Desde la lista", box.ocupados - box.usados_agenda], ["Libres", box.libres]].map(([t, n]) => (
                    <div key={t} className="bg-surface-container-low py-2"><div className="text-[22px] font-bold">{n}</div><div className="text-[13px] text-on-surface-variant">{t}</div></div>
                  ))}
                </div>

                {box.citas.length > 0 && (
                  <div className="mb-4">
                    <h3 className="text-[13px] uppercase tracking-wide text-on-surface-variant font-semibold mb-1">Citas asignadas desde la lista</h3>
                    <ul className="divide-y divide-outline-variant/60">
                      {box.citas.map((c) => {
                        const activa = c.estado === "citado" || c.estado === "confirmado";
                        return (
                          <li key={c.id_cita} className="py-2.5">
                            <div className="flex items-start justify-between gap-2">
                              <button onClick={() => c.posicion && onVer(c.id_paciente)} className="text-left">
                                <div className="font-semibold">{c.nombre_fantasia} <span className="font-normal text-[14px] text-on-surface-variant">· {c.posicion ? `N° ${c.posicion}` : "fuera de la lista"}</span></div>
                                <div className="text-[14px] text-on-surface-variant">{c.diagnostico_texto}</div>
                              </button>
                              <span className={`text-[14px] font-semibold whitespace-nowrap ${TONO[c.estado]}`}>{ESTADO[c.estado]}</span>
                            </div>
                            {activa && (
                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 mt-2 text-[14px]">
                                {c.estado === "citado" && <button disabled={!!ocupado} onClick={() => estado(c, "confirmado")} className="h-10 border-2 border-primary text-primary font-semibold disabled:opacity-50">Confirmó</button>}
                                <button disabled={!!ocupado} onClick={() => estado(c, "asistio")} className="h-10 bg-verde text-background font-semibold disabled:opacity-50">Asistió</button>
                                <button disabled={!!ocupado} onClick={() => estado(c, "no_asistio")} className="h-10 border-2 border-ambar text-ambar font-semibold disabled:opacity-50">No asistió</button>
                                <button disabled={!!ocupado} onClick={() => estado(c, "cancelo")} className="h-10 border-2 border-outline-variant font-semibold disabled:opacity-50">Canceló</button>
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}

                <h3 className="text-[13px] uppercase tracking-wide text-on-surface-variant font-semibold mb-1">Cupos libres · siguientes de la lista</h3>
                {box.libres === 0 && <p className="text-[15px] text-on-surface-variant">Sin cupos libres. Si un paciente cancela o no asiste, el cupo se libera aquí y se sugiere al siguiente.</p>}
                {box.libres > 0 && box.pacientes.length === 0 && <p className="text-[15px] text-on-surface-variant">{box.libres} cupos libres, pero no quedan pacientes de {box.especialidad} sin cita.</p>}
                <ul className="flex flex-col gap-2">
                  {box.pacientes.map((p, i) => (
                    <li key={p.id_paciente} className={`border border-outline-variant p-3 ${p.riesgo_vital ? "border-l-4 border-l-error" : ""}`}>
                      <div className="flex items-start gap-2">
                        <span className="text-[13px] text-on-surface-variant pt-0.5">Cupo {i + 1}</span>
                        <div className="flex-1 min-w-0">
                          <button onClick={() => onVer(p.id_paciente)} className="text-left font-semibold">{p.nombre_fantasia} <span className="font-normal text-[14px] text-on-surface-variant">· N° {p.posicion} · {p.dias_espera} días</span></button>
                          <div className="text-[14px]">{p.motivo}</div>
                          {p.riesgo_inasistencia && <div className="text-[13px] text-ambar font-semibold">2 inasistencias seguidas: confirmar por teléfono (no baja la prioridad)</div>}
                        </div>
                        <Prioridad cat={p.categoria} />
                      </div>
                      <button disabled={!!ocupado} onClick={() => asignar(box.id_box, p.id_paciente)} className="mt-2 w-full sm:w-auto h-11 px-4 bg-primary text-on-primary font-semibold disabled:opacity-50">
                        {ocupado === `a-${box.id_box}-${p.id_paciente}` ? "Asignando…" : "Asignar cupo"}</button>
                    </li>
                  ))}
                </ul>
                {box.esp.alternativa && (
                  <div className="mt-3 border border-dashed border-outline p-2.5 text-[14px]">
                    <div className="text-on-surface-variant">Siguiente en la lista si alguien no confirma:</div>
                    <div className="font-semibold">{box.esp.alternativa.nombre_fantasia} <span className="font-normal text-on-surface-variant">· N° {box.esp.alternativa.posicion}</span></div>
                    {box.esp.alternativa.por_que_despues && <div>Va después porque: {box.esp.alternativa.por_que_despues}</div>}
                  </div>
                )}
              </Caja>
            ) : (
              <Caja><p className="text-on-surface-variant">Seleccione un box del mapa para asignar sus cupos libres a los siguientes de la lista o registrar si el paciente asistió.</p></Caja>
            )}
          </div>

          <Caja titulo="Resumen por especialidad">
            <div className="overflow-x-auto">
              <table className="w-full text-[14px] min-w-[420px]">
                <thead><tr className="text-left text-on-surface-variant text-[13px] border-b border-outline-variant"><th className="py-1.5">Especialidad</th><th>Box</th><th>Libres</th><th>Citas</th><th title="Inasistencia histórica en citaciones.csv">Inasist.</th><th>Riesgo vital sin cupo</th></tr></thead>
                <tbody>
                  {b.especialidades.filter((e) => filtra(e.especialidad)).map((e) => (
                    <tr key={e.especialidad} className="border-b border-outline-variant/50">
                      <td className="py-1.5 font-semibold">{e.especialidad}</td><td>{e.asignaciones.length}</td>
                      <td className={e.cupos_libres_hoy ? "text-hlf font-semibold" : ""}>{e.cupos_libres_hoy}</td><td>{e.citas_hoy}</td>
                      <td>{e.inasistencia_pct ?? "—"}%</td>
                      <td className={e.vitales_sin_cupo.length ? "text-error font-semibold" : ""}>{e.vitales_sin_cupo.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Caja>
        </div>
      </div>
    </div>
  );
}
