# vision-mcp

面向**没有多模态能力、只能处理文本**的大模型：通过 **Model Context Protocol（stdio）** 调用视觉 API，把图片读成**结构化文本描述**，再让主对话模型基于这些文字继续推理、摘要或问答。

**默认提供商**：阿里云百炼 **通义千问 VL**（`qwen3-vl-flash`）。设置 `VISION_MCP_PROVIDER=moonshot` 可改用 **Moonshot / Kimi** 视觉模型（见 [API Key](#api-key)）。

适用场景：宿主模型不支持图像输入、或聊天里贴图无法进入模型上下文时，用本服务单独「看图」，把结果当普通文本用。

**English:** [README.md](README.md)

## 功能概览

- **vision.analyze**：视觉理解与抽取（多意图、场景画像、质量档位）
- **vision.clipboard_image**（**仅 macOS**）：从剪贴板读出图片，保存到 `$HOME/.vision_mcp/clipboard/`，返回本地路径，便于再走 `vision.analyze`
- **多图**：单次 1～16 张；每张可带 `url` / `base64`+`mime_type` / `file_path`；**同时存在时优先 `file_path`，其次 URL，最后 base64**
- **意图**：`describe` | `ocr` | `extract_structure` | `compare` | `reason` | `other`
- **场景画像**：`general` | `document` | `chart` | `ui` | `education`
- **质量**：`fast` | `balanced` | `high_detail`（仅 DashScope 生效，映射 `extra_body`；Moonshot/Kimi 下忽略）
- **大文件 / 大图**：DashScope 可走百炼临时 OSS；Moonshot/Kimi 将图片内联为 data URL（不支持 `oss://`）
- **本地路径**：默认可访问 `$HOME`、系统临时目录（便于剪贴板截图）及 `VISION_MCP_ALLOWED_DIRS` 配置的目录

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

复制 `.env.example` 为 `.env`（**切勿将 `.env` 提交到 Git**），按需选择提供商：

### 百炼 DashScope（默认）

```bash
# VISION_MCP_PROVIDER=dashscope   # 可省略，默认即 dashscope
DASHSCOPE_API_KEY=sk-your-dashscope-key
# VISION_MCP_MODEL=qwen3-vl-flash
```

**macOS 钥匙串**：`start.sh` 在未设置 `DASHSCOPE_API_KEY` 时会执行 `security find-generic-password -s dashscope-api-key -w`；请先在钥匙串中创建对应条目，或通过 `VISION_MCP_KEYCHAIN_SERVICE` 改用自定义服务名。

### Moonshot / Kimi

```bash
VISION_MCP_PROVIDER=moonshot
MOONSHOT_API_KEY=sk-your-key
VISION_MCP_MODEL=moonshot-v1-8k-vision-preview   # 或 kimi-for-coding（Coding Plan）
MOONSHOT_BASE_URL=https://api.moonshot.cn/v1     # Coding Plan：https://api.kimi.com/coding/v1
```

也可使用通用变量 `VISION_MCP_API_KEY` 代替各提供商专用 Key。解析顺序：`VISION_MCP_API_KEY` → `MOONSHOT_API_KEY` → `DASHSCOPE_API_KEY`。

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

不同客户端配置文件位置不同；修改后一般需要**重启客户端**使 MCP 生效。

## 可选环境变量

| 变量 | 说明 |
|------|------|
| `VISION_MCP_PROVIDER` | `dashscope`（默认）或 `moonshot` / `kimi` |
| `VISION_MCP_API_KEY` | 通用 API Key（优先于各提供商专用变量） |
| `VISION_MCP_MODEL` | DashScope 默认 `qwen3-vl-flash`；Moonshot 默认 `moonshot-v1-8k-vision-preview` |
| `VISION_MCP_BASE_URL` | 可选，覆盖 Moonshot OpenAI 兼容端点 |
| `DASHSCOPE_API_KEY` | 百炼 API Key |
| `DASHSCOPE_BASE_URL` | 默认 `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `MOONSHOT_API_KEY` | Moonshot / Kimi API Key |
| `MOONSHOT_BASE_URL` | 默认 `https://api.moonshot.cn/v1` |
| `VISION_MCP_ALLOWED_DIRS` | 额外允许的本地目录，POSIX 下用 `:` 分隔（`$HOME` 与系统临时目录始终允许） |
| `VISION_MCP_KEYCHAIN_SERVICE` | （macOS + `start.sh`）钥匙串服务名，默认 `dashscope-api-key` |

## 临时 OSS 上传（仅 DashScope）

当 `VISION_MCP_PROVIDER=dashscope` 时，大体积本地图片与 `oss://` 可走百炼临时 OSS；客户端通过 OpenAI SDK `default_headers` 设置 `X-DashScope-OssResourceResolve: enable`。

Moonshot/Kimi 下图片以内联 data URL 发送，不支持 `oss://`，请改用 `file_path` 或 `base64`。

详见：[获取临时文件 URL](https://www.alibabacloud.com/help/zh/model-studio/get-temporary-file-url)

## 输出

工具返回体含 `structuredContent`：`summary`、`structured`、`per_image`、`meta`、`usage` 等；面向用户的纯文本摘要一般为 `summary`。

## 文档与模型

- [Qwen VL OpenAI 兼容](https://help.aliyun.com/zh/model-studio/developer-reference/qwen-vl-compatible-with-openai)
- [Moonshot 开放平台](https://platform.moonshot.cn/docs)

## 交流与作者

使用问题、建议与交流：**https://pjlab.top**

## 开源前自检（推送公开仓库）

仓库内**不应**出现真实密钥或仅属于你本机的路径：

| 检查项 | 说明 |
|--------|------|
| `.env` | 已在 `.gitignore` 中忽略；推送前执行 `git status`，确认未误加 |
| `git ls-files` 含 `.env` | 勿把 `.env` 纳入版本库（勿 `git add .env`） |
| 文档与示例 | 使用 `/path/to/...` 等占位路径，不要写个人用户目录 |
| `.env.example` | 仅保留占位符（如 `sk-your-key`），不要提交真实 Key |

本仓库代码中 API Key **仅**来自环境变量或钥匙串注入，无硬编码；若你曾本地修改过含密钥的文件，推送前请用 `git diff` 复核。

## 开源许可

本项目以 **MIT License** 开源，详见仓库根目录 [LICENSE](LICENSE) 文件。
