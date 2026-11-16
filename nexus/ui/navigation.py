"""Páginas opacas: evita composição de telas antigas no backing store do Qt."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QWidget


def scroll_page(content: QWidget) -> QScrollArea:
    content.setObjectName('modulePage')
    content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    content.setAutoFillBackground(True)
    scroll = QScrollArea()
    scroll.setObjectName('moduleScroll')
    scroll.setWidgetResizable(True)
    scroll.viewport().setObjectName('moduleViewport')
    scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    scroll.viewport().setAutoFillBackground(True)
    scroll.setWidget(content)
    return scroll


def switch_page(stack, index: int) -> None:
    if not 0 <= index < stack.count():
        return
    # Full-page opacity effects on QScrollArea can leave stale pixels on Windows.
    # A normal StackOne switch paints an opaque page and keeps only it visible.
    stack.setCurrentIndex(index)
    stack.currentWidget().update()
    stack.update()
