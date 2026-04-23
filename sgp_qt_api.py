"""LLM Vision API helpers for Study Game Pro (Qt).

Supports OpenAI-compatible vision APIs (DeepSeek, OpenAI, etc.).
No Qt imports — pure logic so it can be tested independently.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import ssl
import urllib.request
from typing import Any

SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
SUPPORTED_PDF_EXTS = {".pdf"}
MAX_IMAGE_SIZE = 20 * 1024 * 1024
MAX_PDF_PAGES = 20

STEP_READ_FILE = 0
STEP_PREPARE_IMAGE = 1
STEP_SEND_REQUEST = 2
STEP_AI_PROCESSING = 3
STEP_PARSE_RESULT = 4
STEP_TOTAL = 5


class ApiError(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


def is_api_configured() -> bool:
    from sgp_qt_core import app_config
    return bool(app_config.get("llm_api_key", "").strip())


def get_api_config() -> dict[str, str]:
    from sgp_qt_core import app_config
    return {
        "api_key": str(app_config.get("llm_api_key", "") or "").strip(),
        "base_url": str(app_config.get("llm_api_base_url", "https://api.deepseek.com") or "").strip(),
        "model": str(app_config.get("llm_api_model", "deepseek-chat") or "").strip(),
    }


def classify_file(file_path: str) -> str:
    ext = _get_ext(file_path)
    if ext in SUPPORTED_IMAGE_EXTS:
        return "image"
    if ext in SUPPORTED_PDF_EXTS:
        return "pdf"
    if ext == ".json":
        return "json"
    return "unsupported"


def _get_ext(path: str) -> str:
    dot = path.rfind(".")
    return path[dot:].lower() if dot >= 0 else ""


def image_to_base64(file_path: str) -> tuple[str, str]:
    ext = _get_ext(file_path)
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    mime = mime_map.get(ext, "image/jpeg")
    with open(file_path, "rb") as f:
        data = f.read()
    if len(data) > MAX_IMAGE_SIZE:
        raise ApiError(f"图片超过 20MB 限制（当前 {len(data) / 1024 / 1024:.1f}MB），请压缩后重试")
    return base64.b64encode(data).decode("utf-8"), mime


def pdf_to_images_base64(file_path: str) -> list[tuple[str, str]]:
    try:
        import fitz
    except ImportError:
        raise ApiError(
            "缺少 PyMuPDF 库，无法解析 PDF",
            "请在终端运行: pip install PyMuPDF",
        )

    doc = None
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise ApiError("PDF 文件无法读取，可能已加密或损坏", str(e))

    if doc.is_encrypted:
        doc.close()
        raise ApiError("PDF 文件已加密，无法读取内容")

    total_pages = len(doc)
    if total_pages > MAX_PDF_PAGES:
        doc.close()
        raise ApiError(
            f"PDF 超过 {MAX_PDF_PAGES} 页（当前 {total_pages} 页），目录通常不需要这么多页，请确认是否正确"
        )

    results: list[tuple[str, str]] = []
    page_errors: list[int] = []
    for i in range(total_pages):
        try:
            page = doc[i]
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            if len(img_bytes) > MAX_IMAGE_SIZE:
                pix = page.get_pixmap(dpi=120)
                img_bytes = pix.tobytes("png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            results.append((b64, "image/png"))
        except Exception:
            page_errors.append(i + 1)

    doc.close()

    if not results and page_errors:
        raise ApiError(f"PDF 全部 {total_pages} 页均渲染失败，可能文件损坏或格式不支持")
    if page_errors:
        pass

    if not results:
        raise ApiError("PDF 中未找到可渲染的页面")

    return results


def pdf_to_base64(file_path: str) -> tuple[str, str]:
    with open(file_path, "rb") as f:
        raw = f.read()
    if len(raw) > 50 * 1024 * 1024:
        raise ApiError(f"PDF 文件过大（{len(raw) / 1024 / 1024:.1f}MB），请控制在 50MB 以内")
    return base64.b64encode(raw).decode("utf-8"), "application/pdf"


def prepare_images(file_paths: list[str], progress_callback: Any | None = None) -> list[tuple[str, str]]:
    all_images: list[tuple[str, str]] = []
    if progress_callback:
        progress_callback(STEP_READ_FILE, f"正在读取 {len(file_paths)} 个文件...")
    for fp in file_paths:
        kind = classify_file(fp)
        if kind == "image":
            b64, mime = image_to_base64(fp)
            all_images.append((b64, mime))
        elif kind == "pdf":
            if progress_callback:
                progress_callback(STEP_PREPARE_IMAGE, f"正在转换 PDF: {os.path.basename(fp)}")
            all_images.extend(pdf_to_images_base64(fp))
        elif kind == "json":
            raise ApiError('这是 JSON 文件，请使用「选择 JSON 文件导入」功能')
        else:
            ext = _get_ext(fp)
            raise ApiError(f"不支持的文件格式 ({ext})，请使用 JPG/PNG/PDF 文件")
    return all_images


def call_vision_api(
    images: list[tuple[str, str]],
    prompt: str,
    progress_callback: Any | None = None,
) -> str:
    cfg = get_api_config()
    if not cfg["api_key"]:
        raise ApiError("API Key 未配置", "请在设置中填写 API Key 后重试")

    base_url = cfg["base_url"].rstrip("/")
    url = f"{base_url}/chat/completions"

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for b64_data, mime in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64_data}"},
        })

    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 8192,
        "temperature": 0.1,
        "stream": True,
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }

    if progress_callback:
        progress_callback(STEP_SEND_REQUEST, "正在发送请求...")

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    max_retries = 2
    timeout = 600
    full_text = ""
    for attempt in range(max_retries + 1):
        try:
            if progress_callback:
                if attempt > 0:
                    progress_callback(STEP_AI_PROCESSING, f"AI 正在识别... (第 {attempt + 1} 次)")
                else:
                    progress_callback(STEP_AI_PROCESSING, "AI 正在识别...")
            context = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
                buffer = ""
                for raw_chunk in resp:
                    chunk = raw_chunk.decode("utf-8", errors="replace")
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(data_str)
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                            content_piece = delta.get("content", "")
                            if content_piece:
                                full_text += content_piece
                                if progress_callback:
                                    progress_callback(STEP_AI_PROCESSING, full_text)
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
            break
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if e.code == 401:
                raise ApiError("API Key 验证失败，请检查是否正确或已过期", error_body)
            if e.code == 402 or e.code == 429:
                raise ApiError("API 余额不足或请求过于频繁，请稍后重试或前往平台充值", error_body)
            if e.code == 400:
                raise ApiError("请求格式错误，请检查图片是否有效", error_body)
            raise ApiError(f"API 请求失败 (HTTP {e.code})", error_body)
        except Exception as e:
            err_str = str(e).lower()
            if "timed out" in err_str or "timeout" in err_str:
                if attempt < max_retries:
                    import time as _time
                    _time.sleep(2)
                    continue
                raise ApiError(
                    f"请求超时（已重试 {max_retries} 次），可能原因：\n"
                    "1. 网络连接不稳定\n"
                    "2. 图片过大（建议压缩到 5MB 以内）\n"
                    "3. API 服务端繁忙\n"
                    "建议稍后重试或换用更小的图片",
                )
            if isinstance(e, urllib.error.URLError):
                raise ApiError(f"网络连接失败，请检查网络设置: {e.reason}")
            raise ApiError(f"请求异常: {e}")

    if not full_text:
        raise ApiError("API 返回内容为空，请重试")

    return full_text


def extract_json_from_response(text: str) -> list[Any]:
    cleaned = text.strip()

    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(1).strip()

    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start >= 0 and end > start:
        cleaned = cleaned[start:end + 1]

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ApiError(
            "模型未返回有效 JSON，请检查图片是否清晰",
            f"解析错误: {e}\n\n原始返回:\n{text[:800]}",
        )

    if not isinstance(result, list):
        raise ApiError(
            "模型返回的 JSON 格式不正确，期望数组",
            f"原始返回:\n{text[:500]}",
        )

    if not result:
        raise ApiError(
            "未能识别出有效内容，请确认图片是否为书籍目录页或论文内容",
            f"原始返回:\n{text[:500]}",
        )

    return result


def validate_book_json(data: list[Any]) -> None:
    has_end = False
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if title == "全书结束":
            has_end = True
            break
    if not has_end:
        raise ApiError(
            '缺少"全书结束"页码，请确认目录截图是否完整',
            "JSON 中未找到 title 为'全书结束'的条目",
        )


def smart_import_book(file_paths: list[str], progress_callback: Any | None = None) -> list[Any]:
    from sgp_qt_core import app_config
    from sgp_qt_prompts import DEFAULT_BOOK_JSON_PROMPT

    images = prepare_images(file_paths, progress_callback)
    if progress_callback:
        if len(images) > 1:
            progress_callback(STEP_PREPARE_IMAGE, f"已准备 {len(images)} 张图片")
        else:
            progress_callback(STEP_PREPARE_IMAGE, "已准备 1 张图片")

    prompt = app_config.get("reading_book_prompt", "") or DEFAULT_BOOK_JSON_PROMPT

    raw_text = call_vision_api(images, prompt, progress_callback)
    if progress_callback:
        progress_callback(STEP_PARSE_RESULT, "正在解析返回结果...")
    json_data = extract_json_from_response(raw_text)
    validate_book_json(json_data)
    return json_data


def smart_import_paper(file_paths: list[str], progress_callback: Any | None = None) -> list[Any]:
    from sgp_qt_core import app_config
    from sgp_qt_prompts import DEFAULT_PAPER_JSON_PROMPT

    images = prepare_images(file_paths, progress_callback)
    if progress_callback:
        if len(images) > 1:
            progress_callback(STEP_PREPARE_IMAGE, f"已准备 {len(images)} 张图片")
        else:
            progress_callback(STEP_PREPARE_IMAGE, "已准备 1 张图片")

    prompt = app_config.get("reading_paper_prompt", "") or DEFAULT_PAPER_JSON_PROMPT

    raw_text = call_vision_api(images, prompt, progress_callback)
    if progress_callback:
        progress_callback(STEP_PARSE_RESULT, "正在解析返回结果...")
    json_data = extract_json_from_response(raw_text)
    return json_data
