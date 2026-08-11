"""Intent / profile / quality -> system prompt and DashScope extra_body."""

from __future__ import annotations

from typing import Any

INTENTS = frozenset({"describe", "ocr", "extract_structure", "compare", "reason", "other"})
PROFILES = frozenset({"general", "document", "chart", "ui", "education"})
QUALITIES = frozenset({"fast", "balanced", "high_detail"})

# intent -> default instruction when question is empty
DEFAULT_QUESTIONS: dict[str, str] = {
    "describe": "请详细描述这些图片的内容。",
    "ocr": "请识别并输出图中的文字内容。",
    "extract_structure": "请提取图中的结构化信息（如表格、键值对、段落层级）。",
    "compare": "请对比多张图片的相似点与差异。",
    "reason": "请根据图片内容进行推理作答（若是题目，请先提取题干与选项）。",
    "other": "请根据图片回答用户的问题。",
}

# (intent, profile) -> extra system hints (ZH)
PROFILE_HINTS: dict[tuple[str, str], str] = {
    ("describe", "general"): "关注主体对象、场景、色彩、构图、画面中的可读文字及其含义。",
    ("describe", "document"): "关注页面布局、标题、段落层级与可见文字概要（无需逐字 OCR，除非用户要求）。",
    ("describe", "chart"): "关注图表类型、坐标轴含义、刻度、图例、趋势与关键点。",
    ("describe", "ui"): "关注界面层级、控件类型、可操作元素、文案与可能的交互路径。",
    ("describe", "education"): "关注题目/图示/手写或印刷内容的关系，帮助学生理解画面信息。",
    ("ocr", "document"): "逐字识别，尽量保留原有的编号、项目符号与缩进层级；不确定处用占位说明。",
    ("ocr", "general"): "输出完整可读文本，并保持原有阅读顺序（自上而下、从左到右为主）。",
    ("ocr", "education"): "保留题号、选项标号（A/B/C…）及公式的大概形式（可用 LaTeX 或纯文本近似）。",
    ("extract_structure", "chart"): "提取标题、数据来源（如有）、轴标签、单位、图例与各系列的关键数据点。",
    ("extract_structure", "document"): "提取标题、章节、小节、列表与表格（用 rows/cols 描述表格）。",
    ("extract_structure", "ui"): "提取屏幕上的控件树或区域划分（顶部栏、侧栏、主内容区等）。",
    ("extract_structure", "general"): "提取关键实体、关系与任何表格化信息。",
    ("compare", "general"): "先逐张概述，再给出相似点与差异点列表。",
    ("compare", "document"): "对比版式、段落结构、差异段落或修订痕迹（若有）。",
    ("compare", "chart"): "对比坐标范围、单位、系列数量、趋势差异。",
    ("reason", "education"): "先抽取题干与选项，再分步推理；给出最终答案并标注不确定处。",
    ("reason", "general"): "基于可见证据分步推理，避免臆测画面外信息。",
    ("other", "general"): "严格依据图片可见内容回答；信息不足请明确说明。",
}

JSON_INSTRUCTION = """
你必须只输出一个合法 JSON 对象（不要加 Markdown 代码围栏），包含以下三个顶层键：
- "summary": 字符串，2～6 句中文总结。
- "structured": 对象，按任务类型填充（无相关字段则留空对象 {}）。常见字段：
  - ocr: "recognized_text"（字符串）
  - extract_structure: "tables"（数组）, "key_values"（对象或数组）
  - compare: "similarities"（数组）, "differences"（数组）
  - reason: "steps"（数组）, "answer"（字符串）
  - describe/other: 可选 "notes"（字符串或数组）
- "per_image": 数组，与你收到的图片顺序严格一一对应；每项：
  {"index": 整数, "label": 字符串或null, "brief": 字符串（该图简述，不超过100字）}
不要输出任何 JSON 以外的内容，不要在 JSON 前后加说明文字。
"""


def resolve_intent_profile_quality(
    intent: str | None,
    profile: str | None,
    quality: str | None,
) -> tuple[str, str, str]:
    i = (intent or "describe").strip()
    p = (profile or "general").strip()
    q = (quality or "balanced").strip()
    if i not in INTENTS:
        i = "other"
    if p not in PROFILES:
        p = "general"
    if q not in QUALITIES:
        q = "balanced"
    return i, p, q


def quality_extra_body(quality: str) -> dict[str, Any]:
    """Map quality to provider-specific request extras."""
    from vision_mcp.vision_client import uses_dashscope_oss

    if not uses_dashscope_oss():
        return {}
    if quality == "high_detail":
        return {"vl_high_resolution_images": True}
    if quality == "fast":
        # 约 1024×1024；在未开高分辨率时生效
        return {"vl_high_resolution_images": False, "max_pixels": 1024 * 1024}
    # balanced
    return {"vl_high_resolution_images": False}


def build_system_prompt(intent: str, profile: str) -> str:
    hint_key = (intent, profile)
    hint = PROFILE_HINTS.get(hint_key)
    if hint is None:
        # fallback: intent with general profile hint, else generic
        hint = PROFILE_HINTS.get((intent, "general"), PROFILE_HINTS[("other", "general")])

    task_line = (
        f"任务 intent={intent}，场景 profile={profile}。"
        f"请在遵守安全与合规的前提下完成视觉理解。"
    )
    return f"{task_line}\n{hint}\n{JSON_INSTRUCTION}"


def effective_question(question: str | None, intent: str) -> str:
    q = (question or "").strip()
    if q:
        return q
    return DEFAULT_QUESTIONS.get(intent, DEFAULT_QUESTIONS["other"])


def build_user_content(
    normalized_urls: list[tuple[int, str | None, str]],
    question: str,
) -> list[dict[str, Any]]:
    """Build multimodal user content: optional index labels, images, trailing text."""
    parts: list[dict[str, Any]] = []
    for idx, label, url in normalized_urls:
        label_txt = f"[图 {idx}]" + (f" ({label})" if label else "")
        parts.append({"type": "text", "text": label_txt})
        parts.append({"type": "image_url", "image_url": {"url": url}})
    parts.append(
        {
            "type": "text",
            "text": "用户指令与问题如下：\n" + question,
        }
    )
    return parts


def build_messages(
    intent: str,
    profile: str,
    quality: str,
    question: str,
    normalized_urls: list[tuple[int, str | None, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sys_prompt = build_system_prompt(intent, profile)
    extra = quality_extra_body(quality)
    user_content = build_user_content(normalized_urls, effective_question(question, intent))
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_content},
    ]
    return messages, extra
