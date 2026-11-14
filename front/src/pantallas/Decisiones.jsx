// Decisiones del sistema: la cola de trabajo del especialista (GET /decisiones). Cada tarjeta dice qué pasó, por qué y
// quién decidió; el especialista responde si la decisión es adecuada o incorrecta y ve qué aprendió el sistema.
import { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "../api";
import { descargarExcel } from "../excel";
import { Filtro, Icono } from "../componentes/comunes";
import { CANAL, DISPARADOR, TarjetaDecision, VEREDICTO_TXT, fmtHora, quienDecidio, textoEvento } from "../componentes/Decision";
import { ESPECIALIDADES, ETIQUETA, plural } from "../constantes";
import { fmt } from "../util";

const ESTADOS = { pendiente: "Pendientes de revisión", revisada: "Revisadas", todas: "Todas" };

export function Decisiones({ data, esp, setEsp, fecha, lote, onQuitarLote, onVer, onCambio, onAviso, onIrAprendizaje }) {
  const [estado, setEstado] = useState("pendiente");
  const [r, setR] = useState(null);
  const [error, setError] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [motivos, setMotivos] = useState([]);
  const [recientes, setRecientes] = useState([]);  // revisadas en esta pantalla: se quedan a la vista con lo que aprendió el sistema
  useEffect(() => { api.catalogoCache().then((c) => setMotivos(c.motivos_veredicto || [])).catch(() => {}); }, []);
  const espApi = lote || esp === "Todas" ? null : esp;
  const cargar = useCallback(async () => {
    setCargando(true);
    try { setError(null); setR(await api.getDecisiones(lote ? "todas" : estado, espApi, lote ? 1000 : 200)); }
    catch (e) { setError(e.message); } finally { setCargando(false); }
  }, [estado, espApi, lote]);
  useEffect(() => { cargar(); }, [cargar]);

  // nombre y diagnóstico de cada paciente: la lista cargada es de una especialidad; si hay decisiones de otras (p. ej. un lote),
  // se pide una vez la lista de todo el hospital
  const [todos, setTodos] = useState(null);
  const faltan = (r?.decisiones || []).some((d) => !data?.pacientes.some((p) => p.id_paciente === d.id_paciente));
  useEffect(() => {
    if (!faltan || todos) return;
    let vivo = true;
    api.getPacientes(fecha).then((x) => vivo && setTodos(x.pacientes)).catch(() => {});
    return () => { vivo = false; };
  }, [faltan, todos, fecha]);
  const porId = useMemo(() => Object.fromEntries([...(todos || []).map((p) => ({ ...p, rev: undefined })), ...(data?.pacientes || [])].map((p) => [p.id_paciente, p])), [data, todos]);
  const idsRecientes = new Set(recientes.map((x) => x.d.id_dictamen));
  const lista = (r?.decisiones || []).filter((d) => (!lote || d.disparador?.id_lote === lote) && !idsRecientes.has(d.id_dictamen));

  const revisado = async (d, resp) => {
    if (resp) setRecientes((xs) => [{ d: { ...d, revision: resp.revision, necesita_revision: false }, aprendizaje: resp.aprendizaje || {} }, ...xs]);
    await Promise.all([onCambio?.(), cargar()]);
  };

  const exportar = () => {
    const todas = [...recientes.map((x) => x.d), ...lista];
    descargarExcel(`decisiones_HLF_${fecha}${espApi ? `_${espApi}` : ""}.xlsx`, [
      { nombre: "Decisiones", filas: [["Fecha", "Paciente", "ID", "Especialidad", "Qué la gatilló", "Detalle", "Canal", "Prioridad antes", "Prioridad después",
        "Puesto antes", "Puesto después", "De", "Abre alerta 72 h", "Explicación", "Quién decidió", "Modelo de IA", "Estado", "Veredicto", "Motivo", "Explicación del especialista", "Revisó", "Fecha revisión", "ID decisión"],
      ...todas.map((d) => { const s = d.resultado || {}, v = d.revision, ds = d.disparador || {};
        return [fmtHora(d.fecha), porId[d.id_paciente]?.nombre_fantasia || "", d.id_paciente, d.especialidad, DISPARADOR[ds.tipo] || ds.tipo, textoEvento(ds.descripcion),
          CANAL[ds.canal] || ds.canal || "", ETIQUETA[s.categoria_antes] || "", ETIQUETA[s.categoria] || "", s.posicion_antes ?? "", s.posicion ?? "", s.total ?? "",
          s.alerta_nueva ? "Sí" : "", d.explicacion || "", quienDecidio(d).texto, d.informacion_utilizada?.ia?.modelo || "",
          v ? "Revisada" : d.necesita_revision ? "Pendiente" : "No requiere revisión", v ? VEREDICTO_TXT[v.veredicto] : "",
          v ? motivos.find((m) => m.valor === v.motivo_codigo)?.texto || v.motivo_codigo || "" : "", v?.motivo || "", v?.usuario || "", v ? fmt(v.fecha) : "", d.id_dictamen]; })] },
      { nombre: "Fundamento", filas: [["ID decisión", "ID paciente", "Factor", "Detalle", "Fuente"],
        ...todas.flatMap((d) => (d.fundamento || []).map((f) => [d.id_dictamen, d.id_paciente, f.factor, f.valor, f.fuente]))] },
      { nombre: "Filtros e información", filas: [["Dato", "Valor"], ["Estado", lote ? `Lote ${lote}` : ESTADOS[estado]], ["Especialidad", espApi || "Todas"],
        ["Decisiones exportadas", todas.length], ["Generado por", api.getUsuario() || "(sin nombre)"], ["Generado el", new Date().toLocaleString("es-CL")],
        ["Datos", "Sintéticos de demostración: no son pacientes reales"],
        ["Criterio", "La IA lee; el sistema decide con criterios con fuente; el especialista revisa y decide."]] }]);
  };

  const campo = "h-10 px-2 border border-outline-variant rounded bg-surface-container-lowest";
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-[22px] font-bold">Decisiones del sistema</h1>
        <p className="text-[15px] text-on-surface-variant">Cada vez que llega información de un paciente, el sistema decide su prioridad y deja escrito por qué.
          Aquí el especialista revisa esas decisiones: si son adecuadas o no, y por qué. El sistema propone; el equipo clínico decide.</p>
      </div>
      <div className="flex flex-wrap items-end gap-3 text-[14px]">
        {lote ? <div className="flex items-center gap-2 h-10 px-3 rounded bg-primary/10 text-primary font-semibold">
          <Icono n="inventory_2" className="text-[18px]" />Decisiones del lote {lote}
          <button onClick={onQuitarLote} className="ml-1 text-on-surface-variant hover:text-on-surface" aria-label="Quitar filtro de lote"><Icono n="close" className="text-[18px]" /></button></div>
          : <>
            <div className="flex rounded border border-outline-variant overflow-hidden" role="group" aria-label="Estado">
              {Object.entries(ESTADOS).map(([k, t]) => <button key={k} onClick={() => setEstado(k)} aria-pressed={estado === k}
                className={`h-10 px-3 ${estado === k ? "bg-primary text-on-primary font-semibold" : "bg-surface-container-lowest text-on-surface-variant hover:text-on-surface"}`}>{t}</button>)}
            </div>
            <Filtro label="Especialidad"><select value={esp} onChange={(e) => setEsp(e.target.value)} className={campo}>{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select></Filtro>
          </>}
        <button onClick={cargar} disabled={cargando} className={`${campo} px-3 flex items-center gap-1 font-semibold disabled:opacity-50`}><Icono n="refresh" className="text-[18px]" />Actualizar</button>
        <button onClick={exportar} disabled={!lista.length && !recientes.length} className="ml-auto h-10 px-4 rounded bg-primary text-on-primary font-semibold flex items-center gap-1 disabled:opacity-40">
          <Icono n="download" className="text-[18px]" />Exportar a Excel</button>
      </div>

      {error && <div className="rounded bg-error-container text-on-error-container p-3 flex items-center gap-2"><Icono n="cloud_off" className="text-[20px]" />
        No se pudieron cargar las decisiones: {error}. <button onClick={cargar} className="font-semibold underline">Reintentar</button></div>}

      {recientes.length > 0 && <section className="flex flex-col gap-3" aria-label="Revisadas recién">
        <h2 className="text-[15px] font-semibold text-on-surface-variant">Revisadas recién por usted</h2>
        {recientes.map(({ d, aprendizaje }) => <TarjetaDecision key={d.id_dictamen} d={d} paciente={porId[d.id_paciente]} motivos={motivos} fecha={fecha} aprendizaje={aprendizaje}
          onVer={onVer} onAviso={onAviso} onRevisado={() => revisado(d, null)} onIrAprendizaje={onIrAprendizaje} />)}
      </section>}

      {!r && !error && <div className="flex flex-col gap-3" aria-hidden="true">{[0, 1, 2].map((i) => <div key={i} className="h-40 rounded bg-surface-container-high/50 animate-pulse" />)}</div>}
      {r && !error && lista.length === 0 && <div className="rounded border border-outline-variant bg-surface-container-lowest p-6 text-center">
        <Icono n={estado === "pendiente" && !lote ? "task_alt" : "inbox"} className="text-[40px] text-hlf" />
        <p className="font-semibold mt-1">{lote ? "Este lote no generó decisiones (ningún paciente de la lista recibió información clínica nueva)."
          : estado === "pendiente" ? `No hay decisiones pendientes de revisión${espApi ? ` en ${espApi}` : ""}.` : `No hay decisiones ${estado === "revisada" ? "revisadas" : "registradas"}${espApi ? ` en ${espApi}` : ""}.`}</p>
        {!lote && estado === "pendiente" && <p className="text-[13px] text-on-surface-variant">Aparecen aquí cuando el sistema sube una prioridad, abre una alerta o
          deja un caso para revisión: por ejemplo, al registrar un evento en la ficha de un paciente o al cargar un archivo en «Recepción de datos».</p>}
      </div>}

      <div className={`flex flex-col gap-3 ${cargando ? "opacity-60" : ""}`}>
        {lista.map((d) => <TarjetaDecision key={d.id_dictamen} d={d} paciente={porId[d.id_paciente]} motivos={motivos} fecha={fecha}
          onVer={onVer} onAviso={onAviso} onRevisado={(resp) => revisado(d, resp)} onIrAprendizaje={onIrAprendizaje} />)}
      </div>
      {r && lista.length > 0 && <p className="text-[13px] text-on-surface-variant">{plural(lista.length, "decisión", "decisiones")}
        {estado === "pendiente" && !lote ? " · primero las que abren una alerta, luego los casos donde los especialistas más han discrepado, luego las más recientes" : " · más recientes primero"}.
        {r.total >= (lote ? 1000 : 200) ? " Se muestran las primeras: use el filtro de especialidad." : ""}</p>}
    </div>
  );
}
