import { useState } from "react";
import { Caja, Icono, Prioridad } from "../componentes/comunes";
import { ESPECIALIDADES, plural } from "../constantes";
import { fmt } from "../util";

// Carril GES: los pacientes con garantía de oportunidad para la atención por especialista (Ley 19.966) se ordenan por la
// fecha límite de su garantía, no por gravedad. La lista principal (No GES, tabla del HLF y Ord. 536) no cambia: si un
// paciente GES empeora, igual sube allí. Plazos y citas: lambda/conocimiento/ges_especialista.json (auge.minsal.cl).
const ESTADO = {
  vencida: ["Vencida", "bg-error text-on-error"],
  por_vencer: ["Por vencer", "bg-ambar-container text-ambar"],
  en_plazo: ["En plazo", "bg-hlf-claro text-hlf"],
};

export function CarrilGES({ data, esp, setEsp, onVer }) {
  const [abierto, setAbierto] = useState(null);
  const ges = (data?.pacientes || []).filter((p) => p.ges).sort((a, b) => a.ges.dias_restantes - b.ges.dias_restantes);
  const n = (e) => ges.filter((p) => p.ges.estado === e).length;
  const problemas = [...new Map(ges.map((p) => [p.ges.problema, p.ges])).values()].sort((a, b) => a.problema - b.problema);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-bold">Garantías GES</h1>
          <p className="text-[14px] text-on-surface-variant max-w-3xl">Pacientes con garantía legal de atención por especialista (Ley 19.966). Se ordenan por la <b>fecha límite</b> de
            su garantía, no por gravedad. La lista principal no cambia: si un paciente GES empeora, sube igual allí.</p>
        </div>
        <label className="text-[14px] flex flex-col gap-1">Especialidad
          <select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">
            {ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select></label>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {[["vencida", "superaron el plazo legal"], ["por_vencer", "quedan 14 días o menos"], ["en_plazo", "dentro del plazo"]].map(([e, t]) => (
          <div key={e} className={`rounded border border-outline-variant bg-surface-container-lowest p-3 border-l-4 ${e === "vencida" ? "border-l-error" : e === "por_vencer" ? "border-l-ambar" : "border-l-hlf"}`}>
            <div className="text-[13px] text-on-surface-variant">{ESTADO[e][0]}</div>
            <div className="text-[28px] font-bold leading-tight">{n(e)}</div>
            <div className="text-[12px] text-on-surface-variant">{t}</div>
          </div>
        ))}
      </div>

      <Caja titulo={`${plural(ges.length, "paciente con garantía GES", "pacientes con garantía GES")}${esp !== "Todas" ? ` en ${esp}` : ""}`}>
        {ges.length === 0 ? <p className="text-[14px] text-on-surface-variant">No hay pacientes con garantía GES de especialista en esta vista.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-[14px]">
              <thead><tr className="text-left text-[13px] text-on-surface-variant border-b border-outline-variant">
                <th className="py-2 pr-3 font-semibold">Garantía</th><th className="py-2 pr-3 font-semibold">Paciente</th>
                <th className="py-2 pr-3 font-semibold">Problema GES</th><th className="py-2 pr-3 font-semibold">Fecha límite</th>
                <th className="py-2 pr-3 font-semibold">Prioridad clínica</th><th className="py-2 font-semibold">N° en la lista</th></tr></thead>
              <tbody>
                {ges.map((p) => {
                  const g = p.ges;
                  return (
                    <tr key={p.id_paciente} onClick={() => onVer(p.id_paciente)} className="border-b border-outline-variant/60 cursor-pointer hover:bg-primary/5">
                      <td className="py-2 pr-3 align-top whitespace-nowrap">
                        <span className={`text-[12px] font-semibold rounded px-2 py-0.5 ${ESTADO[g.estado][1]}`}>{ESTADO[g.estado][0]}</span>
                        <div className="text-[12px] text-on-surface-variant mt-0.5">{g.dias_restantes < 0 ? `hace ${-g.dias_restantes} días` : `quedan ${g.dias_restantes} días`}</div>
                      </td>
                      <td className="py-2 pr-3 align-top"><b>{p.nombre_fantasia}</b><div className="text-[12px] text-on-surface-variant">{p.edad} años · {p.diagnostico_texto}</div></td>
                      <td className="py-2 pr-3 align-top">N°{g.problema} · {g.plazo_dias} días<div className="text-[12px] text-on-surface-variant">{g.nombre}</div></td>
                      <td className="py-2 pr-3 align-top whitespace-nowrap">{fmt(g.fecha_limite)}<div className="text-[12px] text-on-surface-variant">ingreso {fmt(p.fecha_ingreso_lista)}</div></td>
                      <td className="py-2 pr-3 align-top"><Prioridad cat={p.categoria} />{(p.riesgo_vital || p.estado_clinico === "descompensado") &&
                        <div className="text-[12px] text-error font-semibold mt-0.5">empeoró: sube también en la lista</div>}</td>
                      <td className="py-2 align-top">{p.posicion}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Caja>

      <Caja titulo="Plazos usados (fuente oficial)">
        <ul className="text-[13px] space-y-1.5">
          {problemas.map((g) => (
            <li key={g.problema}>
              <button onClick={() => setAbierto(abierto === g.problema ? null : g.problema)} className="text-left hover:underline">
                <b>N°{g.problema} {g.nombre}</b>: {g.plazo_dias} días · {g.condicion}</button>
              {abierto === g.problema && <div className="mt-1 pl-3 border-l-4 border-outline-variant text-on-surface-variant">«{g.cita}» ·{" "}
                <a href={g.url} target="_blank" rel="noreferrer" className="text-primary underline">auge.minsal.cl</a></div>}
            </li>
          ))}
        </ul>
        <p className="text-[12px] text-on-surface-variant mt-3 flex gap-1.5"><Icono n="info" className="text-[16px]" />
          <span>El plazo corre desde la derivación. Aquí se usa la fecha de ingreso de la interconsulta a la lista; en producción se toma la fecha del hito desde SIGGES.
            Solo se incluyen garantías de consulta con especialista (no de cirugía, tratamiento ni control después del alta). Datos sintéticos de demostración.</span></p>
      </Caja>
    </div>
  );
}
