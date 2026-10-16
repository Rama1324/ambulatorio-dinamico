"""Antes de mandar un texto clínico a la IA (Amazon Bedrock) se ocultan el RUT y el nombre del paciente (Ley 21.719:
minimización; los datos de salud salen de Chile). La identidad se verifica antes, en nuestro código, con el texto original."""
import re
import unicodedata

RUT = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}\s*-\s*[\dkK]\b")
RUT_ROTULADO = re.compile(r"\b((?i:rut|run))([\s:.°#]*)\d{1,2}\.?\d{3}\.?\d{3}-?[\dkK]\b")
# nombre rotulado: "Nombre: Juan Pérez", "Paciente: María Soto", "Sra. Rosa Díaz". El rótulo ignora mayúsculas; el nombre son
# palabras con mayúscula inicial en la misma línea (así "Paciente con nódulo" no se toca).
ROTULO = re.compile(r"\b((?i:nombre(?:[ \t]+completo)?|paciente|sr\.?|sra\.?|srta\.?|don|doña))([ \t]*:[ \t]*|[ \t]+)"
                    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:[ \t]+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*)")


def _sin_tildes(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def ocultar(texto, nombres=(), ruts=()):
    """Devuelve el texto con [RUT] y [NOMBRE] en lugar de los datos que identifican a la persona."""
    if not texto:
        return texto
    out = RUT.sub("[RUT]", texto)
    out = RUT_ROTULADO.sub(lambda m: m.group(1) + m.group(2) + "[RUT]", out)
    for r in ruts:
        if r:
            out = re.sub(re.escape(r), "[RUT]", out, flags=re.IGNORECASE)
    for n in nombres:
        for v in {(n or "").strip(), _sin_tildes((n or "").strip())}:
            if len(v) >= 3:  # el nombre registrado, con o sin tildes y en cualquier combinación de mayúsculas
                out = re.sub(r"\b" + r"[ \t]+".join(re.escape(p) for p in v.split()) + r"\b", "[NOMBRE]", out, flags=re.IGNORECASE)
    # nombres rotulados que no son los del registro (otra persona, un familiar)
    return ROTULO.sub(lambda m: m.group(1) + m.group(2) + "[NOMBRE]", out)
