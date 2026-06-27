import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from appimagectl_lib.__about__ import __version__ as VERSION
from appimagectl_lib.desktop import (
    detect_wmclass_runtime,
    ensure_index_theme,
    find_best_icon,
    find_internal_desktop,
    generate_placeholder_icon,
    is_electron_app,
    parse_desktop_file,
    try_imagemagick_icon,
)
from appimagectl_lib.shared import (
    C,
    DISTRO,
    SESSION_TYPE,
    ask,
    compare_versions,
    desktop_dir,
    extract_version,
    icon_base_dir,
    log_error,
    log_info,
    log_ok,
    log_warn,
    make_id,
    print_kv,
    safe_mkdir,
    strip_version,
    title_case,
    update_system_caches,
    xdg_desktop_dir,
)
from appimagectl_lib.store import (
    add_installed,
    find_installed,
    find_installed_by_base,
    get_config,
    init_config,
    remove_installed,
    resolve_install_dir,
)


def extract_appimage(appimage_path: Path) -> Path | None:
    work_dir = Path(tempfile.mkdtemp())
    try:
        subprocess.run(
            [str(appimage_path), "--appimage-extract"],
            cwd=str(work_dir),
            capture_output=True,
            check=True,
            timeout=120,
        )
        squashfs = work_dir / "squashfs-root"
        if squashfs.exists():
            return work_dir
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        pass
    shutil.rmtree(work_dir, ignore_errors=True)
    return None


def full_remove(
    app: dict,
    delete_appimage: bool = True,
    ask_delete: bool = True,
):
    ibd = icon_base_dir()

    log_info(f"正在移除 {app['display_name']} ({app.get('wmclass', '?')})...")

    desktop_path = Path(app["desktop_file"])
    if desktop_path.exists():
        desktop_path.unlink()
        log_ok("已删除桌面文件")

    (ibd / "256x256" / "apps" / f"{app['icon_name']}.png").unlink(missing_ok=True)
    (ibd / "scalable" / "apps" / f"{app['icon_name']}.svg").unlink(missing_ok=True)

    shortcut = xdg_desktop_dir() / desktop_path.name
    if shortcut.exists():
        shortcut.unlink()
        log_ok("已删除桌面快捷方式")

    appimage = Path(app["appimage_path"])
    if delete_appimage and appimage.exists():
        should_delete = True
        if ask_delete and get_config("ask_before_delete", True):
            print(f"  {C.YELLOW}是否删除 AppImage 文件？{C.NC}", file=sys.stderr)
            print(f"  {C.DIM}{appimage}{C.NC}", file=sys.stderr)
            should_delete = ask("  [y/N]").lower() == "y"
        if should_delete:
            appimage.unlink()
            log_ok(f"已删除 AppImage: {appimage}")
        else:
            log_info("保留 AppImage 文件")

    remove_installed(app["app_id"])

    update_system_caches()
    log_ok(f"已移除 {app['display_name']}")


def cmd_install(
    appimage_str: str,
    custom_name: str | None = None,
    reinstall: bool = False,
    force: bool = False,
):
    appimage_path = Path(appimage_str).resolve()

    if not appimage_path.exists():
        log_error(f"文件不存在: {appimage_path}")
        sys.exit(1)

    if not appimage_path.name.lower().endswith(".appimage"):
        if not force:
            response = ask(
                f"{C.YELLOW}[WARN]{C.NC} 文件扩展名不是 .AppImage，是否继续？[y/N]"
            )
            if response.lower() != "y":
                sys.exit(0)

    init_config()
    install_dir = resolve_install_dir()
    ibd = icon_base_dir()
    applications_dir = desktop_dir()

    name_clean = appimage_path.name
    if name_clean.lower().endswith(".appimage"):
        name_clean = name_clean[: -len(".appimage")]

    base_name = strip_version(name_clean)
    version = extract_version(name_clean)
    app_id = f"appimage-{make_id(name_clean)}"

    existing = find_installed(app_id=app_id)
    if not existing and base_name and base_name.lower() != name_clean.lower():
        existing = find_installed_by_base(base_name)

    if existing:
        existing_version = existing.get("version", "")

        if reinstall:
            log_info(f"重新安装：移除已有的 {existing['display_name']}...")
            full_remove(existing, delete_appimage=True, ask_delete=False)

        elif version and existing_version:
            comparison = compare_versions(version, existing_version)
            if comparison > 0:
                log_info(f"检测到版本升级: {existing_version} → {version}")
                log_info(f"移除旧版本 {existing['display_name']}...")
                full_remove(existing, delete_appimage=True, ask_delete=False)
            elif comparison == 0:
                if force:
                    full_remove(existing, delete_appimage=True, ask_delete=False)
                else:
                    log_warn(f"版本 {version} 已安装")
                    log_info("如需重新安装，请使用:")
                    log_info(f"  {sys.argv[0]} --reinstall {appimage_path}")
                    log_info(f"  或添加 -y 参数:  {sys.argv[0]} -y {appimage_path}")
                    sys.exit(0)
            else:
                if force:
                    log_warn(f"降级: {existing_version} → {version}")
                    full_remove(existing, delete_appimage=True, ask_delete=False)
                else:
                    log_warn(
                        f"已安装版本 {existing_version}，"
                        f"当前版本 {version} 更旧"
                    )
                    log_info("如需降级，请添加 -y 参数")
                    sys.exit(1)
        else:
            if force or reinstall:
                log_info(f"移除已有安装 {existing['display_name']}...")
                full_remove(existing, delete_appimage=True, ask_delete=not force)
            else:
                log_warn(f"'{existing['display_name']}' 已安装")
                log_info("如需重新安装，请使用 --reinstall 或添加 -y 参数")
                sys.exit(0)

    action_word = "重新安装" if reinstall else "安装"
    log_info("=" * 41)
    log_info(f"  AppImage Installer v{VERSION}")
    log_info(f"  系统: {DISTRO} | 会话: {SESSION_TYPE}")
    log_info(f"  安装目录: {install_dir}")
    log_info("=" * 41)
    print(file=sys.stderr)

    log_info("步骤 1/6: 安装 AppImage 文件...")
    install_dir.mkdir(parents=True, exist_ok=True)
    target = install_dir / appimage_path.name

    if appimage_path != target:
        shutil.copy2(appimage_path, target)
        log_ok(f"已复制到 {target}")
    else:
        log_ok("文件已在目标位置")
    target.chmod(target.stat().st_mode | 0o111)

    log_info("步骤 2/6: 解析 AppImage 内部结构...")
    extract_dir = extract_appimage(target)
    if extract_dir:
        log_ok("AppImage 解析成功")
    else:
        log_warn("无法解析 AppImage 内部结构")

    log_info("步骤 3/6: 提取元数据...")
    meta: dict[str, str] = {}
    electron = False

    if extract_dir:
        electron = is_electron_app(extract_dir)
        if electron:
            log_ok("检测到 Electron 应用")

        internal_desktop = find_internal_desktop(extract_dir)
        if internal_desktop:
            meta = parse_desktop_file(internal_desktop)
            log_ok(f"已读取内部元数据: {internal_desktop.name}")
            for key in ("Name", "StartupWMClass", "Icon", "Categories"):
                if meta.get(key):
                    log_info(f"  {key}={meta[key]}")
        else:
            log_warn("未找到内部 .desktop 文件")

    log_info("步骤 4/6: 确定窗口类名...")
    wmclass_fallback = make_id(name_clean)
    wmclass = ""
    wmclass_source = ""

    if meta.get("StartupWMClass"):
        wmclass = meta["StartupWMClass"]
        wmclass_source = "内部 .desktop"
    else:
        detected = detect_wmclass_runtime(target)
        if detected:
            wmclass = detected
            wmclass_source = "运行时检测"
        else:
            wmclass = wmclass_fallback
            wmclass_source = "文件名推断"

    if wmclass_source == "文件名推断":
        log_warn(f"未能确定窗口类名，使用文件名推断: {wmclass}")
    else:
        log_ok(f"{wmclass_source}窗口类名: {wmclass}")

    match True:
        case _ if custom_name:
            display_name = custom_name
        case _ if meta.get("Name"):
            display_name = meta["Name"]
        case _ if wmclass_source != "文件名推断":
            display_name = title_case(wmclass)
        case _:
            display_name = name_clean.replace("-", " ").replace("_", " ")

    log_info("步骤 5/6: 提取图标...")
    icon_name = wmclass
    icon_found = False
    ensure_index_theme()

    if extract_dir:
        search_names: list[str] = []
        if meta.get("Icon"):
            search_names.append(meta["Icon"])
        search_names.extend([wmclass, strip_version(name_clean)])

        found_icon = find_best_icon(extract_dir, *search_names)
        if found_icon and found_icon.exists():
            if found_icon.suffix.lower() == ".svg":
                dest = ibd / "scalable" / "apps" / f"{icon_name}.svg"
            else:
                dest = ibd / "256x256" / "apps" / f"{icon_name}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(found_icon, dest)
            icon_found = True
            log_ok(f"已提取图标: {found_icon.name}")

    if not icon_found:
        log_warn("未能提取到图标，尝试生成占位图标...")
        placeholder = ibd / "256x256" / "apps" / f"{icon_name}.png"
        letter = display_name[0].upper() if display_name else "A"
        if try_imagemagick_icon(placeholder, letter):
            log_ok("已生成占位图标 (ImageMagick)")
            icon_found = True
        else:
            try:
                generate_placeholder_icon(placeholder)
                log_ok("已生成占位图标")
                icon_found = True
            except Exception:
                log_warn("占位图标生成失败，将使用系统默认图标")
                icon_name = "application-x-executable"

    log_info("步骤 6/6: 生成桌面文件...")
    desktop_file = applications_dir / f"{wmclass}.desktop"
    applications_dir.mkdir(parents=True, exist_ok=True)

    exec_args = " --no-sandbox" if electron else ""
    categories = meta.get("Categories", "Utility;")
    comment = meta.get("Comment", f"{display_name} AppImage application")
    terminal = meta.get("Terminal", "false")
    mime = meta.get("MimeType", "")

    lines = [
        "[Desktop Entry]",
        f"Name={display_name}",
        f"Comment={comment}",
        f"Exec={target}{exec_args} %U",
        f"Icon={icon_name}",
        "Type=Application",
        f"Categories={categories}",
        f"Terminal={terminal}",
        f"StartupWMClass={wmclass}",
    ]
    if mime:
        lines.append(f"MimeType={mime}")
    lines.append(f"Keywords=appimage;{app_id};")

    desktop_file.write_text("\n".join(lines) + "\n")
    desktop_file.chmod(0o644)
    log_ok(f"桌面文件: {desktop_file}")

    update_system_caches()
    log_ok("图标缓存已更新")
    log_ok("桌面数据库已更新")

    shortcut_file: Path | None = None
    if get_config("create_desktop_shortcut", True):
        log_info("创建桌面快捷方式...")
        desk_dir = xdg_desktop_dir()
        if desk_dir.exists() or safe_mkdir(desk_dir):
            shortcut_file = desk_dir / f"{wmclass}.desktop"
            shutil.copy2(desktop_file, shortcut_file)
            shortcut_file.chmod(0o755)
            subprocess.run(
                ["gio", "set", str(shortcut_file), "metadata::trusted", "true"],
                capture_output=True,
            )
            log_ok(f"桌面快捷方式: {shortcut_file}")
        else:
            log_warn(f"无法创建桌面目录: {desk_dir}")
    else:
        log_info("跳过桌面快捷方式（配置中已禁用）")

    add_installed(
        {
            "app_id": app_id,
            "base_name": base_name,
            "version": version,
            "display_name": display_name,
            "appimage_path": str(target),
            "desktop_file": str(desktop_file),
            "icon_name": icon_name,
            "wmclass": wmclass,
            "installed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    log_ok("已记录到安装列表")

    if extract_dir and extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)

    print(file=sys.stderr)
    print(f"{C.GREEN}========================================={C.NC}", file=sys.stderr)
    print(f"{C.GREEN}  {action_word}完成！{C.NC}", file=sys.stderr)
    print(f"{C.GREEN}========================================={C.NC}", file=sys.stderr)
    print(file=sys.stderr)
    print_kv("应用名称", display_name)
    print_kv("窗口类名", wmclass)
    print_kv("内部标识", app_id)
    if version:
        print_kv("版本", version)
    print_kv("安装位置", str(target))
    print_kv("桌面文件", str(desktop_file))
    print_kv("桌面快捷方式", str(shortcut_file) if shortcut_file else "未创建")
    print_kv("图标", icon_name)
    if electron:
        print_kv("Electron", "是 (--no-sandbox 已添加)")
    print(file=sys.stderr)
    print(f"  {C.CYAN}操作提示:{C.NC}", file=sys.stderr)
    print(f"  - dock 图标不显示 → {C.BOLD}注销重新登录{C.NC}", file=sys.stderr)
    print("  - 桌面快捷方式无法启动 → 右键 → Allow Launching", file=sys.stderr)
    print(f"  - 查看已安装应用: {C.BOLD}{sys.argv[0]} --list{C.NC}", file=sys.stderr)
    print(f"  - 查看当前配置:   {C.BOLD}{sys.argv[0]} --config{C.NC}", file=sys.stderr)
    print(f"  - 卸载此应用:     {C.BOLD}{sys.argv[0]} --remove {wmclass}{C.NC}", file=sys.stderr)
    print(file=sys.stderr)