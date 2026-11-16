"""Validação explícita de scripts locais e argumentos sem shell."""
import json
from pathlib import Path


def arguments(text):
    values = json.loads(text)
    if not isinstance(values, list) or any(not isinstance(a, str) or '\x00' in a for a in values):
        raise ValueError('Argumentos devem ser uma lista JSON de textos sem caracteres nulos.')
    return values


def validate_registration(values):
    path = Path(values[3]).resolve()
    if path.suffix.lower() != '.py' or not path.is_file():
        raise ValueError('Selecione um script Python local existente.')
    arguments(values[4])
    values[3] = str(path)
    return values
