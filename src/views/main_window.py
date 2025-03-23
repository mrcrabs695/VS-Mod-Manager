from .mod_index import HyperTag, ModDetail
from vsmoddb.client import ModDbClient

from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox, QLabel, QPushButton, QScrollArea, QGraphicsPixmapItem
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QPixmap, QPalette, QColor

class RootView(QWidget):
    def __init__(self):
        super().__init__()
        
        self.mod_api_client = ModDbClient()
        mod = self.mod_api_client.get_mod("primitivesurvival")
        
        root_layout = QGridLayout(self)
        root_layout.setObjectName("root_layout")
        
        # configure view toggles
        mod_index_switch = QPushButton()
        mod_index_switch.pressed.connect(self.show_mod_index)
        mod_index_switch.setText("Mod Index")
        mod_index_switch.setObjectName("mod_index_switch")
        local_mods_switch = QPushButton()
        local_mods_switch.pressed.connect(self.show_local_mods)
        local_mods_switch.setText("Installed Mods")
        local_mods_switch.setObjectName("local_mods_switch")
        settings_switch = QPushButton()
        settings_switch.pressed.connect(self.show_settings)
        settings_switch.setText("Settings")
        settings_switch.setObjectName("settings_switch")
        
        image = QPixmap()
        image.load("data/test.png")
        test_pixmap = QLabel()
        test_pixmap.setPixmap(image)
        mod_detail = ModDetail(mod)
        
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(mod_detail)
        self.view_stack.addWidget(test_pixmap)
        self.view_stack.addWidget(HyperTag("Worldgen", "#333333"))
        
        root_layout.addWidget(mod_index_switch, 0, 0)
        root_layout.addWidget(local_mods_switch, 0, 1)
        root_layout.addWidget(settings_switch, 0, 2)
        root_layout.addWidget(self.view_stack, 1, 0, 1, 3)
    
    @Slot()
    def show_mod_index(self):
        # will change the stacked widget to show the mod index view
        self.view_stack.setCurrentIndex(0)
    
    @Slot()
    def show_local_mods(self):
        # will change the stacked widget to show the local mods/profile selection view
        self.view_stack.setCurrentIndex(1)
    
    @Slot()
    def show_settings(self):
        # will change the stacked widget to show the settings menu
        self.view_stack.setCurrentIndex(2)