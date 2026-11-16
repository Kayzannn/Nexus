"""Tabelas virtuais: dados por linha, sem criar widgets por célula."""
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLineEdit, QTableView

RECORD_ROLE = Qt.ItemDataRole.UserRole
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
SEARCH_ROLE = Qt.ItemDataRole.UserRole + 2
DATE_COLUMNS = {'created', 'modified', 'captured'}
LABELS = {'path': 'Caminho', 'name': 'Nome', 'extension': 'Extensão', 'size': 'Bytes',
          'created': 'Criação', 'modified': 'Modificação', 'captured': 'Captura EXIF',
          'source': 'Origem', 'target': 'Destino', 'kind': 'Operação', 'status': 'Estado',
          'error': 'Erro', 'context': 'Contexto', 'message': 'Mensagem'}


def display_value(key: str, value: Any) -> str:
    if value is None:
        return ''
    if key in DATE_COLUMNS and isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).isoformat(' ', timespec='seconds')
    return str(value)


def prepare_rows(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> tuple:
    """Prepare searchable text in the worker, not during painting/filtering."""
    return list(rows), [' '.join(display_value(k, row.get(k)) for k in columns).casefold() for row in rows]


class RecordModel(QAbstractTableModel):
    def __init__(self, columns: Sequence[str], parent=None):
        super().__init__(parent)
        self.columns = list(columns)
        self.records: list[dict[str, Any]] = []
        self.search_text: list[str] = []

    def replace(self, prepared: tuple) -> None:
        self.beginResetModel()
        self.records, self.search_text = prepared
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        row = self.records[index.row()]
        if role == RECORD_ROLE:
            return row
        if role == SEARCH_ROLE:
            return self.search_text[index.row()]
        value = row.get(self.columns[index.column()])
        if role == SORT_ROLE:
            return value
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return display_value(self.columns[index.column()], value)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return LABELS.get(self.columns[section], self.columns[section]) if orientation == Qt.Orientation.Horizontal else section+1
        return None


class RecordProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ''
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(True)

    def search(self, text: str):
        self.query = text.casefold()
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        return not self.query or self.query in model.search_text[row]

    def lessThan(self, left, right):
        a, b = left.data(SORT_ROLE), right.data(SORT_ROLE)
        if a is None or b is None:
            return a is None and b is not None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a < b
        return str(a).casefold() < str(b).casefold()


class RecordView(QTableView):
    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self.records = RecordModel(columns, self)
        self.proxy = RecordProxy(self)
        self.proxy.setSourceModel(self.records)
        self.setModel(self.proxy)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setDefaultSectionSize(26)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setDefaultSectionSize(160)
        self.setMinimumHeight(150)

    def selected_record(self):
        index = self.currentIndex()
        if not index.isValid():
            raise ValueError('Selecione uma operação na tabela.')
        return index.data(RECORD_ROLE)

    def visible_records(self):
        return [self.proxy.index(i, 0).data(RECORD_ROLE) for i in range(self.proxy.rowCount())]
