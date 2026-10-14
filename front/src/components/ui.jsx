import { useState } from "react";
import { COLOR_CAT, ETIQUETA } from "../lib/constantes";

export const Icono = ({ n, className = "" }) => <span className={`material-symbols-outlined align-middle ${className}`}>{n}</span>;
export const Prioridad = ({ cat }) => (
  <span className={`inline-block min-w-[58px] text-center px-2 py-0.5 rounded border text-[14px] font-semibold ${COLOR_CAT[cat]}`}>{ETIQUETA[cat]}</span>
);
export const Marca = ({ children, tono = "gris", title }) => {
  const t = { rojo: "text-error border-error/40 bg-error-container/50", ambar: "text-ambar border-ambar/40 bg-ambar-container/50", gris: "text-on-surface-variant border-outline-variant bg-surface-container-low", azul: "text-primary border-primary/30 bg-primary/5" }[tono];
  return <span title={title} className={`inline-block px-1.5 py-px rounded border text-[13px] whitespace-nowrap ${t}`}>{children}</span>;
};
export const Caja = ({ titulo, accion, children, className = "" }) => (
  <section className={`bg-surface-container-lowest border border-outline-variant rounded ${className}`}>
    {titulo && <div className="px-4 py-2.5 border-b border-outline-variant flex items-center justify-between"><h2 className="text-[15px] font-semibold">{titulo}</h2>{accion}</div>}
    <div className="p-4">{children}</div>
  </section>
);

// Logo oficial del hospital: poner el archivo en front/public/logo-hlf.png. Si no está, se muestra el ícono.
export function Logo() {
  const [ok, setOk] = useState(true);
  return ok
    ? <img src="/logo-hlf.png" alt="Hospital Clínico Dra. Eloísa Díaz Inzunza" className="h-10 lg:h-14 w-auto object-contain" onError={() => setOk(false)} />
    : <div className="w-9 h-11 rounded bg-primary text-on-primary flex items-center justify-center"><Icono n="local_hospital" className="text-[22px]" /></div>;
}

export const Indicador = ({ n, t, tono, onClick }) => {
  const c = tono === "rojo" ? "border-l-error text-error" : tono === "ambar" ? "border-l-ambar text-ambar" : tono === "azul" ? "border-l-primary text-primary" : "border-l-outline text-on-surface";
  return (
    <button onClick={onClick} disabled={!onClick} className={`text-left bg-surface-container-lowest border border-outline-variant border-l-4 rounded px-3 py-2 ${c} ${onClick ? "hover:bg-surface-container-low" : "cursor-default"}`}>
      <div className="text-[24px] font-semibold leading-tight">{n}</div><div className="text-[14px] text-on-surface-variant">{t}</div>
    </button>
  );
};
export const Filtro = ({ label, children }) => <label className="flex flex-col gap-1"><span className="text-on-surface-variant">{label}</span>{children}</label>;

export function EstadoRevision({ p }) {
  if (p.estado_revision === "requiere_revision") return <span className="text-ambar font-semibold">Requiere nueva revisión</span>;
  if (p.estado_revision === "pendiente") return <span className="text-on-surface-variant">Pendiente{p.revision_sugerida?.length ? " · revisión sugerida" : ""}</span>;
  return <span className="text-verde font-semibold">{p.estado_revision === "ajustado" ? "Ajustada" : "Confirmada"}{p.revision?.usuario && ` · ${p.revision.usuario}`}</span>;
}
