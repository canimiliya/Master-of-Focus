import json
import time
import os
import sys
import shutil
import threading
import socket
import calendar
import random
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, filedialog, font

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TK_DND_AVAILABLE = True
except Exception:
    TK_DND_AVAILABLE = False
    DND_FILES = None
    TkinterDnD = None

try:
    from win10toast import ToastNotifier
    WIN_TOAST_AVAILABLE = True
except Exception:
    ToastNotifier = None
    WIN_TOAST_AVAILABLE = False

# 导入绘图依赖包
import matplotlib
matplotlib.use("TkAgg")  
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FuncFormatter
import numpy as np

# 设置中文字体，防止图表乱码
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# ===================== 核心防多开锁机制 =====================
instance_socket = None
def enforce_single_instance():
    global instance_socket
    try:
        instance_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        instance_socket.bind(('127.0.0.1', 38594))
    except socket.error:
        windows_force_top_alert("启动拦截", "【改变自己】已经在运行中了！请查看任务栏或系统托盘。")
        sys.exit(0)

# ===================== 本地路径与配置系统 =====================
DATA_FOLDER_NAME = "专注改变（个人软件数据）"
LEGACY_DATA_DIR = r"D:\专注改变（个人软件数据）"
LEGACY_CONFIG_FILE = os.path.join(LEGACY_DATA_DIR, ".study_game_config.json")
OLD_APP_CONFIG_FILE = os.path.expanduser("~/.study_game_config.json")
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".study_game")
APP_CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
app_config = {
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
    "holiday_cache": {}
}
TASK_CATS = ["科研", "理论/技术", "生活", "兴趣爱好"]
PENALTY_MULTIPLIER = 1.5

def load_app_config():
    global app_config
    if not os.path.exists(APP_CONFIG_FILE):
        for legacy_path in (OLD_APP_CONFIG_FILE, LEGACY_CONFIG_FILE):
            if os.path.exists(legacy_path):
                try:
                    os.makedirs(CONFIG_DIR, exist_ok=True)
                    shutil.move(legacy_path, APP_CONFIG_FILE)
                except Exception:
                    pass
                break
    if os.path.exists(APP_CONFIG_FILE):
        with open(APP_CONFIG_FILE, "r", encoding="utf-8") as f:
            try: app_config.update(json.load(f))
            except Exception: pass
    if app_config.get("data_dir") and not app_config.get("storage_root_dir"):
        app_config["storage_root_dir"] = os.path.dirname(app_config["data_dir"])
    if app_config.get("storage_root_dir") and not app_config.get("data_dir"):
        app_config["data_dir"] = os.path.join(app_config["storage_root_dir"], DATA_FOLDER_NAME)
    if app_config.get("storage_root_dir") and "storage_dir_confirmed" not in app_config:
        app_config["storage_dir_confirmed"] = True

def save_app_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(APP_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(app_config, f, ensure_ascii=False, indent=4)

DATA_FILE_NAME = "study_game_reward.json"
DATA_FILE_PATH = None
global_data = None

def windows_force_top_alert(title, message):
    if sys.platform == "win32":
        import ctypes
        style = 0x00000000 | 0x00000030 | 0x00040000 | 0x00010000
        ctypes.windll.user32.MessageBoxW(0, message, title, style)
    else:
        messagebox.showinfo(title, message)

def notify_system(title, message, duration=6):
    if sys.platform == "win32" and WIN_TOAST_AVAILABLE:
        def _show():
            ToastNotifier().show_toast(title, message, duration=duration, threaded=False)
        threading.Thread(target=_show, daemon=True).start()
        return True
    return False

# ===================== 数据核心逻辑 =====================
def init_data():
    global global_data, DATA_FILE_PATH

    
    if app_config.get("data_dir"):
        DATA_FILE_PATH = os.path.join(app_config["data_dir"], DATA_FILE_NAME)
    else:
        DATA_FILE_PATH = None

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_date = datetime.now().date()

    if DATA_FILE_PATH and os.path.exists(DATA_FILE_PATH):
        with open(DATA_FILE_PATH, "r", encoding="utf-8") as f:
            global_data = json.load(f)
            if "today_structured_tasks" not in global_data:
                global_data["today_structured_tasks"] = {cat: [] for cat in TASK_CATS}
            if "last_penalty_date" not in global_data:
                global_data["last_penalty_date"] = ""
            if "focus_logs" not in global_data:
                global_data["focus_logs"] = []
            if "today_incentive_pool" not in global_data:
                global_data["today_incentive_pool"] = 0
            if "incentive_claims" not in global_data:
                global_data["incentive_claims"] = {"night": "", "noon": ""}
            if "long_term_tasks" not in global_data:
                global_data["long_term_tasks"] = []
            if "report_exclusions" not in global_data:
                global_data["report_exclusions"] = []

        if not app_config.get("rewards_history_reset_done"):
            # Only reset once on first migration, not every day
            app_config["rewards_history_reset_done"] = True
            app_config["rewards_history_reset_date"] = today_str
            save_app_config()

        global_data.setdefault("last_checkin_date", today_str)
    else:
        global_data = {
            "total_points": 0, "today_tomatoes": 0, "today_study_time": 0,
            "continuous_checkin_days": 1, "last_checkin_date": today_str,
            "first_use_date": today_str, "exchange_history": [], "study_history": [],
            "today_exchanged_time": 0, "today_task_submitted": False, "today_review_submitted": False,
            "today_structured_tasks": {cat: [] for cat in TASK_CATS},
            "today_review_text": "", "daily_rewards_history": [], "last_penalty_date": "",
            "focus_logs": [],
            "today_incentive_pool": 0,
            "incentive_claims": {"night": "", "noon": ""},
            "long_term_tasks": [],
            "report_exclusions": []
        }
        if DATA_FILE_PATH: save_data()
            
    return global_data

def save_data():
    if global_data is None or DATA_FILE_PATH is None: return
    with open(DATA_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(global_data, f, ensure_ascii=False, indent=4)

def get_holiday_info(date_str):
    if not app_config.get("holiday_api_enabled", True):
        return None
    cache = app_config.setdefault("holiday_cache", {})
    if date_str in cache:
        return cache[date_str]

    base = app_config.get("holiday_api_base", "").strip()
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

    cache[date_str] = data
    save_app_config()
    return data

def is_workday(date_obj=None):
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

# ===================== UI 界面类 =====================
BaseTk = TkinterDnD.Tk if TK_DND_AVAILABLE else tk.Tk

class StudyGameUI(BaseTk):
    def __init__(self):
        super().__init__()
        self.title("✨改变自己✨")
        self.geometry("780x580")  
        self.configure(bg="#FFF0F5")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        load_app_config()
        self.ensure_storage_directory()
        init_data()
        self.time_left = 0
        self.timer_running = False
        self.current_stage = ""
        self.timer_id = None
        self.current_focus_task = None
        self.focus_segment_start_dt = None
        self.pending_focus_segments = []
        
        self.font_normal = font.Font(family="Microsoft YaHei", size=10)
        self.font_strike = font.Font(family="Microsoft YaHei", size=10, overstrike=1)
        self.font_bold_normal = font.Font(family="Microsoft YaHei", size=11, weight="bold")
        self.font_bold_strike = font.Font(family="Microsoft YaHei", size=11, weight="bold", overstrike=1)

        self.current_date_str = datetime.now().strftime("%Y-%m-%d")
        self.create_widgets()
        # Ensure rollover settlement happens on startup before daily reset.
        self.handle_new_day_rollover(show_popup=True)
        self.schedule_daily_check()

    def on_closing(self):
        if self.timer_id: self.after_cancel(self.timer_id)
        self.destroy()
        sys.exit(0)

    def update_date_label(self):
        today_str_full = datetime.now().strftime("%Y年%m月%d日")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_text = weekdays[datetime.now().weekday()]
        holiday_suffix = ""

        info = get_holiday_info(datetime.now().strftime("%Y-%m-%d"))
        if info:
            holiday = info.get("holiday")
            if isinstance(holiday, dict):
                if holiday.get("holiday") is True:
                    holiday_suffix = f" · 节假日: {holiday.get('name', '')}".rstrip()
                elif holiday.get("holiday") is False:
                    holiday_suffix = f" · 调休补班: {holiday.get('name', '')}".rstrip()
            if not holiday_suffix:
                day_type = info.get("type", {}).get("type")
                if day_type == 2:
                    holiday_suffix = " · 节假日"
                elif day_type == 3:
                    holiday_suffix = " · 调休补班"

        self.date_label.config(text=f"📅 {today_str_full} {weekday_text}{holiday_suffix}")

    def force_window_front(self, win):
        try:
            self.attributes("-topmost", True)
            win.attributes("-topmost", True)
            win.lift()
            win.focus_force()
            self.after(200, lambda: self.attributes("-topmost", False))
            win.after(300, lambda: win.attributes("-topmost", False))
        except Exception:
            pass

    def schedule_daily_check(self):
        def check_rollover():
            now_str = datetime.now().strftime("%Y-%m-%d")
            if now_str != self.current_date_str:
                self.current_date_str = now_str
                self.handle_new_day_rollover()
            self.check_review_reminder()
            self.after(60 * 1000, check_rollover)

        self.after(60 * 1000, check_rollover)

    def check_review_reminder(self):
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        if now.hour != 23:
            return
        if now.minute < 30:
            return
        if global_data.get("today_review_submitted"):
            return
        if app_config.get("review_reminder_date") == today_str:
            return
        self.attributes('-topmost', True)
        messagebox.showinfo("⚠️ 复盘提醒", "现在距离零点不远了，请尽快提交【今日复盘】！\n\n点击“确认”后继续使用。", parent=self)
        self.attributes('-topmost', False)
        app_config["review_reminder_date"] = today_str
        save_app_config()

    def export_task_reports(self):
        import csv
        data_dir = app_config.get("data_dir")
        if not data_dir or not os.path.exists(data_dir):
            return
            
        by_date = {}
        by_cat = {}

        # 取消勾选“删除表格记录”只影响报表导出：通过排除清单跳过对应记录，不删除看板历史
        exclusions = global_data.get("report_exclusions", [])
        excluded_focus = set()
        excluded_history = set()
        for ex in exclusions:
            try:
                t = ex.get("type")
                if t == "focus_log":
                    excluded_focus.add((ex.get("start"), ex.get("end"), ex.get("category"), ex.get("task")))
                elif t == "study_history":
                    excluded_history.add((ex.get("date"), ex.get("category"), ex.get("task"), ex.get("study_time")))
            except Exception:
                pass

        def record(date_str, cat, task, dur):
            if dur <= 0: return
            if date_str not in by_date:
                by_date[date_str] = {}
            k = f"{cat}::{task}"
            if k not in by_date[date_str]:
                by_date[date_str][k] = {"cat": cat, "task": task, "dur": 0}
            by_date[date_str][k]["dur"] += dur
            
            if cat not in by_cat:
                by_cat[cat] = {}
            if task not in by_cat[cat]:
                by_cat[cat][task] = {"dates": set(), "dur": 0}
            by_cat[cat][task]["dates"].add(date_str)
            by_cat[cat][task]["dur"] += dur

        # 1. 提取 study_history (包含 科研/理论 的番茄用时)
        for item in global_data.get("study_history", []):
            try:
                dt_full = item.get("date", "")
                dt_str = dt_full.split()[0]
                dur = item.get("study_time", item.get("duration", 0))
                cat = item.get("category", "其他")
                task = item.get("task", "未知任务")
                if (dt_full, cat, task, dur) in excluded_history:
                    continue
                if len(dt_str) == 10 and dur > 0:
                    record(dt_str, cat, task, dur)
            except Exception:
                pass

        # 2. 提取 focus_logs (包含 生活/兴趣爱好 的手动记录时间)
        for log in global_data.get("focus_logs", []):
            try:
                cat = log.get("category", "")
                if cat in ["科研", "理论/技术"]:
                    continue  # 避免与 study_history 重复计算
                task = log.get("task", "未知任务")
                start_str = log.get("start")
                end_str = log.get("end")
                if (start_str, end_str, cat, task) in excluded_focus:
                    continue
                s = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
                e = datetime.strptime(end_str, "%Y-%m-%d %H:%M")
                dur = int((e - s).total_seconds() / 60)
                if dur > 0:
                    record(s.strftime("%Y-%m-%d"), cat, task, dur)
            except Exception:
                pass

        try:
            file_date = os.path.join(data_dir, "任务复盘报表_按日期.csv")
            with open(file_date, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["日期", "任务分类", "子任务明细", "当日专注时长(分钟)"])
                for d in sorted(by_date.keys(), reverse=True):
                    for k, v in by_date[d].items():
                        writer.writerow([d, v["cat"], v["task"], v["dur"]])

            file_cat = os.path.join(data_dir, "任务复盘报表_按分类汇总.csv")
            with open(file_cat, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["任务分类", "子任务明细", "总计专注时长(分钟)", "坚持天数", "参与的打卡日期"])
                for cat in TASK_CATS + [c for c in by_cat.keys() if c not in TASK_CATS]:
                    if cat not in by_cat: continue
                    tasks = sorted(by_cat[cat].items(), key=lambda x: x[1]["dur"], reverse=True)
                    for task, v in tasks:
                        dates_list = sorted(list(v["dates"]))
                        writer.writerow([cat, task, v["dur"], len(dates_list), "、".join(dates_list)])

            # 写入成功：允许下次失败时再次弹窗提示
            self._report_write_permission_alerted = False
        except PermissionError as e:
            print("写入CSV报表失败:", e)
            if not getattr(self, "_report_write_permission_alerted", False):
                self._report_write_permission_alerted = True
                messagebox.showwarning(
                    "报表写入失败",
                    "CSV报表正在被占用，无法实时更新。\n\n"
                    "请关闭正在打开的报表文件（Excel/WPS），再勾选/取消勾选一次即可刷新。",
                    parent=self,
                )
        except Exception as e:
            print("写入CSV报表失败:", e)

    def handle_new_day_rollover(self, show_popup=False):
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_date = datetime.now().date()
        last_checkin_str = global_data.get("last_checkin_date")
        settlement_msg = None

        if last_checkin_str != today_str:
            tasks_snapshot = {
                cat: [dict(t) for t in global_data.get("today_structured_tasks", {}).get(cat, [])]
                for cat in TASK_CATS
            }
            if last_checkin_str:
                self.log_daily_task_time(last_checkin_str, tasks_snapshot)
            carryover_tasks = {
                cat: [t for t in tasks_snapshot.get(cat, []) if not t.get("done")]
                for cat in TASK_CATS
            }
            if last_checkin_str:
                settlement_msg = f"已结算昨日({last_checkin_str})"
            if last_checkin_str and global_data.get("last_penalty_date") != last_checkin_str:
                total_tasks, done_tasks, rate = self.get_task_completion_stats()
                settlement_note = ""
                if global_data.get("today_task_submitted") and total_tasks > 0:
                    reward = self.get_reward_by_rate(rate)
                    penalty = self.get_penalty_by_rate(rate)
                    delta = 0
                    title = "【自动结算】"
                    if reward > 0:
                        delta = reward
                        title = "【自动奖励】"
                        global_data["total_points"] += reward
                    elif penalty < 0:
                        delta = penalty
                        title = "【自动惩罚】"
                        global_data["total_points"] = max(0, global_data["total_points"] + penalty)

                    self.upsert_daily_reward_history(last_checkin_str, rate, delta)
                    settlement_note = f"完成率 {done_tasks}/{total_tasks} ({rate:.0f}%)，奖惩 {delta} 分"

                    if delta != 0:
                        task_status_text = ""
                        if penalty < 0:
                            task_status_text = self.build_task_status_lines(global_data.get("today_structured_tasks", {}))
                        log_text = (
                            f"{title}\n"
                            f"日期: {last_checkin_str}\n"
                            f"完成率 {done_tasks}/{total_tasks} ({rate:.0f}%)\n"
                            f"奖惩 {delta} 分\n"
                            f"{task_status_text}"
                            f"{'='*40}\n"
                        )
                        self.log_to_txt("review", log_text)
                else:
                    settlement_note = "昨日未提交任务清单，未结算奖惩"
                if settlement_msg and settlement_note:
                    settlement_msg = f"{settlement_msg}\n{settlement_note}"
                global_data["last_penalty_date"] = last_checkin_str

            if last_checkin_str:
                last_date = datetime.strptime(last_checkin_str, "%Y-%m-%d").date()
                if (today_date - last_date).days == 1:
                    global_data["continuous_checkin_days"] = global_data.get("continuous_checkin_days", 0) + 1
                else:
                    global_data["continuous_checkin_days"] = 1
            else:
                global_data["continuous_checkin_days"] = 1

            global_data["today_tomatoes"] = 0
            global_data["today_study_time"] = 0
            global_data["today_exchanged_time"] = 0
            global_data["today_incentive_pool"] = 0
            global_data["today_structured_tasks"] = carryover_tasks
            
            # ====== 注入长期任务 ======
            month_day = today_date.strftime("%m%d")
            for lt_task in global_data.get("long_term_tasks", []):
                try:
                    start_date = datetime.strptime(lt_task["start_date"], "%Y-%m-%d").date()
                    end_date = start_date + timedelta(days=lt_task["days"] - 1)
                    if start_date <= today_date <= end_date:
                        cat = lt_task["cat"]
                        formatted_text = f"（长期）{lt_task['text']}（{month_day}）"
                        exists = any(t['text'] == formatted_text for t in global_data["today_structured_tasks"].get(cat, []))
                        if not exists:
                            global_data["today_structured_tasks"].setdefault(cat, []).append({
                                "text": formatted_text,
                                "done": False,
                                "req_time": lt_task["req_time"]
                            })
                except Exception as e:
                    print("解析长期任务失败:", e)

            # 更新 today_task_submitted 状态，以防只有长期任务
            global_data["today_task_submitted"] = any(global_data["today_structured_tasks"].get(cat) for cat in TASK_CATS)

            global_data["today_review_text"] = ""
            global_data["last_checkin_date"] = today_str
            save_data()

        # 每次跨天检查/结算后，都会重新导出一份最新报表
        self.export_task_reports()

        self.update_date_label()
        self.update_dashboard()
        self.update_task_buttons()
        self.update_task_status_label()
        if show_popup and settlement_msg:
            messagebox.showinfo("启动结算完成", settlement_msg, parent=self)

    def create_widgets(self):
        self.header_frame = tk.Frame(self, bg="#FFB6C1", pady=10)
        self.header_frame.pack(fill=tk.X)
        
        today_str_full = datetime.now().strftime("%Y年%m月%d日")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        self.date_label = tk.Label(self.header_frame, text=f"📅 {today_str_full} {weekdays[datetime.now().weekday()]}", font=("Microsoft YaHei", 10), bg="#FFB6C1", fg="#FFFFFF")
        self.date_label.pack(pady=(0, 2))

        self.task_status_label = tk.Label(self.header_frame, text="", font=("Microsoft YaHei", 10, "bold"), bg="#FFB6C1", fg="#FFFFE0")
        self.task_status_label.pack()

        self.penalty_hint_label = tk.Label(self.header_frame, text="", font=("Microsoft YaHei", 9), bg="#FFB6C1", fg="#FFFFFF")
        self.penalty_hint_label.pack(pady=(2, 0))
        
        self.points_label = tk.Label(self.header_frame, text="🪙 积分: 0", font=("Microsoft YaHei", 20, "bold"), bg="#FFB6C1", fg="#FFFFFF")
        self.points_label.pack()
        
        self.games_label = tk.Label(self.header_frame, text="✨ 今日还有多少时间改变自己: 0 分钟 | 额度: ∞", font=("Microsoft YaHei", 11), bg="#FFB6C1", fg="#FFFFFF")
        self.games_label.pack(pady=2)

        self.discount_info_label = tk.Label(self.header_frame, text="", font=("Microsoft YaHei", 9, "bold"), bg="#FFB6C1", fg="#FFFFE0")
        self.discount_info_label.pack(pady=(2, 2))

        self.body_frame = tk.Frame(self, bg="#FFF0F5")
        self.body_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # ====== 左侧列 ======
        self.left_frame = tk.Frame(self.body_frame, bg="#FFF0F5")
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self.timer_label = tk.Label(self.left_frame, text="25:00", font=("Arial", 48, "bold"), bg="#FFF0F5", fg="#FF69B4")
        self.timer_label.pack(pady=(15, 5))
        
        self.stage_label = tk.Label(self.left_frame, text="准备开始专注", font=("Microsoft YaHei", 12), bg="#FFF0F5", fg="#888888", wraplength=320, justify=tk.LEFT, anchor="w")
        self.stage_label.pack(pady=(0, 15))

        btn_style = {"font": ("Microsoft YaHei", 12, "bold"), "fg": "white", "width": 20, "pady": 8, "bd": 0, "cursor": "hand2"}

        self.btn_tomato = tk.Button(self.left_frame, text="🍅 开始专注 (25分钟)", bg="#FF69B4", activebackground="#FF1493", command=self.on_tomato_button, **btn_style)
        self.btn_tomato.pack(pady=6)

        self.btn_cancel = tk.Button(self.left_frame, text="⏹️ 放弃当前计时", bg="#CCCCCC", activebackground="#A9A9A9", command=self.cancel_timer, state=tk.DISABLED, **btn_style)
        self.btn_cancel.pack(pady=6)

        self.frame_tasks = tk.Frame(self.left_frame, bg="#FFF0F5")
        self.frame_tasks.pack(pady=6)
        
        self.btn_daily_task = tk.Button(self.frame_tasks, text="📝 制定每日清单", bg="#87CEFA", activebackground="#00BFFF", command=self.open_task_editor, **btn_style)
        
        self.frame_two_btns = tk.Frame(self.frame_tasks, bg="#FFF0F5")
        self.btn_view_task = tk.Button(self.frame_two_btns, text="✅ 任务打卡看板", bg="#87CEFA", fg="white", font=("Microsoft YaHei", 11, "bold"), width=11, bd=0, pady=8, cursor="hand2", command=self.open_task_viewer)
        self.btn_review_task = tk.Button(self.frame_two_btns, text="📝 今日复盘", bg="#FFD700", fg="white", font=("Microsoft YaHei", 11, "bold"), width=9, bd=0, pady=8, cursor="hand2", command=self.open_review)
        self.btn_view_task.pack(side=tk.LEFT, padx=5)
        self.btn_review_task.pack(side=tk.LEFT, padx=5)

        self.update_task_buttons()

        # ====== 右侧列 ======
        self.right_frame = tk.Frame(self.body_frame, bg="#FFF0F5")
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        tk.Frame(self.right_frame, height=20, bg="#FFF0F5").pack() 
        self.btn_exchange = tk.Button(self.right_frame, text="🎮 兑换商店", bg="#98FB98", activebackground="#32CD32", command=self.open_exchange_shop, **btn_style)
        self.btn_exchange.pack(pady=6)
        self.btn_stats = tk.Button(self.right_frame, text="📊 查看高级数据与图表", bg="#DDA0DD", activebackground="#BA55D3", command=self.show_charts_window, **btn_style)
        self.btn_stats.pack(pady=6)
        self.btn_memo = tk.Button(self.right_frame, text="💡 随手记 (文件/图文归档)", bg="#FFB6C1", activebackground="#FF69B4", command=self.open_memo_window, **btn_style)
        self.btn_memo.pack(pady=6)
        self.btn_work_log = tk.Button(self.right_frame, text="📒 今日工作日志", bg="#FFB07C", activebackground="#FF8C42", command=self.open_work_log_window, **btn_style)
        self.btn_work_log.pack(pady=6)
        self.btn_change_dir = tk.Button(self.right_frame, text="📁 更改数据存储目录", bg="#B0C4DE", activebackground="#778899", command=self.change_data_directory, font=("Microsoft YaHei", 11, "bold"), fg="white", width=20, pady=6, bd=0, cursor="hand2")
        self.btn_change_dir.pack(pady=6)

    def update_task_status_label(self):
        tasks_dict = global_data.get("today_structured_tasks", {})
        total_tasks = sum(len(items) for items in tasks_dict.values())
        done_tasks = sum(1 for items in tasks_dict.values() for t in items if t.get("done"))
        
        if total_tasks == 0:
            self.task_status_label.config(text="⚠️ 今日您还没有添加任务！", fg="#FF6347")
        elif done_tasks == total_tasks:
            self.task_status_label.config(text="🎉 真棒！！今日任务全部完成", fg="#32CD32")
        else:
            self.task_status_label.config(text=f"🔥 今日还有 {total_tasks - done_tasks} 个任务未完成", fg="#FFFFE0")

        if total_tasks == 0:
            self.penalty_hint_label.config(text="📌 未设定任务，暂无扣分")
        else:
            rate = (done_tasks / total_tasks) * 100
            penalty = self.get_penalty_by_rate(rate)
            if penalty < 0:
                self.penalty_hint_label.config(text=f"⚠️ 当前完成率 {rate:.0f}%，若保持将扣 {abs(penalty)} 分")
            else:
                self.penalty_hint_label.config(text=f"✅ 当前完成率 {rate:.0f}%，无扣分")

    def update_task_buttons(self):
        self.btn_daily_task.pack_forget()
        self.frame_two_btns.pack_forget()
        if global_data.get("today_task_submitted"):
            self.frame_two_btns.pack()
        else:
            self.btn_daily_task.pack()

    def on_tomato_button(self):
        if not self.timer_running:
            self.start_tomato_dialog_by_action("start")
            return
        if self.current_stage == "study":
            self.start_tomato_dialog_by_action("change")
            return

    def split_duration_by_day(self, start_dt, duration_mins):
        segments = []
        curr_dt = start_dt
        mins_left = duration_mins
        while mins_left > 0:
            next_day = (curr_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            mins_in_day = int((next_day - curr_dt).total_seconds() / 60)
            if mins_left <= mins_in_day:
                segments.append((curr_dt, mins_left))
                break
            segments.append((curr_dt, mins_in_day))
            mins_left -= mins_in_day
            curr_dt = next_day
        return segments

    def get_daily_minutes_for_study(self, target_date_str):
        total = 0
        for item in global_data.get("study_history", []):
            end_dt = datetime.strptime(item["date"], "%Y-%m-%d %H:%M:%S")
            duration = item["study_time"]
            start_dt = end_dt - timedelta(minutes=duration)
            for seg_start, seg_mins in self.split_duration_by_day(start_dt, duration):
                if seg_start.strftime("%Y-%m-%d") == target_date_str:
                    total += seg_mins
        return total

    def get_daily_minutes_for_exchange(self, target_date_str):
        total = 0
        for item in global_data.get("exchange_history", []):
            start_dt = datetime.strptime(item["date"], "%Y-%m-%d %H:%M:%S")
            duration = item["exchange_time"]
            for seg_start, seg_mins in self.split_duration_by_day(start_dt, duration):
                if seg_start.strftime("%Y-%m-%d") == target_date_str:
                    total += seg_mins
        return total

    def get_task_completion_stats(self):
        tasks_dict = global_data.get("today_structured_tasks", {})
        total = sum(len(items) for items in tasks_dict.values())
        done = sum(1 for items in tasks_dict.values() for t in items if t.get("done"))
        if total == 0:
            return 0, 0, 0.0
        rate = (done / total) * 100
        return total, done, rate

    def get_penalty_by_rate(self, rate):
        if rate >= 60:
            return 0
        if rate >= 50:
            base = -20
        elif rate >= 40:
            base = -50
        elif rate >= 30:
            base = -90
        elif rate >= 20:
            base = -140
        else:
            base = -200
        return int(round(base * PENALTY_MULTIPLIER))

    def format_minutes(self, minutes):
        mins = int(round(minutes))
        if mins < 60:
            return f"{mins}min"
        h, m = divmod(mins, 60)
        return f"{h}h{m}min"

    def normalize_dt(self, dt_obj):
        return dt_obj.replace(second=0, microsecond=0)

    def get_today_focus_logs(self, include_current=False):
        today_str = datetime.now().strftime("%Y-%m-%d")
        logs = []
        for item in global_data.get("focus_logs", []):
            if item.get("start", "").startswith(today_str):
                logs.append(item)
        if include_current and self.timer_running and self.current_stage == "study" and self.current_focus_task and self.focus_segment_start_dt:
            now_dt = self.normalize_dt(datetime.now())
            start_dt = self.normalize_dt(self.focus_segment_start_dt)
            if now_dt > start_dt:
                logs.append({
                    "start": start_dt.strftime("%Y-%m-%d %H:%M"),
                    "end": now_dt.strftime("%Y-%m-%d %H:%M"),
                    "category": self.current_focus_task["cat"],
                    "task": self.current_focus_task["text"]
                })
        return logs

    def append_focus_log(self, start_dt, end_dt, cat, text):
        start_dt = self.normalize_dt(start_dt)
        end_dt = self.normalize_dt(end_dt)
        if end_dt <= start_dt:
            return
        global_data.setdefault("focus_logs", []).append({
            "start": start_dt.strftime("%Y-%m-%d %H:%M"),
            "end": end_dt.strftime("%Y-%m-%d %H:%M"),
            "category": cat,
            "task": text
        })
        save_data()

    def check_focus_conflict(self, start_dt, end_dt):
        for item in self.get_today_focus_logs(include_current=True):
            try:
                existing_start = datetime.strptime(item["start"], "%Y-%m-%d %H:%M")
                existing_end = datetime.strptime(item["end"], "%Y-%m-%d %H:%M")
            except Exception:
                continue
            if start_dt < existing_end and end_dt > existing_start:
                conflict_range = f"{existing_start.strftime('%H:%M')} —— {existing_end.strftime('%H:%M')}"
                conflict_task = f"<{item.get('category', '')}>-{item.get('task', '')}"
                return conflict_range, conflict_task
        return None, None

    def collect_manual_focus_time(self, cat, task_text):
        dialog = tk.Toplevel(self)
        dialog.title("选择专注时间")
        dialog.geometry("360x220")
        dialog.configure(bg="#FFF0F5")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text=f"任务: <{cat}>-{task_text}", bg="#FFF0F5", font=("Microsoft YaHei", 9, "bold")).pack(pady=(10, 6))

        hours = [f"{h:02d}" for h in range(24)]
        minutes = [""] + [f"{m:02d}" for m in range(60)]

        def build_row(label):
            row = tk.Frame(dialog, bg="#FFF0F5")
            row.pack(pady=4)
            tk.Label(row, text=label, bg="#FFF0F5", width=6).pack(side=tk.LEFT)
            hour_var = tk.StringVar()
            min_var = tk.StringVar()
            hour_cb = ttk.Combobox(row, textvariable=hour_var, values=hours, width=4, state="readonly")
            min_cb = ttk.Combobox(row, textvariable=min_var, values=minutes, width=4, state="readonly")
            hour_cb.pack(side=tk.LEFT, padx=4)
            tk.Label(row, text=":", bg="#FFF0F5").pack(side=tk.LEFT)
            min_cb.pack(side=tk.LEFT, padx=4)
            return hour_var, min_var

        start_hour_var, start_min_var = build_row("开始")
        end_hour_var, end_min_var = build_row("结束")

        result = {"ok": False}

        def confirm():
            if not start_hour_var.get() or not end_hour_var.get():
                messagebox.showwarning("填写不完整", "请至少选择开始和结束的小时。", parent=dialog)
                return
            sh = int(start_hour_var.get())
            sm = int(start_min_var.get() or "0")
            eh = int(end_hour_var.get())
            em = int(end_min_var.get() or "0")

            today = datetime.now().strftime("%Y-%m-%d")
            start_dt = datetime.strptime(f"{today} {sh:02d}:{sm:02d}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{today} {eh:02d}:{em:02d}", "%Y-%m-%d %H:%M")
            now_dt = self.normalize_dt(datetime.now())
            latest_end = None
            for item in self.get_today_focus_logs(include_current=True):
                try:
                    existing_end = datetime.strptime(item["end"], "%Y-%m-%d %H:%M")
                except Exception:
                    continue
                if latest_end is None or existing_end > latest_end:
                    latest_end = existing_end
            if latest_end and start_dt < latest_end:
                messagebox.showwarning("时间错误", f"开始时间必须晚于已有记录结束时间：{latest_end.strftime('%H:%M')}", parent=dialog)
                return
            if end_dt > now_dt:
                messagebox.showwarning("时间错误", "结束时间必须早于当前时间。", parent=dialog)
                return
            if end_dt <= start_dt:
                messagebox.showwarning("时间错误", "结束时间必须晚于开始时间。", parent=dialog)
                return

            conflict_range, conflict_task = self.check_focus_conflict(start_dt, end_dt)
            if conflict_range:
                messagebox.showwarning("时间冲突", f"所选时间与已有记录冲突：\n{conflict_range} {conflict_task}", parent=dialog)
                return

            self.append_focus_log(start_dt, end_dt, cat, task_text)
            result["ok"] = True
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg="#FFF0F5")
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="确认", bg="#87CEFA", fg="white", width=8, command=confirm).pack(side=tk.RIGHT, padx=6)
        tk.Button(btn_frame, text="取消", bg="#CCCCCC", fg="black", width=8, command=dialog.destroy).pack(side=tk.RIGHT)

        self.wait_window(dialog)
        return result["ok"]

    def open_work_log_window(self):
        win = tk.Toplevel(self)
        win.title("📒 今日工作日志")
        win.geometry("620x560")
        win.configure(bg="white")
        win.transient(self)
        win.grab_set()

        logs = self.get_today_focus_logs(include_current=True)
        logs.sort(key=lambda x: x.get("start", ""))

        tk.Label(win, text="今日专注日志", font=("Microsoft YaHei", 10, "bold"), bg="white").pack(anchor="w", padx=12, pady=(10, 4))

        log_frame = tk.Frame(win, bg="white")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12)
        log_text = tk.Text(log_frame, height=10, font=("Microsoft YaHei", 9), wrap="none")
        log_scroll = tk.Scrollbar(log_frame, command=log_text.yview)
        log_text.configure(yscrollcommand=log_scroll.set)
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        if not logs:
            log_text.insert(tk.END, "暂无记录\n")
        else:
            for item in logs:
                try:
                    start_dt = datetime.strptime(item["start"], "%Y-%m-%d %H:%M")
                    end_dt = datetime.strptime(item["end"], "%Y-%m-%d %H:%M")
                except Exception:
                    continue
                line = f"{start_dt.strftime('%H:%M')} —— {end_dt.strftime('%H:%M')} <{item.get('category', '')}>-{item.get('task', '')}\n"
                log_text.insert(tk.END, line)
        log_text.configure(state=tk.DISABLED)

        tk.Label(win, text="已完成任务耗时", font=("Microsoft YaHei", 10, "bold"), bg="white").pack(anchor="w", padx=12, pady=(12, 4))

        done_frame = tk.Frame(win, bg="white")
        done_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
        done_text = tk.Text(done_frame, height=10, font=("Microsoft YaHei", 9), wrap="none")
        done_scroll = tk.Scrollbar(done_frame, command=done_text.yview)
        done_text.configure(yscrollcommand=done_scroll.set)
        done_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        done_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        totals = {}
        for item in logs:
            try:
                start_dt = datetime.strptime(item["start"], "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(item["end"], "%Y-%m-%d %H:%M")
            except Exception:
                continue
            mins = (end_dt - start_dt).total_seconds() / 60.0
            key = (item.get("category", ""), item.get("task", ""))
            totals[key] = totals.get(key, 0) + mins

        tasks_dict = global_data.get("today_structured_tasks", {})
        has_done = False
        for cat in TASK_CATS:
            for t in tasks_dict.get(cat, []):
                if not t.get("done"):
                    continue
                has_done = True
                mins = totals.get((cat, t.get("text", "")), 0)
                line = f"√已完成——耗时{self.format_minutes(mins)}——<{cat}>-{t.get('text', '')}\n"
                done_text.insert(tk.END, line)

        if not has_done:
            done_text.insert(tk.END, "暂无已完成任务\n")
        done_text.configure(state=tk.DISABLED)

    def get_reward_by_rate(self, rate):
        if rate >= 100:
            base = 200
        elif rate >= 80:
            base = 80
        elif rate >= 70:
            base = 30
        else:
            base = 0
        return int(round(base * PENALTY_MULTIPLIER))

    def build_task_status_lines(self, tasks_dict):
        done_lines = []
        undone_lines = []
        for cat in TASK_CATS:
            for t in tasks_dict.get(cat, []):
                text = t.get("text", "")
                line = f"<{cat}>-{text}"
                if t.get("done"):
                    done_lines.append(f"√已完成——{line}")
                else:
                    undone_lines.append(f"×未完成——{line}")
        lines = []
        lines.extend(done_lines)
        lines.extend(undone_lines)
        if not lines:
            return ""
        return "\n".join(lines) + "\n"

    def is_duplicate_task_text(self, text):
        normalized = text.strip().casefold()
        if not normalized:
            return False
        for items in global_data.get("today_structured_tasks", {}).values():
            for t in items:
                if t.get("text", "").strip().casefold() == normalized:
                    return True
        return False

    def upsert_daily_reward_history(self, date_str, rate, reward):
        history = global_data.get("daily_rewards_history", [])
        updated = False
        for item in history:
            if item.get("date") == date_str:
                item["rate"] = rate
                item["reward"] = reward
                updated = True
                break
        if not updated:
            history.append({"date": date_str, "rate": rate, "reward": reward})
        history = sorted(history, key=lambda x: x.get("date", ""))[-365:]
        global_data["daily_rewards_history"] = history

    # ====================================
    # ====== 新版 Todo 清单编辑器 ======
    # ====================================
    
    def add_long_term_task_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("新增长期任务")
        dialog.geometry("350x300")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="任务名称:").pack(pady=5)
        name_entry = tk.Entry(dialog, width=30)
        name_entry.pack()

        tk.Label(dialog, text="所属分类:").pack(pady=5)
        cat_combo = ttk.Combobox(dialog, values=TASK_CATS, state="readonly", width=28)
        cat_combo.current(0)
        cat_combo.pack()

        tk.Label(dialog, text="持续天数 (例如 10):").pack(pady=5)
        days_entry = tk.Entry(dialog, width=30)
        days_entry.pack()

        tk.Label(dialog, text="每日需专注分钟数 (例如 30):").pack(pady=5)
        mins_entry = tk.Entry(dialog, width=30)
        mins_entry.pack()

        def submit():
            text = name_entry.get().strip()
            cat = cat_combo.get()
            try:
                days = int(days_entry.get().strip())
                req_time = int(mins_entry.get().strip())
            except ValueError:
                messagebox.showerror("错误", "天数和分钟数必须为整数！", parent=dialog)
                return
            
            if not text:
                return

            if "long_term_tasks" not in global_data:
                global_data["long_term_tasks"] = []

            today_str = datetime.now().strftime("%Y-%m-%d")
            global_data["long_term_tasks"].append({
                "text": text,
                "cat": cat,
                "start_date": today_str,
                "days": days,
                "req_time": req_time
            })
            
            # 手动注入今天的任务字典，因为今天已经过了跨天结算
            month_day = datetime.now().strftime("%m%d")
            formatted_text = f"（长期）{text}（{month_day}）"
            exists = any(t['text'] == formatted_text for t in global_data["today_structured_tasks"].get(cat, []))
            if not exists:
                global_data["today_structured_tasks"].setdefault(cat, []).append({
                    "text": formatted_text,
                    "done": False,
                    "req_time": req_time
                })
            
            save_data()
            
            # 由于可能当前时间界面需要刷新
            self.handle_new_day_rollover(show_popup=False)
            messagebox.showinfo("成功", f"长期任务【{text}】已添加！\n\n请重新打开或者刷新【任务打卡看板】即可看到最新任务。", parent=dialog)
            dialog.destroy()
            self.update_dashboard()
            self.update_task_buttons()
            self.update_task_status_label()

        tk.Button(dialog, text="保存", bg="#90EE90", command=submit).pack(pady=15)

    def open_task_editor(self):
        editor = tk.Toplevel(self)
        editor.title("📝 制定今日 Todo 清单")
        editor.geometry("500x650")
        editor.configure(bg="white")
        editor.transient(self)
        editor.grab_set()

        canvas = tk.Canvas(editor, bg="white", highlightthickness=0)
        scrollbar = tk.Scrollbar(editor, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=460)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y")

        tk.Label(scrollable_frame, text="请添加今日任务小点 (科研/理论属学习类，将记录番茄)", bg="white", fg="gray", font=("Microsoft YaHei", 9)).pack(pady=(0,10))

        def submit_tasks():
            total = sum(len(items) for items in global_data["today_structured_tasks"].values())
            if total == 0:
                messagebox.showwarning("无法提交", "四大分类中总共至少需要添加 1 个任务小点才能提交！", parent=editor)
                return
            global_data["today_task_submitted"] = True
            save_data()
            self.update_task_buttons()
            self.update_task_status_label()
            
            log_text = ""
            for cat in TASK_CATS:
                items = global_data["today_structured_tasks"].get(cat, [])
                if items:
                    log_text += f"[{cat}]\n"
                    for i, t in enumerate(items): log_text += f"{i+1}. {t['text']}\n"
            self.log_to_txt("task_update", log_text)
            
            editor.destroy()
            messagebox.showinfo("提交成功", "今日任务已设定！你可以开始打卡和计时的旅程了。")

        def refresh_editor_ui():
            for widget in scrollable_frame.winfo_children():
                # 保留最顶部的提示语不删
                if isinstance(widget, tk.Frame) or isinstance(widget, tk.Button):
                    widget.destroy()
            
            for cat in TASK_CATS:
                cat_frame = tk.Frame(scrollable_frame, bg="#F5F5F5", pady=10, padx=10)
                cat_frame.pack(fill=tk.X, pady=5)
                
                title_color = "#FF69B4" if cat in ["科研", "理论/技术"] else "#20B2AA"
                tk.Label(cat_frame, text=f"■ {cat}", font=("Microsoft YaHei", 11, "bold"), fg=title_color, bg="#F5F5F5").pack(anchor="w")

                tasks = global_data["today_structured_tasks"].get(cat, [])
                for idx, t in enumerate(tasks):
                    item_frame = tk.Frame(cat_frame, bg="#F5F5F5")
                    item_frame.pack(fill=tk.X, pady=2, padx=15)
                    
                    # ✅ 核心修复：先 pack 右侧按钮，确保它占据固定位置绝对不被挤掉
                    btn_del = tk.Button(item_frame, text="删除", font=("Microsoft YaHei", 8), bg="#FFB6C1", fg="white", bd=0, command=lambda c=cat, i=idx: delete_task(c, i))
                    btn_del.pack(side=tk.RIGHT, anchor="n", padx=(5, 0), pady=2)
                    
                    # ✅ 核心修复：添加 wraplength 属性让过长的文本自动换行，且 justify 靠左
                    lbl = tk.Label(item_frame, text=f"• {t['text']}", font=("Microsoft YaHei", 10), bg="#F5F5F5", justify=tk.LEFT, anchor="w", wraplength=340)
                    lbl.pack(side=tk.LEFT, fill=tk.X)

                add_frame = tk.Frame(cat_frame, bg="#F5F5F5")
                add_frame.pack(fill=tk.X, pady=(5,0), padx=15)
                entry = tk.Entry(add_frame, width=35, font=("Microsoft YaHei", 10))
                entry.pack(side=tk.LEFT, padx=(0,10))
                btn_add = tk.Button(add_frame, text="添加", font=("Microsoft YaHei", 9), bg="#87CEFA", fg="white", bd=0, command=lambda c=cat, e=entry: add_task(c, e))
                btn_add.pack(side=tk.LEFT)

            btn_long_term = tk.Button(scrollable_frame, text="➕ 新增长期任务", bg="#FFD700", fg="black", font=("Microsoft YaHei", 12, "bold"), bd=0, pady=10, command=self.add_long_term_task_dialog)
            btn_long_term.pack(fill=tk.X, padx=10, pady=(10, 5))

            btn_submit = tk.Button(scrollable_frame, text="🚀 完成设定并提交", bg="#32CD32", fg="white", font=("Microsoft YaHei", 12, "bold"), bd=0, pady=10, command=submit_tasks)
            btn_submit.pack(fill=tk.X, padx=10, pady=(5, 20))

        def add_task(cat, entry_widget):
            text = entry_widget.get().strip()
            if not text:
                return
            if self.is_duplicate_task_text(text):
                messagebox.showwarning("重复任务", "已存在同名任务，不能重复添加。", parent=editor)
                return
            global_data["today_structured_tasks"][cat].append({"text": text, "done": False})
            entry_widget.delete(0, tk.END)
            refresh_editor_ui()

        def delete_task(cat, idx):
            del global_data["today_structured_tasks"][cat][idx]
            refresh_editor_ui()

        refresh_editor_ui()

    # ====================================
    # ====== 新版 Todo 任务打卡看板 ======
    # ====================================
    def open_task_viewer(self):
        viewer = tk.Toplevel(self)
        viewer.title("✅ 今日打卡看板")
        viewer.geometry("420x560")
        viewer.configure(bg="#20B2AA") 
        viewer.transient(self)

        container = tk.Frame(viewer, bg="#20B2AA")
        container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        canvas = tk.Canvas(container, bg="#F0FFF0", highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        main_frame = tk.Frame(canvas, bg="#F0FFF0")

        main_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=main_frame, anchor="nw", width=380)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.cat_labels = {}
        self.cat_frames = {}
        self.task_cbs = {} 
        self.task_cancel_btns = {}

        def toggle_task(cat, idx):
            var, cb = self.task_cbs[(cat, idx)]
            is_done = var.get()
            
            task_item = global_data["today_structured_tasks"][cat][idx]
            task_text = task_item["text"]

            # 实时同步报表：
            # - 勾选：如果之前误取消过，则撤回一条“报表排除项”，让记录立刻回到CSV
            # - 取消勾选：新增一条“报表排除项”，让记录立刻从CSV消失（但不删除历史数据）
            restored = False
            if is_done:
                today_str = datetime.now().strftime("%Y-%m-%d")
                exclusions = global_data.setdefault("report_exclusions", [])

                if cat in ["生活", "兴趣爱好"]:
                    latest_ex_idx = None
                    latest_ex_start = None
                    for i, ex in enumerate(exclusions):
                        if ex.get("type") != "focus_log":
                            continue
                        if ex.get("category") != cat or ex.get("task") != task_text:
                            continue
                        s = ex.get("start", "")
                        if not s.startswith(today_str):
                            continue
                        if latest_ex_start is None or s > latest_ex_start:
                            latest_ex_start = s
                            latest_ex_idx = i
                    if latest_ex_idx is not None:
                        del exclusions[latest_ex_idx]
                        restored = True

                if cat in ["科研", "理论/技术"] and not restored:
                    latest_ex_idx = None
                    latest_ex_date = None
                    for i, ex in enumerate(exclusions):
                        if ex.get("type") != "study_history":
                            continue
                        if ex.get("category") != cat or ex.get("task") != task_text:
                            continue
                        d = ex.get("date", "")
                        if not d.startswith(today_str):
                            continue
                        if latest_ex_date is None or d > latest_ex_date:
                            latest_ex_date = d
                            latest_ex_idx = i
                    if latest_ex_idx is not None:
                        del exclusions[latest_ex_idx]
                        restored = True

            if is_done and (not restored) and cat in ["生活", "兴趣爱好"]:
                ok = self.collect_manual_focus_time(cat, task_text)
                if not ok:
                    var.set(False)
                    return

            if is_done and (not restored) and cat in ["科研", "理论/技术"]:
                today_str = datetime.now().strftime("%Y-%m-%d")
                has_time = any(
                    (item.get("category") == cat and item.get("task") == task_text and item.get("date", "").startswith(today_str))
                    for item in global_data.get("study_history", [])
                )
                if not has_time:
                    var.set(False)
                    messagebox.showwarning("无法打卡", f"⚠️ 缺少番茄钟记录！\n\n 今日尚未对【{task_text}】产生番茄钟记录，请先在首页选择该任务完成一个番茄钟。", parent=viewer)
                    return

            if is_done and (task_text.startswith("（长期）") or task_text.startswith("(长期)")):
                req_time = task_item.get("req_time", 0)
                today_str = datetime.now().strftime("%Y-%m-%d")
                totals = self.get_focus_minutes_by_task(today_str)
                invested = totals.get((cat, task_text), 0)
                if invested < req_time:
                    var.set(False)
                    messagebox.showwarning("时长不足", f"该长期任务需专注满 {req_time} 分钟！\n当前仅记录了 {int(invested)} 分钟。", parent=viewer)
                    return
            
            # 如果取消勾选：只从【报表表格】里撤销最近一次记录，不删除看板中的历史记录
            if not is_done:
                today_str = datetime.now().strftime("%Y-%m-%d")
                exclusions = global_data.setdefault("report_exclusions", [])

                excluded_focus = {
                    (ex.get("start"), ex.get("end"), ex.get("category"), ex.get("task"))
                    for ex in exclusions
                    if ex.get("type") == "focus_log"
                }
                excluded_history = {
                    (ex.get("date"), ex.get("category"), ex.get("task"), ex.get("study_time"))
                    for ex in exclusions
                    if ex.get("type") == "study_history"
                }

                # 生活/兴趣：撤销最新一条 focus_logs 记录（仅对报表生效）
                if cat in ["生活", "兴趣爱好"]:
                    latest_log = None
                    latest_start = None
                    for log in global_data.get("focus_logs", []):
                        if log.get("category") != cat or log.get("task") != task_text:
                            continue
                        start_str = log.get("start", "")
                        if not start_str.startswith(today_str):
                            continue
                        key = (log.get("start"), log.get("end"), log.get("category"), log.get("task"))
                        if key in excluded_focus:
                            continue
                        if latest_start is None or start_str > latest_start:
                            latest_start = start_str
                            latest_log = log
                    if latest_log is not None:
                        exclusions.append({
                            "type": "focus_log",
                            "start": latest_log.get("start"),
                            "end": latest_log.get("end"),
                            "category": latest_log.get("category"),
                            "task": latest_log.get("task"),
                        })

                # 科研/理论 的番茄：撤销最新一条 study_history 记录（仅对报表生效）
                if cat in ["科研", "理论/技术"]:
                    latest_item = None
                    latest_date = None
                    latest_dur = None
                    for item in global_data.get("study_history", []):
                        if item.get("category") != cat or item.get("task") != task_text:
                            continue
                        date_str = item.get("date", "")
                        if not date_str.startswith(today_str):
                            continue
                        dur = item.get("study_time", item.get("duration", 0))
                        key = (date_str, cat, task_text, dur)
                        if key in excluded_history:
                            continue
                        if latest_date is None or date_str > latest_date:
                            latest_date = date_str
                            latest_item = item
                            latest_dur = dur
                    if latest_item is not None:
                        exclusions.append({
                            "type": "study_history",
                            "date": latest_item.get("date"),
                            "study_time": latest_dur,
                            "category": latest_item.get("category"),
                            "task": latest_item.get("task"),
                        })

            global_data["today_structured_tasks"][cat][idx]["done"] = is_done
            cb.configure(font=self.font_strike if is_done else self.font_normal, fg="gray" if is_done else "black")
            cancel_btn = self.task_cancel_btns.get((cat, idx))
            if cancel_btn is not None:
                cancel_btn.configure(state=tk.DISABLED if is_done else tk.NORMAL)
            check_category_status(cat)
            save_data()
            self.update_task_status_label()
            
            # 当消除任务清单上的子任务时(打卡勾选/取消勾选)，动态更新一次报表
            self.export_task_reports()

        def check_category_status(cat):
            items = global_data["today_structured_tasks"].get(cat, [])
            if not items: return
            all_done = all(t["done"] for t in items)
            lbl = self.cat_labels[cat]
            lbl.configure(font=self.font_bold_strike if all_done else self.font_bold_normal, fg="gray" if all_done else "#2F4F4F")

        def add_task_in_viewer(cat, entry_widget):
            text = entry_widget.get().strip()
            if not text:
                return
            if self.is_duplicate_task_text(text):
                messagebox.showwarning("重复任务", "已存在同名任务，不能重复添加。", parent=viewer)
                return
            global_data["today_structured_tasks"][cat].append({"text": text, "done": False})
            save_data()
            entry_widget.delete(0, tk.END)
            new_index = len(global_data["today_structured_tasks"][cat]) - 1
            cat_frame = self.cat_frames[cat]
            row = tk.Frame(cat_frame, bg="white")
            row.pack(anchor="w", padx=20, pady=2, fill=tk.X)
            var = tk.BooleanVar(value=False)
            cb = tk.Checkbutton(row, text=text, variable=var, font=self.font_normal, fg="black", bg="white", activebackground="white", selectcolor="#E0FFFF", justify=tk.LEFT, anchor="w", wraplength=240, command=lambda c=cat, idx=new_index: toggle_task(c, idx))
            cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
            cancel_btn = tk.Button(row, text="取消", font=("Microsoft YaHei", 8), bg="#FFB6C1", fg="white", bd=0, width=5, command=lambda c=cat, idx=new_index: self.handle_task_cancel(c, idx, viewer))
            cancel_btn.pack(side=tk.RIGHT, padx=(6, 0))
            self.task_cbs[(cat, new_index)] = (var, cb)
            self.task_cancel_btns[(cat, new_index)] = cancel_btn
            check_category_status(cat)
            self.update_task_status_label()

        for idx_c, cat in enumerate(TASK_CATS):
            tasks = global_data["today_structured_tasks"].get(cat, [])
            
            cat_frame = tk.Frame(main_frame, bg="white", bd=1, relief="solid", pady=10)
            cat_frame.pack(fill=tk.X, pady=5, padx=5)
            self.cat_frames[cat] = cat_frame
            
            lbl = tk.Label(cat_frame, text=f"{idx_c+1}  {cat}", font=self.font_bold_normal, bg="white", fg="#2F4F4F", anchor="w")
            lbl.pack(fill=tk.X, padx=10, pady=(0,5))
            self.cat_labels[cat] = lbl

            for i, t in enumerate(tasks):
                var = tk.BooleanVar(value=t["done"])
                font_to_use = self.font_strike if t["done"] else self.font_normal
                fg_to_use = "gray" if t["done"] else "black"
                row = tk.Frame(cat_frame, bg="white")
                row.pack(anchor="w", padx=20, pady=2, fill=tk.X)
                cb = tk.Checkbutton(row, text=t["text"], variable=var, font=font_to_use, fg=fg_to_use, bg="white", activebackground="white", selectcolor="#E0FFFF", justify=tk.LEFT, anchor="w", wraplength=240, command=lambda c=cat, idx=i: toggle_task(c, idx))
                cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
                cancel_btn = tk.Button(row, text="取消", font=("Microsoft YaHei", 8), bg="#FFB6C1", fg="white", bd=0, width=5, state=tk.DISABLED if t["done"] else tk.NORMAL, command=lambda c=cat, idx=i: self.handle_task_cancel(c, idx, viewer))
                cancel_btn.pack(side=tk.RIGHT, padx=(6, 0))
                self.task_cbs[(cat, i)] = (var, cb)
                self.task_cancel_btns[(cat, i)] = cancel_btn

            if global_data.get("today_task_submitted"):
                add_frame = tk.Frame(cat_frame, bg="white")
                add_frame.pack(fill=tk.X, padx=20, pady=(5, 0))
                entry = tk.Entry(add_frame, width=28, font=("Microsoft YaHei", 9))
                entry.pack(side=tk.LEFT, padx=(0, 6))
                btn_add = tk.Button(add_frame, text="添加", font=("Microsoft YaHei", 9), bg="#87CEFA", fg="white", bd=0, command=lambda c=cat, e=entry: add_task_in_viewer(c, e))
                btn_add.pack(side=tk.LEFT)
            
            check_category_status(cat)

        btn_long_term_viewer = tk.Button(main_frame, text="➕ 新增长期任务", bg="#FFD700", fg="black", font=("Microsoft YaHei", 10, "bold"), bd=0, pady=8, command=self.add_long_term_task_dialog)
        btn_long_term_viewer.pack(fill=tk.X, padx=10, pady=(10, 20))

    # ====================================
    # ====== 新版番茄钟：绑定任务逻辑 ======
    # ====================================
    def start_tomato_dialog(self):
        self.start_tomato_dialog_by_action("start")

    def start_tomato_dialog_by_action(self, action):
        if not global_data.get("today_task_submitted"):
            messagebox.showwarning("⚠️ 拦截", "请先点击【制定每日清单】提交任务！")
            return
            
        if action == "start" and self.timer_running:
            return

        available_tasks = []
        for cat in ["科研", "理论/技术"]:
            for t in global_data["today_structured_tasks"].get(cat, []):
                if not t["done"]: available_tasks.append((cat, t["text"]))
                
        if not available_tasks:
            messagebox.showwarning("无可用任务", "当前没有未完成的【科研】或【理论/技术】任务小点，无法开启学习番茄钟！\n（生活和兴趣爱好不计入专注记录）")
            return

        dialog = tk.Toplevel(self)
        dialog.title("🎯 选择专注任务")
        dialog.geometry("640x320")
        dialog.configure(bg="#FFF0F5")
        dialog.transient(self)
        dialog.grab_set()
        
        tk.Label(dialog, text="请选择本次番茄钟要执行的任务：", font=("Microsoft YaHei", 10, "bold"), bg="#FFF0F5").pack(pady=12)
        
        list_frame = tk.Frame(dialog, bg="#FFF0F5")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20)

        list_inner = tk.Frame(list_frame, bg="#FFF0F5")
        list_inner.pack(fill=tk.BOTH, expand=True)

        task_list = tk.Listbox(list_inner, font=("Microsoft YaHei", 10), height=6, selectmode=tk.SINGLE)
        y_scroll = tk.Scrollbar(list_inner, command=task_list.yview)
        x_scroll = tk.Scrollbar(list_frame, command=task_list.xview, orient=tk.HORIZONTAL)

        def update_xscroll(first, last):
            x_scroll.set(first, last)
            if float(first) <= 0.0 and float(last) >= 1.0:
                x_scroll.pack_forget()
            else:
                if not x_scroll.winfo_ismapped():
                    x_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        def update_yscroll(first, last):
            y_scroll.set(first, last)
            if float(first) <= 0.0 and float(last) >= 1.0:
                y_scroll.pack_forget()
            else:
                if not y_scroll.winfo_ismapped():
                    y_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        task_list.configure(yscrollcommand=update_yscroll, xscrollcommand=update_xscroll)
        task_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        update_yscroll(0.0, 1.0)
        update_xscroll(0.0, 1.0)
        
        display_values = [f"[{cat}] {text}" for cat, text in available_tasks]
        for item in display_values:
            task_list.insert(tk.END, item)
        task_list.selection_set(0)

        selected_label = tk.Label(dialog, text=display_values[0], font=("Microsoft YaHei", 9), bg="#FFF0F5", fg="#666666", wraplength=580, justify=tk.LEFT)
        selected_label.pack(pady=(6, 0), padx=20, anchor="w")

        def update_selected_label(event=None):
            sel = task_list.curselection()
            if sel:
                selected_label.config(text=task_list.get(sel[0]))

        task_list.bind("<<ListboxSelect>>", update_selected_label)
        
        def confirm():
            sel = task_list.curselection()
            if not sel:
                return
            selected = task_list.get(sel[0])
            dialog.destroy()
            cat_part, text_part = selected.split("] ", 1)
            cat = cat_part[1:]
            if action == "start":
                self.current_focus_task = {"cat": cat, "text": text_part}
                self.execute_start_tomato()
            else:
                self.change_focus_task(cat, text_part)

        tk.Button(dialog, text="开始倒计时", bg="#FF69B4", fg="white", font=("Microsoft YaHei", 11, "bold"), bd=0, width=15, command=confirm).pack(pady=12)

    def execute_start_tomato(self):
        self.timer_running = True
        self.btn_tomato.config(text="🔁 更换任务", bg="#FF69B4")
        self.btn_cancel.config(state=tk.NORMAL, bg="#FFA07A", text="⏹️ 放弃专注 (直接作废)")
        
        self.current_stage = "study"
        self.time_left = 25 * 60
        self.focus_segment_start_dt = datetime.now()
        self.pending_focus_segments = []
        self.stage_label.config(text=f"📖 正在执行: {self.current_focus_task['cat']} - {self.current_focus_task['text']}", fg="#FF69B4")
        self.update_timer()

    def change_focus_task(self, new_cat, new_text):
        if not self.timer_running or self.current_stage != "study":
            return
        now_dt = datetime.now()
        if self.focus_segment_start_dt and self.current_focus_task:
            self.pending_focus_segments.append({
                "start": self.focus_segment_start_dt,
                "end": now_dt,
                "category": self.current_focus_task["cat"],
                "task": self.current_focus_task["text"]
            })
        self.current_focus_task = {"cat": new_cat, "text": new_text}
        self.focus_segment_start_dt = now_dt
        self.stage_label.config(text=f"📖 正在执行: {new_cat} - {new_text}", fg="#FF69B4")

    def update_timer(self):
        if self.time_left > 0:
            mins, secs = divmod(self.time_left, 60)
            self.timer_label.config(text=f"{mins:02d}:{secs:02d}")
            self.time_left -= 1
            self.timer_id = self.after(1000, self.update_timer)
        else:
            self.timer_finished()

    def show_study_end_alert(self):
        msg = "25分钟到了！别学了，快起来活动一下！\n点击软件内弹窗领取积分。"
        notify_system("⏰ 学习结束", msg)

        dialog = tk.Toplevel(self)
        dialog.title("⏰ 学习结束")
        dialog.geometry("420x180")
        dialog.configure(bg="#FFF0F5")
        dialog.transient(self)
        self.force_window_front(dialog)

        tk.Label(dialog, text=msg, bg="#FFF0F5", font=("Microsoft YaHei", 10), justify=tk.LEFT).pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        btn_frame = tk.Frame(dialog, bg="#FFF0F5")
        btn_frame.pack(fill=tk.X, padx=12, pady=(0, 12), side=tk.BOTTOM)
        tk.Button(btn_frame, text="确定", bg="#87CEFA", fg="white", width=8, bd=0, command=dialog.destroy).pack(side=tk.LEFT)

    def timer_finished(self):
        self.timer_label.config(text="00:00")
        if self.current_stage == "study":
            self.deiconify()
            self.lift()
            self.focus_force()
            self.show_study_end_alert()
            ans = messagebox.askyesno("核算积分", "刚才全程专注没有摸鱼吗？", parent=self)
            
            if ans:
                end_dt = datetime.now()
                start_dt = end_dt - timedelta(minutes=25)
                end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")
                cat = self.current_focus_task['cat']
                text = self.current_focus_task['text']

                if self.focus_segment_start_dt and self.current_focus_task:
                    self.pending_focus_segments.append({
                        "start": self.focus_segment_start_dt,
                        "end": end_dt,
                        "category": cat,
                        "task": text
                    })
                for seg in self.pending_focus_segments:
                    self.append_focus_log(seg["start"], seg["end"], seg["category"], seg["task"])
                self.pending_focus_segments = []
                
                global_data["total_points"] += 25
                global_data["today_tomatoes"] += 1
                global_data["today_study_time"] += 25
                global_data["study_history"].append({"date": end_str, "study_time": 25, "category": cat, "task": text})
                save_data()
                self.export_task_reports()  # 番茄钟完成记录时间后，也动态刷新表格
                
                log_line = f"{start_dt.strftime('%H:%M')} —— {end_dt.strftime('%H:%M')} <{cat}>-{text}\n"
                self.log_to_txt("pomodoro", log_line)
                
                self.update_dashboard()
                messagebox.showinfo("🎉 奖励发放", "太棒了！获得 25 积分！\n准备进入 5 分钟休息阶段~", parent=self)
            else:
                messagebox.showinfo("❌ 无效记录", "很遗憾，本次不计入积分。下次专心一点哦！", parent=self)
                self.pending_focus_segments = []
            
            self.current_stage = "break"
            self.time_left = 5 * 60
            self.stage_label.config(text="☕ 休息一下吧...", fg="#87CEFA")
            self.btn_cancel.config(text="⏹️ 提前结束休息")
            self.update_timer()
            
        elif self.current_stage == "break":
            windows_force_top_alert("⏰ 休息结束！", "5分钟休息结束啦！\n准备开启下一个番茄钟吧~")
            self.timer_running = False
            self.current_stage = ""
            self.btn_tomato.config(text="🍅 开始专注 (25分钟)", bg="#FF69B4")
            self.btn_cancel.config(state=tk.DISABLED, bg="#CCCCCC", text="⏹️ 放弃当前计时")
            self.stage_label.config(text="准备开始专注", fg="#888888")
            self.timer_label.config(text="25:00")
            self.focus_segment_start_dt = None

    def cancel_timer(self):
        if not self.timer_running: return
        msg = ""
        if self.current_stage == "study":
            if not messagebox.askyesno("放弃专注", "确定要打断专注吗？中途打断则本番茄钟彻底作废！"): return
            msg = "已作废，调整好状态再战！"
            self.pending_focus_segments = []
        elif self.current_stage == "break":
            if not messagebox.askyesno("结束休息", "提前结束休息开启下一个番茄钟吗？"): return
            msg = "休息已提前结束"

        if self.timer_id: self.after_cancel(self.timer_id); self.timer_id = None
        self.timer_running = False
        self.current_stage = ""
        self.timer_label.config(text="25:00")
        self.stage_label.config(text=msg, fg="#888888")
        self.btn_tomato.config(text="🍅 开始专注 (25分钟)", bg="#FF69B4")
        self.btn_cancel.config(state=tk.DISABLED, bg="#CCCCCC", text="⏹️ 放弃当前计时")
        self.focus_segment_start_dt = None

    # ====================================
    # ====== 新版数据图表 (跨小时切割) ======
    # ====================================
    def split_time_to_bins(self, start_dt, duration_mins):
        bins = [0] * 24
        curr_dt = start_dt
        mins_left = duration_mins
        while mins_left > 0:
            hour = curr_dt.hour
            mins_in_curr_hour = 60 - curr_dt.minute
            if mins_left <= mins_in_curr_hour:
                bins[hour] += mins_left
                break
            else:
                bins[hour] += mins_in_curr_hour
                mins_left -= mins_in_curr_hour
                curr_dt = (curr_dt + timedelta(hours=1)).replace(minute=0, second=0)
        return bins

    def show_charts_window(self):
        chart_win = tk.Toplevel(self)
        chart_win.title("📊 学习与改变自己时间看板")
        chart_win.geometry("980x880") 
        chart_win.configure(bg="white")

        today_str = datetime.now().strftime("%Y-%m-%d")
        today_study_minutes = self.get_daily_minutes_for_study(today_str)
        today_exchange_minutes = self.get_daily_minutes_for_exchange(today_str)
        study_display = self.format_minutes(today_study_minutes)
        
        info_text = (
            f"🏅 今日完成番茄: {global_data['today_tomatoes']} 个   |   "
            f"⏱️ 今日专注: {study_display}   |   "
            f"🎮 今日兑换: {today_exchange_minutes} 分钟   |   "
            f"📅 连续打卡: {global_data['continuous_checkin_days']} 天"
        )
        tk.Label(chart_win, text=info_text, font=("Microsoft YaHei", 12, "bold"), bg="#f0f0f0", pady=10).pack(fill=tk.X)

        filter_frame = tk.Frame(chart_win, bg="#E6E6FA", pady=8)
        filter_frame.pack(fill=tk.X)
        
        tk.Label(filter_frame, text="📅 图表范围筛选:", bg="#E6E6FA", font=("Microsoft YaHei", 10, "bold")).pack(side=tk.LEFT, padx=10)
        
        range_var = tk.StringVar(value="今日")
        preset_cb = ttk.Combobox(filter_frame, textvariable=range_var, values=["今日", "最近一周", "最近一月", "全部记录", "自定义范围"], width=10, state="readonly")
        preset_cb.pack(side=tk.LEFT, padx=5)

        years = [str(y) for y in range(2025, 2031)]
        months = [f"{m:02d}" for m in range(1, 13)]

        def build_date_selectors(label_text):
            tk.Label(filter_frame, text=label_text, bg="#E6E6FA").pack(side=tk.LEFT, padx=(10, 0))
            year_var = tk.StringVar()
            month_var = tk.StringVar()
            day_var = tk.StringVar()

            year_cb = ttk.Combobox(filter_frame, textvariable=year_var, values=years, width=6, state="readonly")
            month_cb = ttk.Combobox(filter_frame, textvariable=month_var, values=months, width=4, state="readonly")
            day_cb = ttk.Combobox(filter_frame, textvariable=day_var, values=[], width=4, state="disabled")

            year_cb.pack(side=tk.LEFT, padx=2)
            month_cb.pack(side=tk.LEFT, padx=2)
            day_cb.pack(side=tk.LEFT, padx=2)

            def update_days(_=None):
                y = year_var.get()
                m = month_var.get()
                if not y or not m:
                    day_cb.configure(state="disabled", values=[])
                    day_var.set("")
                    return
                days = calendar.monthrange(int(y), int(m))[1]
                day_values = [f"{d:02d}" for d in range(1, days + 1)]
                day_cb.configure(state="readonly", values=day_values)
                if day_var.get() not in day_values:
                    day_var.set(day_values[0])

            year_cb.bind("<<ComboboxSelected>>", update_days)
            month_cb.bind("<<ComboboxSelected>>", update_days)

            return year_var, month_var, day_var, year_cb, month_cb, day_cb, update_days

        start_year_var, start_month_var, start_day_var, start_year_cb, start_month_cb, start_day_cb, start_update_days = build_date_selectors("开始:")
        end_year_var, end_month_var, end_day_var, end_year_cb, end_month_cb, end_day_cb, end_update_days = build_date_selectors("结束:")

        def set_date_selectors(dt_obj, enable):
            y = dt_obj.strftime("%Y")
            m = dt_obj.strftime("%m")
            d = dt_obj.strftime("%d")
            for cb in (start_year_cb, start_month_cb, start_day_cb, end_year_cb, end_month_cb, end_day_cb):
                cb.configure(state="readonly" if enable else "disabled")

            start_year_var.set(y)
            start_month_var.set(m)
            start_update_days()
            start_day_var.set(d)

            end_year_var.set(y)
            end_month_var.set(m)
            end_update_days()
            end_day_var.set(d)

        now_dt = datetime.now()
        set_date_selectors(now_dt, enable=False)

        def on_preset_change(event=None):
            val = range_var.get()
            now = datetime.now()
            if val == "自定义范围":
                for cb in (start_year_cb, start_month_cb, start_day_cb, end_year_cb, end_month_cb, end_day_cb):
                    cb.configure(state="readonly")
                start_year_var.set("")
                start_month_var.set("")
                start_day_var.set("")
                end_year_var.set("")
                end_month_var.set("")
                end_day_var.set("")
                start_day_cb.configure(state="disabled", values=[])
                end_day_cb.configure(state="disabled", values=[])
                return

            for cb in (start_year_cb, start_month_cb, start_day_cb, end_year_cb, end_month_cb, end_day_cb):
                cb.configure(state="disabled")

            if val == "今日":
                start_dt = now
                end_dt = now
            elif val == "最近一周":
                start_dt = now - timedelta(days=6)
                end_dt = now
            elif val == "最近一月":
                start_dt = now - timedelta(days=29)
                end_dt = now
            elif val == "全部记录":
                earliest = now
                if global_data.get("first_use_date"):
                    earliest = datetime.strptime(global_data["first_use_date"], "%Y-%m-%d")
                start_dt = earliest
                end_dt = now

            start_year_var.set(start_dt.strftime("%Y"))
            start_month_var.set(start_dt.strftime("%m"))
            start_update_days()
            start_day_var.set(start_dt.strftime("%d"))

            end_year_var.set(end_dt.strftime("%Y"))
            end_month_var.set(end_dt.strftime("%m"))
            end_update_days()
            end_day_var.set(end_dt.strftime("%d"))

        preset_cb.bind("<<ComboboxSelected>>", on_preset_change)

        fig = plt.figure(figsize=(10, 9), facecolor='white')
        gs = gridspec.GridSpec(2, 2, height_ratios=[1, 1], figure=fig)
        canvas = FigureCanvasTkAgg(fig, master=chart_win)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def update_charts():
            start_str = ""
            end_str = ""
            if start_year_var.get() and start_month_var.get() and start_day_var.get():
                start_str = f"{start_year_var.get()}-{start_month_var.get()}-{start_day_var.get()}"
            if end_year_var.get() and end_month_var.get() and end_day_var.get():
                end_str = f"{end_year_var.get()}-{end_month_var.get()}-{end_day_var.get()}"

            if not start_str or not end_str:
                messagebox.showwarning("范围为空", "请填写开始和结束日期。")
                return

            try:
                start_dt_range = datetime.strptime(start_str, "%Y-%m-%d")
                end_dt_range = datetime.strptime(end_str, "%Y-%m-%d")
            except ValueError:
                messagebox.showwarning("格式错误", "日期格式应为 YYYY-MM-DD。")
                return

            if end_dt_range < start_dt_range:
                messagebox.showwarning("范围错误", "结束日期不能早于开始日期。")
                return

            hours_bins = {'科研': [0]*24, '理论/技术': [0]*24, '改变自己': [0]*24}
            totals = {'科研': 0, '理论/技术': 0, '改变自己': 0}

            for item in global_data.get("study_history", []):
                dt_str = item["date"]
                cat = item.get("category", "")
                if cat not in ['科研', '理论/技术']:
                    continue
                end_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                duration = item["study_time"]
                start_dt = end_dt - timedelta(minutes=duration)

                for seg_start, seg_mins in self.split_duration_by_day(start_dt, duration):
                    seg_date = seg_start.strftime("%Y-%m-%d")
                    if start_str <= seg_date <= end_str:
                        bins = self.split_time_to_bins(seg_start, seg_mins)
                        for h, val in enumerate(bins):
                            hours_bins[cat][h] += val
                        totals[cat] += seg_mins

            for item in global_data.get("exchange_history", []):
                dt_str = item["date"]
                start_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                duration = item["exchange_time"]
                for seg_start, seg_mins in self.split_duration_by_day(start_dt, duration):
                    seg_date = seg_start.strftime("%Y-%m-%d")
                    if start_str <= seg_date <= end_str:
                        bins = self.split_time_to_bins(seg_start, seg_mins)
                        for h, val in enumerate(bins):
                            hours_bins['改变自己'][h] += val
                        totals['改变自己'] += seg_mins

            fig.clf() 
            colors = {'科研':'#87CEFA', '理论/技术':'#98FB98', '改变自己':'#FF69B4'}
            
            ax1 = fig.add_subplot(gs[0, :])
            x = np.arange(24)
            width = 0.4  
            
            study_cats = ['科研', '理论/技术']
            bottom_study = np.zeros(24)
            for cat in study_cats:
                arr = np.array(hours_bins[cat])
                ax1.bar(x - width/2, arr, width, label=cat, bottom=bottom_study, color=colors[cat], edgecolor='white')
                bottom_study += arr

            arr_game = np.array(hours_bins['改变自己'])
            ax1.bar(x + width/2, arr_game, width, label='改变自己', color=colors['改变自己'], edgecolor='white')

            for i in range(24):
                if bottom_study[i] > 0:
                    ax1.text(x[i] - width/2, bottom_study[i] + 0.5, f"{int(bottom_study[i])}", ha='center', va='bottom', fontsize=8, color='black', fontweight='bold')
                if arr_game[i] > 0:
                    ax1.text(x[i] + width/2, arr_game[i] + 0.5, f"{int(arr_game[i])}", ha='center', va='bottom', fontsize=8, color='black', fontweight='bold')

            max_val = max(max(bottom_study) if len(bottom_study) > 0 else 0, max(arr_game) if len(arr_game) > 0 else 0)
            if max_val > 180:
                ax1.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f'{y/60:.1f}h'))
                ax1.set_ylabel("时间 (小时)")
            else:
                ax1.set_ylabel("时间 (分钟)")
            ax1.set_ylim(0, max_val + (max_val * 0.15 + 5))

            title_str = "所选范围内" if start_str != end_str else "今日"
            ax1.set_title(f"【{title_str}】24小时时间分布图", fontsize=12, fontweight='bold')
            
            x_labels = [f"{i}-{i+1}" for i in range(24)]
            ax1.set_xticks(x)
            ax1.set_xticklabels(x_labels, rotation=45, ha='right', fontsize=9)
            ax1.legend(loc='upper right')

            # --- 饼图 ---
            ax2 = fig.add_subplot(gs[1, 0])
            pie_labels = []
            pie_sizes = []
            pie_colors = []
            for cat, val in totals.items():
                if val > 0:
                    pie_labels.append(cat)
                    pie_sizes.append(val)
                    pie_colors.append(colors[cat])

            def absolute_value_autopct(val):
                total = sum(pie_sizes)
                a = int(round(val * total / 100.0))
                h, m = divmod(a, 60)
                if h > 0: return f'{h}h{m}min\n({val:.1f}%)'
                return f'{m}min\n({val:.1f}%)'

            if not pie_sizes:
                ax2.text(0.5, 0.5, '暂无记录', ha='center', va='center')
                ax2.axis('off')
            else:
                ax2.pie(pie_sizes, labels=pie_labels, colors=pie_colors, autopct=absolute_value_autopct, startangle=90, textprops={'fontsize': 10})
            total_minutes = sum(totals.values())
            ax2.set_title(f"【{title_str}】任务类型耗时分布 (总计 {self.format_minutes(total_minutes)})", fontsize=11)

            # --- 历史复盘曲线 ---
            ax3 = fig.add_subplot(gs[1, 1])
            history = global_data.get("daily_rewards_history", [])
            filtered_history = [item for item in history if start_str <= item.get("date", "") <= end_str]
            if not filtered_history:
                ax3.text(0.5, 0.5, '暂无完成率/奖惩记录', ha='center', va='center')
                ax3.axis('off')
            else:
                filtered_history = sorted(filtered_history, key=lambda x: x.get("date", ""))
                dates = [item.get('date', '')[-5:] for item in filtered_history]
                rates = [item.get('rate', 0) for item in filtered_history]
                rewards = [item.get('reward', 0) for item in filtered_history]

                ax3.plot(dates, rates, marker='o', color='#1E90FF', linewidth=2, label='完成率(%)')
                ax3.set_ylim(0, 100)
                ax3.set_ylabel("完成率(%)")
                ax3.set_title("完成率与完成奖惩趋势", fontsize=11)
                ax3.grid(True, linestyle='--', alpha=0.6)

                ax3b = ax3.twinx()
                ax3b.plot(dates, rewards, marker='s', color='#FF8C00', linewidth=2, label='奖惩(分)')
                ax3b.set_ylabel("完成奖惩(分)")
                for tick in ax3.get_xticklabels():
                    tick.set_rotation(45)

            plt.tight_layout()
            canvas.draw()

        tk.Button(filter_frame, text="🔄 刷新生成图表", bg="#87CEFA", command=update_charts, font=("Microsoft YaHei", 9, "bold")).pack(side=tk.LEFT, padx=15)
        update_charts()

    # ====== 复盘输入与写入文本日志 ======
    def open_review(self):
        if global_data.get("today_review_submitted"):
            messagebox.showinfo("提示", "今日已复盘，无需重复提交！")
            return
        dialog = tk.Toplevel(self)
        dialog.title("今日复盘")
        dialog.geometry("520x360")
        dialog.configure(bg="#FFF0F5")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="请输入今日任务总结与复盘反思：", font=("Microsoft YaHei", 10, "bold"), bg="#FFF0F5").pack(anchor=tk.W, padx=20, pady=(15, 5))
        text_frame = tk.Frame(dialog, bg="#FFF0F5")
        text_frame.pack(fill=tk.BOTH, expand=True, padx=20)

        review_text = tk.Text(text_frame, height=10, font=("Microsoft YaHei", 10), wrap="word")
        review_scroll = tk.Scrollbar(text_frame, command=review_text.yview)
        review_text.configure(yscrollcommand=review_scroll.set)
        review_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        review_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def submit_review_text():
            content = review_text.get("1.0", tk.END).strip()
            if not content:
                messagebox.showwarning("内容为空", "请填写复盘内容后再提交。", parent=dialog)
                return
            global_data["today_review_text"] = content
            global_data["today_review_submitted"] = True
            save_data()
            task_status_text = self.build_task_status_lines(global_data.get("today_structured_tasks", {}))
            log_text = f"【今日复盘】\n{task_status_text}\n今日反思：\n{global_data['today_review_text']}\n{'='*40}\n"
            self.log_to_txt("review", log_text)
            dialog.destroy()
            messagebox.showinfo("提交成功", "复盘已提交，零点后将自动结算完成率奖惩。")

        btn_frame = tk.Frame(dialog, bg="#FFF0F5")
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        tk.Button(btn_frame, text="提交", bg="#87CEFA", fg="white", font=("Microsoft YaHei", 10, "bold"), bd=0, width=10, command=submit_review_text).pack(side=tk.RIGHT)
        tk.Button(btn_frame, text="取消", bg="#CCCCCC", fg="black", font=("Microsoft YaHei", 10), bd=0, width=10, command=dialog.destroy).pack(side=tk.RIGHT, padx=(0, 10))

    def show_review_rates_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("任务完成率评估")
        dialog.geometry("300x260")
        dialog.transient(self); dialog.grab_set()
        
        total_tasks, done_tasks, rate = self.get_task_completion_stats()
        info_text = "当前尚未设定任务" if total_tasks == 0 else f"系统统计完成率: {done_tasks}/{total_tasks} ({rate:.0f}%)"
        tk.Label(dialog, text=info_text, font=("Microsoft YaHei", 9), fg="#555555").pack(pady=(8, 2))

        penalty = self.get_penalty_by_rate(rate) if total_tasks > 0 else 0
        if penalty < 0:
            tk.Label(dialog, text=f"低于60%将扣分: {penalty} 分", font=("Microsoft YaHei", 9, "bold"), fg="#FF4500").pack(pady=(0, 6))

        rates = [("完成率 < 70%", 0, "#CCCCCC"), ("完成率 70-80%", 30, "#87CEFA"), ("完成率 80-90%", 80, "#98FB98"), ("完成率 100%", 200, "#FFD700")]
        for text, pts, color in rates:
            tk.Button(dialog, text=text, font=("Microsoft YaHei", 10, "bold"), bg=color, width=20, command=lambda t=text, p=pts, r=rate, tt=total_tasks, dt=done_tasks: self.submit_review(t, p, dialog, r, tt, dt)).pack(pady=6)

    def submit_review(self, rate_text, pts, dialog, completion_rate, total_tasks, done_tasks):
        dialog.destroy()
        global_data["today_review_submitted"] = True
        global_data["total_points"] += pts
        
        penalty = self.get_penalty_by_rate(completion_rate) if total_tasks > 0 else 0
        if penalty < 0:
            global_data["total_points"] = max(0, global_data["total_points"] + penalty)
            global_data["last_penalty_date"] = datetime.now().strftime("%Y-%m-%d")
        else:
            global_data["last_penalty_date"] = datetime.now().strftime("%Y-%m-%d")

        delta = pts + (penalty if penalty < 0 else 0)
        self.upsert_daily_reward_history(datetime.now().strftime("%Y-%m-%d"), completion_rate, delta)

        save_data()
        
        penalty_text = f"，惩罚 {penalty} 分" if penalty < 0 else ""
        log_text = f"【今日复盘】\n{global_data['today_review_text']}\n【评级】{rate_text}，奖励 {pts} 分{penalty_text}\n【完成率】{done_tasks}/{total_tasks} ({completion_rate:.0f}%)\n{'='*40}\n"
        self.log_to_txt("review", log_text)
        self.update_dashboard()
        final_msg = f"获得复盘奖励 {pts} 积分！"
        if penalty < 0:
            final_msg += f"\n完成率低于60%，已扣除 {abs(penalty)} 分。"
        messagebox.showinfo("🎉 复盘完成", final_msg)

    def log_to_txt(self, log_type, content):
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = "daily_tasks_log.txt"
        if app_config.get("data_dir"): log_file = os.path.join(app_config["data_dir"], log_file)
        with open(log_file, "a", encoding="utf-8") as f:
            if log_type == "task_update": f.write(f"\n{'='*40}\n日期: {today}\n【每日任务设定】\n{content}\n")
            elif log_type == "pomodoro": f.write(f"{content}")
            elif log_type == "review": f.write(f"{content}")
            elif log_type == "task_cancel": f.write(f"{content}")
            elif log_type == "task_time": f.write(f"{content}")

    def reset_cancel_counter_if_needed(self):
        month_key = datetime.now().strftime("%Y-%m")
        if app_config.get("cancel_month") != month_key:
            app_config["cancel_month"] = month_key
            app_config["cancel_count"] = 0
            save_app_config()

    def get_cancel_penalty_info(self):
        self.reset_cancel_counter_if_needed()
        count = int(app_config.get("cancel_count", 0))
        penalty = 20 * (2 ** count)
        return count, penalty

    def prompt_cancel_reason(self, cat, text, count, penalty):
        dialog = tk.Toplevel(self)
        dialog.title("取消任务")
        dialog.geometry("420x260")
        dialog.configure(bg="#FFF0F5")
        dialog.transient(self)
        dialog.grab_set()

        info = (
            f"任务: <{cat}>-{text}\n"
            f"本月已使用 {count} 次取消机会\n"
            f"若本次取消将扣除 {penalty} 分"
        )
        tk.Label(dialog, text=info, bg="#FFF0F5", justify=tk.LEFT, font=("Microsoft YaHei", 9)).pack(anchor="w", padx=16, pady=(12, 6))

        tk.Label(dialog, text="请输入取消原因:", bg="#FFF0F5", font=("Microsoft YaHei", 9, "bold")).pack(anchor="w", padx=16)
        reason_text = tk.Text(dialog, height=5, font=("Microsoft YaHei", 9), wrap="word")
        reason_text.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 8))

        result = {"reason": ""}

        def confirm():
            reason = reason_text.get("1.0", tk.END).strip()
            if not reason:
                messagebox.showwarning("需要原因", "请填写取消原因。", parent=dialog)
                return
            result["reason"] = reason
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg="#FFF0F5")
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 12))
        tk.Button(btn_frame, text="取消", bg="#CCCCCC", fg="black", width=8, command=dialog.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(btn_frame, text="确认", bg="#FFB6C1", fg="white", width=8, command=confirm).pack(side=tk.RIGHT)

        self.wait_window(dialog)
        return result["reason"] or None

    def handle_task_cancel(self, cat, idx, viewer=None):
        if global_data.get("total_points", 0) < 0:
            messagebox.showwarning("无法取消", "当前积分为负，禁止取消任务。")
            return
        tasks = global_data.get("today_structured_tasks", {}).get(cat, [])
        if idx < 0 or idx >= len(tasks):
            return
            
        task_text = tasks[idx].get("text", "")
        if task_text.startswith("（长期）"):
            messagebox.showwarning("无法取消", "长期任务只要没有完成，就永远不能删除！")
            return
            
        if tasks[idx].get("done"):
            messagebox.showwarning("无法取消", "已完成任务不能取消。")
            return

        count, penalty = self.get_cancel_penalty_info()
        reason = self.prompt_cancel_reason(cat, tasks[idx].get("text", ""), count, penalty)
        if not reason:
            return

        text = tasks[idx].get("text", "")
        del tasks[idx]
        global_data["total_points"] = global_data.get("total_points", 0) - penalty
        app_config["cancel_count"] = count + 1
        save_app_config()
        save_data()

        log_text = (
            f"【任务取消】\n"
            f"日期: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"任务: <{cat}>-{text}\n"
            f"原因: {reason}\n"
            f"本月已使用 {count + 1} 次，扣除 {penalty} 分\n"
            f"{'='*40}\n"
        )
        self.log_to_txt("task_cancel", log_text)

        self.update_dashboard()
        self.update_task_status_label()

        if viewer is not None:
            viewer.destroy()
            self.open_task_viewer()

    def get_focus_minutes_by_task(self, date_str):
        totals = {}
        for item in global_data.get("focus_logs", []):
            start_str = item.get("start", "")
            end_str = item.get("end", "")
            if not start_str.startswith(date_str):
                continue
            try:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M")
            except Exception:
                continue
            mins = (end_dt - start_dt).total_seconds() / 60.0
            if mins <= 0:
                continue
            key = (item.get("category", ""), item.get("task", ""))
            totals[key] = totals.get(key, 0) + mins
        return totals

    def log_daily_task_time(self, date_str, tasks_snapshot):
        totals = self.get_focus_minutes_by_task(date_str)
        lines = []
        for cat in TASK_CATS:
            tasks = tasks_snapshot.get(cat, [])
            if not tasks:
                continue
            lines.append(f"[{cat}]")
            for t in tasks:
                text = t.get("text", "")
                mins = totals.get((cat, text), 0)
                lines.append(f"- {text}：{self.format_minutes(mins)}")
        if not lines:
            return
        log_text = (
            f"【每日任务耗时】\n"
            f"日期: {date_str}\n"
            + "\n".join(lines)
            + f"\n{'='*40}\n"
        )
        self.log_to_txt("task_time", log_text)

    def change_data_directory(self):
        self.apply_storage_directory()

    def ensure_storage_directory(self):
        root_dir = app_config.get("storage_root_dir")
        if root_dir and os.path.isdir(root_dir):
            data_dir = os.path.join(root_dir, DATA_FOLDER_NAME)
            if os.path.isdir(data_dir):
                app_config["data_dir"] = data_dir
                app_config["memo_dir"] = data_dir
                app_config["storage_dir_confirmed"] = True
                save_app_config()
                return
        if root_dir and not os.path.isdir(root_dir):
            app_config["storage_dir_confirmed"] = False
            save_app_config()
        messagebox.showinfo("需要设置目录", "请设置统一的数据存储根目录。\n\n将在该目录下创建或使用【专注改变（个人软件数据）】文件夹。", parent=self)
        new_root = filedialog.askdirectory(title="请选择统一的数据存储根目录")
        if not new_root:
            windows_force_top_alert("必须设置目录", "未选择目录，程序将退出。")
            sys.exit(0)
        self.apply_storage_directory(new_root_dir=new_root, show_message=False)

    def apply_storage_directory(self, new_root_dir=None, show_message=True):
        global DATA_FILE_PATH
        if new_root_dir is None:
            new_root_dir = filedialog.askdirectory(title="请选择存放数据的文件夹")
            if not new_root_dir:
                return
        new_root_dir = os.path.normpath(new_root_dir)
        target_data_dir = os.path.join(new_root_dir, DATA_FOLDER_NAME)
        old_data_dir = app_config.get("data_dir")

        if not os.path.isdir(target_data_dir):
            if old_data_dir and os.path.isdir(old_data_dir):
                try:
                    os.makedirs(new_root_dir, exist_ok=True)
                    shutil.move(old_data_dir, target_data_dir)
                except Exception:
                    os.makedirs(target_data_dir, exist_ok=True)
            else:
                os.makedirs(target_data_dir, exist_ok=True)

        app_config["storage_root_dir"] = new_root_dir
        app_config["data_dir"] = target_data_dir
        app_config["memo_dir"] = target_data_dir
        app_config["storage_dir_confirmed"] = True
        save_app_config()
        DATA_FILE_PATH = os.path.join(app_config["data_dir"], DATA_FILE_NAME)
        init_data()
        if hasattr(self, "points_label"):
            self.update_date_label()
            self.update_dashboard()
            self.update_task_buttons()
            self.update_task_status_label()
        if show_message:
            messagebox.showinfo("设置成功", f"未来的数据将存储在：\n{target_data_dir}")

    # ====================================
    # ====== 随手记功能 ======
    # ====================================
    def open_memo_window(self):
        if not app_config.get("memo_dir"):
            if not app_config.get("data_dir"):
                self.ensure_storage_directory()
            app_config["memo_dir"] = app_config["data_dir"]
            save_app_config()

        self.memo_win = tk.Toplevel(self)
        self.memo_win.title("💡 随手记归档面板")
        self.memo_win.geometry("500x360")
        self.memo_win.minsize(500, 360)
        self.memo_win.configure(bg="#FFF0F5")
        self.memo_win.transient(self)
        self.memo_win.grab_set()

        self.memo_file_paths = []
        self.memo_img_paths = []

        tk.Label(self.memo_win, text="✏️ 文本内容 (必填):", bg="#FFF0F5", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(15, 5))
        self.memo_text_input = tk.Text(self.memo_win, height=6, font=("Microsoft YaHei", 10))
        self.memo_text_input.pack(fill=tk.X, padx=20)

        drop_hint = "拖拽文件/图片到这里（可多选）" if TK_DND_AVAILABLE else "拖拽上传需要安装 tkinterdnd2"
        self.drop_area = tk.Label(self.memo_win, text=drop_hint, bg="#FFF0F5", fg="#777777", font=("Microsoft YaHei", 9), relief="groove", bd=1, padx=10, pady=8)
        self.drop_area.pack(fill=tk.X, padx=20, pady=(10, 6))

        if not TK_DND_AVAILABLE:
            tk.Button(self.memo_win, text="查看拖拽安装说明", bg="#E6E6FA", font=("Microsoft YaHei", 9), command=self.show_dnd_help).pack(padx=20, pady=(0, 5), anchor=tk.W)

        if TK_DND_AVAILABLE:
            self.drop_area.drop_target_register(DND_FILES)
            self.drop_area.dnd_bind("<<Drop>>", self.handle_memo_drop)

        self.file_label = tk.Label(self.memo_win, text="", bg="#FFF0F5", fg="blue", font=("Microsoft YaHei", 9), wraplength=460, justify=tk.LEFT, anchor="w")
        self.file_label.pack(anchor=tk.W, padx=20, pady=2)
        self.img_label = tk.Label(self.memo_win, text="", bg="#FFF0F5", fg="green", font=("Microsoft YaHei", 9), wraplength=460, justify=tk.LEFT, anchor="w")
        self.img_label.pack(anchor=tk.W, padx=20, pady=2)

        tk.Button(self.memo_win, text="🚀 一键归档至随手记", bg="#FF69B4", fg="white", font=("Microsoft YaHei", 12, "bold"), bd=0, pady=8, command=self.save_memo_entry).pack(fill=tk.X, padx=20, pady=(10, 8))
        self.refresh_memo_window_size()

    def handle_memo_drop(self, event):
        paths = self.memo_win.tk.splitlist(event.data)
        img_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
        for path in paths:
            ext = os.path.splitext(path)[1].lower()
            if ext in img_exts:
                if path not in self.memo_img_paths:
                    self.memo_img_paths.append(path)
            else:
                if path not in self.memo_file_paths:
                    self.memo_file_paths.append(path)
        self.update_memo_attachment_labels()

    def update_memo_attachment_labels(self):
        if self.memo_file_paths:
            names = [os.path.basename(p) for p in self.memo_file_paths]
            self.file_label.config(text=f"📎 已选文件({len(names)}):\n" + "\n".join(names))
        else:
            self.file_label.config(text="")

        if self.memo_img_paths:
            names = [os.path.basename(p) for p in self.memo_img_paths]
            self.img_label.config(text=f"🖼️ 已选图片({len(names)}):\n" + "\n".join(names))
        else:
            self.img_label.config(text="")
        self.refresh_memo_window_size()

    def refresh_memo_window_size(self):
        self.memo_win.update_idletasks()
        req_h = self.memo_win.winfo_reqheight()
        screen_h = self.memo_win.winfo_screenheight()
        target_h = min(max(req_h + 6, 360), int(screen_h * 0.9))
        self.memo_win.geometry(f"500x{target_h}")

    def show_dnd_help(self):
        messagebox.showinfo("拖拽依赖", "拖拽上传需要安装 tkinterdnd2。\n\n安装命令：\npip install tkinterdnd2")

    def save_memo_entry(self):
        content = self.memo_text_input.get("1.0", tk.END).strip()
        has_attachment = bool(self.memo_file_paths or self.memo_img_paths)

        if has_attachment and not content:
            messagebox.showwarning("⚠️ 格式错误", "按照规则，上传文件或图片必须附加文字说明才可以上传！", parent=self.memo_win)
            return
        if not content and not has_attachment:
            messagebox.showwarning("⚠️ 内容为空", "请填写记录内容！", parent=self.memo_win)
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        memo_base = app_config["memo_dir"]
        memo_txt_path = os.path.join(memo_base, "随手记.txt")
        memo_folder_path = os.path.join(memo_base, "随手记", today_str)

        is_new_day = (app_config.get("memo_date") != today_str)
        if is_new_day:
            app_config["memo_date"] = today_str
            app_config["memo_count"] = 0
            
            mode = "a" if os.path.exists(memo_txt_path) else "w"
            with open(memo_txt_path, mode, encoding="utf-8") as f:
                if mode == "a": f.write("\n\n\n") 
                f.write(f"【{today_str}】\n")
            save_app_config()

        app_config["memo_count"] += 1
        save_app_config()
        idx = app_config["memo_count"]

        attach_msg = ""
        if has_attachment:
            if not os.path.exists(memo_folder_path): os.makedirs(memo_folder_path)

            file_names = []
            for file_path in self.memo_file_paths:
                fname = os.path.basename(file_path)
                shutil.copy(file_path, os.path.join(memo_folder_path, fname))
                file_names.append(fname)
            if file_names:
                attach_msg += f"，对应文件《{'、'.join(file_names)}》在 {memo_folder_path} 可以查看"

            img_names = []
            for img_path in self.memo_img_paths:
                iname = os.path.basename(img_path)
                shutil.copy(img_path, os.path.join(memo_folder_path, iname))
                img_names.append(iname)
            if img_names:
                attach_msg += f"，对应图片《{'、'.join(img_names)}》在 {memo_folder_path} 可以查看"

        line_str = f"{idx}、{content}{attach_msg}\n"

        with open(memo_txt_path, "a", encoding="utf-8") as f:
            f.write(line_str)

        messagebox.showinfo("🎉 归档成功", "内容已成功写入随手记，附件已分发至日期文件夹！", parent=self.memo_win)
        self.memo_win.destroy()

    def update_dashboard(self):
        pts = global_data["total_points"]
        monthly_tomatoes = sum(1 for item in global_data.get("study_history", []) if item["date"].startswith(datetime.now().strftime("%Y-%m")))
        # Learning 100 minutes gives 25 minutes of "改变自己"
        # Every 40 Pomodoros adds 5 minutes to the rate (100 mins -> 30 mins)
        bonus = (monthly_tomatoes // 40) * 5
        rate = 25 + bonus  # This means 100 learning minutes = rate minutes of change
        
        # 1 point = 1 minute of learning. Cost per minute of change is 100 / rate
        cost_per_minute = 100 / rate
        
        # No workday/weekend limits => max_ex conceptually infinite, but we'll adapt today_ex to tracking if wanted
        # It's better to just calculate playable time directly
        today_ex = self.get_today_point_exchange_count() # Still tracks count if used
        incentive_pool = int(global_data.get("today_incentive_pool", 0))
        
        point_time = 0
        if cost_per_minute > 0:
            point_time = int(pts / cost_per_minute)
            
        today_playable = point_time + incentive_pool
        
        self.points_label.config(text=f"总积分: {pts}")
        self.games_label.config(text=f"✨ 今日还有多少时间改变自己: {today_playable} 分钟 | 积分可换: {point_time} 分钟 ({cost_per_minute:.1f}分/分钟) | 激励池: {incentive_pool} 分钟")
        self.discount_info_label.config(text=f"📌 本月累计番茄: {monthly_tomatoes} 个 | 再专注 {40 - (monthly_tomatoes % 40)} 个，比例提升 5 分！(当前兑换比: 100分换{rate}分)")

    def get_today_point_exchange_count(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        return sum(
            1
            for item in global_data.get("exchange_history", [])
            if item.get("used_points", 0) > 0 and item.get("date", "").startswith(today_str)
        )

    def open_exchange_shop(self):
        shop = tk.Toplevel(self)
        shop.title("🎮 兑换商店")
        shop.geometry("360x240")
        shop.configure(bg="#FFF0F5")
        shop.transient(self)
        shop.grab_set()

        tk.Label(shop, text="请选择兑换方式", font=("Microsoft YaHei", 11, "bold"), bg="#FFF0F5").pack(pady=(16, 10))

        btn_style = {"font": ("Microsoft YaHei", 10, "bold"), "fg": "white", "width": 22, "pady": 8, "bd": 0}
        tk.Button(shop, text="🎮 兑换【改变自己】时间", bg="#98FB98", activebackground="#32CD32", command=self.exchange_points, **btn_style).pack(pady=6)
        tk.Button(shop, text="⭐ 激励计划", bg="#87CEFA", activebackground="#00BFFF", command=self.open_incentive_plan, **btn_style).pack(pady=6)
        tk.Button(shop, text="关闭", bg="#CCCCCC", fg="black", width=10, bd=0, command=shop.destroy).pack(pady=(8, 0))

    def open_incentive_plan(self):
        dialog = tk.Toplevel(self)
        dialog.title("⭐ 激励计划")
        dialog.geometry("460x320")
        dialog.configure(bg="#FFF0F5")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="选择激励选项领取奖励", font=("Microsoft YaHei", 10, "bold"), bg="#FFF0F5").pack(pady=(14, 8))
        pool_label = tk.Label(dialog, text="", font=("Microsoft YaHei", 9), bg="#FFF0F5", fg="#555555")
        pool_label.pack(pady=(0, 10))

        btn_frame = tk.Frame(dialog, bg="#FFF0F5")
        btn_frame.pack(fill=tk.X, padx=20)

        btn_night = tk.Button(btn_frame, text="前一天晚上没有带手机上床且醒了立即下床", bg="#FFB6C1", fg="white", font=("Microsoft YaHei", 9, "bold"), bd=0, wraplength=360, justify=tk.LEFT)
        btn_noon = tk.Button(btn_frame, text="中午没有带手机上床且醒了立即下床", bg="#FFD700", fg="white", font=("Microsoft YaHei", 9, "bold"), bd=0, wraplength=360, justify=tk.LEFT)
        btn_redeem = tk.Button(btn_frame, text="兑换激励分钟 (改变自己)", bg="#98FB98", fg="white", font=("Microsoft YaHei", 10, "bold"), bd=0)

        btn_night.pack(fill=tk.X, pady=6)
        btn_noon.pack(fill=tk.X, pady=6)
        btn_redeem.pack(fill=tk.X, pady=(12, 6))

        def refresh_state():
            today_str = datetime.now().strftime("%Y-%m-%d")
            claims = global_data.get("incentive_claims", {})
            night_claimed = claims.get("night") == today_str
            noon_claimed = claims.get("noon") == today_str
            pool = int(global_data.get("today_incentive_pool", 0))

            pool_label.config(text=f"当前激励可兑换: {pool} 分钟 (改变自己)")
            btn_night.config(state=tk.DISABLED if night_claimed else tk.NORMAL)
            btn_noon.config(state=tk.DISABLED if noon_claimed else tk.NORMAL)
            btn_redeem.config(state=tk.NORMAL if pool > 0 else tk.DISABLED)

        def claim_night():
            today_str = datetime.now().strftime("%Y-%m-%d")
            claims = global_data.get("incentive_claims", {})
            if claims.get("night") == today_str:
                return
            reward = random.randint(1, 2)
            global_data["today_incentive_pool"] = int(global_data.get("today_incentive_pool", 0)) + reward
            claims["night"] = today_str
            global_data["incentive_claims"] = claims
            save_data()
            messagebox.showinfo("激励奖励", f"抽中 {reward} 分钟【改变自己】时间，已加入可兑换池。", parent=dialog)
            refresh_state()

        def claim_noon():
            today_str = datetime.now().strftime("%Y-%m-%d")
            claims = global_data.get("incentive_claims", {})
            if claims.get("noon") == today_str:
                return
            reward = 1
            global_data["today_incentive_pool"] = int(global_data.get("today_incentive_pool", 0)) + reward
            claims["noon"] = today_str
            global_data["incentive_claims"] = claims
            save_data()
            messagebox.showinfo("激励奖励", "获得 1 分钟【改变自己】时间，已加入可兑换池。", parent=dialog)
            refresh_state()

        def redeem_incentive():
            pool = int(global_data.get("today_incentive_pool", 0))
            if pool <= 0:
                return
            count = 1
            if pool > 1:
                count = simpledialog.askinteger("兑换激励分钟 (改变自己)", f"当前可兑换 {pool} 分钟 (改变自己)，想兑换几分钟 (改变自己)？", minvalue=1, maxvalue=pool, parent=dialog)
                if count is None:
                    return
            if not messagebox.askyesno("兑换确认", f"确定兑换 {count} 分钟【改变自己】时间吗？", parent=dialog):
                return

            for _ in range(count):
                global_data["today_exchanged_time"] += 1
                global_data["exchange_history"].append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "exchange_time": 1,
                    "used_points": 0,
                    "source": "incentive"
                })

            global_data["today_incentive_pool"] = pool - count
            save_data()
            self.update_dashboard()
            messagebox.showinfo("兑换成功", f"已兑换 {count} 分钟【改变自己】时间。", parent=dialog)
            refresh_state()

        btn_night.config(command=claim_night)
        btn_noon.config(command=claim_noon)
        btn_redeem.config(command=redeem_incentive)
        refresh_state()

    def exchange_points(self):
        if not global_data.get("today_task_submitted"):
            messagebox.showwarning("拦截", "请先提交今天的任务清单！")
            return

        monthly_tomatoes = sum(1 for item in global_data.get("study_history", []) if item["date"].startswith(datetime.now().strftime("%Y-%m")))
        bonus = (monthly_tomatoes // 40) * 5
        rate = 25 + bonus
        cost_per_minute = 100 / rate
            
        pts = global_data["total_points"]
        max_mins = int(pts / cost_per_minute)

        if max_mins < 1:
            messagebox.showwarning("积分不足", f"换1分钟【改变自己】时间需要 {cost_per_minute:.1f} 积分，先去赚积分吧！")
            return
            
        count = simpledialog.askinteger("兑换时间", f"当前积分可兑换最多 {max_mins} 分钟【改变自己】。\n你想兑换多少分钟？", minvalue=1, maxvalue=max_mins)
        if count is None or count <= 0:
            return
            
        total_cost = int(count * cost_per_minute)

        if messagebox.askyesno("兑换确认", f"确定消耗 {total_cost} 积分兑换 {count} 分钟【改变自己】时间吗？"):
            global_data["total_points"] -= total_cost
            global_data["today_exchanged_time"] += count
            global_data["exchange_history"].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "exchange_time": count,
                "used_points": total_cost,
                "source": "points"
            })
            save_data()
            self.update_dashboard()
            messagebox.showinfo("兑换成功", f"成功消耗 {total_cost} 积分，兑换了 {count} 分钟！")

if __name__ == "__main__":
    enforce_single_instance()
    app = StudyGameUI()
    app.mainloop()