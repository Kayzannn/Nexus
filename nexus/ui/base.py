"""Interface desktop. Operações de disco demoradas rodam fora da thread Qt."""
import sys
from pathlib import Path
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QFormLayout,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QLabel, QAbstractItemView)
import pyqtgraph as pg
from nexus.db import Database
from nexus.services.records import Records
from nexus.services.photos import Photos
from nexus.services.automations import Automations
from nexus.services.files import plan_copy, execute_copy, duplicates


class Window(QMainWindow):
    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self.records, self.photos, self.automations = Records(self.db), Photos(self.db), Automations(self.db)
        self.pool = QThreadPool(self)
        self.jobs = set()
        self.setWindowTitle("NEXUS — Personal Automation Hub")
        self.resize(1100, 760)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tables = {}
        self.build_files()
        self.build_studies()
        self.build_calibrations()
        self.build_photos()
        self.build_automations()
        self.refresh()
        self.statusBar().showMessage(f"Dados locais: {self.db.path}")

    def page(self, title):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.tabs.addTab(page, title)
        return layout

    def button(self, layout, text, callback):
        button = QPushButton(text)
        button.clicked.connect(lambda: self.guard(callback))
        layout.addWidget(button)
        return button

    def guard(self, callback):
        try:
            callback()
        except Exception as exc:
            QMessageBox.warning(self, "NEXUS", str(exc))

    def table(self, layout, key):
        table = QTableWidget()
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(table)
        self.tables[key] = table
        self.button(layout, "Excluir registro selecionado", lambda: self.delete(key))

    def selected(self, key):
        row = self.tables[key].currentRow()
        if row < 0:
            raise ValueError("Selecione um registro.")
        return self.data[key][row]

    def delete(self, key):
        record = self.selected(key)
        if QMessageBox.question(self, "Excluir registro", "Excluir apenas este registro do catálogo? Os arquivos originais serão preservados.") == QMessageBox.StandardButton.Yes:
            self.records.delete(key, record["id"])
            self.refresh()

    def refresh(self):
        self.data = {}
        for key, table in self.tables.items():
            rows = self.records.list(key)
            self.data[key] = rows
            headers = list(rows[0]) if rows else ["id"]
            table.setColumnCount(len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, column in enumerate(headers):
                    table.setItem(i, j, QTableWidgetItem(str(row[column])))
            table.resizeColumnsToContents()
        totals = self.db.rows("SELECT subject, SUM(minutes) AS total FROM studies GROUP BY subject ORDER BY subject")
        self.plot.clear()
        if totals:
            self.plot.addItem(pg.BarGraphItem(x=list(range(len(totals))), height=[r["total"] for r in totals], width=.6))
        self.plot.getAxis("bottom").setTicks([[(i, r["subject"]) for i, r in enumerate(totals)]])

    def folder_field(self, layout, label):
        line = QLineEdit()
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(line)
        def choose():
            path = QFileDialog.getExistingDirectory(self, label)
            if path:
                line.setText(path)
        self.button(row, "Escolher pasta", choose)
        layout.addLayout(row)
        return line

    def build_files(self):
        layout = self.page("Arquivos")
        layout.addWidget(QLabel("Cópia da pasta imediata (sem subpastas). Originais preservados; conflitos interrompem a operação."))
        self.source = self.folder_field(layout, "Origem")
        self.destination = self.folder_field(layout, "Destino")
        self.extension = QLineEdit()
        self.extension.setPlaceholderText("Extensão opcional, por exemplo .jpg")
        layout.addWidget(self.extension)
        self.button(layout, "Gerar prévia e copiar…", self.copy_files)
        self.button(layout, "Localizar duplicados na origem", self.find_duplicates)
        layout.addStretch()

    def paths(self):
        if not self.source.text().strip() or not self.destination.text().strip():
            raise ValueError("Selecione origem e destino.")
        return Path(self.source.text()), Path(self.destination.text()), self.extension.text()

    def confirm_plan(self, plan, run):
        if not plan:
            QMessageBox.information(self, "Prévia", "Nenhum arquivo corresponde à regra.")
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Confirmar cópia")
        dialog.setText(f"Copiar {len(plan)} arquivo(s)? Consulte os detalhes antes de confirmar.")
        dialog.setDetailedText("\n".join(f"{p.source} → {p.target}" for p in plan))
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        if dialog.exec() == QMessageBox.StandardButton.Yes:
            self.background(lambda: run(plan), lambda n: QMessageBox.information(self, "Concluído", f"{n} arquivo(s) copiado(s)."))

    def copy_files(self):
        args = self.paths()
        self.background(lambda: plan_copy(*args), lambda plan: self.confirm_plan(plan, execute_copy))

    def find_duplicates(self):
        if not self.source.text().strip():
            raise ValueError("Selecione a origem.")
        source = Path(self.source.text())
        def show(groups):
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Duplicados SHA-256")
            dialog.setText(f"{len(groups)} grupo(s) de arquivos idênticos. Nenhum arquivo foi removido.")
            dialog.setDetailedText("\n\n".join("\n".join(g) for g in groups) or "Nenhum duplicado.")
            dialog.exec()
        self.background(lambda: duplicates(source), show)

    def build_studies(self):
        layout = self.page("Estudos")
        form = QFormLayout()
        subject, notes = QLineEdit(), QLineEdit()
        minutes = QSpinBox()
        minutes.setRange(1, 1440)
        minutes.setValue(30)
        for label, field in [("Assunto", subject), ("Minutos", minutes), ("Notas", notes)]:
            form.addRow(label, field)
        layout.addLayout(form)
        def save():
            self.records.add_study(subject.text(), minutes.value(), notes.text())
            self.refresh()
        self.button(layout, "Registrar sessão", save)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("left", "Minutos")
        self.plot.setMaximumHeight(220)
        layout.addWidget(self.plot)
        self.table(layout, "studies")

    def build_calibrations(self):
        layout = self.page("Calibrações 3D")
        form = QFormLayout()
        printer, material, notes = QLineEdit(), QLineEdit(), QLineEdit()
        temperature, flow = QDoubleSpinBox(), QDoubleSpinBox()
        temperature.setRange(0, 500)
        temperature.setValue(200)
        flow.setRange(.01, 300)
        flow.setValue(100)
        for label, field in [("Impressora", printer), ("Material", material), ("Temperatura (°C)", temperature), ("Fluxo (%)", flow), ("Resultado / notas", notes)]:
            form.addRow(label, field)
        layout.addLayout(form)
        def save():
            self.records.add_calibration(printer.text(), material.text(), temperature.value(), flow.value(), notes.text())
            self.refresh()
        self.button(layout, "Salvar calibração", save)
        self.table(layout, "calibrations")

    def build_photos(self):
        layout = self.page("Fotografias")
        layout.addWidget(QLabel("Catálogo por referência: mantenha os arquivos originais em seus caminhos."))
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("Tags para as fotos importadas")
        layout.addWidget(self.tags)
        def choose():
            paths, _ = QFileDialog.getOpenFileNames(self, "Importar fotos", "", "Imagens (*.jpg *.jpeg *.png *.tif *.tiff *.webp)")
            tags = self.tags.text()
            def load():
                for path in paths:
                    self.photos.import_file(Path(path), tags)
                return len(paths)
            if paths:
                self.background(load, lambda _: self.refresh())
        self.button(layout, "Importar fotografias", choose)
        self.table(layout, "photos")

    def build_automations(self):
        layout = self.page("Automações")
        layout.addWidget(QLabel("Regras manuais de cópia por extensão. Não há agendamento nesta versão."))
        source = self.folder_field(layout, "Origem")
        destination = self.folder_field(layout, "Destino")
        extension = QLineEdit()
        extension.setPlaceholderText("Extensão opcional: .pdf")
        layout.addWidget(extension)
        def save():
            if not source.text().strip() or not destination.text().strip():
                raise ValueError("Selecione as duas pastas.")
            args = source.text(), destination.text(), extension.text()
            self.background(lambda: self.automations.save(*args), lambda _: self.refresh())
        def run():
            rule = self.selected("automations").copy()
            self.background(lambda: self.automations.plan(rule),
                            lambda plan: self.confirm_plan(plan, lambda p: self.automations.run(rule, p, continue_on_error=True)))
        self.button(layout, "Salvar regra", save)
        self.button(layout, "Prévia e execução da regra selecionada…", run)
        self.table(layout, "automations")

    def closeEvent(self, event):
        if self.jobs:
            QMessageBox.information(self, "Operação em andamento", "Aguarde a conclusão das operações antes de fechar.")
            event.ignore()
        else:
            event.accept()
