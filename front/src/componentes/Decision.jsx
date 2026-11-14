// Piezas compartidas de las "decisiones del sistema" (dictámenes, en el backend): la tarjeta, el detalle de en qué se
// basó, el formulario de veredicto del especialista y lo que aprendió el sistema. Las usan la pantalla Decisiones,
// la pestaña Decisiones de la ficha y la caja "Revisión de la prioridad" del Resumen (un solo formulario).
import { useEffect, useState } from "react";
import * as api from "../api";
import { Icono, Prioridad } from "./comunes";
import { ETIQUETA, FACTOR, TIPO_EVENTO } from "../constantes";
import { usePuede } from "../permisos";
import { fmt } from "../util";

const MIN = 20;
export const fmtHora = (iso) => (iso ? `${fmt(iso)} ${iso.slice(11, 16)}` : "");

export const DISPARADOR = { evento: "Evento clínico", ingreso: "Ingreso a la lista", novedad: "Novedad registrada", informe: "Informe o foto leído",
  importacion: "Carga de archivo", criterio_local: "Criterio local aprobado por jefatura", enmienda: "Corrección de un evento",
  barrido: "Revisión nocturna de la lista", revision_directa: "Revisión directa del especialista" };
export const CANAL = { app: "desde esta aplicación", archivo: "archivo cargado en «Recepción de datos»", api: "sistema del hospital (API)",
  s3: "carpeta de carga automática", informe: "informe o foto" };
const SEVERIDAD = { grave: "grave", moderada: "moderada", leve: "leve" };

// "visita_urgencia · triage ESI 2 (grave)" → "Urgencia · triage ESI 2 (grave)"
export const textoEvento = (s) => String(s || "").replace(/\b([a-z]+_[a-z_]+)\b/g, (k) => TIPO_EVENTO[k] || k.replaceAll("_", " "));

// "I10|visita_urgencia|grave" → "I10 · Urgencia · grave"
export const textoPatron = (p) => {
  if (!p) return "";
  const [cie, tipo, sev] = p.split("|");
  return tipo === "*" ? `${cie} · sin evento determinante` : `${cie} · ${TIPO_EVENTO[tipo] || tipo.replaceAll("_", " ")} · ${SEVERIDAD[sev] || sev}`;
};

// Quién decidió, en palabras simples. La IA nunca "decide" sola: lee, y el sistema decide con criterios con fuente.
export function quienDecidio(d) {
  const ia = d.informacion_utilizada?.ia;
  const simulado = ia?.modelo === "simulado";
  if (d.motor === "ia_rubrica") return { icono: "smart_toy", tono: "azul", simulado,
    texto: simulado ? "Una IA de demostración (simulada, sin Amazon Bedrock) leyó el historial; el sistema decidió con criterios con fuente."
      : `Una IA (Amazon Bedrock${ia?.modelo ? `, ${ia.modelo}` : ""}) leyó el historial ${ia?.lecturas || 3} veces; el sistema decidió con criterios con fuente.` };
  if (d.motor === "reglas_respaldo") return { icono: "rule", tono: "ambar", simulado,
    texto: "La IA no pudo leer el historial o su lectura no pasó los controles: el sistema decidió solo con las reglas con fuente." };
  return { icono: "rule", tono: "gris", simulado, texto: "El sistema decidió con las reglas con fuente (sin IA)." };
}

const TONO = { azul: "text-primary border-primary/30 bg-primary/5", ambar: "text-ambar border-ambar/40 bg-ambar-container/50",
  gris: "text-on-surface-variant border-outline-variant bg-surface-container-low", verde: "text-verde border-verde/40 bg-verde-container/50",
  rojo: "text-error border-error/40 bg-error-container/50" };
export const Etiqueta = ({ children, tono = "gris", title }) =>
  <span title={title} className={`inline-flex items-center gap-1 px-1.5 py-px rounded border text-[12px] ${TONO[tono]}`}>{children}</span>;

export const VEREDICTO_TXT = { adecuada: "Adecuada", incorrecta: "Incorrecta" };

// Estado de revisión de una decisión: pendiente, revisada con su veredicto, o cubierta por una revisión posterior.
export function EstadoDecision({ d, motivos }) {
  const r = d.revision;
  if (r) {
    const m = motivos?.find((x) => x.valor === r.motivo_codigo)?.texto;
    return <Etiqueta tono={r.veredicto === "adecuada" ? "verde" : "ambar"} title={r.motivo || undefined}>
      <Icono n={r.veredicto === "adecuada" ? "thumb_up" : "thumb_down"} className="text-[14px]" />
      {VEREDICTO_TXT[r.veredicto] || r.veredicto}{m ? `: ${m.toLowerCase()}` : ""} · {r.usuario} · {fmt(r.fecha)}</Etiqueta>;
  }
  return d.necesita_revision ? <Etiqueta tono="rojo"><Icono n="pending_actions" className="text-[14px]" />Espera la revisión del especialista</Etiqueta>
    : <Etiqueta>No requiere revisión</Etiqueta>;
}

// Tarjeta de una decisión: se entiende sola (paciente, qué la gatilló, antes → después, explicación, quién decidió).
export function TarjetaDecision({ d, paciente, motivos, fecha, onVer, onRevisado, onAviso, onIrAprendizaje, aprendizaje, mostrarPaciente = true }) {
  const puede = usePuede();
  const [abierto, setAbierto] = useState(false);
  const [aprendido, setAprendido] = useState(aprendizaje || null);
  const res = d.resultado || {}, disp = d.disparador || {};
  const quien = quienDecidio(d);
  const subio = res.cambio === "sube", bajo = res.cambio === "baja";
  return (
    <article className={`bg-surface-container-lowest border border-outline-variant rounded border-l-4 ${d.necesita_revision && !d.revision ? (res.alerta_nueva ? "border-l-error" : "border-l-ambar") : "border-l-outline-variant"}`}>
      <div className="p-3 sm:p-4 flex flex-col gap-2 text-[14px]">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {mostrarPaciente && <button onClick={() => onVer?.(d.id_paciente)} className="text-[16px] font-semibold text-primary hover:underline text-left">
              {paciente?.nombre_fantasia || d.id_paciente}</button>}
            {mostrarPaciente && <div className="text-[13px] text-on-surface-variant">{paciente ? `${paciente.diagnostico_cie10} ${paciente.diagnostico_texto} · ` : ""}{d.especialidad} · {d.id_paciente}</div>}
            <div className="text-[12px] text-on-surface-variant">Decisión del sistema del {fmtHora(d.fecha)} · lista al {fmt(d.fecha_corte)}</div>
          </div>
          <EstadoDecision d={d} motivos={motivos} />
        </div>

        <div className="rounded bg-surface-container-low px-3 py-2">
          <div className="text-[12px] text-on-surface-variant">Qué la gatilló</div>
          <div><b>{DISPARADOR[disp.tipo] || disp.tipo}</b>{disp.descripcion ? `: ${textoEvento(disp.descripcion)}` : ""}</div>
          <div className="text-[12px] text-on-surface-variant">Llegó {CANAL[disp.canal] || disp.canal || "—"}{disp.usuario ? ` · registró ${disp.usuario}` : ""}{disp.id_lote ? ` · lote ${disp.id_lote}` : ""}</div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="flex items-center gap-1.5">Prioridad
            {res.categoria_antes && res.categoria_antes !== res.categoria ? <><Prioridad cat={res.categoria_antes} /><span>→</span></> : null}
            <Prioridad cat={res.categoria} />
            {res.categoria_antes === res.categoria && <span className="text-[13px] text-on-surface-variant">(se mantiene)</span>}</span>
          {res.posicion != null && <span>Puesto {res.posicion_antes != null ? <>N° {res.posicion_antes} → </> : null}<b className={subio ? "text-error" : ""}>N° {res.posicion}</b>
            {res.total ? <span className="text-on-surface-variant text-[13px]"> de {res.total}</span> : null}</span>}
          {res.alerta_nueva && <Etiqueta tono="rojo"><Icono n="emergency" className="text-[14px]" />Abre alerta: evaluar en 72 h</Etiqueta>}
          {res.urgencia_hoy && <Etiqueta tono="rojo">Derivar hoy a urgencia</Etiqueta>}
          {bajo && <Etiqueta tono="ambar">Bajó por una decisión de una persona</Etiqueta>}
        </div>

        {d.explicacion && <p className="leading-relaxed">{d.explicacion}</p>}

        <p className={`text-[13px] flex items-start gap-1.5 ${quien.simulado ? "text-ambar" : "text-on-surface-variant"}`}>
          <Icono n={quien.icono} className="text-[18px]" /><span>{quien.texto}</span></p>

        <button onClick={() => setAbierto(!abierto)} aria-expanded={abierto} className="self-start text-[13px] text-primary font-semibold flex items-center gap-1">
          <Icono n={abierto ? "expand_less" : "expand_more"} className="text-[18px]" />{abierto ? "Ocultar en qué se basó" : "Ver en qué se basó"}</button>
        {abierto && <DetalleDictamen d={d} />}

        {!d.revision && puede("especialista") && !aprendido &&
          <FormVeredicto pid={d.id_paciente} categoria={res.categoria} idDictamen={d.id_dictamen} rev={paciente?.rev} fecha={fecha || d.fecha_corte}
            onAviso={onAviso} onListo={(r) => { setAprendido(r.aprendizaje || {}); onRevisado?.(r); }} onConflicto={() => onRevisado?.(null)} />}
        {!d.revision && !puede("especialista") && <p className="text-[12px] text-on-surface-variant">La revisión la hace un especialista o la jefatura (elija el rol arriba).</p>}
        {aprendido && <Aprendido a={aprendido} pid={d.id_paciente} fecha={fecha || d.fecha_corte} onAviso={onAviso} onCambio={() => onRevisado?.(null)} onIrAprendizaje={onIrAprendizaje} />}
      </div>
    </article>
  );
}

// "Ver en qué se basó": fundamento con fuentes, información utilizada (registros, fuentes y versiones, criterios locales,
// lecturas de la IA y sus controles) y precedentes de casos parecidos.
export function DetalleDictamen({ d }) {
  const iu = d.informacion_utilizada || {};
  const an = iu.antecedentes || {}, co = iu.conocimiento || {}, pr = iu.precedentes, ia = iu.ia;
  const Seccion = ({ t, children }) => <section className="flex flex-col gap-1"><h4 className="text-[13px] font-semibold">{t}</h4>{children}</section>;
  return (
    <div className="rounded border border-outline-variant p-3 flex flex-col gap-3 text-[13px]">
      <Seccion t="Fundamento">
        <ul className="space-y-1.5">
          {(d.fundamento || []).map((r, i) => (
            <li key={i} className={`pl-2 border-l-4 ${r.factor === "criterio_local" ? "border-primary" : r.sin_regla ? "border-outline-variant" : "border-error/50"}`}>
              <span className="text-on-surface-variant">{FACTOR[r.factor] || r.factor}:</span> {r.valor}
              <div className="text-[12px] text-on-surface-variant italic">Fuente: {r.fuente}</div>
            </li>))}
        </ul>
      </Seccion>
      <Seccion t="Información utilizada">
        <p>{an.eventos ?? 0} eventos, {an.mediciones ?? 0} mediciones y {an.comorbilidades ?? 0} comorbilidades del registro
          {an.desde ? ` (del ${fmt(an.desde)} al ${fmt(an.hasta)})` : ""}.</p>
        {an.citados?.length > 0 && <ul className="list-disc pl-5">
          {an.citados.map((c, i) => <li key={i} className={c.anulado ? "line-through text-on-surface-variant" : ""}>
            {fmt(c.fecha)} · {TIPO_EVENTO[c.tipo] || c.tipo}: {c.valor}{c.severidad ? ` (${c.severidad})` : ""}
            {c.rol === "determinante" && <b> · determinó la decisión</b>}{c.anulado && " · anulado"}{c.id_evento && <span className="text-on-surface-variant"> · {c.id_evento}</span>}</li>)}
        </ul>}
      </Seccion>
      <Seccion t={`Fuentes y versiones${co.paquete?.etiqueta ? ` (paquete ${co.paquete.etiqueta})` : ""}`}>
        <ul className="space-y-0.5">
          {(co.fuentes || []).map((f) => <li key={f.id}>{f.titulo} · <b>{f.version || "sin versión (dato del registro)"}</b>
            {f.sha256 && <span className="text-on-surface-variant font-mono text-[11px]"> · {f.sha256.slice(0, 12)}</span>}</li>)}
        </ul>
        {co.criterios_locales?.length > 0 && <p><b>Criterios locales aplicados:</b> {co.criterios_locales.map((c) => `${c.id} v${c.version}`).join(", ")}</p>}
        {co.criterios_propuestos?.length > 0 && <p className="text-ambar"><b>Criterios locales propuestos que le calzan</b> (no cambian nada hasta que jefatura los apruebe): {co.criterios_propuestos.map((c) => `${c.id} v${c.version}`).join(", ")}</p>}
        <p className="text-on-surface-variant">Versión de los criterios locales: {co.capa_local?.version ?? 0}{co.paquete?.huella ? ` · huella del paquete ${co.paquete.huella}` : ""}</p>
      </Seccion>
      {ia && <Seccion t="Lectura de la IA">
        <p>{ia.modelo === "simulado" ? "IA simulada (demostración sin Amazon Bedrock)" : `Modelo ${ia.modelo}`} · {ia.lecturas} lecturas · rúbrica {ia.version_rubrica}
          {ia.tokens_entrada ? ` · ${ia.tokens_entrada} + ${ia.tokens_salida} tokens` : ""}{ia.latencia_s ? ` · ${ia.latencia_s} s` : ""}</p>
        <p>Prioridad con las respuestas de la IA: {ETIQUETA[ia.categoria_rubrica] || "—"} · con las reglas: {ETIQUETA[ia.categoria_reglas] || "—"}
          {ia.respaldo_reglas ? " · rigieron las reglas (respaldo)" : ""}</p>
        <p>Controles: {ia.controles?.length ? ia.controles.map((c) => (typeof c === "string" ? c : `${(c.motivo || "").replaceAll("_", " ")}${c.detalle ? ` (${c.detalle})` : ""}`)).join(" · ") : "todos pasaron (citas verificadas en el registro, lecturas iguales, no baja a nadie)"}</p>
      </Seccion>}
      {pr && <Seccion t="Casos parecidos">
        {pr.total ? <p>En <b>{pr.total}</b> caso{pr.total !== 1 ? "s" : ""} parecido{pr.total !== 1 ? "s" : ""} ({textoPatron(pr.patron)}), los especialistas dijeron: <b>{pr.adecuadas}</b> adecuada{pr.adecuadas !== 1 ? "s" : ""} y <b>{pr.incorrectas}</b> incorrecta{pr.incorrectas !== 1 ? "s" : ""}.</p>
          : <p className="text-on-surface-variant">Aún no hay revisiones de especialistas en casos parecidos ({textoPatron(pr.patron)}).</p>}
        {pr.ultimos?.length > 0 && <ul className="list-disc pl-5">{pr.ultimos.map((u, i) => <li key={i}>{VEREDICTO_TXT[u.veredicto] || u.veredicto} · {u.usuario} · {fmt(u.fecha)}{u.motivo ? `: «${u.motivo}»` : ""}</li>)}</ul>}
      </Seccion>}
    </div>
  );
}

// Formulario del veredicto del especialista (uno solo para toda la app). Manda rev_vista: si el paciente cambió mientras
// lo tenía abierto, la API responde 409 y se avisa que hay información nueva.
export function FormVeredicto({ pid, categoria, idDictamen, rev, fecha, onListo, onAviso, onConflicto, texto }) {
  const [motivos, setMotivos] = useState([]);
  const [modo, setModo] = useState(null);  // null | "incorrecta"
  const [f, setF] = useState({ categoria, motivo_codigo: "", motivo: "" });
  const [revVista, setRevVista] = useState(rev);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { api.catalogoCache().then((c) => setMotivos(c.motivos_veredicto || [])).catch(() => {}); }, []);
  // la versión que vio: la de la fila si se conoce; si no, la del paciente al abrir el formulario
  useEffect(() => {
    if (rev != null) { setRevVista(rev); return; }
    let vivo = true;
    api.getPaciente(pid, fecha).then((x) => vivo && setRevVista(x.paciente?.rev)).catch(() => {});
    return () => { vivo = false; };
  }, [pid, rev, fecha]);

  const enviar = async (veredicto) => {
    if (!api.getUsuario()) { onAviso?.({ titulo: "Escriba su nombre y cargo arriba a la derecha: la revisión queda a su nombre" }); return; }
    const cambia = veredicto === "incorrecta" && f.categoria !== categoria;
    setEnviando(true); setError(null);
    try {
      const r = await api.postRevision(pid, { accion: cambia ? "ajustar" : "confirmar", veredicto, fecha_corte: fecha,
        ...(cambia ? { categoria_ajustada: f.categoria } : {}),
        ...(veredicto === "incorrecta" ? { motivo_codigo: f.motivo_codigo, motivo: f.motivo.trim() } : {}),
        ...(idDictamen ? { id_dictamen: idDictamen } : {}), ...(revVista != null ? { rev_vista: revVista } : {}) });
      setModo(null);
      onAviso?.({ titulo: veredicto === "adecuada" ? "Decisión marcada como adecuada" : cambia ? `Decisión marcada como incorrecta: prioridad ${ETIQUETA[f.categoria].toLowerCase()}` : "Decisión marcada como incorrecta" });
      await onListo?.(r);
    } catch (e) {
      if (e.status === 409 && e.codigo === "conflicto_edicion") {
        onAviso?.({ titulo: "El paciente tiene información nueva desde que abrió esta decisión: se recargó. Revísela de nuevo." });
        setError("El paciente recibió información nueva mientras tenía esto abierto. Se recargaron los datos: revise y vuelva a responder.");
        onConflicto?.();
      } else setError(e.message);
    } finally { setEnviando(false); }
  };
  const valido = f.motivo_codigo && f.motivo.trim().length >= MIN;
  const elegido = motivos.find((m) => m.valor === f.motivo_codigo);
  return (
    <div className="rounded border border-primary/30 bg-primary/5 p-3 flex flex-col gap-2 text-[14px]">
      {texto && <p className="text-[13px] text-on-surface-variant">{texto}</p>}
      <div className="flex flex-col sm:flex-row gap-2">
        <button onClick={() => enviar("adecuada")} disabled={enviando} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-50 flex items-center justify-center gap-1">
          <Icono n="thumb_up" className="text-[18px]" />La decisión es adecuada</button>
        <button onClick={() => setModo(modo ? null : "incorrecta")} disabled={enviando} aria-expanded={!!modo}
          className={`flex-1 py-2 rounded border font-semibold flex items-center justify-center gap-1 ${modo ? "bg-ambar-container border-ambar/50 text-ambar" : "border-primary text-primary"}`}>
          <Icono n="thumb_down" className="text-[18px]" />La decisión es incorrecta</button>
      </div>
      {modo && <div className="flex flex-col gap-2">
        <label className="flex flex-col gap-1"><span className="text-[13px] text-on-surface-variant">¿Qué prioridad corresponde?</span>
          <select value={f.categoria} onChange={(e) => setF({ ...f, categoria: e.target.value })} className="h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">
            {Object.entries(ETIQUETA).map(([k, v]) => <option key={k} value={k}>Prioridad {v.toLowerCase()}{k === categoria ? " (la que dejó el sistema)" : ""}</option>)}
          </select></label>
        <label className="flex flex-col gap-1"><span className="text-[13px] text-on-surface-variant">¿Por qué es incorrecta?</span>
          <select value={f.motivo_codigo} onChange={(e) => setF({ ...f, motivo_codigo: e.target.value })} className="h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">
            <option value="">Elija un motivo…</option>
            {motivos.map((m) => <option key={m.valor} value={m.valor}>{m.texto}</option>)}
          </select></label>
        {elegido?.efecto && <p className="text-[12px] text-on-surface-variant">Qué hace el sistema con esta respuesta: {elegido.efecto}.</p>}
        <textarea rows={2} value={f.motivo} onChange={(e) => setF({ ...f, motivo: e.target.value })} placeholder={`Explicación clínica (obligatoria, mínimo ${MIN} caracteres)`}
          className="px-2 py-1.5 border border-outline-variant rounded bg-surface-container-lowest" />
        <div className="flex items-center justify-between gap-2">
          <span className={`text-[12px] ${f.motivo.trim().length >= MIN ? "text-verde" : "text-on-surface-variant"}`}>{f.motivo.trim().length}/{MIN} caracteres</span>
          <button onClick={() => enviar("incorrecta")} disabled={!valido || enviando} className="px-4 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">
            {enviando ? "Guardando…" : "Guardar revisión"}</button>
        </div>
      </div>}
      {error && <p className="text-[13px] text-error">{error}</p>}
      <p className="text-[12px] text-on-surface-variant">Queda registrada a su nombre ({api.getUsuario() || "escriba su nombre arriba"}). Sirve para medir la concordancia y para que el sistema aprenda.</p>
    </div>
  );
}

// Qué aprendió el sistema con la respuesta del especialista (campo `aprendizaje` de POST /revision).
export function Aprendido({ a, pid, fecha, onAviso, onCambio, onIrAprendizaje }) {
  const [aplicada, setAplicada] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const s = a.sugerencia, c = a.criterio_local;
  const aplicar = async () => {
    setEnviando(true);
    try {
      await api.postEnmienda(pid, s.id_evento, { ...(s.cuerpo || { accion: s.accion }), fecha_corte: fecha, ...(api.getUsuario() ? { usuario: api.getUsuario() } : {}) });
      setAplicada(true); onAviso?.({ titulo: "Corrección del evento registrada: la prioridad se recalculó" }); await onCambio?.();
    } catch (e) { onAviso?.({ titulo: "No se pudo aplicar la corrección: " + e.message }); } finally { setEnviando(false); }
  };
  return (
    <div className="rounded border border-hlf/40 bg-hlf-claro p-3 text-[14px] flex flex-col gap-2">
      <div className="font-semibold text-hlf flex items-center gap-1"><Icono n="school" className="text-[18px]" />Qué aprendió el sistema con su respuesta</div>
      {c ? <div>
        <p>Propuso un <b>criterio local</b> ({c.id}): «{c.texto}».</p>
        <p className="text-[13px] text-on-surface-variant">Estado: <b>{c.estado}</b>. Lo propuesto no cambia ninguna prioridad hasta que una jefatura lo apruebe, y solo puede subir.</p>
        {onIrAprendizaje && <button onClick={onIrAprendizaje} className="text-[13px] text-primary font-semibold hover:underline">Ver en «Aprendizaje»</button>}
      </div> : s ? <div className="flex flex-col gap-1.5">
        <p>Sugiere corregir el evento <b>{s.id_evento}</b>: {s.texto}</p>
        {aplicada ? <p className="text-verde font-semibold">Corrección aplicada.</p>
          : <button onClick={aplicar} disabled={enviando} className="self-start px-3 py-1.5 rounded bg-primary text-on-primary font-semibold disabled:opacity-50">{enviando ? "Aplicando…" : "Aplicar la corrección"}</button>}
      </div> : <p>Queda como <b>precedente</b>: las próximas decisiones en casos parecidos mostrarán lo que usted respondió.</p>}
      {a.mensaje && <p className="text-[12px] text-on-surface-variant">{a.mensaje}</p>}
    </div>
  );
}
