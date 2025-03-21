import sys
from PySide6.QtWidgets import QMainWindow, QWidget, QApplication
from vsmoddb.client import ModDbClient
from vsmoddb.models import SearchOrderBy

class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

if __name__ == "__main__":
    app = QApplication([])
    widget = MainWindow()
    widget.show()
    sys.exit(app.exec())
    
    # testing
    # client = ModDbClient()
    # print(client.get_mod("carrycapacity"))
    