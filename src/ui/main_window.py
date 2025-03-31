import os

from . import moddb_client, user_settings
from .mod_index import HyperTag, ModDetail, ModIndex
from .settings_page import SettingsPage
from .worker import WorkerSignals
from settings import get_installed_game_version, APP_PATH

from vsmoddb.client import ModDbClient

from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox, QLabel, QPushButton, QScrollArea, QGraphicsPixmapItem, QDialog, QFormLayout, QMessageBox
from PySide6.QtCore import Slot, Qt, Signal
from PySide6.QtGui import QPixmap, QPalette, QColor, QIcon


class FirstLaunchPopup(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        
        self.continue_startup = WorkerSignals()
        
        self.setWindowTitle("Configure Mod Manager")
        self.setMinimumSize(600, 400)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
        self.setLayout(QVBoxLayout())
        
        self.main_text_label = QLabel("<h1>Welcome to VS Mod Manager!</h1><p>Select the version of Vintage Story you are using to setup the mod manager.</p>")
        self.main_text_label.setWordWrap(True)
        self.main_text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.form_layout = QFormLayout()
        self.version_combo_box = QComboBox()
        
        self.version_texts = [version.name for version in moddb_client.versions]
        try:
            current_version_index = self.version_texts.index('v' + user_settings.game_version)
        except ValueError:
            current_version_index = 0
        
        self.version_combo_box.addItems(self.version_texts)
        self.version_combo_box.setCurrentIndex(current_version_index)
        self.form_layout.addRow(QLabel("<h2>Game Version: </h2>"), self.version_combo_box)
        
        self.game_path_line_edit = QLineEdit(user_settings.game_path if user_settings.game_path else "")
        self.game_path_line_edit.setPlaceholderText("Enter the path to your game's root folder.")
        self.form_layout.addRow(QLabel("<h2>Game Path: </h2>"), self.game_path_line_edit)
        
        self.rescan_path_button = QPushButton("Rescan Path")
        self.rescan_path_button.clicked.connect(lambda clicked: self.rescan_path())
        self.form_layout.addWidget(self.rescan_path_button)
        
        self.game_data_path_line_edit = QLineEdit(user_settings.game_data_path if user_settings.game_data_path else "")
        self.game_data_path_line_edit.setPlaceholderText("Enter the path to your game's user data folder.")
        self.form_layout.addRow(QLabel("<h2>Game Data Path: </h2>"), self.game_data_path_line_edit)
        
        self.mod_install_location_line_edit = QLineEdit(user_settings.mod_download_location if user_settings.mod_download_location else "")
        self.mod_install_location_line_edit.setPlaceholderText("Enter the path where you would like the mod manager to install new mods (not your games mod folder).")
        self.form_layout.addRow(QLabel("<h2>Mod Install Location: </h2>"), self.mod_install_location_line_edit)
        
        self.form = QWidget()
        self.form.setLayout(self.form_layout)
        
        self.confirm_button = QPushButton("Save")
        self.confirm_button.clicked.connect(self.on_confirm_clicked)
        
        self.layout().addWidget(self.main_text_label)
        self.layout().addWidget(self.form)
        self.layout().addWidget(self.confirm_button)
        
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
    
    def check_paths(self):
        game_path = self.game_path_line_edit.text().strip()
        game_data_path = self.game_data_path_line_edit.text().strip()
        
        if not os.path.exists(game_path):
            QMessageBox.warning(self, "Error", f"Game path does not exist: {game_path}")
            return None
        
        if not os.path.exists(game_data_path):
            QMessageBox.warning(self, "Error", f"Game data path does not exist: {game_data_path}")
            return None
        
        return (game_path, game_data_path)
    
    def rescan_path(self):
        game_path, game_data_path = self.check_paths()
        
        if game_path is None or game_data_path is None:
            return
        
        version = get_installed_game_version()
        print(version)
        if version is not None:
            try:
                version_index = self.version_texts.index('v' + version)
            except ValueError:
                QMessageBox.warning(self, "Error", "Failed to get game version (make sure you have the right folder selected)")
                return
            self.version_combo_box.setCurrentIndex(version_index)
            user_settings.game_version = version
    
    def on_confirm_clicked(self):
        game_version = self.version_combo_box.currentText().removeprefix("v")
        game_path, game_data_path = self.check_paths()
        
        if game_path is None or game_data_path is None:
            return
        
        mod_download_location = self.mod_install_location_line_edit.text().strip()
        
        if not os.path.exists(mod_download_location):
            QMessageBox.warning(self, "Error", f"Mod download location does not exist: {mod_download_location}")
            return
        
        if user_settings.game_version is not None and game_version != get_installed_game_version():
            message_box = QMessageBox()
            message_box.setText(f"Selected game version does not match found game version: {user_settings.game_version}")
            message_box.setInformativeText("Do you want to continue?")
            message_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Default)
            message_box.setDefaultButton(QMessageBox.Yes)
            
            response = message_box.exec_()
            if response == QMessageBox.StandardButton.No:
                return
            elif response == QMessageBox.StandardButton.Default:
                game_version = user_settings.game_version
        
        self.hide()
        user_settings.game_version = game_version
        user_settings.game_path = game_path
        user_settings.game_data_path = game_data_path
        user_settings.mod_download_location = mod_download_location
        user_settings.first_launch = False
        user_settings.save()
        
        self.continue_startup.finished.emit()
        self.deleteLater()

class RootView(QWidget):
    def __init__(self):
        super().__init__()
        
        if user_settings.first_launch:
            self.first_launch_popup = FirstLaunchPopup()
            self.first_launch_popup.show()
            self.first_launch_popup.continue_startup.finished.connect(self.continue_setup)
        else:
            self.continue_setup()
    
    def continue_setup(self):
        user_settings.main_window.show()
        user_settings.main_window.setFocus()
        
        root_layout = QGridLayout(self)
        root_layout.setObjectName("root_layout")
        
        # configure view toggles
        mod_index_switch = QPushButton()
        mod_index_switch.pressed.connect(self.show_mod_index)
        mod_index_switch.setText("Mod Index")
        mod_index_switch.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/world-download.svg')))
        mod_index_switch.setObjectName("mod_index_switch")
        local_mods_switch = QPushButton()
        local_mods_switch.pressed.connect(self.show_local_mods)
        local_mods_switch.setText("Installed Mods")
        local_mods_switch.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/files.svg')))
        local_mods_switch.setObjectName("local_mods_switch")
        settings_switch = QPushButton()
        settings_switch.pressed.connect(self.show_settings)
        settings_switch.setText("Settings")
        settings_switch.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/settings.svg')))
        settings_switch.setObjectName("settings_switch")
        
        image = QPixmap()
        image.load("data/test.png")
        test_pixmap = QLabel()
        test_pixmap.setPixmap(image)
        mod_detail = ModIndex()
        self.settings_view = SettingsPage()
        
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(mod_detail)
        self.view_stack.addWidget(test_pixmap)
        self.view_stack.addWidget(self.settings_view)
        
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