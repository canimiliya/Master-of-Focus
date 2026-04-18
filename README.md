# 专注王者（Study Game Pro）

一个面向个人专注与自律的 Windows 桌面工具（PySide6 / Qt GUI），集番茄钟、任务清单、复盘、兑换激励与阅读管理于一体。当前版本为 Qt 模块化重构后的大更新。

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
- 所有数据都存放在该文件夹内：
  - `study_game_reward.json`
  - `daily_tasks_log.txt`
  - `随手记.txt`
  - `随手记/`（附件按日期归档）
- 需要更改数据存储路径：主界面右侧“更改数据存储目录”。
- 支持防多开：同一时间只允许一个实例运行。

## 4. 功能概览

- 番茄钟：25 分钟专注 + 5 分钟休息（可绑定任务）
- 每日任务清单：按类别管理、完成率统计、跨天携带（含长期任务）
- 奖惩与复盘：每日结算、奖励/惩罚日志
- 数据图表与报表：统计图表、CSV 报表导出
- 游戏化兑换：积分兑换娱乐时间、激励池
- 随手记：文本 + 文件归档（按日期）
- 今日工作日志：按任务聚合今日专注耗时、自动归档

## 5. 阅读管理（大更新）

- 书籍卡片列表：每本书独立卡片，显示进度条、已专注时长与预计剩余
- 目录树结构：章节/小节树状结构，支持右键加入今日任务
- 小节驱动进度：有小节时进度由小节汇总，章节为汇总层
- 任务分类选择：右键加入任务时可选“科研/理论技术”
- 进度条视觉：糖果风格渐变填充，进度越高颜色越饱满

## 6. 项目结构（Qt 模块化）

- [study_game_pro_qt.py](study_game_pro_qt.py)：程序入口
- [sgp_qt_main_window.py](sgp_qt_main_window.py)：主窗口与业务 UI
- [sgp_qt_dialogs.py](sgp_qt_dialogs.py)：对话框（如任务选择）
- [sgp_qt_core.py](sgp_qt_core.py)：配置/数据读写与核心逻辑（无 Qt 依赖）
- [sgp_qt_platform.py](sgp_qt_platform.py)：平台相关（防多开、Windows 通知）
- [sgp_qt_reading.py](sgp_qt_reading.py)：阅读管理模块（卡片 UI、目录树、进度管理）

## 7. Windows 打包为 .exe

推荐使用 PyInstaller：

```bash
pip install pyinstaller
python -m PyInstaller --onefile --noconsole --name change_self study_game_pro_qt.py
```

输出：`dist/change_self.exe`

## 8. License

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。
