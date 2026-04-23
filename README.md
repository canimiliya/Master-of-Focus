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
├── sgp_qt_notify.py         # 企业微信 Webhook 通知模块
├── sgp_qt_prompts.py        # LLM 提示词模板
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

## 配置说明

### API 配置

1. **MinerU API**（PDF解析）：
   - 访问 [MinerU](https://mineru.net) 获取 Token
   - 在「论文批量翻译」窗口点击「API 设置」配置

2. **SiliconFlow API**（翻译服务）：
   - 访问 [SiliconFlow](https://siliconflow.cn) 获取 API Key
   - 在「论文批量翻译」窗口点击「API 设置」配置

3. **LLM Vision API**（图片/PDF识别）：
   - 支持 OpenAI、DeepSeek 等兼容 API
   - 在「LLM Vision API」功能中配置

### 通知配置

1. **企业微信 Webhook**：
   - 在企业微信群聊中添加「群机器人」获取 Webhook URL
   - 在「设置」→「通知设置」中配置

### 数据目录配置

- 首次启动时会要求选择数据存储根目录
- 配置文件位置：`~/.study_game/config.json`
- 可手动修改配置或通过界面设置

## 开发指南

### 环境设置

```bash
# 克隆仓库
git clone https://github.com/canimiliya/Master-of-Focus.git
cd Master-of-Focus

# 创建虚拟环境（可选）
python -m venv venv
venv\Scripts\activate  # Windows

# 安装依赖
pip install pyside6 matplotlib
pip install win10toast  # 可选：Windows 通知
```

### 代码结构

- **核心逻辑**：`sgp_qt_core.py` - 数据模型与业务逻辑（无 Qt 依赖）
- **UI 混合类**：`sgp_qt_main_window.py` 组合多个 Mixin 功能模块
- **功能模块**：每个 `sgp_qt_*.py` 文件负责特定功能
- **POC 模块**：`pdf2md_poc.py` 包含 PDF 解析与翻译核心算法

### 运行测试

```bash
# 直接运行主程序
python study_game_pro_qt.py

# 运行独立测试脚本
python pdf2md_poc.py  # 测试 PDF 解析功能
```

## 贡献指南

我们欢迎任何形式的贡献，包括但不限于：

### 报告问题
- 使用 GitHub Issues 报告 Bug 或提出功能建议
- 提供详细的重现步骤和环境信息

### 提交代码
1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

### 开发规范
- 遵循现有代码风格（PEP 8 基础）
- 添加适当的类型注解
- 确保代码兼容 Python 3.10+
- 更新相关文档（README、注释等）

## 常见问题

### Q: 程序启动时提示「数据目录未选择」
A: 首次启动必须选择数据存储根目录，请按照提示选择合适的位置。

### Q: PDF 解析功能无法使用
A: 请确保已正确配置 MinerU API Token，并检查网络连接。

### Q: 企业微信通知不工作
A: 检查 Webhook URL 是否正确，确保企业微信群机器人已启用。

### Q: 打包后的程序无法运行
A: 确保使用 PyInstaller 打包时包含所有必要资源，或尝试在虚拟环境中打包。

### Q: 如何备份数据？
A: 数据存储在「专注改变（个人软件数据）」文件夹中，可直接复制该文件夹进行备份。

## 更新日志

### v1.0.0 (2026-04-23)
- 初始版本发布
- 集成番茄钟、任务管理、阅读管理、PDF翻译等核心功能
- 支持企业微信通知
- 提供数据图表与报表导出

## License

MIT License，详见 [LICENSE](LICENSE)。