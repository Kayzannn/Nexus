"""Entrada estável; módulos das fases posteriores exigem opção explícita."""
import argparse
import sys
import traceback
from PySide6.QtWidgets import QApplication, QMessageBox
from nexus.ui.foundation import Window
from nexus.core.logger import log_error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='NEXUS — Personal Automation Hub')
    parser.add_argument('--experimental-modules', action='store_true', help='Abre implementações das Fases 3–5, ainda experimentais')
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setStyle('Fusion')
    cls = Window
    if args.experimental_modules:
        try:
            from nexus.ui.main_window import Window as ExperimentalWindow
        except ImportError:
            parser.error('Módulos experimentais indisponíveis. Instale .[experimental] ou gere o pacote com build.py --experimental.')
        cls = ExperimentalWindow
    try:
        window = cls()
    except Exception as exc:
        QMessageBox.critical(None, 'NEXUS — falha de inicialização', str(exc))
        return 1
    if args.experimental_modules:
        window.setWindowTitle('NEXUS — MÓDULOS EXPERIMENTAIS (Fases 3–5)')
    def unhandled(exc_type, exc, tb):
        log_error(window.db, 'unhandled', exc, ''.join(traceback.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = unhandled
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
