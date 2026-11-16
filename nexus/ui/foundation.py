"""Janela estável das Fases 1/2; módulos posteriores são opt-in."""
from pathlib import Path
from typing import Callable, Any
from PySide6.QtCore import Qt, Slot, QThreadPool, QTimer, QPropertyAnimation
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QProgressBar, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget, QGraphicsOpacityEffect)
from nexus.core.database import Database
from nexus.core.logger import close_logger, get_logger, log_error
from nexus.core.settings import Settings
from nexus.core.workers import Task
from nexus.modules.file_manager.service import FileManager
from nexus.modules.file_manager.ui import FileManagerMixin
from nexus.ui.models import RecordView, prepare_rows
from nexus.ui.sidebar import Sidebar
from nexus.ui.themes import apply_theme

COLUMNS = {
    'scan': ['path', 'name', 'extension', 'size', 'created', 'modified', 'captured'],
    'file_operations': ['id', 'kind', 'source', 'target', 'status', 'error', 'created', 'batch_id'],
    'error_logs': ['id', 'context', 'message', 'traceback', 'created'],
}


class Window(FileManagerMixin, QMainWindow):
    def __init__(self, db: Database | None = None):
        super().__init__()
        self.db = db or Database()
        self.settings = Settings(self.db)
        self.manager = FileManager(self.db)
        self.scanned = []
        self.scan_generation = self.filter_generation = self.refresh_generation = 0
        self.jobs: set[Task] = set()
        self.callbacks: dict[Task, Callable] = {}
        self.extra_tables: dict[str, RecordView] = {}
        self.pool = QThreadPool(self)
        # Serializes filesystem jobs in this window; painting remains in the GUI thread.
        self.pool.setMaxThreadCount(1)
        self.setWindowTitle('NEXUS — Personal Automation Hub')
        self.resize(1280, 850)
        self.setMinimumSize(760, 580)
        shell = QWidget()
        layout = QHBoxLayout(shell)
        sidebar = QVBoxLayout()
        logo = QLabel('NEXUS')
        logo.setStyleSheet('font-size: 26px; font-weight: 700; color: #398fff; padding: 16px;')
        sidebar.addWidget(logo)
        self.navigation = Sidebar()
        self.navigation.addItems(['⌂  Início', '▤  Arquivos', '⚙  Configurações'])
        sidebar.addWidget(self.navigation, 1)
        self.button(sidebar, 'Alternar tema ☀ / ☾', self.toggle_theme)
        layout.addLayout(sidebar)
        self.stack = QStackedWidget()
        self.tabs = self.stack
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)
        self.build_home()
        self.build_files()
        self.build_settings()
        self.dry_run.setChecked(self.settings.get('dry_run', True))
        self.dry_run.toggled.connect(lambda value: self.settings.set('dry_run', value))
        self.navigation.currentRowChanged.connect(self.navigate)
        self.navigation.setCurrentRow(0)
        self.dark = self.settings.get('dark', True)
        apply_theme(self.dark)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage(f'Dados locais: {self.db.path}')
        get_logger(self.db).info('Aplicação iniciada: Fases 1/2')
        self.refresh()

    def navigate(self, index: int):
        self.stack.setCurrentIndex(index)
        page = self.stack.currentWidget()
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        self.fade = QPropertyAnimation(effect, b'opacity', self)
        self.fade.setDuration(150)
        self.fade.setStartValue(.7)
        self.fade.setEndValue(1.0)
        self.fade.start()

    def page(self, title: str):
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(title)
        label.setStyleSheet('font-size: 22px; font-weight: 600; padding: 8px;')
        layout.addWidget(label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.stack.addWidget(scroll)
        return layout

    def button(self, layout, text: str, callback: Callable):
        button = QPushButton(text)
        button.clicked.connect(lambda: self.guard(callback))
        layout.addWidget(button)
        return button

    def folder_field(self, layout, label: str):
        line = QLineEdit()
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(line, 1)
        def choose():
            path = QFileDialog.getExistingDirectory(self, label)
            if path:
                line.setText(path)
        self.button(row, 'Escolher pasta', choose)
        layout.addLayout(row)
        return line

    def grid(self, layout, key: str):
        search = QLineEdit()
        search.setPlaceholderText('Pesquisar em todas as colunas; clique no cabeçalho para ordenar.')
        layout.addWidget(search)
        table = RecordView(COLUMNS[key], self)
        layout.addWidget(table)
        # Debounce typing, then use one precomputed text per record.
        timer = QTimer(table)
        timer.setSingleShot(True)
        timer.setInterval(180)
        timer.timeout.connect(lambda: table.proxy.search(search.text()))
        search.textChanged.connect(lambda _: timer.start())
        table.search_field = search
        self.extra_tables[key] = table
        return table

    def selected_table(self, table: RecordView):
        table.proxy.search(table.search_field.text())
        return table.selected_record()

    def notify(self, text: str):
        self.statusBar().showMessage(text, 9000)

    def guard(self, callback: Callable):
        try:
            callback()
        except Exception as exc:
            log_error(self.db, 'interface', exc)
            QMessageBox.warning(self, 'NEXUS', str(exc))

    def background(self, fn: Callable, done: Callable):
        task = Task(fn)
        self.jobs.add(task)
        self.callbacks[task] = done
        task.events.done.connect(self.task_done, Qt.ConnectionType.QueuedConnection)
        task.events.error.connect(self.task_error, Qt.ConnectionType.QueuedConnection)
        self.progress.show()
        self.pool.start(task)

    @Slot(object, object)
    def task_done(self, task, result):
        self.jobs.discard(task)
        done = self.callbacks.pop(task)
        if not self.jobs:
            self.progress.hide()
        self.guard(lambda: done(result))

    @Slot(object, str)
    def task_error(self, task, message):
        self.jobs.discard(task)
        self.callbacks.pop(task, None)
        if not self.jobs:
            self.progress.hide()
        log_error(self.db, 'worker', RuntimeError(message), task.traceback)
        self.notify('Erro: ' + message)
        QMessageBox.warning(self, 'Operação interrompida', message)
        self.refresh()

    def refresh(self):
        self.refresh_generation += 1
        generation = self.refresh_generation
        def load():
            return {key: prepare_rows(self.db.rows(f'SELECT * FROM {key} ORDER BY id DESC'), COLUMNS[key])
                    for key in ('file_operations', 'error_logs')}
        def done(data):
            if generation != self.refresh_generation:
                return
            for key, prepared in data.items():
                self.extra_tables[key].records.replace(prepared)
            pending = sum(r['status'] in {'pending', 'undo_pending', 'needs_recovery'} for r in data['file_operations'][0])
            self.overview.setText(f"{len(data['file_operations'][0])} operação(ões) registrada(s) · {pending} pendência(s) de recuperação · {len(data['error_logs'][0])} erro(s)")
        self.background(load, done)

    def build_home(self):
        layout = self.page('Seu espaço de automação')
        intro = QLabel('Fases 1 e 2: fundação e gerenciamento de arquivos.\nAnalise, confira a simulação e confirme as alterações quando estiver pronto.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.overview = QLabel('Consultando histórico local…')
        self.overview.setObjectName('card')
        self.overview.setWordWrap(True)
        layout.addWidget(self.overview)
        self.button(layout, 'Abrir gerenciador de arquivos', lambda: self.navigation.setCurrentRow(1))
        later = QLabel('Fases seguintes: dashboard acadêmico, estudos, impressão 3D, fotografia e scripts.\nAs implementações existentes ficam disponíveis somente com --experimental-modules e ainda exigem validação específica.')
        later.setWordWrap(True)
        layout.addWidget(later)
        layout.addStretch()

    def build_settings(self):
        layout = self.page('Configurações locais')
        info = QLabel(f'Banco SQLite: {self.db.path}\nLogs: {self.db.path.parent / "logs"}\nAs preferências e os dados não ficam na pasta temporária do executável.')
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.setWordWrap(True)
        layout.addWidget(info)
        self.button(layout, 'Alternar tema escuro / claro', self.toggle_theme)
        self.button(layout, 'Atualizar histórico e indicadores', self.refresh)
        layout.addWidget(QLabel('Para fazer backup, feche o NEXUS e copie sua pasta de dados.'))
        layout.addStretch()

    def toggle_theme(self):
        self.dark = not self.dark
        self.settings.set('dark', self.dark)
        apply_theme(self.dark)

    def closeEvent(self, event):
        if self.jobs:
            QMessageBox.information(self, 'Operação em andamento', 'Aguarde os trabalhos terminarem antes de fechar.')
            event.ignore()
            return
        get_logger(self.db).info('Aplicação encerrada')
        close_logger(self.db)
        event.accept()
