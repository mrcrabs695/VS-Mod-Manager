import sys
from vsmoddb.client import ModDbClient
from vsmoddb.models import SearchOrderBy
from ui.main_window import RootView
from ui import user_settings, moddb_client

from PySide6.QtWidgets import QMainWindow, QWidget, QApplication
from PySide6.QtCore import Slot

class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        user_settings.main_window = self
        root_view = RootView()
        self.setCentralWidget(root_view)
        
        self.setWindowTitle("VS Mod Manager")

@Slot()
def shutdown():
    user_settings.save()
    moddb_client.cache_manager.save_to_file()

if __name__ == "__main__":
    app = QApplication([])
    widget = MainWindow()
    app.aboutToQuit.connect(shutdown)
    sys.exit(app.exec())
    
    # testing
    # client = ModDbClient()
    # print(client.get_mod("carrycapacity"))
    