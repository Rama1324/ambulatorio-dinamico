import { Caja } from "../componentes/comunes";

export function Criterios({ ia }) {
  const filas = [["I50", "Insuficiencia cardíaca descompensada", "Alta", 85], ["I20", "Angina inestable", "Alta", 85],
    ["J44", "EPOC grave no controlado", "Alta", 95], ["J45", "Asma grave no controlada", "Alta", 95],
    ["K70", "Cirrosis hepática descompensada", "Alta", 95], ["E11", "DM2 descontrolada", "Media", 101],
    ["E03", "Hipotiroidismo sintomático", "Media", 94], ["G40", "Epilepsia con crisis mensuales", "Media", 103]];
  return (
    <div className="grid gap-5 lg:grid-cols-2 text-[14px] leading-relaxed">
      <Caja titulo="Cómo se ordena la lista">
        <ol className="list-decimal pl-5 space-y-2">
          <li><b>Prioridad (alta, media, baja).</b> Se parte de la prioridad asignada por el especialista al revisar la interconsulta. Si después el paciente presenta una descompensación (urgencia, hospitalización o evento grave) que no estaba en la interconsulta, la prioridad sube a la que indica la <i>Tabla de priorización SSMSO 2025, Hospital Dra. Eloísa Díaz</i> (págs. 84–111) para ese diagnóstico descompensado. Si llega un <b>cáncer confirmado o sospechoso</b>, sube a alta (todas las filas de cáncer activo de la tabla del HLF son alta). La lista se mueve sola: el sistema sube automáticamente, pero <b>nunca baja una prioridad por sí solo</b>; bajar lo decide el equipo clínico.</li>
          <li><b>Descompensación grave: requiere evaluación.</b> Evento grave sin estabilización posterior en un diagnóstico cuya fila de la tabla es prioridad alta. Va primero dentro de su prioridad y pide que el especialista revise su prioridad. El sistema no declara "riesgo vital": eso lo decide el médico. La alerta se cierra cuando el especialista revisa: una decisión clínica registrada, confirmar o ajustar la prioridad, o un ajuste manual de la posición (llamar o citar no la cierran).</li>
          <li><b>Orden dentro de cada prioridad</b> (MINSAL, Ord. 536 del 21-03-2025): criterio médico (primero la descompensación grave, luego cualquier paciente descompensado: va antes que un paciente estable aunque este pertenezca a un grupo de protección), grupos de especial protección (PRAIS, NNA bajo protección del Estado, Valech, Rettig), antigüedad en lista mayor a 1 año y fecha de ingreso. {ia
            ? <>No se usa ningún puntaje adicional: <b>sin LACE</b>, solo la cascada oficial.</>
            : <>El <b>puntaje LACE</b> es experimental: solo desempata a pacientes con la misma prioridad y antigüedad.</>}</li>
          <li><b>Observaciones</b> que no cambian el orden: posible incumplimiento GES (a verificar, porque el plazo corre desde un hito que el registro no trae); 2 inasistencias consecutivas (posible causal de egreso 8); HbA1c o PHQ-9 fuera de rango en dos mediciones seguidas. Los signos vitales (presión, saturación, glicemia capilar, dolor) no se usan como razón: cambian en minutos.</li>
          <li><b>Egreso por fallecimiento</b> (causal 9, Manual de Gestión de la Demanda SSMSO).</li>
        </ol>
      </Caja>
      <Caja titulo="Tabla HLF usada para pacientes descompensados">
        <table className="w-full text-[14px]">
          <thead><tr className="text-left text-on-surface-variant text-[13px] border-b border-outline-variant"><th className="py-1">CIE-10</th><th>Fila de la tabla</th><th>Prioridad</th><th>Pág.</th></tr></thead>
          <tbody>{filas.map(([c, f, pr, pg]) => <tr key={c} className="border-b border-outline-variant/50"><td className="py-1 font-semibold">{c}</td><td>{f}</td><td>{pr}</td><td>{pg}</td></tr>)}</tbody>
        </table>
        <p className="text-[13px] text-on-surface-variant mt-2">I10, K21, F32, F41, G43, E66, M17, M54 y M75 no tienen fila de "descompensado" en la tabla del HLF: mantienen su prioridad y el evento queda visible para revisión clínica.</p>
        <p className="text-[13px] font-semibold mt-3">Cáncer (informes, biopsias, epicrisis)</p>
        <table className="w-full text-[14px]">
          <tbody>
            {[["Broncopulmonar", "Cáncer de pulmón sospechoso", "Alta", "95"], ["Traumatología", "Osteosarcoma / tumores musculoesqueléticos", "Alta", "111"],
              ["Otras especialidades", "Toda fila de cáncer activo o sospechoso es alta (equivalencia a validar)", "Alta", "88, 94, 95, 111"],
              ["Cualquiera", "Antecedente de neoplasia en remisión", "Baja (no sube)", "102"]].map(([e, f, pr, pg]) => (
              <tr key={e + f} className="border-b border-outline-variant/50"><td className="py-1 font-semibold">{e}</td><td>{f}</td><td>{pr}</td><td>{pg}</td></tr>))}
          </tbody>
        </table>
        <p className="text-[13px] text-ambar mt-1"><b>Equivalencias a validar con los especialistas:</b> K70 (enfermedad hepática alcohólica) se asimila a la fila de cirrosis; I20 incluye toda angina, la fila es solo angina inestable; G40 usa la fila "crisis mensuales" porque no hay fila de epilepsia descompensada.</p>
        <p className="text-[13px] mt-1">Fuente: <a className="text-primary underline" target="_blank" rel="noreferrer" href="https://redsalud.ssmso.cl/wp-content/uploads/2025/07/PRIORIZACION-SSMSO-02.07.2025-I-ETAPA.pdf">Priorización SSMSO 2025 (PDF)</a></p>
      </Caja>
      <Caja titulo="Base oficial y evidencia (por qué el sistema decide así)">
        <ul className="list-disc pl-5 space-y-1.5">
          <li><b>El problema es real:</b> entre enero y junio de 2025 murieron 19.137 personas mientras esperaban en la lista No GES, 1.426 en la red SSMSO; el 92% esperaba su primera consulta de especialidad (MINSAL, informe Glosa 06, II trimestre 2026). El propio MINSAL dice que no puede saber si eran evitables porque la lista no tiene información clínica: eso es lo que agrega esta herramienta.</li>
          <li><b>Criterios por diagnóstico:</b> además de la tabla del HLF, se usan los criterios oficiales de Queensland (Australia, Clinical Prioritisation Criteria) para los 17 diagnósticos del registro, con emergencia y categorías 1/2/3 (≤30/90/365 días); salud mental desde NICE. Ejemplos que el sistema aplica solo con el registro: asma con UCI en los últimos 12 meses → alta; EPOC con más de 3 urgencias en 12 meses → media; HbA1c mayor a 10% que empeora → alta; cirrosis y reflujo nunca quedan en baja ("no category 3").</li>
          <li><b>Letalidad:</b> entre pacientes de la misma prioridad, va primero el evento más mortal (nivel 1: cirrosis descompensada, ACV, sepsis, fractura de cadera… · nivel 2: insuficiencia cardíaca, EPOC hospitalizada, infarto… · nivel 3 · nivel 4: daño irreversible sin alta mortalidad). Cada razón muestra la cifra y su estudio.</li>
          <li><b>Plazo de referencia:</b> si alguien supera el plazo de su prioridad (30/90/365 días), se muestra con su riesgo: en listas cardiológicas, los "no urgentes" acumularon más muertes porque esperaron más (OR 1,66).</li>
          <li><b>Cada razón dice qué puede pasar</b> y de dónde sale. Lo que no está verificado en una fuente oficial solo genera una alerta visible; nunca mueve a nadie.</li>
        </ul>
        <p className="text-[12px] text-on-surface-variant mt-2">Informe completo con fuentes: "Priorización clínica de listas de espera" (15-10-2026).</p>
      </Caja>
      <Caja titulo="El motivo del evento importa">
        <p>Una urgencia o una hospitalización solo sube la prioridad si es por <b>la enfermedad por la que el paciente espera</b> (o una complicación de ella). Una amputación por un accidente en un paciente que espera cardiología <b>no</b> cambia su prioridad de cardiología: queda como alerta para revisar si necesita otra derivación. Las urgencias se clasifican por triage: ESI 1-2 grave, ESI 3 moderada, ESI 4-5 leve (un dolor de dedo no sube a nadie). La IA lee el motivo y la relación en el informe; en las planillas se pueden cargar en las columnas <i>motivo</i> y <i>relacionado</i>.</p>
      </Caja>
      <Caja titulo="Combinaciones de riesgo: lo que juntas es más grave">
        <p className="mb-2">Una condición menor puede ser grave según quién la tenga. El sistema revisa <b>44 combinaciones</b> (35 con fuente oficial verificada; 9 solo como alerta) de una condición de base del paciente con un evento o hallazgo, cada una con su fuente: diabetes + lesión en el pie (pie diabético), anticoagulado + golpe en la cabeza, quimioterapia + fiebre, cáncer + dolor de espalda con debilidad, cirrosis + sangrado, adulto mayor + caída con dolor de cadera, embarazo + presión alta, insuficiencia renal + potasio alto, entre otras.</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>La IA marca la combinación copiando la frase; el código verifica que la base esté en el registro del paciente (o en una frase del texto), que el gatillo esté escrito y no negado, y que hable de lo que dice el gatillo.</li>
          <li>Efecto: <b>urgencia</b> (derivar hoy, primero en la lista) o <b>prioridad alta</b>. Nunca baja a nadie.</li>
          <li>Red de seguridad: si la IA ve una combinación peligrosa que no está en la lista, queda como <b>alerta visible</b> para el equipo.</li>
          <li>Entre pacientes descompensados de la misma prioridad, va primero el evento más grave: UCI o C1 antes que hospitalización o C2.</li>
          <li>Los <b>signos vitales</b> (presión, saturación, glicemia capilar, dolor) no justifican la prioridad: cambian en minutos.</li>
        </ul>
        <p className="text-[13px] text-on-surface-variant mt-2">Probado con Claude en 45 casos escritos a mano: 26 de 26 urgencias detectadas, 10 de 10 casos trampa sin falsa alarma (negaciones, paciente sin diabetes, aspirina sola, dolor de dedo).</p>
      </Caja>
      <Caja titulo="Criterios clínicos por enfermedad">
        <p className="mb-2">Para 46 enfermedades de Oftalmología, Otorrinolaringología, Psiquiatría, Reumatología y Urología hay criterios de prioridad <b>dentro</b> de cada enfermedad (no solo por diagnóstico): por ejemplo, hipoacusia gradual → media; hipoacusia súbita de menos de 72 h → <b>urgencia</b>. La IA lee el motivo de la interconsulta o el informe, elige el criterio y copia la frase que lo respalda; el código verifica la frase y aplica el nivel.</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>Solo <b>sube</b> la prioridad; si el criterio indica una menor, se mantiene (bajar lo decide el especialista).</li>
          <li>Si el texto no alcanza para decidir, <b>no se asigna baja</b>: queda la prioridad asignada.</li>
          <li>Las <b>excepciones de urgencia</b> ("derivar hoy": torsión testicular, desprendimiento de retina agudo, riesgo suicida con plan…) ponen al paciente primero, en alta y con "contactar hoy".</li>
        </ul>
        <p className="text-[13px] text-on-surface-variant mt-2">Probado con Claude en 154 notas clínicas (una por nivel de cada enfermedad y una por cada urgencia): 97,8 % del nivel correcto, 0 casos clasificados más bajo de lo que corresponde, 16 de 16 urgencias detectadas y ninguna urgencia falsa.</p>
      </Caja>
      {ia && <Caja titulo="Algoritmo con IA: la IA lee, el código decide">
        <ol className="list-decimal pl-5 space-y-2">
          <li><b>Lectura.</b> Un modelo de IA (Claude, en Amazon Bedrock) lee el historial del paciente <b>3 veces</b> y responde preguntas cerradas (¿hubo descompensación?, ¿se estabilizó después?, ¿empeora su medición clave?, ¿cambió el tratamiento por mal control?), citando cada registro. La IA no asigna prioridades.</li>
          <li><b>Verificación.</b> El código comprueba en el registro cada cita: que exista, que sea de verdad una descompensación, que la estabilización sea posterior y que la medición realmente empeore (con los valores registrados, no los que escribe la IA).</li>
          <li><b>Fórmula fija.</b> Con lo verificado, la prioridad sale de la tabla del HLF. Un evento sigue vigente durante su ventana con evidencia publicada (PubMed); sin evidencia, no vence.</li>
          <li><b>Controles.</b> Si la IA no puede leer un dato, lo responde el registro. Si una cita no existe o no respalda lo dicho, las 3 lecturas no coinciden o la IA falla, se usan las reglas <b>sin pedirle nada a nadie</b>. Solo cuando la evidencia indica que un paciente podría <b>bajar</b> de prioridad, el sistema no lo baja: lo deja como está y avisa al especialista (en este registro, 3 de 409 pacientes).</li>
          <li><b>Cuándo.</b> Al llegar un paciente, un evento o un informe, la lista se recalcula al instante. Un barrido nocturno revisa al resto.</li>
        </ol>
        <p className="text-[13px] text-on-surface-variant mt-2">Probado con 409 pacientes y 2.454 lecturas reales: 0 lecturas fallidas, 3 lecturas iguales en el 100 % de los pacientes, nadie baja sin una persona y solo 3 pacientes requieren al especialista. Cuando la IA decidía sola, concordaba con la tabla oficial apenas κ 0,09; por eso decide la fórmula.</p>
      </Caja>}
      {!ia && <Caja titulo="Puntaje LACE (experimental, solo desempate)">
        <p className="mb-2">Índice validado para riesgo de muerte o reingreso no planificado tras un alta hospitalaria (<a className="text-primary underline" target="_blank" rel="noreferrer" href="https://pmc.ncbi.nlm.nih.gov/articles/PMC2845681/">van Walraven et al., <i>CMAJ</i> 2010;182(6):551-7</a>). Estadístico C 0,68–0,71 en Ontario. <b>No está validado para listas de espera</b>: por eso aquí solo desempata.</p>
        <table className="w-full text-[14px]">
          <tbody className="divide-y divide-outline-variant/60">
            <tr><td className="py-1 font-semibold w-8">L</td><td>Días de estada: &lt;1 = 0 · 1 = 1 · 2 = 2 · 3 = 3 · 4–6 = 4 · 7–13 = 5 · ≥14 = 7 <span className="text-on-surface-variant">(sin dato en el registro → 0)</span></td></tr>
            <tr><td className="py-1 font-semibold">A</td><td>Ingreso de urgencia = 3 (hospitalización en los últimos 6 meses)</td></tr>
            <tr><td className="py-1 font-semibold">C</td><td>Charlson: 0 = 0 · 1 = 1 · 2 = 2 · 3 = 3 · ≥4 = 5. Pesos: insuficiencia cardíaca 2 · enfermedad pulmonar crónica 2 · hepática leve 2 · diabetes sin complicaciones 1 (CIE-10 según Quan 2005)</td></tr>
            <tr><td className="py-1 font-semibold">E</td><td>Consultas en urgencia en 6 meses: 0–3 = mismo número · ≥4 = 4</td></tr>
          </tbody>
        </table>
        <p className="text-[13px] text-on-surface-variant mt-2">Validación en este registro (datos sintéticos): a más puntos, más eventos en los 90 días siguientes (LACE 0: 11% · 2: 14% · 3: 17%), con discriminación baja (AUC 0,54). Debe recalibrarse con datos reales del HLF.</p>
      </Caja>}
      <Caja titulo="Garantías GES · atención por especialista">
        <p>Depresión (N°34): 30 días · Hipertensión (N°21): 45 · EPOC (N°38): 45 · Diabetes tipo 2 (N°7): 60 · Asma (N°61): 60 · Epilepsia (N°60): 60 · Artrosis de rodilla, 55 años o más (N°41): 120.</p>
        <p className="text-[13px] text-on-surface-variant mt-1">El plazo corre desde la derivación con sospecha o confirmación diagnóstica; el registro solo trae el ingreso a la lista, así que la herramienta marca "posible incumplimiento: verificar". Fuente: <a className="text-primary underline" target="_blank" rel="noreferrer" href="https://auge.minsal.cl">auge.minsal.cl</a></p>
      </Caja>
      <Caja titulo="Lectura automática de informes">
        {ia
          ? <p>Las fotos se leen con Amazon Textract (OCR). La IA lee el informe 3 veces y lista los hallazgos (cáncer confirmado o sospechoso, hospitalización, UCI, descompensación, examen alterado, cambio de tratamiento) <b>copiando la frase del documento</b>. El código verifica que la frase esté en el texto; lo que aparece en las 3 lecturas y no puede bajar a nadie <b>se registra solo y la lista se recalcula</b>. Si hay una negación cerca ("se descarta neoplasia"), si las lecturas no coinciden, si el documento podría ser de otro paciente o si el hallazgo podría bajar una prioridad (estabilización), lo confirma el equipo clínico. Un cáncer en remisión no sube (tabla pág. 102).</p>
          : <p>Las fotos de informes se leen con Amazon Textract (OCR). Reglas con detección de negaciones buscan urgencias, hospitalizaciones, exámenes alterados y cambios de fármaco, y cada propuesta se valida con Pydantic, citando la frase exacta del documento. Se verifica que el documento sea del paciente. Ninguna prioridad cambia sin confirmación del equipo clínico. No se hacen predicciones: las alertas se basan en eventos ya registrados.</p>}
      </Caja>
      <Caja titulo="Datos de esta demostración">
        <p>Registro sintético entregado por el hospital: 500 pacientes, 7 especialidades, eventos hasta el 13-10-2026. No contiene pacientes reales. La versión publicada trabaja con la fecha de hoy en Chile; el modo demostración permite ver la lista en fechas anteriores.</p>
      </Caja>
    </div>
  );
}
