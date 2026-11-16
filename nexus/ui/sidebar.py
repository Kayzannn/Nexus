"""Navegação lateral redimensionável."""
from PySide6.QtWidgets import QListWidget


class Sidebar(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('navigation')
        self.setMaximumWidth(210)
