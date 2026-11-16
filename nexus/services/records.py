import math
from nexus.db import Database


def required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Preencha os campos obrigatórios.")
    return value


class Records:
    def __init__(self, db: Database):
        self.db = db

    def add_study(self, subject, minutes, notes=""):
        if not isinstance(minutes, int) or minutes <= 0:
            raise ValueError("A duração deve ser um inteiro positivo.")
        return self.db.execute("INSERT INTO studies(subject, minutes, notes) VALUES(?,?,?)",
                               (required(subject), minutes, notes.strip()))

    def add_calibration(self, printer, material, temperature, flow, notes=""):
        if not all(math.isfinite(v) for v in (temperature, flow)) or not 0 <= temperature <= 500 or not 0 < flow <= 300:
            raise ValueError("Temperatura: 0–500 °C; fluxo: maior que 0 até 300%.")
        return self.db.execute("INSERT INTO calibrations(printer, material, temperature, flow, notes) VALUES(?,?,?,?,?)",
                               (required(printer), required(material), temperature, flow, notes.strip()))

    def list(self, table):
        if table not in {"studies", "calibrations", "photos", "automations", "runs"}:
            raise ValueError("Registro desconhecido.")
        return self.db.rows(f"SELECT * FROM {table} ORDER BY id DESC")

    def delete(self, table, record_id):
        if table not in {"studies", "calibrations", "photos", "automations"}:
            raise ValueError("Registro desconhecido.")
        self.db.execute(f"DELETE FROM {table} WHERE id=?", (record_id,))
