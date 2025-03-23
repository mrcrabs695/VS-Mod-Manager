from vsmoddb.models import Mod, Comment

from PySide6.QtWidgets import QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QComboBox, QLabel, QPushButton, QScrollArea, QGraphicsPixmapItem, QSizePolicy, QFrame
from PySide6.QtCore import Slot, QSize
from PySide6.QtGui import QPixmap, QColor, QPalette

class ModIndex(QWidget):
    def __init__(self, parent:QWidget|None = None):
        super().__init__(parent=parent)

class CommentView(QWidget):
    def __init__(self, comment:Comment):
        self.setStyleSheet("background-color: rgb(86, 86, 125); border-radius: 2px; border: 1px solid white")
        self.setLayout(QVBoxLayout())
        
        self.title_label = QLabel()
        self.title_label.setText(f"{comment.user.name}, {comment.last_modified.strftime("%d/%m/%Y | %H:%M:%S")}")
        self.comment_body = QLabel()
        self.comment_body.setText(comment.text)

class ModDetail(QScrollArea):
    def __init__(self, mod:Mod, parent:QWidget|None = None):
        super().__init__(parent=parent)
        
        self.root_container = QWidget()
        self.root_container.setLayout(QGridLayout())
        
        self.title_card_container = QWidget()
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
        
        self.content_box = QStackedWidget()
        self.content_box.setStyleSheet(" QStackedWidget { border: 2px solid grey; }")
        self.description_container = QWidget()
        self.description_container.setLayout(QGridLayout())
        size_policy = QSizePolicy()
        size_policy.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        size_policy.setHorizontalPolicy(QSizePolicy.Policy.MinimumExpanding)
        self.description_container.setSizePolicy(size_policy)
        self.releases_container = QWidget()
        self.releases_container.setLayout(QVBoxLayout())
        self.content_box.layout().addWidget(self.description_container)
        self.content_box.layout().addWidget(self.releases_container)
        
        self.tags_container = QWidget()
        self.tags_container.setLayout(QHBoxLayout())
        
        self.author = QLabel()
        self.mod_side = QLabel()
        self.time_created = QLabel()
        self.last_modified = QLabel()
        self.downloads_counter = QLabel()
        self.follow_counter = QLabel()
        self.download_button = QPushButton()
        self.mod_description = QLabel()
        self.mod_description.setWordWrap(True)
        
        self.description_container.layout().addWidget(self.tags_container, 0, 0)
        self.description_container.layout().addWidget(self.author, 1, 0)
        self.description_container.layout().addWidget(self.mod_side, 2, 0)
        self.description_container.layout().addWidget(self.time_created, 3, 0)
        self.description_container.layout().addWidget(self.last_modified, 4, 0)
        self.description_container.layout().addWidget(self.downloads_counter, 5, 0)
        self.description_container.layout().addWidget(self.follow_counter, 6, 0)
        self.description_container.layout().addWidget(self.download_button, 7, 0, 1, 2)
        self.description_container.layout().addWidget(self.mod_description, 8, 0)
        
        self.root_container.layout().addWidget(self.title_card_container, 0, 0, 1, 3)
        self.root_container.layout().addWidget(self.description_switch, 1, 0, 1, 1)
        self.root_container.layout().addWidget(self.releases_switch, 1, 1, 1, 1)
        self.root_container.layout().addWidget(self.content_box, 2, 0, 1, 3)
        
        self.update_mod(mod)
        self.setWidget(self.root_container)
    
    @Slot()
    def show_description(self):
        self.content_box.setCurrentIndex(0)
    
    @Slot()
    def show_releases(self):
        self.content_box.setCurrentIndex(1)
    
    @Slot()
    def update_mod(self, mod:Mod):
        self.mod = mod
        
        self.title_label.setText(f"<h1>{self.mod.name}</h1>")
        self.title_label.setObjectName("mod_view_title_label")
        
        # TODO: will need to replace this with a function to download the image in the background without halting the rest of the update
        
        self.primary_image.load("data/test.png")
        self.primary_image_widget.setPixmap(self.primary_image.scaledToWidth(560))
        self.primary_image_widget.setMaximumSize(560, 350)
        self.primary_image_widget.setObjectName("mod_view_primary_image")
        
        placeholder_version = "v1.20.x"
        self.download_button.setText(f"Install mod for version {placeholder_version}...")
        self.download_button.pressed.connect(self.download_mod)
        
        for child in self.tags_container.children():
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
        
        self.time_created.setText(f"<h2>Created: {mod.created.strftime("%d/%m/%Y, %H:%M:%S")}</h2>")
        self.time_created.setObjectName("mod_view_time_created")
        
        self.last_modified.setText(f"<h2>Last Modified: {mod.last_modified.strftime("%d/%m/%Y, %H:%M:%S")}</h2>")
        self.last_modified.setObjectName("mod_view_last_modified")
        
        self.downloads_counter.setText(f"<h2>Downloads: {str(mod.downloads)}</h2>")
        self.downloads_counter.setObjectName("mod_view_downloads_counter")
        
        self.follow_counter.setText(f"<h2>Follows: {str(mod.follows)}</h2>")
        self.follow_counter.setObjectName("mod_view_follow_counter")
        
        self.mod_description.setText(mod.description)
        self.mod_description.setObjectName("mod_view_description")
    
    @Slot()
    def download_mod(self):
        print("Download function not implemented, have this nice debug message instead :)")

class HyperTag(QLabel):
    def __init__(self, text:str, bg_color:str = "#333333", tag_color:str = "aqua", text_color:str = "white", parent:QWidget|None = None):
        super().__init__(parent=parent)
        self.setStyleSheet(f"background-color: {bg_color}; border-radius: 4px")
        self.setText(f"""<p style="color: {text_color}"><b style="color: {tag_color}">#</b>  {text}</p>""")
        self.setFixedHeight(20)
        size_policy = QSizePolicy()
        size_policy.setHorizontalPolicy(QSizePolicy.Policy.Minimum)
        self.setSizePolicy(size_policy)