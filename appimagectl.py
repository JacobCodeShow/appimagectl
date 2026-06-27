#!/usr/bin/env python3
"""
AppImage Installer for GNOME (Fedora / Ubuntu 通用)
===================================================

用法:
  {SCRIPT_NAME} --install <file> [name]     安装
  {SCRIPT_NAME} --reinstall <file> [name]   删除已有后重新安装
  {SCRIPT_NAME} <file> [name]               安装（简写）
  {SCRIPT_NAME} --remove <name>             卸载
  {SCRIPT_NAME} --list                      查看已安装
  {SCRIPT_NAME} --verify                    验证完整性
  {SCRIPT_NAME} --config                    查看配置
  {SCRIPT_NAME} --scan                      扫描未管理的 AppImage
  {SCRIPT_NAME} --import                    导入未管理的 AppImage

  -y / -f   跳过所有确认提示

配置文件:   ~/.config/appimage-installer/config.json
已安装列表: ~/.config/appimage-installer/installed.json
"""

# ══════════════════════════════════════════
# 版本检查
# ══════════════════════════════════════════

import sys

MIN_VERSION = (3, 10)
if sys.version_info < MIN_VERSION:
    print(
        f"需要 Python {'.'.join(map(str, MIN_VERSION))}+，"
        f"当前 {sys.version.split()[0]}",
        file=sys.stderr,
    )
    sys.exit(1)

# ══════════════════════════════════════════
# 导入（仅标准库，零外部依赖）
# ══════════════════════════════════════════

import argparse
from appimagectl_lib.__about__ import __version__ as VERSION
from appimagectl_lib.commands import cmd_config, cmd_import, cmd_list, cmd_remove, cmd_scan, cmd_verify
from appimagectl_lib.install import cmd_install
from appimagectl_lib.shared import (
    CONFIG_DIR,
    DISTRO,
    SCRIPT_NAME,
    SESSION_TYPE,
    check_dependencies,
)
from appimagectl_lib.store import load_installed


# ══════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description="AppImage Installer for GNOME (Fedora / Ubuntu)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage=f"{SCRIPT_NAME} [选项] [文件] [名称]",
    )
    # 隐藏的位置参数（兼容简写形式）
    parser.add_argument("appimage", nargs="?", default=None, help=argparse.SUPPRESS)
    parser.add_argument("name", nargs="?", default=None, help=argparse.SUPPRESS)

    # 主要操作
    parser.add_argument(
        "--install", "-i", action="store_true",
        help="安装 AppImage（显式指定，与直接传文件等效）",
    )
    parser.add_argument(
        "--reinstall", action="store_true",
        help="删除已有安装后重新安装",
    )
    parser.add_argument("--remove", "-r", metavar="NAME", help="卸载应用")
    parser.add_argument("--list", "-l", action="store_true", help="查看已安装列表")
    parser.add_argument("--verify", action="store_true", help="验证完整性")
    parser.add_argument("--config", "-c", action="store_true", help="查看配置")

    # 扫描 & 导入
    parser.add_argument(
        "--scan", "-s", action="store_true",
        help="扫描未管理的 AppImage",
    )
    parser.add_argument(
        "--import", "-I", dest="do_import", action="store_true",
        help="将未管理的 AppImage 导入管理列表",
    )
    parser.add_argument(
        "--scan-dir", metavar="DIR", action="append", default=[],
        help="指定扫描目录（可多次使用）",
    )
    parser.add_argument(
        "--deep", action="store_true",
        help="深度扫描：用文件头魔数检测（较慢，含无后缀文件）",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="自动修复：创建缺失的 .desktop 文件和图标",
    )

    # 修饰符
    parser.add_argument(
        "--version", "-v", action="store_true",
        help="显示版本信息",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="跳过所有确认提示")
    parser.add_argument("-f", "--force", action="store_true", help="同 -y")

    return parser


def main():
    parser = build_parser()

    args = parser.parse_args()
    force = args.yes or args.force

    if args.install and args.reinstall:
        parser.error("--install 和 --reinstall 不能同时使用")

    match True:
        case _ if args.version:
            print(f"{SCRIPT_NAME}  {VERSION}")
            print(f"  Python   {sys.version.split()[0]}")
            print(f"  系统     {DISTRO}")
            print(f"  会话     {SESSION_TYPE}")
            print(f"  配置目录 {CONFIG_DIR}")
            apps = load_installed()
            print(f"  已安装   {len(apps)} 个应用")
        case _ if args.config:
            cmd_config()
        case _ if args.list:
            cmd_list()
        case _ if args.verify:
            cmd_verify(force=force)
        case _ if args.remove:
            cmd_remove(args.remove, force=force)
        case _ if args.do_import:
            cmd_import(
                scan_dirs=args.scan_dir or None,
                deep=args.deep,
                fix=args.fix,
                force=force,
            )
        case _ if args.scan:
            cmd_scan(
                scan_dirs=args.scan_dir or None,
                deep=args.deep,
            )
        case _ if args.appimage:
            check_dependencies()
            cmd_install(
                args.appimage,
                custom_name=args.name,
                reinstall=args.reinstall,
                force=force,
            )
        case _ if args.install or args.reinstall:
            parser.error("请指定 AppImage 文件路径")
        case _:
            parser.print_help(sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()