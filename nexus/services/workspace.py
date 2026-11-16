"""Dados estruturados dos módulos e migração aditiva da versão 1."""
from pathlib import Path
from nexus.services.records import required
from nexus.modules.study_manager.service import validate_activity
from nexus.modules.printing_3d.service import validate_profile, export_csv
from nexus.modules.script_manager.service import validate_registration

TABLES = {
    'subjects': ('name',),
    'activities': ('subject', 'title', 'kind', 'due', 'done'),
    'materials': ('subject', 'path'),
    'printers': ('name',),
    'filaments': ('manufacturer', 'color', 'material'),
    'profiles': ('name', 'printer', 'filament', 'nozzle', 'bed', 'flow', 'pressure', 'retraction', 'speed', 'notes', 'image'),
    'scripts': ('name', 'description', 'category', 'path', 'arguments'),
    'albums': ('name',),
}


from nexus.core.migrations import migrate


class Workspace:
    def __init__(self, db):
        self.db = db

    def list(self, table):
        if table not in TABLES and table not in {'script_runs', 'file_operations', 'error_logs'}:
            raise ValueError('Tabela inválida.')
        return self.db.rows(f'SELECT * FROM {table} ORDER BY id DESC')

    def add(self, table, values):
        columns = TABLES[table]
        if len(values) != len(columns):
            raise ValueError('Campos incompletos.')
        values = list(values)
        if table == 'activities':
            validate_activity(values)
        if table == 'materials' and not Path(values[1]).is_file():
            raise ValueError('Material não encontrado.')
        if table == 'scripts':
            values = validate_registration(values)
        if table == 'profiles':
            validate_profile(values)
        for i, value in enumerate(values):
            if isinstance(value, str) and columns[i] not in {'notes', 'image', 'description', 'arguments'}:
                values[i] = required(value)
        return self.db.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", values)

    def complete(self, record_id):
        self.db.execute('UPDATE activities SET done=1-done WHERE id=?', (record_id,))

    def export_csv(self, path):
        export_csv(path, self.list('profiles'), ('id', *TABLES['profiles']))
