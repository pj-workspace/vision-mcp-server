"""OpenAI-compatible client for DashScope Qwen VL or Moonshot Kimi vision."""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

_DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_MOONSHOT_BASE = "https://api.moonshot.cn/v1"
_client: OpenAI | None = None

LOGGER = logging.getLogger("vision_mcp.client")


def load_env() -> None:
    """Load .env from cwd (MCP cwd should point to project root)."""
    load_dotenv(override=False)


def provider() -> str:
    return (os.environ.get("VISION_MCP_PROVIDER") or "dashscope").strip().lower()


def uses_dashscope_oss() -> bool:
    return provider() == "dashscope"


def default_model() -> str:
    if provider() in {"moonshot", "kimi"}:
        return (
            os.environ.get("VISION_MCP_MODEL", "moonshot-v1-8k-vision-preview").strip()
            or "moonshot-v1-8k-vision-preview"
        )
    return os.environ.get("VISION_MCP_MODEL", "qwen3-vl-flash").strip() or "qwen3-vl-flash"


def resolve_api_key() -> str:
    for env_name in ("VISION_MCP_API_KEY", "MOONSHOT_API_KEY", "DASHSCOPE_API_KEY"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    if provider() in {"moonshot", "kimi"}:
        raise ValueError(
            "未设置 Moonshot API Key。请在 .env 中配置 MOONSHOT_API_KEY 或 VISION_MCP_API_KEY。"
        )
    raise ValueError(
        "未设置 DASHSCOPE_API_KEY。请在 .env 中配置或使用 start.sh 从钥匙串注入。"
    )


def resolve_base_url() -> str:
    if provider() in {"moonshot", "kimi"}:
        return (
            os.environ.get("VISION_MCP_BASE_URL")
            or os.environ.get("MOONSHOT_BASE_URL")
            or _MOONSHOT_BASE
        ).strip() or _MOONSHOT_BASE
    return os.environ.get("DASHSCOPE_BASE_URL", _DASHSCOPE_BASE).strip() or _DASHSCOPE_BASE


def get_client() -> OpenAI:
    """Return a module-level cached OpenAI client (created once per process)."""
    global _client
    load_env()
    api_key = resolve_api_key()
    base_url = resolve_base_url()
    if _client is None:
        headers: dict[str, str] = {}
        if uses_dashscope_oss():
            headers["X-DashScope-OssResourceResolve"] = "enable"
        _client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=headers or None,
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
        provider_name = provider()
        raise RuntimeError(
            f"视觉 API 返回了空的 choices 列表（provider={provider_name}, model={m}）。"
            "请检查 API Key 是否有效、模型名是否正确。"
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
