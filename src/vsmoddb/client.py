import json
import pickle
import time
import traceback
import os

from .models import (
    Tag,
    TagType,
    Comment,
    User,
    ChangeLog,
    SearchOrderBy,
    SearchOrderDirection,
    Mod,
    PartialMod,
    ModRelease,
    ModScreenshot,
)

import httpx
from PySide6.QtWidgets import QProgressBar, QProgressDialog

USER_AGENT = "vs-mod-manager/0.1.0"
BASE_URL = "https://mods.vintagestory.at"


class ApiException(Exception):
    pass


class ModDbClient:
    def __init__(self):
        self.headers = {"user-agent": USER_AGENT}
        self.__http_client = httpx.Client(headers=self.headers, base_url=BASE_URL)

        # prefetch all tags and game versions
        self.tags: list[Tag] = self.update_mod_tags()
        self.versions: list[Tag] = self.update_game_versions()
        self.authors = self.get_all_users()

    def construct_get_params(self, options: dict[str, list[str] | str]) -> str:
        result = ""
        for key, item in options.items():
            if item == None or item == [] or item == '':
                continue
            elif isinstance(item, list):
                for inner_item in item:
                    result += key + "=" + str(inner_item) + "&"
            else:
                result += key + "=" + str(item) + "&"
        result = result.removesuffix("&")
        return result

    def get_api(self, interface: str, get_params: str = None, *args, **kwargs) -> dict:
        request = self.__http_client.build_request(
            "GET", f"/api/{interface}{f"?{get_params}" if get_params != None else ""}"
        )
        response = self.__http_client.send(request)
        response.raise_for_status()
        
        parsed_response = json.loads(response.text)
        if parsed_response['statuscode'] == '200':
            return parsed_response
        else:
            raise ApiException(
                f"Mod Db request returned {parsed_response['statuscode']}"
            )

    def get_list_like(
        self, interface: str, object_key: str, to_run, get_params: str = None
    ) -> list:
        raw_object = self.get_api(interface, get_params)
        objects = []
        for object in raw_object[object_key]:
            to_run(objects, object)
        return objects

    def update_mod_tags(self) -> list[Tag]:
        def e(tags, tag):
            tags.append(
                Tag(int(tag['tagid']), tag['name'], tag['color'], type=TagType.MOD)
            )

        return self.get_list_like("tags", "tags", e)

    def update_game_versions(self) -> list[Tag]:
        def e(versions, version):
            versions.append(
                Tag(
                    int(version['tagid']),
                    version['name'],
                    version['color'],
                    type=TagType.VERSION,
                )
            )

        return self.get_list_like("gameversions", "gameversions", e)

    def get_all_users(self) -> list[User]:
        def e(users, user):
            users.append(User(int(user['userid']), user['name']))

        return self.get_list_like("authors", "authors", e)

    def get_comments(self, asset_id: int) -> list[Comment]:
        def e(comments, raw_comment):
            user = self.user_from_id(raw_comment['userid'])
            comment = Comment(raw_comment, user)
            comments.append(comment)

        return self.get_list_like("comments/" + str(asset_id), "comments", e)

    def get_changelogs(self, asset_id: int) -> list[ChangeLog]:
        def e(changelogs, raw_changelog):
            changelog = Comment(raw_changelog)
            changelogs.append(changelog)

        return self.get_list_like("changelogs/" + str(asset_id), "changelogs", e)

    def get_mods(
        self,
        mod_tags: list[Tag] = None,
        version: Tag = None,
        versions: list[Tag] = None,
        author: User = None,
        text: str = None,
        orderby: SearchOrderBy = SearchOrderBy.TRENDING,
        order_direction: SearchOrderDirection = SearchOrderDirection.DESC,
    ):
        def e(mods, raw_mod):
            mod_author = self.user_from_name(raw_mod['author'])
            tags = []
            for tag in raw_mod['tags']:
                tags.append(self.tag_from_name(tag))
            mod = PartialMod(raw_mod, tags, mod_author)
            mods.append(mod)

        params = {
            "tagids[]": mod_tags if mod_tags != None else None,
            "gv": version.id if version != None else None,
            "gameversions[]": versions,
            "author": author.user_id if author != None else None,
            "text": text,
            "orderby": orderby.value if orderby != None else None,
            "orderdirection": (
                order_direction.value if order_direction != None else None
            ),
        }

        return self.get_list_like(
            "mods", "mods", e, get_params=self.construct_get_params(params)
        )

    def get_mod(self, mod_id: int | str):
        raw_mod = self.get_api(f"mod/{mod_id}")['mod']

        tags = []
        for tag in raw_mod['tags']:
            tags.append(self.tag_from_name(tag))

        author = self.user_from_name(raw_mod['author'])

        releases = []
        for release in raw_mod['releases']:
            release_tags = []
            for tag in release['tags']:
                release_tags.append(self.tag_from_name(tag))
            try:
                releases.append(ModRelease(release, release_tags, raw_mod['modid']))
            except TypeError:
                pass

        screenshots = []
        for screenshot in raw_mod['screenshots']:
            screenshots.append(ModScreenshot(screenshot))

        mod = Mod(raw_mod, author, tags, releases, screenshots)
        return mod
    
    def fetch_to_memory(self, url:str, *args, **kwargs) -> bytes:
        response = self.__http_client.get(url)
        response.raise_for_status()
        return response.content
    
    def fetch_to_file(self, url:str, file_location:str, start_callback = None, progress_callback = None, end_callback = None):
        try:
            with open(file_location, 'wb') as file:
                with self.__http_client.stream("GET", url) as response:
                    if start_callback:
                        try:
                            content_size = int(response.headers.get('content-length'))
                        except:
                            start_callback(0)
                        else:
                            start_callback(content_size)
                    for chunk in response.iter_bytes():
                        file.write(chunk)
                        if progress_callback:
                            progress_callback(len(chunk))
            if end_callback:
                end_callback()
        except:
            traceback.print_exc()
            return False
        return True
    
    def tag_from_id(self, id: int) -> Tag | None:
        for tag in self.tags:
            if tag.id == id:
                return tag
        for version in self.versions:
            if version.id == id:
                return version
        return None

    def tag_from_name(self, name: str) -> Tag | None:
        for tag in self.tags:
            if tag.name == name:
                return tag
        for version in self.versions:
            if version.name == name:
                return version
        return None

    def user_from_id(self, id: int) -> User | None:
        for author in self.authors:
            if author.user_id == id:
                return author
        return None

    def user_from_name(self, name: str) -> User | None:
        for author in self.authors:
            if author.name == name:
                return author
        return None


class CacheManager:
    def __init__(self, cache_location:str = "") -> None:
        self.cache_location = cache_location
        self.cache: dict[str, dict[str, object]] = {} # {key: {'object' or 'expires': object }}
        
        self.load_from_file()
    
    def get(self, key: str) -> any:
        if key not in self.cache:
            return None
        if time.time() > self.cache[key]['expires']:
            del self.cache[key]
            return None
        
        return self.cache[key]['object']
    
    def set(self, key: str, object: object, expires:int = 15):
        self.cache[key] = {
            "object": object,
            "expires": time.time() + 60 * expires # minutes
        }
    
    def clear(self):
        self.cache.clear()
        self.save_to_file()
    
    def save_to_file(self) -> None:
        to_remove = []
        for key, value in self.cache.items():
            if time.time() > value['expires']:
                to_remove.append(key)
            if key.endswith('.png'):
                to_remove.append(key)
        
        for item in to_remove:
            try:
                del self.cache[item]
            except KeyError:
                pass
        
        with open(os.path.join(self.cache_location, 'cache.dat'), 'wb') as f:
            pickle.dump(self.cache, f)

    def load_from_file(self) -> None:
        if not os.path.exists(os.path.join(self.cache_location, 'cache.dat')):
            return
        
        with open(os.path.join(self.cache_location, 'cache.dat'), 'rb') as f:
            try:
                self.cache = pickle.load(f)
            except EOFError:
                return


class CachedModDbClient(ModDbClient):
    def __init__(self, cache_manager: CacheManager = CacheManager()) -> None:
        self.cache_manager = cache_manager
        super().__init__()
    
    def get_api(self, interface, get_params = None, *args, **kwargs):
        key = f"{interface}_{get_params}"
        cached_response = self.cache_manager.get(key)
        
        if cached_response is not None:
            return cached_response
        
        response = super().get_api(interface, get_params, *args, **kwargs)
        self.cache_manager.set(key, response)
        
        return response
    
    def fetch_to_memory(self, url, *args, **kwargs):
        key = f"{url}"
        cached_response = self.cache_manager.get(key)
        
        if cached_response is not None:
            return cached_response
        
        response = super().fetch_to_memory(url, *args, **kwargs)
        self.cache_manager.set(key, response)
        
        return response
    
    def fetch_to_file(self, url, file_location, start_callback=None, progress_callback=None, end_callback=None):
        key = f"{url}_{file_location}"
        
        cached_response = self.cache_manager.get(key)
        if cached_response and os.path.exists(file_location):
            return True
        
        result = super().fetch_to_file(url, file_location, start_callback, progress_callback, end_callback)
        self.cache_manager.set(key, result)
        
        return result