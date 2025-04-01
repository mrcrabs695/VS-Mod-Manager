import sys
import os
import json
import pickle
import traceback

from mod_profiles import ModProfile
from mod_info_parser import LocalMod, scan_mod_directory

if sys.platform == "win32":
    GAME_SEARCH_PATHS = [
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
        "active_profile": None,
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


# TODO: this needs a serious refactor dawg
class UserSettings:
    def __init__(self, settings_file_path:str = SETTINGS_FILE_PATH, raw:dict = None):
        # if os.path.exists(settings_file_path):
        self._settings_file_path = settings_file_path
        self._mod_info_location = None
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
                # "downloaded_mods": self.downloaded_mods,
                "profiles": self.profiles,
                "active_profile": self.active_profile,
            }
        }
    
    def save(self):
        with open(self._settings_file_path, 'w') as f:
            json.dump(self.to_dict(), f)
        
        if self._mod_info_location is not None:
            with open(self._mod_info_location, 'wb') as f:
                pickle.dump(self._downloaded_mods, f)
    
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
        # self._downloaded_mods = mod_section.get('downloaded_mods', [])
        self._profiles = mod_section.get('profiles', [])
        self._active_profile = mod_section.get('active_profile', DEFAULTS['mod_manager']['active_profile'])
        
        self._mod_info_location = os.path.join(self.mod_download_location, 'local_mod_info.dat')
        self._downloaded_mods = scan_mod_directory(self.mod_download_location)
        
        with open(self._mod_info_location, 'r+b' if os.path.exists(self._mod_info_location) else 'x+b') as f:
            try:
                loaded_mods:list[LocalMod]  = pickle.load(f)
            except EOFError:
                print("Failed to load local mod info")
                traceback.print_exc()
                loaded_mods = []
        
        for mod in loaded_mods:
            scanned_mod = self.get_mod_info(mod.mod_id_str)
            if scanned_mod is not None:
                if scanned_mod.full_mod_info != mod.full_mod_info:
                    index = self.downloaded_mods.index(scanned_mod)
                    self.downloaded_mods[index] = mod
        
        enabled_mods = scan_mod_directory(os.path.join(self.game_data_path, 'Mods'))
        for mod in enabled_mods:
            mod.is_enabled = True
            name = os.path.basename(mod.install_location)
            mod.install_location = os.path.join(self.mod_download_location, name)
            mod.current_path = os.path.join(self.game_data_path, 'Mods', name)
            
            scanned_mod = self.get_mod_info(mod.mod_id_str)
            if scanned_mod is not None:
                index = self.downloaded_mods.index(scanned_mod)
                self.downloaded_mods[index] = mod
            else:
                self.downloaded_mods.append(mod)
        
    
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
    def downloaded_mods(self) -> list[LocalMod]:
        return self._downloaded_mods
    
    @downloaded_mods.setter
    def downloaded_mods(self, value:list[LocalMod]):
        self._downloaded_mods = value
    
    def get_mod_info(self, mod_id:str|int) -> LocalMod | None:
        for mod in self.downloaded_mods:
            if mod.mod_id_str == mod_id:
                return mod
            
            elif mod.full_mod_info is not None:
                if mod.full_mod_info.mod_id == mod_id:
                    return mod
                elif mod.full_mod_info.mod_id_str == mod_id:
                    return mod
        return None
    
    @property
    def profiles(self) -> list:
        return self._profiles
    
    @profiles.setter
    def profiles(self, value:list):
        self._profiles = value
    
    @property
    def active_profile(self) -> ModProfile | None:
        return self._active_profile
    
    @active_profile.setter
    def active_profile(self, value:ModProfile | None):
        self._active_profile = value