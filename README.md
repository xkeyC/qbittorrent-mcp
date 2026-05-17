# qbittorrent-mcp

MCP Compatible

一个基于 Model Context Protocol (MCP) 的 QBittorrent 远程管理工具，专为自动化脚本、AI 助手、机器人集成或自定义管理工具开发而设计。通过 MCP 协议与 QBittorrent WebUI API 对接，实现种子任务的远程管理与自动化操作。

## 设计理念

qbittorrent-mcp 旨在让 AI 或自动化系统能够以极简、标准化的方式远程控制 QBittorrent，实现批量种子管理、自动化下载、智能监控等场景。通过抽象出高层 API，屏蔽底层 WebUI 细节，让开发者专注于业务逻辑。

核心优势：
- **MCP 标准协议**：与主流 AI/自动化平台无缝集成
- **极简接口**：一行代码即可完成连接与操作
- **异步支持**：高并发、低延迟，适合大规模自动化
- **环境变量配置**：可通过环境变量注入 QBittorrent WebUI 登录信息
- **安全隔离**：无需暴露 QBittorrent 账号密码给第三方

## 功能特点

- 静默连接 QBittorrent WebUI（支持鉴权）
- 支持从环境变量读取 QBittorrent WebUI 连接信息
- 获取、筛选种子列表及详细属性、Tracker、文件列表
- 添加磁力链接/URL 下载任务，支持分类、标签、保存路径、限速、暂停添加等参数
- 批量暂停/恢复/删除/校验/重新汇报种子
- 管理种子分类、标签、保存位置、文件优先级、限速、顺序下载、强制开始等
- 查看应用设置、传输状态并调整常用限速配置
- 管理 RSS 文件夹、订阅源、已读状态、刷新和自动下载规则
- 适用于自动化脚本、AI 助手、机器人等多种场景

## 安装方法

### uv 安装

```bash
uv tool install git+https://github.com/xkeyC/qbittorrent-mcp
```

### 方法三：配置 Claude Desktop

在 Claude Desktop 配置文件中添加服务器配置：
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

添加如下配置：
```json
{
  "mcpServers": {
    "qbittorrent": {
      "command": "uvx",
      "args": [
        "qbittorrent-mcp"
      ],
      "env": {
        "QBITTORRENT_HOST": "127.0.0.1",
        "QBITTORRENT_PORT": "8080",
        "QBITTORRENT_USERNAME": "admin",
        "QBITTORRENT_PASSWORD": "adminadmin"
      }
    }
  }
}
```

### 方法四：从源码安装并配置 Cursor 本地开发环境

在 Cursor IDE 中，可以通过本地配置文件来设置 MCP 服务器：
- Windows: `C:\Users\用户名\.cursor\mcp.json`
- macOS: `~/.cursor/mcp.json`

添加如下配置：
```json
{
  "mcpServers": {
    "qbittorrent": {
      "command": "uv",
      "args": [
        "--directory",
        "/你的本地项目路径/qbittorrent-mcp/",
        "run",
        "qbittorrent-mcp"
      ],
      "env": {
        "QBITTORRENT_HOST": "127.0.0.1",
        "QBITTORRENT_PORT": "8080",
        "QBITTORRENT_USERNAME": "admin",
        "QBITTORRENT_PASSWORD": "adminadmin"
      }
    }
  }
}
```

这种配置方式适合本地开发和测试使用，可以直接指向本地代码目录。

### 方法五：源码安装

```bash
git clone https://github.com/yourname/qbittorrent-mcp.git
cd qbittorrent-mcp
pip install .
```

## 环境变量配置

服务器启动时可读取以下环境变量，并在首次调用工具时静默创建 QBittorrent WebUI 客户端；因此在 MCP 客户端配置了环境变量后，可以直接调用 `list_torrents()`、`add_torrent_urls()` 等工具，无需额外执行连接步骤。

| 环境变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `QBITTORRENT_URL` | 否 | 无 | 完整 WebUI 地址，例如 `http://127.0.0.1:8080`；设置后优先于 `SCHEME/HOST/PORT` |
| `QBITTORRENT_SCHEME` | 否 | `http` | WebUI 协议，未设置 `QBITTORRENT_URL` 时生效 |
| `QBITTORRENT_HOST` | 否 | `127.0.0.1` | WebUI 主机名或 IP 地址，未设置 `QBITTORRENT_URL` 时生效 |
| `QBITTORRENT_PORT` | 否 | `8080` | WebUI 端口，未设置 `QBITTORRENT_URL` 时生效 |
| `QBITTORRENT_USERNAME` | 是 | 无 | QBittorrent WebUI 用户名 |
| `QBITTORRENT_PASSWORD` | 是 | 无 | QBittorrent WebUI 密码 |

连接过程由服务端静默完成。客户端会按 qBittorrent WebUI API 要求自动携带会话 Cookie、`Origin` 和 `Referer`，避免启用 CSRF/Host 校验后添加下载任务出现 403。

```bash
export QBITTORRENT_HOST=127.0.0.1
export QBITTORRENT_PORT=8080
export QBITTORRENT_USERNAME=admin
export QBITTORRENT_PASSWORD=adminadmin
uvx qbittorrent-mcp
```

## MCP 协议实现

本项目通过官方 `mcp.server.fastmcp.FastMCP` 创建 MCP Server，并使用 `stdio` transport 启动，适用于 Claude Desktop、Cursor 等通过标准输入/输出通信的 MCP 客户端。安装包会暴露 `qbittorrent-mcp` 命令，该命令入口会启动 MCP stdio 服务。

当前暴露的主要 MCP tools：

- 种子查询：`list_torrents`、`get_torrent_properties`、`get_torrent_trackers`、`get_torrent_files`
- 任务添加：`add_torrent_urls`
- 批量控制：`pause_torrents`、`resume_torrents`、`delete_torrents`、`recheck_torrents`、`reannounce_torrents`
- 单任务兼容工具：`pause_torrent`、`resume_torrent`、`delete_torrent`
- 种子管理：`add_trackers`、`set_file_priority`、`set_torrent_location`、`rename_torrent`、`set_torrent_category`
- 限速管理：`get_torrent_download_limits`、`set_torrent_download_limit`、`get_torrent_upload_limits`、`set_torrent_upload_limit`、`set_global_download_limit`、`set_global_upload_limit`
- 分类与标签：`list_categories`、`create_category`、`edit_category`、`remove_categories`、`list_tags`、`create_tags`、`delete_tags`、`add_torrent_tags`、`remove_torrent_tags`
- 高级开关：`set_auto_torrent_management`、`toggle_sequential_download`、`toggle_first_last_piece_priority`、`set_force_start`、`set_super_seeding`
- 应用信息：`get_application_info`、`get_application_preferences`、`set_application_preferences`、`get_transfer_info`
- RSS：`rss_add_folder`、`rss_add_feed`、`rss_remove_item`、`rss_move_item`、`rss_items`、`rss_mark_as_read`、`rss_refresh_item`、`rss_set_rule`、`rss_rename_rule`、`rss_remove_rule`、`rss_rules`、`rss_matching_articles`

批量工具的 `hashes` 参数支持单个哈希、用逗号/换行/竖线分隔的多个哈希，或 qBittorrent API 支持的 `all`。

## 典型场景

- **AI 助手自动管理下载任务**：结合大模型，实现智能下载、自动暂停/恢复、异常监控等
- **机器人批量任务处理**：批量添加、暂停、删除种子，适合 Telegram/QQ/微信机器人集成
- **自定义 Web/CLI 工具**：快速开发自己的种子管理前端或命令行工具

## API 说明

### 1. 获取种子列表
```python
await list_torrents(keyword: str = "", filter: str = "", limit: int | None = None, offset: int | None = None) -> str
```
返回种子的详细信息（名称、哈希、状态、进度、速度等）。`filter` 支持 `downloading`、`completed`、`paused`、`active` 等 qBittorrent 状态筛选；`limit` 和 `offset` 支持分页。传入 `keyword` 时，会在 MCP 侧按页查询最多 10000 条任务，并在 `name`、`hash`、`category`、`tags`、`state`、`save_path`、`content_path` 中进行大小写不敏感匹配，再对匹配结果应用 `limit` 和 `offset`。

示例：
```python
await list_torrents(keyword="ubuntu")
await list_torrents(keyword="ubuntu", filter="completed", limit=20, offset=0)
```

### 2. 暂停种子
```python
await pause_torrent(torrent_hash: str) -> str
```
暂停指定哈希的种子。

### 3. 恢复种子
```python
await resume_torrent(torrent_hash: str) -> str
```
恢复指定哈希的种子。

### 4. 删除种子
```python
await delete_torrent(torrent_hash: str, delete_files: bool = False) -> str
```
删除指定哈希的种子，可选是否同时删除已下载文件。

### 5. 添加 URL 或磁力链接下载任务
```python
await add_torrent_urls(urls: str, save_path: str = "", category: str = "", tags: str = "") -> str
```
`urls` 支持换行分隔的多个 URL 或 magnet。更多参数可控制保存路径、Cookie、跳校验、暂停添加、分类、标签、限速、自动管理、顺序下载和首尾块优先级。

### 6. RSS 订阅
```python
await rss_add_feed(url: str, path: str = "") -> str
await rss_items(with_data: bool = False) -> str
await rss_set_rule(rule_name: str, rule_def_json: str) -> str
```
`rule_def_json` 需要传入 JSON 对象字符串，对应 qBittorrent 的 RSS 自动下载规则定义。

## 最佳实践

- **调用工具前请确保 QBittorrent WebUI 已开启并允许 API 访问**
- **所有操作均为异步，建议在 async 环境下调用**
- **建议将账号密码配置在安全环境变量中，避免泄露**
- **在 Claude Desktop、Cursor 等 MCP 客户端中优先通过 `env` 字段注入 `QBITTORRENT_USERNAME` 和 `QBITTORRENT_PASSWORD`**

## 常见问题解答

**Q: 连接失败怎么办？**
A: 请检查 QBittorrent WebUI 是否开启、端口/用户名/密码是否正确，或是否有防火墙阻挡。

**Q: 如何获取种子的哈希值？**
A: 调用 `list_torrents()`，返回信息中包含每个种子的哈希值。

**Q: 支持批量操作吗？**
A: 支持。批量工具的 `hashes` 参数可传单个哈希、多个哈希或 `all`。

**Q: 添加下载任务为什么以前会 403？**
A: qBittorrent WebUI API 在启用 CSRF/Host 校验时要求请求带有匹配的 `Origin` 或 `Referer`，并使用登录获得的 SID Cookie。当前实现已按官方 API 处理这些请求头和会话 Cookie。

## 依赖说明

- Python >= 3.11
- httpx
- mcp

## 许可证

MIT License
