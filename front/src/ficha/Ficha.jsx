import { useEffect, useState } from "react";
import * as api from "../api";
import { Caja, Icono, Prioridad } from "../componentes/comunes";
import { ESTILO_GESTION, ETIQUETA, FACTOR, TIPO_EVENTO } from "../constantes";
import { AjusteManual, Contacto, DecisionClinica, GestionCaso, Novedad } from "./Acciones";
import { EvolucionPaciente } from "./Evolucion";
import { Informe } from "./Informe";
import { fmt, fmtHace, hace } from "../util";

const EVENTOS = {
  urgencia: { label: "Consulta en urgencia (ESI 2)", tipo_evento: "visita_urgencia", subtipo: "triage ESI 2", severidad: "grave" },
  hospitalizacion: { label: "Hospitalización", tipo_evento: "hospitalizacion", subtipo: "ingreso hospitalario", severidad: "grave" },
  examen: { label: "Examen alterado", tipo_evento: "examen_alterado", subtipo: "resultado alterado", severidad: "moderada" },
  mejora: { label: "Buena respuesta en APS", tipo_evento: "control_aps", subtipo: "buena respuesta", severidad: "leve" },
  leve: { label: "Urgencia leve (ESI 4-5): dolor de dedo", tipo_evento: "visita_urgencia", subtipo: "triage ESI 4-5", severidad: "leve",
    motivo_clinico: "dolor de dedo tras golpe", relacionado: false },
  ajena: { label: "Hospitalización sin relación: amputación traumática", tipo_evento: "hospitalizacion", subtipo: "ingreso hospitalario", severidad: "grave",
    motivo_clinico: "amputación traumática de pierna (accidente)", relacionado: false },
};

export function Ficha({ p, total, detalle, fecha, demo, esp, onCambio, onAviso, onDestacar, onVer }) {
  const [resumen, setResumen] = useState(null);
  const [cargando, setCargando] = useState(null);
  const [ajuste, setAjuste] = useState(null);
  const [tipoEv, setTipoEv] = useState("hospitalizacion");
  const [resultado, setResultado] = useState(null);  // qué pasó con el último evento registrado desde la ficha
  useEffect(() => { setResumen(null); }, [p.categoria, p.estado_clinico, fecha]);

  const correr = async (nombre, fn) => {
    setCargando(nombre);
    try { await fn(); return true; } catch (e) { onAviso({ titulo: "No se pudo completar: " + e.message }); return false; } finally { setCargando(null); }
  };
  const registrarEvento = (ev, origen) => correr("evento", async () => {
    const r = await api.postEvento({ id_paciente: p.id_paciente, fecha_corte: fecha, fecha_evento: ev.fecha_evento || fecha,
      ...(esp && esp !== "Todas" ? { especialidad: esp } : {}),
      tipo_evento: ev.tipo_evento, subtipo: ev.subtipo, severidad: ev.severidad, detalle: ev.detalle,
      ...(ev.motivo_clinico ? { motivo: ev.motivo_clinico } : {}), ...(ev.relacionado != null ? { relacionado: ev.relacionado } : {}) });
    await onCambio(); onDestacar(p.id_paciente);
    setResultado({ origen, evento: ev.label || `${TIPO_EVENTO[ev.tipo_evento] || ev.tipo_evento}: ${ev.subtipo}`, antes: r.posicion_antes, despues: r.posicion_despues,
      catAntes: p.categoria, paciente: r.paciente });
    onAviso({ titulo: `${origen}. Lista actualizada`, antes: r.posicion_antes, despues: r.posicion_despues, cat: r.paciente?.categoria });
  });
  const [tab, setTab] = useState("resumen");
  const sinNombre = () => !api.getUsuario() && (onAviso({ titulo: "Escriba su nombre y cargo arriba a la derecha: la revisión queda a su nombre" }), true);
  const confirmar = () => !sinNombre() && correr("rev", async () => { await api.postRevision(p.id_paciente, { accion: "confirmar", fecha_corte: fecha }); await onCambio(); onAviso({ titulo: "Prioridad confirmada" }); });
  const guardarAjuste = () => !sinNombre() && correr("rev", async () => {
    await api.postRevision(p.id_paciente, { accion: "ajustar", categoria_ajustada: ajuste.categoria, motivo: ajuste.motivo, fecha_corte: fecha });
    setAjuste(null); await onCambio(); onAviso({ titulo: "Cambio de prioridad registrado" });
  });
  const pedirResumen = () => correr("ia", async () => setResumen(await api.postExplicar(p.id_paciente, fecha)));

  // avisos que piden mirar algo; "prioridad ajustada por tabla HLF" no es aviso: es el motivo por el que ya subió (ver Fundamento)
  const avisos = [...new Set((p.revision_sugerida || []).map((s) => s.motivo).filter((m) => !m.includes("prioridad ajustada")))];
  const timeline = detalle ? [
    ...detalle.eventos_clinicos.map((e) => ({ f: e.fecha_evento, t: `${TIPO_EVENTO[e.tipo_evento] || e.tipo_evento}: ${e.subtipo}`, d: [e.detalle?.startsWith("Informe") ? e.detalle : null, e.fecha_en_documento === false ? "el documento no decía la fecha: se registró con la del día en que se leyó" : null].filter(Boolean).join(" · ") || null, rojo: e.severidad === "grave", nuevo: e.id_evento?.startsWith("EV-DEMO") })),
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
            <div className="text-[13px] text-on-surface-variant">{p.rut ? `RUT ${p.rut} · ` : ""}{p.edad} años · {p.sexo === "F" ? "Femenino" : "Masculino"} · {p.comuna} · {p.id_paciente}</div>
          </div>
          <Prioridad cat={p.categoria} />
        </div>
        {p.urgencia_hoy && <div className="mt-3 p-2.5 rounded bg-error text-on-error text-[14px] flex gap-2"><Icono n="emergency" className="text-[20px]" /><span>
          <b>Derivar hoy a urgencia.</b> {p.razones.find((r) => r.factor === "urgencia")?.valor}. No corresponde esperar una cita electiva.</span></div>}
        {p.urgencia_cerrada && <div className="mt-3 p-2.5 rounded bg-hlf-claro text-hlf text-[14px] flex gap-2"><Icono n="task_alt" className="text-[20px]" /><span>
          <b>Urgencia revisada</b>{p.urgencia_cerrada.responsable && ` por ${p.urgencia_cerrada.responsable}`}: sale del carril de urgencia y sigue en prioridad alta.</span></div>}
        {p.contactar_hoy && p.riesgo_vital && <div className="mt-3 p-2.5 rounded bg-error-container text-on-error-container text-[14px] flex gap-2"><Icono n="call" className="text-[20px]" /><span>
          <b>Descompensación grave: contactar al paciente.</b> Evento del {fmtHace(p.evaluacion?.fecha_evento, fecha)}, en el sistema desde el {fmt(p.evaluacion?.llego_al_sistema)}.
          {" "}La prioridad ya se actualizó; el especialista puede cambiarla si corresponde.</span></div>}
        {p.riesgo_vital && !p.contactar_hoy && p.evaluacion?.cierre && <div className="mt-3 p-2.5 rounded bg-hlf-claro text-hlf text-[14px] flex gap-2"><Icono n="task_alt" className="text-[20px]" /><span>
          <b>Prioridad revisada: {p.evaluacion.cierre.texto}</b>{p.evaluacion.cierre.responsable && ` · ${p.evaluacion.cierre.responsable}`}{p.decision?.seguimiento && ` · seguimiento ${fmt(p.decision.seguimiento)}`}</span></div>}
        {p.estado_revision === "requiere_revision" && <div className="mt-2 p-2.5 rounded bg-ambar-container text-ambar text-[14px] flex gap-2"><Icono n="rate_review" className="text-[20px]" /><span><b>Hay información nueva desde la última revisión:</b> {p.revision_vencida_por}. El especialista ve si mantiene su decisión.</span></div>}
        {p.estado_revision === "pendiente" && avisos.length > 0 && <div className="mt-2 p-2.5 rounded bg-ambar-container/60 text-ambar text-[14px] flex gap-2"><Icono n="rate_review" className="text-[20px]" /><span><b>Aviso para el especialista:</b> {avisos.join(" · ")}</span></div>}
        <dl className="mt-3 grid grid-cols-[130px_1fr] gap-y-1 text-[14px]">
          <dt className="text-on-surface-variant">Especialidad</dt><dd>{p.especialidad}</dd>
          <dt className="text-on-surface-variant">Diagnóstico</dt><dd>{p.diagnostico_cie10} · {p.diagnostico_texto}</dd>
          <dt className="text-on-surface-variant">Ingreso a lista</dt><dd>{fmt(p.fecha_ingreso_lista)} ({p.dias_espera} días)</dd>
          <dt className="text-on-surface-variant">Prioridad inicial</dt><dd className="capitalize">{p.prioridad_inicial}</dd>
          <dt className="text-on-surface-variant">N° en la lista</dt><dd>{p.posicion} de {total} {esp && esp !== "Todas" ? `en ${esp}` : "(todas las especialidades)"}</dd>
          <dt className="text-on-surface-variant">Prioridad</dt><dd><EstadoRevision p={p} /></dd>
          {p.gestion && <><dt className="text-on-surface-variant">Gestión</dt><dd><b className={ESTILO_GESTION[p.gestion.estado]}>{p.gestion.texto}</b>{p.gestion.motivo_texto && ` · ${p.gestion.motivo_texto}`}</dd>
            <dt className="text-on-surface-variant">Próxima acción</dt><dd>{p.gestion.proxima_accion}{p.gestion.seguimiento && <span className={p.gestion.seguimiento_vencido ? "text-error font-semibold" : ""}> · seguimiento {fmt(p.gestion.seguimiento)}{p.gestion.seguimiento_vencido && " (vencido)"}</span>}</dd>
            <dt className="text-on-surface-variant">Responsable</dt><dd className={p.gestion.responsable ? "" : "text-ambar"}>{p.gestion.responsable || "Sin responsable asignado"}</dd></>}
          {(p.grupo_proteccion || p.acg) && <><dt className="text-on-surface-variant">Riesgo social</dt><dd>{[p.grupo_proteccion && `Grupo ${p.grupo_proteccion}`, p.acg && `ACG ${p.acg}`].filter(Boolean).join(" · ")}</dd></>}
          {p.comorbilidades?.length > 0 && <><dt className="text-on-surface-variant">Comorbilidades</dt><dd>{p.comorbilidades.map((c) => c.nombre).join(", ")}</dd></>}
        </dl>
        {p.categoria !== p.categoria_sistema && <p className="mt-2 text-[13px] text-on-surface-variant">El sistema proponía prioridad {p.categoria_sistema}; el equipo clínico la cambió a {p.categoria}. Motivo: {p.revision?.motivo}</p>}
      </Caja>

      <div className="shrink-0 flex border-b border-outline-variant bg-surface-container-lowest rounded-t text-[14px] sticky top-0 z-10 overflow-x-auto" role="tablist">
        {[["resumen", "Resumen"], ["gestion", "Gestión"], ["registrar", "Registrar"], ["puntaje", "Fundamento"], ["historia", "Historia"]].map(([k, t]) => (
          <button key={k} onClick={() => setTab(k)} className={`flex-1 py-2 border-b-2 -mb-px ${tab === k ? "border-primary text-primary font-semibold" : "border-transparent text-on-surface-variant"}`}>{t}</button>
        ))}
      </div>

      {tab === "resumen" && <>
      <Caja titulo={`Por qué está en el N° ${p.posicion} y cómo se ha movido`}>
        <EvolucionPaciente p={p} fecha={fecha} esp={esp && esp !== "Todas" ? esp : null} />
      </Caja>
      {p.comparacion && (p.comparacion.arriba || p.comparacion.abajo) && <Caja titulo="Comparado con sus vecinos en la lista">
        <Vecino v={p.comparacion.arriba} arriba onVer={onVer} />
        <Vecino v={p.comparacion.abajo} onVer={onVer} />
        <p className="text-[12px] text-on-surface-variant mt-2">Se comparan con los criterios del orden de la lista, en este orden: prioridad, urgencia «derivar hoy»,
          descompensación grave, mortalidad, gravedad del evento, descompensado o estable; recién después grupo de protección y tiempo de espera (Ord. MINSAL 536/2025).</p>
      </Caja>}
      </>}

      {tab === "gestion" && <>
        <GestionCaso p={p} fecha={fecha} onListo={async () => { await onCambio(); onDestacar(p.id_paciente); onAviso({ titulo: `${p.nombre_fantasia}: gestión actualizada` }); }} onAviso={onAviso} />
        {p.riesgo_vital && <DecisionClinica p={p} fecha={fecha} onListo={async (r) => { await onCambio(); onAviso({ titulo: `${p.nombre_fantasia}: ${r.decision.texto} (${r.decision.responsable})` }); }} onAviso={onAviso} />}
        <Contacto p={p} fecha={fecha} onListo={async (r) => { await onCambio(); onAviso({ titulo: `${p.nombre_fantasia}: ${r.contacto.texto}` }); }} onAviso={onAviso} />
        <AjusteManual p={p} fecha={fecha} onListo={async (r, quitar) => {
          await onCambio(); onDestacar(p.id_paciente);
          onAviso(quitar ? { titulo: `${p.nombre_fantasia}: ajuste manual deshecho, vuelve al orden del sistema` }
            : { titulo: `${p.nombre_fantasia} movido a mano`, antes: r.ajuste.posicion_anterior, despues: r.paciente?.posicion_especialidad });
        }} onAviso={onAviso} />
      </>}

      {tab === "puntaje" && <>
      {p.algoritmo && <Caja titulo="Cómo se calculó esta prioridad">
        {p.algoritmo === "rubrica" && p.rubrica ? <div className="text-[14px] space-y-1.5">
          <p><b>Algoritmo con rúbrica:</b> un modelo de IA (Amazon Bedrock) leyó el historial {p.rubrica.categorias_corridas?.length || 3} veces y
            respondió preguntas cerradas con citas; una fórmula fija con la tabla del HLF calculó la prioridad. La IA no decide.</p>
          <p className="text-[13px] text-on-surface-variant">Reglas: {p.rubrica.categoria_reglas} · rúbrica: {p.rubrica.categoria_rubrica ?? "—"} ·
            lecturas: {(p.rubrica.categorias_corridas || []).map((c) => c || "falló").join(" / ")} · {p.rubrica.modelo} · {p.rubrica.version_kb}</p>
          {p.rubrica.requiere_revision
            ? <div className="rounded bg-ambar-container/60 text-ambar p-2 text-[13px]"><b>Podría bajar de prioridad:</b> {p.controles.filter((m) => m.motivo === "bajaria").map((m) => m.detalle).join(" · ")}. El sistema nunca baja solo: mantiene la prioridad hasta que el especialista decida.</div>
            : p.controles?.length > 0
              ? <div className="rounded bg-surface-container-low text-on-surface-variant p-2 text-[13px]">Esta vez se usaron las reglas (la lectura de la IA no se pudo verificar: {p.controles.map((m) => m.motivo.replaceAll("_", " ")).join(", ")}). No requiere acción.</div>
              : <div className="rounded bg-hlf-claro text-hlf p-2 text-[13px]">Controles OK: citas verificadas en el registro, 3 lecturas iguales, no baja a nadie.</div>}
        </div> : <p className="text-[13px] text-on-surface-variant">Sin evaluación vigente del algoritmo con rúbrica: se usan las reglas actuales.</p>}
      </Caja>}
      <Caja titulo={`Fundamento de la prioridad ${ETIQUETA[p.categoria].toLowerCase()}`}>
        <ul className="space-y-2.5 text-[14px]">
          {p.razones.map((r, i) => (
            <li key={i} className={["tabla_oficial", "riesgo_vital", "urgencia", "combinacion", "criterio_registro", "oncologico"].includes(r.factor) ? "pl-2 border-l-4 border-error" : "pl-2 border-l-4 border-outline-variant"}>
              <div className="text-[12px] text-on-surface-variant">{FACTOR[r.factor] || r.factor}</div>
              <div>{r.valor}</div>
              {r.riesgo && <div className="text-[13px] mt-0.5"><b>Qué puede pasar:</b> {r.riesgo}</div>}
              <div className="text-[12px] text-on-surface-variant italic">Fuente: {r.fuente}</div>
            </li>
          ))}
        </ul>
      </Caja>
      <Caja titulo="Puntaje LACE (experimental, solo desempate)">
        <BoletaLace lace={p.lace} />
      </Caja>
      </>}

      {tab === "resumen" && (
        <>
          <Caja titulo="Revisión de la prioridad (especialista)">
            <p className="text-[13px] text-on-surface-variant mb-2">¿Está de acuerdo con la prioridad {ETIQUETA[p.categoria].toLowerCase()} que propone el sistema? Su respuesta se usa para medir la concordancia (kappa).</p>
            <div className="flex gap-2">
              <button onClick={confirmar} disabled={cargando} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-50">Confirmar prioridad</button>
              <button onClick={() => setAjuste(ajuste ? null : { categoria: p.categoria, motivo: "" })} className="flex-1 py-2 rounded border border-primary text-primary font-semibold">Cambiar prioridad</button>
            </div>
            {ajuste && (
              <div className="mt-3 flex flex-col gap-2">
                <select value={ajuste.categoria} onChange={(e) => setAjuste({ ...ajuste, categoria: e.target.value })} className="h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">
                  {Object.entries(ETIQUETA).map(([k, v]) => <option key={k} value={k}>Prioridad {v.toLowerCase()}</option>)}
                </select>
                <input placeholder="Motivo clínico (obligatorio, mínimo 20 caracteres)" value={ajuste.motivo} onChange={(e) => setAjuste({ ...ajuste, motivo: e.target.value })} className="h-9 px-2 border border-outline-variant rounded" />
                <button disabled={ajuste.motivo.trim().length < 20 || !ajuste.motivo} onClick={guardarAjuste} className="py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Guardar cambio</button>
              </div>
            )}
          </Caja>

          <Caja titulo="Resumen para el equipo" accion={<button onClick={pedirResumen} disabled={cargando} className="text-[13px] text-primary font-semibold disabled:opacity-50">{cargando === "ia" ? "Redactando…" : resumen ? "Actualizar" : "Generar"}</button>}>
            {resumen ? <>
              <p className="text-[14px] leading-relaxed">{resumen.explicacion_ia}</p>
              <p className="text-[12px] text-on-surface-variant mt-2">Texto redactado automáticamente a partir del fundamento ({resumen.fuente === "bedrock" ? "Amazon Bedrock" : "plantilla"}). No modifica la prioridad.</p>
            </> : <p className="text-[13px] text-on-surface-variant">Redacta en lenguaje simple el fundamento, por ejemplo para contactar al paciente.</p>}
          </Caja>
        </>
      )}

      {tab === "registrar" && (
        <>
          {demo && (
            <Caja titulo="Simular evento (demostración)" className="border-ambar/50">
              <div className="flex flex-wrap gap-2">
                <select value={tipoEv} onChange={(e) => setTipoEv(e.target.value)} className="flex-1 min-w-0 h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">
                  {Object.entries(EVENTOS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
                <button onClick={() => registrarEvento(EVENTOS[tipoEv], "Evento simulado")} disabled={cargando} className="shrink-0 h-9 px-4 rounded bg-ambar text-background font-semibold disabled:opacity-50">Simular</button>
              </div>
            </Caja>
          )}
          {resultado && <ResultadoEvento r={resultado} onVer={onVer} onCerrar={() => setResultado(null)} />}
          {!demo && <p className="text-[12px] text-on-surface-variant">Para simular un evento en una demostración, marque «Explorar fechas anteriores» arriba a la derecha.</p>}
          <Informe p={p} fecha={fecha} cargando={cargando} onConfirmar={(ev) => registrarEvento(ev, "Evento del informe registrado")} onAviso={onAviso}
            onRegistrado={async (r) => { await onCambio(); onDestacar(p.id_paciente);
              onAviso({ titulo: `La IA leyó el informe y registró: ${r.registrados.map((e) => e.subtipo).join(", ")}. Lista actualizada`, antes: r.posicion_antes, despues: r.posicion_despues, cat: r.paciente?.categoria }); }} />

          <Novedad p={p} fecha={fecha} onListo={async (r) => {
            await onCambio();
            onAviso(r.en_lista ? { titulo: `Registrado: ${r.mensaje}`, despues: r.paciente?.posicion, antes: p.posicion, cat: r.paciente?.categoria }
              : { titulo: `${p.nombre_fantasia}: ${r.mensaje}` });
          }} onAviso={onAviso} />

        </>
      )}

      {tab === "historia" && <Caja titulo="Historia mientras espera">
        <ol className="text-[14px]">
          {timeline.map((x, i) => (
            <li key={i} className={`grid grid-cols-[96px_1fr] gap-2 py-1.5 border-b border-outline-variant/50 ${x.nuevo ? "bg-ambar-container/50" : ""}`}>
              <span className="text-on-surface-variant text-[13px] leading-tight">{fmt(x.f)}<br /><span className="text-[11px]">{hace(x.f, fecha)}</span></span>
              <span className={x.rojo ? "text-error font-semibold" : x.ambar ? "text-ambar" : ""}>{x.t}{x.d && <span className="text-on-surface-variant font-normal"> · {x.d}</span>}</span>
            </li>
          ))}
          {!detalle && [0, 1, 2, 3, 4].map((i) => <li key={i} className="h-8 my-1.5 rounded bg-surface-container-high/50 animate-pulse" aria-hidden="true" />)}
        </ol>
      </Caja>}
    </>
  );
}

// Qué pasó con el evento recién registrado: puesto y prioridad antes/después, la regla que lo explica y sus nuevos vecinos.
const FACTORES_CAMBIO = ["urgencia", "combinacion", "criterio_registro", "oncologico", "riesgo_vital", "tabla_oficial"];
function ResultadoEvento({ r, onVer, onCerrar }) {
  const p = r.paciente;
  if (!p) return null;
  const subio = r.despues < r.antes, cambioCat = p.categoria !== r.catAntes;
  const ev = p.razones.find((x) => x.factor === "evento");
  const reglas = p.razones.filter((x) => FACTORES_CAMBIO.includes(x.factor));
  return (
    <Caja titulo={`Resultado: ${r.evento}`} className={subio ? "border-error/50" : "border-outline-variant"}
      accion={<button onClick={onCerrar} className="text-[13px] text-on-surface-variant">Cerrar</button>}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[15px]">
        <span>Puesto: N° {r.antes} → <b className={subio ? "text-error" : ""}>N° {r.despues}</b>
          {subio ? <span className="text-error text-[13px] font-semibold"> (subió {r.antes - r.despues})</span> : r.despues === r.antes ? <span className="text-on-surface-variant text-[13px]"> (se mantiene)</span> : null}</span>
        <span className="flex items-center gap-1">Prioridad: <Prioridad cat={r.catAntes} />{cambioCat && <>→<Prioridad cat={p.categoria} /></>}</span>
      </div>
      <div className="mt-2 text-[14px]"><b>Por qué:</b>
        {ev && <p className="text-[13px] text-on-surface-variant">Evento registrado: {ev.valor}</p>}
        <ul className="mt-1 space-y-1.5">
          {reglas.map((x, i) => (
            <li key={i} className="pl-2 border-l-4 border-error/60 text-[13px]">{x.valor}
              {x.riesgo && <div className="text-on-surface-variant">Riesgo: {x.riesgo}</div>}
              <div className="text-[12px] text-on-surface-variant">Fuente: {x.fuente}</div></li>
          ))}
          {reglas.length === 0 && <li className="text-[13px]">Ninguna regla oficial cambia su prioridad con este evento{ev?.valor?.includes("sin relación") ? " (no tiene relación con su diagnóstico)" : ""}
            {subio ? ". Dentro de la misma prioridad avanza porque ahora está descompensado y se ordena por la gravedad del evento (ver vecinos)." : ": se mantiene donde estaba."}</li>}
        </ul>
      </div>
      {p.comparacion && <div className="mt-2"><Vecino v={p.comparacion.arriba} arriba onVer={onVer} /><Vecino v={p.comparacion.abajo} onVer={onVer} /></div>}
    </Caja>
  );
}

// Por qué va después del de arriba o antes del de abajo: el primer criterio del orden en que se diferencian.
function Vecino({ v, arriba, onVer }) {
  if (!v) return null;
  const otro = <button onClick={() => onVer?.(v.id_paciente)} className="text-primary font-semibold hover:underline">N° {v.posicion} · {v.nombre_fantasia}</button>;
  const quien = arriba ? <>{otro}</> : "este paciente";
  const despues = arriba ? "este paciente" : <>N° {v.posicion}</>;
  let razon;
  if (!v.este) razon = <>{v.texto[0].toUpperCase() + v.texto.slice(1)}.</>;
  else if (v.clinico) razon = <>Lo de {quien} es más grave por <b>{v.criterio}</b>: <b>{v.este}</b>; {despues}: {v.otro}.</>;
  else razon = <>Misma gravedad clínica (igual prioridad, descompensación y mortalidad). Desempata <b>{v.criterio}</b>: {quien}, {v.este}; {despues}, {v.otro}.</>;
  return (
    <div className="flex gap-2 py-2 border-b border-outline-variant/50 last:border-0 text-[14px]">
      <Icono n={arriba ? "arrow_upward" : "arrow_downward"} className={`text-[20px] ${arriba ? "text-on-surface-variant" : "text-primary"}`} />
      <div>
        <div>{arriba ? "Va después de " : "Va antes de "}{otro} <span className="text-on-surface-variant text-[13px]">({v.diagnostico_texto}, {v.especialidad}, prioridad {v.categoria})</span></div>
        <div className="text-[13px] mt-0.5">{razon}</div>
      </div>
    </div>
  );
}

function EstadoRevision({ p }) {
  if (p.estado_revision === "requiere_revision") return <span className="text-ambar font-semibold">Información nueva desde la revisión</span>;
  if (p.estado_revision === "pendiente") return <span className="text-on-surface-variant">Vigente · {p.categoria_sistema !== p.prioridad_inicial ? "actualizada por el sistema" : "asignada en la SIC"}</span>;
  return <span className="text-verde font-semibold">{p.estado_revision === "ajustado" ? "Ajustada" : "Confirmada"}{p.revision?.usuario && ` · ${p.revision.usuario}`}</span>;
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
                <div className="text-[12px] text-on-surface-variant">{x.valor}</div>
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
      <p className="text-[12px] text-on-surface-variant mt-2">
        <b>Experimental.</b> Puntos según {lace.fuente}. Solo desempata pacientes con la misma prioridad y antigüedad; no es un puntaje validado para listas de espera.
      </p>
      {lace.datos_faltantes?.length > 0 && <p className="text-[12px] text-ambar mt-1">Datos faltantes: {lace.datos_faltantes.join(" · ")}.</p>}
    </div>
  );
}
