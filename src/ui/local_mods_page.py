import os
import traceback
import json

from . import moddb_client, thread_pool, user_settings
from .worker import Worker, WorkerSignals
from .mod_index import FlowLayout, ModPreview, downloader
from mod_info_parser import LocalMod, get_mod_info, scan_mod_directory
from mod_profiles import ModProfile, enable_mod, disable_mod, clear_game_disabled_mods
from settings import APP_PATH

from vsmoddb.models import Mod, Comment, ModRelease, PartialMod, SearchOrderBy, SearchOrderDirection

from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox, QLabel, QPushButton, QScrollArea, QGraphicsPixmapItem, QSizePolicy, QFrame, QProgressDialog, QMessageBox, QLayout, QListWidget, QListWidgetItem, QSplitter, QFormLayout, QDialog, QInputDialog, QFileDialog
from PySide6.QtCore import Slot, QSize, QThread, QObject, QThreadPool, QRect, QPoint, QByteArray
from PySide6.QtGui import QPixmap, QColor, QPalette, QIcon, QMouseEvent, Qt
from httpx import HTTPStatusError

class MissingMod(QFrame):
    def __init__(self, data:tuple[str, str], parent=None):
        super().__init__(parent=parent)
        
        self.main_layout =QVBoxLayout()
        self.title = QLabel("<b>Missing Mod:</b>")
        self.mod_name = QLabel(data[0])
        self.mod_version = QLabel(data[1])
        self.main_layout.addWidget(self.title)
        self.main_layout.addWidget(self.mod_name)
        self.main_layout.addWidget(self.mod_version)
        self.setLayout(self.main_layout)

class LocalModsPage(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.updating_list = False
        
        self.main_layout = QGridLayout()
        
        self.profile_selector = QComboBox()
        self.profile_selector.addItems([profile.name for profile in user_settings.profiles])
        self.selected_profile = user_settings.active_profile
        self.profile_selector.setCurrentIndex(self.profile_selector.findText(self.selected_profile.name))
        self.profile_selector.currentIndexChanged.connect(lambda index: self.on_change_profile())
        
        
        self.tool_dock = QWidget()
        self.tool_dock_layout = QVBoxLayout()
        
        self.create_profile_button = QPushButton("Create New Profile...")
        self.create_profile_button.clicked.connect(self.on_new_profile)
        self.apply_profile_button = QPushButton("Apply Profile")
        self.apply_profile_button.clicked.connect(lambda clicked: self.load_profile(self.selected_profile))
        self.rename_profile_button = QPushButton("Rename Profile")
        self.rename_profile_button.clicked.connect(self.on_profile_renamed)
        self.delete_profile_button = QPushButton("Delete Profile")
        self.delete_profile_button.clicked.connect(self.on_remove_profile)
        self.import_profile_button = QPushButton("Import Profile")
        self.import_profile_button.clicked.connect(self.import_profile)
        self.export_profile_button = QPushButton("Export Profile")
        self.export_profile_button.clicked.connect(self.export_profile)
        self.download_missing_mods_button = QPushButton("Download Missing Mods")
        self.download_missing_mods_button.clicked.connect(lambda clicked: self.download_mods_required(self.selected_profile))
        self.delete_all_button = QPushButton("Delete All installed mods")
        self.delete_all_button.clicked.connect(lambda clicked: downloader.delete_mods([mod.mod_id_str for mod in user_settings.downloaded_mods]))
        
        self.tool_dock_layout.addWidget(self.create_profile_button)
        self.tool_dock_layout.addWidget(self.import_profile_button)
        self.tool_dock_layout.addWidget(self.export_profile_button)
        self.tool_dock_layout.addSpacing(10)
        self.tool_dock_layout.addWidget(self.apply_profile_button)
        self.tool_dock_layout.addWidget(self.rename_profile_button)
        self.tool_dock_layout.addWidget(self.delete_profile_button)
        self.tool_dock_layout.addSpacing(10)
        self.tool_dock_layout.addWidget(self.download_missing_mods_button)
        self.tool_dock_layout.addWidget(self.delete_all_button)
        self.tool_dock.setLayout(self.tool_dock_layout)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area_content = QWidget()
        self.scroll_area_content_layout = FlowLayout()
        
        downloader.signals.finished.connect(self.update_mod_list)
        self.update_mod_list()
        
        self.scroll_area_content.setLayout(self.scroll_area_content_layout)
        self.scroll_area.setWidget(self.scroll_area_content)
        
        self.main_layout.addWidget(self.profile_selector, 0, 0, 1, 2)
        self.main_layout.addWidget(self.tool_dock, 1, 5, 2, 1)
        self.main_layout.addWidget(self.scroll_area, 1, 0, 3, 5)
        
        self.setLayout(self.main_layout)
    
    @Slot()
    def update_mod_list(self):
        if self.updating_list:
            return
        self.updating_list = True
        
        for child in self.scroll_area_content.children():
            if isinstance(child, ModPreview) or isinstance(child, MissingMod):
                child.deleteLater()
        
        for mod_name, mod_version in user_settings.active_profile.mods.items():
            if user_settings.get_mod_info(mod_name) is None:
                missing_mod = MissingMod((mod_name, mod_version))
                self.scroll_area_content_layout.addWidget(missing_mod)
        
        for mod in user_settings.downloaded_mods:
            preview = ModPreview(mod)
            self.scroll_area_content_layout.addWidget(preview)
        self.updating_list = False

    def get_missing_mods(self, profile:ModProfile) -> list[tuple[str, str]]:
        mods_to_download = []
        for mod_id, version in profile.mods.items():
            local_mod = user_settings.get_mod_info(mod_id)
            if local_mod is None:
                mods_to_download.append((mod_id, version))
        return mods_to_download
    
    def download_mods_required(self, profile:ModProfile, mods:list[tuple[LocalMod, str]] = None):
        if mods is None:
            mods = self.get_missing_mods(profile)
        failed_mods = []
        downloader.signals.finished.connect(lambda profile=profile: self.on_download_finished(profile=profile))
        
        for mod_id, version in mods:
            try:
                full_mod = moddb_client.get_mod(mod_id)
            except:
                print(f"Failed to download mod {mod_id}")
                failed_mods.append((mod_id, version))
                continue
            
            release = full_mod.get_release(version)
            if release is None:
                print(f"Failed to find release for mod {mod_id} version {version}")
                failed_mods.append((mod_id, version))
                continue
            
            download_path = downloader.release_download_path(release)
            download_job = downloader.prepare_mod_download(release, download_path)
            downloader.add_download_job(download_job)
        downloader.start_download()
    
    @Slot()
    def on_download_finished(self, profile:ModProfile):
        downloader.signals.finished.disconnect(lambda profile=profile: self.on_download_finished(profile))
        self.load_profile(profile)
    
    @Slot()
    def load_profile(self, profile:ModProfile):
        # Load a mod profile into the game
        mods_to_download = []
        for mod in [mod for mod in user_settings.downloaded_mods if mod.is_enabled]:
            if mod.mod_id_str not in profile.mods.keys():
                disable_mod(mod, mod.version, user_settings.game_data_path)
        
        for mod_id, version in profile.mods.items():
            local_mod = user_settings.get_mod_info(mod_id)
            if local_mod is not None:
                if not local_mod.is_enabled:
                    enable_mod(local_mod, version, user_settings.game_data_path)
            else:
                mods_to_download.append((mod_id, version))
        
        if len(mods_to_download) > 0:
            self.download_mods_required(profile, mods_to_download)
        
        user_settings.active_profile = profile
        self.selected_profile = profile
        self.update_mod_list()
    
    @Slot()
    def change_selected_profile(self, new_profile:ModProfile):
        self.selected_profile = new_profile
        user_settings.active_profile = new_profile
        self.update_mod_list()
    
    @Slot()
    def on_change_profile(self):
        selected_profile = user_settings.get_profile(self.profile_selector.currentText())
        self.change_selected_profile(selected_profile)
    
    def create_profile(self, new_profile_name: str = "Default", profile:ModPreview = None):
        new_profile_name = new_profile_name.strip()
        if not user_settings.get_profile(new_profile_name):
            if profile is None:
                new_profile = ModProfile(name=new_profile_name, game_version=user_settings.game_version)
            else:
                new_profile = profile
            user_settings.profiles.append(new_profile)
            self.profile_selector.addItem(new_profile.name)
            self.profile_selector.setCurrentIndex(self.profile_selector.count() - 1)
            user_settings.save()
            return new_profile
        else:
            QMessageBox.warning(self, "Profile Name Exists", f"A profile with the name '{new_profile_name}' already exists.")
            return None
    
    def is_default_profile(self, profile:ModProfile) -> bool:
        if profile.name == "Default":
            return True
        else:
            return False
    
    @Slot()
    def on_new_profile(self):
        new_profile_name, ok = QInputDialog.getText(self, "New Profile", "Enter profile name:")
        if new_profile_name and ok:
            new_profile = self.create_profile(new_profile_name)
            if new_profile is not None:
                self.change_selected_profile(new_profile)
            
    
    @Slot()
    def on_profile_renamed(self):
        if self.is_default_profile(self.selected_profile):
            QMessageBox.warning(self, "Cannot Rename Default Profile", "The default profile cannot be renamed.")
        
        new_profile_name, ok = QInputDialog.getText(self, "Rename Profile", "Enter profile name:")
        if new_profile_name and ok:
            if not user_settings.get_profile(new_profile_name):
                self.selected_profile.name = new_profile_name
                self.profile_selector.setItemText(self.profile_selector.currentIndex(), new_profile_name)
                user_settings.save()
            else:
                QMessageBox.warning(self, "Profile Name Exists", f"A profile with the name '{new_profile_name}' already exists.")
    
    @Slot()
    def on_remove_profile(self):
        if self.is_default_profile(self.selected_profile):
            QMessageBox.warning(self, "Cannot Remove Default Profile", "The default profile cannot be removed.")
        
        profile_name = self.selected_profile.name
        if user_settings.get_profile(profile_name):
            user_settings.profiles.remove(self.selected_profile)
            if user_settings.active_profile == profile_name:
                for mod_id, version in self.selected_profile.mods.values():
                    mod = user_settings.get_mod_info(mod_id)
                    if mod:
                        disable_mod(mod, version, user_settings.game_data_path)
                user_settings.active_profile = user_settings.get_profile("Default")
            user_settings.save()
            self.profile_selector.removeItem(self.profile_selector.currentIndex())
            self.profile_selector.setCurrentIndex(0) 
            self.change_selected_profile(user_settings.active_profile)
        else:
            QMessageBox.warning(self, "Profile Not Found", f"The profile '{profile_name}' does not exist.")
    
    @Slot()
    def import_profile(self):
        file_path = QFileDialog.getOpenFileName(self, "Import Profile", "", "JSON Files (*.json)")[0]
        if file_path == '':
            return
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                new_profile_data = ModProfile.import_from_json(data)
                new_profile = self.create_profile(new_profile_data.name, profile=new_profile_data)
                if new_profile is not None:
                    self.change_selected_profile(new_profile)
        except FileNotFoundError:
            QMessageBox.warning(self, "File Not Found", f"The file '{file_path}' does not exist.")
        except json.JSONDecodeError:
            QMessageBox.warning(self, "Invalid JSON", "The file contains invalid JSON data.")
        except:
            QMessageBox.critical(self, "Error", traceback.format_exc())
    
    @Slot()
    def export_profile(self):
        profile = self.selected_profile
        json_data = json.dumps(profile.export_to_json())
        bytes_data = QByteArray.fromStdString(json_data)
        QFileDialog.saveFileContent(bytes_data, profile.name.lower().strip().replace(' ', '_') + '.json', self)