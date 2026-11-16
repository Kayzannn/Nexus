import logging
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nexus.core.database import Database
from nexus.core.settings import Settings
from nexus.core.migrations import MIGRATIONS
from nexus.modules.file_manager.service import FileManager, scan, rename_plan, move_exclusive
from nexus.modules.file_manager.files import digest


class ReliabilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(logging.shutdown)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.db = Database(self.root / 'db.sqlite3')
        self.manager = FileManager(self.db)

    def test_settings_survive_restart(self):
        Settings(self.db).set('dark', False)
        Settings(self.db).set('preferences', {'sort': 'captured', 'recursive': True})
        reopened = Settings(Database(self.db.path))
        self.assertFalse(reopened.get('dark'))
        self.assertEqual(reopened.get('preferences')['sort'], 'captured')
        self.assertEqual(reopened.get('missing', 12), 12)

    def test_dry_run_has_no_destination_or_history_writes(self):
        path = self.source / 'a.txt'
        path.write_text('preserve')
        before = digest(path)
        plan = rename_plan(scan(self.source))
        result = self.manager.execute(plan, dry_run=True, continue_on_error=True)
        self.assertEqual((result.simulated, result.completed, result.failed), (1, 0, 0))
        self.assertIn('Foto_001.txt', result.previews[0])
        self.assertEqual(digest(path), before)
        self.assertFalse(plan[0].target.exists())
        self.assertEqual(self.db.rows('SELECT * FROM file_operations'), [])
        self.assertEqual(self.db.rows('SELECT * FROM operation_batches'), [])

    def test_one_permission_failure_does_not_stop_independent_file(self):
        for name in ['a.txt', 'b.txt']:
            (self.source / name).write_text(name)
        plan = rename_plan(scan(self.source), order='name')
        def move(source, target):
            if source.name == 'a.txt':
                raise PermissionError('arquivo bloqueado')
            move_exclusive(source, target)
        with patch('nexus.modules.file_manager.service.move_exclusive', side_effect=move):
            result = self.manager.execute(plan, continue_on_error=True)
        self.assertEqual((result.completed, result.failed), (1, 1))
        self.assertTrue((self.source / 'a.txt').exists())
        self.assertTrue((self.source / 'Foto_002.txt').exists())
        self.assertEqual(self.db.rows('SELECT status FROM operation_batches')[0]['status'], 'partial')
        error = self.db.rows('SELECT * FROM error_logs')[0]
        self.assertIn('PermissionError', error['traceback'])
        self.assertTrue((self.root / 'logs' / 'nexus.log').is_file())

    def test_changed_source_does_not_stop_independent_file(self):
        for name in ['a.txt', 'b.txt']:
            (self.source / name).write_text(name)
        plan = rename_plan(scan(self.source), order='name')
        plan[0].source.write_text('changed since preview')
        result = self.manager.execute(plan, continue_on_error=True)
        self.assertEqual((result.completed, result.failed), (1, 1))
        self.assertEqual(plan[0].source.read_text(), 'changed since preview')

    def record_pending(self, source, target, status='pending'):
        return self.db.execute('INSERT INTO file_operations(kind,source,target,digest,status) VALUES(?,?,?,?,?)',
            ('rename', str(source), str(target), digest(source), status))

    def test_recover_move_after_process_crash_then_undo(self):
        source, target = self.source / 'a.txt', self.source / 'renamed.txt'
        source.write_text('original')
        record = self.record_pending(source, target)
        source.rename(target)  # Crash after disk change but before status update.
        self.assertEqual(self.manager.recover().completed, 1)
        row = self.db.rows('SELECT * FROM file_operations WHERE id=?', (record,))[0]
        self.assertEqual(row['status'], 'done')
        self.manager.undo(row)
        self.assertEqual(source.read_text(), 'original')

    def test_recovery_keeps_ambiguous_files_intact(self):
        source, target = self.source / 'a.txt', self.source / 'renamed.txt'
        source.write_text('original')
        self.record_pending(source, target)
        target.write_text('original')
        result = self.manager.recover()
        self.assertEqual(result.failed, 1)
        self.assertEqual(source.read_text(), 'original')
        self.assertEqual(target.read_text(), 'original')
        self.assertEqual(self.db.rows('SELECT status FROM file_operations')[0]['status'], 'pending')

    def test_recover_interrupted_undo(self):
        source, target = self.source / 'a.txt', self.source / 'renamed.txt'
        source.write_text('original')
        self.record_pending(source, target, 'undo_pending')
        self.assertEqual(self.manager.recover().completed, 1)
        self.assertEqual(self.db.rows('SELECT status FROM file_operations')[0]['status'], 'undone')
        self.assertTrue(source.exists())

    def test_migration_failure_rolls_back_schema_and_version(self):
        path = self.root / 'v2.sqlite3'
        with patch('nexus.core.migrations.SCHEMA_VERSION', 2):
            old = Database(path)
        old.execute("INSERT INTO subjects(name) VALUES('preservar')")
        with patch.dict(MIGRATIONS, {3: 'CREATE TABLE marker(id INTEGER); INVALID SQL;'}):
            with self.assertRaises(sqlite3.OperationalError):
                Database(path)
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='marker'").fetchone()[0], 0)
        reopened = Database(path)
        self.assertEqual(reopened.rows('SELECT name FROM subjects')[0]['name'], 'preservar')
        self.assertEqual(reopened.rows('PRAGMA user_version')[0]['user_version'], 3)

    def test_newer_database_is_rejected_without_schema_changes(self):
        self.db.execute('PRAGMA user_version=999')
        before = self.db.rows('SELECT sql FROM sqlite_master ORDER BY name')
        with self.assertRaises(ValueError):
            Database(self.db.path)
        self.assertEqual(self.db.rows('SELECT sql FROM sqlite_master ORDER BY name'), before)
        self.assertEqual(self.db.rows('PRAGMA user_version')[0]['user_version'], 999)

    def test_persistence_failure_after_move_stops_batch_for_recovery(self):
        for name in ['a.txt', 'b.txt']:
            (self.source / name).write_text(name)
        plan = rename_plan(scan(self.source), order='name')
        with patch.object(self.manager, 'relocate_references', side_effect=RuntimeError('persistence unavailable')):
            with self.assertRaises(RuntimeError):
                self.manager.execute(plan, continue_on_error=True)
        self.assertTrue(plan[0].target.exists())
        self.assertTrue(plan[1].source.exists())
        row = self.db.rows('SELECT * FROM file_operations')[0]
        self.assertEqual(row['status'], 'needs_recovery')
        self.assertEqual(self.manager.recover().completed, 1)
        self.assertEqual(self.db.rows('SELECT status FROM file_operations')[0]['status'], 'done')
        self.assertEqual(self.db.rows('SELECT status FROM operation_batches')[0]['status'], 'recovered')

    def test_analysis_does_not_modify_files_and_continues_on_directory_error(self):
        path = self.source / 'a.txt'
        path.write_text('original')
        denied = self.source / 'denied'
        denied.mkdir()
        before = (path.read_bytes(), path.stat().st_mtime_ns, sorted(self.source.iterdir()))
        original = Path.iterdir
        def iterdir(folder):
            if folder == denied:
                raise PermissionError('directory blocked')
            return original(folder)
        errors = []
        with patch.object(Path, 'iterdir', iterdir):
            rows = scan(self.source, True, on_error=lambda path, exc: errors.append(str(exc)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(errors, ['directory blocked'])
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, sorted(self.source.iterdir())), before)
