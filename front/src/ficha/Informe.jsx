import { useEffect, useRef, useState } from "react";
import * as api from "../api";
import { Caja, Icono, Prioridad } from "../componentes/comunes";
import { TIPO_EVENTO } from "../constantes";
import { fmtHace } from "../util";

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
          <p className="text-[13px] text-on-surface-variant mt-2">Encuadre el documento completo dentro del recuadro, con buena luz.</p>
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

export function Informe({ p, fecha, cargando, onConfirmar, onAviso, onRegistrado }) {
  const [texto, setTexto] = useState("");
  const [res, setRes] = useState(null);
  const [leyendo, setLeyendo] = useState(false);
  const [camara, setCamara] = useState(false);
  const [elegido, setElegido] = useState(0);
  const [esDelPaciente, setEsDelPaciente] = useState(false);
  const [fechaEv, setFechaEv] = useState("");  // fecha del evento que confirma el equipo (corrige la del documento)
  const analizar = async (body) => {
    setLeyendo(true); setRes(null); setElegido(0); setEsDelPaciente(false);
    try {
      const r = await api.postInforme(p.id_paciente, { ...body, fecha_corte: fecha });
      setRes(r);
      if (r.registrados?.length) await onRegistrado?.(r);
    }
    catch (e) { onAviso({ titulo: "No se pudo leer el informe: " + e.message }); }
    finally { setLeyendo(false); }
  };
  const foto = (b64) => { setCamara(false); analizar({ imagen_base64: b64, media_type: "image/jpeg" }); };
  const eventos = res?.eventos || [];
  const ev = eventos[elegido];
  useEffect(() => setFechaEv(ev?.fecha_en_documento ? ev.fecha_evento : ""), [ev]);  // sin fecha en el documento: la indica una persona
  const dudosas = new Set((res?.lectura?.lineas_dudosas || []).map((l) => l.texto));
  const bloqueado = res?.otro_paciente || (res?.lectura && !res.lectura.legible);
  return (
    <Caja titulo="Registrar informe recibido">
      <p className="text-[13px] text-on-surface-variant mb-2">Epicrisis, DAU de urgencia, biopsia o nota clínica. {p.algoritmo
        ? "La IA lo lee 3 veces y lo que verifica en el texto (cáncer, hospitalización, descompensación…) se registra solo y la lista se recalcula. Lo que podría bajar una prioridad lo confirma usted."
        : "Se propone el evento y usted confirma antes de actualizar la lista."}</p>
      <textarea rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Ej.: Consulta en urgencia por dolor torácico en reposo. Se hospitaliza en cardiología."
        className="w-full p-2 border border-outline-variant rounded focus:outline-none focus:border-primary resize-y text-[14px]" />
      <div className="flex gap-2 mt-2">
        <button disabled={!texto.trim() || leyendo} onClick={() => analizar({ texto })} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{leyendo ? "Leyendo…" : "Revisar informe"}</button>
        <button disabled={leyendo} onClick={() => setCamara(true)} className="flex-1 py-2 rounded border border-outline-variant font-semibold flex items-center justify-center gap-1"><Icono n="photo_camera" className="text-[18px]" />Foto del documento</button>
      </div>
      {camara && <Camara onFoto={foto} onCerrar={() => setCamara(false)} />}
      {leyendo && <p className="mt-2 text-[13px] text-on-surface-variant flex items-center gap-1"><Icono n="hourglass_top" className="text-[16px] animate-spin" />Leyendo el documento…</p>}
      {res?.advertencias?.length > 0 && (
        <div className="mt-3 space-y-1">
          {res.advertencias.map((a, i) => (
            <div key={i} className={`rounded p-2 text-[13px] flex gap-1.5 ${res.otro_paciente && i === 0 ? "bg-error text-on-error font-semibold" : "bg-ambar-container text-ambar"}`}>
              <Icono n="warning" className="text-[18px]" /><span>{a}</span></div>
          ))}
        </div>
      )}
      {res?.registrados?.length > 0 && (
        <div className="mt-3 rounded border border-hlf bg-hlf-claro p-3 text-[14px] space-y-1.5">
          <p className="font-semibold text-hlf flex items-center gap-1"><Icono n="check_circle" className="text-[18px]" />Registrado automáticamente ({res.ia?.lecturas} lecturas iguales de la IA, cita verificada en el documento)</p>
          {res.registrados.map((e, i) => (
            <div key={i}><b>{TIPO_EVENTO[e.tipo_evento] || e.tipo_evento}</b> · {e.subtipo} · {fmtHace(e.fecha_evento, fecha)}
              {e.fecha_en_documento === false && <span className="text-ambar text-[12px]"> (el documento no dice la fecha: se usó la de hoy)</span>}
              {e.motivo && <span> · motivo: {e.motivo}</span>}
              {e.relacionado === false && <span className="ml-1 text-[12px] rounded bg-surface-container-low px-1">sin relación con su diagnóstico: no cambia su prioridad</span>}
              <blockquote className="border-l-4 border-hlf px-2 italic text-[13px]">“{e.cita}”</blockquote></div>
          ))}
          {res.posicion_antes != null && <p className="text-[13px]">N° {res.posicion_antes} → <b>N° {res.posicion_despues}</b> · prioridad <Prioridad cat={res.paciente?.categoria} /></p>}
          {res.paciente?.razones?.filter((r) => r.factor === "oncologico" || r.factor === "tabla_oficial").map((r, i) => <p key={i} className="text-[12px] text-on-surface-variant">{r.valor} · Fuente: {r.fuente}</p>)}
        </div>
      )}
      {res?.criterio && (res.criterio.nivel || res.criterio.urgencia) && (
        <div className={`mt-3 rounded p-3 text-[14px] ${res.criterio.urgencia ? "bg-error text-on-error" : "border border-primary bg-primary/5"}`}>
          <b>{res.criterio.urgencia ? "Derivar hoy a urgencia" : `Criterio clínico (${res.criterio.enfermedad}): ${res.criterio.nivel}`}</b>
          {res.criterio.urgencia && <div>{res.criterio.urgencia} · “{res.criterio.cita_urgencia}”</div>}
          {res.criterio.nivel && <div className="text-[13px]">{res.criterio.criterio} · “{res.criterio.cita}”</div>}
          <div className="text-[12px] opacity-80">{res.criterio.fuente} · solo sube la prioridad, nunca la baja.</div>
        </div>
      )}
      {res?.combinaciones?.aplicadas?.length > 0 && (
        <div className={`mt-3 rounded p-3 text-[14px] ${res.combinaciones.aplicadas.some((a) => a.efecto === "urgencia") ? "bg-error text-on-error" : "border border-error bg-error-container/40"}`}>
          <b>Combinación de riesgo detectada</b>
          {res.combinaciones.aplicadas.map((a) => (
            <div key={a.id} className="text-[13px] mt-1">{a.efecto === "urgencia" ? "URGENCIA · " : "Prioridad alta · "}<b>{a.nombre}</b>: “{a.cita_gatillo}” → riesgo de {a.desenlace}
              <div className="text-[12px] opacity-80">Fuente: {a.fuente.documento}{a.fuente.ubicacion ? `, ${a.fuente.ubicacion}` : ""}{a.estado === "guia_citada" ? " (verificar texto)" : ""}</div></div>
          ))}
        </div>
      )}
      {res?.combinaciones?.alertas?.length > 0 && res.combinaciones.alertas.map((a, i) => (
        <div key={i} className="mt-2 rounded p-2 text-[13px] bg-ambar-container text-ambar"><b>Posible combinación de riesgo (no está en la lista):</b> {a.descripcion} · “{a.cita}”. Queda visible para el equipo; no cambia la prioridad.</div>
      ))}
      {res?.informativos?.length > 0 && res.informativos.map((h, i) => (
        <p key={i} className="mt-2 text-[13px] text-on-surface-variant">ℹ “{h.cita}”: {h.nota}.</p>
      ))}
      {res?.segundos != null && <p className="mt-1 text-[12px] text-on-surface-variant">Leído por IA (Amazon Bedrock) en {res.segundos} s.</p>}
      {res && !ev && !res.registrados?.length && <p className="mt-2 text-[13px] text-on-surface-variant">{res.mensaje}</p>}
      {res?.transcripcion && (
        <details className="mt-2 text-[13px]" open={dudosas.size > 0}>
          <summary className="cursor-pointer text-on-surface-variant">
            Texto leído del documento (Amazon Textract{res.lectura?.confianza_media != null && ` · confianza ${res.lectura.confianza_media}%`})
          </summary>
          <div className="mt-1 rounded border border-outline-variant p-2 font-mono text-[12px]">
            {res.transcripcion.split("\n").map((l, i) => <div key={i} className={dudosas.has(l) ? "bg-ambar-container text-ambar" : ""} title={dudosas.has(l) ? "Leída con baja confianza: verifique" : ""}>{l}</div>)}
          </div>
        </details>
      )}
      {res?.descartados?.length > 0 && <p className="mt-1 text-[12px] text-on-surface-variant">Descartados por la validación: {res.descartados.map((d) => `${d.subtipo}${d.cita ? ` “${d.cita}”` : ""} (${d.motivo})`).join("; ")}</p>}
      {ev && (
        <div className="mt-3 border border-outline-variant rounded p-3 space-y-2 text-[14px]">
          {res.modo === "ia" && <p className="text-[13px] font-semibold text-ambar">Para confirmar: {ev.motivo}</p>}
          {eventos.length > 1 && <p className="text-[13px] font-semibold">Se encontraron {eventos.length} eventos en el documento. Elija cuál registrar:</p>}
          <div className="space-y-1">
            {eventos.map((e, i) => (
              <label key={i} className={`flex items-start gap-2 rounded p-1.5 cursor-pointer ${i === elegido ? "bg-primary/10" : "hover:bg-surface-container-low"}`}>
                {eventos.length > 1 && <input type="radio" checked={i === elegido} onChange={() => setElegido(i)} className="mt-1" />}
                <span>
                  <b>{TIPO_EVENTO[e.tipo_evento]}</b> · {e.subtipo} · {fmtHace(e.fecha_evento, fecha)}
                  {!e.fecha_en_documento && <span className="text-ambar text-[12px]"> (fecha no encontrada: verificar)</span>}
                  {(e.detectado_por === "bedrock" || e.detectado_por === "ia") && <span className="ml-1 text-[11px] rounded bg-tertiary-fixed text-on-tertiary-fixed-variant px-1">leído por IA</span>}
                </span>
              </label>
            ))}
          </div>
          <blockquote className="border-l-4 border-ambar bg-ambar-container/40 px-2 py-1 italic">“{ev.evidencia}”</blockquote>
          <label className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className={ev.fecha_en_documento ? "text-on-surface-variant" : "text-ambar font-semibold"}>
              {ev.fecha_en_documento ? "¿Cuándo ocurrió?" : "El documento no dice cuándo ocurrió. Indique la fecha:"}</span>
            <input type="date" value={fechaEv} max={fecha} onChange={(e) => setFechaEv(e.target.value)} className="h-8 px-2 border border-outline-variant rounded" />
            {fechaEv && <span className="text-on-surface-variant">{fmtHace(fechaEv, fecha).split(" (")[1]?.replace(")", "")}</span>}
          </label>
          <div className="flex items-center gap-2"><span className="text-on-surface-variant">Prioridad:</span><Prioridad cat={res.categoria_actual} /><span>→</span><Prioridad cat={ev.categoria_propuesta} /></div>
          {ev.razones_propuestas?.map((r, i) => <div key={i} className="text-[13px] text-on-surface-variant">{r.valor} · {r.fuente}</div>)}
          <label className={`flex items-start gap-2 rounded p-2 text-[13px] ${bloqueado ? "opacity-50" : "bg-surface-container-low"}`}>
            <input type="checkbox" checked={esDelPaciente} disabled={bloqueado} onChange={(e) => setEsDelPaciente(e.target.checked)} className="mt-0.5" />
            <span>Confirmo que el documento corresponde a <b>{p.nombre_fantasia}</b> ({p.id_paciente}) y que el evento está bien leído.</span>
          </label>
          <div className="flex gap-2 pt-1">
            <button disabled={cargando || !esDelPaciente || bloqueado || !fechaEv} onClick={async () => { if (await onConfirmar({ ...ev, fecha_evento: fechaEv, detalle: `Informe: ${ev.evidencia}` })) { setRes(null); setTexto(""); } }}
              className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">Confirmar y actualizar lista</button>
            <button onClick={() => setRes(null)} className="flex-1 py-2 rounded border border-outline-variant font-semibold">Descartar</button>
          </div>
          <p className="text-[12px] text-on-surface-variant">
            {res.transcripcion ? "Leído con Amazon Textract (OCR). " : ""}Evento detectado por {ev.detectado_por === "bedrock" ? "IA (respaldo)" : ev.detectado_por === "ia" ? "IA (Amazon Bedrock)" : "reglas"} y validado: tipo y severidad del registro, frase presente en el documento, fecha no futura.
          </p>
        </div>
      )}
    </Caja>
  );
}
