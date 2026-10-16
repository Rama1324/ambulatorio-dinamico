import { Fragment, useEffect, useState } from "react";
import * as api from "../api";
import { descargarExcel } from "../excel";
import { Caja, Filtro, Icono, Prioridad } from "../componentes/comunes";
import { COLOR_HEX, ESPECIALIDADES } from "../constantes";
import { EvolucionPaciente } from "../ficha/Evolucion";
import { fmt } from "../util";

// Estadísticas (aporte de Diego, integrado y mejorado): curva de variación de la lista en el tiempo, por qué cambió
// (evento clínico exacto que entrega GET /estadisticas, una sola llamada) y evolución de cada paciente.
const TIPO_LARGO = {
  visita_urgencia: "Consulta en urgencia", hospitalizacion: "Hospitalización", examen_alterado: "Examen alterado",
  cambio_farmaco: "Cambio de fármaco", control_aps: "Control en APS",
};

// Clasifica el subtipo/texto de un evento en una categoría legible, aunque venga de la API como texto suelto.
function clasificarEvento(ev) {
  if (!ev) return null;
  if (ev.tipo_evento === "sin_evento") return "Sin evento propio (se movió por cambios en la lista)";
  if (ev.tipo_evento && TIPO_LARGO[ev.tipo_evento]) return TIPO_LARGO[ev.tipo_evento];
  const s = `${ev.subtipo || ""} ${ev.tipo_evento || ""}`.toLowerCase();
  if (s.includes("urgencia") || s.includes("esi")) return "Consulta en urgencia";
  if (s.includes("hospital")) return "Hospitalización";
  if (s.includes("examen") || s.includes("alterad")) return "Examen alterado";
  if (s.includes("farmaco") || s.includes("fármaco") || s.includes("dosis")) return "Cambio de fármaco";
  if (s.includes("aps") || s.includes("control")) return "Control en APS";
  return "Otro evento clínico";
}

// Área apilada: cantidad de pacientes por prioridad (alta/media/baja) en cada corte + línea de descompensaciones graves.
function GraficoComposicion({ serie }) {
  const [hover, setHover] = useState(null);
  if (serie.length < 2) return <p className="text-[13px] text-on-surface-variant">Aún no hay suficientes cortes para dibujar la curva.</p>;
  const W = 720, H = 240, m = { l: 42, r: 14, t: 14, b: 28 };
  const t = (f) => new Date(f + "T12:00:00").getTime();
  const x0 = t(serie[0].fecha), x1 = t(serie[serie.length - 1].fecha);
  const ymax = Math.max(...serie.map((s) => s.total), 1);
  const X = (f) => m.l + ((t(f) - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
  const Y = (v) => H - m.b - (v / ymax) * (H - m.t - m.b);
  const ticks = [0, Math.round(ymax / 2), ymax];
  const meses = [...new Set(serie.map((s) => s.fecha.slice(0, 7)))];
  const nombreMes = (ym) => ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"][+ym.slice(5, 7) - 1];
  // Área apilada de abajo hacia arriba: alta, media, baja.
  const capas = [
    { k: "alta", color: "rgb(var(--c-error))", base: () => 0 },
    { k: "media", color: "rgb(var(--c-ambar))", base: (s) => s.alta },
    { k: "baja", color: "rgb(var(--c-verde))", base: (s) => s.alta + s.media },
  ];
  const area = (capa) => {
    const sup = serie.map((s) => `${X(s.fecha).toFixed(1)},${Y(capa.base(s) + s[capa.k]).toFixed(1)}`);
    const inf = [...serie].reverse().map((s) => `${X(s.fecha).toFixed(1)},${Y(capa.base(s)).toFixed(1)}`);
    return `M${sup.join(" L")} L${inf.join(" L")} Z`;
  };
  // Gráfico aparte para las descompensaciones graves: con la escala de la lista completa (400+) quedarían planas en el cero
  const H2 = 120, gmax = Math.max(...serie.map((s) => s.graves), 1);
  const Y2 = (v) => H2 - m.b - (v / gmax) * (H2 - m.t - m.b);
  const lineaGraves = serie.map((s, i) => `${i ? "L" : "M"}${X(s.fecha).toFixed(1)},${Y2(s.graves).toFixed(1)}`).join(" ");
  const hs = hover != null ? serie[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Composición de la lista de espera por prioridad a lo largo del tiempo">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke="rgb(var(--c-divider))" strokeWidth="1" />
            <text x={m.l - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="rgb(var(--c-muted))">{v}</text>
          </g>
        ))}
        {capas.map((c) => <path key={c.k} d={area(c)} fill={c.color} fillOpacity="0.55" stroke={c.color} strokeOpacity="0.8" strokeWidth="1" />)}
        {hover != null && <line x1={X(serie[hover].fecha)} x2={X(serie[hover].fecha)} y1={m.t} y2={H - m.b} stroke="rgb(var(--c-text))" strokeWidth="1" strokeOpacity="0.5" />}
        {serie.map((s, i) => (
          <rect key={s.fecha} x={X(s.fecha) - 10} y={m.t} width="20" height={H - m.t - m.b} fill="transparent"
            onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
        ))}
        {meses.map((ym) => { const xx = X(`${ym}-01` < serie[0].fecha ? serie[0].fecha : `${ym}-01`); return <text key={ym} x={xx} y={H - 8} fontSize="11" fill="rgb(var(--c-muted))" textAnchor="middle">{nombreMes(ym)}</text>; })}
      </svg>
      {hs && (
        <div className="absolute pointer-events-none bg-on-surface text-background text-[12px] rounded px-2 py-1 shadow"
          style={{ left: `${(X(hs.fecha) / W) * 100}%`, top: "4%", transform: "translate(-50%, 0)" }}>
          {fmt(hs.fecha)} · {hs.total} en lista · alta {hs.alta} / media {hs.media} / baja {hs.baja} · {hs.graves} con descompensación grave
        </div>
      )}
      <div className="mt-4 text-[13px] font-semibold">Descompensaciones graves en la lista</div>
      <svg viewBox={`0 0 ${W} ${H2}`} className="w-full h-auto" role="img" aria-label="Pacientes con descompensación grave a lo largo del tiempo">
        {[0, gmax].map((v) => (
          <g key={v}>
            <line x1={m.l} x2={W - m.r} y1={Y2(v)} y2={Y2(v)} stroke="rgb(var(--c-divider))" strokeWidth="1" />
            <text x={m.l - 6} y={Y2(v) + 4} textAnchor="end" fontSize="11" fill="rgb(var(--c-muted))">{v}</text>
          </g>
        ))}
        <path d={lineaGraves} fill="none" stroke="rgb(var(--c-error))" strokeWidth="2" />
        {serie.map((s, i) => (
          <g key={s.fecha} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect x={X(s.fecha) - 10} y={m.t} width="20" height={H2 - m.t - m.b} fill="transparent" />
            <circle cx={X(s.fecha)} cy={Y2(s.graves)} r={hover === i ? 5 : 4} fill="rgb(var(--c-error))" stroke="rgb(var(--c-raised))" strokeWidth="2" />
          </g>
        ))}
        {(() => { const u = serie[serie.length - 1]; return <text x={X(u.fecha) - 8} y={Y2(u.graves) + (Y2(u.graves) < 30 ? 18 : -8)} textAnchor="end" fontSize="12" fontWeight="600" fill="rgb(var(--c-text))">{u.graves}</text>; })()}
        {meses.map((ym) => { const xx = X(`${ym}-01` < serie[0].fecha ? serie[0].fecha : `${ym}-01`); return <text key={ym} x={xx} y={H2 - 8} fontSize="11" fill="rgb(var(--c-muted))" textAnchor="middle">{nombreMes(ym)}</text>; })}
      </svg>
      <div className="flex flex-wrap gap-3 text-[12px] text-on-surface-variant mt-1">
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: COLOR_HEX.alta }} />Prioridad alta</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: COLOR_HEX.media }} />Media</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: COLOR_HEX.baja }} />Baja</span>
      </div>
    </div>
  );
}

// Indicadores para la jefatura del hospital. Un solo filtro de especialidad para toda la página:
// metas oficiales del HLF, situación de la lista, resumen por especialidad, evolución (gráficos aportados por Diego),
// tiempos de espera, por qué cambió la lista, trabajo pendiente y evolución de cada paciente.
const POR_PAGINA_EST = 25;

export function Indicadores({ fecha, data, esp, setEsp, onVer }) {
  const [k, setK] = useState(null);
  const [e, setE] = useState(null);
  const [err, setErr] = useState(null);
  const [verTabla, setVerTabla] = useState(false);
  const [verSaltos, setVerSaltos] = useState(5);
  const [buscaEst, setBuscaEst] = useState("");
  const [mostrar, setMostrar] = useState(POR_PAGINA_EST);
  const [expandido, setExpandido] = useState(null);
  const espApi = esp === "Todas" ? null : esp;
  useEffect(() => {
    let vivo = true;
    setErr(null);
    Promise.all([api.getKpis(fecha, espApi), api.getEstadisticas(fecha, espApi)])
      .then(([a, b]) => { if (vivo) { setK(a); setE(b); } })
      .catch((x) => { if (vivo) setErr(x.message); });
    return () => { vivo = false; };
  }, [fecha, espApi, data]);
  useEffect(() => setMostrar(POR_PAGINA_EST), [buscaEst, esp]);
  if (err) return <Caja><p className="text-error">No se pudieron calcular los indicadores: {err}</p></Caja>;
  if (!k || !e) return <p className="text-on-surface-variant">Calculando indicadores…</p>;

  const kap = k.concordancia.kappa;
  const re = k.reevaluacion, co = k.contactabilidad, cc = k.concordancia, tp = k.trabajo_pendiente, es = k.espera;
  const num = (x, d = 1) => (x == null ? "—" : String(Math.round(x * 10 ** d) / 10 ** d).replace(".", ","));
  const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
  const signo = (n) => (n > 0 ? `+${n}` : `${n}`);
  const serie = e.serie, ini = serie[0], fin = serie[serie.length - 1];
  const alcance = esp === "Todas" ? "todo el hospital" : esp;

  // Pacientes de la lista (misma especialidad) + el evento exacto que entrega el servidor
  const pacientes = (data?.pacientes || []).map((p) => ({ ...p, evento_causa: e.evento_causa?.[p.id_paciente] || null }));
  const subieron = pacientes.filter((p) => p.posicion_anterior && p.posicion_anterior - p.posicion >= 10)
    .map((p) => ({ ...p, salto: p.posicion_anterior - p.posicion })).sort((a, b) => b.salto - a.salto);
  const causas = {};
  for (const p of pacientes) {
    if (p.estado_clinico !== "descompensado" && !(p.posicion_anterior && p.posicion_anterior - p.posicion >= 10)) continue;
    const c = clasificarEvento(p.evento_causa || { tipo_evento: "sin_evento" });
    causas[c] = (causas[c] || 0) + 1;
  }
  const causasOrden = Object.entries(causas).sort((a, b) => b[1] - a[1]);
  const totalCausas = causasOrden.reduce((s, [, n]) => s + n, 0) || 1;
  const q = buscaEst.trim().toLowerCase();
  const listaPac = pacientes.filter((p) => !q || [p.nombre_fantasia, p.id_paciente, p.rut, p.diagnostico_texto].some((x) => (x || "").toLowerCase().includes(q)));
  const maxTramo = Math.max(...k.tramos_espera.map((t) => t.pacientes), 1);

  const Seccion = ({ titulo, sub, accion, children }) => (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-2 border-b border-outline-variant pb-1.5">
        <div><h2 className="text-[18px] font-semibold">{titulo}</h2>{sub && <p className="text-[13px] text-on-surface-variant">{sub}</p>}</div>
        {accion}
      </div>
      {children}
    </section>
  );
  const Meta = ({ titulo, valor, meta, estado, detalle }) => (
    <article className={`bg-surface-container-lowest border border-outline-variant rounded p-4 border-l-4 ${estado === "ok" ? "border-l-hlf" : estado === "mal" ? "border-l-ambar" : "border-l-outline"}`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-[15px]">{titulo}</h3>
        <span className={`text-[12px] font-semibold rounded px-2 py-0.5 whitespace-nowrap ${estado === "ok" ? "bg-hlf-claro text-hlf" : estado === "mal" ? "bg-ambar-container text-ambar" : "bg-surface-container text-on-surface-variant"}`}>
          {estado === "ok" ? "✓ En meta" : estado === "mal" ? "Bajo la meta" : "Aún sin datos"}</span>
      </div>
      <div className="text-[34px] font-bold text-primary-container mt-1 leading-tight">{valor}</div>
      <div className="text-[13px] text-on-surface-variant">Meta del hospital: <b>{meta}</b></div>
      <p className="text-[13px] mt-2">{detalle}</p>
    </article>
  );
  const Tarjeta = ({ titulo, valor, sub, tono }) => (
    <article className={`bg-surface-container-lowest border border-outline-variant rounded p-3.5 border-l-4 ${tono === "rojo" ? "border-l-error" : tono === "ambar" ? "border-l-ambar" : tono === "verde" ? "border-l-hlf" : "border-l-primary"}`}>
      <div className="text-[13px] text-on-surface-variant">{titulo}</div>
      <div className="text-[28px] font-bold leading-tight mt-0.5">{valor}</div>
      {sub && <div className="text-[12px] text-on-surface-variant mt-1">{sub}</div>}
    </article>
  );
  const Fila = ({ t, v, c = "" }) => <div className="flex justify-between gap-2"><span>{t}</span><b className={c}>{v}</b></div>;

  const exportar = () => descargarExcel(`indicadores_HLF_${k.fecha_corte}${espApi ? `_${espApi}` : ""}.xlsx`, [
    { nombre: "Metas del hospital", filas: [["Meta", "Valor", "Meta del hospital", "Cómo se mide"],
      ["Actualización tras un evento", "Al instante (milisegundos)", "Inmediata", "La lista se recalcula al registrar un evento, un informe o un paciente nuevo"],
      ["Tiempo hasta la revisión del especialista", re.evaluados ? `${num(re.mediana_horas)} h (mediana)` : "Sin datos", "—", "Horas desde que el evento llega hasta que el especialista revisa la prioridad (informativo)"],
      ["Concordancia con el especialista", kap == null ? "Sin datos" : `kappa ${num(kap, 2)} · ${cc.acuerdo_pct}% de acuerdo · n = ${cc.revisiones}`, "kappa ≥ 0,70", "Prioridad propuesta vs. decisión del especialista"],
      ["Cobertura con criterio común", `${k.cobertura.pct}% (${k.cobertura.evaluados} de ${k.cobertura.en_espera})`, "100%", k.cobertura.criterio]] },
    { nombre: "Por especialidad", filas: [["Especialidad", "En espera", "Alta", "Media", "Baja", "Más de 1 año", "Más de 500 días", "Mediana (días)", "Máxima (días)",
      "Descompensaciones graves", "Sin revisar", "Pendientes de revisión", "Sin responsable", "Egresos", "Atendidos", "Fallecidos"],
      ...[...k.por_especialidad, k.total_hospital].map((r) => [r.especialidad, r.en_espera, r.alta, r.media, r.baja, r.mas_de_1_anio, r.mas_de_500_dias,
        r.mediana_dias, r.maxima_dias, r.graves, r.graves_sin_revisar, r.pendientes_revision, r.sin_responsable, r.egresos, r.atendidos, r.fallecidos])] },
    { nombre: "Evolución", filas: [["Fecha", "En lista", "Alta", "Media", "Baja", "Descompensaciones graves", "Egresos acumulados", "Atendidos", "Fallecidos"],
      ...serie.map((s) => [fmt(s.fecha), s.total, s.alta, s.media, s.baja, s.graves, s.egresos, s.atendidos, s.fallecidos])] },
    { nombre: "Tiempos de espera", filas: [["Tramo", "Pacientes", "% de la lista"], ...k.tramos_espera.map((t) => [t.tramo, t.pacientes, `${pct(t.pacientes, k.cobertura.en_espera)}%`])] },
    { nombre: "Causas de los cambios", filas: [["Evento que movió la prioridad", "Pacientes"], ...causasOrden] },
    { nombre: "Mayores saltos", filas: [["Paciente", "RUT / ID", "Especialidad", "Diagnóstico", "N° anterior", "N° actual", "Subió", "Evento", "Fecha del evento"],
      ...subieron.map((p) => [p.nombre_fantasia, p.rut || p.id_paciente, p.especialidad, p.diagnostico_texto, p.posicion_anterior, p.posicion, p.salto,
        clasificarEvento(p.evento_causa) || "", fmt(p.evento_causa?.fecha_evento)])] },
    { nombre: "Trabajo pendiente", filas: [["Indicador", "Valor"], ["Pendientes de revisión", tp.por_estado.pendiente_revision], ["Pendientes de contacto", tp.por_estado.pendiente_contacto],
      ["Pendientes de cita", tp.por_estado.pendiente_cita], ["Con cita reservada", tp.por_estado.cita_reservada], ["Sin responsable", tp.sin_responsable],
      ["Seguimiento vencido", tp.seguimiento_vencido], ["Ajustes manuales vigentes", k.ajustes_manuales.vigentes], ["Ajustes sin efecto por evento nuevo", k.ajustes_manuales.sin_efecto_por_evento],
      ["Llamadas registradas", co.intentos], ["Llamadas con respuesta", co.efectivos], ["Egresos por fallecimiento (causal 9)", k.egresos.fallecidos], ["Atendidos en consulta nueva", k.egresos.atendidos]] },
    { nombre: "Información", filas: [["Dato", "Valor"], ["Alcance", alcance], ["Indicadores al", fmt(k.fecha_corte)], ["Evolución desde", fmt(ini.fecha)],
      ["Generado por", api.getUsuario() || "(sin nombre)"], ["Generado el", new Date().toLocaleString("es-CL")], ["Datos", "Sintéticos de demostración: no son pacientes reales"]] }]);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-bold">Indicadores de la lista de espera</h1>
          <p className="text-[14px] text-on-surface-variant">{esp === "Todas" ? "Todo el hospital" : <b>{esp}</b>} · al {fmt(k.fecha_corte)} · evolución desde el {fmt(ini.fecha)} · datos sintéticos de demostración</p>
        </div>
        <div className="flex flex-wrap items-end gap-2 text-[14px]">
          <Filtro label="Especialidad">
            <select value={esp} onChange={(x) => setEsp(x.target.value)} className="h-10 px-2 border border-outline-variant rounded bg-surface-container-lowest">{ESPECIALIDADES.map((x) => <option key={x}>{x}</option>)}</select>
          </Filtro>
          <button onClick={exportar} className="h-10 px-4 rounded bg-primary text-on-primary font-semibold flex items-center gap-1"><Icono n="download" className="text-[18px]" />Exportar todo a Excel</button>
        </div>
      </div>

      <Seccion titulo="Metas del hospital" sub="Los tres indicadores que fijó el HLF para el desafío. Se miden con lo registrado en la herramienta.">
        <div className="grid gap-4 lg:grid-cols-3">
          <Meta titulo="Actualización tras un evento" valor="al instante" meta="inmediata" estado="ok"
            detalle={<>Cada evento, informe o paciente nuevo recalcula la lista en milisegundos.{re.evaluados
              ? <> El especialista revisó la prioridad en una mediana de {num(re.mediana_horas)} h ({re.evaluados} revisadas; {re.sin_evaluar} sin revisar).</> : null}
              {" "}Hoy hay <b>{re.descompensados_en_lista}</b> descompensaciones graves: {re.evaluacion_hecha} revisadas y <b className={re.evaluacion_pendiente ? "text-error" : ""}>{re.evaluacion_pendiente} por revisar</b>.</>} />
          <Meta titulo="Concordancia con el especialista" valor={kap == null ? "—" : `κ ${num(kap, 2)}`} meta="kappa ≥ 0,70"
            estado={!cc.suficiente ? null : kap >= cc.meta ? "ok" : "mal"}
            detalle={cc.revisiones
              ? <>{cc.acuerdo_pct}% de acuerdo en {cc.revisiones} revisiones (confirmar = acuerdo; cambiar = desacuerdo).{!cc.suficiente && ` Con menos de ${cc.n_recomendado} revisiones el kappa es solo orientativo.`}</>
              : <>Todavía no hay revisiones. Se calcula cuando los especialistas confirman o cambian la prioridad que propone el sistema (se recomiendan al menos {cc.n_recomendado}).</>} />
          <Meta titulo="Cobertura con criterio común" valor={`${k.cobertura.pct}%`} meta="100% de la lista"
            estado={k.cobertura.pct === 100 ? "ok" : "mal"}
            detalle={<>{k.cobertura.evaluados} de {k.cobertura.en_espera} pacientes ordenados con el mismo criterio: {k.cobertura.criterio}.</>} />
        </div>
      </Seccion>

      <Seccion titulo="Situación de la lista hoy" sub={`${alcance === "todo el hospital" ? "Todo el hospital" : alcance}. Cambios comparados con el ${fmt(ini.fecha)}.`}>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          <Tarjeta titulo="Pacientes en espera" valor={fin.total} sub={`${signo(fin.total - ini.total)} desde el ${fmt(ini.fecha)}`} />
          <Tarjeta titulo="Prioridad alta" valor={fin.alta} tono="rojo" sub={`${pct(fin.alta, fin.total)}% de la lista · ${signo(fin.alta - ini.alta)}`} />
          <Tarjeta titulo="Esperan más de 1 año" valor={es.mas_de_1_anio} tono="ambar" sub={`${pct(es.mas_de_1_anio, fin.total)}% · ${es.mas_de_500_dias} con más de 500 días`} />
          <Tarjeta titulo="Mediana de espera" valor={`${num(es.mediana_dias, 0)} días`} sub={`Máxima: ${es.maxima_dias} días`} />
          <Tarjeta titulo="Descompensaciones graves" valor={fin.graves} tono="rojo" sub={`${re.evaluacion_hecha} revisadas · ${re.evaluacion_pendiente} por revisar`} />
          <Tarjeta titulo="Egresos del período" valor={fin.egresos - ini.egresos} tono="verde" sub={`${fin.atendidos - ini.atendidos} atendidos · ${fin.fallecidos - ini.fallecidos} fallecidos`} />
        </div>
      </Seccion>

      <Seccion titulo="Resumen por especialidad" sub="Haga clic en una especialidad para ver toda la página solo con ella.">
        <div className="bg-surface-container-lowest border border-outline-variant rounded overflow-x-auto">
          <table className="w-full text-[14px] border-collapse min-w-[860px]">
            <thead><tr className="bg-surface-container-low text-on-surface-variant text-[13px] border-b border-outline-variant text-right">
              <th className="py-2 px-3 text-left font-semibold">Especialidad</th><th className="px-2 font-semibold">En espera</th><th className="px-2 font-semibold">Alta</th>
              <th className="px-2 font-semibold">Más de 1 año</th><th className="px-2 font-semibold">Más de 500 días</th><th className="px-2 font-semibold">Mediana</th>
              <th className="px-2 font-semibold">Máxima</th><th className="px-2 font-semibold">Desc. graves</th><th className="px-2 font-semibold">Pend. revisión</th>
              <th className="px-2 font-semibold">Sin responsable</th><th className="px-3 font-semibold">Egresos</th></tr></thead>
            <tbody>
              {k.por_especialidad.map((r) => (
                <tr key={r.especialidad} onClick={() => setEsp(esp === r.especialidad ? "Todas" : r.especialidad)} tabIndex={0}
                  onKeyDown={(x) => { if (x.key === "Enter") setEsp(esp === r.especialidad ? "Todas" : r.especialidad); }}
                  className={`cursor-pointer border-b border-outline-variant/60 text-right ${esp === r.especialidad ? "bg-primary/10 font-semibold" : "hover:bg-surface-container-low"}`}>
                  <td className="py-2 px-3 text-left text-primary font-semibold">{r.especialidad}</td>
                  <td className="px-2">{r.en_espera}</td><td className="px-2">{r.alta}</td>
                  <td className="px-2">{r.mas_de_1_anio} <span className="text-[12px] text-on-surface-variant">({pct(r.mas_de_1_anio, r.en_espera)}%)</span></td>
                  <td className={`px-2 ${r.mas_de_500_dias ? "text-error font-semibold" : ""}`}>{r.mas_de_500_dias}</td>
                  <td className="px-2">{num(r.mediana_dias, 0)} d</td><td className="px-2">{r.maxima_dias} d</td>
                  <td className="px-2">{r.graves ? <span className={r.graves_sin_revisar ? "text-error font-semibold" : ""}>{r.graves}{r.graves_sin_revisar ? ` (${r.graves_sin_revisar} sin revisar)` : ""}</span> : "0"}</td>
                  <td className={`px-2 ${r.pendientes_revision ? "text-ambar" : ""}`}>{r.pendientes_revision}</td>
                  <td className="px-2">{r.sin_responsable}</td><td className="px-3">{r.egresos}</td>
                </tr>
              ))}
              {(() => { const r = k.total_hospital; return (
                <tr className="bg-surface-container-low font-semibold text-right">
                  <td className="py-2 px-3 text-left">Todo el hospital</td><td className="px-2">{r.en_espera}</td><td className="px-2">{r.alta}</td>
                  <td className="px-2">{r.mas_de_1_anio} <span className="text-[12px] text-on-surface-variant">({pct(r.mas_de_1_anio, r.en_espera)}%)</span></td>
                  <td className="px-2">{r.mas_de_500_dias}</td><td className="px-2">{num(r.mediana_dias, 0)} d</td><td className="px-2">{r.maxima_dias} d</td>
                  <td className="px-2">{r.graves}</td><td className="px-2">{r.pendientes_revision}</td><td className="px-2">{r.sin_responsable}</td><td className="px-3">{r.egresos}</td>
                </tr>); })()}
            </tbody>
          </table>
        </div>
      </Seccion>

      <Seccion titulo="Evolución de la lista" sub={`Cómo cambió la lista cada quincena, del ${fmt(ini.fecha)} al ${fmt(fin.fecha)}.`}
        accion={<button onClick={() => setVerTabla(!verTabla)} className="text-[13px] text-primary font-semibold">{verTabla ? "Ver gráfico" : "Ver como tabla"}</button>}>
        <Caja>
          {verTabla ? (
            <div className="overflow-x-auto"><table className="w-full text-[13px] text-right border-collapse">
              <thead><tr className="text-on-surface-variant border-b border-outline-variant">
                {["Fecha", "En lista", "Alta", "Media", "Baja", "Desc. graves", "Egresos acumulados"].map((c, i) => <th key={c} className={`py-1 px-2 font-semibold ${i ? "" : "text-left"}`}>{c}</th>)}</tr></thead>
              <tbody>{serie.map((s) => <tr key={s.fecha} className="border-b border-outline-variant/50">
                <td className="py-1 px-2 text-left">{fmt(s.fecha)}</td><td className="px-2">{s.total}</td><td className="px-2">{s.alta}</td><td className="px-2">{s.media}</td>
                <td className="px-2">{s.baja}</td><td className="px-2">{s.graves}</td><td className="px-2">{s.egresos}</td></tr>)}</tbody>
            </table></div>
          ) : <GraficoComposicion serie={serie} />}
        </Caja>
      </Seccion>

      <div className="grid gap-8 lg:grid-cols-2">
        <Seccion titulo="Tiempos de espera" sub="Cuántos pacientes hay en cada tramo de días esperando.">
          <Caja>
            <div className="flex flex-col gap-2.5">
              {k.tramos_espera.map((t) => (
                <div key={t.tramo} className="grid grid-cols-[150px_1fr_90px] items-center gap-3 text-[14px]" title={`${t.pacientes} pacientes`}>
                  <span>{t.tramo}</span>
                  <div className="h-5 rounded bg-surface-container-high overflow-hidden">
                    <div className={`h-full ${t.desde >= 365 ? "bg-error" : "bg-primary"}`} style={{ width: `${(t.pacientes / maxTramo) * 100}%` }} />
                  </div>
                  <span className="text-right"><b>{t.pacientes}</b> <span className="text-[12px] text-on-surface-variant">({pct(t.pacientes, k.cobertura.en_espera)}%)</span></span>
                </div>
              ))}
            </div>
            <p className="text-[12px] text-on-surface-variant mt-3">En rojo, los tramos de más de 1 año (criterio de antigüedad MINSAL Ord. 536/2025).</p>
          </Caja>
        </Seccion>

        <Seccion titulo="Por qué cambió la lista" sub="Pacientes descompensados o que subieron 10+ puestos, por el evento clínico que lo explica.">
          <Caja>
            {causasOrden.length === 0 ? <p className="text-[13px] text-on-surface-variant">No hay cambios de prioridad por eventos en este corte.</p> : (
              <div className="flex flex-col gap-2.5">
                {causasOrden.map(([c, n]) => (
                  <div key={c} className="grid grid-cols-[180px_1fr_40px] items-center gap-3 text-[14px]">
                    <span>{c}</span>
                    <div className="h-5 rounded bg-surface-container-high overflow-hidden"><div className="h-full bg-primary" style={{ width: `${(n / totalCausas) * 100}%` }} /></div>
                    <b className="text-right">{n}</b>
                  </div>
                ))}
              </div>
            )}
            <p className="text-[12px] text-on-surface-variant mt-3">El orden lo calculan reglas oficiales; el evento clínico es la causa del cambio.</p>
          </Caja>
        </Seccion>
      </div>

      <Seccion titulo={`Mayores saltos en la lista (${subieron.length})`} sub="Pacientes que avanzaron 10 o más puestos en las últimas dos semanas, con el evento que lo explica. Clic para ver su ficha.">
        {subieron.length === 0 ? <p className="text-[13px] text-on-surface-variant">Nadie avanzó 10 o más puestos en las últimas dos semanas.</p> : (
          <div className="flex flex-col gap-2">
            {subieron.slice(0, verSaltos).map((p) => (
              <button key={p.id_paciente} onClick={() => onVer(p.id_paciente)}
                className="text-left bg-surface-container-lowest border border-outline-variant rounded p-3 hover:bg-surface-container-low flex flex-wrap items-center gap-x-5 gap-y-1">
                <div className="flex items-center gap-2 min-w-[260px] flex-1">
                  <Prioridad cat={p.categoria} />
                  <div>
                    <div className="font-semibold text-[14px]">{p.nombre_fantasia} <span className="font-normal text-on-surface-variant">· {p.especialidad}</span></div>
                    <div className="text-[13px] text-on-surface-variant">{p.diagnostico_cie10} {p.diagnostico_texto}</div>
                  </div>
                </div>
                <div className="text-[14px] whitespace-nowrap">N° {p.posicion_anterior} <Icono n="arrow_forward" className="text-[16px]" /> <b>N° {p.posicion}</b> <span className="text-error font-semibold ml-1">▲ {p.salto}</span></div>
                <div className="text-[13px] flex-1 min-w-[240px]">
                  {p.evento_causa ? <span><b>{clasificarEvento(p.evento_causa)}</b> · {fmt(p.evento_causa.fecha_evento)}</span>
                    : <span className="text-on-surface-variant">Sin evento propio: avanzó porque otros salieron de la lista o cumplió más de 1 año</span>}
                </div>
              </button>
            ))}
            {subieron.length > 5 && <button onClick={() => setVerSaltos(verSaltos > 5 ? 5 : subieron.length)} className="self-start text-[13px] text-primary font-semibold">
              {verSaltos > 5 ? "Ver menos" : `Ver los ${subieron.length}`}</button>}
          </div>
        )}
      </Seccion>

      <Seccion titulo="Trabajo pendiente y seguimiento" sub="Lo que falta hacer con los pacientes de la lista y lo que ya se registró.">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Caja titulo="Gestión de los casos">
            <div className="text-[14px] space-y-1">
              <Fila t="Pendientes de revisión" v={tp.por_estado.pendiente_revision} c="text-ambar" />
              <Fila t="Pendientes de contacto" v={tp.por_estado.pendiente_contacto} />
              <Fila t="Pendientes de cita" v={tp.por_estado.pendiente_cita} />
              <Fila t="Con cita reservada" v={tp.por_estado.cita_reservada} c="text-hlf" />
              <Fila t="Sin responsable asignado" v={tp.sin_responsable} c={tp.sin_responsable ? "text-ambar" : ""} />
              <Fila t="Seguimiento vencido" v={tp.seguimiento_vencido} c={tp.seguimiento_vencido ? "text-error" : ""} />
            </div>
          </Caja>
          <Caja titulo="Revisión del especialista">
            <div className="text-[14px] space-y-1">
              <Fila t="Requieren revisión" v={k.alertas.revision_sugerida} c="text-ambar" />
              <Fila t="Revisiones registradas" v={cc.revisiones} />
              <Fila t="Ajustes manuales vigentes" v={k.ajustes_manuales.vigentes} />
              <Fila t="Ajustes sin efecto por evento nuevo" v={k.ajustes_manuales.sin_efecto_por_evento} c={k.ajustes_manuales.sin_efecto_por_evento ? "text-ambar" : ""} />
            </div>
          </Caja>
          <Caja titulo="Contacto con pacientes">
            <div className="text-[14px] space-y-1">
              <Fila t="Llamadas registradas" v={co.intentos} />
              <Fila t="Con respuesta" v={co.pct == null ? "—" : `${co.efectivos} (${co.pct}%)`} />
              <Fila t="Pacientes con reintentos" v={co.pacientes_con_reintentos} c={co.pacientes_con_reintentos ? "text-ambar" : ""} />
            </div>
          </Caja>
          <Caja titulo="Egresos de la lista">
            <div className="text-[14px] space-y-1">
              <Fila t="Atendidos en consulta nueva" v={k.egresos.atendidos} c="text-hlf" />
              <Fila t="Fallecimiento (causal 9)" v={k.egresos.fallecidos} />
              <p className="text-[12px] text-on-surface-variant pt-1">Acumulado al {fmt(k.fecha_corte)}.</p>
            </div>
          </Caja>
        </div>
      </Seccion>

      <details className="bg-surface-container-lowest border border-outline-variant rounded group">
        <summary className="px-4 py-3 cursor-pointer text-[16px] font-semibold flex items-center gap-2">
          <Icono n="expand_more" className="text-[20px] group-open:rotate-180 transition-transform" />Evolución de cada paciente ({pacientes.length})
          <span className="text-[13px] font-normal text-on-surface-variant">· por qué está en su lugar y cómo se ha movido</span>
        </summary>
        <div className="px-4 pb-4">
          <div className="flex justify-end mb-2"><input value={buscaEst} onChange={(x) => setBuscaEst(x.target.value)} placeholder="Buscar nombre, RUT o diagnóstico"
            className="h-9 px-2 w-64 border border-outline-variant rounded text-[14px]" /></div>
          <div className="border border-outline-variant rounded overflow-x-auto">
            <table className="w-full text-left border-collapse text-[14px] min-w-[640px]">
              <thead><tr className="bg-surface-container-low text-[13px] text-on-surface-variant border-b border-outline-variant">
                <th className="py-2 px-3 font-semibold w-14">N°</th><th className="py-2 px-2 font-semibold">Prioridad</th><th className="py-2 px-3 font-semibold">Paciente / diagnóstico</th>
                <th className="py-2 px-2 font-semibold text-right">Cambio (14 días)</th><th className="py-2 px-3 font-semibold text-right">Espera</th><th className="w-8" /></tr></thead>
              <tbody>
                {listaPac.slice(0, mostrar).map((p) => {
                  const abierto = expandido === p.id_paciente;
                  const dl = p.posicion_anterior ? p.posicion_anterior - p.posicion : 0;
                  return (
                    <Fragment key={p.id_paciente}>
                      <tr onClick={() => setExpandido(abierto ? null : p.id_paciente)} tabIndex={0} onKeyDown={(x) => { if (x.key === "Enter") setExpandido(abierto ? null : p.id_paciente); }}
                        className={`cursor-pointer border-b border-outline-variant/60 ${abierto ? "bg-primary/10" : "hover:bg-surface-container-low"}`}>
                        <td className={`py-2 px-3 font-semibold ${p.riesgo_vital ? "border-l-4 border-l-error" : "border-l-4 border-l-transparent"}`}>{p.posicion}</td>
                        <td className="py-2 px-2"><Prioridad cat={p.categoria} /></td>
                        <td className="py-2 px-3"><div className="font-semibold">{p.nombre_fantasia}</div><div className="text-[13px] text-on-surface-variant">{p.especialidad} · {p.diagnostico_cie10} {p.diagnostico_texto}</div></td>
                        <td className="py-2 px-2 text-right whitespace-nowrap">{dl > 0 ? <span className="text-error font-semibold">▲ {dl}</span> : dl < 0 ? <span className="text-on-surface-variant">▼ {-dl}</span> : <span className="text-on-surface-variant">—</span>}</td>
                        <td className="py-2 px-3 text-right whitespace-nowrap">{p.dias_espera} días</td>
                        <td className="py-2 px-2 text-on-surface-variant"><Icono n={abierto ? "expand_less" : "expand_more"} className="text-[20px]" /></td>
                      </tr>
                      {abierto && <tr><td colSpan={6} className="px-4 py-3 border-b border-outline-variant">
                        <div className="flex justify-end"><button onClick={() => onVer(p.id_paciente)} className="text-[13px] text-primary font-semibold flex items-center gap-1"><Icono n="open_in_new" className="text-[16px]" />Ver ficha completa</button></div>
                        <EvolucionPaciente p={p} fecha={fecha} />
                      </td></tr>}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            {listaPac.length === 0 && <p className="p-5 text-on-surface-variant text-[13px]">No hay pacientes con esa búsqueda.</p>}
          </div>
          <div className="flex items-center justify-between mt-2 text-[13px] text-on-surface-variant">
            <span>Mostrando {Math.min(mostrar, listaPac.length)} de {listaPac.length} pacientes.</span>
            {mostrar < listaPac.length && <button onClick={() => setMostrar(mostrar + POR_PAGINA_EST * 2)} className="text-primary font-semibold">Mostrar más</button>}
          </div>
        </div>
      </details>

      <p className="text-[12px] text-on-surface-variant">Indicadores de {alcance} al {fmt(k.fecha_corte)}, calculados en el servidor con el mismo motor de reglas de la lista
        (Tabla SSMSO 2025 del HLF y MINSAL Ord. 536/2025). La herramienta propone y explica; el equipo clínico decide. Datos sintéticos de demostración.</p>
    </div>
  );
}
