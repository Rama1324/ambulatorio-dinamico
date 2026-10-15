import { useEffect, useRef, useState } from "react";
import * as api from "../api";
import { COLOR_HEX, ETIQUETA, EVENTOS, FACTOR, TIPO_EVENTO, fmt } from "../lib/constantes";
import { Caja, EstadoRevision, Filtro, Icono, Prioridad } from "../components/ui";

export function Ficha({ p, total, detalle, fecha, esApi, demo, onCambio, onAviso, onDestacar }) {
  const [historia, setHistoria] = useState(null);
  useEffect(() => { api.getHistoria(p.id_paciente, fecha).then(setHistoria).catch(() => setHistoria(null)); }, [p.id_paciente, fecha, p.categoria, p.posicion]);
  const [resumen, setResumen] = useState(null);
  const [cargando, setCargando] = useState(null);
  const [ajuste, setAjuste] = useState(null);
  const [tipoEv, setTipoEv] = useState("hospitalizacion");
  useEffect(() => { setResumen(null); }, [p.categoria, p.estado_clinico, fecha]);

  const correr = async (nombre, fn) => {
    setCargando(nombre);
    try { await fn(); } catch (e) { onAviso({ titulo: "No se pudo completar: " + e.message }); } finally { setCargando(null); }
  };
  const registrarEvento = (ev, origen) => correr("evento", async () => {
    const r = await api.postEvento({ id_paciente: p.id_paciente, fecha_corte: fecha, fecha_evento: ev.fecha_evento || fecha,
      tipo_evento: ev.tipo_evento, subtipo: ev.subtipo, severidad: ev.severidad, detalle: ev.detalle });
    await onCambio(); onDestacar(p.id_paciente);
    onAviso({ titulo: `${origen}. Lista actualizada`, antes: r.posicion_antes, despues: r.posicion_despues, cat: r.paciente?.categoria });
  });
  const [tab, setTab] = useState("resumen");
  const confirmar = () => correr("rev", async () => { await api.postRevision(p.id_paciente, { accion: "confirmar", fecha_corte: fecha }); await onCambio(); onAviso({ titulo: "Prioridad confirmada" }); });
  const guardarAjuste = () => correr("rev", async () => {
    await api.postRevision(p.id_paciente, { accion: "ajustar", categoria_ajustada: ajuste.categoria, motivo: ajuste.motivo, fecha_corte: fecha });
    setAjuste(null); await onCambio(); onAviso({ titulo: "Cambio de prioridad registrado" });
  });
  const pedirResumen = () => correr("ia", async () => setResumen(await api.postExplicar(p.id_paciente, fecha)));

  const timeline = detalle ? [
    ...detalle.eventos_clinicos.map((e) => ({ f: e.fecha_evento, t: `${TIPO_EVENTO[e.tipo_evento] || e.tipo_evento}: ${e.subtipo}`, d: e.detalle?.startsWith("Informe") ? e.detalle : null, rojo: e.severidad === "grave", nuevo: e.id_evento?.startsWith("EV-DEMO") })),
    ...detalle.mediciones.map((m) => ({ f: m.fecha_medicion, t: `${m.tipo_medicion.replace("_", " ")}: ${m.valor} ${m.unidad}`, d: m.fuera_de_rango ? "fuera de rango" : null, ambar: m.fuera_de_rango })),
    ...(detalle.citaciones || []).map((c) => ({ f: c.fecha_cita, t: `Citación ${c.id_box}: ${c.estado_cita.replace("_", " ")}`, ambar: c.estado_cita === "no_asistio" })),
    { f: p.fecha_ingreso_lista, t: "Ingreso de la interconsulta", d: `prioridad inicial ${p.prioridad_inicial}` },
  ].sort((a, b) => b.f.localeCompare(a.f)) : [];

  return (
    <>
      <Caja>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[18px] font-semibold">{p.nombre_fantasia}</div>
            <div className="text-[14px] text-on-surface-variant">{p.edad} años · {p.sexo === "F" ? "Femenino" : "Masculino"} · {p.comuna} · {p.id_paciente}</div>
          </div>
          <Prioridad cat={p.categoria} />
        </div>
        {p.contactar_hoy && <div className="mt-3 p-2.5 rounded bg-error-container text-on-error-container text-[14px] flex gap-2"><Icono n="call" className="text-[20px]" /><span><b>Contactar hoy.</b> Evaluar sobrecupo o derivación a urgencia según criterio médico.</span></div>}
        {p.riesgo_vital && !p.contactar_hoy && p.contacto && <div className="mt-3 p-2.5 rounded bg-hlf-claro text-hlf text-[14px] flex gap-2"><Icono n="task_alt" className="text-[20px]" /><span><b>{p.contacto.texto}</b> · {p.contacto.usuario}{p.contacto.nota && ` · ${p.contacto.nota}`}</span></div>}
        {p.estado_revision === "requiere_revision" && <div className="mt-2 p-2.5 rounded bg-ambar-container text-ambar text-[14px] flex gap-2"><Icono n="rate_review" className="text-[20px]" /><span><b>Requiere nueva revisión:</b> {p.revision_vencida_por} después de la última revisión.</span></div>}
        {p.estado_revision === "pendiente" && p.revision_sugerida?.length > 0 && <div className="mt-2 p-2.5 rounded bg-ambar-container/60 text-ambar text-[14px] flex gap-2"><Icono n="rate_review" className="text-[20px]" /><span><b>Revisión sugerida:</b> {[...new Set(p.revision_sugerida.map((s) => s.motivo))].join(" · ")}</span></div>}
        <dl className="mt-3 grid grid-cols-[130px_1fr] gap-y-1 text-[14px]">
          <dt className="text-on-surface-variant">Especialidad</dt><dd>{p.especialidad}</dd>
          <dt className="text-on-surface-variant">Diagnóstico</dt><dd>{p.diagnostico_cie10} · {p.diagnostico_texto}</dd>
          <dt className="text-on-surface-variant">Ingreso a lista</dt><dd>{fmt(p.fecha_ingreso_lista)} ({p.dias_espera} días)</dd>
          <dt className="text-on-surface-variant">Prioridad inicial</dt><dd className="capitalize">{p.prioridad_inicial}</dd>
          <dt className="text-on-surface-variant">N° en la lista</dt><dd>{p.posicion} de {total}</dd>
          <dt className="text-on-surface-variant">Revisión</dt><dd><EstadoRevision p={p} /></dd>
          {(p.grupo_proteccion || p.acg) && <><dt className="text-on-surface-variant">Riesgo social</dt><dd>{[p.grupo_proteccion && `Grupo ${p.grupo_proteccion}`, p.acg && `ACG ${p.acg}`].filter(Boolean).join(" · ")}</dd></>}
          {p.comorbilidades?.length > 0 && <><dt className="text-on-surface-variant">Comorbilidades</dt><dd>{p.comorbilidades.map((c) => c.nombre).join(", ")}</dd></>}
        </dl>
        {p.categoria !== p.categoria_sistema && <p className="mt-2 text-[14px] text-on-surface-variant">El sistema proponía prioridad {p.categoria_sistema}; el equipo clínico la cambió a {p.categoria}. Motivo: {p.revision?.motivo}</p>}
      </Caja>

      <div role="tablist" className="flex border-b-2 border-outline-variant bg-surface-container-lowest text-[15px] sticky top-[var(--ficha-top,0px)] z-10">
        {[["resumen", "Resumen"], ["puntaje", "Puntaje"], ["registrar", "Registrar"], ["historia", "Historia"]].map(([k, t]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`flex-1 h-11 border-b-4 -mb-[2px] ${tab === k ? "border-primary text-primary font-semibold" : "border-transparent text-on-surface-variant"}`}>{t}</button>
        ))}
      </div>

      {tab === "resumen" && <>
      <Caja titulo="Cómo se decidió su lugar en la lista">
        <Camino p={p} total={total} />
      </Caja>
      {esApi && p.riesgo_vital && <Contacto p={p} fecha={fecha} onListo={async (r) => { await onCambio(); onAviso({ titulo: `${p.nombre_fantasia}: ${r.contacto.texto}` }); }} onAviso={onAviso} />}
      </>}

      {tab === "puntaje" && <>
      {p.criticidad != null && <Criticidad p={p} />}

      <Caja titulo="Puntaje de riesgo clínico (LACE)">
        <BoletaLace lace={p.lace} />
      </Caja>

      <Caja titulo="Evolución en la lista">
        {historia ? <GraficoPosicion h={historia} /> : <p className="text-[14px] text-on-surface-variant">Cargando…</p>}
      </Caja>

      <Caja titulo={`Fundamento de la prioridad ${ETIQUETA[p.categoria].toLowerCase()}`}>
        <ul className="space-y-2.5 text-[14px]">
          {p.razones.map((r, i) => (
            <li key={i} className={r.factor === "tabla_oficial" || r.factor === "riesgo_vital" ? "pl-2 border-l-4 border-error" : "pl-2 border-l-4 border-outline-variant"}>
              <div className="text-[13px] text-on-surface-variant">{FACTOR[r.factor] || r.factor}</div>
              <div>{r.valor}</div>
              <div className="text-[13px] text-on-surface-variant italic">Fuente: {r.fuente}</div>
            </li>
          ))}
        </ul>
      </Caja>
      </>}

      {tab === "resumen" && (esApi ? (
        <>
          <Caja titulo="Decisión clínica">
            <div className="flex gap-2">
              <button onClick={confirmar} disabled={cargando} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-50">Confirmar prioridad</button>
              <button onClick={() => setAjuste(ajuste ? null : { categoria: p.categoria, motivo: "" })} className="flex-1 py-2 rounded border border-primary text-primary font-semibold">Cambiar prioridad</button>
            </div>
            {ajuste && (
              <div className="mt-3 flex flex-col gap-2">
                <select value={ajuste.categoria} onChange={(e) => setAjuste({ ...ajuste, categoria: e.target.value })} className="h-11 px-2 border border-outline-variant rounded bg-surface-container-lowest">
                  {Object.entries(ETIQUETA).map(([k, v]) => <option key={k} value={k}>Prioridad {v.toLowerCase()}</option>)}
                </select>
                <input placeholder="Motivo clínico (obligatorio)" value={ajuste.motivo} onChange={(e) => setAjuste({ ...ajuste, motivo: e.target.value })} className="h-11 px-2 border border-outline-variant rounded" />
                <button disabled={!ajuste.motivo} onClick={guardarAjuste} className="py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Guardar cambio</button>
              </div>
            )}
          </Caja>

          <Caja titulo="Resumen para el equipo" accion={<button onClick={pedirResumen} disabled={cargando} className="text-[14px] text-primary font-semibold disabled:opacity-50">{cargando === "ia" ? "Redactando…" : resumen ? "Actualizar" : "Generar"}</button>}>
            {resumen ? <>
              <p className="text-[14px] leading-relaxed">{resumen.explicacion_ia}</p>
              <p className="text-[13px] text-on-surface-variant mt-2">Texto redactado automáticamente a partir del fundamento ({resumen.fuente === "bedrock" ? "Amazon Bedrock" : "plantilla"}). No modifica la prioridad.</p>
            </> : <p className="text-[14px] text-on-surface-variant">Redacta en lenguaje simple el fundamento, por ejemplo para contactar al paciente.</p>}
          </Caja>
        </>
      ) : <Caja><p className="text-on-surface-variant text-[14px]">Sin conexión al servidor: se muestra la lista precalculada. Registrar decisiones requiere la API.</p></Caja>)}

      {tab === "registrar" && (esApi ? (
        <>
          <Informe p={p} fecha={fecha} cargando={cargando} onConfirmar={(ev) => registrarEvento(ev, "Evento del informe registrado")} onAviso={onAviso} />

          <Novedad p={p} fecha={fecha} onListo={async (r) => {
            await onCambio();
            onAviso(r.en_lista ? { titulo: `Registrado: ${r.mensaje}`, despues: r.paciente?.posicion, antes: p.posicion, cat: r.paciente?.categoria }
              : { titulo: `${p.nombre_fantasia}: ${r.mensaje}` });
          }} onAviso={onAviso} />

          {demo && (
            <Caja titulo="Simular evento (demostración)" className="border-ambar/50">
              <div className="flex gap-2">
                <select value={tipoEv} onChange={(e) => setTipoEv(e.target.value)} className="flex-1 h-11 px-2 border border-outline-variant rounded bg-surface-container-lowest">
                  {Object.entries(EVENTOS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
                <button onClick={() => registrarEvento(EVENTOS[tipoEv], "Evento simulado")} disabled={cargando} className="px-4 rounded bg-ambar text-background font-semibold disabled:opacity-50">Simular</button>
              </div>
            </Caja>
          )}
        </>
      ) : <Caja><p className="text-on-surface-variant text-[14px]">Registrar informes y novedades requiere conexión al servidor.</p></Caja>)}

      {tab === "historia" && <Caja titulo="Historia mientras espera">
        <ol className="text-[14px]">
          {timeline.map((x, i) => (
            <li key={i} className={`grid grid-cols-[88px_1fr] gap-2 py-1.5 border-b border-outline-variant/50 ${x.nuevo ? "bg-ambar-container/50" : ""}`}>
              <span className="text-on-surface-variant text-[14px]">{fmt(x.f)}</span>
              <span className={x.rojo ? "text-error font-semibold" : x.ambar ? "text-ambar" : ""}>{x.t}{x.d && <span className="text-on-surface-variant font-normal"> · {x.d}</span>}</span>
            </li>
          ))}
          {!detalle && <li className="text-on-surface-variant">Cargando…</li>}
        </ol>
      </Caja>}
    </>
  );
}

// Registro del contacto con un paciente 'contactar hoy': reconoce la alerta con un resultado (evita la fatiga de alertas).
function Contacto({ p, fecha, onListo, onAviso }) {
  const [nota, setNota] = useState("");
  const [enviando, setEnviando] = useState(null);
  const enviar = async (resultado) => {
    setEnviando(resultado);
    try { onListo(await api.postContacto(p.id_paciente, { resultado, nota, fecha_corte: fecha })); setNota(""); }
    catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(null); }
  };
  const ops = [["citado", "Citado (sobrecupo)", "bg-primary text-on-primary"], ["derivado_urgencia", "Derivado a urgencia", "bg-error text-on-error"],
    ["se_mantiene", "Se mantiene en lista", "border border-outline-variant"], ["no_contesta", "No contesta", "border border-outline-variant"]];
  return (
    <Caja titulo="Registrar contacto">
      {p.contacto && <p className="text-[14px] mb-2">Último: <b>{p.contacto.texto}</b> · {p.contacto.usuario}</p>}
      <input value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Nota (opcional): p. ej. hora citada, quién contestó" className="w-full h-11 px-2 border border-outline-variant rounded mb-2 text-[14px]" />
      <div className="grid grid-cols-2 gap-2 text-[14px]">
        {ops.map(([k, t, c]) => <button key={k} disabled={enviando} onClick={() => enviar(k)} className={`py-2 rounded font-semibold disabled:opacity-50 ${c}`}>{enviando === k ? "…" : t}</button>)}
      </div>
      <p className="text-[13px] text-on-surface-variant mt-2">Al registrar el contacto la alerta "contactar hoy" se apaga (salvo "no contesta"). El paciente sigue priorizado.</p>
    </Caja>
  );
}

// Boleta del puntaje LACE: cada línea con sus puntos publicados (van Walraven et al., CMAJ 2010, Tabla 3).
function BoletaLace({ lace }) {
  const max = { L: 7, A: 3, C: 5, E: 4 };
  return (
    <div>
      <table className="w-full text-[14px]">
        <tbody>
          {lace.partes.map((x) => (
            <tr key={x.letra} className="border-b border-outline-variant/60">
              <td className="py-1.5 w-8"><span className="inline-flex w-6 h-6 items-center justify-center rounded bg-primary/10 text-primary font-bold">{x.letra}</span></td>
              <td className="py-1.5">
                <div>{x.nombre}</div>
                <div className="text-[13px] text-on-surface-variant">{x.valor}</div>
              </td>
              <td className="py-1.5 w-28">
                <div className="h-2 rounded bg-surface-container-high overflow-hidden"><div className="h-full bg-primary" style={{ width: `${(x.puntos / max[x.letra]) * 100}%` }} /></div>
              </td>
              <td className={`py-1.5 w-14 text-right font-semibold ${x.puntos ? "" : "text-on-surface-variant"}`}>+{x.puntos}</td>
            </tr>
          ))}
          <tr>
            <td colSpan={3} className="pt-2 font-bold text-primary-container">Puntaje LACE total</td>
            <td className="pt-2 text-right text-[22px] font-bold text-primary-container">{lace.total}</td>
          </tr>
        </tbody>
      </table>
      <p className="text-[13px] text-on-surface-variant mt-2">
        Puntos según {lace.fuente}. Ordena a los pacientes dentro de la misma prioridad (más puntos, antes). L queda en 0 porque el registro no trae los días de estada.
      </p>
    </div>
  );
}

// Camino de la decisión: cada paso con su fuente (sin puntos ni pesos).
function Camino({ p, total }) {
  const rz = Object.fromEntries(p.razones.map((r) => [r.factor, r]));
  const subio = rz.tabla_oficial && rz.tabla_oficial.valor.startsWith('"') && !rz.tabla_oficial.valor.includes("no supera");
  const pasos = [{ t: "Interconsulta", v: `Prioridad ${p.prioridad_inicial}`, f: "Especialista al priorizar la SIC", cat: p.prioridad_inicial }];
  if (p.estado_clinico === "descompensado" && rz.evento) pasos.push({ t: "Evento posterior", v: rz.evento.valor, f: "Registro clínico", icon: "emergency" });
  if (p.estado_clinico === "estabilizado" && rz.evento) pasos.push({ t: "Evolución", v: rz.evento.valor.split(":")[0], f: "Registro clínico", icon: "trending_down" });
  if (subio) pasos.push({ t: "Tabla de priorización HLF", v: rz.tabla_oficial.valor.split("→")[0].replaceAll('"', "").trim(), f: rz.tabla_oficial.fuente.replace("Tabla SSMSO 2025, HLF, ", "SSMSO 2025, "), cat: p.categoria_sistema });
  else if (rz.tabla_oficial) pasos.push({ t: "Tabla de priorización HLF", v: "Sin cambio de prioridad", f: "Revisión clínica sugerida", icon: "rate_review" });
  if (p.categoria !== p.categoria_sistema) pasos.push({ t: "Decisión clínica", v: `Prioridad ${p.categoria}`, f: p.revision?.motivo, cat: p.categoria });
  if (p.riesgo_vital) pasos.push(p.contactar_hoy ? { t: "Contactar hoy", v: "Riesgo vital", f: "Criterio MINSAL", icon: "call", rojo: true }
    : { t: "Riesgo vital", v: "Contactado", f: p.contacto?.texto, icon: "task_alt", cat: "alta" });
  if (p.grupo_proteccion) pasos.push({ t: "Grupo de especial protección", v: p.grupo_proteccion, f: "MINSAL criterio 2", icon: "shield_person" });
  pasos.push({ t: "Lugar en la lista", v: `N° ${p.posicion} de ${total}`, f: p.antiguedad_mayor_1_anio ? "Más de 1 año en espera" : `${p.dias_espera} días en espera`, final: true });
  return (
    <div className="flex flex-wrap items-stretch gap-1">
      {pasos.map((s, i) => (
        <div key={i} className="flex items-center gap-1">
          <div className={`rounded border px-2.5 py-1.5 min-w-[96px] max-w-[160px] ${s.rojo ? "bg-error text-on-error border-error" : s.final ? "bg-primary text-on-primary border-primary" : "bg-surface-container-lowest border-outline-variant"}`}
            style={s.cat && !s.rojo && !s.final ? { borderTop: `4px solid ${COLOR_HEX[s.cat]}` } : undefined}>
            <div className={`text-[12px] ${s.rojo || s.final ? "opacity-90" : "text-on-surface-variant"}`}>{s.icon && <Icono n={s.icon} className="text-[14px] mr-0.5" />}{s.t}</div>
            <div className="text-[14px] font-semibold leading-tight">{s.v}</div>
            {s.f && <div className={`text-[12px] leading-tight mt-0.5 ${s.rojo || s.final ? "opacity-80" : "text-on-surface-variant"}`}>{s.f}</div>}
          </div>
          {i < pasos.length - 1 && <Icono n="arrow_forward" className="text-[18px] text-outline" />}
        </div>
      ))}
    </div>
  );
}

// Posición en la lista a lo largo del tiempo (N° 1 arriba). Una sola serie: sin leyenda; el color del punto es la prioridad.
function GraficoPosicion({ h }) {
  const [hover, setHover] = useState(null);
  const pts = h.puntos.filter((x) => !x.excluido);
  if (pts.length < 2) return <p className="text-[14px] text-on-surface-variant">Aún no hay suficiente historia en la lista.</p>;
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
            <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} className="stroke-outline-variant" strokeWidth="1" />
            <text x={m.l - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" className="fill-on-surface-variant">N° {v}</text>
          </g>
        ))}
        {meses.map((ym) => { const xx = X(`${ym}-01` < pts[0].fecha ? pts[0].fecha : `${ym}-01`); return <text key={ym} x={xx} y={H - 8} fontSize="11" className="fill-on-surface-variant" textAnchor="middle">{nombreMes(ym)}</text>; })}
        {evs.map((e, i) => {
          const xx = Math.min(Math.max(X(e.fecha_evento), m.l), W - m.r);
          const grave = e.severidad === "grave" || e.subtipo.includes("descompensaci");
          return (
            <g key={i}>
              <line x1={xx} x2={xx} y1={m.t} y2={H - m.b} className={grave ? "stroke-error" : "stroke-verde"} strokeWidth="1" strokeDasharray="3 3" />
              <circle cx={xx} cy={m.t} r="4" className={grave ? "fill-error" : "fill-verde"}><title>{fmt(e.fecha_evento)}: {e.subtipo}</title></circle>
            </g>
          );
        })}
        <path d={linea} fill="none" className="stroke-primary" strokeWidth="2" strokeLinejoin="round" />
        {pts.map((p, i) => (
          <g key={p.fecha} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <circle cx={X(p.fecha)} cy={Y(p.posicion)} r="12" fill="transparent" />
            <circle cx={X(p.fecha)} cy={Y(p.posicion)} r={hover === i ? 6 : 4.5} style={{ fill: COLOR_HEX[p.categoria] }} className="stroke-surface-container-lowest" strokeWidth="2" />
          </g>
        ))}
        {(() => { const u = pts[pts.length - 1]; return <text x={X(u.fecha) - 8} y={Y(u.posicion) + (Y(u.posicion) < 30 ? 16 : -8)} textAnchor="end" fontSize="12" fontWeight="600" className="fill-on-surface">N° {u.posicion}</text>; })()}
      </svg>
      {hp && (
        <div className="absolute pointer-events-none bg-on-surface text-background text-[13px] rounded px-2 py-1 shadow"
          style={{ left: `${(X(hp.fecha) / W) * 100}%`, top: `${(Y(hp.posicion) / H) * 100}%`, transform: "translate(-50%, -120%)" }}>
          {fmt(hp.fecha)} · N° {hp.posicion} de {hp.total} · {ETIQUETA[hp.categoria]}{hp.riesgo_vital ? " · contactar hoy" : ""}
        </div>
      )}
      <div className="flex flex-wrap gap-3 text-[13px] text-on-surface-variant mt-1">
        {["alta", "media", "baja"].map((c) => <span key={c} className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: COLOR_HEX[c] }} />Prioridad {ETIQUETA[c].toLowerCase()}</span>)}
        <span className="flex items-center gap-1"><span className="w-3 border-t border-dashed border-error" />Descompensación</span>
        <span className="flex items-center gap-1"><span className="w-3 border-t border-dashed border-verde" />Estabilización</span>
      </div>
    </div>
  );
}

// Achica la foto en el navegador para no superar el límite de la Lambda (6 MB) y la devuelve en base64.
function fotoABase64(archivo, lado = 1600) {
  return new Promise((ok, mal) => {
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, lado / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      ok(c.toDataURL("image/jpeg", 0.85).split(",")[1]);
    };
    img.onerror = () => mal(new Error("No se pudo abrir la imagen"));
    img.src = URL.createObjectURL(archivo);
  });
}

// Cámara en vivo dentro de la app: vista previa + botón para tomar la foto.
function Camara({ onFoto, onCerrar }) {
  const video = useRef(null);
  const archivo = useRef(null);
  const [error, setError] = useState(null);
  const [listo, setListo] = useState(false);
  useEffect(() => {
    let stream;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } }, audio: false });
        video.current.srcObject = stream;
        await video.current.play();
        setListo(true);
      } catch (e) {
        setError(e.name === "NotAllowedError" ? "No se dio permiso para usar la cámara." : "No se encontró una cámara disponible.");
      }
    })();
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);
  const tomar = () => {
    const v = video.current, lado = 1600, k = Math.min(1, lado / Math.max(v.videoWidth, v.videoHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(v.videoWidth * k); c.height = Math.round(v.videoHeight * k);
    c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    onFoto(c.toDataURL("image/jpeg", 0.85).split(",")[1]);
  };
  const subir = async (e) => { const f = e.target.files?.[0]; if (f) onFoto(await fotoABase64(f)); };
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onCerrar}>
      <div className="bg-surface-container-lowest rounded max-w-2xl w-full" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-2.5 border-b border-outline-variant flex justify-between items-center">
          <h2 className="font-semibold">Fotografiar documento</h2>
          <button onClick={onCerrar} className="text-on-surface-variant"><Icono n="close" /></button>
        </div>
        <div className="p-4">
          {error ? <p className="text-on-surface-variant mb-3">{error} Puede subir una imagen en su lugar.</p> : (
            <div className="relative bg-black rounded overflow-hidden">
              <video ref={video} playsInline muted className="w-full max-h-[60vh] object-contain" />
              <div className="absolute inset-6 border-2 border-white/70 border-dashed rounded pointer-events-none" />
              {!listo && <p className="absolute inset-0 flex items-center justify-center text-white">Abriendo cámara…</p>}
            </div>
          )}
          <p className="text-[14px] text-on-surface-variant mt-2">Encuadre el documento completo dentro del recuadro, con buena luz.</p>
          <div className="flex gap-2 mt-3">
            {!error && <button disabled={!listo} onClick={tomar} className="flex-1 py-2.5 rounded bg-primary text-on-primary font-semibold flex items-center justify-center gap-1 disabled:opacity-40"><Icono n="photo_camera" />Tomar foto</button>}
            <button onClick={() => archivo.current.click()} className="flex-1 py-2.5 rounded border border-outline-variant font-semibold">Subir imagen</button>
            <input ref={archivo} type="file" accept="image/*" hidden onChange={subir} />
          </div>
        </div>
      </div>
    </div>
  );
}

function Informe({ p, fecha, cargando, onConfirmar, onAviso }) {
  const [texto, setTexto] = useState("");
  const [res, setRes] = useState(null);
  const [leyendo, setLeyendo] = useState(false);
  const [camara, setCamara] = useState(false);
  const analizar = async (body) => {
    setLeyendo(true); setRes(null);
    try { setRes(await api.postInforme(p.id_paciente, { ...body, fecha_corte: fecha })); }
    catch (e) { onAviso({ titulo: "No se pudo leer el informe: " + e.message }); }
    finally { setLeyendo(false); }
  };
  const foto = (b64) => { setCamara(false); analizar({ imagen_base64: b64, media_type: "image/jpeg" }); };
  const ev = res?.evento;
  return (
    <Caja titulo="Registrar informe recibido">
      <p className="text-[14px] text-on-surface-variant mb-2">Epicrisis, DAU de urgencia o nota clínica. Se propone el evento y usted confirma antes de actualizar la lista.</p>
      <textarea rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Ej.: Consulta en urgencia por dolor torácico en reposo. Se hospitaliza en cardiología."
        className="w-full p-2 border border-outline-variant rounded focus:outline-none focus:border-primary resize-y text-[14px]" />
      <div className="flex gap-2 mt-2">
        <button disabled={!texto.trim() || leyendo} onClick={() => analizar({ texto })} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{leyendo ? "Leyendo…" : "Revisar informe"}</button>
        <button disabled={leyendo} onClick={() => setCamara(true)} className="flex-1 py-2 rounded border border-outline-variant font-semibold flex items-center justify-center gap-1"><Icono n="photo_camera" className="text-[18px]" />Foto del documento</button>
      </div>
      {camara && <Camara onFoto={foto} onCerrar={() => setCamara(false)} />}
      {leyendo && <p className="mt-2 text-[14px] text-on-surface-variant flex items-center gap-1"><Icono n="hourglass_top" className="text-[16px] animate-spin" />Leyendo el documento…</p>}
      {res && !ev && <p className="mt-2 text-[14px] text-on-surface-variant">{res.mensaje}</p>}
      {res?.transcripcion && <details className="mt-2 text-[14px]"><summary className="cursor-pointer text-on-surface-variant">Texto leído del documento</summary><p className="whitespace-pre-wrap mt-1">{res.transcripcion}</p></details>}
      {ev && (
        <div className="mt-3 border border-outline-variant rounded p-3 space-y-2 text-[14px]">
          <div><span className="text-on-surface-variant">Evento:</span> <b>{TIPO_EVENTO[ev.tipo_evento]}</b> · {ev.subtipo} · {fmt(ev.fecha_evento)}</div>
          <blockquote className="border-l-4 border-ambar bg-ambar-container/40 px-2 py-1 italic">“{ev.evidencia}”</blockquote>
          <div className="flex items-center gap-2"><span className="text-on-surface-variant">Prioridad:</span><Prioridad cat={res.categoria_actual} /><span>→</span><Prioridad cat={res.categoria_propuesta} /></div>
          {res.razones_propuestas?.map((r, i) => <div key={i} className="text-[14px] text-on-surface-variant">{r.valor} · {r.fuente}</div>)}
          <div className="flex gap-2 pt-1">
            <button disabled={cargando} onClick={async () => { await onConfirmar({ ...ev, detalle: `Informe: ${ev.evidencia}` }); setRes(null); setTexto(""); }}
              className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-50">Confirmar y actualizar lista</button>
            <button onClick={() => setRes(null)} className="flex-1 py-2 rounded border border-outline-variant font-semibold">Descartar</button>
          </div>
          <p className="text-[13px] text-on-surface-variant">Lectura {res.fuente === "bedrock" ? "automática (Amazon Bedrock)" : "por palabras clave"}; verifique antes de confirmar.</p>
        </div>
      )}
    </Caja>
  );
}

// Novedades que registra el equipo: comorbilidad (pondera en Charlson/LACE), cambio de diagnóstico y egresos.
function Novedad({ p, fecha, onListo, onAviso }) {
  const [tipo, setTipo] = useState(null);
  const [cat, setCat] = useState(null);
  const [v, setV] = useState({ condicion: "", cie10: "", fecha });
  const [confirma, setConfirma] = useState(false);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => { if (tipo && !cat) api.getCatalogo().then(setCat).catch((e) => onAviso({ titulo: e.message })); }, [tipo]); // eslint-disable-line react-hooks/exhaustive-deps
  const abrir = (t) => { setTipo(tipo === t ? null : t); setV({ condicion: "", cie10: "", fecha }); setConfirma(false); };
  const enviar = async () => {
    setEnviando(true);
    try {
      const body = { tipo, fecha_corte: fecha, fecha: v.fecha };
      if (tipo === "comorbilidad") Object.assign(body, v.condicion.startsWith("cie:") ? { cie10: v.condicion.slice(4) } : { condicion: v.condicion });
      if (tipo === "diagnostico") body.cie10 = v.cie10;
      if (tipo === "riesgo") Object.assign(body, { grupo_proteccion: (v.grupo ?? p.grupo_proteccion) || null, acg: (v.acg ?? p.acg) || null });
      const r = await api.postNovedad(p.id_paciente, body);
      setTipo(null); onListo(r);
    } catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(false); }
  };
  const peso = cat?.charlson.find((c) => c.condicion === v.condicion)?.peso;
  const campo = "h-11 px-2 border border-outline-variant rounded bg-surface-container-lowest w-full";
  const btn = (t, icono, texto, rojo) => (
    <button onClick={() => abrir(t)} className={`flex-1 min-w-[120px] py-2 rounded border font-semibold text-[14px] flex items-center justify-center gap-1 ${tipo === t ? (rojo ? "bg-error text-on-error border-error" : "bg-primary text-on-primary border-primary") : "border-outline-variant hover:bg-surface-container-low"}`}>
      <Icono n={icono} className="text-[18px]" />{texto}
    </button>
  );
  return (
    <Caja titulo="Registrar novedad del paciente">
      {p.comorbilidades?.length > 0 && <p className="text-[14px] mb-2">Comorbilidades registradas: {p.comorbilidades.map((c) => c.nombre).join(", ")}</p>}
      <div className="flex flex-wrap gap-2">
        {btn("comorbilidad", "add_circle", "Condición / comorbilidad")}
        {btn("diagnostico", "edit_note", "Cambiar diagnóstico")}
        {btn("riesgo", "shield_person", "Grupo protección / ACG")}
        {btn("atendido", "how_to_reg", "Atendido")}
        {btn("fallecimiento", "heart_minus", "Fallecimiento", true)}
      </div>

      {tipo === "comorbilidad" && (
        <div className="mt-3 space-y-2 text-[14px]">
          <select value={v.condicion} onChange={(e) => setV({ ...v, condicion: e.target.value })} className={campo}>
            <option value="">Seleccione la condición…</option>
            <optgroup label="Condiciones de Charlson (suman al LACE)">
              {cat?.charlson.map((c) => <option key={c.condicion} value={c.condicion}>{c.condicion} · peso {c.peso}</option>)}
            </optgroup>
            <optgroup label="Otros diagnósticos (se registran, no suman en Charlson)">
              {cat?.diagnosticos.filter((d) => !["I50", "J44", "J45", "K70", "E11"].includes(d.diagnostico_cie10)).map((d) =>
                <option key={d.diagnostico_cie10} value={`cie:${d.diagnostico_cie10}`}>{d.diagnostico_cie10} · {d.diagnostico_texto}</option>)}
            </optgroup>
          </select>
          {v.condicion && <p className={`text-[14px] ${peso ? "text-primary-container font-semibold" : "text-on-surface-variant"}`}>
            {peso ? `Suma ${peso} al índice de Charlson (van Walraven 2010). El puntaje LACE se recalcula.` : "Queda registrada en la ficha; no tiene peso en el índice de Charlson, no cambia el puntaje."}</p>}
          <button disabled={!v.condicion || enviando} onClick={enviar} className="w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Registrar y recalcular</button>
        </div>
      )}

      {tipo === "diagnostico" && (
        <div className="mt-3 space-y-2 text-[14px]">
          <select value={v.cie10} onChange={(e) => setV({ ...v, cie10: e.target.value })} className={campo}>
            <option value="">Nuevo diagnóstico de la interconsulta…</option>
            {cat?.diagnosticos.map((d) => <option key={d.diagnostico_cie10} value={d.diagnostico_cie10}>{d.especialidad} · {d.diagnostico_cie10} {d.diagnostico_texto}</option>)}
          </select>
          <p className="text-[14px] text-on-surface-variant">Se vuelve a aplicar la tabla del HLF, el puntaje LACE y la garantía GES del nuevo diagnóstico. Si cambia la especialidad, el paciente pasa a esa lista.</p>
          <button disabled={!v.cie10 || enviando} onClick={enviar} className="w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Cambiar y recalcular</button>
        </div>
      )}

      {tipo === "riesgo" && (
        <div className="mt-3 space-y-2 text-[14px]">
          <Filtro label="Grupo de especial protección (MINSAL, criterio 2 de orden)">
            <select value={v.grupo ?? p.grupo_proteccion ?? ""} onChange={(e) => setV({ ...v, grupo: e.target.value })} className={campo}>
              <option value="">Ninguno</option>{cat?.grupos_proteccion.map((g) => <option key={g}>{g}</option>)}
            </select>
          </Filtro>
          <Filtro label="Estratificación de riesgo ACG (ficha Rayen)">
            <select value={v.acg ?? p.acg ?? ""} onChange={(e) => setV({ ...v, acg: e.target.value })} className={campo}>
              <option value="">Sin dato</option>{cat?.acg.map((a) => <option key={a.nivel} value={a.nivel}>{a.nivel} · {a.texto}</option>)}
            </select>
          </Filtro>
          <p className="text-[14px] text-on-surface-variant">El grupo de protección ordena dentro de la misma prioridad (MINSAL Ord. 536/2025). El ACG se muestra como dato de riesgo del SSMSO.</p>
          <button disabled={enviando} onClick={enviar} className="w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Guardar y recalcular</button>
        </div>
      )}

      {(tipo === "fallecimiento" || tipo === "atendido") && (
        <div className="mt-3 space-y-2 text-[14px]">
          <Filtro label={tipo === "fallecimiento" ? "Fecha de defunción" : "Fecha de la consulta nueva de especialidad"}>
            <input type="date" value={v.fecha} max={fecha} onChange={(e) => setV({ ...v, fecha: e.target.value })} className={campo} />
          </Filtro>
          <p className="text-[14px] text-on-surface-variant">{tipo === "fallecimiento"
            ? "Egreso por causal 9 (fallecimiento, Manual SSMSO). El paciente sale de la lista y no recibe nuevas citaciones."
            : "La lista se resuelve cuando el especialista atiende la consulta nueva (CNE). El paciente sale de la lista."}</p>
          <label className="flex items-center gap-2 text-[14px]"><input type="checkbox" checked={confirma} onChange={(e) => setConfirma(e.target.checked)} />
            Confirmo que {p.nombre_fantasia} {tipo === "fallecimiento" ? "falleció" : "fue atendido(a)"} (verificado en {tipo === "fallecimiento" ? "Registro Civil / ficha" : "la ficha clínica"}).</label>
          <button disabled={!confirma || !v.fecha || enviando} onClick={enviar} className={`w-full py-2 rounded font-semibold disabled:opacity-40 ${tipo === "fallecimiento" ? "bg-error text-on-error" : "bg-primary text-on-primary"}`}>
            {tipo === "fallecimiento" ? "Registrar fallecimiento y egresar" : "Registrar atención y egresar"}</button>
        </div>
      )}
    </Caja>
  );
}


// Capa dinámica: señal para el especialista. No cambia la categoría ni el orden MINSAL.
function Criticidad({ p }) {
  const c = p.criticidad_detalle || {};
  const razon = p.razones.find((r) => r.factor === "criticidad");
  const barra = (t, v, tono) => (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-[14px]"><span>{t}</span><b>{Math.round((v || 0) * 100)}</b></div>
      <div className="h-2.5 bg-surface-container-high"><div className={`h-full ${tono}`} style={{ width: `${Math.round((v || 0) * 100)}%` }} /></div>
    </div>
  );
  return (
    <Caja titulo="Criticidad dinámica (señal)" accion={<span className="text-[22px] font-bold">{p.criticidad}<span className="text-[14px] font-normal text-on-surface-variant">/100</span></span>}>
      {p.senal_temprana && <p className="mb-3 p-2.5 bg-ambar-container text-ambar text-[14px] font-semibold">Mediciones empeorando: revisar antes de que llegue el evento.</p>}
      <div className="flex flex-col gap-2.5">
        {barra("Eventos recientes (pesan la mitad a los 60 días)", c.eventos, "bg-error")}
        {barra("Mediciones alteradas o empeorando (90–180 días)", c.mediciones, "bg-ambar")}
        {c.mejora > 0 && barra("Mejora (resta)", c.mejora, "bg-verde")}
      </div>
      {razon && <p className="text-[14px] mt-3">{razon.valor.split("· ").slice(1).join("· ")}</p>}
      <p className="text-[13px] text-on-surface-variant mt-2">No cambia la prioridad ni el orden: pide revisión del especialista. En el registro, 55 % de los pacientes con mediciones empeorando tuvo un deterioro en los 60 días siguientes (vs 16 % del resto).</p>
    </Caja>
  );
}
