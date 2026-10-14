import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as api from "./api";
import "./App.css";

const ESPECIALIDADES = ["Todas", "Cardiología", "Traumatología", "Endocrinología", "Salud Mental", "Broncopulmonar", "Neurología", "Gastroenterología"];
const ETIQUETA = { critica: "Crítica", alta: "Alta", media: "Media", baja: "Baja" };
const EVENTOS = {
  urgencia: { label: "Urgencia (triage ESI 2)", tipo_evento: "visita_urgencia", subtipo: "triage ESI 2", severidad: "grave" },
  hospitalizacion: { label: "Hospitalización", tipo_evento: "hospitalizacion", subtipo: "ingreso hospitalario", severidad: "grave" },
  examen: { label: "Examen alterado", tipo_evento: "examen_alterado", subtipo: "resultado alterado", severidad: "moderada" },
  mejora: { label: "Buena respuesta en APS", tipo_evento: "control_aps", subtipo: "buena respuesta", severidad: "leve" },
};
const FACTOR = { prioridad_inicial: "Prioridad inicial", dias_espera: "Días en espera", plazo_vencido: "Plazo clínico vencido", mediciones_fuera_rango: "Mediciones fuera de rango", edad: "Edad" };

export default function App() {
  const fechas = api.fechas();
  const [iFecha, setIFecha] = useState(fechas.length - 1);
  const [esp, setEsp] = useState("Todas");
  const [vista, setVista] = useState("lista");
  const [data, setData] = useState(null);
  const [sel, setSel] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [destacado, setDestacado] = useState(null);
  const [error, setError] = useState(null);
  const fecha = fechas[iFecha];
  const esApi = api.MODO === "api";

  const cargar = useCallback(async () => {
    try {
      setError(null);
      setData(await api.getPacientes(fecha, esp === "Todas" ? null : esp));
    } catch (e) { setError(e.message); }
  }, [fecha, esp]);

  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    if (!sel) return setDetalle(null);
    api.getPaciente(sel, fecha).then(setDetalle).catch(() => setDetalle(null));
  }, [sel, fecha, data]);

  const mostrarAviso = (txt) => { setAviso(txt); setTimeout(() => setAviso(null), 4000); };

  if (!data) return <div className="cargando">{error ? `Error: ${error}` : "Cargando…"}</div>;
  const lista = data.pacientes.slice(0, 50);
  const paciente = sel && data.pacientes.find((p) => p.id_paciente === sel);
  const altos = data.pacientes.filter((p) => p.categoria === "critica" || p.categoria === "alta").length;

  return (
    <div className="app">
      <header>
        <div>
          <h1>Ambulatorio Dinámico</h1>
          <p>Hospital Clínico Dra. Eloísa Díaz · La Florida · <span className={`modo ${api.MODO}`}>{esApi ? "API conectada" : "modo demo (mock)"}</span></p>
        </div>
        <div className="kpis">
          <Kpi n={data.total} t="en espera" />
          <Kpi n={altos} t="prioridad alta o crítica" />
          <Kpi n={data.excluidos.length} t="excluidos (fallecidos)" />
        </div>
      </header>

      <nav className="tabs">
        <button className={vista === "lista" ? "on" : ""} onClick={() => setVista("lista")}>Lista priorizada</button>
        <button className={vista === "box" ? "on" : ""} onClick={() => setVista("box")} disabled={!esApi} title={esApi ? "" : "Requiere API"}>Uso de box</button>
      </nav>

      <section className="controles">
        <label>
          Fecha de corte: <strong>{fecha}</strong>
          <input type="range" min={0} max={fechas.length - 1} value={iFecha} onChange={(e) => setIFecha(+e.target.value)} />
        </label>
        <select value={esp} onChange={(e) => setEsp(e.target.value)}>
          {ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}
        </select>
      </section>

      {error && <div className="error">{error}</div>}
      <AnimatePresence>{aviso && <motion.div className="aviso" initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ opacity: 0 }}>{aviso}</motion.div>}</AnimatePresence>

      {vista === "box" ? <Boxes fecha={fecha} /> : (
        <main>
          <div>
            <ul className="lista">
              <AnimatePresence>
                {lista.map((p) => {
                  const delta = p.posicion_anterior ? p.posicion_anterior - p.posicion : 0;
                  return (
                    <motion.li key={p.id_paciente} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                      transition={{ type: "spring", stiffness: 300, damping: 30 }}
                      className={`fila ${sel === p.id_paciente ? "activa" : ""} ${destacado === p.id_paciente ? "destacado" : ""}`}
                      onClick={() => setSel(p.id_paciente)}>
                      <span className="pos">#{p.posicion}</span>
                      <span className={`badge ${p.categoria}`}>{ETIQUETA[p.categoria]}</span>
                      <span className="nombre">
                        {p.nombre_fantasia} {p.estado_revision !== "pendiente" && <span className="check" title={p.estado_revision}>✔</span>}
                        <small>{p.especialidad} · {p.diagnostico_texto}</small>
                      </span>
                      {p.riesgo_inasistencia ? <span className="flag" title="2+ inasistencias">⚠ inasistencia</span> : <span />}
                      <span className={`delta ${delta > 0 ? "sube" : delta < 0 ? "baja" : ""}`} title="vs. 14 días antes">
                        {delta > 0 ? `▲ ${delta}` : delta < 0 ? `▼ ${-delta}` : "—"}
                      </span>
                      <span className="puntaje">{p.puntaje}</span>
                    </motion.li>
                  );
                })}
              </AnimatePresence>
            </ul>
            {data.excluidos.length > 0 && (
              <details className="excluidos">
                <summary>Excluidos de la lista ({data.excluidos.length})</summary>
                <ul>{data.excluidos.map((e) => <li key={e.id_paciente}>{e.id_paciente} — {e.motivo}{e.fecha_defuncion ? ` (${e.fecha_defuncion})` : ""}</li>)}</ul>
              </details>
            )}
          </div>

          <aside className="panel">
            {!paciente ? <p className="vacio">Selecciona un paciente</p> : (
              <Panel key={paciente.id_paciente} p={paciente} detalle={detalle} fecha={fecha} esApi={esApi}
                onCambio={cargar} onAviso={mostrarAviso} onDestacar={(id) => { setDestacado(id); setTimeout(() => setDestacado(null), 3000); }} />
            )}
          </aside>
        </main>
      )}
    </div>
  );
}

function Panel({ p, detalle, fecha, esApi, onCambio, onAviso, onDestacar }) {
  const [explicacion, setExplicacion] = useState(null);
  const [cargando, setCargando] = useState(null);
  const [ajuste, setAjuste] = useState(null);
  const [tipoEv, setTipoEv] = useState("urgencia");
  useEffect(() => { setExplicacion(null); }, [p.puntaje, fecha]);

  const correr = async (nombre, fn) => {
    setCargando(nombre);
    try { await fn(); } catch (e) { onAviso("Error: " + e.message); } finally { setCargando(null); }
  };

  const simular = () => correr("evento", async () => {
    const r = await api.postEvento({ id_paciente: p.id_paciente, fecha_corte: fecha, fecha_evento: fecha, ...EVENTOS[tipoEv], label: undefined });
    await onCambio();
    onDestacar(p.id_paciente);
    onAviso(`Reevaluado en ${r.reevaluado_en_ms} ms · posición #${r.posicion_antes} → #${r.posicion_despues}`);
  });
  const confirmar = () => correr("rev", async () => { await api.postRevision(p.id_paciente, { accion: "confirmar" }); await onCambio(); onAviso("Prioridad confirmada por el equipo clínico"); });
  const guardarAjuste = () => correr("rev", async () => {
    await api.postRevision(p.id_paciente, { accion: "ajustar", puntaje_ajustado: Number(ajuste.puntaje), motivo: ajuste.motivo });
    setAjuste(null); await onCambio(); onAviso("Ajuste registrado con su motivo");
  });
  const pedirExplicacion = () => correr("ia", async () => setExplicacion(await api.postExplicar(p.id_paciente, fecha)));

  const timeline = detalle ? [
    ...detalle.eventos_clinicos.map((e) => ({ f: e.fecha_evento, t: `🔴 ${e.tipo_evento.replace("_", " ")}: ${e.subtipo}`, g: e.severidad === "grave", nuevo: e.id_evento?.startsWith("EV-DEMO") })),
    ...detalle.mediciones.map((m) => ({ f: m.fecha_medicion, t: `📊 ${m.tipo_medicion} = ${m.valor} ${m.unidad}`, g: m.fuera_de_rango })),
    ...(detalle.citaciones || []).map((c) => ({ f: c.fecha_cita, t: `📅 cita ${c.id_box}: ${c.estado_cita.replace("_", " ")}`, g: c.estado_cita === "no_asistio" })),
  ].sort((a, b) => b.f.localeCompare(a.f)) : [];

  return (
    <>
      <h2>{p.nombre_fantasia}</h2>
      <p>{p.edad} años · {p.sexo} · {p.comuna}</p>
      <p>{p.especialidad} — {p.diagnostico_cie10} {p.diagnostico_texto}</p>
      <p>Prioridad inicial: <b>{p.prioridad_inicial}</b> · Ingreso: {p.fecha_ingreso_lista}</p>
      <p>Estado: <b className={`estado ${p.estado_revision}`}>{p.estado_revision}</b>{p.puntaje_ajustado != null && ` · ajustado a ${p.puntaje_ajustado}`}</p>

      <h3>Por qué tiene {p.puntaje} puntos</h3>
      <ul className="razones">
        {p.razones.map((r, i) => (
          <li key={i}><span>{r.factor === "evento" ? r.valor : `${FACTOR[r.factor] || r.factor}: ${r.valor}`}</span><b className={r.puntos < 0 ? "neg" : ""}>{r.puntos > 0 ? "+" : ""}{r.puntos}</b></li>
        ))}
      </ul>

      {esApi ? (
        <>
          <button className="btn ia" onClick={pedirExplicacion} disabled={cargando}>{cargando === "ia" ? "Generando…" : "✨ Explicar con IA"}</button>
          {explicacion && <div className="explicacion"><p>{explicacion.explicacion_ia}</p><small>Fuente: {explicacion.fuente === "bedrock" ? "Amazon Bedrock" : "plantilla (Bedrock no configurado)"}</small></div>}

          <div className="fila-btns">
            <button className="btn" onClick={confirmar} disabled={cargando}>✔ Confirmar prioridad</button>
            <button className="btn sec" onClick={() => setAjuste(ajuste ? null : { puntaje: p.puntaje, motivo: "" })}>Ajustar</button>
          </div>
          {ajuste && (
            <div className="ajuste">
              <input type="number" min={0} max={100} value={ajuste.puntaje} onChange={(e) => setAjuste({ ...ajuste, puntaje: e.target.value })} />
              <input placeholder="Motivo clínico (obligatorio)" value={ajuste.motivo} onChange={(e) => setAjuste({ ...ajuste, motivo: e.target.value })} />
              <button className="btn" disabled={!ajuste.motivo} onClick={guardarAjuste}>Guardar</button>
            </div>
          )}

          <h3>Simular evento clínico</h3>
          <div className="fila-btns">
            <select value={tipoEv} onChange={(e) => setTipoEv(e.target.value)}>
              {Object.entries(EVENTOS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
            <button className="btn alerta" onClick={simular} disabled={cargando}>{cargando === "evento" ? "Reevaluando…" : "Simular"}</button>
          </div>
        </>
      ) : <p className="vacio">Conecta la API (VITE_API_URL) para confirmar, simular eventos y explicar con IA.</p>}

      <h3>Línea de tiempo</h3>
      <ul className="timeline">
        {timeline.map((x, i) => <li key={i} className={`${x.g ? "alerta" : ""} ${x.nuevo ? "nuevo" : ""}`}><small>{x.f}</small> {x.t}</li>)}
        {detalle && timeline.length === 0 && <li className="vacio">Sin señales registradas</li>}
      </ul>
    </>
  );
}

function Boxes({ fecha }) {
  const [b, setB] = useState(null);
  useEffect(() => { api.getBoxes(fecha).then(setB).catch(() => setB(null)); }, [fecha]);
  if (!b) return <div className="cargando">Cargando box…</div>;
  const r = b.resumen;
  return (
    <div className="boxes">
      <div className="kpis grande">
        <Kpi n={`${r.ocupacion_pct}%`} t="ocupación de box" />
        <Kpi n={r.cupos_libres?.toLocaleString("es-CL")} t={`cupos sin usar (${r.periodo})`} />
        <Kpi n={`${Math.round((r.inasistencias / r.citas) * 100)}%`} t="inasistencias" />
      </div>
      <div className="grid-box">
        {b.especialidades.map((e) => (
          <div key={e.especialidad} className="card-box">
            <h3>{e.especialidad}</h3>
            <div className="barra"><div style={{ width: `${e.ocupacion_pct}%` }} /></div>
            <p>{e.ocupacion_pct}% ocupación · {e.cupos_libres} cupos libres · ~{e.cupos_libres_promedio_dia}/día</p>
            <p>Sobretiempo prom. {e.sobretiempo_promedio_min} min{e.inasistencia_pct != null && ` · inasistencia ${e.inasistencia_pct}%`}</p>
            <h4>Sugeridos para el próximo cupo libre</h4>
            <ul>{e.sugeridos.map((s) => <li key={s.id_paciente}><span className={`badge ${s.categoria}`}>{s.puntaje}</span> {s.nombre_fantasia} <em>{s.accion}</em></li>)}</ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function Kpi({ n, t }) {
  return <div className="kpi"><b>{n}</b><span>{t}</span></div>;
}
