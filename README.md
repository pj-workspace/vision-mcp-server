# vision-mcp

面向**没有多模态能力、只能处理文本**的大模型：通过 **Model Context Protocol（stdio）** 调用阿里云百炼 **通义千问 VL**（默认 `qwen3-vl-flash`），把图片读成**结构化文本描述**，再让主对话模型基于这些文字继续推理、摘要或问答。

适用场景：宿主模型不支持图像输入、或聊天里贴图无法进入模型上下文时，用本服务单独「看图」，把结果当普通文本用。

## 功能概览

- **vision.analyze**：视觉理解与抽取（多意图、场景画像、质量档位）
- **vision.clipboard_image**（**仅 macOS**）：从剪贴板读出图片，保存到 `$HOME/.vision_mcp/clipboard/`，返回本地路径，便于再走 `vision.analyze`
- **多图**：单次 1～16 张；每张可带 `url` / `base64`+`mime_type` / `file_path`；**同时存在时优先 `file_path`，其次 URL，最后 base64**
- **意图**：`describe` | `ocr` | `extract_structure` | `compare` | `reason` | `other`
- **场景画像**：`general` | `document` | `chart` | `ui` | `education`
- **质量**：`fast` | `balanced` | `high_detail`（映射 DashScope `extra_body`）
- **大文件 / 大图**：可走百炼临时 OSS（需配置 `DASHSCOPE_API_KEY`，上传所用 `model` 须与调用一致）

## 安装

```bash
git clone <你的仓库地址> vision-mcp-server
cd vision-mcp-server
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

入口：安装后可用 `vision-mcp`，或 `python -m vision_mcp`；也可用仓库内 `start.sh`（会从环境变量或 macOS 钥匙串注入 Key，见下）。

## API Key

任选其一：

1. **`.env`**：复制 `.env.example` 为 `.env`，填写 `DASHSCOPE_API_KEY`（**切勿将 `.env` 提交到 Git**）。
2. **macOS 钥匙串**：`start.sh` 在未设置 `DASHSCOPE_API_KEY` 时会执行 `security find-generic-password -s dashscope-api-key -w`；请先在钥匙串中创建对应条目，或通过 `VISION_MCP_KEYCHAIN_SERVICE` 改用自定义服务名。

## 接入 MCP 客户端（stdio）

任意支持 **stdio MCP** 的客户端均可：在配置里写**启动命令**、工作目录和环境变量即可。以下为**占位示例**，请把路径换成你本机克隆后的目录。

**单文件入口（推荐配合 venv）：** `command` 为解释器，`args` 为 `-m vision_mcp`，`cwd` 为项目根。

```json
{
  "mcpServers": {
    "vision-mcp": {
      "command": "/path/to/vision-mcp-server/.venv/bin/python",
      "args": ["-m", "vision_mcp"],
      "cwd": "/path/to/vision-mcp-server",
      "env": {
        "PATH": "/path/to/vision-mcp-server/.venv/bin:/usr/bin:/bin"
      }
    }
  }
}
```

**使用 `start.sh`（便于钥匙串 / 固定 cwd）：**

```json
{
  "mcpServers": {
    "vision-mcp": {
      "command": "bash",
      "args": ["/path/to/vision-mcp-server/start.sh"],
      "cwd": "/path/to/vision-mcp-server"
    }
  }
}
```

不同客户端配置文件位置不同（例如部分应用使用 `claude_desktop_config.json` 等）；修改后一般需要**重启客户端**使 MCP 生效。

## 可选环境变量

| 变量 | 说明 |
|------|------|
| `VISION_MCP_MODEL` | 默认 `qwen3-vl-flash` |
| `DASHSCOPE_BASE_URL` | 默认 `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `VISION_MCP_ALLOWED_DIRS` | 额外允许的本地目录，POSIX 下用 `:` 分隔（默认可访问 `$HOME` 下路径） |
| `VISION_MCP_KEYCHAIN_SERVICE` | （macOS + `start.sh`）钥匙串服务名，默认 `dashscope-api-key` |

## 临时 OSS 上传

与百炼文档一致：解析 `oss://` 资源时需 HTTP 头 `X-DashScope-OssResourceResolve: enable`（本客户端已在 OpenAI SDK 的 `default_headers` 中配置）。

详见：[获取临时文件 URL](https://www.alibabacloud.com/help/zh/model-studio/get-temporary-file-url)

## 输出

工具返回体含 `structuredContent`：`summary`、`structured`、`per_image`、`meta`、`usage` 等；面向用户的纯文本摘要一般为 `summary`。

## 文档与模型

- [Qwen VL OpenAI 兼容](https://help.aliyun.com/zh/model-studio/developer-reference/qwen-vl-compatible-with-openai)

## 开源前自检（推送公开仓库）

仓库内**不应**出现真实密钥或仅属于你本机的路径：

| 检查项 | 说明 |
|--------|------|
| `.env` | 已在 `.gitignore` 中忽略；推送前执行 `git status`，确认未误加 |
| `git ls-files` 含 `.env` | 勿把 `.env` 纳入版本库（勿 `git add .env`） |
| 文档与示例 | 使用 `/path/to/...` 等占位路径，不要写个人用户目录 |
| `.env.example` | 仅保留占位符（如 `sk-your-key`），不要提交真实 Key |

本仓库代码中 API Key **仅**来自环境变量或钥匙串注入，无硬编码；若你曾本地修改过含密钥的文件，推送前请用 `git diff` 复核。
