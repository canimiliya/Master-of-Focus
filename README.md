# 专注王者（Study Game Pro）

一个面向个人专注与自律的 Windows 桌面工具（PySide6 / Qt GUI），集番茄钟、任务清单、复盘、兑换激励、随手记、阅读管理与数据看板于一体。当前版本为 Qt 模块化重构后的大更新。

## 1. 运行环境

- Windows 10/11
- Python 3.8+（推荐 3.10+）

## 2. 安装与运行

在项目根目录执行：

```bash
pip install pyside6 matplotlib
python study_game_pro_qt.py
```

可选依赖（Windows 系统通知）：

```bash
pip install win10toast
```

## 3. 第一次使用注意事项

- 首次启动必须选择“数据存储根目录”，未选择会直接退出。
- 程序会在该根目录下创建/使用：`专注改变（个人软件数据）`
- 主要数据都存放在该文件夹内（会随着功能使用逐步生成）：
  - `study_game_reward.json`（主数据）
  - `daily_tasks_log.txt`（任务设定/复盘/番茄等日志）
  - `随手记.txt`、`随手记/`（随手记与附件按日期归档）
  - `任务复盘报表_按日期.csv`、`任务复盘报表_按分类汇总.csv`（自动导出）
  - `阅读进度报表_YYYYMMDD.csv`（阅读管理手动导出）
- 程序配置文件位于用户目录：`~/.study_game/config.json`（用于记住数据目录、取消次数、节假日 API 缓存等）。
- 需要更改数据存储路径：主界面右侧“更改数据存储目录”。
- 支持防多开：同一时间只允许一个实例运行。

## 4. 功能概览

- 番茄钟：25 分钟专注 + 5 分钟休息（必须绑定“学习类任务”）
  - 仅统计并记录类别为「科研 / 理论/技术」的专注；「生活 / 兴趣爱好」不计入番茄与专注记录
- 每日任务清单：按类别管理、完成率统计、跨天携带（含长期任务）
  - 取消任务会按“本月取消次数”指数级扣分；长期任务未完成前不可删除
- 复盘与结算：每日复盘、奖励/惩罚、23:30 复盘提醒
- 数据图表与报表：学习/兑换时间分布、时段热力、CSV 报表导出
- 游戏化兑换：积分兑换「改变自己」时间；激励池（起床/不带手机上床等）可抽分钟奖励
- 随手记：文本 + 文件/图片归档（按日期文件夹自动整理）
- 今日工作日志：汇总当天专注日志与已完成任务耗时
- 节假日显示：可选在线节假日信息（支持缓存；可在配置中关闭）

## 5. 阅读管理（大更新）

- 书籍卡片列表：每本书独立卡片，显示进度条、累计专注时长与预计剩余
- 目录树结构：章节/小节树状结构，支持右键加入今日任务（科研 / 理论/技术）
- 小节驱动进度：存在小节时进度由叶子节点汇总，章节为汇总层
- 进度条视觉：糖果风格渐变填充，进度越高颜色越饱满
- 目录导入：支持从“目录截图 → JSON”流程导入嵌套目录（工具内置提示词与复制按钮）
- 文献精读规划：支持生成/导入三阶段精读规划（同样提供 JSON 提示词）
- 报表导出：阅读进度 CSV（包含章节/小节与耗时）

## 6. 项目结构（Qt 模块化）

- [study_game_pro_qt.py](study_game_pro_qt.py)：程序入口
- [sgp_qt_main_window.py](sgp_qt_main_window.py)：主窗口与业务 UI
- [sgp_qt_ui.py](sgp_qt_ui.py)：主界面 UI 构建与按钮绑定
- [sgp_qt_dialogs.py](sgp_qt_dialogs.py)：对话框（如任务选择/确认）
- [sgp_qt_core.py](sgp_qt_core.py)：配置/数据读写与核心逻辑（无 Qt 依赖）
- [sgp_qt_platform.py](sgp_qt_platform.py)：平台相关（防多开、Windows 通知）
- [sgp_qt_timer.py](sgp_qt_timer.py)：番茄钟/专注记录与积分发放
- [sgp_qt_tasks.py](sgp_qt_tasks.py)：任务清单、长期任务、取消扣分等
- [sgp_qt_logs.py](sgp_qt_logs.py)：复盘/日志/报表导出/工作日志
- [sgp_qt_exchange.py](sgp_qt_exchange.py)：积分兑换与激励池
- [sgp_qt_memo.py](sgp_qt_memo.py)：随手记与附件归档
- [sgp_qt_charts.py](sgp_qt_charts.py)：Matplotlib 图表看板（可选依赖）
- [sgp_qt_reading.py](sgp_qt_reading.py)：阅读管理（书籍目录树、进度、文献精读规划、导出）

## 7. Windows 打包为 .exe

推荐使用 PyInstaller：

```bash
pip install pyinstaller
python -m PyInstaller --onefile --noconsole --name change_self study_game_pro_qt.py
```

输出：`dist/change_self.exe`

## 8. License

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。
