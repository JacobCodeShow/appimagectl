# appimagectl

一个面向 GNOME 桌面的 AppImage 管理工具，用来把零散的 AppImage 整理成可长期维护的本地安装：复制到统一目录、生成 .desktop、提取图标、修复 StartupWMClass、创建桌面快捷方式，并维护已安装清单。

English summary: `appimagectl` is a GNOME-oriented AppImage manager for Fedora and Ubuntu. It installs AppImages into a managed directory, creates `.desktop` entries and icons, keeps an installed-app index, and can verify, scan, and import unmanaged AppImages.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-GNOME%20%7C%20Fedora%20%7C%20Ubuntu-lightgrey.svg)]()

## English At A Glance

- Primary audience: GNOME users on Fedora, Ubuntu, and compatible distributions
- Runtime: Python 3.10+ with standard library only
- Main commands: `--install`, `--reinstall`, `--remove`, `--list`, `--verify`, `--config`, `--scan`, `--import`
- Default config location: `~/.config/appimagectl/`
- Output language: auto-detected from `APPIMAGECTL_LANG`, `LC_ALL`, `LC_MESSAGES`, then `LANG`

Quick start:

```bash
./appimagectl --install ~/Downloads/App.AppImage
./appimagectl --list
./appimagectl --remove AppName
```

## 特性

- 自动安装 AppImage 到统一目录，补齐执行权限
- 从 AppImage 内部提取 .desktop 元数据、图标、分类和注释
- 优先使用真实 StartupWMClass，减轻 GNOME Dock 图标分裂问题
- 识别 Electron 应用并自动追加 --no-sandbox
- 根据文件名识别版本，支持升级、重装和降级保护
- 维护已安装清单，支持列表、校验、清理残留记录
- 扫描未被本工具管理的 AppImage，并按需导入或修复
- 仅依赖 Python 标准库，无需 pip 安装第三方包

## 系统要求

| 项目 | 要求 |
| --- | --- |
| Python | 3.10 或更高版本 |
| 桌面环境 | GNOME |
| 图形会话 | Wayland 或 X11 |
| 发行版 | Fedora、Ubuntu 及其兼容发行版 |

安装过程中会调用下列系统命令：

- gtk-update-icon-cache
- update-desktop-database
- gio
- xdg-user-dir

其中前两个命令缺失时，工具会尝试通过 dnf 或 apt 自动安装对应系统包。

## 安装

```bash
git clone https://github.com/JacobCodeShow/appimagectl.git
cd appimagectl
chmod +x appimagectl
```

如果你更习惯 SSH，也可以使用：

```bash
git clone git@github.com:JacobCodeShow/appimagectl.git
```

可选：创建一个更短的全局命令。

```bash
sudo ln -s "$(pwd)/appimagectl" /usr/local/bin/appimagectl
```

## 项目结构

当前仓库采用“单入口 + 内部模块目录”的轻量结构：

```text
appimagectl          # CLI 入口（可直接执行）
appimagectl_core/
	shared.py           # 常量、日志、基础工具
	store.py            # 配置与安装记录
	__about__.py        # 项目版本号单一来源
	i18n.py             # 语言选择、装载和 tr() 接口
	locales/
		en.py             # 英文消息表
		zh.py             # 中文消息表
	desktop.py          # .desktop / 图标 / WMClass
	install.py          # 安装与卸载主流程
	commands.py         # list / verify / config / scan / import
```

这样可以直接使用 `./appimagectl`，同时把内部实现限制在 `appimagectl_core/` 下，便于后续维护和扩展。

如果需要更新脚本版本，优先修改 `appimagectl_core/__about__.py` 中的 `__version__`。

输出语言会按以下顺序自动选择：`APPIMAGECTL_LANG` > `LC_ALL` > `LC_MESSAGES` > `LANG`。

- 以 `zh` 开头时显示中文
- 其他值默认显示英文

这条规则当前覆盖 `--help`、参数错误、`--version`、`--config`、`--list`、`--verify`、`--scan`、`--import` 以及安装过程中的主要提示信息。

语言文件约定：

- 所有语言文件统一放在 `appimagectl_core/locales/` 下
- 每个语言文件导出一个顶层 `MESSAGES` 字典
- 消息 key 在不同语言文件中应保持一致，缺失 key 会回退到英文
- 新增语言时，优先新增独立文件，例如 `ja.py`、`fr.py`，再在 `appimagectl_core/i18n.py` 中注册

## 快速开始

以下示例默认直接运行仓库中的可执行入口；如果你已经创建了全局软链接，也可以直接使用 `appimagectl`。

```bash
# 安装
./appimagectl --install ~/Downloads/Obsidian-1.8.10.AppImage

# 指定显示名称
./appimagectl --install ~/Downloads/ZenBrowser.AppImage "Zen Browser"

# 查看已安装应用
./appimagectl --list

# 卸载
./appimagectl --remove Obsidian
```

## 命令用法

```text
appimagectl --install <file> [name]
appimagectl --reinstall <file> [name]
appimagectl --remove <name>
appimagectl --list
appimagectl --verify
appimagectl --config
appimagectl --scan
appimagectl --import
```

无参数执行时会显示帮助信息。

### 安装

```bash
# 显式安装
./appimagectl --install ~/Downloads/App.AppImage

# 重新安装
./appimagectl --reinstall ~/Downloads/App.AppImage

# 跳过确认提示
./appimagectl -y --install ~/Downloads/App.AppImage
```

安装流程包含以下动作：

1. 复制 AppImage 到配置中的安装目录
2. 解压 AppImage 并提取内部 .desktop 元数据
3. 识别 StartupWMClass，必要时做运行时检测或文件名兜底
4. 提取图标，必要时生成占位图标
5. 生成 .desktop 文件并更新系统缓存
6. 按配置创建桌面快捷方式，并写入安装清单

### 卸载

```bash
./appimagectl --remove Obsidian
./appimagectl --remove zen-browser
```

卸载会删除：

- 安装目录中的 AppImage 文件
- .desktop 文件
- 图标缓存目录中的图标
- 桌面快捷方式
- installed.json 中的记录

### 列表与校验

```bash
./appimagectl --list
./appimagectl --verify
./appimagectl -y --verify
```

- --list: 展示已安装应用、版本、路径、安装时间和异常状态
- --verify: 校验 AppImage、.desktop、图标是否存在，可交互清理坏记录
- -y 或 --force 配合 --verify 使用时，会自动清理异常项

### 扫描与导入

```bash
# 扫描当前桌面配置引用到、但未被管理的 AppImage
./appimagectl --scan

# 额外扫描目录
./appimagectl --scan --scan-dir ~/Downloads --scan-dir ~/Apps

# 深度扫描，识别无 .AppImage 后缀文件
./appimagectl --scan --deep --scan-dir ~/Downloads

# 导入扫描结果
./appimagectl --import

# 导入并自动补 .desktop / 图标 / WMClass
./appimagectl --import --fix --scan-dir ~/Downloads
```

- --scan: 收集未纳入 installed.json 管理的 AppImage 候选项
- --scan-dir: 额外递归扫描目录，可多次传入
- --deep: 使用文件头魔数识别 AppImage，速度更慢但更完整
- --import: 将扫描结果写入安装清单
- --fix: 导入时尝试创建缺失的 .desktop、图标和 StartupWMClass

### 配置与版本

```bash
./appimagectl --config
./appimagectl --version
```

工具会显示用户配置和自动检测到的系统信息，包括发行版、会话类型、图标目录、桌面文件目录和已安装数量。

## 配置文件

首次运行会自动创建以下文件：

- ~/.config/appimagectl/config.json
- ~/.config/appimagectl/installed.json

默认配置如下：

```json
{
	"version": 1,
	"user": {
		"install_dir": "~/.AppImage",
		"default_icon_size": 256,
		"auto_detect_wmclass": true,
		"create_desktop_shortcut": true,
		"ask_before_delete": true
	}
}
```

## 工作目录与输出位置

- AppImage 安装目录：默认 ~/.AppImage
- 桌面文件目录：~/.local/share/applications
- 图标目录：~/.local/share/icons/hicolor
- 桌面快捷方式：通过 xdg-user-dir DESKTOP 检测，失败时回退到 ~/Desktop

## 已知行为

- 版本比较基于文件名中的数字，例如 App-1.2.3.AppImage
- 当内部 .desktop 缺少 StartupWMClass 时，工具会尝试运行目标应用约 5 秒来检测窗口类名
- Electron 应用会在 Exec 字段追加 --no-sandbox
- 若无法提取图标，会优先调用 ImageMagick；再失败则生成纯标准库占位 PNG

## 开发与提交

提交前建议至少执行一次帮助和版本检查：

```bash
./appimagectl --help
./appimagectl --version
```

如果你准备对外发布，可以继续补充截图、发行说明或示例 AppImage 场景。

## License

本项目使用 MIT License，见 [LICENSE](LICENSE)。


