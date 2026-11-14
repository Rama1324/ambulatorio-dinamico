// "Fuentes y versiones" (GET /conocimiento) y el buscador "¿qué aplica el sistema para este diagnóstico?"
// (GET /conocimiento/diagnostico/{cie10}). Cada decisión del sistema guarda qué versión de cada fuente usó.
import { useEffect, useMemo, useState } from "react";
import * as api from "../api";
import { Caja, Icono, Prioridad } from "../componentes/comunes";
import { fmt } from "../util";

const TIPO_FUENTE = { tabla_oficial: "Tabla oficial", norma: "Norma MINSAL", garantia_ges: "Garantía GES", criterios_clinicos: "Criterios clínicos",
  combinaciones: "Combinaciones de riesgo", evidencia: "Evidencia publicada", rubrica: "Rúbrica de la IA", motor: "Código del sistema", registro: "Registro", capa_local: "Criterios locales" };
const ESTADO_SI = { a_validar_por_medico: "a validar por un médico", con_fila: "con fila en la tabla", sin_fila: "sin fila en la tabla" };

export function FuentesVersiones() {
  const [k, setK] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.getConocimiento().then(setK).catch((e) => setError(e.message)); }, []);
  if (error) return <Caja titulo="Fuentes y versiones"><p className="text-error text-[14px]">No se pudo cargar el manifiesto de fuentes: {error}</p></Caja>;
  if (!k) return <Caja titulo="Fuentes y versiones"><p className="text-on-surface-variant text-[14px]">Cargando…</p></Caja>;
  const p = k.paquete || {};
  return (
    <Caja titulo="Fuentes y versiones">
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-[14px] mb-3">
        <span>Paquete vigente: <b>{p.etiqueta}</b> <span className="font-mono text-[12px] text-on-surface-variant">{p.huella}</span></span>
        <span>Criterios locales: <b>versión {k.capa_local?.version ?? 0}</b></span>
        <span>Código del sistema: <span className="font-mono text-[12px]">{k.motor?.huella}</span> ({k.motor?.archivos?.length ?? p.motor?.archivos} archivos)</span>
        <span className={k.integridad?.integro ? "text-verde font-semibold" : "text-error font-semibold"}>
          <Icono n={k.integridad?.integro ? "verified" : "gpp_bad"} className="text-[18px]" /> {k.integridad?.integro ? "Íntegro: los archivos coinciden con su huella" : "Hay archivos que no coinciden con su huella"}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-[13px]">
          <thead><tr className="text-left text-on-surface-variant border-b border-outline-variant"><th className="py-1.5 pr-2">Fuente</th><th className="pr-2">Tipo</th><th className="pr-2">Versión</th>
            <th className="pr-2">Verificación</th><th className="pr-2">Huella</th><th>Fecha</th></tr></thead>
          <tbody>{(k.fuentes || []).map((f) => <tr key={f.id} className="border-b border-outline-variant/50 align-top">
            <td className="py-1.5 pr-2">{f.origen_url ? <a href={f.origen_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">{f.titulo}</a> : f.titulo}</td>
            <td className="pr-2 whitespace-nowrap">{TIPO_FUENTE[f.tipo] || f.tipo}</td>
            <td className="pr-2 font-semibold whitespace-nowrap">{f.version || "—"}</td>
            <td className={`pr-2 ${/verificado en la fuente/.test(f.estado || "") ? "text-verde" : "text-ambar"}`} title={f.estado_detalle || undefined}>{f.estado || "—"}</td>
            <td className="pr-2 font-mono text-[11px]">{f.sha256 ? f.sha256.slice(0, 12) : "—"}</td>
            <td className="whitespace-nowrap">{fmt(f.fecha) || "—"}</td></tr>)}</tbody>
        </table>
      </div>
      {k.avisos?.length > 0 && <div className="mt-2 rounded bg-ambar-container/50 text-ambar p-2 text-[12px]"><b>Avisos del manifiesto:</b> {k.avisos.join(" · ")}</div>}
      <p className="text-[12px] text-on-surface-variant mt-2">La huella identifica el contenido exacto del archivo: si cambia una coma, cambia la huella. Cada decisión del sistema guarda la versión y la huella de lo que usó.</p>
      <BuscadorDiagnostico />
    </Caja>
  );
}

function BuscadorDiagnostico() {
  const [dx, setDx] = useState([]);
  const [cie, setCie] = useState("");
  const [r, setR] = useState(null);
  const [error, setError] = useState(null);
  const [cargando, setCargando] = useState(false);
  useEffect(() => { api.catalogoCache().then((c) => setDx(c.diagnosticos || [])).catch(() => {}); }, []);
  const grupos = useMemo(() => {
    const g = {};
    for (const d of dx) (g[d.especialidad] ||= []).push(d);
    return Object.entries(g);
  }, [dx]);
  useEffect(() => {
    if (!cie) return;
    let vivo = true;
    setCargando(true); setError(null);
    api.getConocimientoDx(cie).then((x) => vivo && setR(x)).catch((e) => vivo && setError(e.message)).finally(() => vivo && setCargando(false));
    return () => { vivo = false; };
  }, [cie]);
  return (
    <div className="mt-4 border-t border-outline-variant pt-3 text-[14px]">
      <h3 className="font-semibold text-[15px]">¿Qué aplica el sistema para este diagnóstico?</h3>
      <select value={cie} onChange={(e) => setCie(e.target.value)} aria-label="Diagnóstico" className="mt-1 h-10 w-full max-w-xl px-2 border border-outline-variant rounded bg-surface-container-lowest">
        <option value="">Elija un diagnóstico…</option>
        {grupos.map(([esp, ds]) => <optgroup key={esp} label={esp}>{ds.map((d) => <option key={d.diagnostico_cie10} value={d.diagnostico_cie10}>
          {d.diagnostico_cie10.startsWith("HLF-") ? d.diagnostico_texto : `${d.diagnostico_cie10} · ${d.diagnostico_texto}`}</option>)}</optgroup>)}
      </select>
      {cargando && <p className="text-on-surface-variant mt-2">Buscando…</p>}
      {error && <p className="text-error mt-2">No se pudo consultar: {error}</p>}
      {r && !cargando && !error && <ResultadoDx r={r} />}
    </div>
  );
}

const Fuente = ({ f }) => f ? <span className="text-[12px] text-on-surface-variant italic"> · fuente: {f.id}{f.version ? ` (${f.version})` : ""}</span> : null;

function ResultadoDx({ r }) {
  const t = r.tabla || {}, s = r.si_se_descompensa || {}, co = r.criterios_oficiales, cl = r.criterios_locales || [];
  const Bloque = ({ titulo, children }) => <section className="py-2 border-b border-outline-variant/50"><h4 className="text-[13px] font-semibold text-on-surface-variant">{titulo}</h4>{children}</section>;
  return (
    <div className="mt-2 rounded border border-outline-variant p-3">
      <div className="text-[16px] font-semibold">{r.diagnostico} <span className="text-[13px] font-normal text-on-surface-variant">· {r.codigo} · {r.especialidad}</span></div>
      <Bloque titulo="Tabla del HLF">
        {t.fila ? <p>{t.fila.texto} → <Prioridad cat={t.fila.prioridad} /> (pág. {t.fila.pagina})<Fuente f={t.fuente} /></p>
          : t.misma_enfermedad?.length ? <ul className="list-disc pl-5">{t.misma_enfermedad.map((x) => <li key={x.codigo}>{x.texto}: <Prioridad cat={x.prioridad} /> (pág. {x.pagina})</li>)}</ul>
            : <p className="text-on-surface-variant">Sin fila propia.</p>}
      </Bloque>
      <Bloque titulo="Si se descompensa">
        {s.fila ? <p>Sube a la fila «{s.fila}» → <Prioridad cat={s.prioridad} />{s.pagina ? ` (pág. ${s.pagina})` : ""}<Fuente f={s.fuente} />
          {s.equivalencia_a_validar && <span className="block text-[13px] text-ambar">Equivalencia a validar con los especialistas{s.equivalencia ? `: ${s.equivalencia}` : ""}.</span>}</p>
          : <p>No tiene fila de «descompensado»: mantiene su prioridad y queda para revisión clínica{s.estado ? ` (${ESTADO_SI[s.estado] || s.estado.replaceAll("_", " ")})` : ""}.<Fuente f={s.fuente} /></p>}
        {s.detalle && <p className="text-[13px] text-on-surface-variant">{s.detalle}</p>}
      </Bloque>
      {co?.criterios?.length > 0 && <Bloque titulo={`Criterios clínicos oficiales (${co.enfermedad})`}>
        <ul className="list-disc pl-5">{co.criterios.map((c) => <li key={c.codigo}><Prioridad cat={c.nivel} /> {c.texto}</li>)}</ul>
        {co.urgencias?.length > 0 && <ul className="list-disc pl-5 text-error mt-1">{co.urgencias.map((u) => <li key={u.codigo}>Derivar hoy: {u.texto}</li>)}</ul>}
        <p className="text-[12px] text-on-surface-variant">{co.url && <a href={co.url} target="_blank" rel="noreferrer" className="text-primary underline">Ver criterio original</a>}<Fuente f={co.fuente} /></p>
      </Bloque>}
      {cl.length > 0 && <Bloque titulo="Criterios locales del HLF">
        <ul className="list-disc pl-5">{cl.map((c) => <li key={c.id}><b>{c.id} v{c.version}</b> ({c.estado}): «{c.texto}»{c.resuelto_por ? ` · ${c.estado === "vigente" ? "aprobado" : c.estado} por ${c.resuelto_por}` : ""}</li>)}</ul>
      </Bloque>}
      {r.ges && <Bloque titulo="Garantía GES"><p>N° {r.ges.problema} · {r.ges.nombre}: especialista dentro de <b>{r.ges.plazo_dias} días</b>.<Fuente f={r.ges.fuente} /></p></Bloque>}
      {r.letalidad && <Bloque titulo="Gravedad si se descompensa"><p>Nivel {r.letalidad.nivel} (1 = más letal): {r.letalidad.detalle}</p></Bloque>}
      {r.rubrica?.medicion?.umbral && <Bloque titulo="Medición que mira la IA"><p>{r.rubrica.medicion.tipo?.replaceAll("_", " ")}: umbral {r.rubrica.medicion.umbral.valor} {r.rubrica.medicion.umbral.unidad}<Fuente f={r.rubrica.medicion.umbral.fuente} /></p></Bloque>}
      {r.fuentes?.length > 0 && <p className="text-[12px] text-on-surface-variant mt-2">Fuentes consultadas: {r.fuentes.map((f) => `${f.id}${f.version ? ` ${f.version}` : ""}`).join(" · ")}</p>}
    </div>
  );
}
