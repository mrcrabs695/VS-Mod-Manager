import os
import traceback

from . import moddb_client, thread_pool, user_settings
from .worker import Worker, WorkerSignals
from settings import APP_PATH
from vsmoddb.models import Mod, Comment, ModRelease, PartialMod, SearchOrderBy, SearchOrderDirection

from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox, QLabel, QPushButton, QScrollArea, QGraphicsPixmapItem, QSizePolicy, QFrame, QProgressDialog, QMessageBox, QLayout, QListWidget, QListWidgetItem, QSplitter
from PySide6.QtCore import Slot, QSize, QThread, QObject, QThreadPool, QRect, QPoint
from PySide6.QtGui import QPixmap, QColor, QPalette, QIcon, QMouseEvent, Qt
from httpx import HTTPStatusError

# TODO: once the groundwork is done, all the temp style sheets will need to be removed and replaced with a proper app level stylesheet


class ModDownloader(QObject):
    #? This could be refactored to handle more then just downloading once the actual mod index widget is created
    def __init__(self, to_disabled_buttons:list[QPushButton] = None, mod_release:ModRelease|list[ModRelease] = None, parent:QWidget|None = None):
        super().__init__(parent=parent)
        self.to_disabled_buttons = to_disabled_buttons if to_disabled_buttons else []
        self.mod_release = mod_release
        self.download_jobs:list[ModDownloader.DownloadJob] = []
        self.progress_dialog = None
        
        if isinstance(mod_release, list):
            for release in mod_release:
                self.add_download_job(self.prepare_mod_download(release, self.release_download_path(release)))
            self.start_download()
        elif isinstance(mod_release, ModRelease):
            self.download_mod_single(mod_release)
        # self.progress_dialog.show()
    
    class DownloadJob:
        def __init__(self, worker:Worker, signals:WorkerSignals, file_name:str) -> None:
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
    def total_jobs(self) -> int:
        return len(self.download_jobs)
    
    @property
    def finished_jobs(self) -> int:
        return len([job for job in self.download_jobs if job.finished])
    
    @property
    def failed_jobs(self) -> int:
        return len([job for job in self.download_jobs if job.failed])
    
    @property
    def gather_failed_jobs(self):
        return [job for job in self.download_jobs if job.failed]
    
    @property
    def disable_buttons(self):
        return self.to_disabled_buttons
    
    @disable_buttons.setter
    def disable_buttons(self, value:list[QPushButton]):
        self.to_disabled_buttons = value
    
    def release_download_path(self, mod_release:ModRelease, base_path:str = None):
        return os.path.join(user_settings.mod_download_location if base_path is None else base_path, f"{mod_release.filename}")
    
    
    def prepare_mod_download(self, release:ModRelease, download_path:str):
        download_worker_signals = WorkerSignals()
        download_worker = Worker(
            moddb_client.fetch_to_file,
            release.main_file,
            download_path,
            download_worker_signals.progress_start.emit,
            download_worker_signals.progress.emit,
            signals = download_worker_signals
        )
        return ModDownloader.DownloadJob(download_worker, download_worker_signals, release.filename)
    
    
    def add_download_job(self, job):
        self.download_jobs.append(job)
        
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
        
        self.progress_dialog.setMaximum(self.total_jobs)
        
        for job in self.download_jobs:
            thread_pool.start(job.worker)
    
    @Slot()
    def download_mod_single(self, release:ModRelease):
        path = self.release_download_path(release)
        
        job = self.prepare_mod_download(release, path)
        self.add_download_job(job)
        self.start_download()
        
    @Slot()
    def download_finished(self, result):
        result.finished = True
        self.progress_dialog.setValue(self.finished_jobs)
        
        if self.finished_jobs == self.total_jobs:
            self.progress_dialog.close()
            if self.failed_jobs > 0:
                QMessageBox.warning(self.parent(), "Download Complete", f" {self.finished_jobs} mods downloaded and {self.failed_jobs} mods failed to download\n Failed to download: {[job.filename + "\n" for job in self.gather_failed_jobs]}", QMessageBox.StandardButton.Ok)
            else:
                QMessageBox.information(self.parent(), "Download Complete", f"{self.finished_jobs} mods downloaded", QMessageBox.StandardButton.Ok)
            
            if self.disable_buttons:
                for button in self.disable_buttons:
                    if not button.isEnabled():
                        button.setEnabled(True)
            
            self.download_jobs.clear()


downloader = ModDownloader()

class ModPreview(QFrame):
    def __init__(self, mod:PartialMod, mod_detail: QWidget = None):
        super().__init__()
        self.mod = mod
        self.mod_detail_view = mod_detail
        
        self.main_layout = QVBoxLayout()
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        
        self.logo_image = QPixmap()
        self.logo_label = QLabel()
        
        if self.mod.logo != None and self.mod.logo !=  'None':
            self.fetch_logo_worker = Worker(moddb_client.fetch_to_memory, self.mod.logo)
            self.fetch_logo_worker.signals.result.connect(self.load_logo)
            self.fetch_logo_worker.signals.error.connect(lambda error: self.load_placeholder_logo())
            thread_pool.start(self.fetch_logo_worker)
        else:
            self.logo_image.load('data/test.png')
            self.logo_label.setPixmap(self.logo_image.scaledToWidth(200))
        
        self.title_label = QLabel(mod.name)
        self.summary_label = QLabel(mod.summary)
        self.summary_label.setWordWrap(True)
        self.downloads_label = QLabel(f"Downloads: <b>{mod.downloads}</b>")
        download_icon = QIcon(os.path.join(APP_PATH, 'data/icons/download.svg'))
        download_icon.addFile(os.path.join(APP_PATH, 'data/icons/download-off.svg'), mode=QIcon.Mode.Disabled)
        self.quick_download_button = QPushButton("Download")
        self.quick_download_button.setIcon(download_icon)
        self.quick_download_button.clicked.connect(self.download_mod)
        
        self.main_layout.addWidget(self.logo_label, 2)
        self.main_layout.addWidget(self.title_label, 1)
        self.main_layout.addWidget(self.summary_label, 3)
        self.main_layout.addWidget(self.downloads_label, 1)
        self.main_layout.addWidget(self.quick_download_button, 1)
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
        full_mod = moddb_client.get_mod(self.mod.mod_id)
        downloader.download_mod_single(full_mod.releases[0])
    
    def mousePressEvent(self, event:QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            event.accept()
            print(self.mod.url_alias)
            if self.mod_detail_view != None:
                self.mod_detail_view.update_mod(moddb_client.get_mod(self.mod.mod_id))
                self.mod_detail_view.show()

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
        self.search_buttons_enabled = True
        self.mods = []
        self.mods_shown = 0
        
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
        self.search_button.clicked.connect(self.search_mods)
        
        self.extra_search_container = QFrame()
        extra_search_layout = QHBoxLayout()
        
        # TODO: extra search widgets
        
        self.extra_search_container.setLayout(extra_search_layout)
        
        self.result_number = QLabel()
        self.result_number.hide()
        
        self.mods_list = QFrame()
        self.mods_list_layout = FlowLayout()
        self.mods_list.setLayout(self.mods_list_layout)
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
    
    @Slot()
    def search_mods(self):
        if self.search_buttons_enabled:
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
                    try:
                        downloader.disable_buttons.remove(widget.quick_download_button)
                    except:
                        pass
                    widget.deleteLater()
                elif isinstance(widget, QPushButton):
                    self.mods_list_layout.removeWidget(widget)
            self.mods_shown = 0
            self.mods = mods
        
        previous_shown = self.mods_shown
        self.mods_shown += 100
        print(self.mods_shown)
        mods_to_add = self.mods[previous_shown:self.mods_shown]
        
        for mod in mods_to_add:
            widget = ModPreview(mod, self.mod_detail_view)
            downloader.disable_buttons.append(widget.quick_download_button)
            self.mods_list_layout.addWidget(widget)
        
        if mods is not None:
            self.result_number.setText(f"{len(self.mods)} results found.")
            self.result_number.show()
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
        download_icon = QIcon(os.path.join(APP_PATH, 'data/icons/download.svg'))
        download_icon.addFile(os.path.join(APP_PATH, 'data/icons/download-off.svg'), mode=QIcon.Mode.Disabled)
        self.download_button.setIcon(download_icon)
        self.download_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.mod_description = QLabel()
        self.mod_description.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
    def update_mod(self, mod:Mod):
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
        self.fetch_image_worker.signals.error.connect(self.thread_exception)
        thread_pool.start(self.fetch_image_worker)
        
        self.download_button.setText("Install latest version...")
        self.download_button.clicked.connect(lambda checked: downloader.download_mod_single(self.supported_releases[0]['release']))
        to_disable_buttons.append(self.download_button)
        
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
        if isinstance(exc_tuple[0], HTTPStatusError):
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