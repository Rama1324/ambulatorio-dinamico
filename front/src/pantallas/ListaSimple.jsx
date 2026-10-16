import { useEffect, useState } from "react";
import { descargarExcel } from "../excel";
import { Filtro, Icono, Prioridad } from "../componentes/comunes";
import { ESPECIALIDADES, ETIQUETA } from "../constantes";
import { fmt } from "../util";

// Decisión clínica ante una descompensación grave: la registra un profesional identificado, con seguimiento.
// Lista de espera simple: como una planilla, sin términos técnicos. Un clic abre todo el detalle en "Lista detallada".
const POR_PAGINA_SIMPLE = 50;

export function ListaSimple({ data, fecha, esp, setEsp, actualizando, onVer }) {
  const [busca, setBusca] = useState("");
  const [prioridad, setPrioridad] = useState("todas");
  const [pagina, setPagina] = useState(0);
  useEffect(() => setPagina(0), [busca, prioridad, esp]);
  const q = busca.trim().toLowerCase();
  const filas = data.pacientes.filter((p) => (prioridad === "todas" || p.categoria === prioridad) &&
    (!q || [p.nombre_fantasia, p.rut, (p.rut || "").replace(/[.-]/g, ""), p.id_paciente, p.diagnostico_texto, p.comuna].some((x) => (x || "").toLowerCase().includes(q))));
  const pag = filas.slice(pagina * POR_PAGINA_SIMPLE, (pagina + 1) * POR_PAGINA_SIMPLE);
  const paginas = Math.max(1, Math.ceil(filas.length / POR_PAGINA_SIMPLE));
  const SEXO = { F: "Femenino", M: "Masculino" };
  const columnas = ["N°", "Nombre", "RUT / ID", "Edad", "Sexo", "Comuna", "Previsión", "Especialidad", "Diagnóstico", "Prioridad", "Ingreso a la lista", "Días de espera"];
  const exportar = () => descargarExcel(`lista_espera_HLF_${fecha}.xlsx`, [{ nombre: "Lista de espera", filas: [columnas,
    ...filas.map((p) => [p.posicion, p.nombre_fantasia, p.rut || p.id_paciente, p.edad, SEXO[p.sexo] || p.sexo, p.comuna, p.prevision || "", p.especialidad,
      `${p.diagnostico_cie10} ${p.diagnostico_texto}`, ETIQUETA[p.categoria], fmt(p.fecha_ingreso_lista), p.dias_espera])] }]);
  const campo = "h-10 px-3 border border-outline-variant rounded bg-surface-container-lowest text-[15px]";
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-[22px] font-bold">Lista de espera</h1>
        <p className="text-[15px] text-on-surface-variant">Ordenada desde quien debe atenderse primero. Haga clic en un paciente para ver todo su detalle.</p>
      </div>
      <div className="flex flex-wrap items-end gap-3 text-[14px]">
        <Filtro label="Buscar"><input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nombre, RUT o diagnóstico" className={`${campo} w-64`} /></Filtro>
        <Filtro label="Especialidad"><select value={esp} onChange={(e) => setEsp(e.target.value)} className={campo}>{ESPECIALIDADES.map((e) => <option key={e}>{e}</option>)}</select></Filtro>
        <Filtro label="Prioridad"><select value={prioridad} onChange={(e) => setPrioridad(e.target.value)} className={campo}>
          <option value="todas">Todas</option><option value="alta">Alta</option><option value="media">Media</option><option value="baja">Baja</option></select></Filtro>
        <button onClick={exportar} className="ml-auto h-10 px-4 rounded bg-primary text-on-primary font-semibold flex items-center gap-1"><Icono n="download" className="text-[18px]" />Descargar en Excel</button>
      </div>
      <section className="bg-surface-container-lowest border border-outline-variant rounded overflow-x-auto relative" aria-busy={actualizando}>
        <table className={`w-full text-left border-collapse text-[14px] ${actualizando ? "opacity-40" : ""}`}>
          <thead><tr className="bg-surface-container-low text-on-surface-variant border-b border-outline-variant">
            {columnas.map((c) => <th key={c} className={`py-2 px-3 font-semibold whitespace-nowrap ${["N°", "Edad", "Días de espera"].includes(c) ? "text-right" : ""}`}>{c}</th>)}
          </tr></thead>
          <tbody>
            {pag.map((p) => (
              <tr key={p.id_paciente} onClick={() => onVer(p.id_paciente)} tabIndex={0} title="Ver todo el detalle"
                onKeyDown={(e) => { if (e.key === "Enter") onVer(p.id_paciente); }}
                className="cursor-pointer border-b border-outline-variant/60 hover:bg-primary/5 focus:bg-primary/10">
                <td className="py-2 px-3 text-right font-semibold">{p.posicion}</td>
                <td className="py-2 px-3 font-semibold text-primary whitespace-nowrap">{p.nombre_fantasia}</td>
                <td className="py-2 px-3 whitespace-nowrap">{p.rut || <span className="text-on-surface-variant">{p.id_paciente}</span>}</td>
                <td className="py-2 px-3 text-right">{p.edad}</td>
                <td className="py-2 px-3">{SEXO[p.sexo] || p.sexo}</td>
                <td className="py-2 px-3 whitespace-nowrap">{p.comuna}</td>
                <td className="py-2 px-3 whitespace-nowrap">{p.prevision}</td>
                <td className="py-2 px-3 whitespace-nowrap">{p.especialidad}</td>
                <td className="py-2 px-3">{p.diagnostico_texto}</td>
                <td className="py-2 px-3"><Prioridad cat={p.categoria} /></td>
                <td className="py-2 px-3 whitespace-nowrap">{fmt(p.fecha_ingreso_lista)}</td>
                <td className="py-2 px-3 text-right font-semibold whitespace-nowrap">{p.dias_espera}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {filas.length === 0 && <p className="p-6 text-on-surface-variant">No hay pacientes con esa búsqueda.</p>}
      </section>
      <div className="flex flex-wrap items-center justify-between gap-2 text-[14px] text-on-surface-variant">
        <span>{actualizando ? "Actualizando…" : `${filas.length} pacientes`} · lista al {fmt(fecha)}</span>
        <div className="flex items-center gap-2">
          <button disabled={pagina === 0} onClick={() => setPagina(pagina - 1)} className="px-3 py-1.5 border border-outline-variant rounded bg-surface-container-lowest disabled:opacity-40">Anterior</button>
          <span>Página {pagina + 1} de {paginas}</span>
          <button disabled={pagina >= paginas - 1} onClick={() => setPagina(pagina + 1)} className="px-3 py-1.5 border border-outline-variant rounded bg-surface-container-lowest disabled:opacity-40">Siguiente</button>
        </div>
      </div>
      <p className="text-[12px] text-on-surface-variant">Datos sintéticos: el registro de prueba no trae RUT, por eso se muestra el ID (en gris). Los pacientes ingresados con RUT y las planillas del hospital muestran el RUT.</p>
    </div>
  );
}
