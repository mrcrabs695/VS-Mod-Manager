import os
import traceback

from . import moddb_client, thread_pool, user_settings
from .worker import Worker, WorkerSignals
from .mod_index import FlowLayout, ModPreview, downloader
from mod_info_parser import LocalMod, get_mod_info, scan_mod_directory
from mod_profiles import ModProfile, enable_mod, disable_mod, clear_game_disabled_mods
from settings import APP_PATH

from vsmoddb.models import Mod, Comment, ModRelease, PartialMod, SearchOrderBy, SearchOrderDirection

from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox, QLabel, QPushButton, QScrollArea, QGraphicsPixmapItem, QSizePolicy, QFrame, QProgressDialog, QMessageBox, QLayout, QListWidget, QListWidgetItem, QSplitter
from PySide6.QtCore import Slot, QSize, QThread, QObject, QThreadPool, QRect, QPoint
from PySide6.QtGui import QPixmap, QColor, QPalette, QIcon, QMouseEvent, Qt
from httpx import HTTPStatusError

class LocalModsPage(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.updating_list = False
        
        self.main_layout = QGridLayout()
        
        self.profile_selector = QComboBox()
        self.profile_selector.setEditable(True)
        self.selected_profile = user_settings.active_profile
        self.change_profile_button = QPushButton("Change Profile")
        
        
        self.tool_dock = QWidget()
        self.tool_dock_layout = QVBoxLayout()
        
        self.delete_all_button = QPushButton("Delete All installed mods")
        self.delete_all_button.clicked.connect(lambda clicked: downloader.delete_mods([mod.mod_id_str for mod in user_settings.downloaded_mods]))
        
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
        
        self.main_layout.addWidget(self.tool_dock, 0, 5, 2, 1)
        self.main_layout.addWidget(self.scroll_area, 0, 0, 3, 5)
        
        self.setLayout(self.main_layout)
    
    @Slot()
    def update_mod_list(self):
        if self.updating_list:
            return
        self.updating_list = True
        
        for child in self.scroll_area_content.children():
            if isinstance(child, ModPreview):
                child.deleteLater()
        
        for mod in user_settings.downloaded_mods:
            preview = ModPreview(mod)
            self.scroll_area_content_layout.addWidget(preview)
        self.updating_list = False

    def download_mods_required(self, profile:ModProfile, mods:list[tuple[LocalMod, str]]):
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
    
    def on_download_finished(self, profile:ModProfile):
        downloader.signals.finished.disconnect(lambda profile=profile: self.on_download_finished(profile))
        self.load_profile(profile)
    
    def load_profile(self, profile:ModProfile):
        # Load a mod profile into the game
        mods_to_download = []
        for mod_id, version in profile.mods.items():
            local_mod = user_settings.get_mod_info(mod_id)
            if local_mod is not None:
                enable_mod(local_mod, version, user_settings.game_data_path)
            else:
                mods_to_download.append((mod_id, version))
        
        if len(mods_to_download) > 0:
            self.download_mods_required(profile, mods_to_download)
