import { useRef, useState } from "react";
import * as api from "../api";
import { Caja, Icono } from "../components/ui";

const leerBase64 = (f) => new Promise((ok, mal) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result).split(",")[1]);
  r.onerror = () => mal(new Error(`No se pudo leer ${f.name}`));
  r.readAsDataURL(f);
});

const TABLAS_IMPORT = [
  ["pacientes", "Pacientes", "id_paciente, edad, sexo"],
  ["lista_espera", "Lista de espera", "id_paciente, diagnostico_cie10, prioridad_inicial, fecha_ingreso_lista"],
  ["eventos_clinicos", "Eventos clínicos", "id_paciente, fecha_evento, tipo_evento"],
  ["mediciones", "Mediciones", "id_paciente, fecha_medicion, tipo_medicion, valor"],
  ["citaciones", "Citaciones", "id_paciente, fecha_cita, estado_cita"],
  ["agenda_box", "Agenda de box", "id_box, fecha, especialidad, capacidad_cupos"],
];

export function CargarDatos({ esApi, onListo }) {
  const [archivos, setArchivos] = useState([]);
  const [rev, setRev] = useState(null);
  const [estado, setEstado] = useState(null);
  const [error, setError] = useState(null);
  const [arrastrando, setArrastrando] = useState(false);
  const input = useRef(null);

  const agregar = (lista) => {
    const nuevos = [...lista].filter((f) => /\.(xlsx|xlsm|csv|txt)$/i.test(f.name));
    if (nuevos.length < lista.length) setError("Solo se aceptan archivos .xlsx o .csv (en Excel: Guardar como → Libro de Excel o CSV).");
    else setError(null);
    setArchivos((a) => [...a.filter((x) => !nuevos.some((n) => n.name === x.name)), ...nuevos]);
    setRev(null);
  };
  const enviar = async (confirmar) => {
    setEstado(confirmar ? "cargando" : "revisando"); setError(null);
    try {
      const datos = await Promise.all(archivos.map(async (f) => ({ nombre: f.name, contenido_base64: await leerBase64(f) })));
      const r = await api.postImportar(datos, confirmar);
      setRev(r);
      if (confirmar) { setArchivos([]); onListo(r); }
    } catch (e) { setError(e.message); } finally { setEstado(null); }
  };
  if (!esApi) return <Caja><p className="text-on-surface-variant">Cargar datos requiere conexión al servidor.</p></Caja>;
  const validas = rev?.informe.reduce((s, i) => s + (i.validas || 0), 0) || 0;

  return (
    <div className="grid gap-5 lg:grid-cols-12 items-start">
      <div className="lg:col-span-8 flex flex-col gap-4">
        <Caja titulo="Cargar planillas del hospital">
          <div onDragOver={(e) => { e.preventDefault(); setArrastrando(true); }} onDragLeave={() => setArrastrando(false)}
            onDrop={(e) => { e.preventDefault(); setArrastrando(false); agregar(e.dataTransfer.files); }}
            onClick={() => input.current.click()}
            className={`cursor-pointer rounded border-2 border-dashed p-8 text-center ${arrastrando ? "border-primary bg-primary/5" : "border-outline-variant hover:bg-surface-container-low"}`}>
            <Icono n="upload_file" className="text-[40px] text-primary" />
            <p className="font-semibold mt-1">Arrastre aquí archivos Excel (.xlsx) o CSV, o haga clic para elegirlos</p>
            <p className="text-[14px] text-on-surface-variant">Puede subir varios a la vez. Cada hoja de un Excel se lee como una tabla distinta.</p>
            <input ref={input} type="file" multiple accept=".xlsx,.xlsm,.csv,.txt" hidden onChange={(e) => { agregar(e.target.files); e.target.value = ""; }} />
          </div>
          {archivos.length > 0 && (
            <ul className="mt-3 divide-y divide-outline-variant/60 text-[14px]">
              {archivos.map((f) => (
                <li key={f.name} className="py-1.5 flex items-center justify-between">
                  <span className="flex items-center gap-2"><Icono n={f.name.toLowerCase().endsWith("csv") ? "description" : "table_view"} className="text-[18px] text-hlf" />{f.name}<span className="text-[13px] text-on-surface-variant">{Math.round(f.size / 1024)} KB</span></span>
                  <button onClick={() => { setArchivos(archivos.filter((x) => x !== f)); setRev(null); }} className="text-on-surface-variant"><Icono n="close" className="text-[18px]" /></button>
                </li>
              ))}
            </ul>
          )}
          {error && <p className="mt-2 text-error text-[14px]">{error}</p>}
          <div className="flex gap-2 mt-3">
            <button disabled={!archivos.length || estado} onClick={() => enviar(false)} className="flex-1 py-2 rounded border border-primary text-primary font-semibold disabled:opacity-40">{estado === "revisando" ? "Revisando…" : "1. Revisar archivos"}</button>
            <button disabled={!rev || rev.cargado || !validas || estado} onClick={() => enviar(true)} className="flex-1 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{estado === "cargando" ? "Cargando…" : "2. Cargar al sistema"}</button>
          </div>
          <p className="text-[13px] text-on-surface-variant mt-2">Nada se guarda hasta el paso 2. Los pacientes que ya existen se actualizan y los eventos repetidos no se duplican.</p>
        </Caja>

        {rev && (
          <Caja titulo={rev.cargado ? "Carga completada" : "Revisión de los archivos"}>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-4 text-center">
              {[["pacientes_nuevos", "Pacientes nuevos"], ["pacientes_actualizados", "Actualizados"], ["eventos", "Eventos"],
                ["mediciones", "Mediciones"], ["citaciones", "Citaciones"], ["bloques_agenda", "Bloques de box"]].map(([k, t]) => (
                <div key={k} className="rounded bg-surface-container-low p-2"><div className="text-[20px] font-semibold text-primary-container">{rev.resumen[k]}</div><div className="text-[13px] text-on-surface-variant">{t}</div></div>
              ))}
            </div>
            {rev.avisos.length > 0 && <div className="mb-3 rounded bg-ambar-container/50 p-2 text-[14px]">{rev.avisos.map((a, i) => <div key={i}>⚠ {a}</div>)}</div>}
            <div className="space-y-3">
              {rev.informe.map((i, k) => (
                <div key={k} className="rounded border border-outline-variant p-3 text-[14px]">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold">{i.archivo}{i.hoja && i.hoja !== "hoja" ? ` · hoja "${i.hoja}"` : ""}</span>
                    {i.tabla ? <span className="rounded bg-hlf-claro text-hlf px-2 py-0.5 text-[14px] font-semibold">Detectado: {i.nombre_tabla}</span>
                      : <span className="rounded bg-error-container text-on-error-container px-2 py-0.5 text-[14px] font-semibold">No reconocido</span>}
                  </div>
                  {i.error && <p className="text-error text-[14px] mt-1">{i.error}</p>}
                  {i.tabla && <>
                    <div className="mt-1 flex items-center gap-2">
                      <div className="flex-1 h-2 rounded bg-error-container overflow-hidden"><div className="h-full bg-hlf" style={{ width: `${i.filas ? (i.validas / i.filas) * 100 : 0}%` }} /></div>
                      <span className="text-[14px] whitespace-nowrap"><b>{i.validas}</b> de {i.filas} filas correctas</span>
                    </div>
                    <details className="mt-2"><summary className="cursor-pointer text-[14px] text-primary">Cómo se leyeron las columnas</summary>
                      <div className="flex flex-wrap gap-1 mt-1">{i.columnas.map((c) => <span key={c.campo} className="rounded bg-surface-container-low px-1.5 py-0.5 text-[13px]">{c.original} → <b>{c.campo}</b></span>)}</div>
                      {i.ignoradas.length > 0 && <p className="text-[13px] text-on-surface-variant mt-1">No usadas: {i.ignoradas.join(", ")}</p>}
                    </details>
                    {i.errores.length > 0 && (
                      <table className="w-full mt-2 text-[14px]">
                        <thead><tr className="text-left text-on-surface-variant"><th className="w-16">Fila</th><th>Problema</th></tr></thead>
                        <tbody>{i.errores.map((e) => <tr key={e.fila} className="border-t border-outline-variant/50"><td className="py-0.5">{e.fila}</td><td className="text-error">{e.motivo}</td></tr>)}</tbody>
                      </table>
                    )}
                    {i.n_errores > i.errores.length && <p className="text-[13px] text-on-surface-variant">… y {i.n_errores - i.errores.length} filas más con problemas.</p>}
                  </>}
                </div>
              ))}
            </div>
          </Caja>
        )}
      </div>

      <div className="lg:col-span-4 flex flex-col gap-4">
        <Caja titulo="Plantillas">
          <p className="text-[14px] text-on-surface-variant mb-2">Columnas mínimas de cada tabla. Los nombres pueden variar (p. ej. "RUT", "Fecha ingreso", "CIE10", "Prioridad"): el sistema los reconoce.</p>
          <ul className="divide-y divide-outline-variant/60 text-[14px]">
            {TABLAS_IMPORT.map(([t, n, req]) => (
              <li key={t} className="py-2">
                <div className="flex items-center justify-between"><span className="font-semibold">{n}</span>
                  <a href={api.urlPlantilla(t)} className="text-primary text-[14px] font-semibold flex items-center gap-0.5"><Icono n="download" className="text-[16px]" />Plantilla</a></div>
                <div className="text-[13px] text-on-surface-variant">{req}</div>
              </li>
            ))}
          </ul>
        </Caja>
        <Caja titulo="Qué se convierte solo">
          <ul className="list-disc pl-5 text-[14px] space-y-1">
            <li>Fechas en dd-mm-aaaa, dd/mm/aaaa, aaaa-mm-dd o fecha interna de Excel.</li>
            <li>Prioridad "ALTA", "Alta", "1", "Inmediata" → alta (igual media y baja).</li>
            <li>Sexo "Femenino", "Mujer", "F" → F. Sí/No, 1/0, X → verdadero/falso.</li>
            <li>CIE-10 "I50.9" → I50; la especialidad y el diagnóstico se completan desde el catálogo.</li>
            <li>Si una medición no trae "fuera de rango", se calcula con los rangos del diccionario de datos.</li>
            <li>CSV separado por coma, punto y coma o tabulación; UTF-8 o Latin-1.</li>
          </ul>
        </Caja>
      </div>
    </div>
  );
}
