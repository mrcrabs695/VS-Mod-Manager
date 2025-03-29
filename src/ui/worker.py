import traceback
from PySide6.QtCore import QRunnable, Signal, Slot, QObject

class WorkerSignals(QObject):
    finished = Signal()
    result = Signal(object)
    error = Signal(tuple)
    progress = Signal(int)
    progress_end = Signal(int)
    progress_start = Signal(int)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        if kwargs.get("signals", None) is None:
            self.signals = WorkerSignals()
        else:
            self.signals = kwargs.pop("signals")
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
    
    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            traceback.print_exc()
            self.signals.error.emit((type(e), e, traceback.format_exc()))
        finally:
            self.signals.finished.emit()