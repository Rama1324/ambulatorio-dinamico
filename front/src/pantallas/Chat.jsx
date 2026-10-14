import { useEffect, useRef, useState } from "react";
import * as api from "../api";
import { LINEAS_AYUDA, estadoInicial, payload, pregunta, responder, textoLibre } from "../lib/chatFlujo";
import { Icono } from "../components/ui";

const DEMO = ["PAC-HLF-00001", "PAC-HLF-00002", "PAC-HLF-00028", "PAC-HLF-00020", "PAC-HLF-00003"];
const CARAS = (v) => (v <= 3 ? "M8 14s1.5 2 4 2 4-2 4-2" : v <= 6 ? "M8 15h8" : "M16 16s-1.5-2-4-2-4 2-4 2");

// Chat de seguimiento del paciente: preguntas simples, un tema por mensaje, botones grandes.
export function Chat({ pacientes, fecha, onEnviado, onVerLista }) {
  const [e, setE] = useState(estadoInicial);
  const [msgs, setMsgs] = useState(() => [{ de: "bot", texto: pregunta(estadoInicial()).texto }]);
  const [txt, setTxt] = useState("");
  const [escribiendo, setEscribiendo] = useState(false);
  const [verJson, setVerJson] = useState(false);
  const [enviado, setEnviado] = useState(null);
  const [error, setError] = useState(null);
  const caja = useRef(null);
  useEffect(() => { caja.current?.scrollTo({ top: caja.current.scrollHeight, behavior: "smooth" }); }, [msgs, escribiendo]);

  const ctx = { pacientes, fechaCorte: fecha };
  const q = e.fin ? null : pregunta(e);
  const decir = (nuevos, estado) => {
    setEscribiendo(true);
    setTimeout(() => {
      setEscribiendo(false);
      setMsgs((m) => [...m, ...nuevos, ...(estado.fin ? [{ de: "resumen" }] : [{ de: "bot", texto: pregunta(estado).texto }])]);
    }, 450);
  };
  const avanzar = (valor, etiqueta) => {
    if (escribiendo) return;
    setMsgs((m) => [...m, { de: "pac", texto: etiqueta }]);
    const r = responder(e, valor, ctx);
    if (r.error) return decir([{ de: "bot", texto: r.error }], e);
    setE(r.estado);
    decir(r.alerta ? [{ de: "alerta", texto: r.alerta }] : [], r.estado);
  };
  const enviarTexto = () => {
    const t = txt.trim();
    if (!t || escribiendo) return;
    setTxt("");
    if (e.paso === "id" || q?.entrada) return avanzar(t, t);
    setMsgs((m) => [...m, { de: "pac", texto: t }]);
    const r = textoLibre(e, t);
    setE(r.estado);
    decir([r.alerta ? { de: "alerta", texto: r.alerta } : { de: "bot", texto: "Gracias, lo dejo anotado para el equipo clínico." }], r.estado);
  };
  const reiniciar = () => { const s = estadoInicial(); setE(s); setMsgs([{ de: "bot", texto: pregunta(s).texto }]); setEnviado(null); setError(null); };
  const enviar = async () => {
    setError(null);
    try {
      const r = await api.postAutoreporte(e.paciente.id_paciente, payload(e, fecha));
      setEnviado(r.autoreporte); onEnviado?.(r);
    } catch (err) { setError(err.message); }
  };
  const datos = payload(e, fecha);
  const demo = pacientes.filter((p) => DEMO.includes(p.id_paciente));

  return (
    <section aria-label="Chat de seguimiento del paciente" className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px] items-start">
      <div className="flex flex-col bg-surface-container-lowest border-2 border-outline-variant h-[calc(100dvh-200px)] min-h-[440px] lg:h-[calc(100vh-220px)]">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b-2 border-outline-variant flex-wrap">
          <div className="flex-1 min-w-[160px]">
            <div className="font-bold text-[17px]">{e.paciente ? e.paciente.nombre_fantasia : "Seguimiento mientras espera"}</div>
            <div className="text-[14px] text-on-surface-variant">{e.paciente ? `${e.paciente.especialidad} · ${e.paciente.id_paciente}` : "El chat no diagnostica ni asigna horas"}</div>
          </div>
          <button onClick={() => setVerJson(!verJson)} aria-expanded={verJson} className="h-11 px-3 border-2 border-outline-variant font-semibold text-[14px] lg:hidden">{verJson ? "Ocultar datos" : "Ver datos capturados"}</button>
          <button onClick={reiniciar} className="h-11 px-3 font-semibold text-[14px] text-primary">Reiniciar</button>
        </div>

        <div ref={caja} role="log" aria-live="polite" className="flex-1 min-h-0 overflow-y-auto px-4 py-5 flex flex-col gap-2.5">
          {msgs.map((m, i) => m.de === "bot" ? (
            <div key={i} className="self-start max-w-[88%] bg-surface-container-low border-l-[3px] border-primary px-4 py-3 text-[17px] leading-snug">{m.texto}</div>
          ) : m.de === "pac" ? (
            <div key={i} className="self-end max-w-[82%] bg-primary text-on-primary px-4 py-3 text-[17px] leading-snug">{m.texto}</div>
          ) : m.de === "alerta" ? (
            <div key={i} role="alert" className="self-stretch bg-error text-on-error p-5 flex flex-col gap-3">
              <div className="flex items-center gap-2"><Icono n="warning" className="text-[28px]" /><strong className="text-[22px] leading-tight">Esto necesita atención ahora</strong></div>
              <p className="text-[17px] leading-snug">{m.texto}</p>
              <div className="border-t-2 border-on-error/60">
                {LINEAS_AYUDA.map((l) => (
                  <div key={l.num} className="flex justify-between items-baseline flex-wrap gap-x-4 py-2 border-b border-on-error/40">
                    <span className="text-[16px]">{l.label}</span>
                    <a href={`tel:${l.num.replace(/\s/g, "")}`} className="font-bold text-[22px] tracking-wide select-text underline-offset-4 hover:underline">{l.num}</a>
                  </div>
                ))}
              </div>
              <p className="text-[15px]">Su respuesta quedó marcada como alerta para el equipo clínico.</p>
            </div>
          ) : (
            <div key={i} className="self-stretch border-2 border-outline-variant bg-surface-container-lowest p-4 flex flex-col gap-3">
              <div className="text-[13px] tracking-wider uppercase text-on-surface-variant font-semibold">Resumen de lo registrado</div>
              <ul className="list-disc pl-5 text-[16px] leading-snug space-y-1">{datos.resumen.map((l, k) => <li key={k}>{l}</li>)}{e.textos.length > 0 && <li>Comentarios: «{e.textos.join(" · ")}»</li>}</ul>
              <p className="px-3 py-2.5 bg-primary/10 text-[15px]">El equipo clínico revisará esta información. Esto no es una hora asignada.</p>
              {enviado ? (
                <div className="flex flex-col gap-2">
                  <p className="text-[15px] font-semibold text-hlf flex items-center gap-1"><Icono n="task_alt" />Enviado al modelo como «por validar» ({enviado.id_autoreporte}).</p>
                  <button onClick={onVerLista} className="h-12 px-4 bg-primary text-on-primary font-semibold text-[16px] text-left flex items-center justify-between">Ver al paciente en la lista<Icono n="arrow_forward" /></button>
                </div>
              ) : (
                <button onClick={enviar} className="h-[52px] px-4 bg-primary text-on-primary font-semibold text-[17px] flex items-center justify-between">Enviar al modelo<Icono n="arrow_forward" /></button>
              )}
              {error && <p className="text-error text-[14px]">{error}</p>}
            </div>
          ))}
          {escribiendo && <div className="self-start escribiendo text-on-surface-variant px-4 py-3 bg-surface-container-low" aria-label="Escribiendo"><span /><span /><span /></div>}
          {e.paso === "id" && !escribiendo && demo.length > 0 && (
            <div className="border-t-2 border-outline-variant pt-3 mt-1 flex flex-col gap-2">
              <div className="text-[13px] tracking-wider uppercase text-on-surface-variant font-semibold">Modo demo · elija un paciente</div>
              <div className="grid gap-1.5 grid-cols-[repeat(auto-fill,minmax(220px,1fr))]">
                {demo.map((p) => (
                  <button key={p.id_paciente} onClick={() => avanzar(p.id_paciente, p.id_paciente)} className="text-left min-h-[56px] px-3 py-2 border border-outline-variant bg-surface-container-lowest hover:bg-primary/10">
                    <span className="flex gap-2 items-baseline"><strong className="text-[15px]">{p.nombre_fantasia}</strong><span className="ml-auto text-[13px] text-on-surface-variant">{p.id_paciente.slice(-5)}</span></span>
                    <span className="text-[13px] text-on-surface-variant">{p.especialidad} · {p.diagnostico_texto}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="border-t-2 border-outline-variant px-4 py-3 flex flex-col gap-2.5">
          {q?.opciones && !escribiendo && (
            <div className="flex flex-wrap gap-2">
              {q.opciones.map((o) => (
                <button key={String(o.valor)} onClick={() => avanzar(o.valor, o.label)} className="min-h-[48px] px-4 py-2 text-[17px] border-2 border-primary bg-surface-container-lowest text-left font-medium hover:bg-primary/10 active:bg-primary/20">{o.label}</button>
              ))}
            </div>
          )}
          {q?.escala && !escribiendo && (
            <div>
              <div className="grid gap-1 grid-cols-[repeat(auto-fill,minmax(48px,1fr))]">
                {Array.from({ length: 11 }, (_, v) => (
                  <button key={v} onClick={() => avanzar(v, `${v} de 10`)} aria-label={`Dolor ${v} de 10`}
                    className="min-h-[64px] flex flex-col items-center justify-center gap-1 border border-outline-variant bg-surface-container-lowest hover:bg-primary/10"
                    style={{ borderBottom: `5px solid ${v <= 3 ? "rgb(var(--c-verde))" : v <= 6 ? "rgb(var(--c-ambar))" : "rgb(var(--c-error))"}` }}>
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="10" /><path d="M9 9h.01M15 9h.01" /><path d={CARAS(v)} /></svg>
                    <span className="font-semibold text-[17px]">{v}</span>
                  </button>
                ))}
              </div>
              <div className="flex justify-between text-[14px] text-on-surface-variant mt-1"><span>0 · sin dolor</span><span>10 · el peor dolor</span></div>
            </div>
          )}
          <div className="flex gap-2">
            <input value={txt} onChange={(ev) => setTxt(ev.target.value)} onKeyDown={(ev) => ev.key === "Enter" && enviarTexto()} disabled={e.fin}
              placeholder={e.paso === "id" ? "PAC-HLF-00001" : q?.entrada === "presion" ? "135/85" : q?.entrada === "numero" ? "Escriba el número" : "Escriba si quiere contar algo más"}
              aria-label="Escriba su respuesta" inputMode={q?.entrada === "numero" ? "decimal" : "text"}
              className="flex-1 min-w-0 h-12 px-3 text-[17px] border-2 border-outline-variant focus:border-primary outline-none disabled:opacity-50" />
            <button onClick={enviarTexto} disabled={e.fin} aria-label="Enviar" className="h-12 w-14 bg-primary text-on-primary flex items-center justify-center disabled:opacity-40"><Icono n="send" /></button>
          </div>
        </div>
      </div>

      <aside aria-label="Datos capturados" className={`${verJson ? "flex" : "hidden"} lg:flex flex-col border-2 border-outline-variant bg-surface-container-lowest lg:h-[calc(100vh-220px)]`}>
        <div className="px-4 py-2.5 border-b-2 border-outline-variant">
          <div className="font-bold text-[16px]">Datos capturados</div>
          <div className="text-[14px] text-on-surface-variant leading-snug">En vivo. Entra al modelo con fuente <b>autoreporte</b> y estado <b>por validar</b>: la prioridad cambia solo cuando el equipo clínico lo valida.</div>
        </div>
        <pre className="flex-1 min-h-0 overflow-auto m-0 p-4 text-[13px] leading-relaxed bg-surface-container-low whitespace-pre-wrap break-words font-mono">{JSON.stringify(datos, null, 2)}</pre>
      </aside>
    </section>
  );
}
