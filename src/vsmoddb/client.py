from .models import (
    Tag,
    TagType,
    Comment,
    Author,
    ChangeLog,
    SearchOrderBy,
    SearchOrderDirection,
    Mod,
    PartialMod,
    ModRelease,
    ModScreenshot,
)
import httpx
import json

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
        self.authors = self.get_all_authors()

    def construct_get_params(self, options: dict[str, list[str] | str]) -> str:
        result = ""
        for key, item in options.items():
            if item == None:
                continue
            if isinstance(item, list):
                for inner_item in item:
                    result += key + "=" + str(inner_item) + "&"
            else:
                result += key + "=" + str(item) + "&"
        result.removesuffix("&")
        return result

    def get_api(self, interface: str, get_params: str = None, *args, **kwargs) -> dict:
        request = self.__http_client.build_request(
            "GET", f"/api/{interface}{"?" + get_params if get_params != None else ""}"
        )
        response = self.__http_client.send(request)

        # response = self.__http_client.get("/api/" + interface, *args, params=get_params, **kwargs)

        print(response.url)
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

    def get_all_authors(self) -> list[Author]:
        def e(authors, author):
            authors.append(Author(int(author['userid']), author['name']))

        return self.get_list_like("authors", "authors", e)

    def get_comments(self, asset_id: int) -> list[Comment]:
        def e(comments, raw_comment):
            comment = Comment(raw_comment)
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
        author: Author = None,
        text: str = None,
        orderby: SearchOrderBy = None,
        order_direction: SearchOrderDirection = None,
    ):
        def e(mods, raw_mod):
            mod_author = self.author_from_name(raw_mod['author'])
            tags = []
            for tag in raw_mod['tags']:
                tags.append(self.tag_from_name(tag))
            mod = PartialMod(raw_mod, tags, mod_author)
            mods.append(mod)

        params = {
            "tagids[]": mod_tags,
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

        author = self.author_from_name(raw_mod['author'])

        releases = []
        for release in raw_mod['releases']:
            release_tags = []
            for tag in release['tags']:
                release_tags.append(self.tag_from_name(tag))
            releases.append(ModRelease(release, release_tags))

        screenshots = []
        for screenshot in raw_mod['screenshots']:
            screenshots.append(ModScreenshot(screenshot))

        mod = Mod(raw_mod, author, tags, releases, screenshots)
        return mod

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

    def author_from_id(self, id: int) -> Author | None:
        for author in self.author:
            if author.id == id:
                return author
        return None

    def author_from_name(self, name: str) -> Author | None:
        for author in self.authors:
            if author.name == name:
                return author
        return None
