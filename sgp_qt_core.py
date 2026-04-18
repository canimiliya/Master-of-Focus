"""Core data/config helpers for Study Game Pro (Qt).

This module keeps JSON formats compatible with the legacy Tkinter version.
It intentionally contains no Qt imports.
"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import urllib.request
from datetime import datetime, timedelta
from typing import Any


# ===================== Paths & config =====================
DATA_FOLDER_NAME = "专注改变（个人软件数据）"
LEGACY_DATA_DIR = r"D:\专注改变（个人软件数据）"
LEGACY_CONFIG_FILE = os.path.join(LEGACY_DATA_DIR, ".study_game_config.json")
OLD_APP_CONFIG_FILE = os.path.expanduser("~/.study_game_config.json")
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".study_game")
APP_CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

TASK_CATS = ["科研", "理论/技术", "生活", "兴趣爱好"]
PENALTY_MULTIPLIER = 1.5


def default_app_config() -> dict[str, Any]:
    return {
        "data_dir": "",
        "memo_dir": "",
        "storage_root_dir": "",
        "storage_dir_confirmed": False,
        "cancel_month": "",
        "cancel_count": 0,
        "memo_date": "",
        "memo_count": 0,
        "review_reminder_date": "",
        "rewards_history_reset_done": False,
        "rewards_history_reset_date": "",
        "holiday_api_enabled": True,
        "holiday_api_base": "https://timor.tech/api/holiday/info/",
        "holiday_cache": {},
    }


# Keep these objects stable across imports; mutate instead of rebinding.
app_config: dict[str, Any] = default_app_config()

DATA_FILE_NAME = "study_game_reward.json"
DATA_FILE_PATH: str | None = None

# Always a dict object so other modules can import and hold a reference.
global_data: dict[str, Any] = {}


def load_app_config() -> None:
    """Load app configuration from disk (with legacy migration)."""

    if not os.path.exists(APP_CONFIG_FILE):
        for legacy_path in (OLD_APP_CONFIG_FILE, LEGACY_CONFIG_FILE):
            if os.path.exists(legacy_path):
                try:
                    os.makedirs(CONFIG_DIR, exist_ok=True)
                    shutil.move(legacy_path, APP_CONFIG_FILE)
                except Exception:
                    pass
                break

    app_config.clear()
    app_config.update(default_app_config())

    if os.path.exists(APP_CONFIG_FILE):
        try:
            with open(APP_CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                app_config.update(loaded)
        except Exception:
            pass

    if app_config.get("data_dir") and not app_config.get("storage_root_dir"):
        app_config["storage_root_dir"] = os.path.dirname(app_config["data_dir"])
    if app_config.get("storage_root_dir") and not app_config.get("data_dir"):
        app_config["data_dir"] = os.path.join(app_config["storage_root_dir"], DATA_FOLDER_NAME)
    if app_config.get("storage_root_dir") and "storage_dir_confirmed" not in app_config:
        app_config["storage_dir_confirmed"] = True


def save_app_config() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(APP_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(app_config, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


def save_data() -> None:
    if DATA_FILE_PATH is None:
        return
    try:
        with open(DATA_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(global_data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


def compute_read_pages_from_tree(tree: list[dict[str, Any]] | None) -> int:
    total = 0
    for chap in tree or []:
        if not isinstance(chap, dict):
            continue
        sections = chap.get("sections", [])
        if isinstance(sections, list) and sections:
            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                if sec.get("done"):
                    try:
                        total += int(sec.get("pages_count", 0) or 0)
                    except Exception:
                        pass
        else:
            if chap.get("done"):
                try:
                    total += int(chap.get("pages_count", 0) or 0)
                except Exception:
                    pass
    return total


def normalize_reading_books(data: dict[str, Any]) -> None:
    books = data.get("reading_books")
    if not isinstance(books, dict):
        data["reading_books"] = {}
        return

    for title, info in list(books.items()):
        if not isinstance(info, dict):
            books.pop(title, None)
            continue

        info.setdefault("author", "")
        info.setdefault("version", "")
        info.setdefault("total_pages", 0)
        info.setdefault("read_pages", 0)
        info.setdefault("time_spent", 0)

        tree = info.get("tree")
        if not isinstance(tree, list):
            info["tree"] = []
            tree = info["tree"]

        for chap in tree:
            if not isinstance(chap, dict):
                continue
            chap.setdefault("title", "")
            chap.setdefault("start_page", 0)
            chap.setdefault("pages_count", 0)
            chap.setdefault("done", False)
            chap.setdefault("time_spent", 0)

            sections = chap.get("sections")
            if not isinstance(sections, list):
                chap["sections"] = []
                sections = chap["sections"]

            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                sec.setdefault("title", "")
                sec.setdefault("start_page", 0)
                sec.setdefault("pages_count", 0)
                sec.setdefault("done", False)
                sec.setdefault("time_spent", 0)

        for chap in tree:
            sections = chap.get("sections", [])
            if sections:
                chap["pages_count"] = sum(
                    int(sec.get("pages_count", 0) or 0) for sec in sections if isinstance(sec, dict)
                )

        info["read_pages"] = compute_read_pages_from_tree(tree)
        total_pages = int(info.get("total_pages", 0) or 0)
        if total_pages and info["read_pages"] > total_pages:
            info["read_pages"] = total_pages


def init_data() -> dict[str, Any]:
    """Load (or initialize) the main data JSON and normalize required keys."""

    global DATA_FILE_PATH

    if app_config.get("data_dir"):
        DATA_FILE_PATH = os.path.join(app_config["data_dir"], DATA_FILE_NAME)
    else:
        DATA_FILE_PATH = None

    today_str = datetime.now().strftime("%Y-%m-%d")

    loaded_data: dict[str, Any] | None = None
    if DATA_FILE_PATH and os.path.exists(DATA_FILE_PATH):
        try:
            with open(DATA_FILE_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                loaded_data = raw
        except Exception:
            loaded_data = None

    if loaded_data is not None:
        global_data.clear()
        global_data.update(loaded_data)

        global_data.setdefault("today_structured_tasks", {cat: [] for cat in TASK_CATS})
        global_data.setdefault("last_penalty_date", "")
        global_data.setdefault("focus_logs", [])
        global_data.setdefault("today_incentive_pool", 0)
        global_data.setdefault("incentive_claims", {"night": "", "noon": ""})
        global_data.setdefault("long_term_tasks", [])
        global_data.setdefault("report_exclusions", [])
        global_data.setdefault("reading_books", {})

        if not app_config.get("rewards_history_reset_done"):
            app_config["rewards_history_reset_done"] = True
            app_config["rewards_history_reset_date"] = today_str
            save_app_config()

        global_data.setdefault("last_checkin_date", today_str)
    else:
        global_data.clear()
        global_data.update({
            "total_points": 0,
            "today_tomatoes": 0,
            "today_study_time": 0,
            "continuous_checkin_days": 1,
            "last_checkin_date": today_str,
            "first_use_date": today_str,
            "exchange_history": [],
            "study_history": [],
            "today_exchanged_time": 0,
            "today_task_submitted": False,
            "today_review_submitted": False,
            "today_structured_tasks": {cat: [] for cat in TASK_CATS},
            "today_review_text": "",
            "daily_rewards_history": [],
            "last_penalty_date": "",
            "focus_logs": [],
            "today_incentive_pool": 0,
            "incentive_claims": {"night": "", "noon": ""},
            "long_term_tasks": [],
            "report_exclusions": [],
            "reading_books": {},
        })
        if DATA_FILE_PATH:
            save_data()

    normalize_reading_books(global_data)
    return global_data


def get_holiday_info(date_str: str) -> dict[str, Any] | None:
    if not app_config.get("holiday_api_enabled", True):
        return None

    cache = app_config.setdefault("holiday_cache", {})
    if isinstance(cache, dict) and date_str in cache:
        return cache[date_str]

    base = str(app_config.get("holiday_api_base", "") or "").strip()
    if not base:
        return None

    url = f"{base}{date_str}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=5, context=context) as resp:
            payload = resp.read().decode("utf-8")
            data = json.loads(payload)
    except Exception:
        return None

    if not isinstance(data, dict) or data.get("code") != 0:
        return None

    if isinstance(cache, dict):
        cache[date_str] = data
    save_app_config()
    return data


def is_workday(date_obj: datetime.date | None = None) -> bool:
    target = date_obj or datetime.now().date()
    date_str = target.strftime("%Y-%m-%d")
    info = get_holiday_info(date_str)

    if info:
        holiday = info.get("holiday")
        if isinstance(holiday, dict):
            flag = holiday.get("holiday")
            if flag is True:
                return False
            if flag is False:
                return True

        day_type = info.get("type", {}).get("type")
        if day_type in (0, 3):
            return True
        if day_type in (1, 2):
            return False

    return target.isoweekday() <= 5


def inject_long_term_tasks_for_date(data: dict[str, Any], target_date: datetime.date) -> bool:
    """Ensure long-term tasks for target_date exist in today_structured_tasks.

    Returns True if data was modified.
    """

    if not isinstance(data, dict):
        return False

    changed = False
    tasks = data.get("today_structured_tasks")
    if not isinstance(tasks, dict):
        tasks = {cat: [] for cat in TASK_CATS}
        data["today_structured_tasks"] = tasks
        changed = True

    for cat in TASK_CATS:
        if cat not in tasks or not isinstance(tasks.get(cat), list):
            tasks[cat] = []
            changed = True

    month_day = target_date.strftime("%m%d")
    for lt_task in data.get("long_term_tasks", []) or []:
        if not isinstance(lt_task, dict):
            continue
        try:
            start_date_str = lt_task.get("start_date", "")
            if not start_date_str:
                continue
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

            days_raw = lt_task.get("days", 0)
            days = int(days_raw)
            if days <= 0:
                continue

            end_date = start_date + timedelta(days=days - 1)
            if not (start_date <= target_date <= end_date):
                continue

            cat = lt_task.get("cat")
            text = (lt_task.get("text") or "").strip()
            if not cat or not text:
                continue

            formatted_text = f"（长期）{text}（{month_day}）"
            exists = any(t.get("text") == formatted_text for t in tasks.get(cat, []))
            if exists:
                continue

            req_time_raw = lt_task.get("req_time", 0)
            req_time = int(req_time_raw) if str(req_time_raw).strip() else 0

            tasks.setdefault(cat, []).append({
                "text": formatted_text,
                "done": False,
                "req_time": req_time,
            })
            changed = True
        except Exception as e:
            print("解析长期任务失败:", e)

    if changed:
        data["today_task_submitted"] = any(data.get("today_structured_tasks", {}).get(cat) for cat in TASK_CATS)
    return changed


def calculate_book_pages(json_data: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(json_data, list):
        raise ValueError("目录 JSON 必须是列表")

    cleaned: list[dict[str, Any]] = []
    total_pages = 0
    for item in json_data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        page = item.get("page", None)
        if page is None:
            continue
        try:
            page_num = int(page)
        except Exception:
            continue
        if title == "全书结束":
            total_pages = max(total_pages, page_num)
            continue
        cleaned.append({"title": title, "page": page_num})

    if total_pages <= 0:
        raise ValueError("目录 JSON 缺少“全书结束”页码")
    if not cleaned:
        return [], total_pages

    book_tree: list[dict[str, Any]] = []
    current_chapter: dict[str, Any] | None = None
    for idx, item in enumerate(cleaned):
        next_page = cleaned[idx + 1]["page"] if idx + 1 < len(cleaned) else total_pages
        pages_count = max(0, int(next_page) - int(item["page"]))
        node_data: dict[str, Any] = {
            "title": item["title"],
            "start_page": int(item["page"]),
            "pages_count": pages_count,
            "done": False,
            "time_spent": 0,
        }

        if "§" in item["title"] and current_chapter is not None:
            current_chapter["sections"].append(node_data)
        else:
            current_chapter = dict(node_data)
            current_chapter["sections"] = []
            book_tree.append(current_chapter)

    for chap in book_tree:
        if chap.get("sections"):
            chap["pages_count"] = sum(
                int(sec.get("pages_count", 0) or 0) for sec in chap["sections"] if isinstance(sec, dict)
            )

    return book_tree, total_pages
