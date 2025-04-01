import os
import json
import traceback
from zipfile import ZipFile

from vsmoddb.models import Mod, Tag, ModRelease
from httpx import HTTPStatusError

BASE_GAME_MOD_IDS = ['game', 'survival', 'creative']

class LocalMod:
    def __init__(self, raw:dict, path:str, icon_bytes:bytes):
        raw = {key.lower():value for key, value in raw.items()}
        
        self.type = raw.get('type', None)
        self.mod_id_str = raw.get('modid')
        self.network_version = raw.get('networkVersion', None)
        self.name = raw.get('name', None)
        self.description = raw.get('description', None)
        self.authors = raw.get('authors', None)
        self.contributors = raw.get('contributors', None)
        self.translators = raw.get('translators', None)
        self.version = raw.get('version', None)
        self.dependencies:dict = {key:value for key, value in raw.get('dependencies', {}).items() if key not in BASE_GAME_MOD_IDS}
        self.website = raw.get('website', None)
        self.icon:bytes = icon_bytes
        
        self.install_location = path
        self.current_path = path
        self.is_enabled = False
        self.full_mod_info:Mod | None = None
    
    def fetch_full_mod_info(self, vsmoddb_client):
        if self.full_mod_info is None:
            try:
                self.full_mod_info = vsmoddb_client.get_mod(self.mod_id_str)
            except HTTPStatusError:
                print(f"Failed to get mod info for mod ID: {self.mod_id_str}")
    
    def get_matching_release(self, vsmoddb_client):
        if self.full_mod_info is None:
            self.fetch_full_mod_info(vsmoddb_client)
        
        for release in self.full_mod_info.releases:
            if release.mod_version == self.version:
                return release
        return None
    
    def check_for_updates(self, vsmoddb_client, game_version:Tag):
        if self.full_mod_info is None:
            self.fetch_full_mod_info(vsmoddb_client)
        
        current_release = self.get_matching_release(vsmoddb_client)
        latest_release:ModRelease = self.full_mod_info.get_releases_for_version(game_version)[0]['release']
        
        if current_release.mod_version != latest_release.mod_version:
            print(f"Update available: {latest_release.mod_version} -> {current_release.mod_version}")
            return latest_release
        else:
            print("No updates available.")
            return None
    
    def get_mod_dependencies(self, vsmoddb_client):
        mods_to_get: list[tuple[LocalMod, ModRelease]]  = []
        failed_mod_ids: list[str] = []
        
        for mod_id_str, version in self.dependencies.items():
            print(f"Fetching {mod_id_str}")
            print(f"Version: {version}")
            try:
                mod = vsmoddb_client.get_mod(mod_id_str)
            except HTTPStatusError:
                failed_mod_ids.append(mod_id_str)
                continue
            
            mod_release = mod.get_release(version)
            if mod_release is not None:
                mods_to_get.append((mod, mod_release))
            else:
                failed_mod_ids.append(mod_id_str)
        
        return mods_to_get, failed_mod_ids

def get_mod_info(mod_path:str) -> LocalMod:
    if not os.path.exists(mod_path):
        raise FileNotFoundError(f"Mod file {mod_path} does not exist.")
    if not mod_path.endswith('.zip'):
        raise ValueError("Mod file must be a ZIP archive.")
    
    with ZipFile(mod_path, 'r') as zip_ref:
        info_file = zip_ref.open('modinfo.json')
        mod_info = json.load(info_file)
        try:
            icon = zip_ref.read('modicon.png')
        except KeyError:
            icon = None
        
        return LocalMod(mod_info, mod_path, icon)

# def mod_info_from_filename(filename:str) -> LocalMod:
#     if not filename.endswith('.zip'):
#         raise ValueError("Mod file must be a ZIP archive.")
#     mod_info = {}
#     mod_info['']
    
def scan_mod_directory(directory:str) -> list[LocalMod]:
    scanned_mods = []
    
    for entry in os.scandir(directory):
        if entry.is_file() and entry.name.endswith('.zip'):
            try:
                local_mod = get_mod_info(entry.path)
            except:
                print(f"Failed to scan mod: {entry.path}")
                traceback.print_exc()
                # print("Continuing with limited data...")
                continue
            scanned_mods.append(local_mod)
    
    return scanned_mods
