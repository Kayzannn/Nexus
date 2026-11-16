"""Aceitação da distribuição padrão, independente dos módulos posteriores."""
import time
from pathlib import Path
from unittest.mock import patch
import pytest
from PySide6.QtCore import Qt, QThread, QTimer, QEventLoop
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from nexus.app import Window
from nexus.core.database import Database
from nexus.core.settings import Settings
from nexus.modules.file_manager.service import scan, rename_plan, FileManager
from nexus.ui.models import RecordView, prepare_rows


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


def drain(window, timeout=20):
    # A real Qt event loop releases the GIL; repeated QTest.qWait calls can
    # starve Python workers and produce a misleading performance failure.
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if not window.jobs else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(int(timeout*1000))
    if window.jobs:
        loop.exec()
    poll.stop()
    deadline.stop()
    assert not window.jobs, 'Workers não concluíram dentro do prazo de teste'


@pytest.fixture
def window(app, tmp_path):
    instance = Window(Database(tmp_path / 'dados locais' / 'nexus.sqlite3'))
    instance.show()
    drain(instance)
    yield instance
    drain(instance)
    instance.close()
    app.processEvents()


def test_default_navigation_and_safe_settings(window):
    assert window.stack.count() == 3
    assert [window.navigation.item(i).text() for i in range(3)] == ['⌂  Início', '▤  Arquivos', '⚙  Configurações']
    assert window.dry_run.isChecked()
    assert '0 operação(ões)' in window.overview.text()
    window.toggle_theme()
    assert Settings(Database(window.db.path)).get('dark') == window.dark
    assert isinstance(window.extra_tables['scan'], RecordView)


def test_unicode_scan_rename_and_undo(window, tmp_path):
    folder = tmp_path / 'Fotos da família 日本語'
    folder.mkdir()
    (folder / 'ação com espaços.JPG').write_bytes(b'not an actual image, fallback to modification date')
    window.source.setText(str(folder))
    window.analyze()
    drain(window)
    rows = window.file_rows()
    assert rows[0]['name'] == 'ação com espaços.JPG'
    plan = rename_plan(rows, base='Férias São Paulo')
    assert plan[0].target.name == 'Férias São Paulo_001.JPG'
    assert window.manager.execute(plan) == 1
    record = window.db.rows('SELECT * FROM file_operations')[0]
    assert window.manager.undo(record) == 1
    assert (folder / 'ação com espaços.JPG').is_file()
    window.refresh()
    drain(window)
    assert window.extra_tables['file_operations'].records.records[0]['status'] == 'undone'


def test_proxy_numeric_sort_and_search_preserve_source_records(app):
    view = RecordView(['path', 'size', 'modified'])
    records = [{'path': 'Z São Paulo.txt', 'size': 2, 'modified': 30.0},
               {'path': 'A 日本語.txt', 'size': 100, 'modified': 10.0}]
    view.records.replace(prepare_rows(records, view.records.columns))
    view.sortByColumn(1, Qt.SortOrder.DescendingOrder)
    assert view.visible_records()[0]['size'] == 100
    view.proxy.search('São Paulo')
    assert view.visible_records() == [records[0]]
    view.proxy.search('日本語')
    assert view.visible_records() == [records[1]]
    view.close()


def test_preview_cancel_keeps_original(window, tmp_path):
    folder = tmp_path / 'source'
    folder.mkdir()
    original = folder / 'a.txt'
    original.write_text('original')
    plan = rename_plan(scan(folder))
    window.dry_run.setChecked(False)
    with patch('nexus.modules.file_manager.ui.PreviewDialog.exec', return_value=0):
        window.confirm_changes(plan, 'rename')
    assert original.read_text() == 'original'
    assert not plan[0].target.exists()
    assert window.db.rows('SELECT * FROM file_operations') == []


def test_dry_run_ui_does_not_execute(window, tmp_path):
    folder = tmp_path / 'source'
    folder.mkdir()
    original = folder / 'a.txt'
    original.write_text('original')
    plan = rename_plan(scan(folder))
    result = []
    with patch.object(window, 'show_batch', side_effect=result.append):
        window.confirm_changes(plan, 'rename')
        drain(window)
    assert result[0].simulated == 1
    assert original.exists()
    assert not plan[0].target.exists()


@pytest.mark.performance
def test_3000_files_async_scan_and_virtual_table(window, tmp_path, record_property):
    folder = tmp_path / 'milhares de arquivos'
    folder.mkdir()
    for index in range(3000):
        (folder / f'arquivo São Paulo {index:04}.txt').write_text(f'conteúdo {index}')
    ticks = []
    timer = QTimer(window)
    timer.setInterval(5)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    window.navigation.setCurrentRow(1)
    window.source.setText(str(folder))
    started = time.monotonic()
    window.analyze()
    drain(window)
    duration = time.monotonic()-started
    timer.stop()
    table = window.extra_tables['scan']
    assert table.proxy.rowCount() == 3000
    assert len(window.file_rows()) == 3000
    assert ticks, 'O loop Qt deve continuar respondendo durante a análise'
    record_property('scan_and_render_3000_seconds', round(duration, 3))
    record_property('qt_heartbeat_ticks', len(ticks))
    print(f'3000 arquivos: análise + modelo = {duration:.3f}s; {len(ticks)} eventos de timer Qt')


def test_confirmed_rename_and_undo_through_ui(window, tmp_path):
    from PySide6.QtWidgets import QMessageBox, QDialog
    folder = tmp_path / 'Fotos com espaços'
    folder.mkdir()
    original = folder / 'original.txt'
    original.write_text('conteúdo importante')
    window.source.setText(str(folder))
    window.analyze()
    drain(window)
    window.rename_base.setText('Documento ação')
    window.dry_run.setChecked(False)
    results = []
    with patch('nexus.modules.file_manager.ui.PreviewDialog.exec', return_value=QDialog.DialogCode.Accepted), patch.object(window, 'show_batch', side_effect=results.append):
        window.preview_rename()
        drain(window)
    target = folder / 'Documento ação_001.txt'
    assert target.read_text() == 'conteúdo importante'
    assert not original.exists()
    assert results[0].completed == 1
    table = window.extra_tables['file_operations']
    table.selectRow(0)
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
        window.undo_file()
        drain(window)
    assert original.read_text() == 'conteúdo importante'
    assert not target.exists()
    assert window.db.rows('SELECT status FROM file_operations')[0]['status'] == 'undone'
