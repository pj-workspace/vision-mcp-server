"""Normalize image inputs to DashScope-compatible image URLs."""

from __future__ import annotations

import base64
import io
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from vision_mcp.oss_upload import OssUploadError, upload_file_and_get_url
from vision_mcp.vision_client import uses_dashscope_oss

LOGGER = logging.getLogger("vision_mcp.image_utils")

# 超过此字节数优先走临时 OSS，避免巨大 base64
BASE64_SIZE_THRESHOLD = 4 * 1024 * 1024

# 超过 8K（7680x4320）则缩放到 4K 以内
MAX_WIDTH_TRIGGER = 7680
MAX_HEIGHT_TRIGGER = 4320
MAX_WIDTH_TARGET = 3840
MAX_HEIGHT_TARGET = 2160

# 允许 PIL 打开超大图以便我们自行缩放，不依赖其内置炸弹检测
Image.MAX_IMAGE_PIXELS = None


@dataclass
class NormalizedImage:
    index: int
    label: str | None
    image_url: str | None
    error: str | None


def _allowed_dirs() -> list[Path]:
    home = Path.home().resolve()
    raw = os.environ.get("VISION_MCP_ALLOWED_DIRS", "").strip()
    dirs: list[Path] = [home]
    # 系统临时目录（macOS /var/folders/.../T，Linux /tmp）默认放行，
    # 以便直接分析剪贴板/截图落盘的临时文件，无需手动复制到 $HOME。
    tmp = Path(tempfile.gettempdir()).resolve()
    if tmp not in dirs:
        dirs.append(tmp)
    if raw:
        for part in raw.split(os.pathsep if os.pathsep in raw else ":"):
            p = part.strip()
            if p:
                dirs.append(Path(p).expanduser().resolve())
    return dirs


def _is_path_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in _allowed_dirs():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _maybe_resize_image_bytes(data: bytes) -> bytes:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("图片解码失败，跳过缩图（将原样传给 API）: %s", exc)
        return data
    w, h = img.size
    if w <= MAX_WIDTH_TRIGGER and h <= MAX_HEIGHT_TRIGGER:
        return data
    scale = min(MAX_WIDTH_TARGET / w, MAX_HEIGHT_TARGET / h, 1.0)
    if scale >= 1.0:
        return data
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    LOGGER.info("缩图：%dx%d -> %dx%d", w, h, new_w, new_h)
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    fmt = img.format or "PNG"
    buf = io.BytesIO()
    if fmt.upper() in {"JPEG", "JPG"}:
        resized = resized.convert("RGB")
        resized.save(buf, format="JPEG", quality=90)
    else:
        resized.save(buf, format="PNG")
    return buf.getvalue()


def _encode_data_url(data: bytes, mime_type: str) -> str:
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


def _fetch_url_as_data_url(url: str) -> str:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if not content_type.startswith("image/"):
        content_type = "image/jpeg"
    data = _maybe_resize_image_bytes(response.content)
    return _encode_data_url(data, content_type)


def _normalize_from_path(
    index: int,
    label: str | None,
    file_path: Any,
    *,
    api_key: str | None,
    model_name: str,
) -> NormalizedImage:
    path = Path(str(file_path).strip()).expanduser()
    if not path.is_file():
        return NormalizedImage(index, label, None, f"文件不存在: {path}")
    if not _is_path_allowed(path):
        return NormalizedImage(
            index,
            label,
            None,
            f"路径不在允许目录内（当前限制为 $HOME 及 VISION_MCP_ALLOWED_DIRS）: {path}",
        )
    try:
        data = path.read_bytes()
    except OSError as exc:
        return NormalizedImage(index, label, None, f"读取文件失败: {exc}")

    data = _maybe_resize_image_bytes(data)
    size = len(data)
    if size <= BASE64_SIZE_THRESHOLD or not uses_dashscope_oss():
        suffix = path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".heic": "image/heic",
        }
        mt = mime_map.get(suffix, "application/octet-stream")
        return NormalizedImage(index, label, _encode_data_url(data, mt), None)

    if not api_key:
        return NormalizedImage(
            index,
            label,
            None,
            "文件超过 4MB 且未配置 API Key，无法走临时上传",
        )
    suffix = path.suffix.lower() or ".jpg"
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"vision_mcp_{os.getpid()}_{index}{suffix}"
    try:
        tmp.write_bytes(data)
        oss_url = upload_file_and_get_url(api_key, model_name, tmp)
    except (OssUploadError, OSError) as exc:
        return NormalizedImage(index, label, None, f"临时上传失败: {exc}")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return NormalizedImage(index, label, oss_url, None)


def _normalize_from_url(
    index: int,
    label: str | None,
    url: Any,
) -> NormalizedImage:
    u = str(url).strip()
    if u.startswith(("https://", "http://")):
        if uses_dashscope_oss():
            return NormalizedImage(index, label, u, None)
        try:
            return NormalizedImage(index, label, _fetch_url_as_data_url(u), None)
        except Exception as exc:  # noqa: BLE001
            return NormalizedImage(index, label, None, f"下载图片失败: {exc}")
    if u.startswith("oss://"):
        if uses_dashscope_oss():
            return NormalizedImage(index, label, u, None)
        return NormalizedImage(
            index,
            label,
            None,
            "Moonshot/Kimi 不支持 oss://，请改用本地 file_path 或 base64",
        )
    return NormalizedImage(index, label, None, f"不支持的 url 协议: {u[:80]}")


def _normalize_from_base64(
    index: int,
    label: str | None,
    b64: Any,
    mime: Any,
    *,
    api_key: str | None,
    model_name: str,
) -> NormalizedImage:
    if not mime or not str(mime).strip():
        return NormalizedImage(index, label, None, "使用 base64 时必须提供 mime_type")
    try:
        raw = base64.b64decode(str(b64).strip(), validate=False)
    except Exception as exc:  # noqa: BLE001
        return NormalizedImage(index, label, None, f"base64 解码失败: {exc}")
    raw = _maybe_resize_image_bytes(raw)
    mime_clean = str(mime).strip()
    if len(raw) > BASE64_SIZE_THRESHOLD and uses_dashscope_oss():
        if not api_key:
            return NormalizedImage(
                index,
                label,
                None,
                "图片过大且未配置 API Key，无法走临时上传；请缩小图片或使用 URL",
            )
        suffix = ".jpg"
        if "png" in mime_clean.lower():
            suffix = ".png"
        elif "webp" in mime_clean.lower():
            suffix = ".webp"
        tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"vision_mcp_{os.getpid()}_{index}{suffix}"
        try:
            tmp.write_bytes(raw)
            oss_url = upload_file_and_get_url(api_key, model_name, tmp)
        except (OssUploadError, OSError) as exc:
            return NormalizedImage(index, label, None, f"大文件上传失败: {exc}")
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        return NormalizedImage(index, label, oss_url, None)
    return NormalizedImage(
        index,
        label,
        _encode_data_url(raw, mime_clean),
        None,
    )


def normalize_one(
    index: int,
    item: dict[str, Any],
    *,
    api_key: str | None,
    model_name: str,
) -> NormalizedImage:
    label_raw = item.get("label")
    label = str(label_raw).strip() if label_raw is not None else None
    if label == "":
        label = None

    url = item.get("url")
    b64 = item.get("base64")
    mime = item.get("mime_type")
    file_path = item.get("file_path")

    has_url = url is not None and str(url).strip() != ""
    has_b64 = b64 is not None and str(b64).strip() != ""
    has_path = file_path is not None and str(file_path).strip() != ""

    if not (has_url or has_b64 or has_path):
        return NormalizedImage(index, label, None, "缺少图片来源：请提供 url、base64 或 file_path")

    attempts: list[tuple[str, NormalizedImage]] = []
    if has_path:
        attempts.append(
            (
                "file_path",
                _normalize_from_path(
                    index, label, file_path, api_key=api_key, model_name=model_name
                ),
            )
        )
    if has_url:
        attempts.append(("url", _normalize_from_url(index, label, url)))
    if has_b64:
        attempts.append(
            (
                "base64",
                _normalize_from_base64(
                    index, label, b64, mime, api_key=api_key, model_name=model_name
                ),
            )
        )

    errs: list[str] = []
    for name, result in attempts:
        if result.error is None:
            if len(attempts) > 1:
                LOGGER.info(
                    "多来源时选用 %s（优先级：file_path > url > base64）",
                    name,
                )
            return result
        errs.append(f"{name}: {result.error}")

    msg = "；".join(errs)
    if len(msg) > 1200:
        msg = msg[:1200] + "…"
    return NormalizedImage(index, label, None, msg or "所有图片来源均不可用")


def normalize_all(
    images: list[dict[str, Any]],
    *,
    api_key: str | None,
    model_name: str,
) -> list[NormalizedImage]:
    return [
        normalize_one(i, item, api_key=api_key, model_name=model_name)
        for i, item in enumerate(images)
    ]
