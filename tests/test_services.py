import tempfile
import logging
import unittest
from pathlib import Path
from PIL import Image
from nexus.db import Database
from nexus.services.records import Records
from nexus.services.files import plan_copy, execute_copy, duplicates
from nexus.services.photos import Photos
from nexus.services.automations import Automations


class ServicesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(logging.shutdown)
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "db.sqlite3")
        self.source = self.root / "source"
        self.source.mkdir()
        self.target = self.root / "target"

    def test_persistence_and_validation(self):
        records = Records(self.db)
        records.add_study("Python", 45, "SQLite")
        records.add_calibration("Ender", "PLA", 210, 98)
        reopened = Records(Database(self.db.path))
        self.assertEqual(reopened.list("studies")[0]["minutes"], 45)
        self.assertEqual(reopened.list("calibrations")[0]["material"], "PLA")
        with self.assertRaises(ValueError):
            records.add_study("", 10)
        with self.assertRaises(ValueError):
            records.add_calibration("X", "PLA", float("nan"), 100)
        records.delete("studies", reopened.list("studies")[0]["id"])
        self.assertEqual(records.list("studies"), [])

    def test_copy_duplicates_and_conflicts(self):
        (self.source / "a.txt").write_text("same")
        (self.source / "b.txt").write_text("same")
        self.assertEqual(len(duplicates(self.source)), 1)
        plan = plan_copy(self.source, self.target, ".txt")
        self.assertEqual(execute_copy(plan), 2)
        self.assertEqual((self.target / "a.txt").read_text(), "same")
        self.assertTrue((self.source / "a.txt").exists())
        with self.assertRaises(FileExistsError):
            plan_copy(self.source, self.target)
        with self.assertRaises(ValueError):
            plan_copy(self.source, self.source / "nested")

    def test_stale_preview_and_concurrent_target(self):
        file = self.source / "a.txt"
        file.write_text("first")
        plan = plan_copy(self.source, self.target)
        file.write_text("changed")
        with self.assertRaises(ValueError):
            execute_copy(plan)
        plan = plan_copy(self.source, self.target)
        self.target.mkdir()
        (self.target / "a.txt").write_text("preserve")
        with self.assertRaises(FileExistsError):
            execute_copy(plan)
        self.assertEqual((self.target / "a.txt").read_text(), "preserve")

    def test_photo_upsert(self):
        path = self.source / "photo.jpg"
        Image.new("RGB", (20, 15)).save(path)
        photos = Photos(self.db)
        photos.import_file(path, "natureza")
        photos.import_file(path, "viagem")
        rows = Records(self.db).list("photos")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["width"], rows[0]["height"], rows[0]["tags"]), (20, 15, "viagem"))

    def test_automation_run_history(self):
        (self.source / "a.pdf").write_bytes(b"example")
        automation = Automations(self.db)
        automation.save(self.source, self.target, ".pdf")
        rule = Records(self.db).list("automations")[0]
        self.assertEqual(automation.run(rule, automation.plan(rule)), 1)
        self.assertEqual(Records(self.db).list("runs")[0]["copied"], 1)


if __name__ == "__main__":
    unittest.main()
