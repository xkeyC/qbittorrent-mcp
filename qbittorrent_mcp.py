import json
import os
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("qbittorrent")


@dataclass
class QBittorrentConfig:
    """qBittorrent WebUI connection configuration."""

    base_url: str
    username: str
    password: str


class QBittorrentAPIError(Exception):
    """qBittorrent WebUI API error with optional HTTP status code."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _get_response_message(response: httpx.Response) -> str:
    """Return the most useful error message from an HTTP response."""

    return response.text.strip() or response.reason_phrase or "Unknown error"


def _format_error(action: str, error: QBittorrentAPIError) -> str:
    """Format an API error for MCP tool responses."""

    if error.status_code is not None:
        return f"{action}失败：HTTP {error.status_code} - {error.message}"
    return f"{action}失败：{error.message}"


def _missing_config_message() -> str:
    return (
        "qBittorrent WebUI credentials are not configured. Set "
        "QBITTORRENT_USERNAME and QBITTORRENT_PASSWORD."
    )


def _get_env_config() -> Optional[QBittorrentConfig]:
    """Load qBittorrent WebUI connection configuration from environment variables."""

    username = os.getenv("QBITTORRENT_USERNAME")
    password = os.getenv("QBITTORRENT_PASSWORD")

    if not username or not password:
        return None

    base_url = os.getenv("QBITTORRENT_URL")
    if not base_url:
        scheme = os.getenv("QBITTORRENT_SCHEME", "http")
        host = os.getenv("QBITTORRENT_HOST", "127.0.0.1")
        port = os.getenv("QBITTORRENT_PORT", "8080")
        base_url = f"{scheme}://{host}:{port}"

    return QBittorrentConfig(base_url.rstrip("/"), username, password)


def _format_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _clean_params(values: dict[str, Any]) -> dict[str, str]:
    params: dict[str, str] = {}
    for key, value in values.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            params[key] = _bool(value)
        else:
            params[key] = str(value)
    return params


def _pipe_value(value: str, *, name: str) -> str:
    normalized = "|".join(part.strip() for part in re.split(r"[|,\n]", value) if part.strip())
    if not normalized:
        raise ValueError(f"{name} 不能为空")
    return normalized


def _comma_value(value: str, *, name: str) -> str:
    normalized = ",".join(part.strip() for part in re.split(r"[,\n]", value) if part.strip())
    if not normalized:
        raise ValueError(f"{name} 不能为空")
    return normalized


def _lines_value(value: str, *, name: str) -> str:
    normalized = "\n".join(part.strip() for part in re.split(r"[\n,]", value) if part.strip())
    if not normalized:
        raise ValueError(f"{name} 不能为空")
    return normalized


def _json_object(value: str, *, name: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} 必须是合法 JSON 对象：{exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} 必须是 JSON 对象")
    return parsed


class QBittorrentClient:
    """qBittorrent WebUI API v2 client."""

    def __init__(self, config: QBittorrentConfig):
        self.config = config
        self._authenticated = False
        self.session = httpx.AsyncClient(
            base_url=config.base_url,
            follow_redirects=True,
            timeout=30.0,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Origin": config.base_url,
                "Referer": config.base_url,
                "User-Agent": "qbittorrent-mcp/0.1",
            },
        )

    async def _login(self) -> None:
        """Login to qBittorrent WebUI and keep the SID cookie in the session."""

        try:
            response = await self.session.post(
                "/api/v2/auth/login",
                data={"username": self.config.username, "password": self.config.password},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response = exc.response
            raise QBittorrentAPIError(
                _get_response_message(response),
                response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise QBittorrentAPIError(str(exc)) from exc

        body = response.text.strip()
        if body != "Ok.":
            raise QBittorrentAPIError(body or "Login failed", response.status_code)

        self._authenticated = True

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        retry_auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Make an authenticated request to qBittorrent WebUI API."""

        if not self._authenticated:
            await self._login()

        try:
            response = await self.session.request(method, f"/api/v2/{endpoint}", **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response = exc.response
            if response.status_code == 403 and retry_auth:
                self._authenticated = False
                await self._login()
                return await self._request(method, endpoint, retry_auth=False, **kwargs)
            raise QBittorrentAPIError(
                _get_response_message(response),
                response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise QBittorrentAPIError(str(exc)) from exc

        if not response.content:
            return True

        try:
            return response.json()
        except ValueError:
            return response.text.strip() or True

    async def get(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> Any:
        return await self._request("GET", endpoint, params=_clean_params(params or {}))

    async def post(self, endpoint: str, data: Optional[dict[str, Any]] = None) -> Any:
        return await self._request("POST", endpoint, data=_clean_params(data or {}))

    async def add_torrent_urls(self, urls: str, options: dict[str, Any]) -> Any:
        fields = _clean_params({"urls": _lines_value(urls, name="urls"), **options})
        multipart_fields = [(key, (None, value)) for key, value in fields.items()]
        return await self._request("POST", "torrents/add", files=multipart_fields)


_client: Optional[QBittorrentClient] = None


def _get_client() -> Optional[QBittorrentClient]:
    """Return the active client, lazily initializing it from environment variables."""

    global _client

    if _client:
        return _client

    config = _get_env_config()
    if not config:
        return None

    _client = QBittorrentClient(config)
    return _client


async def _execute(
    action: str,
    operation: Callable[[QBittorrentClient], Awaitable[Any]],
    *,
    success_message: Optional[str] = None,
    as_json: bool = False,
) -> str:
    client = _get_client()
    if not client:
        return _missing_config_message()

    try:
        result = await operation(client)
    except ValueError as error:
        return f"{action}失败：{error}"
    except QBittorrentAPIError as error:
        return _format_error(action, error)

    if as_json:
        return _format_json(result)
    return success_message or f"{action}成功"


def _torrent_add_options(
    save_path: str,
    cookie: str,
    category: str,
    tags: str,
    skip_checking: Optional[bool],
    paused: Optional[bool],
    root_folder: Optional[bool],
    rename: str,
    upload_limit: Optional[int],
    download_limit: Optional[int],
    ratio_limit: Optional[float],
    seeding_time_limit: Optional[int],
    auto_tmm: Optional[bool],
    sequential_download: Optional[bool],
    first_last_piece_priority: Optional[bool],
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "savepath": save_path,
        "cookie": cookie,
        "category": category,
        "tags": tags,
        "skip_checking": skip_checking,
        "paused": paused,
        "root_folder": root_folder,
        "rename": rename,
        "upLimit": upload_limit,
        "dlLimit": download_limit,
        "ratioLimit": ratio_limit,
        "seedingTimeLimit": seeding_time_limit,
        "autoTMM": auto_tmm,
        "sequentialDownload": sequential_download,
        "firstLastPiecePrio": first_last_piece_priority,
    }
    return options


@mcp.tool()
async def list_torrents(
    filter: str = "",
    category: str = "",
    tag: str = "",
    sort: str = "",
    reverse: Optional[bool] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    hashes: str = "",
) -> str:
    """List torrents with optional qBittorrent filters."""

    params = {
        "filter": filter,
        "category": category,
        "tag": tag,
        "sort": sort,
        "reverse": reverse,
        "limit": limit,
        "offset": offset,
        "hashes": _pipe_value(hashes, name="hashes") if hashes else "",
    }
    return await _execute("获取种子列表", lambda client: client.get("torrents/info", params), as_json=True)


@mcp.tool()
async def get_torrent_properties(torrent_hash: str) -> str:
    """Get generic properties for one torrent hash."""

    return await _execute(
        "获取种子属性",
        lambda client: client.get("torrents/properties", {"hash": torrent_hash}),
        as_json=True,
    )


@mcp.tool()
async def get_torrent_trackers(torrent_hash: str) -> str:
    """Get trackers for one torrent hash."""

    return await _execute(
        "获取 Tracker 列表",
        lambda client: client.get("torrents/trackers", {"hash": torrent_hash}),
        as_json=True,
    )


@mcp.tool()
async def get_torrent_files(torrent_hash: str, indexes: str = "") -> str:
    """Get files for one torrent hash. indexes accepts comma, pipe, or newline separated ids."""

    params = {"hash": torrent_hash, "indexes": _pipe_value(indexes, name="indexes") if indexes else ""}
    return await _execute("获取种子文件", lambda client: client.get("torrents/files", params), as_json=True)


@mcp.tool()
async def pause_torrents(hashes: str) -> str:
    """Pause torrents. hashes accepts hash list or 'all'."""

    return await _execute(
        "暂停种子",
        lambda client: client.post("torrents/pause", {"hashes": _pipe_value(hashes, name="hashes")}),
    )


@mcp.tool()
async def pause_torrent(torrent_hash: str) -> str:
    """Pause a torrent by its hash."""

    return await pause_torrents(torrent_hash)


@mcp.tool()
async def resume_torrents(hashes: str) -> str:
    """Resume torrents. hashes accepts hash list or 'all'."""

    return await _execute(
        "恢复种子",
        lambda client: client.post("torrents/resume", {"hashes": _pipe_value(hashes, name="hashes")}),
    )


@mcp.tool()
async def resume_torrent(torrent_hash: str) -> str:
    """Resume a paused torrent by its hash."""

    return await resume_torrents(torrent_hash)


@mcp.tool()
async def delete_torrents(hashes: str, delete_files: bool = False) -> str:
    """Delete torrents. hashes accepts hash list or 'all'."""

    return await _execute(
        "删除种子",
        lambda client: client.post(
            "torrents/delete",
            {"hashes": _pipe_value(hashes, name="hashes"), "deleteFiles": delete_files},
        ),
    )


@mcp.tool()
async def delete_torrent(torrent_hash: str, delete_files: bool = False) -> str:
    """Delete a torrent by its hash."""

    return await delete_torrents(torrent_hash, delete_files)


@mcp.tool()
async def recheck_torrents(hashes: str) -> str:
    """Recheck torrents. hashes accepts hash list or 'all'."""

    return await _execute(
        "校验种子",
        lambda client: client.post("torrents/recheck", {"hashes": _pipe_value(hashes, name="hashes")}),
    )


@mcp.tool()
async def reannounce_torrents(hashes: str) -> str:
    """Reannounce torrents. hashes accepts hash list or 'all'."""

    return await _execute(
        "重新汇报种子",
        lambda client: client.post("torrents/reannounce", {"hashes": _pipe_value(hashes, name="hashes")}),
    )


@mcp.tool()
async def add_torrent_urls(
    urls: str,
    save_path: str = "",
    cookie: str = "",
    category: str = "",
    tags: str = "",
    skip_checking: Optional[bool] = None,
    paused: Optional[bool] = None,
    root_folder: Optional[bool] = None,
    rename: str = "",
    upload_limit: Optional[int] = None,
    download_limit: Optional[int] = None,
    ratio_limit: Optional[float] = None,
    seeding_time_limit: Optional[int] = None,
    auto_tmm: Optional[bool] = None,
    sequential_download: Optional[bool] = None,
    first_last_piece_priority: Optional[bool] = None,
) -> str:
    """Add torrents from URLs or magnet links. Multiple URLs can be newline separated."""

    options = _torrent_add_options(
        save_path,
        cookie,
        category,
        tags,
        skip_checking,
        paused,
        root_folder,
        rename,
        upload_limit,
        download_limit,
        ratio_limit,
        seeding_time_limit,
        auto_tmm,
        sequential_download,
        first_last_piece_priority,
    )
    return await _execute("添加下载任务", lambda client: client.add_torrent_urls(urls, options))


@mcp.tool()
async def add_trackers(torrent_hash: str, urls: str) -> str:
    """Add tracker URLs to a torrent. Multiple URLs can be newline separated."""

    return await _execute(
        "添加 Tracker",
        lambda client: client.post(
            "torrents/addTrackers",
            {"hash": torrent_hash, "urls": _lines_value(urls, name="urls")},
        ),
    )


@mcp.tool()
async def set_file_priority(torrent_hash: str, file_ids: str, priority: int) -> str:
    """Set torrent file priority. priority: 0 skip, 1 normal, 6 high, 7 max."""

    return await _execute(
        "设置文件优先级",
        lambda client: client.post(
            "torrents/filePrio",
            {"hash": torrent_hash, "id": _pipe_value(file_ids, name="file_ids"), "priority": priority},
        ),
    )


@mcp.tool()
async def get_torrent_download_limits(hashes: str) -> str:
    """Get per-torrent download limits in bytes/s. hashes accepts hash list or 'all'."""

    return await _execute(
        "获取下载限速",
        lambda client: client.post("torrents/downloadLimit", {"hashes": _pipe_value(hashes, name="hashes")}),
        as_json=True,
    )


@mcp.tool()
async def set_torrent_download_limit(hashes: str, limit: int) -> str:
    """Set per-torrent download limit in bytes/s. 0 disables the limit."""

    return await _execute(
        "设置下载限速",
        lambda client: client.post(
            "torrents/setDownloadLimit",
            {"hashes": _pipe_value(hashes, name="hashes"), "limit": limit},
        ),
    )


@mcp.tool()
async def get_torrent_upload_limits(hashes: str) -> str:
    """Get per-torrent upload limits in bytes/s. hashes accepts hash list or 'all'."""

    return await _execute(
        "获取上传限速",
        lambda client: client.post("torrents/uploadLimit", {"hashes": _pipe_value(hashes, name="hashes")}),
        as_json=True,
    )


@mcp.tool()
async def set_torrent_upload_limit(hashes: str, limit: int) -> str:
    """Set per-torrent upload limit in bytes/s. 0 disables the limit."""

    return await _execute(
        "设置上传限速",
        lambda client: client.post(
            "torrents/setUploadLimit",
            {"hashes": _pipe_value(hashes, name="hashes"), "limit": limit},
        ),
    )


@mcp.tool()
async def set_torrent_location(hashes: str, location: str) -> str:
    """Set download location for torrents. hashes accepts hash list or 'all'."""

    return await _execute(
        "设置保存位置",
        lambda client: client.post(
            "torrents/setLocation",
            {"hashes": _pipe_value(hashes, name="hashes"), "location": location},
        ),
    )


@mcp.tool()
async def rename_torrent(torrent_hash: str, name: str) -> str:
    """Rename a torrent."""

    return await _execute(
        "重命名种子",
        lambda client: client.post("torrents/rename", {"hash": torrent_hash, "name": name}),
    )


@mcp.tool()
async def set_torrent_category(hashes: str, category: str) -> str:
    """Set category for torrents. hashes accepts hash list or 'all'."""

    return await _execute(
        "设置种子分类",
        lambda client: client.post(
            "torrents/setCategory",
            {"hashes": _pipe_value(hashes, name="hashes"), "category": category},
        ),
    )


@mcp.tool()
async def list_categories() -> str:
    """List all qBittorrent categories."""

    return await _execute("获取分类", lambda client: client.get("torrents/categories"), as_json=True)


@mcp.tool()
async def create_category(category: str, save_path: str = "") -> str:
    """Create a qBittorrent category."""

    return await _execute(
        "创建分类",
        lambda client: client.post("torrents/createCategory", {"category": category, "savePath": save_path}),
    )


@mcp.tool()
async def edit_category(category: str, save_path: str) -> str:
    """Edit a qBittorrent category save path."""

    return await _execute(
        "编辑分类",
        lambda client: client.post("torrents/editCategory", {"category": category, "savePath": save_path}),
    )


@mcp.tool()
async def remove_categories(categories: str) -> str:
    """Remove categories. Multiple category names can be comma or newline separated."""

    return await _execute(
        "删除分类",
        lambda client: client.post(
            "torrents/removeCategories",
            {"categories": _lines_value(categories, name="categories")},
        ),
    )


@mcp.tool()
async def list_tags() -> str:
    """List all qBittorrent tags."""

    return await _execute("获取标签", lambda client: client.get("torrents/tags"), as_json=True)


@mcp.tool()
async def create_tags(tags: str) -> str:
    """Create tags. Multiple tag names can be comma or newline separated."""

    return await _execute(
        "创建标签",
        lambda client: client.post("torrents/createTags", {"tags": _comma_value(tags, name="tags")}),
    )


@mcp.tool()
async def delete_tags(tags: str) -> str:
    """Delete tags. Multiple tag names can be comma or newline separated."""

    return await _execute(
        "删除标签",
        lambda client: client.post("torrents/deleteTags", {"tags": _comma_value(tags, name="tags")}),
    )


@mcp.tool()
async def add_torrent_tags(hashes: str, tags: str) -> str:
    """Add tags to torrents. hashes accepts hash list or 'all'."""

    return await _execute(
        "添加种子标签",
        lambda client: client.post(
            "torrents/addTags",
            {"hashes": _pipe_value(hashes, name="hashes"), "tags": _comma_value(tags, name="tags")},
        ),
    )


@mcp.tool()
async def remove_torrent_tags(hashes: str, tags: str) -> str:
    """Remove tags from torrents. hashes accepts hash list or 'all'."""

    return await _execute(
        "移除种子标签",
        lambda client: client.post(
            "torrents/removeTags",
            {"hashes": _pipe_value(hashes, name="hashes"), "tags": _comma_value(tags, name="tags")},
        ),
    )


@mcp.tool()
async def set_auto_torrent_management(hashes: str, enable: bool) -> str:
    """Enable or disable automatic torrent management. hashes accepts hash list or 'all'."""

    return await _execute(
        "设置自动种子管理",
        lambda client: client.post(
            "torrents/setAutoManagement",
            {"hashes": _pipe_value(hashes, name="hashes"), "enable": enable},
        ),
    )


@mcp.tool()
async def toggle_sequential_download(hashes: str) -> str:
    """Toggle sequential download. hashes accepts hash list or 'all'."""

    return await _execute(
        "切换顺序下载",
        lambda client: client.post(
            "torrents/toggleSequentialDownload",
            {"hashes": _pipe_value(hashes, name="hashes")},
        ),
    )


@mcp.tool()
async def toggle_first_last_piece_priority(hashes: str) -> str:
    """Toggle first/last piece priority. hashes accepts hash list or 'all'."""

    return await _execute(
        "切换首尾块优先",
        lambda client: client.post(
            "torrents/toggleFirstLastPiecePrio",
            {"hashes": _pipe_value(hashes, name="hashes")},
        ),
    )


@mcp.tool()
async def set_force_start(hashes: str, value: bool) -> str:
    """Enable or disable force start. hashes accepts hash list or 'all'."""

    return await _execute(
        "设置强制开始",
        lambda client: client.post(
            "torrents/setForceStart",
            {"hashes": _pipe_value(hashes, name="hashes"), "value": value},
        ),
    )


@mcp.tool()
async def set_super_seeding(hashes: str, value: bool) -> str:
    """Enable or disable super seeding. hashes accepts hash list or 'all'."""

    return await _execute(
        "设置超级做种",
        lambda client: client.post(
            "torrents/setSuperSeeding",
            {"hashes": _pipe_value(hashes, name="hashes"), "value": value},
        ),
    )


@mcp.tool()
async def get_application_info() -> str:
    """Get qBittorrent application and WebAPI versions."""

    async def operation(client: QBittorrentClient) -> dict[str, Any]:
        return {
            "version": await client.get("app/version"),
            "webapi_version": await client.get("app/webapiVersion"),
            "default_save_path": await client.get("app/defaultSavePath"),
        }

    return await _execute("获取应用信息", operation, as_json=True)


@mcp.tool()
async def get_application_preferences() -> str:
    """Get qBittorrent application preferences."""

    return await _execute("获取应用设置", lambda client: client.get("app/preferences"), as_json=True)


@mcp.tool()
async def set_application_preferences(preferences_json: str) -> str:
    """Set qBittorrent application preferences. preferences_json must be a JSON object."""

    async def operation(client: QBittorrentClient) -> Any:
        preferences = _json_object(preferences_json, name="preferences_json")
        return await client.post("app/setPreferences", {"json": json.dumps(preferences)})

    return await _execute("设置应用设置", operation)


@mcp.tool()
async def get_transfer_info() -> str:
    """Get global transfer information."""

    return await _execute("获取传输信息", lambda client: client.get("transfer/info"), as_json=True)


@mcp.tool()
async def set_global_download_limit(limit: int) -> str:
    """Set global download limit in bytes/s. 0 disables the limit."""

    return await _execute(
        "设置全局下载限速",
        lambda client: client.post("transfer/setDownloadLimit", {"limit": limit}),
    )


@mcp.tool()
async def set_global_upload_limit(limit: int) -> str:
    """Set global upload limit in bytes/s. 0 disables the limit."""

    return await _execute(
        "设置全局上传限速",
        lambda client: client.post("transfer/setUploadLimit", {"limit": limit}),
    )


@mcp.tool()
async def rss_add_folder(path: str) -> str:
    """Add an RSS folder by full path."""

    return await _execute("添加 RSS 文件夹", lambda client: client.post("rss/addFolder", {"path": path}))


@mcp.tool()
async def rss_add_feed(url: str, path: str = "") -> str:
    """Add an RSS feed URL. path is an optional RSS folder path."""

    return await _execute("添加 RSS 订阅", lambda client: client.post("rss/addFeed", {"url": url, "path": path}))


@mcp.tool()
async def rss_remove_item(path: str) -> str:
    """Remove an RSS feed or folder by full path."""

    return await _execute("删除 RSS 项", lambda client: client.post("rss/removeItem", {"path": path}))


@mcp.tool()
async def rss_move_item(item_path: str, dest_path: str) -> str:
    """Move or rename an RSS feed/folder."""

    return await _execute(
        "移动 RSS 项",
        lambda client: client.post("rss/moveItem", {"itemPath": item_path, "destPath": dest_path}),
    )


@mcp.tool()
async def rss_items(with_data: bool = False) -> str:
    """Get RSS items. with_data includes feed articles."""

    return await _execute(
        "获取 RSS 项",
        lambda client: client.get("rss/items", {"withData": with_data}),
        as_json=True,
    )


@mcp.tool()
async def rss_mark_as_read(item_path: str, article_id: str = "") -> str:
    """Mark an RSS feed/folder or one article as read."""

    return await _execute(
        "标记 RSS 已读",
        lambda client: client.post("rss/markAsRead", {"itemPath": item_path, "articleId": article_id}),
    )


@mcp.tool()
async def rss_refresh_item(item_path: str) -> str:
    """Refresh an RSS feed or folder."""

    return await _execute(
        "刷新 RSS 项",
        lambda client: client.post("rss/refreshItem", {"itemPath": item_path}),
    )


@mcp.tool()
async def rss_set_rule(rule_name: str, rule_def_json: str) -> str:
    """Create or update an RSS auto-downloading rule. rule_def_json must be a JSON object."""

    async def operation(client: QBittorrentClient) -> Any:
        rule_def = _json_object(rule_def_json, name="rule_def_json")
        return await client.post(
            "rss/setRule",
            {"ruleName": rule_name, "ruleDef": json.dumps(rule_def)},
        )

    return await _execute("设置 RSS 自动下载规则", operation)


@mcp.tool()
async def rss_rename_rule(rule_name: str, new_rule_name: str) -> str:
    """Rename an RSS auto-downloading rule."""

    return await _execute(
        "重命名 RSS 规则",
        lambda client: client.post(
            "rss/renameRule",
            {"ruleName": rule_name, "newRuleName": new_rule_name},
        ),
    )


@mcp.tool()
async def rss_remove_rule(rule_name: str) -> str:
    """Remove an RSS auto-downloading rule."""

    return await _execute(
        "删除 RSS 规则",
        lambda client: client.post("rss/removeRule", {"ruleName": rule_name}),
    )


@mcp.tool()
async def rss_rules() -> str:
    """Get all RSS auto-downloading rules."""

    return await _execute("获取 RSS 规则", lambda client: client.get("rss/rules"), as_json=True)


@mcp.tool()
async def rss_matching_articles(rule_name: str) -> str:
    """Get RSS articles matching an auto-downloading rule."""

    return await _execute(
        "获取 RSS 规则匹配文章",
        lambda client: client.get("rss/matchingArticles", {"ruleName": rule_name}),
        as_json=True,
    )


def main() -> None:
    """Run the MCP server over stdio."""

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
