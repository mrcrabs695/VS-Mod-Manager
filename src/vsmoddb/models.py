import json
from enum import Enum
from datetime import datetime


def parse_datetime(string:str) -> datetime:
    raw:list[str] = string.split(' ', 1)
    year:list[str] = raw[0].split('-')
    time:list[str] = raw[1].split(':')
    result:datetime = datetime(int(year[0]), int(year[1]), int(year[2]), int(time[0]), int(time[1]), int(time[2]))
    return result


class SearchOrderBy(Enum):
    CREATED = "asset.created"
    LAST_RELEASED = "lastreleased"
    DOWNLOADS = "downloads"
    FOLLOWS = "follows"
    COMMENTS = "comments"
    TRENDING = "trendingpoints"

class SearchOrderDirection(Enum):
    ASC = "asc"
    DESC = "desc"

class User:
    def __init__(self, user_id:int, name:str):
        self.user_id:int = user_id
        self.name:str = name
    
    def __str__(self):
        return self.name


class Comment:
    def __init__(self, raw:dict, user:User):
        self.comment_id = int(raw['commentid'])
        self.asset_id = int(raw['assetid'])
        self.user = user
        self.text = str(raw['text'])
        self.created = parse_datetime(raw['created'])
        self.last_modified = parse_datetime(raw['lastmodified'])
        
    def __str__(self):
        return f"comment id: {self.comment_id} by: {self.user_id}"


class ChangeLog:
    def __init__(self, raw:dict):
        self.changelog_id = int(raw['changelogid'])
        self.asset_id = int(raw['assetid'])
        self.user_id = int(raw['userid'])
        self.text = str(raw['text'])
        self.created = parse_datetime(raw['created'])
        self.last_modified = parse_datetime(raw['lastmodified'])
    
    def __str__(self):
        return f"changelog id: {self.changelog_id} by: {self.user_id}"


class ModSupportSide(Enum):
    CLIENT = "client"
    SERVER = "server"
    BOTH = "both"
    
    def match(string:str):
        if string == ModSupportSide.CLIENT:
            return ModSupportSide.CLIENT
        elif string == ModSupportSide.SERVER:
            return ModSupportSide.SERVER
        elif string == ModSupportSide.BOTH:
            return ModSupportSide.BOTH
        else:
            return None



class TagType(Enum):
    VERSION = "version"
    MOD = "mod"


class Tag:
    def __init__(self, id:int, name:str, color:str, type:TagType):
        self.id:int = id
        self.name:str = name
        self.color:str = color
        self.type = type
        
        if self.type == TagType.VERSION:
            splits = name.removeprefix("v").split(".", 2)
            
            try:
                self.major_version = int(splits[0])
                self.minor_version = int(splits[1])
                
                patch_and_modifier = splits[2].split("-")
                try:
                    self.patch_version = int(patch_and_modifier[0])
                    self.version_modifier = patch_and_modifier[1]
                except IndexError:
                    self.patch_version = int(splits[2])
                    self.version_modifier = None
                except ValueError: # this pops up when parsing the games older version format, so this is a bit of a band-aid solution
                    patch_and_modifier = splits[2].split(".")
                    self.patch_version = int(patch_and_modifier[0])
                    self.version_modifier = patch_and_modifier[1]
                
            except ValueError as e:
                raise ValueError(f"Invalid version tag: {name}") from e
    
    def __str__(self):
        return f"{self.name} type: {self.type.value}"


class ModRelease:
    def __init__(self, raw:dict, tags:list[Tag], parent_mod_id:int):
        self.release_id = int(raw['releaseid'])
        self.main_file = str(raw['mainfile'])
        self.filename = str(raw['filename'])
        self.file_id = int(raw['fileid'])
        self.downloads = int(raw['downloads'])
        self.tags = tags
        self.mod_id_str = str(raw['modidstr'])
        self.mod_id = parent_mod_id
        self.mod_version = str(raw['modversion'])
        self.created = parse_datetime(raw['created'])
        self.changelog = str(raw['changelog'])


class ModScreenshot:
    def __init__(self, raw:dict):
        self.file_id = int(raw['fileid'])
        self.main_file = str(raw['mainfile'])
        self.filename = str(raw['filename'])
        self.thumbnail_name = str(raw['thumbnailfilename'])
        self.created = parse_datetime(raw['created'])


class PartialMod:
    def __init__(self, raw:dict, tags:list[Tag], author:User):
        self.mod_id = int(raw['modid'])
        self.asset_id = int(raw['assetid'])
        self.downloads = int(raw['downloads'])
        self.follows = int(raw['follows'])
        self.trending_points = int(raw['trendingpoints'])
        self.comments = int(raw['comments'])
        self.name = str(raw['name'])
        self.summary = str(raw['summary'])
        self.mod_id_strs:list[str] = raw['modidstrs']
        self.author = author
        self.url_alias = str(raw['urlalias'])
        self.side = ModSupportSide.match(raw['side'])
        self.type = str(raw['type'])
        self.logo = str(raw['logo'])
        self.tags = tags
        self.last_released = parse_datetime(raw['lastreleased'])

class Mod:
    def __init__(self, raw:dict, author:User, tags:list[Tag], releases:list[ModRelease], screenshots:list[ModScreenshot]):
        self.mod_id = int(raw['modid'])
        self.asset_id = int(raw['assetid'])
        self.name = str(raw['name'])
        self.description = str(raw['text'])
        self.author = author
        self.url_alias = str(raw['urlalias'])
        self.logo_filename = str(raw['logofilename'])
        self.logo_file = str(raw['logofile'])
        self.homepage_url = str(raw['homepageurl'])
        self.source_code_url = str(raw['sourcecodeurl'])
        self.trailer_video_url = str(raw['trailervideourl'])
        self.issue_tracker_url = str(raw['issuetrackerurl'])
        self.wiki_url = str(raw['wikiurl'])
        self.downloads = int(raw['downloads'])
        self.follows = int(raw['follows'])
        self.trending_points = int(raw['trendingpoints'])
        self.comments = int(raw['comments'])
        self.side = ModSupportSide.match(raw['side'])
        self.type = str(raw['type'])
        self.created = parse_datetime(raw['created'])
        self.last_released = parse_datetime(raw['lastreleased'])
        self.last_modified = parse_datetime(raw['lastmodified'])
        self.tags = tags
        self.releases = releases
        self.screenshots = screenshots
    
    def get_releases_for_version(self, version:Tag, include_pre_release=False, strict_match=False):
        if version.type != TagType.VERSION:
            return []
        
        releases:list[dict[str, ModRelease | list[Tag]]] = []
        for release in self.releases:
            if strict_match and version in release.tags:
                releases.append(release)
                continue
            if include_pre_release:
                # TODO: this should work, but if any bug pops up with version selection, check back on this
                release_tags = [tag for tag in release.tags if tag.minor_version == version.minor_version and tag.major_version == version.major_version]
            else:
                release_tags = [tag for tag in release.tags if tag.minor_version == version.minor_version and tag.major_version == version.major_version and tag.version_modifier is None]
            
            if len(release_tags) < 1:
                continue
            
            releases.append({"release": release, "tags": release_tags})
        
        releases.sort(key=lambda x: x["release"].created, reverse=True)
        return releases