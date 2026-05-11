"""OpenAI-compatible client for DashScope Qwen VL."""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

_DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_client: OpenAI | None = None

LOGGER = logging.getLogger("vision_mcp.client")


def load_env() -> None:
    """Load .env from cwd (MCP cwd should point to project root)."""
    load_dotenv(override=False)


def default_model() -> str:
    return os.environ.get("VISION_MCP_MODEL", "qwen3-vl-flash").strip() or "qwen3-vl-flash"


def get_client() -> OpenAI:
    """Return a module-level cached OpenAI client (created once per process)."""
    global _client
    load_env()
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "未设置 DASHSCOPE_API_KEY。请在 .env 中配置或使用 start.sh 从钥匙串注入。"
        )
    base_url = os.environ.get("DASHSCOPE_BASE_URL", _DEFAULT_BASE).strip() or _DEFAULT_BASE
    if _client is None:
        _client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={"X-DashScope-OssResourceResolve": "enable"},
        )
    return _client


def analyze(
    messages: list[dict[str, Any]],
    extra_body: dict[str, Any],
    *,
    model: str | None = None,
) -> tuple[str, dict[str, int | None]]:
    """Non-stream chat completion; returns assistant text + usage dict."""
    client = get_client()
    m = model or default_model()

    kwargs: dict[str, Any] = {
        "model": m,
        "messages": messages,
        "stream": False,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body

    completion = client.chat.completions.create(**kwargs)

    if not completion.choices:
        raise RuntimeError(
            f"DashScope 返回了空的 choices 列表（model={m}）。"
            "请检查 DASHSCOPE_API_KEY 是否有效、模型名是否正确。"
        )

    msg = completion.choices[0].message
    text = getattr(msg, "content", None) or ""
    usage_raw = getattr(completion, "usage", None)
    usage: dict[str, int | None] = {}
    if usage_raw:
        usage = {
            "prompt_tokens": getattr(usage_raw, "prompt_tokens", None),
            "completion_tokens": getattr(usage_raw, "completion_tokens", None),
            "total_tokens": getattr(usage_raw, "total_tokens", None),
        }
    return text, usage
