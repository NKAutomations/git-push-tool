from threading import Event
from PySide6.QtCore import QThread, Signal
from .models import AppError
from .security import redact


class Job(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(str, object, object)
    log = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function
        self.cancel = Event()

    def run(self):
        try:
            result = self.function(self)
            self.succeeded.emit(result)
        except AppError as error:
            self.failed.emit(redact(str(error)))
        except OSError:
            self.failed.emit('Dateizugriff fehlgeschlagen. Pfad, Rechte und freien Speicher pruefen.')
        except Exception:
            # Do not expose arbitrary exception repr: API libraries can contain credentials.
            self.failed.emit('Unerwarteter Fehler. Bereits abgeschlossene Schritte bleiben erhalten. Remote-Stand vor Wiederholung pruefen.')
        finally:
            self.function = None
