"""stdio MCP server: Qwen VL image analysis via DashScope."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from vision_mcp.clipboard_io import ClipboardError, capture_clipboard_image
from vision_mcp.image_utils import normalize_all
from vision_mcp.profiles import build_messages, resolve_intent_profile_quality
from vision_mcp.vision_client import analyze as vl_analyze
from vision_mcp.vision_client import default_model, load_env, provider, resolve_api_key

LOGGER = logging.getLogger("vision_mcp")

server = Server(
    name="vision-mcp",
    version="0.1.0",
    instructions=(
        "为仅支持文本的模型提供看图能力：默认 DashScope 通义 VL；"
        "设置 VISION_MCP_PROVIDER=moonshot 时使用 Kimi/Moonshot 视觉模型。"
        "vision.analyze：多图；本地路径优先于 URL 再 base64；intent/profile/quality。"
        "vision.clipboard_image（仅 macOS）：剪贴板图片写入 $HOME/.vision_mcp/clipboard/ 并返回路径。"
        "本地 file_path 默认限制在 $HOME 及 VISION_MCP_ALLOWED_DIRS。"
    ),
)


def _tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "images": {
                "type": "array",
                "minItems": 1,
                "maxItems": 16,
                "description": "图片列表；每张可提供 url、base64、file_path；"
                "同时存在时按 file_path > url > base64 取值。",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "https / http / oss://"},
                        "base64": {"type": "string"},
                        "mime_type": {"type": "string"},
                        "file_path": {"type": "string"},
                        "label": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "question": {"type": "string", "description": "用户问题或补充说明，可空"},
            "intent": {
                "type": "string",
                "enum": ["describe", "ocr", "extract_structure", "compare", "reason", "other"],
            },
            "profile": {
                "type": "string",
                "enum": ["general", "document", "chart", "ui", "education"],
            },
            "quality": {
                "type": "string",
                "enum": ["fast", "balanced", "high_detail"],
            },
        },
        "required": ["images"],
        "additionalProperties": False,
    }


def _clipboard_tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "save": {
                "type": "boolean",
                "description": "是否写入本机 $HOME/.vision_mcp/clipboard/（默认真）",
                "default": True,
            },
            "filename_prefix": {
                "type": "string",
                "description": "保存文件名前缀，默认 clipboard",
            },
            "include_base64": {
                "type": "boolean",
                "description": "是否在结果中包含 base64（大图会占内存，默认否）",
                "default": False,
            },
        },
        "additionalProperties": False,
    }


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="vision.analyze",
            description=(
                "调用通义千问视觉模型理解与提取图片内容。"
                "支持单图或多图（最多16张）；来源可为公网/oss URL、base64+mime_type、本地 file_path；"
                "若同时提供多种，优先本地路径，其次 URL，最后 base64。"
                "intent：describe/ocr/extract_structure/compare/reason/other；"
                "profile：general/document/chart/ui/education；"
                "quality：fast/balanced/high_detail。"
            ),
            inputSchema=_tool_schema(),
        ),
        Tool(
            name="vision.clipboard_image",
            description=(
                "（macOS）从系统剪贴板读取一张图片，可选保存到用户目录并返回路径。"
                "典型流程：截图或复制图片后调用本工具，再用 vision.analyze 的 file_path 分析。"
                "非 macOS 会报错；未复制图片时会提示剪贴板无图。"
            ),
            inputSchema=_clipboard_tool_schema(),
        ),
    ]


def extract_json_object(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```\s*$", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = json.loads(raw[start : end + 1])
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _analyze_sync(payload: dict[str, Any]) -> dict[str, Any]:
    """Runs in worker thread."""
    load_env()
    api_key = resolve_api_key()
    model = default_model()

    images = payload.get("images") or []
    if not isinstance(images, list):
        raise ValueError("images 必须为数组")

    question = str(payload.get("question") or "")
    intent, profile, quality = resolve_intent_profile_quality(
        payload.get("intent"),
        payload.get("profile"),
        payload.get("quality"),
    )

    norm = normalize_all(images, api_key=api_key or None, model_name=model)

    base_per_image: list[dict[str, Any]] = []
    urls_for_api: list[tuple[int, str | None, str]] = []
    for n in norm:
        entry = {
            "index": n.index,
            "label": n.label,
            "brief": None,
            "error": n.error,
        }
        base_per_image.append(entry)
        if n.error is None and n.image_url:
            urls_for_api.append((n.index, n.label, n.image_url))

    partial_failure = any(n.error for n in norm)

    if not urls_for_api:
        meta = {
            "model": model,
            "profile": profile,
            "quality": quality,
            "intent": intent,
            "partial_failure": True,
        }
        return {
            "summary": "所有图片均无法用于模型调用（请检查 URL、权限或路径白名单）。",
            "structured": {},
            "per_image": sorted(base_per_image, key=lambda x: x["index"]),
            "meta": meta,
            "usage": {},
        }

    messages, extra_body = build_messages(
        intent, profile, quality, question, urls_for_api
    )

    try:
        raw_text, usage = vl_analyze(messages, extra_body, model=model)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("VL API 调用失败: %s", exc)
        return {
            "summary": f"视觉模型调用失败: {exc}",
            "structured": {},
            "per_image": sorted(base_per_image, key=lambda x: x["index"]),
            "meta": {
                "model": model,
                "profile": profile,
                "quality": quality,
                "intent": intent,
                "partial_failure": partial_failure,
                "api_error": str(exc)[:500],
            },
            "usage": {},
        }

    parsed = extract_json_object(raw_text)

    if parsed is None:
        out = {
            "summary": raw_text.strip()[:8000] or "模型返回为空",
            "structured": {"raw_response": raw_text},
            "per_image": sorted(base_per_image, key=lambda x: x["index"]),
            "meta": {
                "model": model,
                "profile": profile,
                "quality": quality,
                "intent": intent,
                "partial_failure": partial_failure,
                "parse_error": "response_not_json",
            },
            "usage": usage,
        }
        return out

    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = raw_text.strip()[:2000]

    structured = parsed.get("structured")
    if not isinstance(structured, dict):
        structured = {}

    model_per = parsed.get("per_image")
    idx_to_model: dict[int, dict[str, Any]] = {}
    if isinstance(model_per, list):
        for item in model_per:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            idx_to_model[idx] = item

    for row in base_per_image:
        if row.get("error"):
            continue
        idx = row["index"]
        mrow = idx_to_model.get(idx)
        if isinstance(mrow, dict):
            brief = mrow.get("brief")
            if isinstance(brief, str) and brief.strip():
                row["brief"] = brief.strip()

    for row in base_per_image:
        if row.get("error"):
            continue
        if row.get("brief") is None:
            row["brief"] = summary.split("。")[0][:200] if summary else ""

    out_meta = {
        "model": model,
        "profile": profile,
        "quality": quality,
        "intent": intent,
        "partial_failure": partial_failure,
    }

    return {
        "summary": summary.strip(),
        "structured": structured,
        "per_image": sorted(base_per_image, key=lambda x: x["index"]),
        "meta": out_meta,
        "usage": usage,
    }


def _clipboard_sync(payload: dict[str, Any]) -> dict[str, Any]:
    save = payload.get("save")
    if save is None:
        save = True
    include_b64 = payload.get("include_base64")
    if include_b64 is None:
        include_b64 = False
    prefix_raw = payload.get("filename_prefix")
    prefix = str(prefix_raw).strip() if prefix_raw is not None else "clipboard"
    if prefix == "":
        prefix = "clipboard"

    return capture_clipboard_image(
        save=bool(save),
        prefix=prefix,
        include_base64=bool(include_b64),
    )


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> CallToolResult | list[TextContent]:
    args = arguments or {}

    if name == "vision.clipboard_image":
        try:
            result = await asyncio.to_thread(_clipboard_sync, dict(args))
        except ClipboardError as exc:
            return CallToolResult(
                content=[TextContent(type="text", text=str(exc))],
                isError=True,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("vision.clipboard_image failed")
            return CallToolResult(
                content=[TextContent(type="text", text=str(exc))],
                isError=True,
            )
        path_line = ""
        if isinstance(result.get("saved_path"), str):
            path_line = result["saved_path"]
        text_out = (
            f"已保存剪贴板图片: {path_line}\n"
            f"mime={result.get('mime_type')} size={result.get('size_bytes')} bytes"
            if path_line
            else json.dumps(result, ensure_ascii=False)
        )
        return CallToolResult(
            content=[TextContent(type="text", text=text_out)],
            structuredContent=result,
            isError=False,
        )

    if name != "vision.analyze":
        return CallToolResult(
            content=[TextContent(type="text", text=f"未知工具: {name}")],
            isError=True,
        )

    try:
        result = await asyncio.to_thread(_analyze_sync, dict(args))
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("vision.analyze failed")
        return CallToolResult(
            content=[TextContent(type="text", text=str(exc))],
            isError=True,
        )

    summary = result.get("summary", "")
    text_out = summary if isinstance(summary, str) else json.dumps(result, ensure_ascii=False)
    return CallToolResult(
        content=[TextContent(type="text", text=text_out)],
        structuredContent=result,
        isError=False,
    )


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    load_env()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(notification_options=NotificationOptions()),
            raise_exceptions=False,
        )


def run_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run_sync()
