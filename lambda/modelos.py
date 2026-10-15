"""Modelos de datos validados con Pydantic para la lectura de informes y fotos.

Un evento solo se propone si pasa TODAS estas reglas; si no, se descarta con su motivo:
- tipo_evento y subtipo existen en el vocabulario del registro (diccionario de datos HLF);
- la severidad corresponde a ese subtipo;
- la frase de evidencia aparece textual en el documento leído (nada inventado);
- la fecha no es posterior a la fecha de corte ni anterior al año 2000.
"""
import re
import unicodedata
from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

# Vocabulario del registro (diccionario_datos.md): subtipo → severidad
SUBTIPOS = {
    "hospitalizacion": {"ingreso UCI": "grave", "ingreso hospitalario": "grave"},
    "visita_urgencia": {"descompensación grave": "grave", "triage ESI 1": "grave", "triage ESI 2": "grave", "descompensación": "moderada",
                        "triage ESI 3": "moderada", "triage ESI 4-5": "leve"},
    "examen_alterado": {"resultado alterado": "moderada"},
    "cambio_farmaco": {"aumento dosis": "moderada", "reducción dosis": "leve"},
    "control_aps": {"estabilización": "leve", "buena respuesta": "leve", "control": "leve"},
    # Hallazgo en un informe (biopsia, epicrisis): no es una descompensación; sube por las filas oncológicas de la tabla HLF
    "hallazgo_oncologico": {"cáncer confirmado": "grave", "sospecha de cáncer": "grave"},
    # Resultado de los criterios clínicos por enfermedad (criterios.py): solo sube la prioridad; "urgencia" = derivar hoy
    "criterio_clinico": {"prioridad alta": "moderada", "prioridad media": "leve", "prioridad baja": "leve", "urgencia": "grave"},
}
CONFIANZA_MINIMA = 90.0   # % por línea bajo el cual se marca para revisar
CONFIANZA_LEGIBLE = 80.0  # % promedio bajo el cual se pide repetir la foto


def normalizar(s: str) -> str:
    """Minúsculas, sin tildes ni espacios repetidos: para comparar la evidencia con el documento."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def buscar_cita(cita: str, texto_normalizado: str) -> int:
    """Posición de la cita en el texto (ya normalizado) o -1. Si la cita une trozos con "..." o "…", cada trozo (de 4 o más
    caracteres) debe estar textual en el texto y en el mismo orden: sigue siendo verificable, nada inventado."""
    trozos = [t.strip(" .,;:") for t in re.split(r"\.\.\.|…", normalizar(cita))]
    trozos = [t for t in trozos if t]
    if not trozos or any(len(t) < 4 for t in trozos):
        return -1
    pos, inicio = 0, None
    for t in trozos:
        i = texto_normalizado.find(t, pos)
        if i < 0:
            return -1
        inicio = i if inicio is None else inicio
        pos = i + len(t)
    return inicio


class LineaLeida(BaseModel):
    texto: str
    confianza: float = Field(ge=0, le=100)

    @property
    def dudosa(self) -> bool:
        return self.confianza < CONFIANZA_MINIMA


class Lectura(BaseModel):
    """Texto del informe tal como se leyó (escrito o por OCR de Amazon Textract)."""
    origen: Literal["texto", "foto"]
    texto: str = Field(min_length=1)
    lineas: List[LineaLeida] = []
    motor: Literal["teclado", "textract"] = "teclado"

    @property
    def confianza_media(self) -> Optional[float]:
        return round(sum(l.confianza for l in self.lineas) / len(self.lineas), 1) if self.lineas else None

    @property
    def legible(self) -> bool:
        return self.confianza_media is None or self.confianza_media >= CONFIANZA_LEGIBLE

    def resumen(self) -> dict:
        return {"origen": self.origen, "motor": self.motor, "confianza_media": self.confianza_media, "legible": self.legible,
                "lineas_dudosas": [l.model_dump() for l in self.lineas if l.dudosa]}


class EventoPropuesto(BaseModel):
    """Evento clínico detectado en un informe. Se valida contra el documento y la fecha de corte (context)."""
    model_config = ConfigDict(extra="ignore")

    tipo_evento: Literal["hospitalizacion", "visita_urgencia", "examen_alterado", "cambio_farmaco", "control_aps", "hallazgo_oncologico", "criterio_clinico"]
    subtipo: str
    severidad: Literal["leve", "moderada", "grave"]
    fecha_evento: Optional[date] = None
    fecha_en_documento: bool = False
    evidencia: str = Field(min_length=5, max_length=500)
    detectado_por: Literal["reglas", "bedrock"]

    @model_validator(mode="after")
    def coherente_con_registro_y_documento(self, info: ValidationInfo):
        if self.subtipo not in SUBTIPOS[self.tipo_evento]:
            raise ValueError(f"subtipo '{self.subtipo}' no existe para {self.tipo_evento}")
        if SUBTIPOS[self.tipo_evento][self.subtipo] != self.severidad:
            raise ValueError(f"severidad '{self.severidad}' no corresponde a '{self.subtipo}'")
        ctx = info.context or {}
        if ctx.get("texto") is not None and normalizar(self.evidencia) not in normalizar(ctx["texto"]):
            raise ValueError("la frase de evidencia no está en el documento")
        corte = ctx.get("corte")
        if self.fecha_evento and corte and self.fecha_evento > corte:
            raise ValueError(f"fecha {self.fecha_evento} posterior a la fecha de corte {corte}")
        if self.fecha_evento and self.fecha_evento.year < 2000:
            raise ValueError(f"fecha {self.fecha_evento} no plausible")
        return self
