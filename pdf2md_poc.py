"""pdf2md_poc.py — PDF批量转Markdown验证脚本

技术路线（统一使用 MinerU 精准解析 API）：
1. 在线URL → /api/v4/extract/task 提交 → 轮询 → 下载Zip → 提取Markdown
2. 本地文件 → /api/v4/file-urls/batch 申请上传链接 → PUT上传 → 自动解析 → 轮询 → 下载Zip → 提取Markdown
3. 语言检测: 统计中文字符占比判断
4. Kimi 2.5翻译: 英文Markdown → 中文Markdown (via SiliconFlow, 流式输出)
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.parse
import zipfile
from io import BytesIO
from typing import Optional

MINERU_BASE_URL = "https://mineru.net/api"
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_MODEL = "Pro/deepseek-ai/DeepSeek-V3.2"

TRANSLATE_PROMPT = (
    "你是一位专业的文档翻译助手。请将用户提供的 Markdown 文件内容从英文翻译为简体中文。\n\n"
    "**必须严格遵守以下规则，不得违反：**\n\n"
    "1. **仅翻译纯文本内容**：只翻译段落文字、标题文字、表格内的文字描述、列表项文字。"
    "不翻译任何代码、命令、变量名、文件名、数学公式（LaTeX）、数字、日期、人名、机构名、"
    "专有名词（如算法名 PPO、SAC、CEM 等）。\n"
    "2. **保留所有非文本元素**：绝对禁止修改或删除以下内容，必须原样保留：\n"
    "   - Markdown 格式标记（如 `#`、`*`、`-`、`[`、`]`、`(`、`)`、`|`、`:`、` ``` ` 等）。\n"
    "   - LaTeX 数学公式（所有包含 `$` 或 `$$` 的内容）。\n"
    "   - 图片链接（如 `![image](path)`）。\n"
    "   - 代码块（用 ` ``` ` 包裹的部分）。\n"
    "   - 表格的框架（`|`、`-`、对齐标记 `:`）。\n"
    "   - URL 链接。\n"
    "   - 数字、单位、百分比、符号（如 `%`、`±`、`°`）。\n"
    "3. **保持原有排版结构**：段落换行、空行、缩进、列表层级必须与原文完全一致。\n"
    "4. **专有名词处理**：遇到模型名（如 MBD、PPO）、任务名（如 Hopper、Half Cheetah）、"
    "术语（如 Score Function、Trajectory Optimization）时，第一次出现可译为中文并括号附上英文，"
    "之后直接用中文简称或保留英文（根据上下文自然决定，但不要改动公式中的缩写）。\n"
    "5. **直接输出翻译后的 Markdown 文本**，不要添加任何额外解释或说明。\n\n"
    "现在，请将用户上传的 Markdown 文件内容翻译为中文。"
)

CHINESE_RATIO_THRESHOLD = 0.15
TRANSLATE_CHUNK_SIZE = 12000
TRANSLATE_CHUNK_OVERLAP = 500


def _urlopen(req, timeout=60):
    context = ssl._create_unverified_context()
    return urllib.request.urlopen(req, timeout=timeout, context=context)


def _put_to_oss(url: str, data: bytes, timeout: int = 300) -> None:
    import http.client
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    path = parsed.path
    if parsed.query:
        path = f"{path}?{parsed.query}"
    ctx = ssl._create_unverified_context()
    conn = http.client.HTTPSConnection(host, parsed.port or 443, context=ctx, timeout=timeout)
    conn.request("PUT", path, body=data, headers={})
    resp = conn.getresponse()
    resp.read()
    conn.close()
    if resp.status not in (200, 201):
        raise RuntimeError(f"文件上传失败: HTTP {resp.status}")


def _log(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


# ===================== MinerU 精准解析 API =====================

def mineru_create_task(url: str, token: str, model_version: str = "vlm",
                       is_ocr: bool = False, enable_formula: bool = True,
                       enable_table: bool = True, language: str = "ch") -> str:
    api_url = f"{MINERU_BASE_URL}/v4/extract/task"
    payload = {
        "url": url,
        "model_version": model_version,
        "is_ocr": is_ocr,
        "enable_formula": enable_formula,
        "enable_table": enable_table,
        "language": language,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(api_url, data=body, headers=headers, method="POST")
    with _urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"创建任务失败: {json.dumps(result, ensure_ascii=False)}")
    task_id = result["data"].get("task_id", "")
    if not task_id:
        raise RuntimeError(f"未获取到task_id: {json.dumps(result, ensure_ascii=False)[:300]}")
    _log("MinerU", f"任务ID: {task_id}")
    return task_id


def mineru_poll_task(task_id: str, token: str, interval: int = 10,
                     max_wait: int = 600) -> dict:
    api_url = f"{MINERU_BASE_URL}/v4/extract/task/{task_id}"
    headers = {"Authorization": f"Bearer {token}"}
    elapsed = 0
    while elapsed < max_wait:
        req = urllib.request.Request(api_url, headers=headers, method="GET")
        with _urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        data = result.get("data", {})
        state = str(data.get("state", "")).lower()
        if state == "done":
            _log("MinerU", "解析完成!")
            return data
        if state == "failed":
            err_msg = data.get("err_msg", "")
            raise RuntimeError(f"任务失败: {err_msg}")
        if state == "running":
            progress = data.get("extract_progress", {})
            extracted = progress.get("extracted_pages", "?")
            total = progress.get("total_pages", "?")
            _log("MinerU", f"解析中: {extracted}/{total} 页 ({elapsed}/{max_wait}s)")
        elif state == "converting":
            _log("MinerU", f"格式转换中... ({elapsed}/{max_wait}s)")
        else:
            _log("MinerU", f"状态: {state}, 等待 {interval}s... ({elapsed}/{max_wait}s)")
        time.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"任务超时 ({max_wait}s)")


def mineru_download_markdown_from_zip(zip_url: str,
                                      extract_images_to: str = "") -> str:
    _log("MinerU", f"下载结果: {zip_url[:80]}...")
    req = urllib.request.Request(zip_url)
    with _urlopen(req, timeout=180) as resp:
        zip_bytes = resp.read()
    markdown_content = ""
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        md_files = [n for n in zf.namelist() if n.endswith(".md")]
        if md_files:
            md_files.sort(key=lambda n: (not n.endswith("full.md"), n))
            markdown_content = zf.read(md_files[0]).decode("utf-8")
        if extract_images_to:
            image_files = [n for n in zf.namelist()
                           if n.startswith("images/") and not n.endswith("/")]
            if image_files:
                img_dir = os.path.join(extract_images_to, "images")
                os.makedirs(img_dir, exist_ok=True)
                for img_name in image_files:
                    img_data = zf.read(img_name)
                    img_path = os.path.join(extract_images_to, img_name)
                    with open(img_path, "wb") as f:
                        f.write(img_data)
                _log("MinerU", f"提取 {len(image_files)} 张图片到 {img_dir}")
    if not markdown_content:
        raise RuntimeError("Zip包中未找到Markdown文件")
    return markdown_content


def mineru_parse_url(pdf_url: str, token: str, model_version: str = "vlm",
                     output_dir: str = "") -> str:
    _log("MinerU", f"提交URL解析: {pdf_url[:80]}...")
    task_id = mineru_create_task(pdf_url, token, model_version)
    data = mineru_poll_task(task_id, token)
    zip_url = data.get("full_zip_url", "")
    if not zip_url:
        raise RuntimeError(f"任务完成但未找到下载URL: {json.dumps(data, ensure_ascii=False)[:300]}")
    markdown = mineru_download_markdown_from_zip(zip_url, extract_images_to=output_dir)
    _log("MinerU", f"Markdown长度: {len(markdown)}")
    return markdown


def mineru_upload_local_file(file_path: str, token: str,
                             model_version: str = "vlm") -> str:
    filename = os.path.basename(file_path)
    api_url = f"{MINERU_BASE_URL}/v4/file-urls/batch"
    payload = {
        "files": [{"name": filename}],
        "model_version": model_version,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    _log("MinerU", f"申请上传链接: {filename}")
    req = urllib.request.Request(api_url, data=body, headers=headers, method="POST")
    with _urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"申请上传链接失败: {json.dumps(result, ensure_ascii=False)}")

    batch_id = result["data"].get("batch_id", "")
    file_urls = result["data"].get("file_urls", [])
    if not batch_id or not file_urls:
        raise RuntimeError(f"未获取到上传信息: {json.dumps(result, ensure_ascii=False)[:300]}")

    upload_url = file_urls[0]
    file_size = os.path.getsize(file_path)
    _log("MinerU", f"上传文件中... ({file_size/1024/1024:.1f}MB)")
    with open(file_path, "rb") as f:
        file_data = f.read()
    _put_to_oss(upload_url, file_data)
    _log("MinerU", f"上传成功, batch_id: {batch_id}")
    return batch_id


def mineru_poll_batch(batch_id: str, token: str, filename: str = "",
                      interval: int = 10, max_wait: int = 600) -> dict:
    api_url = f"{MINERU_BASE_URL}/v4/extract-results/batch/{batch_id}"
    headers = {"Authorization": f"Bearer {token}"}
    elapsed = 0
    while elapsed < max_wait:
        req = urllib.request.Request(api_url, headers=headers, method="GET")
        with _urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("code") != 0:
            raise RuntimeError(f"批量查询失败: {result.get('msg', '未知错误')}")
        data = result.get("data", {})
        extract_result = data.get("extract_result", [])
        if not extract_result:
            _log("MinerU", f"等待批量任务启动... ({elapsed}/{max_wait}s)")
            time.sleep(interval)
            elapsed += interval
            continue

        file_result = None
        for item in extract_result:
            if isinstance(item, dict):
                if not filename or item.get("file_name") == filename:
                    file_result = item
                    break
        if not file_result:
            file_result = extract_result[0] if isinstance(extract_result[0], dict) else {}

        state = str(file_result.get("state", "")).lower()
        if state == "done":
            _log("MinerU", "解析完成!")
            return file_result
        if state == "failed":
            err_msg = file_result.get("err_msg", "未知错误")
            raise RuntimeError(f"解析失败: {err_msg}")

        done_count = sum(
            1 for t in extract_result
            if isinstance(t, dict) and str(t.get("state", "")).lower() == "done"
        )
        running_info = ""
        if state == "running":
            running_info = " (解析中...)"
        elif state == "converting":
            running_info = " (格式转换中...)"
        elif state == "pending":
            running_info = " (排队中...)"
        _log("MinerU", f"批量进度: {done_count}/{len(extract_result)} 完成{running_info} ({elapsed}/{max_wait}s)")

        time.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"批量任务超时 ({max_wait}s)")


def mineru_parse_local_file(file_path: str, token: str,
                            model_version: str = "vlm",
                            output_dir: str = "") -> str:
    _log("MinerU", f"本地文件解析: {file_path}")
    filename = os.path.basename(file_path)
    batch_id = mineru_upload_local_file(file_path, token, model_version)
    file_result = mineru_poll_batch(batch_id, token, filename)
    zip_url = file_result.get("full_zip_url", "")
    if not zip_url:
        raise RuntimeError(f"任务完成但未找到下载URL: {json.dumps(file_result, ensure_ascii=False)[:300]}")
    markdown = mineru_download_markdown_from_zip(zip_url, extract_images_to=output_dir)
    _log("MinerU", f"Markdown长度: {len(markdown)}")
    return markdown


# ===================== 语言检测 =====================

def detect_language(text: str) -> str:
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_chars = len(re.findall(r'[\u4e00-\u9fff\w]', text))
    if total_chars == 0:
        return "en"
    ratio = chinese_chars / total_chars
    _log("语言检测", f"中文字符占比: {ratio:.2%}")
    return "zh" if ratio > CHINESE_RATIO_THRESHOLD else "en"


# ===================== Kimi 2.5 翻译 (流式) =====================

def _call_llm_stream(messages: list[dict], api_key: str, base_url: str,
                     model: str, max_tokens: int = 16384) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "stream": True,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    full_text = ""
    last_print_len = 0
    char_count = 0
    with _urlopen(req, timeout=600) as resp:
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
                        char_count += len(content_piece)
                        if char_count - last_print_len >= 200:
                            print(f"  已输出 {char_count} 字...", end="\r", flush=True)
                            last_print_len = char_count
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
    if char_count > 0:
        print(f"  输出完成, 共 {char_count} 字", flush=True)
    return full_text


def _split_markdown_chunks(text: str, chunk_size: int = TRANSLATE_CHUNK_SIZE,
                           overlap: int = TRANSLATE_CHUNK_OVERLAP) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > chunk_size and current:
            chunks.append("\n".join(current))
            overlap_lines: list[str] = []
            overlap_len = 0
            for l in reversed(current):
                if overlap_len + len(l) + 1 > overlap:
                    break
                overlap_lines.insert(0, l)
                overlap_len += len(l) + 1
            current = overlap_lines
            current_len = overlap_len
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def translate_to_chinese(markdown_text: str, api_key: str,
                         base_url: str = SILICONFLOW_BASE_URL,
                         model: str = SILICONFLOW_MODEL,
                         prompt: str | None = None) -> str:
    system_prompt = prompt if prompt else TRANSLATE_PROMPT
    chunks = _split_markdown_chunks(markdown_text)
    if len(chunks) == 1:
        _log("翻译", f"单次翻译, 长度: {len(markdown_text)}")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": markdown_text},
        ]
        return _call_llm_stream(messages, api_key, base_url, model)
    _log("翻译", f"分 {len(chunks)} 块翻译, 总长度: {len(markdown_text)}")
    translated_parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        _log("翻译", f"=== 第 {i}/{len(chunks)} 块, 长度: {len(chunk)} ===")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": chunk},
        ]
        part = _call_llm_stream(messages, api_key, base_url, model)
        translated_parts.append(part)
    return "\n".join(translated_parts)


# ===================== 主流程 =====================

def process_single_pdf(
    pdf_source: str,
    output_dir: str,
    mineru_token: str,
    llm_api_key: str,
    llm_base_url: str = SILICONFLOW_BASE_URL,
    llm_model: str = SILICONFLOW_MODEL,
    model_version: str = "vlm",
    skip_translation: bool = False,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    is_url = pdf_source.startswith("http://") or pdf_source.startswith("https://")

    print(f"\n{'='*60}", flush=True)
    print(f"处理: {pdf_source}", flush=True)
    print(f"{'='*60}", flush=True)

    if is_url:
        markdown = mineru_parse_url(pdf_source, mineru_token, model_version, output_dir)
    else:
        if not os.path.isfile(pdf_source):
            raise FileNotFoundError(f"文件不存在: {pdf_source}")
        file_size = os.path.getsize(pdf_source)
        if file_size > 200 * 1024 * 1024:
            raise RuntimeError(f"文件超过200MB限制 ({file_size/1024/1024:.1f}MB)")
        markdown = mineru_parse_local_file(pdf_source, mineru_token, model_version, output_dir)

    lang = detect_language(markdown)
    _log("语言检测", f"检测结果: {'中文' if lang == 'zh' else '英文'}")

    basename = os.path.splitext(os.path.basename(pdf_source))[0]
    basename = re.sub(r'[^\w\-.]', '_', basename)
    if basename.startswith("_"):
        basename = basename.lstrip("_")
    if not basename:
        basename = f"output_{int(time.time())}"

    if lang == "en" and not skip_translation:
        en_output_path = os.path.join(output_dir, f"{basename}.md")
        with open(en_output_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        _log("保存", f"英文版已保存到: {en_output_path}")

        _log("翻译", f"正在调用 {llm_model} 翻译...")
        zh_markdown = translate_to_chinese(markdown, llm_api_key, llm_base_url, llm_model)
        _log("翻译", "翻译完成")

        zh_output_path = os.path.join(output_dir, f"{basename}_zh.md")
        with open(zh_output_path, "w", encoding="utf-8") as f:
            f.write(zh_markdown)
        _log("保存", f"中文版已保存到: {zh_output_path}")
        return zh_output_path

    output_path = os.path.join(output_dir, f"{basename}.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    _log("保存", f"已保存到: {output_path}")
    return output_path


def batch_process(
    pdf_list: list[str],
    output_dir: str,
    mineru_token: str,
    llm_api_key: str,
    llm_base_url: str = SILICONFLOW_BASE_URL,
    llm_model: str = SILICONFLOW_MODEL,
    model_version: str = "vlm",
    skip_translation: bool = False,
) -> list[Optional[str]]:
    results: list[Optional[str]] = []
    total = len(pdf_list)
    for i, pdf_source in enumerate(pdf_list, 1):
        print(f"\n>>> [{i}/{total}]", flush=True)
        try:
            output = process_single_pdf(
                pdf_source, output_dir, mineru_token, llm_api_key,
                llm_base_url, llm_model, model_version, skip_translation,
            )
            results.append(output)
        except Exception as e:
            _log("错误", f"处理失败: {e}")
            results.append(None)
    success = sum(1 for r in results if r is not None)
    print(f"\n{'='*60}", flush=True)
    print(f"批量处理完成: {success}/{total} 成功", flush=True)
    print(f"输出目录: {output_dir}", flush=True)
    print(f"{'='*60}", flush=True)
    return results


# ===================== POC 测试入口 =====================

if __name__ == "__main__":
    MINERU_TOKEN = "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI2NjIwMDg1MyIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3NjczODIyMSwiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiMTg3ODUxNjU2MjYiLCJvcGVuSWQiOm51bGwsInV1aWQiOiIxNTk2YjI3OC1kZjg0LTRhZTgtODdlOS01YzVhZDc0ZjkzMTUiLCJlbWFpbCI6IiIsImV4cCI6MTc4NDUxNDIyMX0.T9zDNK5Ag4lVawHWwnlIXNU56-3ccT4G9RNdXNXQvEZ6TN2Jwq441V1roCNMRJMicNQK-dG3VPN60YDUc-ftnQ"
    LLM_API_KEY = "sk-lkhtzjkkqixaodtdaztonywqitztclalnootypxwiyeqljtf"

    TEST_PDFS = [
        "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    ]

    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "pdf2md_output")

    batch_process(
        pdf_list=TEST_PDFS,
        output_dir=OUTPUT_DIR,
        mineru_token=MINERU_TOKEN,
        llm_api_key=LLM_API_KEY,
    )
