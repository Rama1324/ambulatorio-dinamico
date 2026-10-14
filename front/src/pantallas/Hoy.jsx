import { useEffect, useState } from "react";
import * as api from "../api";
import { ESPECIALIDADES, fmt } from "../lib/constantes";
import { Caja, Icono, Prioridad } from "../components/ui";

export function Hoy({ vitales, fecha, esp, setEsp, onVer, esApi }) {
  const [b, setB] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    if (!esApi) return setErr("La agenda de box requiere conexión al servidor.");
    setB(null);
    api.getBoxes(fecha, esp === "Todas" ? null : esp).then(setB).catch((e) => setErr(e.message));
  }, [fecha, esp, esApi]);

  const todos = vitales.filter((p) => esp === "Todas" || p.especialidad === esp);
  const lista = [...todos.filter((p) => p.contactar_hoy), ...todos.filter((p) => !p.contactar_hoy)];
  const pendientes = todos.filter((p) => p.contactar_hoy).length;
  const cupo = b?.cupo_por_paciente || {};
  const conCupo = lista.filter((p) => cupo[p.id_paciente]).length;
  return (
    <div className="flex flex-col gap-5">
    {b?.mapa && <MapaBox mapa={b.mapa} dia={b.dia_agenda} esp={esp} setEsp={setEsp} />}
    <div className="grid gap-5 lg:grid-cols-12 items-start">
      <Caja titulo={`Contactar hoy (${pendientes} pendiente${pendientes !== 1 ? "s" : ""} de ${todos.length})`} className="lg:col-span-4 border-l-4 border-l-error">
        <p className="text-[14px] text-on-surface-variant mb-2">Descompensación grave después de la interconsulta, sin estabilización posterior, en un diagnóstico de prioridad alta según la tabla del HLF. Llamar hoy a todos, tengan o no cupo de box; abra el paciente para registrar el contacto.</p>
        {b && lista.length > 0 && (
          <div className="flex gap-2 mb-3 text-[14px]">
            <span className="flex-1 rounded bg-hlf-claro text-hlf px-2 py-1"><b>{conCupo}</b> con cupo de box hoy</span>
            <span className={`flex-1 rounded px-2 py-1 ${lista.length - conCupo ? "bg-error-container text-on-error-container" : "bg-surface-container-low"}`}><b>{lista.length - conCupo}</b> sin cupo hoy</span>
          </div>
        )}
        {lista.length === 0 && <p className="text-on-surface-variant">Sin pacientes en esta condición{esp !== "Todas" && ` en ${esp}`}.</p>}
        <ul className="divide-y divide-outline-variant/60">
          {lista.map((p) => (
            <li key={p.id_paciente} className={p.contactar_hoy ? "" : "opacity-70"}>
              <button onClick={() => onVer(p.id_paciente)} className="w-full text-left py-2 hover:bg-surface-container-low">
                <div className="flex items-start justify-between gap-2">
                  <div className="font-semibold">{p.nombre_fantasia} <span className="font-normal text-on-surface-variant text-[14px]">· {p.edad} años · N° {p.posicion}</span></div>
                  {b && (cupo[p.id_paciente]
                    ? <span className="shrink-0 text-[13px] rounded bg-hlf-claro text-hlf px-1.5 py-px font-semibold">Cupo hoy: {cupo[p.id_paciente]}</span>
                    : <span className="shrink-0 text-[13px] rounded bg-error-container text-on-error-container px-1.5 py-px font-semibold">Sin cupo hoy</span>)}
                </div>
                <div className="text-[14px] text-on-surface-variant">{p.especialidad} · {p.diagnostico_texto}</div>
                {p.contactar_hoy
                  ? (b && !cupo[p.id_paciente] && <div className="text-[13px] text-error">Pendiente de contacto · evaluar sobrecupo o derivación a urgencia</div>)
                  : <div className="text-[13px] text-hlf font-semibold flex items-center gap-1"><Icono n="task_alt" className="text-[14px]" />{p.contacto?.texto}</div>}
              </button>
            </li>
          ))}
        </ul>
      </Caja>

      <div className="lg:col-span-8 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-[17px] font-semibold">Agenda de box{b?.dia_agenda && ` · ${fmt(b.dia_agenda)}`}</h2>
          <select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-11 px-2 border border-outline-variant rounded bg-surface-container-lowest text-[14px]">{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select>
        </div>
        {err && <Caja><p className="text-on-surface-variant">{err}</p></Caja>}
        {!err && !b && <p className="text-on-surface-variant">Cargando agenda…</p>}
        {b?.especialidades.map((e) => (
          <Caja key={e.especialidad} titulo={e.especialidad} accion={<span className="text-[14px] text-on-surface-variant">Inasistencia histórica {e.inasistencia_pct ?? "—"}%</span>}>
            <div className="flex flex-wrap gap-2 mb-3 text-[14px]">
              <span className="rounded bg-surface-container-low px-2 py-1"><b>{e.cupos_libres_hoy}</b> cupo{e.cupos_libres_hoy !== 1 ? "s" : ""} libre{e.cupos_libres_hoy !== 1 ? "s" : ""} hoy</span>
              {e.vitales_sin_cupo.length > 0 && <span className="rounded bg-error-container text-on-error-container px-2 py-1"><b>{e.vitales_sin_cupo.length}</b> con riesgo vital sin cupo</span>}
            </div>
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
                          <div className="font-semibold">{p.nombre_fantasia} <span className="font-normal text-[14px] text-on-surface-variant">· {p.diagnostico_texto} · {p.dias_espera} días</span></div>
                          <div className="text-[14px]">{p.motivo}</div>
                          <div className={`text-[14px] font-semibold ${p.riesgo_vital ? "text-error" : p.riesgo_inasistencia ? "text-ambar" : "text-primary"}`}>Acción: {p.accion}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
            {e.vitales_sin_cupo.length > 0 && (
              <div className="mb-3 rounded border border-error/40 bg-error-container/40 p-2 text-[14px]">
                <div className="font-semibold text-on-error-container">No alcanzan cupo hoy, pero tienen riesgo vital: contactar y evaluar sobrecupo o derivación a urgencia</div>
                <ul className="mt-1">
                  {e.vitales_sin_cupo.map((p) => (
                    <li key={p.id_paciente} onClick={() => onVer(p.id_paciente)} className="cursor-pointer hover:underline">
                      N° {p.posicion} · {p.nombre_fantasia} · {p.diagnostico_texto}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {e.alternativa && (
              <div onClick={() => onVer(e.alternativa.id_paciente)} className="cursor-pointer border border-dashed border-outline rounded p-2 text-[14px] hover:bg-surface-container-low">
                <div className="text-[14px] text-on-surface-variant">Siguiente en la lista, si un paciente no confirma:</div>
                <div className="font-semibold">{e.alternativa.nombre_fantasia} <span className="font-normal text-[14px] text-on-surface-variant">· prioridad {e.alternativa.categoria} · N° {e.alternativa.posicion}</span></div>
                <div className="text-[14px]">Va después porque: {e.alternativa.por_que_despues}</div>
              </div>
            )}
          </Caja>
        ))}
      </div>
    </div>
    </div>
  );
}

// Mapa de todos los box del día: especialidad, cupos usados/libres y sobretiempo (agenda_box del registro).
export function MapaBox({ mapa, dia, esp, setEsp }) {
  const activos = mapa.filter((x) => x.especialidad);
  const libres = activos.reduce((s, x) => s + x.libres, 0);
  const capacidad = activos.reduce((s, x) => s + x.capacidad, 0);
  return (
    <Caja titulo={`Box del día · ${fmt(dia)}`} accion={
      <span className="text-[14px] text-on-surface-variant">{activos.length} de {mapa.length} box con agenda · <b className="text-hlf">{libres}</b> cupos libres de {capacidad}</span>}>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-10 gap-2">
        {mapa.map((x) => {
          if (!x.especialidad) return (
            <div key={x.id_box} className="rounded border border-dashed border-outline-variant p-2 text-on-surface-variant">
              <div className="font-semibold text-[14px]">{x.id_box.replace("BOX-", "Box ")}</div>
              <div className="text-[13px]">Sin agenda hoy</div>
            </div>
          );
          const pct = Math.round((x.usados / x.capacidad) * 100);
          const sel = esp === x.especialidad;
          return (
            <button key={x.id_box} onClick={() => setEsp(sel ? "Todas" : x.especialidad)} title={`${x.especialidad} · ${x.bloque} · ${x.usados}/${x.capacidad} cupos usados · sobretiempo ${x.sobretiempo_min} min`}
              className={`text-left rounded border p-2 transition ${sel ? "border-primary ring-2 ring-primary/30 bg-primary/5" : "border-outline-variant hover:bg-surface-container-low"}`}>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-[14px]">{x.id_box.replace("BOX-", "Box ")}</span>
                <span className={`text-[13px] font-bold ${x.libres ? "text-hlf" : "text-on-surface-variant"}`}>{x.libres ? `${x.libres} libres` : "lleno"}</span>
              </div>
              <div className="text-[13px] text-on-surface-variant truncate">{x.especialidad}</div>
              <div className="h-1.5 rounded bg-hlf-claro overflow-hidden mt-1.5" aria-label={`${pct}% ocupado`}>
                <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
              </div>
              <div className="flex justify-between text-[12px] text-on-surface-variant mt-1">
                <span>{x.usados}/{x.capacidad} usados</span>
                {x.sobretiempo_min > 0 && <span title="Sobretiempo del bloque">+{x.sobretiempo_min} min</span>}
              </div>
            </button>
          );
        })}
      </div>
      <p className="text-[13px] text-on-surface-variant mt-2">Barra azul: cupos ya usados · verde: cupos libres que se asignan abajo según la lista. Haga clic en un box para ver su especialidad.</p>
    </Caja>
  );
}
