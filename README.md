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
- 获取全部种子列表及详细信息
- 暂停/恢复指定种子
- 删除种子（可选是否删除文件）
- 添加磁力链接任务
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

服务器启动时可读取以下环境变量，并在首次调用工具时静默创建 QBittorrent WebUI 客户端；因此在 MCP 客户端配置了环境变量后，可以直接调用 `list_torrents()`、`add_magnet()` 等工具，无需额外执行连接步骤。

| 环境变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `QBITTORRENT_HOST` | 否 | `127.0.0.1` | QBittorrent WebUI 主机名或 IP 地址 |
| `QBITTORRENT_PORT` | 否 | `8080` | QBittorrent WebUI 端口 |
| `QBITTORRENT_USERNAME` | 是 | 无 | QBittorrent WebUI 用户名 |
| `QBITTORRENT_PASSWORD` | 是 | 无 | QBittorrent WebUI 密码 |

连接过程由服务端静默完成；`host` 与 `port` 未配置时分别回退到 `127.0.0.1` 和 `8080`。

```bash
export QBITTORRENT_HOST=127.0.0.1
export QBITTORRENT_PORT=8080
export QBITTORRENT_USERNAME=admin
export QBITTORRENT_PASSWORD=adminadmin
uvx qbittorrent-mcp
```

## MCP 协议实现

本项目通过官方 `mcp.server.fastmcp.FastMCP` 创建 MCP Server，并使用 `stdio` transport 启动，适用于 Claude Desktop、Cursor 等通过标准输入/输出通信的 MCP 客户端。安装包会暴露 `qbittorrent-mcp` 命令，该命令入口会启动 MCP stdio 服务。

当前暴露的 MCP tools：

- `list_torrents`：获取全部种子列表及状态信息
- `pause_torrent`：暂停指定哈希的种子
- `resume_torrent`：恢复指定哈希的种子
- `delete_torrent`：删除指定哈希的种子，可选删除文件
- `add_magnet`：添加磁力链接任务

## 典型场景

- **AI 助手自动管理下载任务**：结合大模型，实现智能下载、自动暂停/恢复、异常监控等
- **机器人批量任务处理**：批量添加、暂停、删除种子，适合 Telegram/QQ/微信机器人集成
- **自定义 Web/CLI 工具**：快速开发自己的种子管理前端或命令行工具

## API 说明

### 1. 获取种子列表
```python
await list_torrents() -> str
```
返回所有种子的详细信息（名称、哈希、状态、进度、速度等）。

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

### 5. 添加磁力链接
```python
await add_magnet(magnet_url: str) -> str
```
添加新的磁力链接任务。

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
A: 当前接口为单种子操作，如需批量可自行循环调用。

## 依赖说明

- Python >= 3.11
- httpx
- mcp

## 许可证

MIT License