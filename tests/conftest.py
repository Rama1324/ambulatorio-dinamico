"""Aislamiento entre archivos de tests: cada archivo parte con el almacén recién cargado desde perfiles.json.
Dentro de un mismo archivo los tests siguen compartiendo la memoria (varios dependen de lo que registró el anterior)."""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))


@pytest.fixture(autouse=True, scope="module")
def almacen_recien_cargado():
    """Lo que registra un archivo de tests (eventos, criterios locales vigentes, lotes) no llega al siguiente."""
    import datos
    import evaluacion_ia
    datos.restablecer()
    evaluacion_ia._llm["cliente"] = None  # cliente de IA falso que un test pudo dejar inyectado
    yield
