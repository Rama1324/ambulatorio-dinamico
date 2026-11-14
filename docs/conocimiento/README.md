# Base de conocimiento versionada y trazable

Qué versión de cada fuente médica está vigente, qué sabe y aplica el sistema para cada diagnóstico y qué fuentes
respaldan cada decisión. Contrato: `docs/diseno/ESPECIFICACION_MVP.md` §4.

| Pieza | Para qué |
|---|---|
| `lambda/conocimiento/*.json` | Las fuentes: tabla SSMSO/HLF, Ord. 536, GES, criterios, combinaciones, evidencia. Cada una trae su `version`. |
| `lambda/conocimiento/manifiesto.json` | Registro único: versión y huella de cada fuente, huella del código con reglas, etiqueta del paquete. **Se genera, no se edita.** |
| `scripts/empaquetar_conocimiento.py` | Genera el manifiesto y lo verifica (`--verificar`, para CI). |
| `lambda/base_conocimiento.py` | Servicio de consulta: `paquete()`, `fuentes()`, `para_diagnostico()`, `fuentes_de()`, rutas `GET /conocimiento…`. |
| `tests/test_conocimiento.py` | Falla si un archivo cambia y el manifiesto no. |

## 1. Qué resuelve

La información médica del sistema está en diez JSON y en constantes del código. Cada JSON trae una `version` escrita a
mano, pero no había un registro de qué versiones están vigentes, nada impedía cambiar un archivo sin cambiar su versión
(pasó varias veces: §8) y una decisión no podía decir con exactitud qué usó.

Ahora:
- **Un manifiesto** anota la versión y la huella (sha256) de cada fuente y de cada archivo de código que contiene reglas.
- **Un test** falla si un archivo cambia y el manifiesto no. **El script no acepta** una fuente cuyo contenido cambió con
  la misma versión.
- **Cada decisión** puede guardar el paquete vigente y las fuentes exactas (id, versión, huella y entrada) que respaldan
  sus razones.
- **Una consulta por diagnóstico** muestra todo lo que el sistema sabe y aplica, cada bloque con su fuente y versión.

El servicio no decide nada ni repite reglas: lee lo mismo que lee el motor (`puntaje.py`, `decisor.py`, `criterios.py`,
`combinaciones.py`), con sus mismas funciones.

## 2. Fuentes vigentes

<!-- fuentes:inicio · lo escribe scripts/empaquetar_conocimiento.py; no editar a mano -->
Paquete vigente: **`kb-2026.11.0`** · huella `6c8d773f352c` · motor `614c8bb2289b` · generado 2026-11-14T15:34:24+00:00

| Fuente (`id`) | Qué es | Versión | Estado | Entradas | Quién la usa |
|---|---|---|---|---|---|
| `ssmso_hlf_2025` | Tabla de priorización SSMSO 2025, sección HLF: fila que se usa si un diagnóstico del registro se descompensa | `ssmso_hlf_2025_v1` | verificado en la fuente | 17 | `scripts/consolidar_rubrica.py` |
| `diagnosticos_tabla_hlf` | Tabla de priorización SSMSO 2025, sección HLF: diagnósticos y síntomas de las 7 especialidades (códigos HLF-…) | `tabla_hlf_2025_v1` | verificado en la fuente | 174 | `puntaje.py` |
| `ord536` | MINSAL Ord. C N°536 (21-03-2025): orden de la lista de espera No GES | `ord536_v1` | fuente secundaria | 4 | `scripts/consolidar_rubrica.py` |
| `ges_especialista` | Garantías GES de oportunidad para la atención por especialista (Ley 19.966) | `ges_especialista_v1` | verificado en la fuente | 8 | `puntaje.py` |
| `criterios_registro` | Criterios oficiales por diagnóstico del registro (Queensland CPC y NICE) | `criterios_registro_v1` | verificado en la fuente | 16 | `criterios.py`, `puntaje.py` |
| `criterios_especialidad` | Criterios clínicos por enfermedad y especialidad (dataset aportado al equipo) | `1.0` | origen no confirmado: solo sube | 46 | `criterios.py` |
| `combinaciones_riesgo` | Combinaciones de riesgo: condición de base del paciente + evento o hallazgo | `combinaciones_v2` | verificado en parte | 44 | `combinaciones.py` |
| `pubmed_evidencia` | Ventanas de riesgo tras un evento (PubMed) | `evidencia_v1` | verificado en parte | 24 | `scripts/buscar_pubmed.py`, `scripts/consolidar_rubrica.py` |
| `guias_umbrales` | Umbrales de las mediciones clave (guías MINSAL e internacionales) | `evidencia_v1` | verificado en parte | 24 | `scripts/buscar_pubmed.py`, `scripts/consolidar_rubrica.py` |
| `rubrica_v1` | Rúbrica consolidada que lee la fórmula: tabla, Ord. 536, ventanas y umbrales | `rubrica_v1.2` | consolidado de otras fuentes | 17 | `decisor.py`, `scripts/consolidar_rubrica.py` |
<!-- fuentes:fin -->

Las fuentes van en orden de autoridad (`docs/CRITERIO_PRIORIZACION.md` §3). El detalle de cada una (origen, URL, fecha,
método de verificación, cuántas entradas están verificadas) está en el manifiesto y en `GET /conocimiento`.
"Quién la usa" sale del código (qué módulo nombra el archivo), no de una lista escrita a mano. Las cuatro fuentes que
solo usa `scripts/consolidar_rubrica.py` llegan al motor a través de `rubrica_v1` (campo `derivada_de`); las filas de
`ssmso_hlf_2025` están además como constante en `puntaje.FILA_DESCOMPENSADO`, y un test exige que coincidan.

**Estados.** No se inventan: salen del propio JSON (campos `estado`, `fuente`, `metodo`) y de
`docs/CRITERIO_PRIORIZACION.md` §3.

| Estado | Significa |
|---|---|
| verificado en la fuente | El texto se leyó en el documento oficial (página, cita textual o URL por entrada). |
| verificado en parte | Unas entradas tienen fuente verificada y otras no. Las que no, **no mueven a nadie**: solo alertan o quedan "a validar por médico". El conteo va en `estado_detalle`. |
| fuente secundaria | Se cita a través de otro documento (el Ord. 536, desde el Manual de Gestión de la Demanda SSMSO). |
| origen no confirmado: solo sube | Dataset aportado al equipo, sin validación externa. Puede subir una prioridad, nunca bajarla. |
| consolidado de otras fuentes | Archivo generado a partir de otras fuentes del manifiesto (`derivada_de`). |

**Lo que vive en el código (el "motor").** Parte de las reglas son constantes de `puntaje.py` (fila de descompensación
por diagnóstico, regla oncológica, letalidad, plazo de referencia, LACE…). El manifiesto guarda:
- la huella de los 8 archivos con reglas o prompts (`puntaje`, `decisor`, `controles`, `algoritmo`, `rubrica`,
  `criterios`, `combinaciones`, `lector_documento`);
- cada **constante clínica** con la huella de su valor y su `fuente`, que es el comentario que la explica en el código.
  Se leen del código fuente (no se copian): si alguien cambia una constante o su comentario, cambia el manifiesto;
- las **reglas de `puntaje.aplicar_registro`** (p. ej. "HbA1c > 10 % con deterioro reciente → alta"), también leídas
  del código.

## 3. Cómo se versiona

| Nivel | Identificador | Cambia cuando |
|---|---|---|
| Fuente | `version` (dentro del JSON) + `sha256` | Cambia el contenido del JSON. **Obligatorio subir la versión**: el script no regenera si el contenido cambió y la versión no. |
| Motor | `huella` (12 caracteres) | Cambia cualquiera de los 8 archivos con reglas. No lleva versión a mano. |
| Paquete | `etiqueta` `kb-AAAA.MM.N` + `huella` (12 caracteres) | La huella cambia con cualquier fuente o archivo del motor. La etiqueta se sube a mano en cada despliegue que cambia fuentes. |

- **La huella no depende del formato.** De un JSON se calcula sobre su contenido canónico (claves ordenadas, sin
  espacios); de un `.py`, sobre el texto con saltos de línea `\n`. Reindentar un JSON o bajar el repo en Windows (CRLF)
  no cambia nada; cambiar un número, sí. Por eso no coincide con `sha256sum archivo`: para comprobar una huella,
  `python scripts/empaquetar_conocimiento.py --huella lambda/conocimiento/ord536.json`.
- **`huella` del paquete** = sha256 corto de todas las huellas (fuentes y archivos del motor) ordenadas. Dos despliegues
  con la misma huella aplican exactamente el mismo conocimiento.
- **`generado`** solo cambia cuando cambia algo: regenerar sin cambios no toca el archivo.
- **En ejecución** el servicio recalcula las huellas de los archivos desplegados y las compara con el manifiesto. Lo
  que informa (y lo que queda en cada decisión) es lo que hay en disco; si no coincide, `paquete.integro` es `false` y
  `GET /conocimiento` lista las diferencias. El despliegue es manual, así que este es el control que queda en producción.

## 4. Procedimiento para cambiar una fuente

Lo hace el equipo médico junto con quien integra. Todo queda en un commit: el cambio, quién lo pidió y con qué respaldo.

1. **Editar** el JSON en `lambda/conocimiento/` (una fila, un plazo, un criterio, una combinación). Cada entrada nueva
   lleva su fuente: página, cita textual, URL o PMID. Si no hay fuente, se marca `a_validar_por_medico` o
   `sin_verificar` (y entonces no mueve a nadie).
2. **Subir la `version`** de ese JSON (p. ej. `ges_especialista_v1` → `ges_especialista_v2`) y su fecha.
3. Si se cambió `ssmso_hlf_2025`, `ord536`, `pubmed_evidencia` o `guias_umbrales`: **regenerar la rúbrica** con
   `python scripts/consolidar_rubrica.py` (y subir su versión, que está escrita dentro de ese script).
4. **Regenerar el manifiesto** con la etiqueta nueva del paquete:
   `python scripts/empaquetar_conocimiento.py --etiqueta kb-2026.11.1`
   El script lista qué cambió y actualiza la tabla de este README.
5. **Correr los tests**: `python -X utf8 -m pytest -q tests`. Fallan si el manifiesto no corresponde a los archivos, si
   la rúbrica no corresponde a sus fuentes o si una constante del código contradice la tabla.
6. **Revisión**: un PR con el diff del JSON y del manifiesto. Lo aprueba un médico (el contenido) y alguien del equipo
   técnico (que la versión subió y los tests pasan).
7. **Despliegue**: antes de publicar, `python scripts/empaquetar_conocimiento.py --verificar` (sale con 1 si algo no
   corresponde). Después, `GET /conocimiento` debe mostrar la etiqueta nueva y `integridad.integro: true`.

Si se cambia una **regla del código** (un archivo del motor), basta el paso 4 sin etiqueta nueva, más 5 a 7: la huella
del motor y la del paquete cambian solas.

Lo que **no** va por este camino: los criterios locales que nacen de la revisión de los especialistas. Esos viven en
DynamoDB, los aprueba la jefatura desde la aplicación (ESPECIFICACION_MVP §6) y se suman a esta consulta con
`registrar_capa_local`.

## 5. Qué queda registrado en cada decisión

Cada razón ya trae su `fuente` en texto (p. ej. "Tabla SSMSO 2025, HLF, pág. 85"). El dictamen (ESPECIFICACION_MVP §5)
guarda además, en `informacion_utilizada.conocimiento`, el paquete y las fuentes. Ejemplo real (PAC-HLF-00002 al
13-10-2026, con las reglas; títulos y huellas recortados):

```json
{
  "paquete": {"etiqueta": "kb-2026.11.0", "huella": "…12…", "integro": true},
  "fuentes": [
    {"id": "diagnosticos_tabla_hlf", "titulo": "Tabla de priorización SSMSO 2025, sección HLF: …", "tipo": "tabla_oficial",
     "version": "tabla_hlf_2025_v1", "sha256": "…64…", "factores": ["riesgo_vital", "tabla_oficial"], "claves": ["HLF-CAR-01"]},
    {"id": "ssmso_hlf_2025", "titulo": "…", "tipo": "tabla_oficial", "version": "ssmso_hlf_2025_v1", "sha256": "…64…",
     "factores": ["riesgo_vital", "tabla_oficial"], "claves": ["I20"]},
    {"id": "motor", "titulo": "Reglas y constantes escritas en el código (motor de priorización)", "tipo": "motor",
     "version": "…12…", "sha256": "…64…", "factores": ["riesgo_vital", "tabla_oficial", "lace", "plazo"],
     "claves": ["puntaje.FILA_DESCOMPENSADO", "regla de descompensación grave", "puntaje.LETALIDAD_DX", "puntaje.indice_lace", "puntaje.PLAZO_CATEGORIA"]},
    {"id": "registro_paciente", "titulo": "Registro del paciente: prioridad inicial de la SIC, eventos y mediciones del hospital",
     "tipo": "registro", "version": null, "sha256": null, "factores": ["prioridad_inicial", "evento"],
     "claves": ["prioridad inicial de la SIC", "eventos clínicos"]},
    {"id": "ord536", "titulo": "…", "tipo": "norma", "version": "ord536_v1", "sha256": "…64…", "factores": ["dias_espera"],
     "claves": ["antiguedad_mayor_1_anio"]},
    {"id": "criterios_registro", "titulo": "…", "tipo": "criterios_clinicos", "version": "criterios_registro_v1", "sha256": "…64…",
     "factores": ["plazo"], "claves": []}
  ]
}
```

- `paquete` = `base_conocimiento.paquete()`; `fuentes` = `base_conocimiento.fuentes_de(razones)`.
- `factores`: qué razones de la decisión respalda esa fuente. `claves`: la entrada exacta que se usó (fila de la tabla,
  problema GES, enfermedad, combinación, PMID, constante del código).
- La fila de la tabla se cita con sus transcripciones (`diagnosticos_tabla_hlf`, `ssmso_hlf_2025`) y con el lugar de
  donde la leyó el motor: `rubrica_v1` si decidió la fórmula (modo con IA) o la constante `puntaje.FILA_DESCOMPENSADO`
  si decidieron las reglas. `fuentes_de` lo deduce de las razones; también acepta `motor=` con el valor del dictamen.
- Además de las fuentes del manifiesto aparecen tres que no son archivos: `motor` (lo que vive en el código),
  `registro_paciente` (la prioridad inicial de la SIC y los hechos del paciente) y `criterios_locales`. Una razón con
  un factor desconocido queda en `sin_catalogar`, a la vista; un test exige que todos los factores del motor estén
  catalogados.

**Auditar una decisión antigua.** Con la `huella` del paquete se llega al commit exacto:
`git log -S"<huella>" -- lambda/conocimiento/manifiesto.json`. Ese commit tiene los JSON y el código tal como se
aplicaron. Con el `sha256` de una fuente se confirma que el archivo es el mismo (`--huella`).

## 6. Consultar el conocimiento

```python
import base_conocimiento as bc
bc.paquete()                  # {"etiqueta", "huella", "generado", "integro", "motor": {"huella", "archivos"}}
bc.fuentes()                  # el manifiesto: una ficha por fuente
bc.motor()                    # archivos, constantes clínicas con su fuente y reglas leídas del código
bc.integridad()               # {"integro", "diferencias"}
bc.para_diagnostico("I20")    # todo lo que el sistema sabe y aplica; None si no hay nada específico
bc.fuentes_de(razones)        # fuentes que respaldan esas razones
bc.registrar_capa_local(fn)   # fn(cie10) -> list[dict]: criterios locales vigentes para ese diagnóstico
bc.rutear(method, partes, qs, body)   # GET /conocimiento · GET /conocimiento/diagnostico/{cie10} · None para lo demás
```

`GET /conocimiento` devuelve `{paquete, fuentes, motor, capa_local, integridad, avisos}`: lo vigente, si los archivos
desplegados corresponden al manifiesto y la deuda conocida de las fuentes (§8).

`para_diagnostico` (y `GET /conocimiento/diagnostico/{cie10}`) acepta un CIE-10 del registro (`I20`, `e11.9`) o un
código de la tabla (`HLF-CAR-01`); para un código del que no hay nada específico devuelve `None` (404). Bloques, cada
uno con `fuente: {id, version}` (más `clave` cuando se conoce la entrada exacta):

| Bloque | Qué trae | De dónde |
|---|---|---|
| `tabla` | Fila propia (códigos `HLF-…`: prioridad, página, verificación) y otras filas de la misma enfermedad | `diagnosticos_tabla_hlf` |
| `si_se_descompensa` | Fila que se usa si el paciente se descompensa, página, y si es una equivalencia a validar | `puntaje.fila_descompensado` → `ssmso_hlf_2025` o `diagnosticos_tabla_hlf` |
| `regla_oncologica` | Qué fila se aplica si un informe trae cáncer confirmado o sospechoso, según su especialidad | `puntaje.regla_oncologica` (motor) |
| `ges` | Garantía de atención por especialista: problema, plazo, condición y cita textual | `ges_especialista` |
| `criterios_oficiales` | Lista cerrada de criterios alta/media/baja, urgencias, piso y riesgo | `criterios_registro` |
| `criterios_clinicos` | Lo mismo, para las enfermedades del dataset por especialidad | `criterios_especialidad` |
| `reglas_con_el_registro` | Reglas que el código calcula solo con el registro, sin IA | `puntaje.aplicar_registro` (motor) |
| `rubrica` | Medición clave y umbral, ventanas de vigencia con su PMID, pendientes para médicos | `rubrica_v1` (+ `guias_umbrales`, `pubmed_evidencia`) |
| `letalidad` | Nivel 1–4 con la cifra y el PMID | `puntaje.LETALIDAD_DX` (motor) |
| `combinaciones` | Combinaciones de riesgo cuya condición de base calza con el diagnóstico | `combinaciones_riesgo` |
| `orden` | Cascada del Ord. 536, cómo la aplica el código y, si corresponde, su peso de Charlson en el desempate LACE | `ord536` (+ motor) |
| `plazo_referencia` | Días de referencia por prioridad y el riesgo de esperar más | `puntaje.PLAZO_CATEGORIA` (motor) |
| `criterios_locales` | Lo que devuelvan las capas registradas (hoy ninguna) | DynamoDB, vía `aprendizaje.py` |

Ejemplo recortado de `GET /conocimiento/diagnostico/I20`:

```json
{
  "codigo": "I20", "cie10_base": "I20", "diagnostico": "Angina de pecho", "especialidad": "Cardiología",
  "paquete": {"etiqueta": "kb-2026.11.0", "huella": "…", "integro": true},
  "si_se_descompensa": {
    "fila": "Angina inestable", "prioridad": "alta", "pagina": 85, "equivalencia_a_validar": true,
    "equivalencia": "I20 incluye toda angina de pecho; la fila oficial es solo angina inestable",
    "fuente": {"id": "ssmso_hlf_2025", "version": "ssmso_hlf_2025_v1", "clave": "I20", "constante": "puntaje.FILA_DESCOMPENSADO"}
  },
  "letalidad": {"nivel": 2, "detalle": "infarto: 14,2% de mortalidad hospitalaria en Chile (Nazzal 2011); …",
                "fuente": {"id": "motor", "version": "…", "constante": "puntaje.LETALIDAD_DX", "origen": "… cifras verificadas en PubMed."}},
  "rubrica": {"ventanas": [{"evento": "hospitalizacion", "dias": 45, "estado": "a_validar_por_medico", "pmid": "25656852",
                            "fuente": {"id": "pubmed_evidencia", "version": "evidencia_v1", "clave": "I20.visita_urgencia_o_hospitalizacion.ventana_dias"}}],
              "pendientes_medicos": ["I20: ventana de 45 días tras una hospitalizacion (…). Mientras no se valide: no vence"],
              "fuente": {"id": "rubrica_v1", "version": "rubrica_v1.2", "clave": "I20"}},
  "fuentes": [{"id": "diagnosticos_tabla_hlf", "titulo": "…", "tipo": "tabla_oficial", "version": "tabla_hlf_2025_v1", "sha256": "…"}]
}
```

## 7. Por qué recuperación por clave y no búsqueda semántica

El conocimiento oficial es chico (unos 300 KB, 374 entradas) y estructurado: una fila por diagnóstico, un plazo por
problema GES, un criterio con su código. Se recupera **por clave** (CIE-10, código `HLF-…`, tipo de evento, factor de la
razón), con índices que se arman una vez por proceso. La respuesta es exacta, siempre la misma, y se puede auditar: la
misma pregunta devuelve la misma fila de la misma versión.

Se descartó una base vectorial o Bedrock Knowledge Bases para el MVP: costo fijo, recuperación que no es determinista
(dos consultas parecidas pueden traer trozos distintos) y más difícil de auditar, sin ganancia para un corpus de este
tamaño.

**Cuándo convendría sumar búsqueda semántica:** cuando haya que consultar miles de páginas de guías en texto libre
(guías GES completas, protocolos del hospital, normas técnicas) que nadie alcanzó a convertir en criterios. Ahí sirve
para **encontrar y mostrar** el pasaje al especialista, o para proponer un criterio nuevo. Aun así, **la decisión
seguiría saliendo de criterios estructurados**: lo que encuentre la búsqueda no mueve a nadie hasta que una persona lo
convierta en una entrada con fuente y versión, por el procedimiento de §4.

## 8. Deuda conocida de las fuentes (al 13-11-2026)

El script la muestra al empaquetar (`avisos` del manifiesto) cuando la puede detectar solo.

- **Versión repetida:** `pubmed_evidencia` y `guias_umbrales` comparten `evidencia_v1` (el literal está en
  `scripts/buscar_pubmed.py`, igual que la fecha).
- **Fuentes que cambiaron sin subir su versión** (comprobado con la huella de cada versión del historial de git):
  `ssmso_hlf_2025` (F32 pasó de no tener fila de descompensación a alta, pág. 110, con la misma `ssmso_hlf_2025_v1`),
  `rubrica_v1` (dos contenidos distintos como `rubrica_v1` y dos como `rubrica_v1.2`), `criterios_registro` (tres
  contenidos con `criterios_registro_v1`), `diagnosticos_tabla_hlf` (tres con `tabla_hlf_2025_v1`) y
  `combinaciones_riesgo` (dos con `combinaciones_v2`). Importa porque `algoritmo.vigente` reutiliza una lectura
  guardada si `version_kb` es igual. Desde ahora el script lo impide.
- **Sin fecha en el JSON:** `diagnosticos_tabla_hlf` y `criterios_especialidad`.
- **Versión y fecha escritas en los scripts que generan el archivo** (`buscar_pubmed.py`, `consolidar_rubrica.py`): al
  regenerar hay que acordarse de cambiarlas a mano.
- **Regla que nunca se aplica:** la alerta "PHQ-9 ≥ 16" (NICE NG222) de `puntaje.aplicar_registro` es para F32/F33,
  pero la función termina antes para los diagnósticos que no están en `criterios_registro.json` (F32 usa
  `criterios_especialidad`). `para_diagnostico("F32")` no la muestra, porque no se aplica.
- **`ord536.json`:** su `nota` dice que el algoritmo con rúbrica no usa LACE; `decisor.clave_orden_536` sí lo usa como
  desempate.
- **`diagnosticos_tabla_hlf.json`:** su `metodo` habla de 176 filas; el archivo trae 174 (dos filas partidas se unieron:
  no existen `HLF-END-05` ni `HLF-TRA-04`).
- **`combinaciones_riesgo.json`:** `articulacion_septica` y `riesgo_suicida` figuran como `verificado` y su documento es
  el dataset de origen no confirmado; el estado `guia_citada` está definido y ninguna entrada lo usa.
