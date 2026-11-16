"""Prévias completas em tabelas virtuais, com cancelamento como padrão."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QPlainTextEdit
from nexus.ui.models import RecordView, prepare_rows


class PreviewDialog(QDialog):
    def __init__(self, plan, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 560)
        layout = QVBoxLayout(self)
        label = QLabel(f'{len(plan)} arquivo(s). Confira todos os caminhos antes de confirmar. Destinos existentes nunca serão sobrescritos.')
        label.setWordWrap(True)
        layout.addWidget(label)
        table = RecordView(['source', 'target'], self)
        table.records.replace(prepare_rows([{'source': str(p.source), 'target': str(p.target)} for p in plan], ['source', 'target']))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Confirmar operação')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def show_result(parent, result):
    dialog = QDialog(parent)
    dialog.setWindowTitle('Resultado — simulação' if getattr(result, 'simulated', 0) else 'Resultado do lote')
    dialog.resize(900, 480)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(str(result)))
    details = QPlainTextEdit()
    details.setReadOnly(True)
    lines = getattr(result, 'errors', []) + getattr(result, 'previews', [])
    details.setPlainText('\n'.join(lines))
    layout.addWidget(details)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
