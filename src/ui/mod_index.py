import os
import traceback

from . import moddb_client, thread_pool, user_settings
from .worker import Worker, WorkerSignals
from vsmoddb.models import Mod, Comment, ModRelease

from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox, QLabel, QPushButton, QScrollArea, QGraphicsPixmapItem, QSizePolicy, QFrame, QProgressDialog, QMessageBox, QLayout
from PySide6.QtCore import Slot, QSize, QThread, QObject, QThreadPool
from PySide6.QtGui import QPixmap, QColor, QPalette
from httpx import HTTPStatusError

# TODO: once the groundwork is done, all the temp style sheets will need to be removed and replaced with a proper app level stylesheet


class ModDownloader(QObject):
    #? This could be refactored to handle more then just downloading once the actual mod index widget is created
    def __init__(self, to_disabled_buttons:list[QPushButton] = None, mod_release:ModRelease|list[ModRelease] = None, parent:QWidget|None = None):
        super().__init__(parent=parent)
        self.to_disabled_buttons = to_disabled_buttons
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
            
            for button in self.disable_buttons:
                if not button.isEnabled():
                    button.setEnabled(True)
            
            self.download_jobs.clear()


downloader = ModDownloader()

class ModPreview(QFrame):
    def __init__(self, mod:Mod):
        super().__init__()
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
    
    def sizeHint(self):
        return self.layout().minimumSize()

class ModIndex(QWidget):
    def __init__(self, parent:QWidget|None = None):
        super().__init__(parent=parent)
        
        self.setLayout(QGridLayout())


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
        self.download_button = QPushButton("Download")
        
        layout.addWidget(self.release_title_label, 0, 0, 1, 3)
        layout.addWidget(self.download_counter, 1, 0, 1, 1)
        layout.addWidget(self.release_date_label, 2, 0, 1, 1)
        layout.addWidget(self.download_button, 3, 0, 1, 2)
        layout.addWidget(self.changelog, 4, 0, 3, 3)
        
        self.setLayout(layout)

class ModDetail(QScrollArea):
    def __init__(self, mod:Mod, parent:QWidget|None = None):
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
        self.description_switch.setText("Description")
        self.description_switch.pressed.connect(self.show_description)
        self.releases_switch = QPushButton()
        self.releases_switch.setText("Releases")
        self.releases_switch.pressed.connect(self.show_releases)
        self.comments_switch = QPushButton()
        self.comments_switch.setText("Comments")
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
        
        self.primary_image.load("data/test.png")
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
        
        # for child in self.tags_container.children():
        #     child.deleteLater()
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
        
        # for child in self.releases_container.children():
        #     child.deleteLater()
        
        print(len(self.supported_releases))
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
            
            self.displayed_comments += 100
            try:
                comments_to_add = comments[:self.displayed_comments]
            except:
                comments_to_add = []
        
        else:
            self.displayed_comments += 100
            comments_to_add = self.comments[:self.displayed_comments]
            self.comments_container.layout().removeWidget(self.load_more_comments)
        
        for comment in comments_to_add:
            self.comments_container.layout().addWidget(CommentView(comment))
        
        self.comments_container.layout().addWidget(self.load_more_comments)
        self.comments_container.updateGeometry()
    
    @Slot()
    def thread_exception(self, exc_tuple:tuple):
        if not self.download_button.isEnabled():
            self.download_button.setEnabled(True)
        
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