import { useEffect, useState } from "react";
import * as api from "../api";
import { COLOR_CAT, ETIQUETA } from "../lib/constantes";
import { Filtro, Icono } from "../components/ui";

export function NuevoPaciente({ fecha, onCerrar, onListo }) {
  const [cat, setCat] = useState(null);
  const [f, setF] = useState({ nombre: "", edad: "", sexo: "F", comuna: "La Florida", prevision: "FONASA B", especialidad: "", diagnostico_cie10: "", prioridad_inicial: "media", origen_derivacion: "CESFAM/APS", grupo_proteccion: "", acg: "" });
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => { api.getCatalogo().then(setCat).catch((e) => setError(e.message)); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value, ...(k === "especialidad" ? { diagnostico_cie10: "" } : {}) });
  const especialidades = cat ? [...new Set(cat.diagnosticos.map((d) => d.especialidad))] : [];
  const dxs = cat ? cat.diagnosticos.filter((d) => d.especialidad === f.especialidad) : [];
  const valido = f.nombre.trim() && f.edad !== "" && f.diagnostico_cie10;
  const guardar = async () => {
    setEnviando(true); setError(null);
    try { onListo(await api.postPaciente({ ...f, edad: Number(f.edad), fecha_corte: fecha })); }
    catch (e) { setError(e.message); setEnviando(false); }
  };
  const campo = "h-11 px-2 border border-outline-variant rounded bg-surface-container-lowest w-full";
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onCerrar}>
      <div className="bg-surface-container-lowest rounded max-w-xl w-full" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-2.5 border-b border-outline-variant flex justify-between items-center">
          <h2 className="font-semibold">Ingresar interconsulta a la lista de espera</h2>
          <button onClick={onCerrar} className="text-on-surface-variant"><Icono n="close" /></button>
        </div>
        <div className="p-4 grid grid-cols-2 gap-3 text-[14px]">
          <Filtro label="Nombre del paciente"><input value={f.nombre} onChange={set("nombre")} className={campo} autoFocus /></Filtro>
          <div className="grid grid-cols-2 gap-2">
            <Filtro label="Edad"><input type="number" min={0} max={120} value={f.edad} onChange={set("edad")} className={campo} /></Filtro>
            <Filtro label="Sexo"><select value={f.sexo} onChange={set("sexo")} className={campo}><option value="F">Femenino</option><option value="M">Masculino</option></select></Filtro>
          </div>
          <Filtro label="Comuna"><select value={f.comuna} onChange={set("comuna")} className={campo}>{cat?.comunas.map((c) => <option key={c}>{c}</option>)}</select></Filtro>
          <Filtro label="Previsión"><select value={f.prevision} onChange={set("prevision")} className={campo}>{cat?.previsiones.map((c) => <option key={c}>{c}</option>)}</select></Filtro>
          <Filtro label="Especialidad"><select value={f.especialidad} onChange={set("especialidad")} className={campo}><option value="">Seleccione…</option>{especialidades.map((e) => <option key={e}>{e}</option>)}</select></Filtro>
          <Filtro label="Diagnóstico (CIE-10)"><select value={f.diagnostico_cie10} onChange={set("diagnostico_cie10")} disabled={!f.especialidad} className={campo}><option value="">Seleccione…</option>{dxs.map((d) => <option key={d.diagnostico_cie10} value={d.diagnostico_cie10}>{d.diagnostico_cie10} · {d.diagnostico_texto}</option>)}</select></Filtro>
          <Filtro label="Prioridad asignada al revisar la SIC">
            <div className="flex gap-1">{["alta", "media", "baja"].map((c) => (
              <button key={c} type="button" onClick={() => setF({ ...f, prioridad_inicial: c })} className={`flex-1 h-11 rounded border font-semibold ${f.prioridad_inicial === c ? COLOR_CAT[c] : "border-outline-variant text-on-surface-variant"}`}>{ETIQUETA[c]}</button>
            ))}</div>
          </Filtro>
          <Filtro label="Origen de la derivación"><select value={f.origen_derivacion} onChange={set("origen_derivacion")} className={campo}>{cat?.origenes.map((c) => <option key={c}>{c}</option>)}</select></Filtro>
          <Filtro label="Grupo de especial protección"><select value={f.grupo_proteccion} onChange={set("grupo_proteccion")} className={campo}><option value="">Ninguno</option>{cat?.grupos_proteccion.map((g) => <option key={g}>{g}</option>)}</select></Filtro>
          <Filtro label="Riesgo ACG (si se conoce)"><select value={f.acg} onChange={set("acg")} className={campo}><option value="">Sin dato</option>{cat?.acg.map((a) => <option key={a.nivel} value={a.nivel}>{a.nivel} · {a.texto}</option>)}</select></Filtro>
        </div>
        {error && <p className="px-4 text-error text-[14px]">{error}</p>}
        <div className="px-4 py-3 border-t border-outline-variant flex justify-end gap-2">
          <button onClick={onCerrar} className="px-4 py-2 rounded border border-outline-variant font-semibold">Cancelar</button>
          <button disabled={!valido || enviando} onClick={guardar} className="px-4 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{enviando ? "Ingresando…" : "Ingresar y priorizar"}</button>
        </div>
      </div>
    </div>
  );
}
