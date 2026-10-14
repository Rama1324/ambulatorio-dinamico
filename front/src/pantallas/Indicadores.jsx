import { useEffect, useState } from "react";
import * as api from "../api";
import { fmt } from "../lib/constantes";
import { Caja } from "../components/ui";

// KPIs fijados por el hospital: reevaluación < 72 h tras un evento · concordancia con experto kappa ≥ 0,70 · cobertura 100%.
export function Indicadores({ fecha, esApi, data }) {
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
        <span className={`text-[13px] font-semibold rounded px-2 py-0.5 ${ok === null ? "bg-surface-container text-on-surface-variant" : ok ? "bg-hlf-claro text-hlf" : "bg-ambar-container text-ambar"}`}>
          {ok === null ? "Sin datos suficientes" : ok ? "Cumple" : "Bajo la meta"}</span>
      </div>
      <div className="text-[32px] font-bold text-primary-container mt-1">{valor}</div>
      <div className="text-[14px] text-on-surface-variant">Meta del hospital: {meta}</div>
      {pct != null && <div className="h-2 rounded bg-surface-container-high overflow-hidden mt-2"><div className="h-full bg-hlf" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} /></div>}
      <p className="text-[14px] mt-2">{detalle}</p>
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
            <p className="text-[13px] text-on-surface-variant">Descompensaciones, exámenes alterados o aumentos de dosis posteriores a la interconsulta o a la última revisión.</p>
          </div>
        </Caja>
        <Caja titulo="Egresos de la lista">
          <div className="text-[14px] space-y-1">
            <div className="flex justify-between"><span>Por fallecimiento (causal 9)</span><b>{k.egresos.fallecidos}</b></div>
            <div className="flex justify-between"><span>Atendidos en consulta nueva</span><b>{k.egresos.atendidos}</b></div>
          </div>
        </Caja>
      </div>
      <p className="text-[13px] text-on-surface-variant">Kappa de Cohen entre la prioridad que propone el sistema y la decisión del especialista al revisar (Alta / Media / Baja). Indicadores al {fmt(k.fecha_corte)}.</p>
    </div>
  );
}
