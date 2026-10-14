import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as api from "./api";
import { ESPECIALIDADES, ETIQUETA, POR_PAGINA, fmt } from "./lib/constantes";
import { exportarCsv } from "./lib/exportar";
import { Caja, Filtro, Icono, Indicador, Logo, Marca, Prioridad } from "./components/ui";
import { CargarDatos } from "./pantallas/CargarDatos";
import { Criterios } from "./pantallas/Criterios";
import { Ficha } from "./pantallas/Ficha";
import { Hoy } from "./pantallas/Hoy";
import { Indicadores } from "./pantallas/Indicadores";
import { NuevoPaciente } from "./pantallas/NuevoPaciente";

export default function App() {
  const fechas = api.fechas();
  const esApi = api.MODO === "api";
  const [demo, setDemo] = useState(!esApi);
  const [iFecha, setIFecha] = useState(fechas.length - 1);
  const [esp, setEsp] = useState("Todas");
  const [vista, setVista] = useState(esApi ? "hoy" : "lista");
  const [data, setData] = useState(null);
  const [sel, setSel] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [destacado, setDestacado] = useState(null);
  const [error, setError] = useState(null);
  const [busca, setBusca] = useState("");
  const [filtroCat, setFiltroCat] = useState("todas");
  const [soloPend, setSoloPend] = useState(false);
  const [pagina, setPagina] = useState(0);
  const [nuevo, setNuevo] = useState(false);
  const fecha = demo ? fechas[iFecha] : fechas[fechas.length - 1];

  const cargar = useCallback(async () => {
    try { setError(null); setData(await api.getPacientes(fecha, esp === "Todas" ? null : esp)); }
    catch (e) { setError(e.message); }
  }, [fecha, esp]);
  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    if (!sel) return setDetalle(null);
    api.getPaciente(sel, fecha).then(setDetalle).catch(() => setDetalle(null));
  }, [sel, fecha, data]);
  useEffect(() => setPagina(0), [busca, filtroCat, soloPend, esp]);
  // al seleccionar (p. ej. un paciente recién ingresado) saltar a la página donde está
  useEffect(() => {
    const i = filtrados.findIndex((p) => p.id_paciente === sel);
    if (i >= 0) setPagina(Math.floor(i / POR_PAGINA));
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtrados = useMemo(() => {
    if (!data) return [];
    const q = busca.trim().toLowerCase();
    return data.pacientes.filter((p) =>
      (filtroCat === "todas" || (filtroCat === "vital" ? p.contactar_hoy : filtroCat === "revisar" ? p.revision_sugerida?.length > 0 : p.categoria === filtroCat)) &&
      (!soloPend || p.estado_revision === "pendiente" || p.estado_revision === "requiere_revision") &&
      (!q || p.nombre_fantasia.toLowerCase().includes(q) || p.id_paciente.toLowerCase().includes(q) || p.diagnostico_texto.toLowerCase().includes(q)));
  }, [data, busca, filtroCat, soloPend]);

  const mostrarAviso = (a) => { setAviso(a); setTimeout(() => setAviso(null), 6000); };
  const abrir = (id) => { setSel(id); setVista("lista"); };

  if (!data) return <div className="p-10 text-lg">{error ? `No se pudo cargar la lista: ${error}` : "Cargando lista de espera…"}</div>;
  const paciente = sel && data.pacientes.find((p) => p.id_paciente === sel);
  const vitales = data.pacientes.filter((p) => p.riesgo_vital);
  const porContactar = vitales.filter((p) => p.contactar_hoy);
  const altas = data.pacientes.filter((p) => p.categoria === "alta").length;
  const gesVenc = data.pacientes.filter((p) => p.ges?.vencida).length;
  const pendientes = data.pacientes.filter((p) => p.revision_sugerida?.length > 0).length;
  const pag = filtrados.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA);
  const paginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-surface-container-lowest border-b border-outline-variant">
        <div className="flex h-1.5"><div className="w-1/3 bg-primary" /><div className="w-2/3 bg-gob-rojo" /></div>
        <div className="max-w-[1400px] mx-auto px-6 h-[72px] flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Logo />
            <div className="leading-tight border-l border-outline-variant pl-3">
              <div className="text-[16px] font-bold text-primary-container">Hospital Clínico Dra. Eloísa Díaz Inzunza</div>
              <div className="text-[13px] text-on-surface-variant">La Florida · Servicio de Salud Metropolitano Sur Oriente</div>
              <div className="text-[13px] font-semibold text-hlf">Lista de espera dinámica · Consultas de especialidad</div>
            </div>
          </div>
          <div className="flex items-center gap-3 text-[13px]">
            <span className="text-on-surface-variant">Lista al <b className="text-on-surface">{fmt(fecha)}</b></span>
            <label className="flex items-center gap-1.5 text-on-surface-variant cursor-pointer select-none border-l border-outline-variant pl-3">
              <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} className="accent-[#0f69b4]" />Modo demostración
            </label>
          </div>
        </div>
        <nav className="max-w-[1400px] mx-auto px-6 flex gap-6 text-[14px]">
          {[["hoy", "Hoy", porContactar.length], ["lista", "Lista de espera", null], ["indicadores", "Indicadores", null], ["cargar", "Cargar datos", null], ["criterios", "Criterios", null]].map(([k, t, n]) => (
            <button key={k} onClick={() => setVista(k)}
              className={`py-2.5 border-b-2 -mb-px ${vista === k ? "border-primary text-primary font-semibold" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}>
              {t}{n ? <span className="ml-1.5 px-1.5 rounded-full bg-error text-on-error text-[12px] font-semibold">{n}</span> : null}
            </button>
          ))}
        </nav>
      </header>

      {demo && (
        <div className="bg-ambar-container/60 border-b border-ambar/30">
          <div className="max-w-[1400px] mx-auto px-6 py-2 flex flex-wrap items-center gap-4 text-[13px]">
            <span className="font-semibold text-ambar flex items-center gap-1"><Icono n="science" className="text-[18px]" />Modo demostración{!esApi && " (datos precalculados, sin API)"}</span>
            <label className="flex items-center gap-2 flex-1 min-w-[280px]">
              Ver la lista como estaba el <b>{fmt(fechas[iFecha])}</b>
              <input type="range" min={0} max={fechas.length - 1} value={iFecha} onChange={(e) => setIFecha(+e.target.value)} className="flex-1 accent-[#8a5100]" />
            </label>
            <span className="text-on-surface-variant">Solo se usan registros con fecha anterior o igual.</span>
          </div>
        </div>
      )}

      <AnimatePresence>
        {aviso && (
          <motion.div initial={{ y: -8, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed top-4 left-1/2 -translate-x-1/2 z-50 bg-on-surface text-white px-4 py-2.5 rounded shadow-lg text-[14px] flex items-center gap-2">
            <Icono n="check_circle" className="text-[20px]" />{aviso.titulo}
            {aviso.antes != null && <span className="opacity-90">· posición {aviso.antes} → <b>{aviso.despues}</b>{aviso.cat && ` · prioridad ${ETIQUETA[aviso.cat]}`}</span>}
          </motion.div>
        )}
      </AnimatePresence>

      <main className="flex-1 max-w-[1400px] w-full mx-auto px-6 py-5">
        {error && <div className="bg-error-container text-on-error-container p-3 mb-4 rounded">{error}</div>}

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
          <Indicador n={data.total} t="Pacientes en espera" />
          <Indicador n={porContactar.length} t={`Contactar hoy (de ${vitales.length} con riesgo vital)`} tono={porContactar.length ? "rojo" : null} onClick={() => setVista("hoy")} />
          <Indicador n={altas} t="Prioridad alta" />
          <Indicador n={pendientes} t="Requieren revisión del especialista" tono={pendientes ? "ambar" : null} onClick={() => { setVista("lista"); setFiltroCat("revisar"); setSoloPend(false); }} />
          <Indicador n={gesVenc} t="Garantías GES vencidas" />
        </div>

        {vista === "hoy" && <Hoy vitales={vitales} fecha={fecha} esp={esp} setEsp={setEsp} onVer={abrir} esApi={esApi} />}
        {vista === "criterios" && <Criterios />}
        {vista === "indicadores" && <Indicadores fecha={fecha} esApi={esApi} data={data} />}
        {vista === "cargar" && <CargarDatos esApi={esApi} onListo={async (r) => {
          await cargar();
          mostrarAviso({ titulo: `Datos cargados: ${r.resumen.pacientes_nuevos} pacientes nuevos, ${r.resumen.pacientes_actualizados} actualizados, ${r.resumen.eventos} eventos` });
        }} />}
        {vista === "lista" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            <div className="lg:col-span-7 xl:col-span-8 flex flex-col gap-4">
              <div className="bg-surface-container-lowest border border-outline-variant rounded p-3 flex flex-wrap items-end gap-3 text-[13px]">
                <Filtro label="Especialidad">
                  <select value={esp} onChange={(e) => setEsp(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-white">{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select>
                </Filtro>
                <Filtro label="Buscar paciente">
                  <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nombre, ID o diagnóstico" className="h-9 px-2 w-56 border border-outline-variant rounded" />
                </Filtro>
                <Filtro label="Prioridad">
                  <select value={filtroCat} onChange={(e) => setFiltroCat(e.target.value)} className="h-9 px-2 border border-outline-variant rounded bg-white">
                    <option value="todas">Todas</option><option value="vital">Contactar hoy</option><option value="revisar">Requieren revisión</option><option value="alta">Alta</option><option value="media">Media</option><option value="baja">Baja</option>
                  </select>
                </Filtro>
                <label className="flex items-center gap-2 h-9 cursor-pointer select-none"><input type="checkbox" checked={soloPend} onChange={(e) => setSoloPend(e.target.checked)} className="w-4 h-4 accent-[#0f69b4]" />Solo pendientes de revisión</label>
                <button onClick={() => exportarCsv(filtrados, fecha)} className="ml-auto h-9 px-3 rounded border border-outline-variant bg-white font-semibold flex items-center gap-1"><Icono n="download" className="text-[18px]" />Descargar Excel</button>
                {esApi && <button onClick={() => setNuevo(true)} className="h-9 px-3 rounded bg-primary text-on-primary font-semibold flex items-center gap-1"><Icono n="person_add" className="text-[18px]" />Ingresar paciente</button>}
              </div>
              {nuevo && <NuevoPaciente fecha={fecha} onCerrar={() => setNuevo(false)} onListo={async (r) => {
                setNuevo(false); setBusca(""); setFiltroCat("todas"); setSoloPend(false); await cargar(); setSel(r.id_paciente);
                mostrarAviso({ titulo: `${r.paciente?.nombre_fantasia} ingresado a la lista`, despues: r.paciente?.posicion, antes: "—", cat: r.paciente?.categoria });
              }} />}

              <section className="bg-surface-container-lowest border border-outline-variant rounded overflow-hidden">
                <table className="w-full text-left border-collapse text-[14px]">
                  <thead>
                    <tr className="bg-surface-container-low text-[13px] text-on-surface-variant border-b border-outline-variant">
                      <th className="py-2 px-3 font-semibold w-16">N°</th><th className="py-2 px-2 font-semibold">Prioridad</th>
                      <th className="py-2 px-3 font-semibold">Paciente / diagnóstico</th><th className="py-2 px-2 font-semibold">Observaciones</th>
                      <th className="py-2 px-2 font-semibold text-center" title="Índice LACE (van Walraven 2010)">LACE</th>
                      <th className="py-2 px-3 font-semibold text-right">Espera</th><th className="py-2 px-3 font-semibold">Revisión</th>
                    </tr>
                  </thead>
                  <tbody>
                    <AnimatePresence initial={false}>
                      {pag.map((p) => {
                        const delta = p.posicion_anterior ? p.posicion_anterior - p.posicion : 0;
                        const activo = sel === p.id_paciente;
                        return (
                          <motion.tr key={p.id_paciente} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                            transition={{ type: "spring", stiffness: 300, damping: 32 }} onClick={() => setSel(p.id_paciente)}
                            className={`cursor-pointer border-b border-outline-variant/60 ${activo ? "bg-primary/10" : destacado === p.id_paciente ? "bg-ambar-container/60" : "hover:bg-surface-container-low"}`}>
                            <td className={`py-2.5 px-3 align-top ${p.riesgo_vital ? "border-l-4 border-l-error" : "border-l-4 border-l-transparent"}`}>
                              <div className="font-semibold">{p.posicion}</div>
                              {demo && delta !== 0 && <div className={`text-[12px] ${delta > 0 ? "text-error" : "text-on-surface-variant"}`}>{delta > 0 ? `▲ ${delta}` : `▼ ${-delta}`}</div>}
                            </td>
                            <td className="py-2.5 px-2 align-top"><Prioridad cat={p.categoria} /></td>
                            <td className="py-2.5 px-3 align-top">
                              <div className="font-semibold">{p.nombre_fantasia} <span className="font-normal text-on-surface-variant text-[13px]">· {p.edad} años</span></div>
                              <div className="text-[13px] text-on-surface-variant">{p.especialidad} · {p.diagnostico_cie10} {p.diagnostico_texto}</div>
                            </td>
                            <td className="py-2.5 px-2 align-top">
                              <div className="flex flex-wrap gap-1">
                                {p.contactar_hoy && <Marca tono="rojo">Contactar hoy</Marca>}
                                {p.riesgo_vital && !p.contactar_hoy && <Marca tono="azul" title={p.contacto?.texto}>Contactado</Marca>}
                                {!p.riesgo_vital && p.estado_clinico === "descompensado" && <Marca tono="rojo">Descompensado</Marca>}
                                {p.revision_sugerida?.length > 0 && <Marca tono="ambar" title={[...new Set(p.revision_sugerida.map((s) => s.motivo))].join(" · ")}>Revisar</Marca>}
                                {p.grupo_proteccion && <Marca tono="azul">{p.grupo_proteccion}</Marca>}
                                {p.estado_clinico === "estabilizado" && <Marca>Estabilizado</Marca>}
                                {p.ges?.vencida && <Marca tono="azul" title={`GES N°${p.ges.problema}: plazo ${p.ges.plazo_dias} días`}>GES vencida</Marca>}
                                {p.riesgo_inasistencia && <Marca tono="ambar" title="2 inasistencias consecutivas (causal 8)">2 inasistencias</Marca>}
                              </div>
                            </td>
                            <td className="py-2.5 px-2 align-top text-center">
                              <span className={`inline-block min-w-[28px] px-1.5 py-px rounded font-semibold ${p.lace?.total ? "bg-primary/10 text-primary-container" : "text-on-surface-variant"}`}>{p.lace?.total ?? "—"}</span>
                            </td>
                            <td className="py-2.5 px-3 align-top text-right whitespace-nowrap">{p.dias_espera} días{p.antiguedad_mayor_1_anio && <div className="text-[12px] text-on-surface-variant">más de 1 año</div>}</td>
                            <td className="py-2.5 px-3 align-top text-[13px] whitespace-nowrap">
                              {p.estado_revision === "pendiente" ? <span className="text-on-surface-variant">Pendiente</span>
                                : p.estado_revision === "requiere_revision" ? <span className="text-ambar font-semibold" title={p.revision_vencida_por}><Icono n="update" className="text-[16px]" /> Revisar de nuevo</span>
                                : <span className="text-verde font-semibold"><Icono n="check" className="text-[16px]" /> {p.estado_revision === "ajustado" ? "Ajustada" : "Confirmada"}</span>}
                            </td>
                          </motion.tr>
                        );
                      })}
                    </AnimatePresence>
                  </tbody>
                </table>
                {filtrados.length === 0 && <p className="p-6 text-on-surface-variant">No hay pacientes con esos filtros.</p>}
                <div className="px-3 py-2 flex items-center justify-between text-[13px] text-on-surface-variant bg-surface-container-low">
                  <span>{filtrados.length} pacientes · orden: prioridad, contactar hoy, puntaje LACE, más de 1 año en espera, fecha de ingreso</span>
                  <div className="flex items-center gap-2">
                    <button disabled={pagina === 0} onClick={() => setPagina(pagina - 1)} className="px-2 py-1 border border-outline-variant rounded bg-white disabled:opacity-40">Anterior</button>
                    <span>{pagina + 1} / {paginas}</span>
                    <button disabled={pagina >= paginas - 1} onClick={() => setPagina(pagina + 1)} className="px-2 py-1 border border-outline-variant rounded bg-white disabled:opacity-40">Siguiente</button>
                  </div>
                </div>
              </section>

              {data.excluidos.length > 0 && (
                <details className="bg-surface-container-lowest border border-outline-variant rounded">
                  <summary className="px-4 py-2.5 cursor-pointer text-[14px] font-semibold">
                    Egresados de la lista ({data.excluidos.length}): {data.excluidos.filter((e) => e.motivo === "fallecido").length} por fallecimiento · {data.excluidos.filter((e) => e.motivo === "atendido").length} atendidos
                  </summary>
                  <ul className="px-4 pb-3 text-[13px] text-on-surface-variant">
                    {[...data.excluidos].sort((a, b) => (b.fecha || "").localeCompare(a.fecha || "")).map((e) => (
                      <li key={e.id_paciente} className="py-1 border-t border-outline-variant/60 flex justify-between gap-2">
                        <span>{e.nombre_fantasia || e.id_paciente} · {e.especialidad}</span>
                        <span>{e.motivo === "fallecido" ? `Fallecimiento ${fmt(e.fecha)} · causal 9` : `Atendido en consulta nueva ${fmt(e.fecha)}`}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>

            <aside className="lg:col-span-5 xl:col-span-4 lg:sticky lg:top-4 flex flex-col gap-3 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
              {!paciente ? <Caja><p className="text-on-surface-variant">Seleccione un paciente para ver el detalle.</p></Caja> : (
                <Ficha key={paciente.id_paciente} p={paciente} total={data.total} detalle={detalle} fecha={fecha} esApi={esApi} demo={demo} onCambio={cargar} onAviso={mostrarAviso}
                  onDestacar={(id) => { setDestacado(id); setTimeout(() => setDestacado(null), 3000); }} />
              )}
            </aside>
          </div>
        )}
      </main>

      <footer className="border-t border-outline-variant bg-surface-container-lowest">
        <div className="max-w-[1400px] mx-auto px-6 py-3 text-[12px] text-on-surface-variant flex flex-wrap justify-between gap-2">
          <span>Prioridad según Tabla de priorización SSMSO 2025 (HLF) y criterios MINSAL. La herramienta propone; el equipo clínico decide.</span>
          <span>Datos sintéticos de demostración</span>
        </div>
      </footer>
    </div>
  );
}
