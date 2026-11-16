"""Interface do gerenciador prioritário, isolada dos módulos experimentais."""
from datetime import datetime, timedelta
from pathlib import Path
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QSpinBox)
from nexus.services.manager import scan, filter_rows, rename_plan, category_plan
from nexus.services.files import execute_copy, plan_copy
from nexus.core.logger import log_error
from nexus.ui.dialogs import PreviewDialog, show_result
from nexus.ui.models import prepare_rows


class FileManagerMixin:
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
        if PreviewDialog(plan, 'Prévia de cópia', self).exec() != QDialog.DialogCode.Accepted:
            return
        self.background(lambda: self.manager.copy(plan, continue_on_error=True), lambda result: (self.show_batch(result), self.refresh()))

    def copy_files(self):
        source, destination = self.source.text().strip(), self.destination.text().strip()
        if not source or not destination:
            raise ValueError('Selecione origem e destino.')
        extension = self.extension.text()
        self.background(lambda: plan_copy(Path(source), Path(destination), extension), lambda plan: self.confirm_plan(plan, execute_copy))

    def analyze(self):
        folder = self.source.text().strip()
        if not folder:
            raise ValueError('Selecione uma pasta.')
        recursive = self.recursive.isChecked()
        self.scan_generation += 1
        generation = self.scan_generation
        def analyze():
            errors = []
            def report(path, exc):
                log_error(self.db, f'scan:{path}', exc)
                errors.append(f'{path}: {exc}')
            return scan(folder, recursive, on_error=report), errors
        def done(result):
            if generation != self.scan_generation:
                return
            self.scanned, errors = result
            self.apply_file_filters()
            if errors:
                dialog = QMessageBox(self)
                dialog.setText(f'Análise parcial: {len(errors)} erro(s). Os arquivos acessíveis estão na tabela.')
                dialog.setDetailedText('\n'.join(errors))
                dialog.exec()
        self.background(analyze, done)

    def apply_file_filters(self):
        after = datetime.strptime(self.file_after.text(), '%Y-%m-%d').timestamp() if self.file_after.text() else None
        before = (datetime.strptime(self.file_before.text(), '%Y-%m-%d') + timedelta(days=1)).timestamp() - .000001 if self.file_before.text() else None
        if after is not None and before is not None and after > before:
            raise ValueError('O início do intervalo deve ser anterior ao fim.')
        rows = self.scanned
        args = (self.file_ext.text(), self.file_min.value()*1024, self.file_max.value()*1024 or None, after, before)
        self.filter_generation += 1
        generation = self.filter_generation
        columns = self.extra_tables['scan'].records.columns
        def work():
            return prepare_rows(filter_rows(rows, *args), columns)
        def done(prepared):
            if generation == self.filter_generation:
                self.extra_tables['scan'].records.replace(prepared)
                self.notify(f'{len(prepared[0])} arquivo(s) após os filtros.')
        self.background(work, done)

    def file_rows(self):
        table = self.extra_tables['scan']
        table.proxy.search(table.search_field.text())
        rows = table.visible_records()
        if not rows:
            raise ValueError('Analise uma pasta e verifique os filtros e a pesquisa.')
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
        if PreviewDialog(plan, 'Prévia obrigatória', self).exec() == QDialog.DialogCode.Accepted:
            self.background(lambda: self.manager.execute(plan, kind, continue_on_error=True), self.after_files)

    def after_files(self, result=None):
        if result is not None:
            self.show_batch(result)
        self.refresh()
        self.analyze()

    def show_batch(self, result):
        show_result(self, result)

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
