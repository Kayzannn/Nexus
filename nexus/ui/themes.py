from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_theme(dark=True):
    bg, panel, text, border = ('#111318', '#1d222b', '#e8ecf4', '#343d4c') if dark else ('#eef1f6', '#ffffff', '#172233', '#bdc8d8')
    palette = QPalette()
    for role, color in [(QPalette.ColorRole.Window, bg), (QPalette.ColorRole.Base, panel),
                        (QPalette.ColorRole.AlternateBase, bg), (QPalette.ColorRole.Text, text),
                        (QPalette.ColorRole.WindowText, text), (QPalette.ColorRole.Button, panel),
                        (QPalette.ColorRole.ButtonText, text), (QPalette.ColorRole.Highlight, '#287bd9'),
                        (QPalette.ColorRole.HighlightedText, '#ffffff')]:
        palette.setColor(role, QColor(color))
    app = QApplication.instance()
    app.setPalette(palette)
    app.setStyleSheet(f'''
        QWidget {{ font-family: 'Segoe UI', sans-serif; font-size: 13px; }}
        QMainWindow, QScrollArea {{ background: {bg}; }}
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QPlainTextEdit {{
            background: {panel}; color: {text}; border: 1px solid {border}; border-radius: 5px; padding: 6px; }}
        QPushButton {{ background: {panel}; color: {text}; border: 1px solid {border}; border-radius: 5px; padding: 7px 12px; }}
        QPushButton:hover {{ border-color: #398fff; }}
        QPushButton:pressed {{ background: #287bd9; color: white; }}
        QTableWidget {{ background: {panel}; color: {text}; gridline-color: {border}; border: 0; }}
        QHeaderView::section {{ background: {bg}; color: {text}; padding: 8px; border: 0; }}
        QListWidget#navigation {{ background: {panel}; border: 0; padding: 8px; }}
        QListWidget#navigation::item {{ padding: 14px 8px; border-radius: 6px; }}
        QListWidget#navigation::item:selected {{ background: #225b99; color: white; }}
        QLabel#card {{ background: {panel}; border: 1px solid {border}; border-radius: 8px; padding: 16px; }}
        QProgressBar {{ border: 0; background: {panel}; max-height: 5px; }}
        QProgressBar::chunk {{ background: #398fff; }}
    ''')
