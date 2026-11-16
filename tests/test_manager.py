import tempfile
import logging
import unittest
from pathlib import Path
from PIL import Image
from nexus.db import Database
from nexus.services.workspace import Workspace
from nexus.services.photos import Photos
from nexus.services.manager import scan, filter_rows, rename_plan, category_plan, FileManager


class ManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(logging.shutdown)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'source'
        self.folder.mkdir()
        self.db = Database(self.root / 'db.sqlite3')
        self.manager = FileManager(self.db)

    def test_exif_rename_and_undo_preserve_album(self):
        for name, day in [('IMG_9182.JPG', '2025:01:03 12:00:00'), ('IMG_1002.JPG', '2025:01:01 12:00:00')]:
            exif = Image.Exif()
            exif[36867] = day
            Image.new('RGB', (12, 12)).save(self.folder / name, exif=exif)
        photos = Photos(self.db)
        photo_id = photos.import_file(self.folder / 'IMG_1002.JPG')
        album = Workspace(self.db).add('albums', ['Teste'])
        photos.add_to_album(album, photo_id)
        plan = rename_plan(scan(self.folder), 'Foto')
        self.assertEqual(plan[0].source.name, 'IMG_1002.JPG')
        self.assertEqual(plan[0].target.name, 'Foto_001.JPG')
        self.assertEqual(self.manager.execute(plan), 2)
        self.assertEqual(self.db.rows('SELECT path FROM photos')[0]['path'], str(self.folder / 'Foto_001.JPG'))
        record = self.db.rows('SELECT * FROM file_operations WHERE source=?', (str(self.folder / 'IMG_1002.JPG'),))[0]
        self.manager.undo(record)
        self.assertTrue((self.folder / 'IMG_1002.JPG').exists())
        self.assertEqual(len(self.db.rows('SELECT * FROM album_photos')), 1)
        with self.assertRaises(ValueError):
            self.manager.undo(record)

    def test_recursive_filters_and_category(self):
        (self.folder / 'sub').mkdir()
        (self.folder / 'a.txt').write_text('abc')
        (self.folder / 'sub' / 'b.pdf').write_text('abcdef')
        self.assertEqual(len(scan(self.folder)), 1)
        rows = scan(self.folder, True)
        self.assertEqual(len(rows), 2)
        filtered = filter_rows(rows, '.pdf', 4, 10)
        self.assertEqual(len(filtered), 1)
        plan = category_plan(filtered, self.root / 'organized')
        self.manager.execute(plan, 'move')
        self.assertTrue((self.root / 'organized' / 'Documentos' / 'b.pdf').exists())
        self.manager.undo(self.db.rows('SELECT * FROM file_operations')[0])
        self.assertTrue((self.folder / 'sub' / 'b.pdf').exists())

    def test_conflict_invalid_name_and_stale_plan(self):
        source = self.folder / 'a.txt'
        source.write_text('original')
        with self.assertRaises(ValueError):
            rename_plan(scan(self.folder), 'a/b')
        plan = rename_plan(scan(self.folder))
        source.write_text('changed')
        with self.assertRaises(RuntimeError):
            self.manager.execute(plan)
        self.assertEqual(self.db.rows('SELECT status FROM file_operations')[0]['status'], 'failed')
        self.assertTrue(source.exists())
        (self.folder / 'Foto_001.txt').write_text('preserve')
        with self.assertRaises(FileExistsError):
            rename_plan([r for r in scan(self.folder) if r['name'] == 'a.txt'])

    def test_undo_rejects_modified_target(self):
        (self.folder / 'a.txt').write_text('original')
        plan = rename_plan(scan(self.folder))
        self.manager.execute(plan)
        plan[0].target.write_text('edited')
        with self.assertRaises(ValueError):
            self.manager.undo(self.db.rows('SELECT * FROM file_operations')[0])
        self.assertEqual(plan[0].target.read_text(), 'edited')

    def test_academic_persistence_and_export(self):
        workspace = Workspace(self.db)
        workspace.add('subjects', ['Cálculo'])
        activity = workspace.add('activities', ['Cálculo', 'Lista 1', 'Exercícios', '2026-12-01', 0])
        workspace.complete(activity)
        profile = ['PLA básico', 'Ender 3 V3 KE', 'PLA azul', 210, 60, 100, .04, .8, 120, 'Sem stringing', '']
        workspace.add('profiles', profile)
        reopened = Workspace(Database(self.db.path))
        self.assertEqual(reopened.list('activities')[0]['done'], 1)
        report = self.root / 'profiles.csv'
        reopened.export_csv(report)
        self.assertIn('PLA básico', report.read_text(encoding='utf-8-sig'))
        with self.assertRaises(ValueError):
            workspace.add('activities', ['Cálculo', 'Inválido', 'Prova', '2026-99-01', 0])

    def test_cross_volume_move_and_copy_history(self):
        import errno
        from unittest.mock import patch
        from nexus.services.files import plan_copy
        (self.folder / 'a.txt').write_text('preserved content')
        plan = category_plan(scan(self.folder), self.root / 'organized')
        with patch('nexus.services.manager.os.link', side_effect=OSError(errno.EXDEV, 'cross-device')):
            self.assertEqual(self.manager.execute(plan, 'move'), 1)
        self.assertEqual(plan[0].target.read_text(), 'preserved content')
        self.assertFalse(plan[0].source.exists())
        copied = self.manager.copy(plan_copy(plan[0].target.parent, self.root / 'backup'))
        self.assertEqual(copied, 1)
        records = self.db.rows('SELECT * FROM file_operations ORDER BY id')
        self.assertEqual([r['kind'] for r in records], ['move', 'copy'])
        with self.assertRaises(ValueError):
            self.manager.undo(records[1])

    def test_v1_database_migration_keeps_existing_data(self):
        import sqlite3
        path = self.root / 'legacy.sqlite3'
        with sqlite3.connect(path) as conn:
            conn.executescript("CREATE TABLE studies(id INTEGER PRIMARY KEY, subject TEXT NOT NULL, minutes INTEGER NOT NULL, notes TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP); INSERT INTO studies(subject,minutes,notes) VALUES('Legado',30,'preservar'); PRAGMA user_version=1;")
        migrated = Database(path)
        self.assertEqual(migrated.rows('SELECT subject FROM studies')[0]['subject'], 'Legado')
        self.assertEqual(migrated.rows('PRAGMA user_version')[0]['user_version'], 3)
        self.assertEqual(Workspace(migrated).list('activities'), [])

    def test_photo_album_backup_preserves_original(self):
        from nexus.services.files import digest
        image = self.folder / 'photo.png'
        Image.new('RGB', (30, 20), 'blue').save(image)
        before = digest(image)
        photos = Photos(self.db)
        photo = photos.import_file(image)
        album = Workspace(self.db).add('albums', ['Viagem'])
        photos.add_to_album(album, photo)
        plan = photos.backup_plan(album, self.root / 'backup')
        self.assertEqual(len(plan), 1)
        self.manager.copy(plan)
        self.assertEqual(digest(plan[0].target), before)
        self.assertEqual(digest(image), before)
        with self.assertRaises(FileExistsError):
            photos.backup_plan(album, self.root / 'backup')
