"""Preferências locais no mesmo SQLite dos módulos."""
import json


class Settings:
    def __init__(self, db):
        self.db = db

    def get(self, key, default=None):
        rows = self.db.rows('SELECT value FROM user_settings WHERE key=?', (key,))
        return json.loads(rows[0]['value']) if rows else default

    def set(self, key, value):
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        self.db.execute('''INSERT INTO user_settings(key,value) VALUES(?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated=CURRENT_TIMESTAMP''', (key, encoded))
