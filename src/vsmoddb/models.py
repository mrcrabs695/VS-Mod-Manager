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

class Author:
    def __init__(self, user_id:int, name:str):
        self.user_id:int = user_id
        self.name:str = name
    
    def __str__(self):
        return self.name


class Comment:
    def __init__(self, raw:dict):
        self.comment_id = int(raw['commentid'])
        self.asset_id = int(raw['assetid'])
        self.user_id = int(raw['userid'])
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
    
    def __str__(self):
        return f"{self.name} type: {self.type.value}"


class ModRelease:
    def __init__(self, raw:dict, tags:list[Tag], changelog:ChangeLog):
        self.release_id = int(raw['releaseid'])
        self.main_file = str(raw['mainfile'])
        self.filename = str(raw['filename'])
        self.file_id = int(raw['fileid'])
        self.downloads = int(raw['downloads'])
        self.tags = tags
        self.mod_id = str(raw['modidstr'])
        self.mod_version = str(raw['modversion'])
        self.created = parse_datetime(raw['created'])
        self.changelog = changelog


class ModScreenshot:
    def __init__(self, raw:dict):
        self.file_id = int(raw['fileid'])
        self.main_file = str(raw['mainfile'])
        self.filename = str(raw['filename'])
        self.thumbnail_name = str(raw['thumbnailfilename'])
        self.created = parse_datetime(raw['created'])


class PartialMod:
    def __init__(self, raw:dict, tags:list[Tag], author:Author):
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
    def __init__(self, raw:dict, author:Author, tags:list[Tag], releases:list[ModRelease], screenshots:list[ModScreenshot]):
        self.mod_id = int(raw['modid'])
        self.asset_id = int(raw['assetid'])
        self.name = str(raw['name'])
        self.description = str(raw['description'])
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