// "Lo que la lista de hoy no ve": dónde estarían los pacientes que empeoraron si la lista siguiera ordenada solo por la
// prioridad asignada al ingresar y el orden de llegada (como funciona hoy), y dónde los pone el sistema. Se calcula con la
// misma lista que se está viendo (misma especialidad, misma fecha): no son números escritos a mano.
const RANGO = { alta: 0, media: 1, baja: 2 };
const NARANJO = "#c4662a", AZUL = "#2a6fdb";

function mediana(xs) {
  const v = [...xs].sort((a, b) => a - b);
  return v.length ? (v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2) : null;
}

const Tarjeta = ({ titulo, antes, ahora, sub, borde, onClick }) => {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick} className={`text-left rounded border border-outline-variant bg-surface-container-lowest p-3 border-l-4 ${borde} ${onClick ? "hover:bg-primary/5" : ""}`}>
      <div className="text-[13px] text-on-surface-variant">{titulo}</div>
      <div className="text-[28px] font-bold leading-tight">{antes != null && <><span className="text-on-surface-variant">{antes}</span> → </>}{ahora}</div>
      <div className="text-[12px] text-on-surface-variant">{sub}</div>
    </Tag>
  );
};

export function LoQueNoVe({ data, esp, onVer }) {
  const ps = data?.pacientes || [];
  if (!ps.length) return null;
  const estatica = [...ps].sort((a, b) => RANGO[a.prioridad_inicial] - RANGO[b.prioridad_inicial]
    || a.fecha_ingreso_lista.localeCompare(b.fecha_ingreso_lista) || a.id_paciente.localeCompare(b.id_paciente));
  const posEst = Object.fromEntries(estatica.map((p, i) => [p.id_paciente, i + 1]));
  const empeoraron = ps.filter((p) => p.riesgo_vital || p.estado_clinico === "descompensado" || RANGO[p.categoria] < RANGO[p.prioridad_inicial])
    .map((p) => ({ ...p, antes: posEst[p.id_paciente], ahora: p.posicion })).sort((a, b) => a.ahora - b.ahora);
  if (!empeoraron.length) return null;
  const n = ps.length, top10 = Math.max(1, Math.round(n * 0.1));
  const enTopAntes = empeoraron.filter((p) => p.antes <= top10).length, enTopAhora = empeoraron.filter((p) => p.ahora <= top10).length;
  const subieron = empeoraron.filter((p) => RANGO[p.categoria] < RANGO[p.prioridad_inicial]).length;
  const mayor = [...empeoraron].sort((a, b) => (b.antes - b.ahora) - (a.antes - a.ahora))[0];
  const muestra = empeoraron.slice(0, 15);
  const W = 1000, fila = 26, x0 = 250, x1 = W - 30, H = 44 + muestra.length * fila;
  const X = (pos) => x0 + ((pos - 1) / Math.max(1, n - 1)) * (x1 - x0);
  const alcance = esp === "Todas" ? "todo el hospital" : esp;
  const marcas = [...new Set([1, Math.round(n / 4), Math.round(n / 2), Math.round((3 * n) / 4), n])];

  return (
    <section className="flex flex-col gap-3">
      <div className="border-b border-outline-variant pb-1.5">
        <h2 className="text-[18px] font-semibold">Lo que la lista de hoy no ve</h2>
        <p className="text-[13px] text-on-surface-variant">Hoy la lista se ordena por la prioridad asignada al ingresar y el orden de llegada, y no cambia si el paciente
          empeora. Esta comparación usa los mismos {n} pacientes de {alcance} y los datos de hoy.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Tarjeta titulo="Empeoraron mientras esperaban" ahora={empeoraron.length} borde="border-l-error"
          sub={`urgencia, hospitalización o informe después de la interconsulta · ${subieron} subieron de prioridad`} />
        <Tarjeta titulo="Su puesto mediano" antes={`N° ${Math.round(mediana(empeoraron.map((p) => p.antes)))}`}
          ahora={`N° ${Math.round(mediana(empeoraron.map((p) => p.ahora)))}`} borde="border-l-primary" sub="con la lista de hoy → con el sistema" />
        <Tarjeta titulo={`En los primeros ${top10} puestos (10 %)`} antes={enTopAntes} ahora={enTopAhora} borde="border-l-primary"
          sub={`de los ${empeoraron.length} que empeoraron`} />
        {mayor && <Tarjeta titulo="Mayor salto" antes={`N° ${mayor.antes}`} ahora={`N° ${mayor.ahora}`} borde="border-l-hlf"
          sub={`${mayor.nombre_fantasia} · ${mayor.diagnostico_texto} · ver ficha`} onClick={() => onVer?.(mayor.id_paciente)} />}
      </div>
      <figure className="rounded border border-outline-variant bg-surface-container-lowest p-3">
        <figcaption className="text-[13px] font-semibold mb-1">Puesto de cada paciente que empeoró</figcaption>
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Puesto de cada paciente con la lista de hoy y con el sistema">
          {marcas.map((t) => (
            <g key={t}>
              <line x1={X(t)} x2={X(t)} y1={18} y2={H - 6} stroke="rgb(var(--c-divider))" strokeWidth="1" />
              <text x={X(t)} y={12} fontSize="10" textAnchor="middle" fill="rgb(var(--c-muted))">N° {t}</text>
            </g>
          ))}
          {muestra.map((p, i) => {
            const y = 32 + i * fila;
            return (
              <g key={p.id_paciente} className="cursor-pointer" onClick={() => onVer?.(p.id_paciente)}>
                <title>{`${p.nombre_fantasia} · ${p.diagnostico_texto}: lista de hoy N° ${p.antes} → sistema N° ${p.ahora}`}</title>
                <rect x={0} y={y - fila / 2} width={W} height={fila} fill="transparent" />
                <text x={x0 - 10} y={y + 4} fontSize="11" textAnchor="end" fill="rgb(var(--c-muted))">{p.diagnostico_texto.slice(0, 26)} · {p.id_paciente.slice(-5)}</text>
                <line x1={X(p.antes)} x2={X(p.ahora)} y1={y} y2={y} stroke="rgb(var(--c-muted))" strokeWidth="1.5" />
                <circle cx={X(p.antes)} cy={y} r="5" fill={NARANJO} stroke="white" strokeWidth="1.5" />
                <circle cx={X(p.ahora)} cy={y} r="5" fill={AZUL} stroke="white" strokeWidth="1.5" />
              </g>
            );
          })}
        </svg>
        <p className="text-[12px] text-on-surface-variant mt-1">
          <span style={{ color: NARANJO }}>●</span> Lista de hoy (prioridad al ingresar + orden de llegada) · <span style={{ color: AZUL }}>●</span> Ambulatorio Dinámico.
          {empeoraron.length > muestra.length ? ` Se muestran los ${muestra.length} primeros de ${empeoraron.length}.` : ""} Clic en un paciente para ver su ficha.</p>
      </figure>
    </section>
  );
}
