import sys
import os
import json

if sys.platform == "win32":
    GAME_SEARCH_PATHS = [ #? i think this is the default location for windows users, may need to double check that however
        os.path.join(os.environ['APPDATA'], 'Vintagestory')
    ]
    GAME_DATA_PATH = os.path.join(os.environ['APPDATA'], 'VintagestoryData')
    USER_SETTINGS_PATH = os.path.join(os.environ['APPDATA'], "VsModManager")
elif sys.platform == "linux":
    GAME_SEARCH_PATHS = [ #? this should cover most game installs, but this may need to be modified depending on the game install method (perhaps add a way to manually specify the search paths?)
        "/usr/share/vintagestory/",
        os.path.expanduser("~/.local/share/vintagestory/")
        # TODO: add install directory for flatpak users
    ]
    GAME_DATA_PATH = os.path.expanduser("~/.config/VintagestoryData")
    USER_SETTINGS_PATH = os.path.expanduser("~/.local/share/VsModManager")
else:
    raise NotImplementedError(f"Unsupported platform: {sys.platform}")

if hasattr(sys, 'frozen') and hasattr(sys, '_MEIPASS'):
    # Running as a bundled executable
    APP_PATH = sys._MEIPASS
else:
    # Running as a script
    APP_PATH = os.path.curdir

def locate_game_path():
    for path in GAME_SEARCH_PATHS:
        if os.path.exists(os.path.join(path, "assets")):
            return path
    return None

def locate_game_data_path():
    if os.path.exists(GAME_DATA_PATH):
        return GAME_DATA_PATH
    return None

def locate_user_settings_path():
    if os.path.exists(USER_SETTINGS_PATH):
        return USER_SETTINGS_PATH
    else:
        os.mkdir(USER_SETTINGS_PATH)
        return USER_SETTINGS_PATH

def get_installed_game_version():
    game_path = locate_game_path()
    if game_path is None:
        return None
    assets_folder = os.path.join(game_path, "assets")
    for filename in os.listdir(assets_folder):
        if filename.startswith("version-"):
            return filename.split("-")[1].removesuffix(".txt")
    return None


DEFAULTS = {
    "game": {
        "path": locate_game_path(),
        "version": get_installed_game_version(),
        "data_path": locate_game_data_path(),
        "current_enabled_mods": [], # not including base game mods
    },
    "mod_manager": {
        "download_location": os.path.join(USER_SETTINGS_PATH, "mods"),
        "cache_location": os.path.join(USER_SETTINGS_PATH, "cache"),
        "first_launch": True,
        "downloaded_mods": {},
        "profiles": [],
    }
}

SETTINGS_FILE_PATH = os.path.join(locate_user_settings_path(), "settings.json")


def get_user_settings():
    settings_file = SETTINGS_FILE_PATH
    try:
        with open(settings_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        with open(settings_file, 'x') as f:
            json.dump(DEFAULTS, f)
        return DEFAULTS


class SettingsLoadFailed(Exception):
    pass


class UserSettings:
    def __init__(self, settings_file_path:str = SETTINGS_FILE_PATH, raw:dict = None):
        # if os.path.exists(settings_file_path):
        self._settings_file_path = settings_file_path
        # else:
        #     raise FileNotFoundError(f"Settings file not found at {settings_file_path}")
        
        if raw is not None:
            self.load(raw)
        else:
            result = self.load_from_file()
            if result == False:
                raise SettingsLoadFailed("Failed to load settings from file")
        
        self.generate_dirs()
    
    def to_dict(self) -> dict:
        return {
            "game": {
                "path": self.game_path,
                "version": self.game_version,
                "data_path": self.game_data_path,
                "current_enabled_mods": self.current_enabled_mods,
            },
            "mod_manager": {
                "download_location": self.mod_download_location,
                "cache_location": self.cache_location,
                "first_launch": self.first_launch,
                "downloaded_mods": self.downloaded_mods,
                "profiles": self.profiles,
            }
        }
    
    def save(self):
        with open(self._settings_file_path, 'w') as f:
            json.dump(self.to_dict(), f)
    
    def load(self, raw:dict):
        game_section = raw.get('game', {})
        mod_section = raw.get('mod_manager', {})
        
        self._game_path = game_section.get('path', "")
        self._game_version = game_section.get('version', "")
        self._game_data_path = game_section.get('data_path', "")
        self._current_enabled_mods = game_section.get('current_enabled_mods', [])

        self._first_launch = mod_section.get('first_launch', DEFAULTS['mod_manager']['first_launch'])
        self._mod_download_location = mod_section.get('download_location', DEFAULTS['mod_manager']['download_location'])
        self._cache_location = mod_section.get('cache_location', DEFAULTS['mod_manager']['cache_location'])
        self._downloaded_mods = mod_section.get('downloaded_mods', {})
        self._profiles = mod_section.get('profiles', [])
    
    def load_from_file(self) -> bool:
        raw = get_user_settings()
        
        if raw is not None:
            self.load(raw)
            return True
        else:
            return False
    
    def generate_dirs(self):
        if not os.path.exists(self.mod_download_location):
            os.makedirs(self.mod_download_location)
        if not os.path.exists(self.cache_location):
            os.makedirs(self.cache_location)
    
    @property
    def game_path(self):
        return self._game_path
    
    @game_path.setter
    def game_path(self, value:str):
        self._game_path = value
    
    @property
    def game_version(self):
        return self._game_version
    
    @game_version.setter
    def game_version(self, value:str):
        self._game_version = value
    
    @property
    def game_data_path(self):
        return self._game_data_path
    
    @game_data_path.setter
    def game_data_path(self, value:str):
        self._game_data_path = value
    
    @property
    def current_enabled_mods(self) -> list[str]:
        return self._current_enabled_mods
    
    @current_enabled_mods.setter
    def current_enabled_mods(self, value:list[str]):
        self._current_enabled_mods = value
    
    @property
    def first_launch(self) -> bool:
        return self._first_launch
    
    @first_launch.setter
    def first_launch(self, value:bool):
        self._first_launch = value
    
    @property
    def mod_download_location(self):
        return self._mod_download_location
    
    @mod_download_location.setter
    def mod_download_location(self, value:str):
        self._mod_download_location = value
    
    @property
    def cache_location(self):
        return self._cache_location
    
    @property
    def downloaded_mods(self) -> dict[str, str]:
        return self._downloaded_mods
    
    @downloaded_mods.setter
    def downloaded_mods(self, value:dict[str, str]):
        self._downloaded_mods = value
    
    @property
    def profiles(self) -> list:
        return self._profiles
    
    @profiles.setter
    def profiles(self, value:list):
        self._profiles = value