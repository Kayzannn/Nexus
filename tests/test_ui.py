import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
import pytest
pytest.importorskip("pyqtgraph", reason="Instale .[experimental] para testes das Fases 3–5")
pytestmark = pytest.mark.experimental
from nexus.ui.main_window import Window
from nexus.db import Database


class WindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tabs_and_persisted_records_render(self):
        with tempfile.TemporaryDirectory() as directory:
            window = Window(Database(Path(directory) / "test.db"))
            window.records.add_study("Python", 25)
            window.refresh()
            window.show()
            self.app.processEvents()
            self.assertEqual(window.tabs.count(), 7)
            self.assertEqual(window.tables["studies"].rowCount(), 1)
            self.assertEqual(window.tables["studies"].item(0, 1).text(), "Python")
            window.close()

    def test_sort_selection_and_worker_main_thread(self):
        from PySide6.QtCore import QThread, Qt
        from PySide6.QtTest import QTest
        with tempfile.TemporaryDirectory() as directory:
            window = Window(Database(Path(directory) / 'db.sqlite3'))
            window.records.add_study('Zoologia', 20)
            window.records.add_study('Álgebra', 40)
            window.refresh()
            table = window.tables['studies']
            table.sortItems(2, Qt.SortOrder.DescendingOrder)
            table.selectRow(0)
            self.assertEqual(window.selected('studies')['minutes'], 40)
            result = []
            window.background(lambda: 42, lambda value: result.append((value, QThread.currentThread())))
            for _ in range(500):
                QTest.qWait(10)
                if result:
                    break
            self.assertEqual(result, [(42, self.app.thread())])
            window.close()

    def test_authorized_script_output_and_history(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtTest import QTest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / 'hello.py'
            script.write_text('import sys\nprint("NEXUS_PROGRESS=50")\nprint("hello")\nprint("notice", file=sys.stderr)\n')
            window = Window(Database(root / 'db.sqlite3'))
            window.workspace.add('scripts', ['Teste', 'Teste explícito', 'Testes', str(script), '[]'])
            window.refresh()
            window.extra_tables['scripts'].selectRow(0)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
                window.run_script()
            for _ in range(500):
                QTest.qWait(10)
                if window.process is None:
                    break
            self.assertIsNone(window.process)
            history = window.workspace.list('script_runs')[0]
            self.assertEqual(history['exit_code'], 0)
            self.assertIn('hello', history['output'])
            self.assertIn('notice', history['error'])
            window.close()

    def test_script_can_be_interrupted(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtCore import QProcess
        from PySide6.QtTest import QTest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / 'wait.py'
            script.write_text('import time\nprint("started", flush=True)\ntime.sleep(60)\n')
            window = Window(Database(root / 'db.sqlite3'))
            window.workspace.add('scripts', ['Espera', '', 'Testes', str(script), '[]'])
            window.refresh()
            window.extra_tables['scripts'].selectRow(0)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
                window.run_script()
            for _ in range(200):
                QTest.qWait(10)
                if 'started' in window.output_channels['output']:
                    break
            self.assertIn('started', window.output_channels['output'])
            window.stop_script()
            for _ in range(500):
                QTest.qWait(10)
                if window.process is None:
                    break
            self.assertIsNone(window.process)
            self.assertIsNotNone(window.workspace.list('script_runs')[0]['finished'])
            window.close()

    def test_pdf_report_worker_generates_document(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtTest import QTest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = Window(Database(root / 'db.sqlite3'))
            window.workspace.add('profiles', ['PLA', 'Ender', 'Azul', 210, 60, 100, .04, .8, 100, 'Teste', ''])
            report = root / 'report.pdf'
            errors = []
            with patch.object(window, 'task_error', side_effect=lambda task, error: errors.append(error)):
                with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(report), 'PDF')):
                    window.export_profiles_pdf()
                for _ in range(500):
                    QTest.qWait(10)
                    if not window.jobs or errors:
                        break
            self.assertEqual(errors, [])
            self.assertFalse(window.jobs)
            self.assertTrue(report.read_bytes().startswith(b'%PDF-'))
            window.close()
