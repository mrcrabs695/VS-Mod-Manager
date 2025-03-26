import settings
from vsmoddb.client import ModDbClient, CachedModDbClient, CacheManager
from PySide6.QtCore import QThreadPool

user_settings = settings.UserSettings()
moddb_client = CachedModDbClient(CacheManager(user_settings.cache_location))
thread_pool = QThreadPool()

from . import main_window, mod_index, worker