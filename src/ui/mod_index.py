import os
import traceback

from . import moddb_client, thread_pool, user_settings
from .worker import Worker, WorkerSignals
from settings import APP_PATH
from mod_info_parser import LocalMod, get_mod_info
from mod_profiles import enable_mod, disable_mod
from vsmoddb.models import Mod, Comment, ModRelease, PartialMod, SearchOrderBy, SearchOrderDirection

from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox, QLabel, QPushButton, QScrollArea, QGraphicsPixmapItem, QSizePolicy, QFrame, QProgressDialog, QMessageBox, QLayout, QListWidget, QListWidgetItem, QSplitter
from PySide6.QtCore import Slot, QSize, QThread, QObject, QThreadPool, QRect, QPoint, Signal
from PySide6.QtGui import QPixmap, QColor, QPalette, QIcon, QMouseEvent, Qt
from httpx import HTTPStatusError

# TODO: once the groundwork is done, all the temp style sheets will need to be removed and replaced with a proper app level stylesheet


class DownloaderSignals(QObject):
    finished = Signal()
    progress = Signal(int)
    mod_deleted = Signal(object)

class ModDownloader(QObject):
    #? This could be refactored to handle more then just downloading once the actual mod index widget is created
    def __init__(self, to_disabled_buttons:list[QPushButton] = None, mod_release:ModRelease|list[ModRelease] = None, max_workers:int = 5, parent:QWidget|None = None):
        super().__init__(parent=parent)
        self.to_disabled_buttons = to_disabled_buttons if to_disabled_buttons else []
        self.mod_release = mod_release
        
        self.pending_jobs:list[ModDownloader.DownloadJob] = []
        self.running_jobs:list[ModDownloader.DownloadJob] = []
        self.finished_jobs:list[ModDownloader.DownloadJob] = []
        self.progress_dialog = None
        
        self.max_concurrent_jobs = max_workers
        self.signals = DownloaderSignals()
        
        if isinstance(mod_release, list):
            for release in mod_release:
                self.add_download_job(self.prepare_mod_download(release, self.release_download_path(release)))
            self.start_download()
        elif isinstance(mod_release, ModRelease):
            self.download_mod_single(mod_release)
        # self.progress_dialog.show()
    
    class DownloadJob:
        def __init__(self, worker:Worker, signals:WorkerSignals, file_name:str, release:ModRelease) -> None:
            self.started = False
            self.worker = worker
            self.signals = signals
            self.finished = False
            self.progress = 0
            self.progress_end = 0
            self.progress_start = 0
            self.failed = False
            self.result = None
            self.failed_result = None
            self.file_name = file_name
            self.mod_release = release
        
        def set_result(self, result) -> None:
            self.result = result
        
        def set_error_result(self, result) -> None:
            self.failed = True
            self.failed_result = result
        
        def set_progress(self, progress:int) -> None:
            self.progress = progress
        
        def set_progress_start(self, progress:int) -> None:
            self.progress_start = progress
        
        def set_progress_end(self, progress:int) -> None:
            self.progress_end = progress
    
    @property
    def total_job_count(self) -> int:
        return len(self.pending_jobs) + len(self.finished_jobs) + len(self.running_jobs)
    
    @property
    def pending_job_count(self) -> int:
        return len(self.pending_jobs)
    
    @property
    def running_job_count(self) -> int:
        return len(self.running_jobs)
    
    @property
    def finished_job_count(self) -> int:
        return len(self.finished_jobs)
    
    @property
    def failed_job_count(self) -> int:
        return len([job for job in self.finished_jobs if job.failed])
    
    @property
    def gather_failed_jobs(self):
        return [job for job in self.finished_jobs if job.failed]
    
    @property
    def disable_buttons(self):
        return self.to_disabled_buttons
    
    @disable_buttons.setter
    def disable_buttons(self, value:list[QPushButton]):
        self.to_disabled_buttons = value
    
    def release_download_path(self, mod_release:ModRelease, base_path:str = None):
        return os.path.join(user_settings.mod_download_location if base_path is None else base_path, f"{mod_release.filename}")
    
    
    def prepare_mod_download(self, release:ModRelease, download_path:str, on_result_callback = None):
        download_worker_signals = WorkerSignals()
        download_worker = Worker(
            moddb_client.fetch_to_file,
            release.main_file,
            download_path,
            download_worker_signals.progress_start.emit,
            download_worker_signals.progress.emit,
            signals = download_worker_signals
        )
        if on_result_callback is not None:
            download_worker_signals.result.connect(on_result_callback)
        return ModDownloader.DownloadJob(download_worker, download_worker_signals, download_path, release)
    
    
    def add_download_job(self, job):
        self.pending_jobs.append(job)
        
        job.signals.finished.connect(lambda: self.download_finished(job))
        job.signals.result.connect(lambda result: job.set_result(result))
        job.signals.error.connect(lambda error: job.set_error(error))
        job.signals.progress.connect(lambda progress: job.set_progress(progress))
        job.signals.progress_end.connect(lambda progress: job.set_progress_end(progress))
        job.signals.progress_start.connect(lambda progress: job.set_progress_start(progress))
    
    def start_download(self):
        if self.disable_buttons:
            for button in self.disable_buttons:
                button.setEnabled(False)
        
        if not self.progress_dialog:
            self.progress_dialog = QProgressDialog("Downloading...", "Cancel", 0, 0)
        
        self.progress_dialog.setMaximum(self.total_job_count)
        
        for job in self.pending_jobs:
            if self.running_job_count < self.max_concurrent_jobs:
                job.started = True
                self.pending_jobs.remove(job)
                self.running_jobs.append(job)
                thread_pool.start(job.worker)
        
    
    @Slot()
    def download_mod_single(self, release:ModRelease, on_result_callback = None):
        path = self.release_download_path(release)
        job = self.prepare_mod_download(release, path, on_result_callback)
        self.add_download_job(job)
        self.start_download()
        
    @Slot()
    def download_finished(self, finished_job):
        finished_job.finished = True
        self.running_jobs.remove(finished_job)
        self.finished_jobs.append(finished_job)
        
        self.progress_dialog.setValue(self.finished_job_count)
        self.signals.progress.emit(self.finished_job_count)
        if not finished_job.failed:
            try:
                local_mod = get_mod_info(finished_job.file_name)
            except:
                traceback.print_exc()
            if local_mod:
                if local_mod.full_mod_info is None:
                    local_mod.fetch_full_mod_info(moddb_client)
                
                if local_mod not in user_settings.downloaded_mods:
                    user_settings.downloaded_mods.append(local_mod)
            else:
                print(f"Error adding mod to downloaded mods. Mod file path: {finished_job.file_name}")
        
        if self.pending_job_count > 0 and self.running_job_count < self.max_concurrent_jobs:
            self.start_download()
        
        if self.finished_job_count == self.total_job_count:
            self.progress_dialog.close()
            if self.failed_job_count > 0 and self.total_job_count > 10:
                QMessageBox.warning(self.parent(), "Download Complete", f" {self.finished_job_count} mods downloaded and {self.failed_job_count} mods failed to download\n Failed to download: {[job.filename + "\n" for job in self.gather_failed_jobs]}", QMessageBox.StandardButton.Ok)
            elif self.total_job_count > 10:
                QMessageBox.information(self.parent(), "Download Complete", f"{self.finished_job_count} mods downloaded", QMessageBox.StandardButton.Ok)
            
            if self.disable_buttons:
                for button in self.disable_buttons:
                    if not button.isEnabled():
                        button.setEnabled(True)
            
            self.finished_jobs.clear()
            user_settings.save()
            self.signals.finished.emit()
    
    def delete_mods(self, mod_list:list[int|str]):
        for mod in mod_list:
            local_mod = user_settings.get_mod_info(mod)
            if local_mod is not None:
                path = local_mod.current_path
                try:
                    os.remove(path)
                except:
                    pass
                user_settings.downloaded_mods.remove(local_mod)
                self.signals.mod_deleted.emit(mod)
        user_settings.save()


downloader = ModDownloader()

class ModPreview(QFrame):
    def __init__(self, mod:PartialMod | LocalMod, mod_detail: QWidget = None):
        super().__init__()
        self.mod = mod
        
        if isinstance(mod, PartialMod):
            self.full_mod_info = moddb_client.cache_manager.get(f'mod/{self.mod.mod_id}_')
            self.mod_detail_view = mod_detail
            self.mod_icon = self.mod.logo
            self.mod_id = self.mod.mod_id
        else:
            self.mod_detail_view = None
            self.mod_icon = mod.icon
            self.mod_id = self.mod.mod_id_str
            
            self.full_mod_info = self.mod.full_mod_info
            if self.full_mod_info is None:
                signals = WorkerSignals()
                self.fetch_full_mod_info(signals)
        
        self.main_layout = QVBoxLayout()
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        
        self.logo_image = QPixmap()
        self.logo_label = QLabel()
        
        if self.mod_icon != None and self.mod_icon != 'None' and isinstance(self.mod_icon, str):
            self.fetch_logo_worker = Worker(moddb_client.fetch_to_memory, self.mod_icon)
            self.fetch_logo_worker.signals.result.connect(self.load_logo)
            self.fetch_logo_worker.signals.error.connect(lambda error: self.load_placeholder_logo())
            thread_pool.start(self.fetch_logo_worker)
        elif isinstance(self.mod_icon, bytes):
            self.logo_image.loadFromData(self.mod_icon)
            self.logo_label.setPixmap(self.logo_image.scaledToWidth(200))
        else:
            self.logo_image.load('data/test.png')
            self.logo_label.setPixmap(self.logo_image.scaledToWidth(200))
        
        self.title_label = QLabel(mod.name)
        
        if isinstance(self.mod, PartialMod):
            summary = mod.summary
            info = f"Downloads: <b>{mod.downloads}</b>"
        else:
            summary = mod.description
            info = f"Installed Version: <b>{mod.version}</b>"
        
        self.summary_label = QLabel(summary)
        self.summary_label.setWordWrap(True)
        self.info_label = QLabel(info)
        
        self.download_icon = QIcon(os.path.join(APP_PATH, 'data/icons/download.svg'))
        self.download_icon.addFile(os.path.join(APP_PATH, 'data/icons/download-off.svg'), mode=QIcon.Mode.Disabled)
        self.delete_icon = QIcon(os.path.join(APP_PATH, 'data/icons/trash-x.svg'))
        
        if isinstance(mod, PartialMod):
            if user_settings.get_mod_info(self.mod_id) is not None:
                self.main_action_button = QPushButton("Uninstall")
                self.main_action_button.setIcon(self.delete_icon)
                self.main_action_button.clicked.connect(self.delete_mod)
            else:
                self.main_action_button = QPushButton("Install")
                self.main_action_button.setIcon(self.download_icon)
                self.main_action_button.clicked.connect(self.download_mod)
            self.secondary_action_button = None
            self.add_to_profile_button = None
        else:
            self.main_action_button = QPushButton("Uninstall")
            self.main_action_button.setIcon(self.delete_icon)
            self.main_action_button.clicked.connect(self.delete_mod)
            
            if self.mod.is_enabled:
                self.secondary_action_button = QPushButton("Disable")
                self.secondary_action_button.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/triangle-minus.svg')))
                self.secondary_action_button.clicked.connect(self.disable_mod)
            else:
                self.secondary_action_button = QPushButton("Enable")
                self.secondary_action_button.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/triangle-plus.svg')))
                self.secondary_action_button.clicked.connect(self.enable_mod)
            
            if self.mod.mod_id_str in user_settings.active_profile.mods.keys():
                self.add_to_profile_button = QPushButton("Remove from Profile")
                self.add_to_profile_button.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/triangle-minus.svg')))
                self.add_to_profile_button.clicked.connect(self.remove_from_profile)
            else:
                self.add_to_profile_button = QPushButton("Add to Profile")
                self.add_to_profile_button.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/triangle-plus.svg')))
                self.add_to_profile_button.clicked.connect(self.add_to_profile)
        
        downloader.signals.mod_deleted.connect(self.on_delete_finished)
        
        self.main_layout.addWidget(self.logo_label, 2)
        self.main_layout.addWidget(self.title_label, 1)
        self.main_layout.addWidget(self.summary_label, 3)
        self.main_layout.addWidget(self.info_label, 1)
        self.main_layout.addWidget(self.main_action_button, 1)
        if self.secondary_action_button:
            self.main_layout.addWidget(self.secondary_action_button, 1)
        if self.add_to_profile_button:
            self.main_layout.addWidget(self.add_to_profile_button, 1)
        self.setLayout(self.main_layout)
    
    
    @Slot()
    def load_logo(self, image_data:bytes):
        try:
            result = self.logo_image.loadFromData(image_data)
            if not result:
                return
            
            self.logo_label.setPixmap(self.logo_image.scaledToWidth(280))
        except:
            traceback.print_exc()
        finally:
            self.fetch_logo_worker = None
    
    @Slot()
    def load_placeholder_logo(self):
        self.logo_image.load(os.path.join(APP_PATH, "data/test.png"))
        self.logo_label.setPixmap(self.logo_image.scaledToWidth(200))
    
    @Slot()
    def download_mod(self):
        self.main_action_button.setEnabled(False)
        if self.full_mod_info is None:
            signals = WorkerSignals()
            signals.result.connect(lambda mod: self.on_full_mod_info(mod, downloader.download_mod_single, mod.releases[0], on_result_callback=self.on_download_finished))
            self.fetch_full_mod_info(signals)
        else:
            downloader.download_mod_single(self.full_mod_info.releases[0], on_result_callback=self.on_download_finished)
    
    @Slot()
    def fetch_full_mod_info(self, signals:WorkerSignals):
        self.mod_info_worker = Worker(moddb_client.get_mod, self.mod_id, signals=signals)
        thread_pool.start(self.mod_info_worker)
    
    @Slot()
    def on_full_mod_info(self, mod:Mod, continue_callback, *args, **kwargs):
        self.full_mod_info = mod
        continue_callback(*args, **kwargs)
    
    @Slot()
    def on_download_finished(self, _result):
        self.main_action_button.setEnabled(True)
        self.main_action_button.setText("Uninstall")
        self.main_action_button.setIcon(self.delete_icon)
        self.main_action_button.clicked.disconnect(self.download_mod)
        self.main_action_button.clicked.connect(self.delete_mod)
    
    @Slot()
    def delete_mod(self):
        downloader.delete_mods([self.mod_id])
    
    @Slot()
    def on_delete_finished(self, mod_id:str | int):
        if mod_id != self.mod_id:
            return
        
        if isinstance(self.mod, PartialMod):
            self.main_action_button.setText("Install")
            self.main_action_button.setIcon(self.download_icon)
            self.main_action_button.clicked.connect(self.download_mod)
            self.main_action_button.clicked.disconnect(self.delete_mod)
        else:
            self.deleteLater()
    
    @Slot()
    def enable_mod(self):
        enable_mod(self.mod, self.mod.version, user_settings.game_data_path)
        self.secondary_action_button.setText("Disable")
        self.secondary_action_button.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/triangle-minus.svg')))
        self.secondary_action_button.clicked.connect(self.disable_mod)
        self.secondary_action_button.clicked.disconnect(self.enable_mod)
    
    @Slot()
    def disable_mod(self):
        disable_mod(self.mod, self.mod.version, user_settings.game_data_path)
        self.secondary_action_button.setText("Enable")
        self.secondary_action_button.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/triangle-plus.svg')))
        self.secondary_action_button.clicked.connect(self.enable_mod)
        self.secondary_action_button.clicked.disconnect(self.disable_mod)
    
    @Slot()
    def add_to_profile(self):
        user_settings.active_profile.add_mod(self.mod_id, self.mod.version)
        self.add_to_profile_button.setText("Remove from Profile")
        self.add_to_profile_button.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/triangle-minus.svg')))
        self.add_to_profile_button.clicked.connect(self.remove_from_profile)
        self.add_to_profile_button.clicked.disconnect(self.add_to_profile)
    
    @Slot()
    def remove_from_profile(self):
        user_settings.active_profile.remove_mod(self.mod_id)
        self.add_to_profile_button.setText("Add to Profile")
        self.add_to_profile_button.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/triangle-plus.svg')))
        self.add_to_profile_button.clicked.disconnect(self.remove_from_profile)
        self.add_to_profile_button.clicked.connect(self.add_to_profile)
    
    def mousePressEvent(self, event:QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and event.modifiers() == Qt.KeyboardModifier.NoModifier and isinstance(self.mod, PartialMod):
            event.accept()
            if self.mod_detail_view != None:
                if self.full_mod_info is None:
                    signals = WorkerSignals()
                    signals.result.connect(lambda mod: self.on_full_mod_info(mod, self.mod_detail_view.update_mod, mod, show_after=True))
                    self.fetch_full_mod_info(signals)
                else:
                    self.mod_detail_view.update_mod(self.full_mod_info, show_after=True)

class FlowLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        if parent is not None:
            self.setContentsMargins(0, 0, 0, 0)
        
        self._item_list = []
    
    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)
    
    def addItem(self, item):
        self._item_list.append(item)
    
    def count(self):
        return len(self._item_list)
    
    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        
        return None
    
    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        
        return None
    
    def expandingDirections(self):
        return Qt.Orientation(0)
    
    def hasHeightForWidth(self):
        return True
    
    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height
    
    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self._do_layout(rect, False)
    
    def sizeHint(self):
        return self.minimumSize()
    
    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size
    
    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        
        for item in self._item_list:
            style = item.widget().style()
            layout_spacing_x = style.layoutSpacing(
                QSizePolicy.ControlType.PushButton,
                QSizePolicy.ControlType.PushButton,
                Qt.Orientation.Horizontal
            )
            layout_spacing_y = style.layoutSpacing(
                QSizePolicy.ControlType.PushButton,
                QSizePolicy.ControlType.PushButton,
                Qt.Orientation.Vertical
            )
            space_x = spacing + layout_spacing_x
            space_y = spacing + layout_spacing_y
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        
        return y + line_height - rect.y()


class ModIndex(QSplitter):
    def __init__(self, parent:QWidget|None = None):
        super().__init__(parent=parent)
        
        self.main_layout = QGridLayout()
        self.setOpaqueResize(False)
        self.search_buttons_enabled = True
        self.mods = []
        self.mods_shown = 0
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        
        self.text_search_box = QLineEdit(placeholderText="Search mods by name or description")
        self.text_search_box.returnPressed.connect(self.search_mods)
        self.search_sort = QComboBox()
        self.search_options = [SearchOrderBy.TRENDING, SearchOrderBy.DOWNLOADS, SearchOrderBy.COMMENTS, SearchOrderBy.FOLLOWS, SearchOrderBy.CREATED, SearchOrderBy.LAST_RELEASED]
        self.search_sort.addItems(["Trending", "Downloads", "Comments", "Follows", "Created", "Last Released"])
        self.search_sort.setCurrentIndex(0)
        self.search_order = QComboBox()
        self.search_order.addItems(["asc", "desc"])
        self.search_order.setCurrentIndex(1)
        self.search_button = QPushButton("Search")
        self.search_button.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/input-search.svg')))
        self.search_button.clicked.connect(lambda: self.search_mods())
        
        self.extra_search_container = QFrame()
        extra_search_layout = QHBoxLayout()
        
        # TODO: extra search widgets
        
        self.extra_search_container.setLayout(extra_search_layout)
        
        self.result_number = QLabel()
        self.result_number.hide()
        
        self.mods_list = QFrame()
        self.mods_list_layout = FlowLayout()
        self.mods_list.setLayout(self.mods_list_layout)
        self.mods_list.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.load_more_mods_button = QPushButton("Load More Mods...")
        self.load_more_mods_button.clicked.connect(lambda clicked: self.update_mods_list())
        
        self.main_layout.addWidget(self.text_search_box, 0, 0, 1, 3)
        self.main_layout.addWidget(self.search_sort, 0, 3, 1, 1)
        self.main_layout.addWidget(self.search_order, 0, 4, 1, 1)
        self.main_layout.addWidget(self.search_button, 0, 5, 1, 1)
        self.main_layout.addWidget(self.extra_search_container, 1, 0, 1, 6)
        self.main_layout.addWidget(self.result_number, 2, 0, 1, 1)
        self.main_layout.addWidget(self.mods_list, 3, 0, 6, 6)
        
        self.mod_detail_view = ModDetail()
        self.mod_detail_view.hide()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.main_layout_cont = QFrame()
        self.main_layout_cont.setLayout(self.main_layout)
        self.scroll_area.setWidget(self.main_layout_cont)
        self.addWidget(self.scroll_area)
        self.addWidget(self.mod_detail_view)
        
        self.search_mods(initial=True)
    
    @Slot()
    def search_mods(self, initial:bool = False):
        if self.search_buttons_enabled and not initial:
            self.search_button.setEnabled(False)
            self.search_order.setEnabled(False)
            self.search_sort.setEnabled(False)
            self.search_buttons_enabled = False
        
        search_order:SearchOrderBy = self.search_options[self.search_sort.currentIndex()]
        order_direction:SearchOrderDirection = SearchOrderDirection[self.search_order.currentText().upper()]
        search_query:str = self.text_search_box.text()
        
        current_version_tag = moddb_client.tag_from_name('v' + user_settings.game_version)
        matching_versions = [tag.id for tag in moddb_client.versions if tag.minor_version == current_version_tag.minor_version and tag.major_version == current_version_tag.major_version]
        
        self.search_worker = Worker(moddb_client.get_mods, text=search_query, orderby=search_order, order_direction=order_direction, versions=matching_versions)
        self.search_worker.signals.result.connect(self.update_mods_list)
        self.search_worker.signals.error.connect(lambda error: QMessageBox.critical(self, "Error", error[2]))
        thread_pool.start(self.search_worker)
    
    @Slot()
    def update_mods_list(self, mods:list[Mod] = None):
        if not self.search_buttons_enabled:
            self.search_button.setEnabled(True)
            self.search_order.setEnabled(True)
            self.search_sort.setEnabled(True)
            self.search_buttons_enabled = True
        
        if mods is not None or len(self.mods) < 1:
            for widget in self.mods_list.children():
                if isinstance(widget, ModPreview):
                    # try:
                    #     # downloader.disable_buttons.remove(widget.quick_download_button)
                    # except:
                    #     pass
                    widget.deleteLater()
                elif isinstance(widget, QPushButton):
                    self.mods_list_layout.removeWidget(widget)
            self.mods_shown = 0
            self.mods = mods
        
        previous_shown = self.mods_shown
        self.mods_shown += 100
        mods_to_add = self.mods[previous_shown:self.mods_shown]
        
        for mod in mods_to_add:
            widget = ModPreview(mod, self.mod_detail_view)
            # downloader.disable_buttons.append(widget.quick_download_button)
            self.mods_list_layout.addWidget(widget)
        
        if mods is not None:
            self.result_number.setText(f"{len(self.mods)} results found.")
            self.result_number.show()
        if self.mods_shown <= len(self.mods):
            self.mods_list_layout.addWidget(self.load_more_mods_button)
        
        self.scroll_area.updateGeometry()


class CommentView(QFrame):
    def __init__(self, comment:Comment):
        super().__init__()
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        
        layout = QVBoxLayout()
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        
        self.title_label = QLabel(f"{comment.user.name}, {comment.last_modified.strftime("%d/%m/%Y | %H:%M:%S")}")
        self.comment_body = QLabel(comment.text)
        self.comment_body.setWordWrap(True)
        self.comment_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.title_label)
        layout.addWidget(self.comment_body)
        
        self.setLayout(layout)


class ModReleaseView(QFrame):
    def __init__(self, release:ModRelease, parent:QWidget|None = None):
        super().__init__(parent=parent)
        self.release = release
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        layout = QGridLayout()
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        
        self.release_title_label = QLabel(f"<h1>{release.mod_version}</h1>")
        self.download_counter = QLabel(f"<h3>Downloads: {release.downloads}</h3>")
        self.release_date_label = QLabel(f"<h3>Created: {release.created.strftime('%d/%m/%Y, %H:%M:%S')}</h3>")
        self.changelog = QLabel(f"<h3>Changelog:</h3> {release.changelog}")
        self.changelog.setWordWrap(True)
        download_icon = QIcon(os.path.join(APP_PATH, 'data/icons/download.svg'))
        download_icon.addFile(os.path.join(APP_PATH, 'data/icons/download-off.svg'), mode=QIcon.Mode.Disabled)
        self.download_button = QPushButton("Download")
        self.download_button.setIcon(download_icon)
        
        layout.addWidget(self.release_title_label, 0, 0, 1, 3)
        layout.addWidget(self.download_counter, 1, 0, 1, 1)
        layout.addWidget(self.release_date_label, 2, 0, 1, 1)
        layout.addWidget(self.download_button, 3, 0, 1, 2)
        layout.addWidget(self.changelog, 4, 0, 3, 3)
        
        self.setLayout(layout)

class ModDetail(QScrollArea):
    def __init__(self, mod:Mod = None, parent:QWidget|None = None):
        super().__init__(parent=parent)
        self.setWidgetResizable(True)
        downloader.setParent(self)
        
        self.root_container = QWidget()
        self.root_container.setLayout(QGridLayout())
        
        self.title_card_container = QFrame()
        self.title_card_container.setLayout(QVBoxLayout())
        self.title_card_container.setMinimumSize(560, 400)
        
        self.title_label = QLabel()
        self.primary_image = QPixmap()
        self.primary_image_widget = QLabel()
        self.title_card_container.layout().addWidget(self.title_label)
        self.title_card_container.layout().addWidget(self.primary_image_widget)
        
        self.description_switch = QPushButton()
        self.description_switch.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/text-caption.svg')))
        self.description_switch.setText("Description")
        self.description_switch.pressed.connect(self.show_description)
        self.releases_switch = QPushButton()
        self.releases_switch.setText("Releases")
        self.releases_switch.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/files.svg')))
        self.releases_switch.pressed.connect(self.show_releases)
        self.comments_switch = QPushButton()
        self.comments_switch.setText("Comments")
        self.comments_switch.setIcon(QIcon(os.path.join(APP_PATH, 'data/icons/messages.svg')))
        self.comments_switch.pressed.connect(self.show_comments)
        
        self.description_container = QFrame()
        self.description_container.setLayout(QGridLayout())
        self.releases_container = QFrame()
        self.releases_container.setLayout(QVBoxLayout())
        self.releases_container.hide()
        self.comments_container = QFrame()
        self.comments_container.setLayout(QVBoxLayout())
        self.comments_container.hide()
        
        self.tags_container = QFrame()
        self.tags_container.setLayout(QHBoxLayout())
        
        self.author = QLabel()
        self.mod_side = QLabel()
        self.latest_mod_version = QLabel()
        self.supported_for_version = QLabel()
        self.time_created = QLabel()
        self.last_modified = QLabel()
        self.downloads_counter = QLabel()
        self.follow_counter = QLabel()
        self.download_button = QPushButton()
        self.download_icon = QIcon(os.path.join(APP_PATH, 'data/icons/download.svg'))
        self.download_icon.addFile(os.path.join(APP_PATH, 'data/icons/download-off.svg'), mode=QIcon.Mode.Disabled)
        self.download_button.setIcon(self.download_icon)
        self.download_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.mod_description = QLabel()
        self.mod_description.setWordWrap(True)
        
        self.description_container.layout().addWidget(self.tags_container, 0, 0)
        self.description_container.layout().addWidget(self.author, 1, 0)
        self.description_container.layout().addWidget(self.mod_side, 2, 0)
        self.description_container.layout().addWidget(self.latest_mod_version, 3, 0)
        self.description_container.layout().addWidget(self.supported_for_version, 4, 0)
        self.description_container.layout().addWidget(self.time_created, 5, 0)
        self.description_container.layout().addWidget(self.last_modified, 6, 0)
        self.description_container.layout().addWidget(self.downloads_counter, 7, 0)
        self.description_container.layout().addWidget(self.follow_counter, 8, 0)
        self.description_container.layout().addWidget(self.download_button, 9, 0, 1, 2)
        self.description_container.layout().addWidget(self.mod_description, 10, 0)
        
        self.root_container.layout().addWidget(self.title_card_container, 0, 0, 1, 3)
        self.root_container.layout().addWidget(self.description_switch, 1, 0, 1, 1)
        self.root_container.layout().addWidget(self.releases_switch, 1, 1, 1, 1)
        self.root_container.layout().addWidget(self.comments_switch, 1, 2, 1, 1)
        self.root_container.layout().addWidget(self.description_container, 2, 0, 1, 3)
        self.root_container.layout().addWidget(self.releases_container, 3, 0, 1, 3)
        self.root_container.layout().addWidget(self.comments_container, 4, 0, 1, 3)
        
        if mod is not None:
            self.update_mod(mod)
        self.setWidget(self.root_container)
    
    def sizeHint(self):
        return self.root_container.minimumSize()
    
    @Slot()
    def show_description(self):
        self.releases_container.hide()
        self.description_container.show()
        
        if not self.comments_container.isHidden():
            self.load_comments(clear = True)
        self.comments_container.hide()
    
    @Slot()
    def show_releases(self):
        self.description_container.hide()
        self.releases_container.show()
        
        if not self.comments_container.isHidden():
            self.load_comments(clear = True)
        self.comments_container.hide()
    
    @Slot()
    def show_comments(self):
        self.releases_container.hide()
        self.description_container.hide()
        self.comments_container.show()
        
        if not self.comments:
            self.fetch_comments_worker = Worker(moddb_client.get_comments, self.mod.asset_id)
            self.fetch_comments_worker.signals.result.connect(self.load_comments)
            self.fetch_comments_worker.signals.error.connect(self.thread_exception)
            thread_pool.start(self.fetch_comments_worker)
    
    @Slot()
    def update_mod(self, mod:Mod, show_after=False):
        to_disable_buttons = []
        
        self.mod = mod
        self.comments = None
        self.supported_releases = mod.get_releases_for_version(moddb_client.tag_from_name("v" + user_settings.game_version))
        
        self.title_label.setText(f"<h1>{self.mod.name}</h1>")
        self.title_label.setObjectName("mod_view_title_label")
        
        self.primary_image.load(os.path.join(APP_PATH, "data/test.png"))
        self.primary_image_widget.setPixmap(self.primary_image.scaledToWidth(560))
        self.primary_image_widget.setMaximumSize(560, 350)
        self.primary_image_widget.setObjectName("mod_view_primary_image")
        
        self.fetch_image_worker = Worker(moddb_client.fetch_to_memory, self.mod.logo_file)
        self.fetch_image_worker.signals.result.connect(self.load_primary_image)
        thread_pool.start(self.fetch_image_worker)
        
        self.download_button = QPushButton()
        self.download_button.setIcon(self.download_icon)
        self.download_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.download_button.setText("Install latest version...")
        self.download_button.clicked.connect(lambda checked: downloader.download_mod_single(self.supported_releases[0]['release']))
        
        for child in self.tags_container.children():
            if isinstance(child, QLabel) or isinstance(child, HyperTag):
                child.deleteLater()
        tags_prefix = QLabel()
        tags_prefix.setText("<h2>Tags: </h2>")
        self.tags_container.layout().addWidget(tags_prefix)
        for tag in mod.tags:
            tag_widget = HyperTag(tag.name, tag_color=tag.color)
            self.tags_container.layout().addWidget(tag_widget)
        
        self.author.setText(f"<h2>Author: {mod.author.name}</h2>")
        self.author.setObjectName("mod_view_author")
        
        self.mod_side.setText("<h2>Side: Unknown</h2>")
        self.mod_side.setObjectName("mod_view_side")
        
        self.latest_mod_version.setText(f"<h2>Latest mod version: {mod.releases[0].mod_version}</h2>")
        self.latest_mod_version.setObjectName("mod_view_latest_mod_version")
        
        self.supported_for_version.setText(f"<h2>Supports installed game version: {len(self.supported_releases) > 0}</h2>")
        self.supported_for_version.setObjectName("mod_view_supported_for_version")
        
        self.time_created.setText(f"<h2>Created: {mod.created.strftime("%d/%m/%Y")}</h2>")
        self.time_created.setObjectName("mod_view_time_created")
        
        self.last_modified.setText(f"<h2>Last modified: {mod.last_modified.strftime("%d/%m/%Y")}</h2>")
        self.last_modified.setObjectName("mod_view_last_modified")
        
        self.downloads_counter.setText(f"<h2>Downloads: {str(mod.downloads)}</h2>")
        self.downloads_counter.setObjectName("mod_view_downloads_counter")
        
        self.follow_counter.setText(f"<h2>Follows: {str(mod.follows)}</h2>")
        self.follow_counter.setObjectName("mod_view_follow_counter")
        
        self.mod_description.setText(mod.description)
        self.mod_description.setObjectName("mod_view_description")
        
        for child in self.releases_container.children():
            if isinstance(child, ModReleaseView):
                child.deleteLater()
        
        for i, release in enumerate(self.supported_releases):
            release_widget = ModReleaseView(release['release'])
            release_widget.download_button.clicked.connect(lambda clicked, release=release['release']: downloader.download_mod_single(release))
            to_disable_buttons.append(release_widget.download_button)
            self.releases_container.layout().addWidget(release_widget)
        
        downloader.disable_buttons = to_disable_buttons
        if show_after:
            self.show()
    
    @Slot()
    def load_primary_image(self, image_data:bytes):
        try:
            result = self.primary_image.loadFromData(image_data)
            if not result:
                return
            
            self.primary_image_widget.setPixmap(self.primary_image.scaledToWidth(560))
        except:
            traceback.print_exc()
        finally:
            self.fetch_image_worker = None
    
    @Slot()
    def load_comments(self, comments:list[str] = None, clear:bool = None):
        if self.comments is None or comments is None or clear is True:
            # clear previous comments if there was any
            for child in self.comments_container.children():
                if not issubclass(type(child), QLayout):
                    child.deleteLater()
            
            self.comments = comments
            self.displayed_comments = 0
            self.load_more_comments = QPushButton("Load more comments...")
            self.load_more_comments.clicked.connect(self.load_comments)
            
            previous_displayed = self.displayed_comments
            self.displayed_comments += 100
            try:
                comments_to_add = comments[previous_displayed:self.displayed_comments]
            except:
                comments_to_add = []
        
        else:
            previous_displayed = self.displayed_comments
            self.displayed_comments += 100
            comments_to_add = self.comments[previous_displayed:self.displayed_comments]
            self.comments_container.layout().removeWidget(self.load_more_comments)
        
        for comment in comments_to_add:
            self.comments_container.layout().addWidget(CommentView(comment))
        
        self.comments_container.layout().addWidget(self.load_more_comments)
        self.updateGeometry()
    
    @Slot()
    def thread_exception(self, exc_tuple:tuple):
        if not self.download_button.isEnabled():
            self.download_button.setEnabled(True)
        if isinstance(exc_tuple[1], HTTPStatusError):
            return
        dialog = QMessageBox.warning(self, "Error", f"An error occurred while loading the image: {exc_tuple[2]}")
        dialog.show()

class HyperTag(QLabel):
    def __init__(self, text:str, bg_color:str = "#333333", tag_color:str = "aqua", text_color:str = "white", parent:QWidget|None = None):
        super().__init__(parent=parent)
        self.setStyleSheet(f"background-color: {bg_color}; border-radius: 4px")
        self.setText(f"""<p style="color: {text_color}"><b style="color: {tag_color}">#</b>  {text}</p>""")
        self.setFixedHeight(20)
        size_policy = QSizePolicy()
        size_policy.setHorizontalPolicy(QSizePolicy.Policy.Minimum)
        self.setSizePolicy(size_policy)