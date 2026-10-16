import { useEffect, useState } from "react";
import * as api from "../api";
import { Icono } from "../componentes/comunes";
import { COLOR_HEX, ETIQUETA, TIPO_EVENTO } from "../constantes";
import { fmt, fmtHace } from "../util";

// Carga la historia de un paciente (posición/categoría en el tiempo), dibuja el gráfico
// y explica en detalle qué eventos hicieron subir su prioridad / posición en la lista.
export function EvolucionPaciente({ p, fecha, esp }) {
  const [h, setH] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let vivo = true;
    setH(null); setErr(null);
    api.getHistoria(p.id_paciente, fecha, esp).then((r) => { if (vivo) setH(r); }).catch((e) => { if (vivo) setErr(e.message); });
    return () => { vivo = false; };
  }, [p.id_paciente, fecha, esp]);

  // Razones indexadas por factor: traen el texto y la fuente oficial que ya calculó el motor de reglas.
  const rz = Object.fromEntries((p.razones || []).map((r) => [r.factor, r]));
  const subioTabla = rz.tabla_oficial && rz.tabla_oficial.valor.startsWith('"') && !rz.tabla_oficial.valor.includes("no supera");
  // Eventos graves del timeline (los que empujan la prioridad), más recientes primero.
  const eventosGraves = (h?.eventos || [])
    .filter((e) => e.severidad === "grave" || (e.subtipo || "").toLowerCase().includes("descompensaci"))
    .sort((a, b) => b.fecha_evento.localeCompare(a.fecha_evento));
  const delta = p.posicion_anterior ? p.posicion_anterior - p.posicion : 0;

  // Pasos de la explicación: de la prioridad inicial al lugar actual, señalando la causa de cada subida.
  const pasos = [];
  pasos.push({ icon: "flag", t: "Prioridad inicial", v: `${ETIQUETA[p.prioridad_inicial] || p.prioridad_inicial}`, d: "Asignada por el especialista al priorizar la interconsulta (SIC)." });
  for (const e of eventosGraves) {
    pasos.push({ icon: "emergency", rojo: true, t: `${TIPO_EVENTO[e.tipo_evento] || e.tipo_evento || "Evento clínico"}${e.fecha_evento ? ` · ${fmtHace(e.fecha_evento, fecha)}` : ""}`,
      v: e.subtipo || "Descompensación", d: "Evento clínico registrado después de la interconsulta: es lo que gatilló la reevaluación." });
  }
  if (eventosGraves.length === 0 && rz.evento) {
    pasos.push({ icon: "emergency", rojo: true, t: "Evento posterior a la interconsulta", v: rz.evento.valor.replaceAll("_", " ").replace(/^evento grave: /, ""), d: `Fuente: ${rz.evento.fuente}` });
  }
  if (subioTabla) {
    pasos.push({ icon: "arrow_upward", rojo: true, t: "Subió de prioridad por la tabla oficial",
      v: rz.tabla_oficial.valor.split("→").slice(-1)[0].split(" · ")[0].trim(),
      d: `${rz.tabla_oficial.valor.split("→")[0].replaceAll('"', "").trim()} · Fuente: ${rz.tabla_oficial.fuente}` });
  }
  if (rz.riesgo_vital) {
    pasos.push({ icon: "priority_high", rojo: true, t: "Descompensación grave", v: "Prioridad actualizada: contactar al paciente", d: rz.riesgo_vital.fuente });
  }
  if (p.categoria_sistema && p.categoria !== p.categoria_sistema) pasos.push({ icon: "how_to_reg", t: "Decisión del equipo clínico",
    v: `Prioridad ${ETIQUETA[p.categoria].toLowerCase()} (el sistema proponía ${ETIQUETA[p.categoria_sistema].toLowerCase()})`, d: `${p.revision?.motivo || ""}${p.revision?.usuario ? ` · ${p.revision.usuario}` : ""}` });
  if (p.grupo_proteccion) pasos.push({ icon: "shield_person", t: "Grupo de especial protección", v: p.grupo_proteccion, d: "MINSAL Ord. 536/2025, criterio 2: ordena antes dentro de la misma prioridad." });
  if (rz.ges) pasos.push({ icon: "verified", t: "Garantía GES", v: rz.ges.valor, d: `Fuente: ${rz.ges.fuente}` });
  if (rz.medicion) pasos.push({ icon: "monitor_heart", t: "Medición sostenida fuera de rango", v: rz.medicion.valor, d: `Fuente: ${rz.medicion.fuente}` });
  if (rz.dias_espera) pasos.push({ icon: "schedule", t: "Tiempo de espera", v: rz.dias_espera.valor, d: `Fuente: ${rz.dias_espera.fuente}` });
  if (p.ajuste_manual) pasos.push({ icon: "swap_vert", t: "Ajuste manual de la posición",
    v: `N° ${p.ajuste_manual.posicion} en ${p.ajuste_manual.especialidad} (el sistema lo ponía en el N° ${p.ajuste_manual.posicion_anterior})`,
    d: `${p.ajuste_manual.motivo_texto}: «${p.ajuste_manual.explicacion}» · ${p.ajuste_manual.usuario}` });
  if (p.ajuste_manual_vencido) pasos.push({ icon: "warning", t: "Ajuste manual sin efecto", v: "Volvió al orden del sistema", d: `Llegó un evento nuevo: ${p.ajuste_manual_vencido.vencido_por}` });
  pasos.push({ icon: "format_list_numbered", final: true, t: "Lugar actual en la lista",
    v: `N° ${p.posicion}${p.posicion_anterior ? ` (antes N° ${p.posicion_anterior})` : ""}`,
    d: delta > 0 ? `Subió ${delta} puesto${delta !== 1 ? "s" : ""} respecto al corte anterior.` : delta < 0 ? `Bajó ${-delta} puesto${-delta !== 1 ? "s" : ""} respecto al corte anterior.` : "Sin cambio de posición respecto al corte anterior." });

  if (!h && !err) return (
    <div className="flex flex-col gap-3 animate-pulse" aria-busy="true" aria-label="Cargando la evolución del paciente">
      <div className="max-w-[640px] h-[236px] rounded bg-surface-container-high/70" />
      <div className="h-4 w-48 rounded bg-surface-container-high/70" />
      <div className="h-4 w-full rounded bg-surface-container-high/50" />
      {pasos.map((_, i) => <div key={i} className="ml-6 h-9 rounded bg-surface-container-high/40" />)}
    </div>
  );
  return (
    <div className="flex flex-col gap-3">
      {err ? <p className="text-[13px] text-error">No se pudo cargar la evolución: {err}</p>
        : <div className="max-w-[640px]"><GraficoPosicion h={h} /></div>}

      <div>
        <h4 className="text-[13px] font-semibold mb-2 flex items-center gap-1"><Icono n="trending_up" className="text-[18px]" />Por qué cambió su lugar en la lista</h4>
        {delta > 0
          ? <p className="text-[13px] mb-2">Subió <b className="text-error">{delta} puesto{delta !== 1 ? "s" : ""}</b> (de N° {p.posicion_anterior} a N° {p.posicion}){eventosGraves[0] ? <> por {TIPO_EVENTO[eventosGraves[0].tipo_evento]?.toLowerCase() || "un evento clínico"} del {fmtHace(eventosGraves[0].fecha_evento, fecha)}.</> : "."}</p>
          : p.estado_clinico === "descompensado"
            ? <p className="text-[13px] mb-2">Está en <b className="text-error">prioridad {ETIQUETA[p.categoria].toLowerCase()}</b> por una descompensación registrada después de la interconsulta.</p>
            : <p className="text-[13px] mb-2 text-on-surface-variant">Mantiene su prioridad {ETIQUETA[p.categoria].toLowerCase()}; su lugar sigue el orden oficial de la lista.</p>}
        <ol className="relative border-l-2 border-outline-variant/70 ml-2 pl-4 flex flex-col gap-3">
          {pasos.map((s, i) => (
            <li key={i} className="relative">
              <span className={`absolute -left-[25px] top-0.5 w-5 h-5 rounded-full flex items-center justify-center ${s.rojo ? "bg-error text-on-error" : s.final ? "bg-primary text-on-primary" : "bg-surface-container-high text-on-surface-variant"}`}>
                <Icono n={s.icon} className="text-[13px]" />
              </span>
              <div className="text-[12px] text-on-surface-variant">{s.t}</div>
              <div className={`text-[14px] ${s.rojo ? "text-error font-semibold" : s.final ? "font-semibold" : ""}`}>{s.v}</div>
              {s.d && <div className="text-[12px] text-on-surface-variant italic">{s.d}</div>}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// Posición en la lista a lo largo del tiempo (N° 1 arriba). Una sola serie: sin leyenda; el color del punto es la prioridad.
function GraficoPosicion({ h }) {
  const [hover, setHover] = useState(null);
  const pts = h.puntos.filter((x) => !x.excluido);
  if (pts.length < 2) return <p className="text-[13px] text-on-surface-variant">Aún no hay suficiente historia en la lista.</p>;
  const W = 380, H = 190, m = { l: 40, r: 12, t: 12, b: 26 };
  const t = (f) => new Date(f + "T12:00:00").getTime();
  const x0 = t(pts[0].fecha), x1 = t(pts[pts.length - 1].fecha);
  const ymax = Math.max(...pts.map((p) => p.total));
  const X = (f) => m.l + ((t(f) - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
  const Y = (pos) => m.t + ((pos - 1) / (ymax - 1)) * (H - m.t - m.b);
  const ticks = [1, Math.round(ymax / 2), ymax];
  const meses = [...new Set(pts.map((p) => p.fecha.slice(0, 7)))];
  const nombreMes = (ym) => ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"][+ym.slice(5, 7) - 1];
  const linea = pts.map((p, i) => `${i ? "L" : "M"}${X(p.fecha).toFixed(1)},${Y(p.posicion).toFixed(1)}`).join(" ");
  const evs = h.eventos.filter((e) => e.fecha_evento >= pts[0].fecha);
  const hp = hover != null ? pts[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Posición del paciente en la lista a lo largo del tiempo">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke="rgb(var(--c-divider))" strokeWidth="1" />
            <text x={m.l - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="rgb(var(--c-muted))">N° {v}</text>
          </g>
        ))}
        {meses.map((ym) => { const xx = X(`${ym}-01` < pts[0].fecha ? pts[0].fecha : `${ym}-01`); return <text key={ym} x={xx} y={H - 8} fontSize="11" fill="rgb(var(--c-muted))" textAnchor="middle">{nombreMes(ym)}</text>; })}
        {evs.map((e, i) => {
          const xx = Math.min(Math.max(X(e.fecha_evento), m.l), W - m.r);
          const grave = e.severidad === "grave" || e.subtipo.includes("descompensaci");
          return (
            <g key={i}>
              <line x1={xx} x2={xx} y1={m.t} y2={H - m.b} stroke={grave ? "rgb(var(--c-error))" : "rgb(var(--c-verde))"} strokeWidth="1" strokeDasharray="3 3" />
              <circle cx={xx} cy={m.t} r="4" fill={grave ? "rgb(var(--c-error))" : "rgb(var(--c-verde))"}><title>{fmt(e.fecha_evento)}: {e.subtipo}</title></circle>
            </g>
          );
        })}
        <path d={linea} fill="none" stroke="rgb(var(--c-primary))" strokeWidth="2" strokeLinejoin="round" />
        {pts.map((p, i) => (
          <g key={p.fecha} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <circle cx={X(p.fecha)} cy={Y(p.posicion)} r="12" fill="transparent" />
            <circle cx={X(p.fecha)} cy={Y(p.posicion)} r={hover === i ? 6 : 4.5} fill={COLOR_HEX[p.categoria]} stroke="rgb(var(--c-raised))" strokeWidth="2" />
          </g>
        ))}
        {(() => { const u = pts[pts.length - 1]; return <text x={X(u.fecha) - 8} y={Y(u.posicion) + (Y(u.posicion) < 30 ? 16 : -8)} textAnchor="end" fontSize="12" fontWeight="600" fill="rgb(var(--c-text))">N° {u.posicion}</text>; })()}
      </svg>
      {hp && (
        <div className="absolute pointer-events-none bg-on-surface text-background text-[12px] rounded px-2 py-1 shadow"
          style={{ left: `${(X(hp.fecha) / W) * 100}%`, top: `${(Y(hp.posicion) / H) * 100}%`, transform: "translate(-50%, -120%)" }}>
          {fmt(hp.fecha)} · N° {hp.posicion} de {hp.total} · {ETIQUETA[hp.categoria]}{hp.riesgo_vital ? " · contactar hoy" : ""}
        </div>
      )}
      <div className="flex flex-wrap gap-3 text-[12px] text-on-surface-variant mt-1">
        {["alta", "media", "baja"].map((c) => <span key={c} className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: COLOR_HEX[c] }} />Prioridad {ETIQUETA[c].toLowerCase()}</span>)}
        <span className="flex items-center gap-1"><span className="w-3 border-t border-dashed border-error" />Descompensación</span>
        <span className="flex items-center gap-1"><span className="w-3 border-t border-dashed border-verde" />Estabilización</span>
      </div>
    </div>
  );
}
