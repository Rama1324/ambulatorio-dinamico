import { useState } from "react";
import * as api from "../api";
import { descargarExcel } from "../excel";
import { Caja, Icono } from "../componentes/comunes";
import { ESPECIALIDADES, ETIQUETA, EVAL_TXT } from "../constantes";
import { fmt, fmtHace } from "../util";

// Pestaña "Alertas pendientes": descompensaciones graves cuya prioridad debe revisar el especialista, y quienes se
// descompensaron sin regla que defina cuánto suben (no se mueven solos: se avisa al especialista).
export function Alertas({ vitales, todosPacientes, fecha, esp, setEsp, onVer, onCambio, onAviso }) {
  const [enviando, setEnviando] = useState(null);
  const todos = vitales.filter((p) => esp === "Todas" || p.especialidad === esp);
  const pendientes = todos.filter((p) => p.contactar_hoy);
  const listos = todos.filter((p) => !p.contactar_hoy);
  const aRevisar = todosPacientes.filter((p) => (esp === "Todas" || p.especialidad === esp) && !p.riesgo_vital &&
    p.estado_clinico === "descompensado" && p.estado_revision !== "confirmado" && p.estado_revision !== "ajustado");

  const registrar = async (p, resultado) => {
    setEnviando(p.id_paciente + resultado);
    try {
      const r = await api.postContacto(p.id_paciente, { resultado, fecha_corte: fecha });
      await onCambio(); onAviso({ titulo: `${p.nombre_fantasia}: ${r.contacto.texto}` });
    } catch (e) { onAviso({ titulo: "No se pudo registrar: " + e.message }); } finally { setEnviando(null); }
  };
  const exportar = () => {
    const fila = (p) => [p.posicion, p.nombre_fantasia, p.id_paciente, p.edad, p.especialidad, p.diagnostico_cie10, p.diagnostico_texto, ETIQUETA[p.categoria]];
    const ev = (p) => p.razones.find((r) => r.factor === "evento")?.valor || "";
    descargarExcel(`alertas_HLF_${fecha}.xlsx`, [
      { nombre: "Descompensaciones graves", filas: [["N°", "Paciente", "ID", "Edad", "Especialidad", "CIE-10", "Diagnóstico", "Prioridad", "Evento", "Fecha del evento",
        "Días desde el evento", "Evaluación", "Cerrada por", "Responsable", "Última llamada", "Intentos sin respuesta"],
        ...todos.map((p) => [...fila(p), ev(p), fmt(p.evaluacion?.fecha_evento), p.evaluacion?.dias_desde_evento ?? "", EVAL_TXT[p.evaluacion?.estado] || "",
          p.evaluacion?.cierre?.texto || "", p.evaluacion?.cierre?.responsable || "", p.contacto?.texto || "", p.contacto?.intentos_sin_respuesta || ""])] },
      { nombre: "Avisar al especialista", filas: [["N°", "Paciente", "ID", "Edad", "Especialidad", "CIE-10", "Diagnóstico", "Prioridad", "Evento"],
        ...aRevisar.map((p) => [...fila(p), ev(p)])] },
      { nombre: "Información", filas: [["Dato", "Valor"], ["Fecha", fmt(fecha)], ["Especialidad", esp], ["Generado por", api.getUsuario() || "(sin nombre)"],
        ["Datos", "Sintéticos de demostración: no son pacientes reales"]] }]);
  };
  // Agrupa por especialidad (la que tiene más pacientes primero): cada especialista ve lo suyo
  const agrupar = (xs) => Object.entries(xs.reduce((m, p) => ((m[p.especialidad] ||= []).push(p), m), {})).sort((x, y) => y[1].length - x[1].length);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2 text-[14px]">
        <span className="text-on-surface-variant">Especialidad:</span>
        <select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest">{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select>
        <span className="text-[13px] text-on-surface-variant">{esp === "Todas" ? "Vista de coordinación: todo el hospital, agrupado por especialidad." : `Solo ${esp}.`}</span>
        <button onClick={exportar} className="ml-auto h-9 px-3 rounded border border-outline-variant bg-surface-container-lowest font-semibold flex items-center gap-1"><Icono n="download" className="text-[18px]" />Exportar a Excel</button>
      </div>
      <section className="rounded border border-primary/30 bg-primary/5 p-4 text-[15px] leading-relaxed">
        <b>Resumen del {fmt(fecha)}{esp !== "Todas" ? ` · ${esp}` : ""}:</b>{" "}
        {todos.length ? <>Hay <b>{todos.length} pacientes con descompensación grave</b>: <b className="text-hlf">{todos.length - pendientes.length} con la prioridad ya revisada</b>
          {pendientes.length > 0 && <>, <b className="text-error">{pendientes.length} esperan revisión de su prioridad</b></>}.
        </> : "No hay descompensaciones graves pendientes de revisión."}
      </section>

      <div className="grid gap-5 lg:grid-cols-12 items-start">
        <Caja titulo={`Descompensaciones graves: revisar prioridad (${pendientes.length})`} className="lg:col-span-7 border-l-4 border-l-error">
          <p className="text-[13px] text-on-surface-variant mb-3">Tuvieron un evento grave después de la interconsulta y no hay registro posterior de estabilización ni de evaluación. La lista ya se recalculó al llegar el evento; falta que el especialista revise su prioridad. Llamar o citar no cierra la alerta.</p>
          {todos.length === 0 && <p className="text-on-surface-variant">Nadie pendiente{esp !== "Todas" && ` en ${esp}`}.</p>}
          {agrupar(pendientes).map(([nombreEsp, grupo]) => (
            <div key={nombreEsp} className="mb-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2 bg-surface-container-low rounded px-2 py-1.5 text-[14px]">
                <b>{nombreEsp} · {grupo.length} por revisar</b>
              </div>
              <ul className="divide-y divide-outline-variant/60">
                {grupo.map((p) => (
                  <li key={p.id_paciente} className="py-2.5 text-[14px]">
                    <button onClick={() => onVer(p.id_paciente)} className="text-left hover:underline">
                      <span className="text-on-surface-variant text-[13px] mr-1">N° {p.posicion}</span>
                      <b>{p.nombre_fantasia}</b> <span className="text-on-surface-variant text-[13px]">· {p.edad} años · {p.especialidad} · {p.diagnostico_texto}</span>
                    </button>
                    {p.evaluacion && <div className="text-[12px] font-semibold text-on-surface-variant">
                      Evento grave del {fmtHace(p.evaluacion.fecha_evento, fecha)} · en el sistema desde el {fmt(p.evaluacion.llego_al_sistema)} ({p.evaluacion.dias_en_revision} día{p.evaluacion.dias_en_revision !== 1 ? "s" : ""})</div>}
                    {p.contacto?.intentos_sin_respuesta > 0 && <div className="text-[12px] text-ambar font-semibold">{p.contacto.intentos_sin_respuesta} intento{p.contacto.intentos_sin_respuesta > 1 ? "s" : ""} sin respuesta{p.contacto.intentos_sin_respuesta >= 3 ? ": evaluar visita domiciliaria o derivación" : ""}</div>}
                    {p.contacto?.resultado === "contactado" && <div className="text-[12px] text-on-surface-variant">Informado por teléfono: falta la decisión médica.</div>}
                    <div className="flex flex-wrap items-center gap-1 mt-1.5 text-[12px]">
                      <span className="text-on-surface-variant mr-1">Llamada:</span>
                      {[["citado", "Citado"], ["derivado_urgencia", "Derivado a urgencia"], ["contactado", "Informado"], ["no_contesta", "No contesta"]].map(([k, t]) => (
                        <button key={k} disabled={enviando} onClick={() => registrar(p, k)}
                          className={`px-2 py-1 rounded border font-semibold disabled:opacity-40 ${k === "derivado_urgencia" ? "border-error text-error" : k === "citado" ? "border-primary text-primary" : "border-outline-variant text-on-surface-variant"}`}>
                          {enviando === p.id_paciente + k ? "…" : t}</button>
                      ))}
                      <button onClick={() => onVer(p.id_paciente)} className="px-2 py-1 rounded bg-primary text-on-primary font-semibold">Decisión médica →</button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {listos.length > 0 && (
            <details className="mt-2 text-[13px]">
              <summary className="cursor-pointer text-on-surface-variant">Prioridad ya revisada ({listos.length})</summary>
              <ul className="mt-1 space-y-1">
                {listos.map((p) => <li key={p.id_paciente}><button onClick={() => onVer(p.id_paciente)} className="hover:underline">{p.nombre_fantasia}</button> · <span className="text-hlf">{p.evaluacion?.cierre?.texto}{p.evaluacion?.cierre?.responsable && ` · ${p.evaluacion.cierre.responsable}`}</span></li>)}
              </ul>
            </details>
          )}
        </Caja>

        <Caja titulo={`Avisar al especialista (${aRevisar.length})`} className="lg:col-span-5 border-l-4 border-l-ambar">
          <p className="text-[13px] text-on-surface-variant mb-2">Se descompensaron después de la interconsulta, pero la tabla del HLF no define cuánto sube su prioridad. No se les cambia solo: el especialista debe revisarlos y confirmar o cambiar su prioridad.</p>
          {aRevisar.length === 0 && <p className="text-[13px] text-on-surface-variant">Nadie pendiente de revisión{esp !== "Todas" && ` en ${esp}`}.</p>}
          {agrupar(aRevisar).map(([nombreEsp, grupo]) => (
            <details key={nombreEsp} open={esp !== "Todas"} className="border-t border-outline-variant/60">
              <summary className="cursor-pointer py-1.5 text-[14px] font-semibold">{nombreEsp} · {grupo.length} para revisar</summary>
              <ul className="divide-y divide-outline-variant/60 pl-3">
                {grupo.map((p) => {
                  const ev = p.razones.find((r) => r.factor === "evento");
                  return (
                    <li key={p.id_paciente} className="py-2 text-[14px]">
                      <button onClick={() => onVer(p.id_paciente)} className="text-left hover:underline">
                        <b>{p.nombre_fantasia}</b> <span className="text-on-surface-variant text-[13px]">· {p.diagnostico_texto} · prioridad {p.categoria}</span>
                      </button>
                      {ev && <div className="text-[13px] text-ambar">{ev.valor}</div>}
                    </li>
                  );
                })}
              </ul>
            </details>
          ))}
        </Caja>
      </div>
    </div>
  );
}
