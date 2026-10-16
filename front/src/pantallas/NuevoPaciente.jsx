import { useEffect, useState } from "react";
import * as api from "../api";
import { Filtro, Icono } from "../componentes/comunes";
import { COLOR_CAT, ETIQUETA } from "../constantes";

// RUT chileno: dígito verificador módulo 11. Devuelve "12.345.678-5" o null.
function validarRut(valor) {
  const s = String(valor || "").replace(/[^0-9kK]/g, "").toUpperCase();
  if (s.length < 2 || !/^\d+$/.test(s.slice(0, -1))) return null;
  const cuerpo = s.slice(0, -1).replace(/^0+/, ""), dv = s.slice(-1);
  if (!cuerpo || cuerpo.length > 8) return null;
  let suma = 0, factor = 2;
  for (const d of [...cuerpo].reverse()) { suma += +d * factor; factor = factor === 7 ? 2 : factor + 1; }
  const r = 11 - (suma % 11), esperado = r === 11 ? "0" : r === 10 ? "K" : String(r);
  return dv === esperado ? `${Number(cuerpo).toLocaleString("es-CL")}-${dv}` : null;
}

export function NuevoPaciente({ fecha, esp, onCerrar, onListo }) {
  const [cat, setCat] = useState(null);
  const [f, setF] = useState({ nombre: "", rut: "", edad: "", sexo: "F", comuna: "La Florida", prevision: "FONASA B", especialidad: esp && esp !== "Todas" ? esp : "", diagnostico_cie10: "", prioridad_inicial: "media", origen_derivacion: "CESFAM/APS", grupo_proteccion: "", acg: "", motivo_interconsulta: "" });
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => { api.getCatalogo().then(setCat).catch((e) => setError(e.message)); }, []);
  const set = (k) => (e) => {
    const v = e.target.value, dx = k === "diagnostico_cie10" ? cat?.diagnosticos.find((d) => d.diagnostico_cie10 === v) : null;
    setF({ ...f, [k]: v, ...(k === "especialidad" ? { diagnostico_cie10: "" } : {}), ...(dx?.prioridad_tabla ? { prioridad_inicial: dx.prioridad_tabla } : {}) });
  };
  const especialidades = cat ? [...new Set(cat.diagnosticos.map((d) => d.especialidad))] : [];
  const dxs = cat ? cat.diagnosticos.filter((d) => d.especialidad === f.especialidad) : [];
  const elegido = dxs.find((d) => d.diagnostico_cie10 === f.diagnostico_cie10);
  const grupos = [["Con pacientes en el registro (CIE-10)", dxs.filter((d) => !d.prioridad_tabla)],
    ...["alta", "media", "baja"].map((c) => [`Tabla oficial HLF · prioridad ${ETIQUETA[c].toLowerCase()}`, dxs.filter((d) => d.prioridad_tabla === c)])].filter(([, l]) => l.length);
  const rutOk = validarRut(f.rut);
  const rutMal = f.rut.trim() !== "" && !rutOk;
  const valido = f.nombre.trim() && f.edad !== "" && f.diagnostico_cie10 && !rutMal;
  const guardar = async () => {
    setEnviando(true); setError(null);
    try { onListo(await api.postPaciente({ ...f, rut: rutOk || undefined, edad: Number(f.edad), fecha_corte: fecha })); }
    catch (e) { setError(e.message); setEnviando(false); }
  };
  const campo = "h-9 px-2 border border-outline-variant rounded bg-surface-container-lowest w-full";
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onCerrar}>
      <div className="bg-surface-container-lowest rounded max-w-xl w-full" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-2.5 border-b border-outline-variant flex justify-between items-center">
          <h2 className="font-semibold">Ingresar interconsulta a la lista de espera</h2>
          <button onClick={onCerrar} className="text-on-surface-variant"><Icono n="close" /></button>
        </div>
        <div className="p-4 grid grid-cols-2 gap-3 text-[14px]">
          <Filtro label="Nombre del paciente"><input value={f.nombre} onChange={set("nombre")} className={campo} autoFocus /></Filtro>
          <Filtro label="RUT">
            <input value={f.rut} onChange={set("rut")} onBlur={() => rutOk && setF({ ...f, rut: rutOk })} placeholder="12.345.678-5" inputMode="text"
              aria-invalid={rutMal} className={`${campo} ${rutMal ? "border-error" : ""}`} />
            <span className={`text-[12px] ${rutMal ? "text-error" : rutOk ? "text-verde" : "text-on-surface-variant"}`}>
              {rutMal ? "RUT inválido: revise el dígito verificador" : rutOk ? "RUT válido" : "Se valida el dígito verificador"}</span>
          </Filtro>
          <div className="grid grid-cols-2 gap-2">
            <Filtro label="Edad"><input type="number" min={0} max={120} value={f.edad} onChange={set("edad")} className={campo} /></Filtro>
            <Filtro label="Sexo"><select value={f.sexo} onChange={set("sexo")} className={campo}><option value="F">Femenino</option><option value="M">Masculino</option></select></Filtro>
          </div>
          <Filtro label="Comuna"><select value={f.comuna} onChange={set("comuna")} className={campo}>{cat?.comunas.map((c) => <option key={c}>{c}</option>)}</select></Filtro>
          <Filtro label="Previsión"><select value={f.prevision} onChange={set("prevision")} className={campo}>{cat?.previsiones.map((c) => <option key={c}>{c}</option>)}</select></Filtro>
          <Filtro label="Especialidad"><select value={f.especialidad} onChange={set("especialidad")} className={campo}><option value="">Seleccione…</option>{especialidades.map((e) => <option key={e}>{e}</option>)}</select></Filtro>
          <Filtro label="Diagnóstico o síntoma"><select value={f.diagnostico_cie10} onChange={set("diagnostico_cie10")} disabled={!f.especialidad} className={campo}><option value="">Seleccione…</option>
            {grupos.map(([t, l]) => <optgroup key={t} label={t}>{l.map((d) => <option key={d.diagnostico_cie10} value={d.diagnostico_cie10}>{d.prioridad_tabla ? d.diagnostico_texto : `${d.diagnostico_cie10} · ${d.diagnostico_texto}`}</option>)}</optgroup>)}
          </select>
            {elegido?.prioridad_tabla && <span className="text-[12px] text-on-surface-variant">Tabla SSMSO 2025, HLF, pág. {elegido.pagina}: prioridad {ETIQUETA[elegido.prioridad_tabla].toLowerCase()}. Puede subirla; el sistema no la deja más abajo.</span>}
          </Filtro>
          <Filtro label="Prioridad asignada al revisar la SIC">
            <div className="flex gap-1">{["alta", "media", "baja"].map((c) => (
              <button key={c} type="button" onClick={() => setF({ ...f, prioridad_inicial: c })} className={`flex-1 h-9 rounded border font-semibold ${f.prioridad_inicial === c ? COLOR_CAT[c] : "border-outline-variant text-on-surface-variant"}`}>{ETIQUETA[c]}</button>
            ))}</div>
          </Filtro>
          <Filtro label="Origen de la derivación"><select value={f.origen_derivacion} onChange={set("origen_derivacion")} className={campo}>{cat?.origenes.map((c) => <option key={c}>{c}</option>)}</select></Filtro>
          <Filtro label="Grupo de especial protección"><select value={f.grupo_proteccion} onChange={set("grupo_proteccion")} className={campo}><option value="">Ninguno</option>{cat?.grupos_proteccion.map((g) => <option key={g}>{g}</option>)}</select></Filtro>
          <div className="col-span-2"><Filtro label="Motivo de la interconsulta (lo que escribió quien deriva)">
            <textarea rows={3} value={f.motivo_interconsulta} onChange={set("motivo_interconsulta")} placeholder="Ej.: Disnea de esfuerzo progresiva y edema de extremidades inferiores desde hace 2 semanas."
              className="w-full p-2 border border-outline-variant rounded bg-surface-container-lowest text-[14px]" />
            <span className="text-[12px] text-on-surface-variant">Si la IA está activa y la enfermedad tiene criterios clínicos, se lee con ellos: puede subir la prioridad o marcar "derivar hoy a urgencia". Nunca la baja.</span>
          </Filtro></div>
          <Filtro label="Riesgo ACG (si se conoce)"><select value={f.acg} onChange={set("acg")} className={campo}><option value="">Sin dato</option>{cat?.acg.map((a) => <option key={a.nivel} value={a.nivel}>{a.nivel} · {a.texto}</option>)}</select></Filtro>
        </div>
        {error && <p className="px-4 text-error text-[13px]">{error}</p>}
        <div className="px-4 py-3 border-t border-outline-variant flex justify-end gap-2">
          <button onClick={onCerrar} className="px-4 py-2 rounded border border-outline-variant font-semibold">Cancelar</button>
          <button disabled={!valido || enviando} onClick={guardar} className="px-4 py-2 rounded bg-primary text-on-primary font-semibold disabled:opacity-40">{enviando ? "Ingresando…" : "Ingresar y priorizar"}</button>
        </div>
      </div>
    </div>
  );
}
