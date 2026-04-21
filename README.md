# ✨ 改变自己（Study Game Pro）

一个面向个人专注与自律的 Windows 桌面工具（PySide6 / Qt），集番茄钟、任务清单、复盘、兑换激励、随手记、阅读管理、论文批量翻译与数据看板于一体。

---

## 运行环境

- Windows 10/11
- Python 3.10+

## 安装与运行

```bash
pip install pyside6 matplotlib
python study_game_pro_qt.py
```

可选依赖：

```bash
pip install win10toast    # Windows 系统通知
```

## 首次使用

- 首次启动必须选择「数据存储根目录」，未选择会直接退出
- 程序会在该目录下创建 `专注改变（个人软件数据）`，所有数据存放在此：
  - `study_game_reward.json` — 主数据
  - `daily_tasks_log.txt` — 任务设定 / 复盘 / 番茄日志
  - `随手记.txt`、`随手记/` — 随手记与附件按日期归档
  - `任务复盘报表_按日期.csv`、`任务复盘报表_按分类汇总.csv` — 自动导出
  - `阅读进度报表_YYYYMMDD.csv` — 阅读管理手动导出
- 配置文件：`~/.study_game/config.json`（数据目录、取消次数、节假日缓存、API Key 等）
- 支持防多开：同一时间只允许一个实例运行

---

## 功能概览

### 🍅 番茄钟

- 25 分钟专注 + 5 分钟休息，必须绑定「学习类任务」
- 仅统计「科研 / 理论/技术」类别的专注；「生活 / 兴趣爱好」不计入

### ✅ 每日任务清单

- 按类别管理、完成率统计、跨天携带（含长期任务）
- 取消任务按「本月取消次数」指数级扣分；长期任务未完成前不可删除

### 📊 复盘与结算

- 每日复盘、奖励/惩罚、23:30 复盘提醒
- 数据图表与报表：学习/兑换时间分布、时段热力、CSV 导出

### 🎮 游戏化兑换

- 积分兑换「改变自己」时间
- 激励池（起床/不带手机上床等）可抽分钟奖励

### 📝 随手记

- 文本 + 文件/图片归档，按日期文件夹自动整理

### 📖 阅读管理

- 书籍卡片列表：独立卡片显示进度条、累计专注时长与预计剩余
- 目录树结构：章节/小节树状结构，右键加入今日任务
- 小节驱动进度：叶子节点汇总，章节为汇总层
- 糖果风格渐变进度条
- 目录导入：从「目录截图 → JSON」流程导入嵌套目录（内置提示词与复制按钮）
- 文献精读规划：生成/导入三阶段精读规划
- 报表导出：阅读进度 CSV

### 📄 论文批量翻译（PDF → Markdown）

- 批量将 PDF 论文转为结构化 Markdown（MinerU 精准解析 API）
- 自动语言检测：中文论文直接保存，英文论文自动翻译为中文
- 翻译模型：DeepSeek-V3.2（via SiliconFlow），流式输出
- 支持拖拽添加文件、实时进度显示、后台线程处理不卡界面
- API 设置独立弹窗管理，Token/Key 加密存储

### 🤖 LLM Vision API

- 内置 OpenAI 兼容视觉 API 调用（支持 DeepSeek、OpenAI 等）
- 图片/PDF 识别与结构化提取

---

## 项目结构

```
study_game_pro/
├── study_game_pro_qt.py     # 程序入口
├── sgp_qt_main_window.py    # 主窗口（Mixin 组合）
├── sgp_qt_ui.py             # 主界面 UI 构建与按钮绑定
├── sgp_qt_core.py           # 配置/数据读写与核心逻辑（无 Qt 依赖）
├── sgp_qt_dialogs.py        # 对话框（任务选择/确认等）
├── sgp_qt_platform.py       # 平台相关（防多开、Windows 通知）
├── sgp_qt_timer.py          # 番茄钟 / 专注记录与积分发放
├── sgp_qt_tasks.py          # 任务清单、长期任务、取消扣分
├── sgp_qt_logs.py           # 复盘 / 日志 / 报表导出
├── sgp_qt_exchange.py       # 积分兑换与激励池
├── sgp_qt_memo.py           # 随手记与附件归档
├── sgp_qt_reading.py        # 阅读管理（目录树、进度、精读规划）
├── sgp_qt_charts.py         # Matplotlib 图表看板
├── sgp_qt_pdf2md.py         # 论文批量翻译窗口（UI + 后台线程）
├── sgp_qt_api.py            # LLM Vision API 辅助（无 Qt 依赖）
├── pdf2md_poc.py            # PDF→Markdown 核心逻辑（MinerU + 翻译）
├── .gitignore
├── LICENSE
└── README.md
```

## Windows 打包

```bash
pip install pyinstaller
python -m PyInstaller --onefile --noconsole --name change_self study_game_pro_qt.py
```

输出：`dist/change_self.exe`

## License

MIT License，详见 [LICENSE](LICENSE)。
