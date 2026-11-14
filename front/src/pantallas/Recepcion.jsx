// Recepción de datos: por dónde llegan los datos (archivo, API para sistemas, carpeta de carga automática, informes),
// la carga de planillas de siempre y "Lo recibido": los últimos lotes (GET /ingesta/lotes) con sus conteos.
import { useCallback, useEffect, useState } from "react";
import * as api from "../api";
import { Caja, Icono } from "../componentes/comunes";
import { CANAL, fmtHora } from "../componentes/Decision";
import { plural } from "../constantes";
import { CargarDatos } from "./CargarDatos";

const VIAS = [
  ["upload_file", "Archivo desde esta pantalla", "Planillas Excel o CSV del hospital (urgencias, laboratorio, lista de espera). Se revisan antes de guardar."],
  ["api", "API para los sistemas del hospital", "El sistema de urgencia, el laboratorio o la ficha clínica envían los eventos solos, apenas ocurren."],
  ["folder_open", "Carpeta de carga automática", "Un archivo dejado en la carpeta de entrada (Amazon S3) se procesa solo; el resultado queda en la carpeta de procesados."],
  ["photo_camera", "Informes y fotos desde la ficha", "En la ficha del paciente → Registrar: se sube la foto o el PDF de un informe y la IA lo lee citando la frase."],
];

function ejemploApi() {
  const base = api.API_URL || window.location.origin;
  return `curl -X POST "${base}/ingesta/eventos" \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: urgencia-2026-10-13-001" \\
  -d '{
    "origen": "sistema-urgencia",
    "eventos": [{
      "id_evento": "URG-2026-0001",
      "id_paciente": "PAC-HLF-00084",
      "fecha_evento": "2026-10-13",
      "tipo_evento": "visita_urgencia",
      "subtipo": "triage ESI 2",
      "motivo": "disnea y tos, exacerbación"
    }]
  }'`;
}

export function Recepcion({ onListo, onVerLote }) {
  const [lotes, setLotes] = useState(null);
  const [error, setError] = useState(null);
  const [copiado, setCopiado] = useState(false);
  const cargarLotes = useCallback(async () => {
    try { setError(null); setLotes((await api.getLotes(30)).lotes || []); } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { cargarLotes(); }, [cargarLotes]);
  const copiar = async () => {
    try { await navigator.clipboard.writeText(ejemploApi()); setCopiado(true); setTimeout(() => setCopiado(false), 2000); } catch { /* sin portapapeles */ }
  };

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-[22px] font-bold">Recepción de datos</h1>
        <p className="text-[15px] text-on-surface-variant">Todo lo que llega pasa por el mismo camino: se valida, no se duplica si llega dos veces, no se guarda a
          quien no está en la lista, y cada paciente con información clínica nueva queda con una decisión del sistema para revisar.</p>
      </div>

      <section aria-label="Vías de llegada" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {VIAS.map(([ic, t, d]) => <article key={t} className="bg-surface-container-lowest border border-outline-variant rounded p-3 text-[14px]">
          <div className="font-semibold flex items-center gap-1.5"><Icono n={ic} className="text-[20px] text-primary" />{t}</div>
          <p className="text-[13px] text-on-surface-variant mt-1">{d}</p>
        </article>)}
      </section>

      <details className="bg-surface-container-lowest border border-outline-variant rounded">
        <summary className="px-4 py-2.5 cursor-pointer font-semibold text-[15px]">Ejemplo de llamada a la API (para el equipo de informática)</summary>
        <div className="px-4 pb-3 text-[13px] flex flex-col gap-2">
          <p className="text-on-surface-variant">Hasta 2.000 filas por llamada. La cabecera <code>Idempotency-Key</code> es opcional: si la misma llamada se repite, no se registra dos
            veces. Si el evento trae su propio <code>id_evento</code>, también se usa para no duplicar.{api.auth.usuarioSesion?.() ? " Con inicio de sesión, agregue la cabecera Authorization con el token de la integración." : ""}</p>
          <pre className="bg-surface-container-low rounded p-3 overflow-x-auto text-[12px] leading-snug"><code>{ejemploApi()}</code></pre>
          <button onClick={copiar} className="self-start px-3 py-1.5 rounded border border-primary text-primary font-semibold flex items-center gap-1">
            <Icono n={copiado ? "check" : "content_copy"} className="text-[16px]" />{copiado ? "Copiado" : "Copiar"}</button>
        </div>
      </details>

      <CargarDatos onListo={async (r) => { await onListo(r); await cargarLotes(); }} />

      <Caja titulo="Lo recibido" accion={<button onClick={cargarLotes} className="text-[13px] text-primary font-semibold flex items-center gap-1"><Icono n="refresh" className="text-[16px]" />Actualizar</button>}>
        {error && <p className="text-error text-[14px] flex items-center gap-2"><Icono n="cloud_off" />No se pudieron cargar los lotes: {error}</p>}
        {!error && !lotes && <p className="text-on-surface-variant text-[14px]">Cargando…</p>}
        {lotes && lotes.length === 0 && <p className="text-on-surface-variant text-[14px]">Todavía no ha llegado nada en esta sesión. Cada archivo, llamada de la API, archivo en la
          carpeta de carga o evento registrado en la app aparece aquí como un lote.</p>}
        {lotes && lotes.length > 0 && <ul className="flex flex-col gap-2">{lotes.map((l) => <Lote key={l.id_lote} l={l} onVerLote={onVerLote} />)}</ul>}
      </Caja>
    </div>
  );
}

function Lote({ l, onVerLote }) {
  const [det, setDet] = useState(null);
  const [abierto, setAbierto] = useState(false);
  const abrir = async () => {
    setAbierto(!abierto);
    if (!det) try { setDet(await api.getLote(l.id_lote)); } catch (e) { setDet({ error: e.message }); }
  };
  const n = (v) => (Array.isArray(v) ? v.length : v ?? 0);
  const Dato = ({ v, t, tono }) => <div className="rounded bg-surface-container-low px-2 py-1 text-center min-w-[84px]">
    <div className={`text-[17px] font-semibold ${tono || ""}`}>{v}</div><div className="text-[11px] text-on-surface-variant leading-tight">{t}</div></div>;
  return (
    <li className="rounded border border-outline-variant p-3 text-[14px]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-semibold">{fmtHora(l.fecha)} · {CANAL[l.canal] || l.canal}</div>
          <div className="text-[12px] text-on-surface-variant">{[l.origen && l.origen !== l.canal && `sistema: ${l.origen}`, l.archivo && `archivo: ${l.archivo}`, l.usuario && `por ${l.usuario}`, l.id_lote,
            l.estado && l.estado !== "procesado" && `estado: ${l.estado}`, l.evaluacion === "en_cola" && "evaluación en cola"].filter(Boolean).join(" · ")}</div>
        </div>
        {n(l.dictamenes) > 0 ? <button onClick={() => onVerLote(l.id_lote)} className="px-3 py-1.5 rounded bg-primary text-on-primary font-semibold text-[13px] flex items-center gap-1">
          <Icono n="fact_check" className="text-[16px]" />Ver sus {plural(n(l.dictamenes), "decisión", "decisiones")}</button>
          : <span className="text-[12px] text-on-surface-variant">Sin decisiones nuevas</span>}
      </div>
      <div className="flex flex-wrap gap-2 mt-2">
        <Dato v={l.recibidos ?? 0} t="registros recibidos" />
        <Dato v={l.registrados ?? 0} t="entraron" tono="text-hlf" />
        <Dato v={l.duplicados ?? 0} t="ya estaban (repetidos)" />
        <Dato v={l.n_rechazados ?? 0} t="rechazados" tono={l.n_rechazados ? "text-error" : ""} />
        <Dato v={l.fuera_de_lista ?? 0} t="personas fuera de la lista" />
        <Dato v={n(l.pacientes_afectados)} t="pacientes afectados" />
      </div>
      <button onClick={abrir} aria-expanded={abierto} className="mt-2 text-[13px] text-primary font-semibold flex items-center gap-1">
        <Icono n={abierto ? "expand_less" : "expand_more"} className="text-[18px]" />{abierto ? "Ocultar detalle" : "Ver detalle y rechazos"}</button>
      {abierto && (!det ? <p className="text-[13px] text-on-surface-variant">Cargando…</p> : det.error ? <p className="text-[13px] text-error">{det.error}</p> : <div className="mt-1 text-[13px] flex flex-col gap-2">
        {det.por_tabla && <table className="w-full max-w-xl"><thead><tr className="text-left text-on-surface-variant"><th>Tabla</th><th className="text-right">Recibidos</th><th className="text-right">Entraron</th>
          <th className="text-right">Repetidos</th><th className="text-right">Rechazados</th><th className="text-right">Fuera de lista</th></tr></thead>
          <tbody>{Object.entries(det.por_tabla).filter(([, x]) => x.recibidos).map(([t, x]) => <tr key={t} className="border-t border-outline-variant/50">
            <td className="py-0.5">{t.replace("_", " ")}</td><td className="text-right">{x.recibidos}</td><td className="text-right">{x.registrados}</td><td className="text-right">{x.duplicados}</td>
            <td className="text-right">{x.rechazados}</td><td className="text-right">{x.fuera_de_lista}</td></tr>)}</tbody></table>}
        {det.rechazados?.length > 0 ? <div><b>Por qué se rechazaron:</b><ul className="list-disc pl-5 text-error">{det.rechazados.map((x, i) =>
          <li key={i}>{x.tabla}, fila {x.indice}: {x.motivo}</li>)}</ul></div> : <p className="text-on-surface-variant">Ningún registro rechazado.</p>}
        {det.cierre?.procesado_en_ms != null && <p className="text-on-surface-variant">Procesado en {det.cierre.procesado_en_ms} ms{det.cierre.errores?.length ? ` · ${det.cierre.errores.length} errores al evaluar` : ""}.</p>}
      </div>)}
    </li>
  );
}
