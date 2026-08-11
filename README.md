# vision-mcp

An MCP (stdio) server for **text-only** large language models: it calls a vision API to turn images into **structured text**, so your main model can keep reasoning without native vision support.

**Default provider:** Alibaba Cloud **DashScope Qwen VL** (`qwen3-vl-flash`). Set `VISION_MCP_PROVIDER=moonshot` to use **Moonshot / Kimi** vision instead (see [API key](#api-key)).

Use it when the host model cannot accept images, or pasted images never reach the model context—run vision here and feed the text back.

**Languages:** [中文说明](README.zh-CN.md)

## Features

- **vision.analyze** — vision understanding with intent, profile, and quality presets
- **vision.clipboard_image** (**macOS only**) — read image from clipboard, save under `$HOME/.vision_mcp/clipboard/`, return paths for **vision.analyze**
- **Multi-image**: 1–16 per request; each item may include `url`, `base64` + `mime_type`, or `file_path` — **if several are set, priority is `file_path` → URL → base64**
- **Intents**: `describe` | `ocr` | `extract_structure` | `compare` | `reason` | `other`
- **Profiles**: `general` | `document` | `chart` | `ui` | `education`
- **Quality**: `fast` | `balanced` | `high_detail` (DashScope only — maps to `extra_body`; ignored on Moonshot/Kimi)
- **Large / big local files**: DashScope can use temporary OSS upload; Moonshot/Kimi inlines images as data URLs (no `oss://` support)
- **Local paths**: `$HOME`, system temp dir (for clipboard screenshots), and `VISION_MCP_ALLOWED_DIRS` are allowed by default

## Install

```bash
git clone <your-repo-url> vision-mcp-server
cd vision-mcp-server
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

After install, use `vision-mcp` or `python -m vision_mcp`. The repo also ships `start.sh` (macOS Keychain or env, see below).

## API key

Copy `.env.example` to `.env` (**never commit `.env`**). Pick one provider:

### DashScope (default)

```bash
# VISION_MCP_PROVIDER=dashscope   # optional; this is the default
DASHSCOPE_API_KEY=sk-your-dashscope-key
# VISION_MCP_MODEL=qwen3-vl-flash
```

**macOS Keychain:** if `DASHSCOPE_API_KEY` is unset, `start.sh` runs `security find-generic-password -s dashscope-api-key -w`. Create that item first, or set `VISION_MCP_KEYCHAIN_SERVICE` to your own service name.

### Moonshot / Kimi

```bash
VISION_MCP_PROVIDER=moonshot
MOONSHOT_API_KEY=sk-your-key
VISION_MCP_MODEL=moonshot-v1-8k-vision-preview   # or kimi-for-coding (Coding Plan)
MOONSHOT_BASE_URL=https://api.moonshot.cn/v1     # Coding Plan: https://api.kimi.com/coding/v1
```

You can also set `VISION_MCP_API_KEY` instead of the provider-specific key. Key resolution order: `VISION_MCP_API_KEY` → `MOONSHOT_API_KEY` → `DASHSCOPE_API_KEY`.

## MCP client (stdio)

Any client that supports **stdio MCP** can launch this server with `command`, `cwd`, and optional `env`. Replace paths with your clone location.

**Python module (recommended with venv):**

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

**`start.sh` (Keychain / fixed cwd):**

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

Restart the host app after editing MCP config.

## Environment variables

| Variable | Description |
|----------|-------------|
| `VISION_MCP_PROVIDER` | `dashscope` (default) or `moonshot` / `kimi` |
| `VISION_MCP_API_KEY` | Optional generic API key (overrides provider-specific keys) |
| `VISION_MCP_MODEL` | DashScope default `qwen3-vl-flash`; Moonshot default `moonshot-v1-8k-vision-preview` |
| `VISION_MCP_BASE_URL` | Optional override for Moonshot OpenAI-compatible base URL |
| `DASHSCOPE_API_KEY` | DashScope API key |
| `DASHSCOPE_BASE_URL` | Default `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `MOONSHOT_API_KEY` | Moonshot / Kimi API key |
| `MOONSHOT_BASE_URL` | Default `https://api.moonshot.cn/v1` |
| `VISION_MCP_ALLOWED_DIRS` | Extra allowed directories (`:`-separated on POSIX; `$HOME` and system temp dir are always allowed) |
| `VISION_MCP_KEYCHAIN_SERVICE` | (macOS + `start.sh`) Keychain service name; default `dashscope-api-key` |

## Temporary OSS upload (DashScope only)

When `VISION_MCP_PROVIDER` is `dashscope`, large local images and `oss://` URLs can use DashScope temporary OSS. The client sets `X-DashScope-OssResourceResolve: enable` via OpenAI SDK `default_headers`.

On Moonshot/Kimi, images are sent as data URLs; `oss://` is not supported — use `file_path` or `base64` instead.

See: [Get temporary file URL](https://www.alibabacloud.com/help/en/model-studio/get-temporary-file-url)

## Output

Tool responses include `structuredContent` (`summary`, `structured`, `per_image`, `meta`, `usage`, etc.). The plain-text tool body is usually the `summary`.

## Documentation

- [Qwen VL OpenAI-compatible API](https://help.aliyun.com/zh/model-studio/developer-reference/qwen-vl-compatible-with-openai)
- [Moonshot Open Platform](https://platform.moonshot.cn/docs)

## Community & author

Questions, feedback, and discussion: **https://pjlab.top**

## Before you push to a public repo

- `.env` is gitignored — do not `git add .env`.
- Keep `.env.example` as placeholders only.
- Use `/path/to/...` in docs, not personal home paths.
- Keys are read from the environment / Keychain only; run `git diff` before publishing.

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file.
