

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
