import os
import traceback

from . import moddb_client, thread_pool, user_settings
from settings import locate_user_settings_path, get_installed_game_version
from .worker import Worker, WorkerSignals
from vsmoddb.models import Mod, Comment, ModRelease

from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox, QLabel, QPushButton, QScrollArea, QGraphicsPixmapItem, QSizePolicy, QFrame, QProgressDialog, QMessageBox, QFormLayout
from PySide6.QtCore import Slot, QSize, QThread, QObject, QThreadPool, QUrl
from PySide6.QtGui import QPixmap, QColor, QPalette, QDesktopServices
from httpx import HTTPStatusError

# TODO: this is very similar to the first time launch popup as of now since there is not many settings to be changed

class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.open_settings_folder_button = QPushButton("Open Settings Folder")
        self.open_settings_folder_button.setMaximumSize(200, 30)
        self.open_settings_folder_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(locate_user_settings_path())))
        
        self.reset_cache_button = QPushButton("Reset Cache")
        self.reset_cache_button.setMaximumSize(200, 30)
        self.reset_cache_button.clicked.connect(lambda: moddb_client.cache_manager.clear())
        self.layout().addWidget(self.open_settings_folder_button)
        self.layout().addWidget(self.reset_cache_button)
        
        self.app_settings_title = QLabel("<h2>Mod Manager Settings</h2>")
        self.layout().addWidget(self.app_settings_title)
        
        self.app_settings_container = QWidget()
        self.app_settings_container.setLayout(QFormLayout())
        
        self.cache_location_line_edit = QLineEdit(user_settings.cache_location)
        self.cache_location_line_edit.textChanged.connect(lambda text: self.on_anything_changed())
        self.app_settings_container.layout().addRow("Cache Location:", self.cache_location_line_edit)
        self.mod_install_location_line_edit = QLineEdit(user_settings.mod_download_location)
        self.mod_install_location_line_edit.textChanged.connect(lambda text: self.on_anything_changed())
        self.app_settings_container.layout().addRow("Mod Install Location:", self.mod_install_location_line_edit)
        
        self.layout().addWidget(self.app_settings_container)
        
        self.game_settings_title = QLabel("<h2>Game Settings</h2>")
        self.layout().addWidget(self.game_settings_title)
        self.game_settings_container = QWidget()
        self.game_settings_container.setLayout(QFormLayout())
        
        version_texts = [version.name for version in moddb_client.versions]
        try:
            current_version_index = version_texts.index('v' + user_settings.game_version)
        except ValueError:
            current_version_index = 0
        
        self.version_combo_box = QComboBox()
        self.version_combo_box.addItems(version_texts)
        self.version_combo_box.setCurrentIndex(current_version_index)
        self.version_combo_box.currentTextChanged.connect(lambda text: self.on_anything_changed())
        self.game_settings_container.layout().addRow("Game Version:", self.version_combo_box)
        self.game_path_line_edit = QLineEdit(user_settings.game_path)
        self.game_path_line_edit.textChanged.connect(lambda text: self.on_anything_changed())
        self.game_settings_container.layout().addRow("Game Path:", self.game_path_line_edit)
        self.game_data_path_line_edit = QLineEdit(user_settings.game_data_path)
        self.game_path_line_edit.textChanged.connect(lambda text: self.on_anything_changed())
        self.game_settings_container.layout().addRow("Game Data Location:", self.game_data_path_line_edit)
        self.layout().addWidget(self.game_settings_container)
        
        self.save_settings_button = QPushButton("Save Settings")
        self.save_settings_button.setEnabled(False)
        self.save_settings_button.clicked.connect(self.on_save_settings_clicked)
        self.layout().addWidget(self.save_settings_button)
    
    @Slot()
    def on_anything_changed(self):
        self.save_settings_button.setEnabled(True)
    
    @Slot()
    def on_save_settings_clicked(self):
        game_version = self.version_combo_box.currentText().removeprefix("v")
        game_path = self.game_path_line_edit.text().strip()
        game_data_path = self.game_data_path_line_edit.text().strip()
        mod_download_location = self.mod_install_location_line_edit.text().strip()
        
        if not os.path.exists(game_path):
            QMessageBox.warning(self, "Error", f"Game path does not exist: {game_path}")
            return
        
        if not os.path.exists(game_data_path):
            QMessageBox.warning(self, "Error", f"Game data path does not exist: {game_data_path}")
            return
        
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
        
        user_settings.game_version = game_version
        user_settings.game_path = game_path
        user_settings.game_data_path = game_data_path
        user_settings.mod_download_location = mod_download_location
        user_settings.save()
        self.save_settings_button.setEnabled(False)
    