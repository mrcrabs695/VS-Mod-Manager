import os
import json

from mod_info_parser import LocalMod

def clear_game_disabled_mods(game_data_path: str):
    # Clear the list of disabled mods from the game settings
    setting_file = os.path.join(game_data_path, "clientsettings.json")
    if os.path.exists(setting_file):
        with open(setting_file, 'r+') as file:
            data = json.load(file)
            try:
                data['stringListSettings']['disabledMods'] = []
            except KeyError:
                return False
            json.dump(data, file, indent=2)
            return True
    else:
        return False

def enable_mod(local_mod:LocalMod, version:str, game_data_path:str):
        path = os.path.join(game_data_path, 'Mods', os.path.basename(local_mod.install_location))
        
        if local_mod.is_enabled and local_mod.version == version and local_mod.current_path == path:
            return
        else:
            local_mod.is_enabled = True
            os.rename(local_mod.install_location, path)
            local_mod.current_path = path

def disable_mod(local_mod:LocalMod, version:str, game_data_path:str):
        path = os.path.join(game_data_path, 'Mods', os.path.basename(local_mod.install_location))
        if local_mod.is_enabled and local_mod.version == version and local_mod.current_path == path:
            local_mod.is_enabled = False
            os.rename(path, local_mod.install_location)
            local_mod.current_path = local_mod.install_location

class ModProfile:
    def __init__(self, mods: dict[str, str] = None, name: str = "Default", description: str = "", game_version: str = None):
        if mods is None:
            self.mods = {}
        else:
            self.mods = mods
        self.name = name
        self.description = description
        self.game_version = game_version
        self.is_active = False
    
    def add_mod(self, mod_id:str, mod_version:str):
        # Add a mod to the profile
        if mod_id not in self.mods.keys():
            self.mods[mod_id] = mod_version
    
    def remove_mod(self, mod_id: str):
        # Remove a mod from the profile
        if mod_id in self.mods.keys():
            self.mods.pop(mod_id)
    
    def update_description(self, new_description:str):
        self.description = new_description
    
    def export_to_json(self) -> dict:
        # Export the profile to JSON format
        return {
            "name": self.name,
            "description": self.description,
            "mods": self.mods,
            "game_version": self.game_version, 
        }
    
    @staticmethod
    def import_from_json(json_data: dict, game_version:str = None) -> 'ModProfile':
        return ModProfile(
            name=json_data.get('name', 'Default'),
            description=json_data.get('description', ''),
            mods=json_data.get('mods', {}),
            game_version=json_data.get('game_version', game_version),
        )
