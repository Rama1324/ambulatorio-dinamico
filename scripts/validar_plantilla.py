#!/usr/bin/env python3
"""Valida template.yaml y samconfig.toml sin necesitar una cuenta AWS.

`cfn-lint template.yaml` solo no alcanza. Con la línea `Transform` de SAM, cfn-lint deja de revisar las referencias
dentro de `Globals`, los parámetros sin usar y los nombres de las acciones IAM (comprobado sembrando errores a
propósito). Y nunca evalúa las reglas (`Rules`) ni los valores de samconfig.toml. Este script hace cinco revisiones:

  1. cfn-lint sobre la plantilla tal cual.
  2. cfn-lint sobre la plantilla "expandida": las funciones de SAM convertidas a AWS::Lambda::Function con lo de
     `Globals` ya aplicado y sin `Transform`. Así corren todas las reglas de cfn-lint.
  3. Todas las combinaciones de parámetros que cambian la estructura (login sí/no, llave propia sí/no, sitio sí/no…):
     en cada combinación que las reglas permiten, ninguna referencia apunta a un recurso que no se crea.
  4. samconfig.toml: cada ambiente usa parámetros que existen, con valores válidos, y no viola ninguna regla.
  5. Las variables de entorno: las que exige la especificación y las que lee el código de lambda/.

Uso:  python scripts/validar_plantilla.py        (requiere Python 3.11+ y `pip install -r requirements-dev.txt`)
Sale con código 0 si todo está bien y 1 si hay algún hallazgo.
"""
import copy
import itertools
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLA = RAIZ / "template.yaml"
SAMCONFIG = RAIZ / "samconfig.toml"
OTRO = "otro-valor"  # representa "cualquier valor distinto de los que la plantilla compara"

# Garantías de seguridad que ninguna combinación permitida puede romper. Si alguien borra o debilita una regla
# (sección Rules) de la plantilla, la revisión 3 falla aquí.
GARANTIAS = [
    ("prod siempre exige login", lambda p: p["Ambiente"] != "prod" or p["Autenticacion"] == "cognito"),
    ("prod nunca acepta cualquier origen web (CORS *)", lambda p: p["Ambiente"] != "prod" or p["OrigenPermitido"] != "*"),
]

# Con el intérprete exacto: en un computador con varios Python, "python -m pip" puede instalar en otro.
INSTALAR = f'"{sys.executable}" -m pip install -r requirements-dev.txt'

try:
    import tomllib
    import yaml
except ImportError as e:  # tomllib existe desde Python 3.11; PyYAML viene con cfn-lint
    sys.exit(f"Falta {e.name} en este Python ({sys.version.split()[0]}). Use Python 3.11 o superior y corra: {INSTALAR}")


# ---------- lectura de la plantilla (YAML con las etiquetas cortas de CloudFormation: !Ref, !Sub, !If…) ----------
class _Cargador(yaml.SafeLoader):
    pass


def _etiqueta(cargador, sufijo, nodo):
    if isinstance(nodo, yaml.ScalarNode):
        valor = cargador.construct_scalar(nodo)
    elif isinstance(nodo, yaml.SequenceNode):
        valor = cargador.construct_sequence(nodo, deep=True)
    else:
        valor = cargador.construct_mapping(nodo, deep=True)
    if sufijo == "GetAtt" and isinstance(valor, str):
        valor = valor.split(".", 1)
    return {sufijo if sufijo in ("Ref", "Condition") else f"Fn::{sufijo}": valor}


_Cargador.add_multi_constructor("!", _etiqueta)


def cargar(ruta):
    return yaml.load(Path(ruta).read_text(encoding="utf-8"), Loader=_Cargador)


# ---------- 1 y 2: cfn-lint ----------
def cfn_lint(ruta):
    """Corre cfn-lint con el mismo Python (no depende de que `cfn-lint` esté en el PATH). Devuelve la lista de hallazgos."""
    r = subprocess.run([sys.executable, "-c", "from cfnlint.runner import main; main()", "-f", "parseable", str(ruta)],
                       capture_output=True, text=True)
    if "No module named" in r.stderr:
        sys.exit(f"Falta cfn-lint en este Python: {INSTALAR}")
    # formato "ruta:línea:col:línea:col:REGLA:mensaje": se quita la ruta para que se lea "línea:col:…:REGLA:mensaje"
    hallazgos = [linea.removeprefix(f"{ruta}:") for linea in (r.stdout + r.stderr).splitlines() if linea.strip()]
    if r.returncode and not hallazgos:
        hallazgos = [f"cfn-lint terminó con código {r.returncode} sin decir por qué"]
    return hallazgos


def expandir_sam(plantilla):
    """Lo que hace la transformación de SAM con ESTA plantilla: aplica Globals a cada función y la deja como
    AWS::Lambda::Function. Vale porque las funciones traen su rol explícito y no usan `Events`."""
    t = copy.deepcopy(plantilla)
    comun = t.pop("Globals", {}).get("Function", {})
    t.pop("Transform", None)
    for nombre, recurso in t["Resources"].items():
        if not recurso["Type"].startswith("AWS::Serverless::"):
            continue
        if recurso["Type"] != "AWS::Serverless::Function" or "Events" in recurso.get("Properties", {}):
            sys.exit(f"{nombre}: este script solo sabe expandir AWS::Serverless::Function sin Events")
        propias = recurso.get("Properties", {})
        props = {**comun, **propias}
        entorno = {**comun.get("Environment", {}).get("Variables", {}), **propias.get("Environment", {}).get("Variables", {})}
        if entorno:
            props["Environment"] = {"Variables": entorno}
        props.pop("CodeUri", None)
        props["Code"] = {"S3Bucket": "artefactos-de-despliegue", "S3Key": "lambda.zip"}
        recurso["Type"], recurso["Properties"] = "AWS::Lambda::Function", props
    return t


# ---------- 3: combinaciones de parámetros ----------
def _valor(x, params):
    if isinstance(x, dict) and "Ref" in x:
        return str(params[x["Ref"]])
    return str(x)


def evaluar(expr, params, condiciones):
    """Evalúa una condición o una regla con valores concretos de los parámetros."""
    (funcion, args), = expr.items()
    if funcion == "Fn::Equals":
        return _valor(args[0], params) == _valor(args[1], params)
    if funcion == "Fn::Not":
        return not evaluar(args[0], params, condiciones)
    if funcion == "Fn::And":
        return all(evaluar(a, params, condiciones) for a in args)
    if funcion == "Fn::Or":
        return any(evaluar(a, params, condiciones) for a in args)
    if funcion == "Condition":
        return evaluar(condiciones[args], params, condiciones)
    raise ValueError(f"función no soportada en condiciones o reglas: {funcion}")


def reglas_violadas(t, params):
    conds, fallas = t.get("Conditions", {}), []
    for nombre, regla in t.get("Rules", {}).items():
        if "RuleCondition" in regla and not evaluar(regla["RuleCondition"], params, conds):
            continue
        fallas += [f"{nombre}: {a.get('AssertDescription', '')}" for a in regla["Assertions"] if not evaluar(a["Assert"], params, conds)]
    return fallas


def _comparados(nodo, params, salida):
    """Junta, por parámetro, las constantes con que la plantilla lo compara (Fn::Equals)."""
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            if clave == "Fn::Equals":
                for a, b in (valor, valor[::-1]):
                    if isinstance(a, dict) and a.get("Ref") in params and not isinstance(b, (dict, list)):
                        salida.setdefault(a["Ref"], set()).add(str(b))
            _comparados(valor, params, salida)
    elif isinstance(nodo, list):
        for x in nodo:
            _comparados(x, params, salida)


def dominios(t):
    """Valores a probar por parámetro: los que la plantilla compara y uno distinto. Devuelve (de condiciones, solo de reglas)."""
    params = t["Parameters"]
    en_cond, en_reglas = {}, {}
    _comparados(t.get("Conditions", {}), params, en_cond)
    _comparados(t.get("Rules", {}), params, en_reglas)

    def candidatos(nombre, vistos):
        permitidos = [str(v) for v in params[nombre].get("AllowedValues", [])]
        otros = [v for v in permitidos if v not in vistos][:1] if permitidos else [OTRO]
        return sorted(vistos) + otros
    todos = {n: en_cond.get(n, set()) | en_reglas.get(n, set()) for n in {*en_cond, *en_reglas}}
    return ({n: candidatos(n, todos[n]) for n in todos if n in en_cond},
            {n: candidatos(n, todos[n]) for n in todos if n not in en_cond})


_VAR_SUB = re.compile(r"\$\{([^!}][^}]*)\}")


def referencias(nodo, guardia=(), ruta=""):
    """Recorre un trozo de la plantilla y entrega (ruta, nombre referido, guardia). La guardia es la lista de
    (condición, valor) que tiene que cumplirse para que esa referencia llegue a existir (ramas de Fn::If)."""
    if isinstance(nodo, list):
        for i, x in enumerate(nodo):
            yield from referencias(x, guardia, f"{ruta}/{i}")
        return
    if not isinstance(nodo, dict):
        return
    if len(nodo) == 1:
        (clave, valor), = nodo.items()
        if clave == "Fn::If":
            cond, si, sino = valor
            yield ruta, ("condicion", cond), guardia
            yield from referencias(si, guardia + ((cond, True),), ruta + "/If(si)")
            yield from referencias(sino, guardia + ((cond, False),), ruta + "/If(no)")
            return
        if clave == "Ref":
            yield ruta, ("recurso", valor), guardia
            return
        if clave == "Fn::GetAtt":
            yield ruta, ("recurso", valor[0] if isinstance(valor, list) else valor.split(".")[0]), guardia
            return
        if clave == "Fn::Sub":
            texto, locales = (valor, {}) if isinstance(valor, str) else valor
            for var in _VAR_SUB.findall(texto):
                if var not in locales:
                    yield ruta, ("recurso", var.split(".")[0]), guardia
            yield from referencias(locales, guardia, ruta + "/Sub")
            return
    for clave, valor in nodo.items():
        yield from referencias(valor, guardia, f"{ruta}/{clave}")


def sitios_de_referencia(t):
    """Todas las referencias de la plantilla con su guardia completa (condición del recurso + ramas de Fn::If)."""
    sitios = []
    for nombre, r in t["Resources"].items():
        base = ((r["Condition"], True),) if "Condition" in r else ()
        if "Condition" in r:
            sitios.append((f"Resources/{nombre}/Condition", ("condicion", r["Condition"]), ()))
        for dep in ([r["DependsOn"]] if isinstance(r.get("DependsOn"), str) else r.get("DependsOn", [])):
            sitios.append((f"Resources/{nombre}/DependsOn", ("recurso", dep), base))
        sitios += list(referencias(r.get("Properties", {}), base, f"Resources/{nombre}"))
    # Globals se aplica a todas las funciones (ninguna es condicional): sus referencias no llevan guardia
    sitios += list(referencias(t.get("Globals", {}), (), "Globals"))
    for nombre, o in t.get("Outputs", {}).items():
        base = ((o["Condition"], True),) if "Condition" in o else ()
        sitios += list(referencias({k: v for k, v in o.items() if k != "Condition"}, base, f"Outputs/{nombre}"))
    return sitios


def colgando(t, sitios, cond):
    """Referencias activas (su guardia se cumple) que apuntan a algo que no existe con esas condiciones."""
    params, recursos = t["Parameters"], t["Resources"]
    fallas = []
    for ruta, (tipo, nombre), guardia in sitios:
        if any(cond.get(c) is not v for c, v in guardia):
            continue
        if tipo == "condicion":
            existe = nombre in cond
        else:
            existe = (nombre in params or nombre.startswith("AWS::")
                      or (nombre in recursos and cond.get(recursos[nombre].get("Condition"), True)))
        if not existe:
            fallas.append(f"{ruta} -> {nombre}")
    return fallas


def revisar_combinaciones(t):
    conds = t.get("Conditions", {})
    estructura, solo_reglas = dominios(t)
    defecto = {n: str(d.get("Default", OTRO)) for n, d in t["Parameters"].items()}
    sitios = sitios_de_referencia(t)
    extras = [dict(zip(solo_reglas, v)) for v in itertools.product(*solo_reglas.values())]
    vistas, rotas, total, prohibidas, hallazgos = {}, {}, 0, 0, []
    for valores in itertools.product(*estructura.values()):
        total += 1
        params = {**defecto, **dict(zip(estructura, valores))}
        # permitida si las reglas aceptan esta combinación con algún valor de los parámetros que solo miran las reglas
        if not any(not reglas_violadas(t, {**params, **extra}) for extra in extras):
            prohibidas += 1
            continue
        for garantia, cumple in GARANTIAS:
            if not cumple(params) and garantia not in rotas:
                rotas[garantia] = ", ".join(f"{n}={params[n]!r}" for n in estructura)
        estado = tuple(evaluar(e, params, conds) for e in conds.values())
        vistas.setdefault(estado, params)
    hallazgos += [f"las reglas ya no garantizan que {g}; lo permite, por ejemplo: {ejemplo}" for g, ejemplo in rotas.items()]
    for estado, params in vistas.items():
        fallas = colgando(t, sitios, dict(zip(conds, estado)))
        if fallas:
            ejemplo = ", ".join(f"{n}={params[n]!r}" for n in estructura)
            hallazgos.append(f"con {ejemplo}:\n      " + "\n      ".join(sorted(set(fallas))))
    resumen = (f"{total} combinaciones de {len(estructura)} parámetros ({prohibidas} prohibidas por las reglas); "
               f"{len(vistas)} estructuras distintas, {len(sitios)} referencias revisadas en cada una")
    return resumen, hallazgos


# ---------- 4: samconfig.toml ----------
def parametros_de(tabla):
    crudo = tabla.get("parameter_overrides", "")
    pares = shlex.split(crudo) if isinstance(crudo, str) else list(crudo)
    return dict(par.split("=", 1) for par in pares)


def valor_config(config, ambiente, clave):
    """Un valor de samconfig como lo resuelve SAM: primero el del comando deploy, después el global del ambiente."""
    for seccion in ("deploy", "global"):
        valor = config.get(ambiente, {}).get(seccion, {}).get("parameters", {}).get(clave)
        if valor is not None:
            return valor
    return config.get("default", {}).get("global", {}).get("parameters", {}).get(clave)


def revisar_samconfig(t):
    hallazgos, lineas = [], []
    if not SAMCONFIG.exists():
        return ["no existe samconfig.toml"], lineas
    config = tomllib.loads(SAMCONFIG.read_text(encoding="utf-8"))
    params = t["Parameters"]
    conds = t.get("Conditions", {})
    sitios = sitios_de_referencia(t)
    ambientes = [a for a, c in config.items() if isinstance(c, dict) and "deploy" in c and a != "default"]
    if not ambientes:
        hallazgos.append("samconfig.toml no define ningún ambiente con [<ambiente>.deploy.parameters]")
    for amb in ambientes:
        despliegue = config[amb]["deploy"]["parameters"]
        try:
            dados = parametros_de(despliegue)
        except ValueError:
            hallazgos.append(f"[{amb}] parameter_overrides mal formado (se espera Clave=Valor separados por espacio)")
            continue
        for nombre, valor in dados.items():
            d = params.get(nombre)
            if d is None:
                hallazgos.append(f"[{amb}] el parámetro {nombre} no existe en la plantilla")
                continue
            if "AllowedValues" in d and valor not in [str(v) for v in d["AllowedValues"]]:
                hallazgos.append(f"[{amb}] {nombre}={valor!r} no está entre {d['AllowedValues']}")
            if "AllowedPattern" in d and not re.fullmatch(d["AllowedPattern"], valor):
                hallazgos.append(f"[{amb}] {nombre}={valor!r} no calza con {d['AllowedPattern']}")
            if d["Type"] == "Number":
                try:
                    n = float(valor)
                    if n < d.get("MinValue", n) or n > d.get("MaxValue", n):
                        hallazgos.append(f"[{amb}] {nombre}={valor} está fuera de [{d.get('MinValue')}, {d.get('MaxValue')}]")
                except ValueError:
                    hallazgos.append(f"[{amb}] {nombre}={valor!r} no es un número")
        completos = {n: str(d.get("Default", "")) for n, d in params.items()} | dados
        sin_valor = [n for n, d in params.items() if "Default" not in d and n not in dados]
        hallazgos += [f"[{amb}] falta el parámetro {n} (no tiene valor por defecto)" for n in sin_valor]
        if dados.get("Ambiente", amb) != amb:
            hallazgos.append(f"[{amb}] declara Ambiente={dados['Ambiente']}: el nombre del ambiente y el parámetro deben coincidir")
        hallazgos += [f"[{amb}] viola la regla {v}" for v in reglas_violadas(t, completos)]
        estado = {c: evaluar(e, completos, conds) for c, e in conds.items()}
        hallazgos += [f"[{amb}] referencia colgando: {f}" for f in colgando(t, sitios, estado)]
        creados = sum(1 for r in t["Resources"].values() if estado.get(r.get("Condition"), True))
        claves = ("Autenticacion", "OrigenPermitido", "LlavePropia", "Algoritmo", "ModelId", "BarridoActivo")
        for clave in ("stack_name", "region"):
            if not valor_config(config, amb, clave):
                hallazgos.append(f"[{amb}] falta {clave}")
        lineas.append(f"[{amb}] stack {valor_config(config, amb, 'stack_name')} en {valor_config(config, amb, 'region')}: "
                      + ", ".join(f"{c}={completos[c] or '(vacío)'}" for c in claves) + f"; {creados} recursos")
    return hallazgos, lineas


# Variables que la especificacion (docs/diseno/ESPECIFICACION_MVP.md, seccion 10) exige en las cuatro funciones.
VARIABLES_EXIGIDAS = {
    "TABLE", "BUCKET", "COLA_EVALUACION_URL", "MODEL_ID", "MODEL_ID_REDACCION", "BEDROCK_REGION", "ALGORITMO",
    "FECHA_REFERENCIA", "REGISTRO_AL", "AUTH", "ORIGEN_PERMITIDO", "LECTURAS_IA", "GUARDRAIL_ID", "GUARDRAIL_VERSION",
    "PREFIJO_ENTRADA", "TEMA_ALERTAS_ARN", "SEGMENTOS_SCAN",
}
# Las que el codigo lee pero no van en la plantilla: solo locales, o las pone Lambda, o tienen respaldo en otra.
VARIABLES_FUERA = {"LOCAL", "DATA_DIR", "AWS_REGION", "TEXTRACT_REGION", "PERFILES_KEY"}


def revisar_variables(t):
    """Globals.Function.Environment trae las variables exigidas y todas las que lee lambda/ (salvo las locales)."""
    dadas = set(t.get("Globals", {}).get("Function", {}).get("Environment", {}).get("Variables", {}))
    leidas = set()
    for py in (RAIZ / "lambda").glob("*.py"):
        leidas |= set(re.findall(r"environ(?:\.get\(|\[)\s*[\"']([A-Z][A-Z0-9_]+)[\"']", py.read_text(encoding="utf-8")))
    hallazgos = [f"falta la variable {v} (la exige la especificacion)" for v in sorted(VARIABLES_EXIGIDAS - dadas)]
    hallazgos += [f"falta la variable {v} (la lee lambda/)" for v in sorted(leidas - dadas - VARIABLES_FUERA)]
    return hallazgos, f"{len(dadas)} variables en Globals; {len(leidas)} distintas leidas en lambda/"


def main():
    for flujo in (sys.stdout, sys.stderr):  # tildes legibles también en Git Bash y en consolas de Windows
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    plantilla = Path(sys.argv[1]) if len(sys.argv) > 1 else PLANTILLA  # otra ruta: solo para probar el validador
    t = cargar(plantilla)
    fallas = 0

    def informe(titulo, hallazgos, detalle=""):
        nonlocal fallas
        fallas += bool(hallazgos)
        print(f"[{'FALLA' if hallazgos else ' OK  '}] {titulo}" + (f" - {detalle}" if detalle else ""))
        for h in hallazgos:
            print(f"    {h}")

    peso = plantilla.stat().st_size
    informe(f"1. cfn-lint {plantilla.name}", cfn_lint(plantilla),
            f"{len(t['Resources'])} recursos, {peso} bytes"
            + (" (sobre 51200: hay que desplegarla subiéndola a S3, como hace sam deploy)" if peso > 51200 else ""))

    with tempfile.TemporaryDirectory() as tmp:
        expandida = Path(tmp) / "template.expandida.json"
        expandida.write_text(json.dumps(expandir_sam(t), indent=1), encoding="utf-8")
        informe("2. cfn-lint sobre la plantilla expandida (sin Transform ni Globals)", cfn_lint(expandida))

    resumen, hallazgos = revisar_combinaciones(t)
    informe("3. Referencias en todas las combinaciones de parámetros", hallazgos, resumen)

    hallazgos, lineas = revisar_samconfig(t)
    informe("4. samconfig.toml", hallazgos)
    for linea in lineas:
        print(f"    {linea}")

    hallazgos, detalle = revisar_variables(t)
    informe("5. Variables de entorno de las funciones", hallazgos, detalle)

    print("\nValidación " + ("CON HALLAZGOS" if fallas else "correcta") + " (estática: no reemplaza un despliegue real).")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
