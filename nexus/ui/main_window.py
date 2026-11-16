"""Shell desktop, navegação e módulos integrados."""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from html import escape
from PySide6.QtCore import (Qt, QTimer, QSettings, QProcess, QDate, Slot, QObject,
                            Signal, QRunnable, QPropertyAnimation)
from PySide6.QtGui import QPixmap, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QStackedWidget, QPushButton, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QDateEdit, QCalendarWidget, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QMessageBox, QFileDialog, QFormLayout, QDialog, QDialogButtonBox,
    QPlainTextEdit, QProgressBar, QGraphicsOpacityEffect, QScrollArea, QTabWidget)
from nexus.ui.base import Window as BaseWindow
from nexus.core.workers import Task
from nexus.core.settings import Settings
from nexus.core.logger import log_error, close_logger
from nexus.ui.sidebar import Sidebar
from nexus.ui.dashboard import DashboardMixin
from nexus.ui.themes import apply_theme
from nexus.services.workspace import Workspace
from nexus.services.manager import FileManager, scan, filter_rows, rename_plan, category_plan
from nexus.services.files import execute_copy
from nexus.modules.script_manager.service import arguments


class NumericItem(QTableWidgetItem):
    def __lt__(self, other):
        a, b = self.data(Qt.ItemDataRole.UserRole + 1), other.data(Qt.ItemDataRole.UserRole + 1)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return super().__lt__(other)


class Window(DashboardMixin, BaseWindow):
    def __init__(self, db=None):
        self.workspace = None
        self.extra_tables = {}
        self.scanned = []
        self.callbacks = {}
        self.process = None
        self.settings = None
        super().__init__(db)
        self.settings = Settings(self.db)
        if self.settings.get('dark') is None:
            self.settings.set('dark', QSettings('Nexus', 'PersonalHub').value('dark', True, type=bool))
        self.dry_run.setChecked(self.settings.get('dry_run', True))
        self.dry_run.toggled.connect(lambda value: self.settings.set('dry_run', value))
        self.workspace = Workspace(self.db)
        self.manager = FileManager(self.db)
        self.build_scripts()
        self.build_dashboard()
        # Replace tabs with scrollable pages and a compact navigation rail.
        old_tabs = self.takeCentralWidget()
        self.stack = QStackedWidget()
        self.navigation = Sidebar()
        titles = ['⌂  Início', '▤  Arquivos', '◷  Estudos', '⚙  Impressão 3D', '▧  Fotografias', '⇄  Automações', '▷  Scripts']
        pages = [old_tabs.widget(old_tabs.count()-1)] + [old_tabs.widget(i) for i in range(old_tabs.count()-1)]
        for title, page in zip(titles, pages):
            self.navigation.addItem(title)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        shell = QWidget()
        root = QHBoxLayout(shell)
        side = QVBoxLayout()
        logo = QLabel('NEXUS')
        logo.setStyleSheet('font-size: 26px; font-weight: 700; color: #398fff; padding: 16px;')
        side.addWidget(logo)
        side.addWidget(self.navigation, 1)
        self.button(side, 'Alternar tema ☀ / ☾', self.toggle_theme)
        root.addLayout(side)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(shell)
        self.tabs = self.stack
        self.navigation.currentRowChanged.connect(self.navigate)
        self.navigation.setCurrentRow(0)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.dark = self.settings.get('dark', True)
        apply_theme(self.dark)
        self.refresh()
        self.resize(1280, 850)
        self.setMinimumSize(760, 580)
        self.timer_dashboard = QTimer(self)
        self.timer_dashboard.timeout.connect(self.refresh_dashboard)
        self.timer_dashboard.start(60000)

    def navigate(self, index):
        self.stack.setCurrentIndex(index)
        effect = QGraphicsOpacityEffect(self.stack.currentWidget())
        self.stack.currentWidget().setGraphicsEffect(effect)
        self.fade = QPropertyAnimation(effect, b'opacity', self)
        self.fade.setDuration(150)
        self.fade.setStartValue(.65)
        self.fade.setEndValue(1)
        self.fade.start()
        self.refresh_dashboard()

    def toggle_theme(self):
        self.dark = not self.dark
        self.settings.set('dark', self.dark)
        apply_theme(self.dark)

    def notify(self, text):
        self.statusBar().showMessage(text, 9000)

    def guard(self, callback):
        try:
            callback()
        except Exception as exc:
            log_error(self.db, 'interface', exc)
            QMessageBox.warning(self, 'NEXUS', str(exc))

    def background(self, fn, done):
        task = Task(fn)
        self.jobs.add(task)
        self.callbacks[task] = done
        task.events.done.connect(self.task_done, Qt.ConnectionType.QueuedConnection)
        task.events.error.connect(self.task_error, Qt.ConnectionType.QueuedConnection)
        if hasattr(self, 'progress'):
            self.progress.show()
        self.pool.start(task)

    @Slot(object, object)
    def task_done(self, task, result):
        self.jobs.discard(task)
        done = self.callbacks.pop(task)
        if not self.jobs and hasattr(self, 'progress'):
            self.progress.hide()
        self.guard(lambda: done(result))
        self.notify('Operação concluída.')

    @Slot(object, str)
    def task_error(self, task, message):
        self.jobs.discard(task)
        self.callbacks.pop(task, None)
        if not self.jobs and hasattr(self, 'progress'):
            self.progress.hide()
        log_error(self.db, 'worker', RuntimeError(message), task.traceback)
        self.notify('Erro: ' + message)
        QMessageBox.warning(self, 'Operação interrompida', message)

    def table(self, layout, key):
        search = QLineEdit()
        search.setPlaceholderText('Pesquisar em todas as colunas…')
        layout.addWidget(search)
        super().table(layout, key)
        table = self.tables[key]
        table.setObjectName(key)
        search.textChanged.connect(lambda text: self.search_table(table, text))
        table.search_field = search

    def search_table(self, table, text):
        for row in range(table.rowCount()):
            table.setRowHidden(row, not any(text.casefold() in table.item(row, col).text().casefold()
                                          for col in range(table.columnCount()) if table.item(row, col)))

    def fill(self, table, rows):
        table.setSortingEnabled(False)
        headers = list(rows[0]) if rows else ['id']
        key = table.objectName()
        if not rows and key in {'studies', 'calibrations', 'photos', 'automations', 'subjects', 'activities', 'materials', 'printers', 'filaments', 'profiles', 'scripts', 'script_runs', 'albums', 'file_operations', 'error_logs'}:
            with self.db.connect() as conn:
                headers = [r['name'] for r in conn.execute(f'PRAGMA table_info({key})')]
        elif not rows and key == 'scan':
            headers = ['path', 'name', 'extension', 'size', 'created', 'modified', 'captured']
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for i, record in enumerate(rows):
            for j, column in enumerate(headers):
                value = record[column]
                item = NumericItem('' if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, record)
                item.setData(Qt.ItemDataRole.UserRole + 1, value)
                table.setItem(i, j, item)
        table.setSortingEnabled(True)
        table.resizeColumnsToContents()
        if hasattr(table, 'search_field'):
            self.search_table(table, table.search_field.text())

    def selected_table(self, table):
        row = table.currentRow()
        if row < 0 or table.isRowHidden(row):
            raise ValueError('Selecione um registro visível.')
        record = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not isinstance(record, dict):
            raise ValueError('Seleção indisponível; atualize a tabela.')
        return record

    def selected(self, key):
        return self.selected_table(self.tables[key])

    def grid(self, layout, key):
        search = QLineEdit()
        search.setPlaceholderText('Pesquisar… Clique no cabeçalho para ordenar.')
        layout.addWidget(search)
        table = QTableWidget()
        table.setObjectName(key)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setMinimumHeight(160)
        layout.addWidget(table)
        search.textChanged.connect(lambda text: self.search_table(table, text))
        table.search_field = search
        self.extra_tables[key] = table
        return table

    def refresh(self):
        for table in self.tables.values():
            table.blockSignals(True)
            table.setSortingEnabled(False)
        super().refresh()
        for key, table in self.tables.items():
            self.fill(table, self.data[key])
            table.blockSignals(False)
        if self.workspace:
            for key, table in self.extra_tables.items():
                if key not in {'scan', 'album_contents'}:
                    self.fill(table, self.workspace.list(key))
            self.refresh_dashboard()
            self.calendar_marks()

    def form_dialog(self, title, fields, save):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        form = QFormLayout(dialog)
        widgets = []
        for label, kind in fields:
            if isinstance(kind, list):
                widget = QComboBox()
                widget.addItems(kind)
            elif kind == 'date':
                widget = QDateEdit(QDate.currentDate())
                widget.setDisplayFormat('yyyy-MM-dd')
                widget.setCalendarPopup(True)
            elif isinstance(kind, tuple):
                widget = QDoubleSpinBox()
                widget.setRange(kind[0], kind[1])
                widget.setDecimals(4)
                widget.setValue(kind[2])
            else:
                widget = QLineEdit(kind or '')
            form.addRow(label, widget)
            widgets.append(widget)
            if kind in ('file', 'image', 'script'):
                widget.clear()
                browse = QPushButton('Selecionar arquivo…')
                def choose(w=widget, k=kind):
                    path, _ = QFileDialog.getOpenFileName(dialog, 'Selecionar arquivo', '', 'Python (*.py)' if k == 'script' else 'Arquivos (*)')
                    if path:
                        w.setText(path)
                browse.clicked.connect(choose)
                form.addRow('', browse)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        def accept():
            values = []
            for w in widgets:
                if isinstance(w, QDateEdit):
                    values.append(w.date().toString('yyyy-MM-dd'))
                elif isinstance(w, QDoubleSpinBox):
                    values.append(w.value())
                elif isinstance(w, QComboBox):
                    values.append(w.currentText())
                else:
                    values.append(w.text())
            try:
                save(values)
            except Exception as exc:
                log_error(self.db, 'form:' + title, exc)
                QMessageBox.warning(dialog, 'Verifique os campos', str(exc))
                return
            dialog.accept()
            self.refresh()
            self.notify('Registro salvo.')
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def build_files(self):
        layout = self.page('Arquivos')
        self.source = self.folder_field(layout, 'Pasta para análise')
        options = QHBoxLayout()
        self.recursive = QCheckBox('Incluir subpastas (sem links simbólicos)')
        options.addWidget(self.recursive)
        self.button(options, 'Analisar pasta', self.analyze)
        layout.addLayout(options)
        filters = QHBoxLayout()
        self.file_ext = QLineEdit()
        self.file_ext.setPlaceholderText('Extensões: .jpg,.cr2')
        self.file_min, self.file_max = QSpinBox(), QSpinBox()
        for w in (self.file_min, self.file_max):
            w.setRange(0, 2000000000)
            w.setSuffix(' KB')
        self.file_max.setSpecialValueText('Sem tamanho máximo')
        self.file_min.setToolTip('Tamanho mínimo em KB')
        self.file_max.setToolTip('Tamanho máximo em KB; zero significa sem limite')
        self.file_after, self.file_before = QLineEdit(), QLineEdit()
        self.file_after.setPlaceholderText('Modificado desde AAAA-MM-DD')
        self.file_before.setPlaceholderText('Até AAAA-MM-DD (inclusive)')
        for w in (self.file_ext, self.file_min, self.file_max, self.file_after, self.file_before):
            filters.addWidget(w)
        layout.addLayout(filters)
        self.button(layout, 'Aplicar filtros', self.apply_file_filters)
        self.grid(layout, 'scan')
        rename = QHBoxLayout()
        self.rename_base, self.rename_prefix, self.rename_suffix = QLineEdit('Foto'), QLineEdit(), QLineEdit()
        self.rename_prefix.setPlaceholderText('Prefixo')
        self.rename_suffix.setPlaceholderText('Sufixo')
        self.rename_order = QComboBox()
        for label, key in [('Captura EXIF', 'captured'), ('Criação', 'created'), ('Modificação', 'modified'), ('Nome', 'name'), ('Extensão', 'extension'), ('Tamanho', 'size')]:
            self.rename_order.addItem(label, key)
        self.rename_fallback = QComboBox()
        self.rename_fallback.addItem('Sem EXIF: modificação', 'modified')
        self.rename_fallback.addItem('Sem EXIF: criação', 'created')
        self.rename_reverse = QCheckBox('Decrescente')
        for w in (self.rename_base, self.rename_prefix, self.rename_suffix, self.rename_order, self.rename_fallback, self.rename_reverse):
            rename.addWidget(w)
        layout.addLayout(rename)
        self.dry_run = QCheckBox('Simulação (dry-run): validar sem alterar origens ou destinos')
        self.dry_run.setChecked(True)
        layout.addWidget(self.dry_run)
        self.button(layout, 'Prévia de renomeação em massa…', self.preview_rename)
        self.destination = self.folder_field(layout, 'Destino da organização / cópia')
        self.extension = QLineEdit()
        self.extension.setPlaceholderText('Filtro de cópia simples: .jpg (opcional)')
        layout.addWidget(self.extension)
        actions = QHBoxLayout()
        self.button(actions, 'Organizar por categoria…', self.preview_category)
        self.button(actions, 'Duplicados dos arquivos filtrados', self.manager_duplicates)
        self.button(actions, 'Copiar pasta imediata…', self.copy_files)
        layout.addLayout(actions)
        layout.addWidget(QLabel('Alterações usam os arquivos visíveis após filtros e pesquisa. Datas de criação indisponíveis aparecem vazias.'))
        self.grid(layout, 'file_operations')
        self.button(layout, 'Desfazer operação selecionada…', self.undo_file)
        self.button(layout, 'Conciliar operações interrompidas…', self.recover_files)
        self.grid(layout, 'error_logs')

    def confirm_plan(self, plan, run):
        if self.dry_run.isChecked():
            self.background(lambda: self.manager.copy(plan, dry_run=True, continue_on_error=True), self.show_batch)
            return
        if not plan:
            self.notify('Nenhum arquivo corresponde à regra.')
            return
        if run is execute_copy:
            run = lambda p: self.manager.copy(p, continue_on_error=True)
        dialog = QMessageBox(self)
        dialog.setWindowTitle('Prévia de cópia')
        dialog.setText(f'Copiar {len(plan)} arquivo(s)? Confira os detalhes antes de confirmar.')
        dialog.setDetailedText('\n'.join(f'{p.source} → {p.target}' for p in plan))
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        def done(result):
            self.show_batch(result)
            self.refresh()
        if dialog.exec() == QMessageBox.StandardButton.Yes:
            self.background(lambda: run(plan), done)

    def analyze(self):
        folder = self.source.text().strip()
        if not folder:
            raise ValueError('Selecione uma pasta.')
        recursive = self.recursive.isChecked()
        def analyze():
            errors = []
            def report(path, exc):
                log_error(self.db, f'scan:{path}', exc)
                errors.append(f'{path}: {exc}')
            return scan(folder, recursive, on_error=report), errors
        def done(result):
            self.scanned, errors = result
            self.apply_file_filters()
            if errors:
                dialog = QMessageBox(self)
                dialog.setText(f'Análise parcial: {len(errors)} erro(s). Os arquivos acessíveis estão na tabela.')
                dialog.setDetailedText('\n'.join(errors))
                dialog.exec()
        self.background(analyze, done)

    def apply_file_filters(self):
        from datetime import timedelta
        after = datetime.strptime(self.file_after.text(), '%Y-%m-%d').timestamp() if self.file_after.text() else None
        before = (datetime.strptime(self.file_before.text(), '%Y-%m-%d') + timedelta(days=1)).timestamp() - .000001 if self.file_before.text() else None
        self.filtered = filter_rows(self.scanned, self.file_ext.text(), self.file_min.value()*1024,
                                    self.file_max.value()*1024 or None, after, before)
        display = []
        for row in self.filtered:
            item = row.copy()
            for key in ('created', 'modified', 'captured'):
                item[key] = datetime.fromtimestamp(row[key]).isoformat(' ', timespec='seconds') if row[key] is not None else ''
            display.append(item)
        self.fill(self.extra_tables['scan'], display)

    def file_rows(self):
        if not getattr(self, 'filtered', []):
            raise ValueError('Analise uma pasta e verifique os filtros.')
        table = self.extra_tables['scan']
        paths = {table.item(i, 0).data(Qt.ItemDataRole.UserRole)['path'] for i in range(table.rowCount()) if not table.isRowHidden(i)}
        rows = [r.copy() for r in self.filtered if r['path'] in paths]
        if not rows:
            raise ValueError('Nenhum arquivo visível corresponde à pesquisa.')
        return rows

    def preview_rename(self):
        rows = self.file_rows()
        args = (self.rename_base.text(), self.rename_prefix.text(), self.rename_suffix.text(),
                self.rename_order.currentData(), self.rename_reverse.isChecked(), self.rename_fallback.currentData())
        self.background(lambda: rename_plan(rows, *args), lambda plan: self.confirm_changes(plan, 'rename'))

    def preview_category(self):
        rows = self.file_rows()
        destination = self.destination.text().strip()
        if not destination:
            raise ValueError('Selecione o destino.')
        self.background(lambda: category_plan(rows, destination), lambda plan: self.confirm_changes(plan, 'move'))

    def confirm_changes(self, plan, kind):
        if self.dry_run.isChecked():
            self.background(lambda: self.manager.execute(plan, kind, dry_run=True, continue_on_error=True), self.show_batch)
            return
        if not plan:
            self.notify('Nenhuma alteração necessária.')
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle('Prévia obrigatória')
        dialog.setText(f'{len(plan)} alteração(ões). Leia os detalhes. Conflitos interrompem a execução; alterações anteriores ficam no histórico.')
        dialog.setDetailedText('\n'.join(f'{p.source} → {p.target}' for p in plan))
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        if dialog.exec() == QMessageBox.StandardButton.Yes:
            self.background(lambda: self.manager.execute(plan, kind, continue_on_error=True), lambda result: self.after_files(result))

    def after_files(self, result=None):
        if result is not None:
            self.show_batch(result)
        self.refresh()
        self.analyze()

    def show_batch(self, result):
        dialog = QMessageBox(self)
        dialog.setWindowTitle('Resultado do lote')
        dialog.setText(str(result))
        details = getattr(result, 'errors', []) + getattr(result, 'previews', [])
        if details:
            dialog.setDetailedText('\n'.join(details))
        dialog.exec()

    def recover_files(self):
        if QMessageBox.question(self, 'Recuperar histórico', 'Inspecionar hashes e conciliar registros pendentes? Nenhum arquivo será movido ou apagado. Estados ambíguos permanecerão para revisão manual.') == QMessageBox.StandardButton.Yes:
            self.background(self.manager.recover, lambda result: (self.show_batch(result), self.refresh()))

    def undo_file(self):
        record = self.selected_table(self.extra_tables['file_operations'])
        if QMessageBox.question(self, 'Prévia do desfazer', f"Restaurar {record['target']}\npara {record['source']}?") == QMessageBox.StandardButton.Yes:
            self.background(lambda: self.manager.undo(record), lambda _: self.after_files())

    def manager_duplicates(self):
        rows = self.file_rows()
        def done(groups):
            dialog = QMessageBox(self)
            dialog.setText(f'{len(groups)} grupo(s) exatos por SHA-256. Nenhum arquivo foi apagado.')
            dialog.setDetailedText('\n\n'.join('\n'.join(g) for g in groups) or 'Nenhum duplicado.')
            dialog.exec()
        self.background(lambda: self.manager.duplicates(rows), done)

    def build_studies(self):
        # Keep the session chart and add persistent academic planning.
        super().build_studies()
        layout = self.tabs.widget(self.tabs.count()-1).layout()
        controls = QHBoxLayout()
        self.button(controls, 'Cadastrar disciplina', lambda: self.form_dialog('Disciplina', [('Nome', '')],
                    lambda v: self.workspace.add('subjects', v)))
        def activity():
            subjects = [r['name'] for r in self.workspace.list('subjects')]
            if not subjects:
                raise ValueError('Cadastre uma disciplina primeiro.')
            self.form_dialog('Atividade acadêmica', [('Disciplina', subjects), ('Título', ''),
                ('Tipo', ['Tarefa', 'Prova', 'Trabalho', 'Exercícios', 'Compromisso']), ('Prazo', 'date')],
                lambda v: self.workspace.add('activities', [*v, 0]))
        self.button(controls, 'Nova atividade / prazo', activity)
        def material():
            subjects = [r['name'] for r in self.workspace.list('subjects')]
            if not subjects:
                raise ValueError('Cadastre uma disciplina primeiro.')
            self.form_dialog('Material de estudo', [('Disciplina', subjects), ('Arquivo PDF, TXT ou código', 'file')],
                             lambda v: self.workspace.add('materials', v))
        self.button(controls, 'Adicionar material', material)
        layout.addLayout(controls)
        self.grid(layout, 'subjects')
        self.grid(layout, 'activities')
        self.button(layout, 'Alternar conclusão da atividade selecionada', self.complete_activity)
        self.grid(layout, 'materials')
        self.calendar = QCalendarWidget()
        self.calendar.setMaximumHeight(260)
        self.calendar.selectionChanged.connect(self.calendar_day)
        layout.addWidget(self.calendar)
        self.calendar_info = QLabel('Selecione um dia para consultar os prazos.')
        self.calendar_info.setWordWrap(True)
        layout.addWidget(self.calendar_info)
        pomo = QHBoxLayout()
        self.pomo_subject = QLineEdit()
        self.pomo_subject.setPlaceholderText('Disciplina do Pomodoro')
        self.pomo_minutes = QSpinBox()
        self.pomo_minutes.setRange(1, 120)
        self.pomo_minutes.setValue(25)
        self.pomo_label = QLabel('Pronto')
        pomo.addWidget(self.pomo_subject)
        pomo.addWidget(self.pomo_minutes)
        pomo.addWidget(self.pomo_label)
        self.button(pomo, 'Iniciar Pomodoro', self.start_pomodoro)
        self.button(pomo, 'Cancelar sessão', self.cancel_pomodoro)
        layout.addLayout(pomo)
        self.pomo_timer = QTimer(self)
        self.pomo_timer.setInterval(250)
        self.pomo_timer.timeout.connect(self.tick_pomodoro)

    def complete_activity(self):
        self.workspace.complete(self.selected_table(self.extra_tables['activities'])['id'])
        self.refresh()

    def calendar_marks(self):
        from PySide6.QtGui import QTextCharFormat, QColor
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())
        style = QTextCharFormat()
        style.setBackground(QColor('#287bd9'))
        style.setForeground(QColor('white'))
        for activity in self.workspace.list('activities'):
            if not activity['done']:
                self.calendar.setDateTextFormat(QDate.fromString(activity['due'], 'yyyy-MM-dd'), style)
        self.calendar_day()

    def calendar_day(self):
        if not self.workspace:
            return
        day = self.calendar.selectedDate().toString('yyyy-MM-dd')
        rows = [r for r in self.workspace.list('activities') if r['due'] == day]
        self.calendar_info.setText('\n'.join(f"{'✓' if r['done'] else '○'} {r['kind']}: {r['title']} — {r['subject']}" for r in rows) or 'Sem atividades neste dia.')

    def start_pomodoro(self):
        from nexus.services.records import required
        if self.pomo_timer.isActive():
            raise ValueError('Já existe uma sessão em andamento.')
        self.pomo_active_subject = required(self.pomo_subject.text())
        self.pomo_duration = self.pomo_minutes.value()
        self.pomo_end = time.monotonic() + self.pomo_duration*60
        self.pomo_timer.start()
        self.tick_pomodoro()

    def tick_pomodoro(self):
        remaining = max(0, int(self.pomo_end-time.monotonic()+.999))
        self.pomo_label.setText(f'{remaining//60:02d}:{remaining%60:02d}')
        if remaining == 0:
            self.pomo_timer.stop()
            self.records.add_study(self.pomo_active_subject, self.pomo_duration, 'Pomodoro concluído')
            self.refresh()
            self.notify('Pomodoro concluído e registrado.')
            QApplication.beep()

    def cancel_pomodoro(self):
        self.pomo_timer.stop()
        self.pomo_label.setText('Cancelado — tempo não registrado')

    def build_calibrations(self):
        super().build_calibrations()
        layout = self.tabs.widget(self.tabs.count()-1).layout()
        actions = QHBoxLayout()
        self.button(actions, 'Cadastrar impressora', lambda: self.form_dialog('Impressora', [('Nome / modelo', '')],
                    lambda v: self.workspace.add('printers', v)))
        self.button(actions, 'Cadastrar filamento', lambda: self.form_dialog('Filamento',
                    [('Fabricante', ''), ('Cor', ''), ('Material', ['PLA', 'PETG', 'PLA Silk', 'ABS', 'ASA', 'TPU', 'Outro'])],
                    lambda v: self.workspace.add('filaments', v)))
        self.button(actions, 'Novo perfil / teste completo', self.new_profile)
        layout.addLayout(actions)
        self.grid(layout, 'printers')
        self.grid(layout, 'filaments')
        self.grid(layout, 'profiles')
        layout.addWidget(QLabel('Perfis em formato interno. Não importa nem exporta perfis de fatiadores.'))
        exports = QHBoxLayout()
        self.button(exports, 'Comparar perfis filtrados', self.compare_profiles)
        self.button(exports, 'Exportar CSV…', self.export_profiles_csv)
        self.button(exports, 'Exportar PDF…', self.export_profiles_pdf)
        layout.addLayout(exports)

    def new_profile(self):
        printers = [r['name'] for r in self.workspace.list('printers')]
        filaments = [f"#{r['id']} {r['manufacturer']} / {r['color']} / {r['material']}" for r in self.workspace.list('filaments')]
        if not printers or not filaments:
            raise ValueError('Cadastre uma impressora e um filamento primeiro.')
        fields = [('Nome do perfil / teste', ''), ('Impressora', printers), ('Filamento', filaments),
                  ('Bico °C', (0, 500, 210)), ('Mesa °C', (0, 200, 60)), ('Fluxo %', (.01, 300, 100)),
                  ('Pressure Advance', (0, 10, 0)), ('Retração mm', (0, 50, .8)), ('Velocidade mm/s', (.01, 2000, 100)),
                  ('Resultados / defeitos / observações', ''), ('Imagem do resultado (referência opcional)', 'image')]
        def save(values):
            if values[-1] and not Path(values[-1]).is_file():
                raise ValueError('Imagem não encontrada.')
            self.workspace.add('profiles', values)
        self.form_dialog('Perfil interno de calibração', fields, save)

    def compare_profiles(self):
        table = self.extra_tables['profiles']
        rows = [table.item(i, 0).data(Qt.ItemDataRole.UserRole) for i in range(table.rowCount()) if not table.isRowHidden(i)]
        if len(rows) < 2:
            raise ValueError('Mantenha pelo menos dois perfis visíveis para comparar.')
        dialog = QDialog(self)
        dialog.setWindowTitle('Comparação de perfis internos')
        dialog.resize(900, 500)
        layout = QVBoxLayout(dialog)
        comparison = QTableWidget()
        transposed = [{'parâmetro': key, **{f"{r['id']}: {r['name']}": r[key] for r in rows}} for key in rows[0] if key != 'id']
        self.fill(comparison, transposed)
        layout.addWidget(comparison)
        dialog.exec()

    def profile_image(self):
        record = self.selected_table(self.extra_tables['profiles'])
        pixmap = QPixmap(record['image'])
        if pixmap.isNull():
            raise ValueError('Imagem não anexada ou indisponível.')
        dialog = QDialog(self)
        dialog.setWindowTitle(record['name'])
        layout = QVBoxLayout(dialog)
        label = QLabel()
        label.setPixmap(pixmap.scaled(850, 650, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(label)
        dialog.exec()

    def export_profiles_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Relatório CSV', 'calibracoes.csv', 'CSV (*.csv)')
        if path:
            self.background(lambda: self.workspace.export_csv(path), lambda _: self.notify('CSV exportado.'))

    def export_profiles_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Relatório PDF', 'calibracoes.pdf', 'PDF (*.pdf)')
        if path:
            def generate():
                document = QTextDocument()
                rows = self.workspace.list('profiles')
                document.setHtml('<h1>NEXUS — Calibrações</h1>' + ''.join('<h2>'+escape(r['name'])+'</h2><dl>'+ ''.join(
                    f'<dt><b>{escape(str(k))}</b></dt><dd>{escape(str(v))}</dd>' for k,v in r.items())+'</dl>' for r in rows))
                printer = QPrinter()
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(path)
                document.print_(printer)
                if not Path(path).is_file() or Path(path).stat().st_size == 0:
                    raise OSError('O relatório PDF não foi gravado.')
            self.background(generate, lambda _: self.notify('PDF exportado.'))

    def build_photos(self):
        layout = self.page('Fotografias')
        layout.addWidget(QLabel('Originais preservados. RAW usa LibRaw; suporte depende do modelo da câmera.'))
        self.tags = QLineEdit()
        self.tags.setPlaceholderText('Tags das imagens importadas')
        layout.addWidget(self.tags)
        def choose():
            paths, _ = QFileDialog.getOpenFileNames(self, 'Importar fotografias', '',
                'Imagens (*.jpg *.jpeg *.png *.tif *.tiff *.webp *.cr2 *.cr3 *.nef *.arw *.dng *.raf *.orf *.rw2)')
            tags = self.tags.text()
            def run():
                errors = []
                for path in paths:
                    try:
                        self.photos.import_file(Path(path), tags)
                    except Exception as exc:
                        errors.append(f'{Path(path).name}: {exc}')
                return errors
            def done(errors):
                self.refresh()
                if errors:
                    QMessageBox.warning(self, 'Importação parcial', '\n'.join(errors))
            if paths:
                self.background(run, done)
        self.button(layout, 'Importar JPG, PNG ou RAW…', choose)
        self.table(layout, 'photos')
        self.tables['photos'].itemSelectionChanged.connect(self.photo_preview)
        self.preview = QLabel('Selecione uma fotografia para visualizar a miniatura e os metadados.')
        self.preview.setMinimumHeight(180)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview)
        self.photo_metadata = QPlainTextEdit()
        self.photo_metadata.setReadOnly(True)
        self.photo_metadata.setMaximumHeight(150)
        layout.addWidget(self.photo_metadata)
        controls = QHBoxLayout()
        self.button(controls, 'Criar coleção / álbum', lambda: self.form_dialog('Álbum', [('Nome', '')],
                    lambda v: self.workspace.add('albums', v)))
        self.button(controls, 'Adicionar foto ao álbum selecionado', self.photo_to_album)
        self.button(controls, 'Duplicatas exatas', self.photo_duplicates)
        layout.addLayout(controls)
        self.grid(layout, 'albums')
        self.button(layout, 'Mostrar conteúdo do álbum', self.show_album)
        self.grid(layout, 'album_contents')
        self.button(layout, 'Backup / preparar cópias para Lightroom…', self.backup_album)
        self.button(layout, 'Renomear originais pelo gerenciador…', self.photo_rename_help)
        self.button(layout, 'Agrupar catálogo por data de captura', self.group_photos)

    def photo_preview(self):
        try:
            row = self.selected('photos')
        except ValueError:
            return
        details = self.db.rows('SELECT * FROM photo_details WHERE photo_id=?', (row['id'],))
        if details:
            pixmap = QPixmap(details[0]['thumbnail'])
            self.preview.setPixmap(pixmap.scaled(450, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.photo_metadata.setPlainText(json.dumps(json.loads(details[0]['metadata']), ensure_ascii=False, indent=2))

    def photo_to_album(self):
        photo = self.selected('photos')
        album = self.selected_table(self.extra_tables['albums'])
        self.photos.add_to_album(album['id'], photo['id'])
        self.show_album()
        self.notify('Fotografia adicionada ao álbum.')

    def show_album(self):
        album = self.selected_table(self.extra_tables['albums'])
        rows = self.db.rows('SELECT photos.* FROM photos JOIN album_photos ON photos.id=photo_id WHERE album_id=? ORDER BY captured,path', (album['id'],))
        self.fill(self.extra_tables['album_contents'], rows)

    def backup_album(self):
        album = self.selected_table(self.extra_tables['albums'])
        destination = QFileDialog.getExistingDirectory(self, 'Destino das cópias da coleção')
        if destination:
            self.background(lambda: self.photos.backup_plan(album['id'], destination),
                            lambda plan: self.confirm_plan(plan, execute_copy))

    def photo_duplicates(self):
        rows = self.db.rows('SELECT digest, GROUP_CONCAT(path, char(10)) AS arquivos, COUNT(*) AS quantidade FROM photos GROUP BY digest HAVING COUNT(*)>1')
        dialog = QMessageBox(self)
        dialog.setText(f'{len(rows)} grupo(s) de duplicatas exatas no catálogo.')
        dialog.setDetailedText('\n\n'.join(r['arquivos'] for r in rows) or 'Nenhum duplicado.')
        dialog.exec()

    def group_photos(self):
        table = self.tables['photos']
        if table.columnCount() > 5:
            table.sortItems(5, Qt.SortOrder.AscendingOrder)
        self.notify('Catálogo ordenado por data de captura; use a pesquisa para filtrar um dia.')

    def photo_rename_help(self):
        row = self.selected('photos')
        self.source.setText(str(Path(row['path']).parent))
        self.navigation.setCurrentRow(1)
        self.notify('Analise a pasta, filtre as fotos e confira a prévia. As referências do catálogo serão atualizadas ao renomear.')

    def build_scripts(self):
        layout = self.page('Scripts')
        layout.addWidget(QLabel('Somente scripts cadastrados e confirmados pelo usuário. Executam com as permissões da sua conta.'))
        self.button(layout, 'Cadastrar e autorizar script local…', self.add_script)
        self.grid(layout, 'scripts')
        self.button(layout, 'Configurar argumentos do script selecionado…', self.edit_script_arguments)
        self.interpreter = QLineEdit(self.settings.get('python_interpreter', sys.executable if not getattr(sys, 'frozen', False) else 'python'))
        self.interpreter.setPlaceholderText('Executável Python usado para scripts')
        layout.addWidget(QLabel('Interpretador Python (não usa shell)'))
        layout.addWidget(self.interpreter)
        actions = QHBoxLayout()
        self.button(actions, 'Executar script selecionado…', self.run_script)
        self.button(actions, 'Interromper processo', self.stop_script)
        layout.addLayout(actions)
        self.script_progress = QProgressBar()
        self.script_progress.setRange(0, 100)
        layout.addWidget(self.script_progress)
        self.script_output = QPlainTextEdit()
        self.script_output.setReadOnly(True)
        self.script_output.setMaximumBlockCount(5000)
        layout.addWidget(self.script_output)
        layout.addWidget(QLabel('Progresso opcional: o script pode imprimir NEXUS_PROGRESS=50 (0 a 100). Histórico limitado a 1 MB por canal.'))
        self.grid(layout, 'script_runs')
        self.button(layout, 'Consultar saída da execução selecionada', self.show_script_history)

    def add_script(self):
        def save(values):
            if QMessageBox.question(self, 'Autorizar script', f'Autoriza cadastrar este script para execução manual?\n{values[3]}\nRevise o código antes de autorizar.') != QMessageBox.StandardButton.Yes:
                raise ValueError('Cadastro não autorizado.')
            self.workspace.add('scripts', values)
        self.form_dialog('Script autorizado', [('Nome', ''), ('Descrição', ''), ('Categoria', ''), ('Script local', 'script'),
                         ('Argumentos (lista JSON de textos)', '[]')], save)

    def edit_script_arguments(self):
        record = self.selected_table(self.extra_tables['scripts'])
        def save(values):
            args = arguments(values[0])
            self.db.execute('UPDATE scripts SET arguments=? WHERE id=?', (json.dumps(args), record['id']))
        self.form_dialog('Argumentos de execução', [('Lista JSON', record['arguments'])], save)

    def run_script(self):
        if self.process is not None:
            raise ValueError('Já existe um script em execução.')
        record = self.selected_table(self.extra_tables['scripts'])
        path = Path(record['path'])
        if not path.is_file():
            raise ValueError('Script não encontrado.')
        args = arguments(record['arguments'])
        if QMessageBox.question(self, 'Confirmar execução', f"Executar {path}?\nArgumentos: {args}\nO script pode alterar arquivos e acessar a rede.") != QMessageBox.StandardButton.Yes:
            return
        self.script_output.clear()
        self.output_channels = {'output': '', 'error': ''}
        self.progress_buffer = ''
        self.script_progress.setRange(0, 0)
        self.script_run_id = self.db.execute('INSERT INTO script_runs(script_id,started) VALUES(?,?)',
                                             (record['id'], datetime.now().isoformat(timespec='seconds')))
        process = QProcess(self)
        self.process = process
        self.settings.set('python_interpreter', self.interpreter.text().strip())
        process.setProgram(self.interpreter.text().strip())
        process.setArguments(['-u', str(path), *args])
        process.setWorkingDirectory(str(path.parent))
        process.readyReadStandardOutput.connect(lambda: self.read_script('output'))
        process.readyReadStandardError.connect(lambda: self.read_script('error'))
        process.finished.connect(self.script_finished)
        process.errorOccurred.connect(self.script_error)
        process.start()

    def read_script(self, channel):
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput() if channel == 'output' else self.process.readAllStandardError())
        text = data.decode('utf-8', errors='replace')
        room = max(0, 1000000-len(self.output_channels[channel]))
        self.output_channels[channel] += text[:room]
        self.script_output.appendPlainText(('stderr: ' if channel == 'error' else '') + text)
        if channel == 'output':
            self.progress_buffer = (self.progress_buffer + text)[-8192:]
            lines = self.progress_buffer.split('\n')
            self.progress_buffer = lines.pop()
            for line in lines:
                if line.startswith('NEXUS_PROGRESS='):
                    try:
                        value = int(line.split('=', 1)[1])
                        self.script_progress.setRange(0, 100)
                        self.script_progress.setValue(max(0, min(100, value)))
                    except ValueError:
                        pass

    def script_error(self, error):
        if self.process and error == QProcess.ProcessError.FailedToStart:
            self.output_channels['error'] += self.process.errorString()
            self.script_finished(-1, QProcess.ExitStatus.CrashExit)

    def script_finished(self, code, status):
        if self.process is None:
            return
        self.read_script('output')
        self.read_script('error')
        self.db.execute('UPDATE script_runs SET finished=?,exit_code=?,output=?,error=? WHERE id=?',
            (datetime.now().isoformat(timespec='seconds'), code, self.output_channels['output'], self.output_channels['error'], self.script_run_id))
        if code != 0:
            log_error(self.db, f'script_run:{self.script_run_id}', RuntimeError(f'Processo finalizado com código {code}'))
        self.process.deleteLater()
        self.process = None
        self.script_progress.setRange(0, 100)
        self.script_progress.setValue(100 if code == 0 else 0)
        self.refresh()
        self.notify(f'Script finalizado: código {code}.')

    def stop_script(self):
        if self.process:
            process = self.process
            process.terminate()
            # Kill only this QProcess if it ignores graceful termination.
            QTimer.singleShot(3000, lambda: process.kill() if self.process is process else None)
            self.notify('Interrupção solicitada ao processo Python.')

    def show_script_history(self):
        record = self.selected_table(self.extra_tables['script_runs'])
        self.script_output.setPlainText(record['output'] + '\n--- stderr ---\n' + record['error'])

    def closeEvent(self, event):
        if self.process is not None:
            QMessageBox.information(self, 'Script em execução', 'Interrompa o script antes de fechar.')
            event.ignore()
            return
        if self.pomo_timer.isActive():
            if QMessageBox.question(self, 'Sessão em andamento', 'Descartar o Pomodoro em andamento e fechar?') != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        super().closeEvent(event)
        if event.isAccepted():
            close_logger(self.db)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Window()
    def unhandled(exc_type, exc, tb):
        import traceback
        log_error(window.db, 'unhandled', exc, ''.join(traceback.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = unhandled
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
