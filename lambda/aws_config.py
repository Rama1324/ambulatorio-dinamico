"""Timeouts para Bedrock y Textract: la Lambda corta a los 30 s, así que cada llamada debe fallar antes y dejar correr el respaldo."""
from botocore.config import Config

CORTA = Config(connect_timeout=3, read_timeout=12, retries={"max_attempts": 1})
