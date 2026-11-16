"""Validação de perfis internos e relatório tabular local."""
import csv
import math
from pathlib import Path


def validate_profile(values):
    limits = [(0, 500), (0, 200), (.01, 300), (0, 10), (0, 50), (.01, 2000)]
    for value, (minimum, maximum) in zip(values[3:9], limits):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError('Parâmetro de impressão fora dos limites permitidos.')
    if values[-1] and not Path(values[-1]).is_file():
        raise ValueError('Imagem do resultado não encontrada.')


def export_csv(path, rows, columns):
    with Path(path).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
