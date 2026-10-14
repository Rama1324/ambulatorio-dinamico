import { Caja } from "../components/ui";

export function Criterios() {
  const filas = [["I50", "Insuficiencia cardíaca descompensada", "Alta", 85], ["I20", "Angina inestable", "Alta", 85],
    ["J44", "EPOC grave no controlado", "Alta", 95], ["J45", "Asma grave no controlada", "Alta", 95],
    ["K70", "Cirrosis hepática descompensada", "Alta", 95], ["E11", "DM2 descontrolada", "Media", 101],
    ["E03", "Hipotiroidismo sintomático", "Media", 94], ["G40", "Epilepsia con crisis mensuales", "Media", 103]];
  return (
    <div className="grid gap-5 lg:grid-cols-2 text-[14px] leading-relaxed">
      <Caja titulo="Cómo se ordena la lista">
        <ol className="list-decimal pl-5 space-y-2">
          <li><b>Prioridad (alta, media, baja).</b> Se parte de la prioridad asignada por el especialista al revisar la interconsulta. Si después el paciente presenta una descompensación (urgencia, hospitalización o evento grave) que no estaba en la interconsulta, la prioridad sube a la que indica la <i>Tabla de priorización SSMSO 2025, Hospital Dra. Eloísa Díaz</i> (págs. 84–111) para ese diagnóstico descompensado. El sistema nunca baja una prioridad por sí solo.</li>
          <li><b>Contactar hoy.</b> Descompensación grave sin estabilización posterior en un diagnóstico de prioridad alta. Corresponde al criterio de criticidad / riesgo vital de MINSAL (SSMSO 2025, pág. 4).</li>
          <li><b>Orden dentro de cada prioridad</b> (MINSAL, Ord. 536 del 21-03-2025): criterio médico, grupos de especial protección (sin datos en este registro), antigüedad en lista mayor a 1 año y, finalmente, fecha de ingreso. Como criterio médico se usa además el <b>puntaje LACE</b> (más puntos, antes).</li>
          <li><b>Observaciones</b> que no cambian el orden: garantía GES vencida; 2 inasistencias consecutivas (posible causal de egreso 8); última medición fuera de rango.</li>
          <li><b>Egreso por fallecimiento</b> (causal 9, Manual de Gestión de la Demanda SSMSO).</li>
        </ol>
      </Caja>
      <Caja titulo="Tabla HLF usada para pacientes descompensados">
        <table className="w-full text-[14px]">
          <thead><tr className="text-left text-on-surface-variant text-[14px] border-b border-outline-variant"><th className="py-1">CIE-10</th><th>Fila de la tabla</th><th>Prioridad</th><th>Pág.</th></tr></thead>
          <tbody>{filas.map(([c, f, pr, pg]) => <tr key={c} className="border-b border-outline-variant/50"><td className="py-1 font-semibold">{c}</td><td>{f}</td><td>{pr}</td><td>{pg}</td></tr>)}</tbody>
        </table>
        <p className="text-[14px] text-on-surface-variant mt-2">I10, K21, F32, F41, G43, E66, M17, M54 y M75 no tienen fila de "descompensado" en la tabla del HLF: mantienen su prioridad y el evento queda visible para revisión clínica.</p>
      </Caja>
      <Caja titulo="Puntaje de riesgo LACE (puntos publicados)">
        <p className="mb-2">Índice validado para riesgo de muerte o reingreso no planificado (van Walraven et al., <i>CMAJ</i> 2010;182(6):551-7). Estadístico C 0,68–0,71 en Ontario.</p>
        <table className="w-full text-[14px]">
          <tbody className="divide-y divide-outline-variant/60">
            <tr><td className="py-1 font-semibold w-8">L</td><td>Días de estada: &lt;1 = 0 · 1 = 1 · 2 = 2 · 3 = 3 · 4–6 = 4 · 7–13 = 5 · ≥14 = 7 <span className="text-on-surface-variant">(sin dato en el registro → 0)</span></td></tr>
            <tr><td className="py-1 font-semibold">A</td><td>Ingreso de urgencia = 3 (hospitalización en los últimos 6 meses)</td></tr>
            <tr><td className="py-1 font-semibold">C</td><td>Charlson: 0 = 0 · 1 = 1 · 2 = 2 · 3 = 3 · ≥4 = 5. Pesos: insuficiencia cardíaca 2 · enfermedad pulmonar crónica 2 · hepática leve 2 · diabetes sin complicaciones 1 (CIE-10 según Quan 2005)</td></tr>
            <tr><td className="py-1 font-semibold">E</td><td>Consultas en urgencia en 6 meses: 0–3 = mismo número · ≥4 = 4</td></tr>
          </tbody>
        </table>
        <p className="text-[14px] text-on-surface-variant mt-2">Validación en este registro (datos sintéticos): a más puntos, más eventos en los 90 días siguientes (LACE 0: 11% · 2: 14% · 3: 17%), con discriminación baja (AUC 0,54). Debe recalibrarse con datos reales del HLF.</p>
      </Caja>
      <Caja titulo="Garantías GES · atención por especialista">
        <p>Depresión (N°34): 30 días · Hipertensión (N°21): 45 · EPOC (N°38): 45 · Diabetes tipo 2 (N°7): 60 · Asma (N°61): 60 · Epilepsia (N°60): 60 · Artrosis de rodilla, 55 años o más (N°41): 120.</p>
      </Caja>
      <Caja titulo="Lectura automática de informes">
        <p>Los informes escritos o fotografiados se leen automáticamente (Amazon Bedrock) solo para proponer el evento, citando la frase del documento. Ninguna prioridad cambia sin confirmación del equipo clínico. No se hacen predicciones: las alertas se basan en eventos ya registrados.</p>
      </Caja>
    </div>
  );
}
