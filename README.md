# vision-mcp

An MCP (stdio) server for **text-only** large language models: it calls Alibaba Cloud **DashScope Qwen VL** (default `qwen3-vl-flash`) to turn images into **structured text**, so your main model can keep reasoning without native vision support.

Use it when the host model cannot accept images, or pasted images never reach the model context—run vision here and feed the text back.

**Languages:** [中文说明](README.zh-CN.md)

## Features

- **vision.analyze** — vision understanding with intent, profile, and quality presets
- **vision.clipboard_image** (**macOS only**) — read image from clipboard, save under `$HOME/.vision_mcp/clipboard/`, return paths for **vision.analyze**
- **Multi-image**: 1–16 per request; each item may include `url`, `base64` + `mime_type`, or `file_path` — **if several are set, priority is `file_path` → URL → base64**
- **Intents**: `describe` | `ocr` | `extract_structure` | `compare` | `reason` | `other`
- **Profiles**: `general` | `document` | `chart` | `ui` | `education`
- **Quality**: `fast` | `balanced` | `high_detail` (maps to DashScope `extra_body`)
- **Large / big local files**: optional temporary OSS upload (needs `DASHSCOPE_API_KEY`; upload `model` must match the call)

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

1. **`.env`**: copy `.env.example` to `.env` and set `DASHSCOPE_API_KEY` (**never commit `.env`**).
2. **macOS Keychain**: if `DASHSCOPE_API_KEY` is unset, `start.sh` runs `security find-generic-password -s dashscope-api-key -w`. Create that item first, or set `VISION_MCP_KEYCHAIN_SERVICE` to your own service name.

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
| `VISION_MCP_MODEL` | Default `qwen3-vl-flash` |
| `DASHSCOPE_BASE_URL` | Default `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `VISION_MCP_ALLOWED_DIRS` | Extra allowed directories (`:`-separated on POSIX; `$HOME` is always allowed) |
| `VISION_MCP_KEYCHAIN_SERVICE` | (macOS + `start.sh`) Keychain service name; default `dashscope-api-key` |

## Temporary OSS upload

Same as DashScope docs: for `oss://` resources, use header `X-DashScope-OssResourceResolve: enable` (already set via OpenAI SDK `default_headers`).

See: [Get temporary file URL](https://www.alibabacloud.com/help/en/model-studio/get-temporary-file-url)

## Output

Tool responses include `structuredContent` (`summary`, `structured`, `per_image`, `meta`, `usage`, etc.). The plain-text tool body is usually the `summary`.

## Documentation

- [Qwen VL OpenAI-compatible API](https://help.aliyun.com/zh/model-studio/developer-reference/qwen-vl-compatible-with-openai)

## Community & author

Questions, feedback, and discussion: **https://pjlab.top**

## Before you push to a public repo

- `.env` is gitignored — do not `git add .env`.
- Keep `.env.example` as placeholders only.
- Use `/path/to/...` in docs, not personal home paths.
- Keys are read from the environment / Keychain only; run `git diff` before publishing.

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file.
