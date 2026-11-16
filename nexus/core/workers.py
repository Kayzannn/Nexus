"""Workers sem acesso a widgets; resultados são entregues por sinais Qt."""
import traceback
from PySide6.QtCore import QObject, Signal, QRunnable


class Events(QObject):
    done = Signal(object, object)
    error = Signal(object, str)


class Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn, self.events = fn, Events()
        self.traceback = ''

    def run(self):
        try:
            self.events.done.emit(self, self.fn())
        except Exception as exc:
            self.traceback = traceback.format_exc()
            self.events.error.emit(self, str(exc))
