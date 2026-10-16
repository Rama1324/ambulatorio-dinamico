

export const fmt = (iso) => (iso ? iso.slice(0, 10).split("-").reverse().join("-") : "");

// Cuánto hace que pasó algo, respecto de la fecha de la lista: "hoy", "ayer", "hace 20 días", "hace 3 meses".
export function hace(iso, ref) {
  if (!iso || !ref) return "";
  const n = Math.round((new Date(ref.slice(0, 10) + "T12:00:00") - new Date(iso.slice(0, 10) + "T12:00:00")) / 864e5);
  if (n <= 0) return "hoy";
  if (n === 1) return "ayer";
  if (n <= 90) return `hace ${n} días`;
  const m = Math.round(n / 30.4);
  return m < 24 ? `hace ${m} meses` : `hace ${Math.round(n / 365)} años`;
}
export const fmtHace = (iso, ref) => (iso ? `${fmt(iso)} (${hace(iso, ref)})` : "");

// Búsqueda que ignora tildes y mayúsculas ("hipertension" encuentra "Hipertensión") y busca también por código CIE-10,
// ID y RUT con o sin puntos y guion.
const sinTildes = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
export function coincide(p, busca) {
  const q = sinTildes(busca).trim();
  if (!q) return true;
  const qRut = q.replace(/[.\-\s]/g, "");
  return [p.nombre_fantasia, p.id_paciente, p.diagnostico_texto, p.diagnostico_cie10, p.especialidad, p.comuna, p.rut]
    .some((x) => sinTildes(x).includes(q)) || (qRut.length >= 4 && sinTildes(p.rut).replace(/[.-]/g, "").includes(qRut));
}
