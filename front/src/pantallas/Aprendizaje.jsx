// Qué ha aprendido el sistema de los especialistas (GET /aprendizaje): criterios locales (propuestos, vigentes, rechazados,
// retirados), concordancia con su n y reglas objetadas. Lo propuesto no cambia nada hasta que una jefatura lo aprueba.
import { useCallback, useEffect, useState } from "react";
import * as api from "../api";
import { descargarExcel } from "../excel";
import { Caja, Filtro, Icono, Prioridad } from "../componentes/comunes";
import { VEREDICTO_TXT, textoPatron } from "../componentes/Decision";
import { ESPECIALIDADES, FACTOR, plural } from "../constantes";
import { usePuede } from "../permisos";
import { fmt } from "../util";

const MIN = 20;
const ESTADO_CL = { propuesto: ["Propuesto", "text-ambar bg-ambar-container/60"], vigente: ["Vigente", "text-verde bg-verde-container/60"],
  rechazado: ["Rechazado", "text-on-surface-variant bg-surface-container-low"], retirado: ["Retirado", "text-on-surface-variant bg-surface-container-low"] };
const num = (x, d = 2) => (x == null ? "—" : x.toFixed(d).replace(".", ","));

export function Aprendizaje({ data, esp, setEsp, fecha, onVer, onCambio, onAviso }) {
  const [a, setA] = useState(null);
  const [error, setError] = useState(null);
  const [resuelto, setResuelto] = useState(null);  // resultado de la última resolución (el criterio cambia de sección al resolverse)
  const espApi = esp === "Todas" ? null : esp;
  const cargar = useCallback(async () => {
    try { setError(null); setA(await api.getAprendizaje(espApi)); } catch (e) { setError(e.message); }
  }, [espApi]);
  useEffect(() => { cargar(); }, [cargar]);

  if (error) return <Caja><p className="text-error flex items-center gap-2"><Icono n="cloud_off" />No se pudo cargar lo aprendido: {error}.
    <button onClick={cargar} className="font-semibold underline">Reintentar</button></p></Caja>;
  if (!a) return <p className="text-on-surface-variant">Cargando lo aprendido…</p>;

  const cls = a.criterios_locales || [];
  const de = (e) => cls.filter((c) => c.estado === e);
  const g = a.concordancia.global;
  const aplicaA = (c) => (data?.pacientes || []).filter((p) => p.criterios_locales?.some((x) => x.id === c.id)).length;
  const precedentesDe = (c) => (a.precedentes_recientes || []).filter((v) => v.patron === c.patron_texto);

  const exportar = () => descargarExcel(`aprendizaje_HLF${espApi ? `_${espApi}` : ""}.xlsx`, [
    { nombre: "Criterios locales", filas: [["ID", "Versión", "Estado", "Criterio", "Diagnóstico", "Evento", "Gravedad", "Sube a", "Revisiones que lo respaldan",
      "Propuesto por", "Resuelto por", "Vigente desde", "Vigente hasta", "Motivo de la resolución", "Fecha"],
      ...cls.map((c) => [c.id, c.version, ESTADO_CL[c.estado]?.[0] || c.estado, c.texto, c.patron?.diagnostico, c.patron?.tipo_evento, c.patron?.severidad,
        c.efecto?.categoria, c.precedentes, c.propuesto_por || "", c.resuelto_por || "", fmt(c.vigente_desde), fmt(c.vigente_hasta), c.motivo_resolucion || "", fmt(c.fecha)])] },
    { nombre: "Concordancia", filas: [["Alcance", "Revisiones (n)", "Adecuadas", "Incorrectas", "% adecuadas", "Kappa"],
      ["Global", g.n, g.adecuadas, g.incorrectas, g.pct_adecuadas ?? "", g.kappa ?? ""],
      ...a.concordancia.por_diagnostico.map((x) => [`Diagnóstico ${x.diagnostico}`, x.n, x.adecuadas, x.incorrectas, x.pct_adecuadas ?? "", ""]),
      ...a.concordancia.por_patron.map((x) => [`Caso ${textoPatron(x.patron)}`, x.n, x.adecuadas, x.incorrectas, x.pct_adecuadas ?? "", ""])] },
    { nombre: "Reglas objetadas", filas: [["Regla", "Detalle", "Fuente", "Objeciones", "Especialistas", "Pacientes"],
      ...(a.reglas_a_validar || []).map((r) => [FACTOR[r.factor] || r.factor, r.valor || "", r.fuente, r.objeciones, r.especialistas, (r.pacientes || []).join(", ")])] },
    { nombre: "Revisiones recientes", filas: [["Fecha", "Paciente", "Caso", "Veredicto", "Motivo", "Explicación", "Especialista", "Prioridad del sistema", "Prioridad final"],
      ...(a.precedentes_recientes || []).map((v) => [fmt(v.fecha), v.id_paciente, textoPatron(v.patron), VEREDICTO_TXT[v.veredicto] || v.veredicto, v.motivo_codigo || "", v.motivo || "", v.usuario, v.categoria_sistema || "", v.categoria_final || ""])] },
    { nombre: "Información", filas: [["Dato", "Valor"], ["Especialidad", espApi || "Todas"], ["Versión de los criterios locales", a.capa_local?.version ?? 0],
      ["Meta de concordancia", "kappa ≥ 0,70"], ["Generado por", api.getUsuario() || "(sin nombre)"], ["Generado el", new Date().toLocaleString("es-CL")]] }]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-bold">Lo que el sistema aprende de los especialistas</h1>
          <p className="text-[15px] text-on-surface-variant">Cuando un especialista dice que una decisión fue incorrecta porque faltaba un criterio, el sistema propone un
            <b> criterio local</b>. <b>Lo propuesto no cambia nada hasta que una jefatura lo aprueba, y solo puede subir prioridades.</b></p>
        </div>
        <div className="flex flex-wrap items-end gap-2 text-[14px]">
          <Filtro label="Especialidad"><select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-10 px-2 border border-outline-variant rounded bg-surface-container-lowest">
            {ESPECIALIDADES.map((x) => <option key={x}>{x}</option>)}</select></Filtro>
          <button onClick={exportar} className="h-10 px-4 rounded bg-primary text-on-primary font-semibold flex items-center gap-1"><Icono n="download" className="text-[18px]" />Exportar a Excel</button>
        </div>
      </div>

      {resuelto && <ResultadoResolucion r={resuelto} onVer={onVer} onCerrar={() => setResuelto(null)} />}

      <Caja titulo={`Criterios locales propuestos (${de("propuesto").length})`} accion={<span className="text-[12px] text-on-surface-variant">Versión de los criterios locales: {a.capa_local?.version ?? 0}</span>}>
        {de("propuesto").length === 0 ? <p className="text-[14px] text-on-surface-variant">No hay criterios esperando aprobación. Aparecen cuando un especialista marca una decisión como
          incorrecta con el motivo «Falta un criterio».</p>
          : <div className="flex flex-col gap-3">{de("propuesto").map((c) => <Criterio key={c.id} c={c} precedentes={precedentesDe(c)} onVer={onVer} onAviso={onAviso}
            onResuelto={async (r) => { setResuelto(r); await Promise.all([cargar(), onCambio?.()]); }} fecha={fecha} />)}</div>}
      </Caja>

      <Caja titulo={`Criterios locales vigentes (${de("vigente").length})`}>
        {de("vigente").length === 0 ? <p className="text-[14px] text-on-surface-variant">Todavía no hay criterios locales aprobados: la lista usa solo la tabla del HLF y los criterios oficiales.</p>
          : <div className="flex flex-col gap-3">{de("vigente").map((c) => <Criterio key={c.id} c={c} aplica={aplicaA(c)} esp={esp} onVer={onVer} onAviso={onAviso}
            onResuelto={async (r) => { setResuelto(r); await Promise.all([cargar(), onCambio?.()]); }} fecha={fecha} />)}</div>}
      </Caja>

      {(de("rechazado").length > 0 || de("retirado").length > 0) && <details className="bg-surface-container-lowest border border-outline-variant rounded">
        <summary className="px-4 py-2.5 cursor-pointer font-semibold text-[15px]">Rechazados ({de("rechazado").length}) y retirados ({de("retirado").length})</summary>
        <div className="px-4 pb-3 flex flex-col gap-3">{[...de("rechazado"), ...de("retirado")].map((c) => <Criterio key={c.id} c={c} onVer={onVer} />)}</div>
      </details>}

      <Caja titulo="Concordancia con los especialistas">
        <div className="grid gap-3 sm:grid-cols-3 text-[14px]">
          <div className={`rounded border border-outline-variant border-l-4 p-3 ${!g.suficiente ? "border-l-outline" : g.kappa >= g.meta_kappa ? "border-l-hlf" : "border-l-ambar"}`}>
            <div className="text-[13px] text-on-surface-variant">Kappa (meta del hospital ≥ {num(g.meta_kappa)})</div>
            <div className="text-[28px] font-bold leading-tight">{g.kappa == null ? "—" : `κ ${num(g.kappa)}`}</div>
            <div className="text-[12px] text-on-surface-variant">n = {g.n_kappa ?? g.n}{!g.suficiente && ` · con menos de ${g.n_recomendado} revisiones es solo orientativo`}</div>
          </div>
          <div className="rounded border border-outline-variant border-l-4 border-l-primary p-3">
            <div className="text-[13px] text-on-surface-variant">Decisiones adecuadas</div>
            <div className="text-[28px] font-bold leading-tight">{g.pct_adecuadas == null ? "—" : `${g.pct_adecuadas}%`}</div>
            <div className="text-[12px] text-on-surface-variant">{g.adecuadas} adecuadas · {g.incorrectas} incorrectas · n = {g.n}</div>
          </div>
          <p className="text-[13px] text-on-surface-variant self-center">El kappa compara la prioridad que dejó el sistema con la que indicó el especialista, descontando
            el acuerdo que se daría por azar. 1 = acuerdo perfecto; 0 = como el azar.</p>
        </div>
        {g.n === 0 ? <p className="text-[14px] text-on-surface-variant mt-3">Todavía no hay revisiones. Se calcula cuando los especialistas responden en «Decisiones».</p>
          : <div className="grid gap-4 lg:grid-cols-2 mt-4">
            <TablaConcordancia titulo="Por diagnóstico" filas={a.concordancia.por_diagnostico.map((x) => [x.diagnostico, x])} />
            <TablaConcordancia titulo="Por tipo de caso" filas={a.concordancia.por_patron.map((x) => [textoPatron(x.patron), x])} />
          </div>}
      </Caja>

      <Caja titulo="Reglas que los especialistas han objetado (a validar con el equipo médico)">
        {(a.reglas_a_validar || []).length === 0 ? <p className="text-[14px] text-on-surface-variant">Ningún especialista ha objetado una regla. Una regla entra aquí cuando alguien marca
          una decisión como incorrecta con el motivo «La regla usada no corresponde a este caso». Nunca baja a nadie sola: queda para revisar con el equipo médico.</p>
          : <ul className="divide-y divide-outline-variant/60 text-[14px]">{a.reglas_a_validar.map((r, i) => (
            <li key={i} className="py-2">
              <div><b>{FACTOR[r.factor] || r.factor}</b>{r.valor ? `: ${r.valor}` : ""}</div>
              <div className="text-[12px] text-on-surface-variant italic">Fuente: {r.fuente}</div>
              <div className="text-[13px]">{plural(r.objeciones, "objeción", "objeciones")} de {plural(r.especialistas, "especialista", "especialistas")} · pacientes:{" "}
                {(r.pacientes || []).map((pid, k) => <button key={pid} onClick={() => onVer(pid)} className="text-primary hover:underline">{k ? ", " : ""}{pid}</button>)}</div>
            </li>))}</ul>}
      </Caja>
    </div>
  );
}

function TablaConcordancia({ titulo, filas }) {
  return (
    <div>
      <h3 className="text-[14px] font-semibold mb-1">{titulo}</h3>
      <table className="w-full text-[13px]">
        <thead><tr className="text-left text-on-surface-variant border-b border-outline-variant"><th className="py-1"> </th><th className="text-right">n</th><th className="text-right">Adecuadas</th><th className="text-right">Incorrectas</th><th className="text-right">% adecuadas</th></tr></thead>
        <tbody>{filas.map(([t, x]) => <tr key={t} className="border-b border-outline-variant/50"><td className="py-1">{t}</td><td className="text-right">{x.n}</td>
          <td className="text-right">{x.adecuadas}</td><td className="text-right">{x.incorrectas}</td><td className="text-right font-semibold">{x.pct_adecuadas ?? "—"}%</td></tr>)}</tbody>
      </table>
    </div>
  );
}

// Un criterio local con su historia y, para la jefatura, aprobar / rechazar (propuesto) o retirar (vigente) con motivo.
function Criterio({ c, precedentes, aplica, esp, onVer, onAviso, onResuelto, fecha }) {
  const puede = usePuede();
  const [accion, setAccion] = useState(null);
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [est, colorEst] = ESTADO_CL[c.estado] || [c.estado, ""];
  const ACC = { aprobar: "Aprobar", rechazar: "Rechazar", retirar: "Retirar" };
  const resolver = async () => {
    if (!api.getUsuario()) { onAviso?.({ titulo: "Escriba su nombre y cargo arriba a la derecha: la resolución queda a su nombre" }); return; }
    setEnviando(true);
    try {
      const r = await api.postResolverCriterio(c.id, { accion, motivo: motivo.trim(), fecha_corte: fecha });
      setAccion(null); setMotivo("");
      onAviso?.({ titulo: `Criterio ${c.id}: ${r.criterio?.estado || accion}${r.pacientes_con_cambio ? ` · ${plural(r.pacientes_con_cambio, "paciente cambia", "pacientes cambian")} de prioridad` : ""}` });
      await onResuelto?.({ accion, ...r });
    } catch (e) { onAviso?.({ titulo: "No se pudo resolver el criterio: " + e.message }); } finally { setEnviando(false); }
  };
  return (
    <article className="rounded border border-outline-variant p-3 text-[14px] flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded px-2 py-0.5 text-[12px] font-semibold ${colorEst}`}>{est}</span>
        <b>{c.id} v{c.version}</b><span className="text-[13px] text-on-surface-variant">· caso {textoPatron(c.patron_texto)}</span>
        <span className="ml-auto flex items-center gap-1 text-[13px]">sube a <Prioridad cat={c.efecto?.categoria} /></span>
      </div>
      <p className="text-[15px]">«{c.texto}»</p>
      <p className="text-[13px] text-on-surface-variant">Propuesto por {c.propuesto_por || "—"} · basado en {plural(c.precedentes || 0, "revisión", "revisiones")} de especialista
        {c.resuelto_por && <> · {c.estado === "vigente" ? "aprobado" : c.estado} por <b>{c.resuelto_por}</b>{c.motivo_resolucion ? `: «${c.motivo_resolucion}»` : ""}</>}
        {c.vigente_desde && <> · rige desde el {fmt(c.vigente_desde)}</>}{c.vigente_hasta && <> hasta el {fmt(c.vigente_hasta)}</>}</p>
      {c.estado === "vigente" && aplica != null && <p className="text-[13px]">Hoy aplica a <b>{plural(aplica, "paciente", "pacientes")}</b> de {esp === "Todas" ? "la lista" : esp}.</p>}
      {precedentes?.length > 0 && <div className="text-[13px]">
        <div className="text-on-surface-variant">Revisiones que lo originaron (las más recientes):</div>
        <ul className="list-disc pl-5">{precedentes.map((v, i) => <li key={i}>{fmt(v.fecha)} · <b>{v.usuario}</b> · {VEREDICTO_TXT[v.veredicto] || v.veredicto}
          {v.categoria_sistema && v.categoria_final && ` (sistema: ${v.categoria_sistema} → especialista: ${v.categoria_final})`}{v.motivo ? `: «${v.motivo}»` : ""} ·{" "}
          <button onClick={() => onVer(v.id_paciente)} className="text-primary hover:underline">{v.id_paciente}</button></li>)}</ul>
      </div>}
      {onResuelto && (c.estado === "propuesto" || c.estado === "vigente") && (puede("jefatura")
        ? <div className="flex flex-col gap-2 mt-1">
          <div className="flex flex-wrap gap-2">
            {(c.estado === "propuesto" ? ["aprobar", "rechazar"] : ["retirar"]).map((k) => <button key={k} onClick={() => setAccion(accion === k ? null : k)} aria-pressed={accion === k}
              className={`px-3 py-1.5 rounded font-semibold ${k === "aprobar" ? "bg-primary text-on-primary" : "border border-primary text-primary"} ${accion === k ? "ring-2 ring-primary/40" : ""}`}>{ACC[k]}</button>)}
          </div>
          {accion && <>
            <textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder={`Motivo para ${ACC[accion].toLowerCase()} (obligatorio, mínimo ${MIN} caracteres)`}
              className="px-2 py-1.5 border border-outline-variant rounded bg-surface-container-lowest" />
            <p className="text-[12px] text-on-surface-variant">{accion === "aprobar" ? "Al aprobarlo, el sistema lo aplica desde hoy a los pacientes que calzan (solo sube) y lo cita como fuente en cada decisión."
              : accion === "retirar" ? "Al retirarlo deja de aplicarse; los pacientes que subió conservan su prioridad hasta que un especialista los revise." : "Rechazado, no cambia nada y queda en el historial."}</p>
            <button onClick={resolver} disabled={motivo.trim().length < MIN || enviando} className="self-start px-4 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">
              {enviando ? "Guardando…" : `Confirmar: ${ACC[accion].toLowerCase()}`}</button>
          </>}
        </div>
        : <p className="text-[12px] text-on-surface-variant">Aprobar, rechazar o retirar un criterio lo hace la jefatura (elija el rol arriba).</p>)}
    </article>
  );
}

// Qué pasó al resolver un criterio: a cuántos pacientes les cambió la prioridad y las decisiones que quedaron para revisión.
function ResultadoResolucion({ r, onVer, onCerrar }) {
  return (
    <div className="rounded border border-hlf/40 bg-hlf-claro text-hlf p-3 text-[14px]">
      <div className="flex justify-between gap-2"><b>Criterio {r.criterio?.id}: {r.criterio?.estado || r.accion}</b><button onClick={onCerrar} className="text-[13px] underline">Cerrar</button></div>

        {r.accion === "aprobar" ? <>Aprobado. {r.pacientes_con_cambio ? `Cambió la prioridad de ${plural(r.pacientes_con_cambio, "paciente", "pacientes")}` : "No cambió la prioridad de nadie"}
          {r.dictamenes?.length ? `; quedaron ${plural(r.dictamenes.length, "decisión", "decisiones")} para revisión en «Decisiones»` : ""}.
          {r.dictamenes?.length > 0 && <ul className="list-disc pl-5 mt-1">{r.dictamenes.map((d) => <li key={d.id_dictamen}>
            <button onClick={() => onVer(d.id_paciente)} className="underline">{d.id_paciente}</button>: {d.categoria_antes} → {d.categoria}</li>)}</ul>}</>
          : `Criterio ${r.criterio?.estado || r.accion}.`}
        {r.conservan_prioridad?.length > 0 && <p className="mt-1">Conservan su prioridad mientras un especialista los revisa: {r.conservan_prioridad.map((x) => x.id_paciente || x).join(", ")}.</p>}
      </div>
  );
}
