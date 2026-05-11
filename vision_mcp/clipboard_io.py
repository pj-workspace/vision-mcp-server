"""Read image data from the system clipboard (macOS)."""

from __future__ import annotations

import base64
import io
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image

LOGGER = logging.getLogger("vision_mcp.clipboard_io")

# 剪贴板图片落盘目录（位于 $HOME 下，与 image_utils 白名单一致）
CLIPBOARD_SUBDIR = ".vision_mcp/clipboard"


class ClipboardError(RuntimeError):
    """剪贴板无法读出图片时抛出。"""


def _darwin_types() -> list[tuple[str, str]]:
    """(NSPasteboard UTI, MIME) 按优先级尝试。"""
    return [
        ("public.png", "image/png"),
        ("public.jpeg", "image/jpeg"),
        ("public.jpg", "image/jpeg"),
        ("public.tiff", "image/tiff"),
        ("com.compuserve.gif", "image/gif"),
        ("public.webp", "image/webp"),
    ]


def read_clipboard_image_bytes() -> tuple[bytes, str]:
    """
    从剪贴板读取一张图片，返回 (bytes, mime_type)。
    在 macOS 下使用 NSPasteboard；其它平台暂不支持。
    """
    if sys.platform == "darwin":
        return _read_clipboard_darwin()
    if sys.platform == "win32":
        raise ClipboardError(
            "当前平台为 Windows：暂不支持剪贴板图片，请使用 file_path 或 base64。"
        )
    raise ClipboardError(
        "当前为非 macOS 系统：剪贴板读图未实现；请使用 file_path、base64 或 URL。"
    )


def _read_clipboard_darwin() -> tuple[bytes, str]:
    try:
        from AppKit import NSPasteboard  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ClipboardError(
            "无法在 macOS 上导入 AppKit（请安装：pip install 'pyobjc-framework-Cocoa'）"
        ) from exc

    pb = NSPasteboard.generalPasteboard()
    for uti, mime in _darwin_types():
        data = pb.dataForType_(uti)
        if not data:
            continue
        raw = bytes(data)
        if len(raw) == 0:
            continue
        if uti == "public.tiff":
            raw, mime = _tiff_bytes_to_png_bytes(raw)
        return raw, mime

    raise ClipboardError("剪贴板中没有可用的图片（请复制或截图后再试）。")


def _tiff_bytes_to_png_bytes(tiff: bytes) -> tuple[bytes, str]:
    """将 TIFF 转为 PNG 字节，便于后续与 mime 一致。"""
    try:
        img = Image.open(io.BytesIO(tiff))
        img.load()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), "image/png"
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("TIFF 转 PNG 失败，原样返回 TIFF: %s", exc)
        return tiff, "image/tiff"


def default_save_dir() -> Path:
    return Path.home() / CLIPBOARD_SUBDIR


def _extension_for_mime(mime: str) -> str:
    m = mime.lower()
    if "jpeg" in m or m.endswith("/jpg"):
        return ".jpg"
    if "png" in m:
        return ".png"
    if "gif" in m:
        return ".gif"
    if "webp" in m:
        return ".webp"
    if "tiff" in m:
        return ".tiff"
    return ".bin"


def capture_clipboard_image(
    *,
    save: bool = True,
    prefix: str = "clipboard",
    include_base64: bool = False,
) -> dict[str, Any]:
    """
    读取剪贴板一张图；可选写入 $HOME/.vision_mcp/clipboard/ 与/或 返回 base64。
    """
    if not save and not include_base64:
        raise ClipboardError("请将 save 或 include_base64 至少其一设为 true")

    raw, mime = read_clipboard_image_bytes()
    out: dict[str, Any] = {
        "mime_type": mime,
        "size_bytes": len(raw),
    }
    if save:
        out_dir = default_save_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        ext = _extension_for_mime(mime)
        name = f"{prefix}_{int(time.time() * 1000)}_{os.getpid()}{ext}"
        path = out_dir / name
        path.write_bytes(raw)
        resolved = str(path.resolve())
        out["saved_path"] = resolved
        out["paths"] = [resolved]
    if include_base64:
        out["base64"] = base64.standard_b64encode(raw).decode("ascii")
    return out
