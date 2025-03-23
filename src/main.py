import sys
from vsmoddb.client import ModDbClient
from vsmoddb.models import SearchOrderBy
from views.main_window import RootView

from PySide6.QtWidgets import QMainWindow, QWidget, QApplication

class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        root_view = RootView()
        self.setCentralWidget(root_view)
        
        self.setWindowTitle("VS Mod Manager")

if __name__ == "__main__":
    app = QApplication([])
    widget = MainWindow()
    widget.show()
    sys.exit(app.exec())
    
    # testing
    # client = ModDbClient()
    # print(client.get_mod("carrycapacity"))
    