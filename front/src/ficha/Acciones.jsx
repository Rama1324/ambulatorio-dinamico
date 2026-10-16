import { useEffect, useState } from "react";
import * as api from "../api";
import { Caja, Filtro, Icono } from "../componentes/comunes";
import { ESTILO_GESTION } from "../constantes";
import { fmt } from "../util";

// Novedades que registra el equipo: comorbilidad (pondera en Charlson/LACE), cambio de diagnóstico y egresos.
export function Novedad({ p, fecha, onListo, onAviso }) {
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
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest w-full";
  const btn = (t, icono, texto, rojo) => (
    <button onClick={() => abrir(t)} className={`flex-1 min-w-[120px] py-2 rounded border font-semibold text-[13px] flex items-center justify-center gap-1 ${tipo === t ? (rojo ? "bg-error text-on-error border-error" : "bg-primary text-on-primary border-primary") : "border-outline-variant hover:bg-surface-container-low"}`}>
      <Icono n={icono} className="text-[18px]" />{texto}
    </button>
  );
  return (
    <Caja titulo="Registrar novedad del paciente">
      {p.comorbilidades?.length > 0 && <p className="text-[13px] mb-2">Comorbilidades registradas: {p.comorbilidades.map((c) => c.nombre).join(", ")}</p>}
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
          {v.condicion && <p className={`text-[13px] ${peso ? "text-primary-container font-semibold" : "text-on-surface-variant"}`}>
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
          <p className="text-[13px] text-on-surface-variant">Se vuelve a aplicar la tabla del HLF, el puntaje LACE y la garantía GES del nuevo diagnóstico. Si cambia la especialidad, el paciente pasa a esa lista.</p>
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
          <p className="text-[13px] text-on-surface-variant">El grupo de protección ordena dentro de la misma prioridad (MINSAL Ord. 536/2025). El ACG se muestra como dato de riesgo del SSMSO.</p>
          <button disabled={enviando} onClick={enviar} className="w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Guardar y recalcular</button>
        </div>
      )}

      {(tipo === "fallecimiento" || tipo === "atendido") && (
        <div className="mt-3 space-y-2 text-[14px]">
          <Filtro label={tipo === "fallecimiento" ? "Fecha de defunción" : "Fecha de la consulta nueva de especialidad"}>
            <input type="date" value={v.fecha} max={fecha} onChange={(e) => setV({ ...v, fecha: e.target.value })} className={campo} />
          </Filtro>
          <p className="text-[13px] text-on-surface-variant">{tipo === "fallecimiento"
            ? "Egreso por causal 9 (fallecimiento, Manual SSMSO). El paciente sale de la lista y no recibe nuevas citaciones."
            : "La lista se resuelve cuando el especialista atiende la consulta nueva (CNE). El paciente sale de la lista."}</p>
          <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={confirma} onChange={(e) => setConfirma(e.target.checked)} />
            Confirmo que {p.nombre_fantasia} {tipo === "fallecimiento" ? "falleció" : "fue atendido(a)"} (verificado en {tipo === "fallecimiento" ? "Registro Civil / ficha" : "la ficha clínica"}).</label>
          <button disabled={!confirma || !v.fecha || enviando} onClick={enviar} className={`w-full py-2 rounded font-semibold disabled:opacity-40 ${tipo === "fallecimiento" ? "bg-error text-on-error" : "bg-primary text-on-primary"}`}>
            {tipo === "fallecimiento" ? "Registrar fallecimiento y egresar" : "Registrar atención y egresar"}</button>
        </div>
      )}
    </Caja>
  );
}

// Contacto = lo que hace quien llama (no decide). Solo cierran la alerta: cita reservada o derivación a urgencia.
export function Contacto({ p, fecha, onListo, onAviso }) {
  const [nota, setNota] = useState("");
  const [enviando, setEnviando] = useState(null);
  const enviar = async (resultado) => {
    setEnviando(resultado);
    try { onListo(await api.postContacto(p.id_paciente, { resultado, nota, fecha_corte: fecha })); setNota(""); }
    catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(null); }
  };
  const ops = [["citado", "Citado (sobrecupo)", "bg-primary text-on-primary"], ["derivado_urgencia", "Derivado a urgencia", "bg-error text-on-error"],
    ["contactado", "Informado, sin decisión aún", "border border-outline-variant"], ["no_contesta", "No contesta", "border border-outline-variant"]];
  return (
    <Caja titulo="Registrar llamada">
      {p.contacto && <p className="text-[13px] mb-2">Última: <b>{p.contacto.texto}</b> · {p.contacto.usuario}{p.contacto.intentos_sin_respuesta > 0 && ` · ${p.contacto.intentos_sin_respuesta} intento(s) sin respuesta`}</p>}
      <input value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Nota (opcional): p. ej. quién contestó" className="w-full h-9 px-2 border border-outline-variant rounded mb-2 text-[14px]" />
      <div className="grid grid-cols-2 gap-2 text-[13px]">
        {ops.map(([k, t, c]) => <button key={k} disabled={enviando} onClick={() => enviar(k)} className={`py-2 rounded font-semibold disabled:opacity-50 ${c}`}>{enviando === k ? "…" : t}</button>)}
      </div>
      <p className="text-[12px] text-on-surface-variant mt-2">Llamar, citar o derivar quedan registrados por separado. La alerta de descompensación se cierra solo cuando el especialista revisa la prioridad (decisión, confirmar o ajustar).</p>
    </Caja>
  );
}

// Gestión del caso: qué falta (estado calculado), quién se encarga, qué se hace y cuándo se vuelve a mirar.
const MOTIVOS_PENDIENTE = [["falta_cupo", "Falta de cupo"], ["contacto", "No se ha podido contactar"], ["antecedentes", "Faltan antecedentes o exámenes"],
  ["revision", "Espera revisión del especialista"], ["paciente", "Decisión o disponibilidad del paciente"],
  ["revision_humana", "El paciente pidió que una persona revise su prioridad (Ley 21.719, art. 8 bis)"], ["otro", "Otro (documentado)"]];

export function GestionCaso({ p, fecha, onListo, onAviso }) {
  const g = p.gestion || {};
  const [f, setF] = useState({ responsable: g.responsable || api.getUsuario(), proxima_accion: g.accion_asignada ? g.proxima_accion : "",
    seguimiento: g.seguimiento || "", motivo_pendiente: g.motivo_pendiente || "", nota: g.nota || "" });
  const [enviando, setEnviando] = useState(false);
  const usuario = api.getUsuario();
  const notaCorta = f.motivo_pendiente === "otro" && f.nota.trim().length < MIN_EXPLICACION;
  const guardar = async () => {
    setEnviando(true);
    try { await api.postGestion(p.id_paciente, { ...f, fecha_corte: fecha }); onListo(); }
    catch (e) { onAviso({ titulo: "No se pudo guardar: " + e.message }); } finally { setEnviando(false); }
  };
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest text-[14px] w-full";
  return (
    <Caja titulo="Gestión del caso">
      <div className="text-[14px] mb-2">Estado: <b className={ESTILO_GESTION[g.estado]}>{g.texto}</b>
        <span className="text-[12px] text-on-surface-variant"> (se calcula con lo registrado: revisión, llamadas y citas)</span></div>
      {g.actualizado_por && <p className="text-[12px] text-on-surface-variant mb-2">Última actualización: {g.actualizado_por} · {fmt(g.actualizado)}</p>}
      <div className="grid grid-cols-2 gap-2 text-[13px]">
        <Filtro label="Responsable"><input value={f.responsable} onChange={(e) => setF({ ...f, responsable: e.target.value })} placeholder="Nombre y cargo" className={campo} /></Filtro>
        <Filtro label="Fecha de seguimiento"><input type="date" min={fecha} value={f.seguimiento} onChange={(e) => setF({ ...f, seguimiento: e.target.value })} className={campo} /></Filtro>
        <div className="col-span-2"><Filtro label={`Próxima acción (si se deja vacía: "${ESTADO_ACCION[g.estado] || g.proxima_accion}")`}>
          <input value={f.proxima_accion} onChange={(e) => setF({ ...f, proxima_accion: e.target.value })} placeholder="Ej.: pedir ecografía a APS antes de citar" className={campo} /></Filtro></div>
        <div className="col-span-2"><Filtro label="Motivo del pendiente (qué bloquea la atención)">
          <select value={f.motivo_pendiente} onChange={(e) => setF({ ...f, motivo_pendiente: e.target.value })} className={campo}>
            <option value="">Sin motivo registrado</option>{MOTIVOS_PENDIENTE.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select></Filtro></div>
        <div className="col-span-2"><Filtro label={f.motivo_pendiente === "otro" ? `Nota (obligatoria, mínimo ${MIN_EXPLICACION} caracteres)` : "Nota (opcional)"}>
          <input value={f.nota} onChange={(e) => setF({ ...f, nota: e.target.value })} className={campo} /></Filtro></div>
      </div>
      {!usuario && <p className="text-[12px] text-ambar font-semibold mt-2">Escriba su nombre y cargo arriba a la derecha: la gestión queda registrada a su nombre.</p>}
      <button disabled={enviando || !usuario || notaCorta} onClick={guardar} className="mt-2 w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{enviando ? "Guardando…" : "Guardar gestión"}</button>
    </Caja>
  );
}

const ESTADO_ACCION = { pendiente_revision: "Ver si corresponde cambiar la prioridad", pendiente_contacto: "Volver a llamar", pendiente_cita: "Buscar cupo y citar",
  cita_reservada: "Confirmar asistencia" };

// Ajuste manual de la posición en la lista: siempre con un motivo previo, explicado y a nombre de quien lo hace.
const MOTIVOS_AJUSTE = [["criterio_clinico", "Criterio clínico del especialista"], ["informacion_no_registrada", "Información clínica que no está en el registro"],
  ["comite", "Decisión de comité o jefatura"], ["error_registro", "Corrección de un error de registro"], ["otro", "Otro motivo (explicado)"]];

const MIN_EXPLICACION = 20;

export function AjusteManual({ p, fecha, onListo, onAviso }) {
  const [abierto, setAbierto] = useState(false);
  const [f, setF] = useState({ posicion: "", motivo: "", explicacion: "" });
  const [enviando, setEnviando] = useState(false);
  const usuario = api.getUsuario();
  const a = p.ajuste_manual;
  const faltan = MIN_EXPLICACION - f.explicacion.trim().length;
  const enviar = async (quitar) => {
    setEnviando(true);
    try {
      const body = quitar ? { quitar: true, explicacion: f.explicacion, fecha_corte: fecha }
        : { posicion: Number(f.posicion), motivo: f.motivo, explicacion: f.explicacion, fecha_corte: fecha };
      const r = await api.postOrden(p.id_paciente, body);
      setAbierto(false); setF({ posicion: "", motivo: "", explicacion: "" }); onListo(r, quitar);
    } catch (e) { onAviso({ titulo: "No se pudo guardar: " + e.message }); } finally { setEnviando(false); }
  };
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest text-[14px]";
  return (
    <Caja titulo="Mover en la lista (ajuste manual)" accion={!abierto && <button onClick={() => setAbierto(true)} className="text-[13px] text-primary font-semibold">{a ? "Cambiar o deshacer" : "Mover"}</button>}>
      {a ? <div className="text-[14px] rounded bg-primary/5 border border-primary/30 p-2">
          <b>Movido a mano al N° {a.posicion} de {a.especialidad}</b> (el sistema lo ponía en el N° {a.posicion_anterior}).
          <div className="text-[13px] mt-0.5">Motivo: {a.motivo_texto}. «{a.explicacion}»</div>
          <div className="text-[12px] text-on-surface-variant">{a.usuario} · {fmt(a.fecha)}</div>
        </div>
        : <p className="text-[13px] text-on-surface-variant">N° {p.posicion_especialidad} en la lista de {p.especialidad}. Si el equipo necesita cambiar su lugar, debe dejar el motivo explicado: queda registrado a su nombre.</p>}
      {p.ajuste_manual_vencido && <p className="mt-2 text-[13px] text-ambar font-semibold">El ajuste manual anterior dejó de aplicarse por un evento nuevo ({p.ajuste_manual_vencido.vencido_por}): revise su lugar en la lista.</p>}
      {abierto && (
        <div className="mt-3 flex flex-col gap-2 text-[14px]">
          {!usuario && <p className="text-[13px] text-ambar font-semibold">Escriba su nombre y cargo arriba a la derecha: el ajuste queda registrado a su nombre.</p>}
          {a && <p className="text-[13px] text-on-surface-variant">Para deshacer el ajuste, explique por qué y presione "Deshacer". Para cambiarlo, complete todo.</p>}
          <label className="flex items-center gap-2">Mover al N°
            <input type="number" min={1} value={f.posicion} onChange={(e) => setF({ ...f, posicion: e.target.value })} className={`${campo} w-24`} />
            <span className="text-on-surface-variant text-[13px]">de la lista de {p.especialidad}</span></label>
          <select value={f.motivo} onChange={(e) => setF({ ...f, motivo: e.target.value })} className={campo}>
            <option value="">Motivo del ajuste…</option>{MOTIVOS_AJUSTE.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
          <textarea rows={3} value={f.explicacion} onChange={(e) => setF({ ...f, explicacion: e.target.value })}
            placeholder="Explique el motivo (obligatorio). Ej.: la familia informa crisis semanales que no están registradas; evaluado por el Dr. X."
            className="p-2 border border-outline-variant rounded bg-surface-container-lowest resize-y" />
          <span className={`text-[12px] ${faltan > 0 ? "text-ambar" : "text-on-surface-variant"}`}>{faltan > 0 ? `Faltan ${faltan} caracteres para explicar el motivo.` : "Explicación suficiente."}</span>
          <div className="flex gap-2">
            <button disabled={enviando || !usuario || faltan > 0 || !f.motivo || !(Number(f.posicion) >= 1)} onClick={() => enviar(false)}
              className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{enviando ? "Guardando…" : "Mover"}</button>
            {a && <button disabled={enviando || !usuario || faltan > 0} onClick={() => enviar(true)} className="flex-1 py-2 rounded border border-primary text-primary font-semibold disabled:opacity-40">Deshacer</button>}
            <button onClick={() => setAbierto(false)} className="px-3 py-2 rounded border border-outline-variant font-semibold">Cancelar</button>
          </div>
          <p className="text-[12px] text-on-surface-variant">Si después llega un evento clínico nuevo (urgencia, hospitalización, examen alterado), el ajuste deja de aplicarse y el paciente vuelve al orden del sistema para que se revise.</p>
        </div>
      )}
    </Caja>
  );
}

export function DecisionClinica({ p, fecha, onListo, onAviso }) {
  const [f, setF] = useState({ decision: "citar_prioritario", responsable: api.getUsuario(), nota: "", seguimiento: "" });
  const [enviando, setEnviando] = useState(false);
  const enviar = async () => {
    setEnviando(true);
    try { onListo(await api.postDecision(p.id_paciente, { ...f, seguimiento: f.seguimiento || null, fecha_corte: fecha })); }
    catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(false); }
  };
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest text-[14px]";
  return (
    <Caja titulo="Decisión del especialista ante la descompensación" className={p.contactar_hoy ? "border-l-4 border-l-error" : ""}>
      {p.decision && <p className="text-[13px] mb-2">Última: <b>{p.decision.texto}</b> · {p.decision.responsable}{p.decision.nota && ` · ${p.decision.nota}`}</p>}
      <div className="grid grid-cols-2 gap-2">
        <select value={f.decision} onChange={(e) => setF({ ...f, decision: e.target.value })} className={`${campo} col-span-2`}>
          <option value="citar_prioritario">Citar en forma prioritaria</option><option value="derivar_urgencia">Derivar a urgencia</option>
          <option value="adelantar_control">Adelantar control o teleconsulta</option><option value="mantener">Se mantiene en lista con su prioridad</option>
        </select>
        <input value={f.responsable} onChange={(e) => setF({ ...f, responsable: e.target.value })} placeholder="Profesional responsable" className={campo} />
        <label className="flex items-center gap-1 text-[12px] text-on-surface-variant">Seguimiento
          <input type="date" min={fecha} value={f.seguimiento} onChange={(e) => setF({ ...f, seguimiento: e.target.value })} className={`${campo} flex-1`} /></label>
        <input value={f.nota} onChange={(e) => setF({ ...f, nota: e.target.value })} placeholder="Fundamento (opcional)" className={`${campo} col-span-2`} />
      </div>
      <button disabled={enviando || !f.responsable.trim()} onClick={enviar} className="mt-2 w-full py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{enviando ? "Guardando…" : "Registrar decisión"}</button>
    </Caja>
  );
}
