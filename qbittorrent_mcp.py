import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("qbittorrent")


@dataclass
class QBittorrentConfig:
    """QBittorrent WebUI connection configuration."""
    host: str
    port: int
    username: str
    password: str


class QBittorrentAPIError(Exception):
    """QBittorrent WebUI API error with optional HTTP status code."""

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
        return f"{action}: HTTP {error.status_code} - {error.message}"
    return f"{action}: {error.message}"


def _get_env_config() -> Optional[QBittorrentConfig]:
    """Load QBittorrent WebUI connection configuration from environment variables."""
    username = os.getenv("QBITTORRENT_USERNAME")
    password = os.getenv("QBITTORRENT_PASSWORD")

    if not username or not password:
        return None

    host = os.getenv("QBITTORRENT_HOST", "127.0.0.1")
    port = int(os.getenv("QBITTORRENT_PORT", "8080"))
    return QBittorrentConfig(host, port, username, password)


class QBittorrentClient:
    """QBittorrent WebUI API client."""

    def __init__(self, config: QBittorrentConfig):
        self.base_url = f"http://{config.host}:{config.port}"
        self.auth = (config.username, config.password)
        self.session = httpx.AsyncClient()
        self._cookies = None

    async def _login(self) -> None:
        """Login to QBittorrent WebUI."""
        try:
            response = await self.session.post(
                f"{self.base_url}/api/v2/auth/login",
                data={"username": self.auth[0], "password": self.auth[1]},
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

        self._cookies = response.cookies

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Any]:
        """Make an authenticated request to QBittorrent WebUI API."""
        if not self._cookies:
            await self._login()

        try:
            response = await self.session.request(
                method,
                f"{self.base_url}/api/v2/{endpoint}",
                cookies=self._cookies,
                **kwargs,
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

        if not response.content:
            return True

        try:
            return response.json()
        except ValueError:
            return response.text.strip() or True

    async def get_torrents(self) -> List[Dict[str, Any]]:
        """Get list of torrents."""
        result = await self._request("GET", "torrents/info")
        return result or []

    async def pause_torrents(self, hashes: List[str]) -> bool:
        """Pause torrents by their hashes."""
        result = await self._request(
            "POST",
            "torrents/pause",
            data={"hashes": "|".join(hashes)},
        )
        return result is not None

    async def resume_torrents(self, hashes: List[str]) -> bool:
        """Resume torrents by their hashes."""
        result = await self._request(
            "POST",
            "torrents/resume",
            data={"hashes": "|".join(hashes)},
        )
        return result is not None

    async def delete_torrents(self, hashes: List[str], delete_files: bool = False) -> bool:
        """Delete torrents by their hashes."""
        result = await self._request(
            "POST",
            "torrents/delete",
            data={
                "hashes": "|".join(hashes),
                "deleteFiles": str(delete_files).lower(),
            },
        )
        return result is not None

    async def add_torrent(self, magnet_url: str) -> bool:
        """Add a new torrent from magnet link."""
        result = await self._request(
            "POST",
            "torrents/add",
            data={"urls": magnet_url},
        )
        return result is not None

# Global client instance
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


@mcp.tool()
async def list_torrents() -> str:
    """Get list of all torrents and their download information."""
    client = _get_client()
    if not client:
        return (
            "QBittorrent WebUI credentials are not configured. Set "
            "QBITTORRENT_USERNAME and QBITTORRENT_PASSWORD."
        )

    try:
        torrents = await client.get_torrents()
    except QBittorrentAPIError as error:
        return _format_error("Failed to fetch torrents", error)

    if not torrents:
        return "No torrents found."

    result = []
    for t in torrents:
        status = f"""
名称: {t.get('name', 'Unknown')}
哈希值: {t.get('hash', 'Unknown')}
状态: {t.get('state', 'Unknown')}
进度: {t.get('progress', 0) * 100:.1f}%
大小: {t.get('size', 0) / (1024*1024*1024):.2f} GB
下载速度: {t.get('dlspeed', 0) / (1024*1024):.1f} MB/s
上传速度: {t.get('upspeed', 0) / (1024*1024):.1f} MB/s"""
        result.append(status)

    return "\n---\n".join(result)


@mcp.tool()
async def pause_torrent(torrent_hash: str) -> str:
    """Pause a torrent by its hash.

    Args:
        torrent_hash: Hash of the torrent to pause
    """
    client = _get_client()
    if not client:
        return (
            "QBittorrent WebUI credentials are not configured. Set "
            "QBITTORRENT_USERNAME and QBITTORRENT_PASSWORD."
        )

    try:
        if await client.pause_torrents([torrent_hash]):
            return "Successfully paused torrent"
    except QBittorrentAPIError as error:
        return _format_error("Failed to pause torrent", error)
    return "Failed to pause torrent"


@mcp.tool()
async def resume_torrent(torrent_hash: str) -> str:
    """Resume a paused torrent by its hash.

    Args:
        torrent_hash: Hash of the torrent to resume
    """
    client = _get_client()
    if not client:
        return (
            "QBittorrent WebUI credentials are not configured. Set "
            "QBITTORRENT_USERNAME and QBITTORRENT_PASSWORD."
        )

    try:
        if await client.resume_torrents([torrent_hash]):
            return "Successfully resumed torrent"
    except QBittorrentAPIError as error:
        return _format_error("Failed to resume torrent", error)
    return "Failed to resume torrent"


@mcp.tool()
async def delete_torrent(torrent_hash: str, delete_files: bool = False) -> str:
    """Delete a torrent by its hash.

    Args:
        torrent_hash: Hash of the torrent to delete
        delete_files: Whether to delete downloaded files
    """
    client = _get_client()
    if not client:
        return (
            "QBittorrent WebUI credentials are not configured. Set "
            "QBITTORRENT_USERNAME and QBITTORRENT_PASSWORD."
        )

    try:
        if await client.delete_torrents([torrent_hash], delete_files):
            return "Successfully deleted torrent"
    except QBittorrentAPIError as error:
        return _format_error("Failed to delete torrent", error)
    return "Failed to delete torrent"


@mcp.tool()
async def add_magnet(magnet_url: str) -> str:
    """Add a new torrent from magnet link.

    Args:
        magnet_url: Magnet URL of the torrent
    """
    client = _get_client()
    if not client:
        return (
            "QBittorrent WebUI credentials are not configured. Set "
            "QBITTORRENT_USERNAME and QBITTORRENT_PASSWORD."
        )

    try:
        if await client.add_torrent(magnet_url):
            return "Successfully added torrent"
    except QBittorrentAPIError as error:
        return _format_error("Failed to add torrent", error)
    return "Failed to add torrent"


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
