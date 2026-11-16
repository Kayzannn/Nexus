"""Migrações ordenadas e atômicas; nunca rebaixa um banco mais recente."""
SCHEMA_VERSION = 3

MIGRATIONS = {
    1: """
CREATE TABLE IF NOT EXISTS studies (
                    id INTEGER PRIMARY KEY, subject TEXT NOT NULL,
                    minutes INTEGER NOT NULL CHECK(minutes > 0),
                    notes TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS calibrations (
                    id INTEGER PRIMARY KEY, printer TEXT NOT NULL, material TEXT NOT NULL,
                    temperature REAL NOT NULL, flow REAL NOT NULL CHECK(flow > 0),
                    notes TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS photos (
                    id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE,
                    digest TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
                    captured TEXT NOT NULL, camera TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS automations (
                    id INTEGER PRIMARY KEY, source TEXT NOT NULL, destination TEXT NOT NULL,
                    extension TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY, automation_id INTEGER,
                    copied INTEGER NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """,
    2: """
CREATE TABLE IF NOT EXISTS studies (
                    id INTEGER PRIMARY KEY, subject TEXT NOT NULL,
                    minutes INTEGER NOT NULL CHECK(minutes > 0),
                    notes TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS calibrations (
                    id INTEGER PRIMARY KEY, printer TEXT NOT NULL, material TEXT NOT NULL,
                    temperature REAL NOT NULL, flow REAL NOT NULL CHECK(flow > 0),
                    notes TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS photos (
                    id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE,
                    digest TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
                    captured TEXT NOT NULL, camera TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS automations (
                    id INTEGER PRIMARY KEY, source TEXT NOT NULL, destination TEXT NOT NULL,
                    extension TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY, automation_id INTEGER,
                    copied INTEGER NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);


        CREATE TABLE IF NOT EXISTS subjects(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS activities(id INTEGER PRIMARY KEY, subject TEXT NOT NULL, title TEXT NOT NULL,
          kind TEXT NOT NULL, due TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY, subject TEXT NOT NULL, path TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS printers(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS filaments(id INTEGER PRIMARY KEY, manufacturer TEXT NOT NULL, color TEXT NOT NULL, material TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profiles(id INTEGER PRIMARY KEY, name TEXT NOT NULL, printer TEXT NOT NULL, filament TEXT NOT NULL,
          nozzle REAL NOT NULL, bed REAL NOT NULL, flow REAL NOT NULL, pressure REAL NOT NULL, retraction REAL NOT NULL,
          speed REAL NOT NULL, notes TEXT NOT NULL, image TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS scripts(id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
          category TEXT NOT NULL, path TEXT NOT NULL, arguments TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS script_runs(id INTEGER PRIMARY KEY, script_id INTEGER NOT NULL, started TEXT NOT NULL,
          finished TEXT, exit_code INTEGER, output TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS albums(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS album_photos(album_id INTEGER NOT NULL, photo_id INTEGER NOT NULL, PRIMARY KEY(album_id,photo_id));
        CREATE TABLE IF NOT EXISTS photo_details(photo_id INTEGER PRIMARY KEY, metadata TEXT NOT NULL, thumbnail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS file_operations(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, source TEXT NOT NULL,
          target TEXT NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
          created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """,
    3: """
CREATE TABLE user_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE error_logs(id INTEGER PRIMARY KEY, context TEXT NOT NULL, message TEXT NOT NULL, traceback TEXT NOT NULL,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE operation_batches(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, dry_run INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished TEXT);
ALTER TABLE file_operations ADD COLUMN batch_id INTEGER REFERENCES operation_batches(id);
CREATE INDEX file_operations_status_idx ON file_operations(status);
CREATE INDEX activities_due_idx ON activities(done,due);
CREATE INDEX error_logs_created_idx ON error_logs(created);
    """,
}



def migrate(db):
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError('Banco criado por versão mais recente do NEXUS.')
        for target in range(version + 1, SCHEMA_VERSION + 1):
            # Statements have no embedded semicolons; execute instead of executescript
            # so DDL and version updates share the same rollback boundary.
            for statement in MIGRATIONS[target].split(';'):
                if statement.strip():
                    conn.execute(statement)
            conn.execute(f'PRAGMA user_version={target}')
