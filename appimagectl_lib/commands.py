import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from appimagectl_lib.__about__ import __version__ as VERSION
from appimagectl_lib.desktop import (
    ensure_index_theme,
    find_best_icon,
    find_internal_desktop,
    generate_placeholder_icon,
    parse_desktop_file,
    try_imagemagick_icon,
)
from appimagectl_lib.install import extract_appimage, full_remove
from appimagectl_lib.shared import (
    C,
    CONFIG_DIR,
    CONFIG_FILE,
    DISTRO,
    HOME,
    INSTALLED_LIST,
    SESSION_TYPE,
    ask,
    desktop_dir,
    extract_version,
    icon_base_dir,
    log_info,
    log_ok,
    log_warn,
    make_id,
    strip_version,
    title_case,
    update_system_caches,
    xdg_desktop_dir,
)
from appimagectl_lib.store import (
    add_installed,
    find_installed,
    init_config,
    load_config,
    load_installed,
    save_installed,
)


def cmd_list():
    init_config()
    apps = load_installed()

    if not apps:
        log_info("还没有安装任何 AppImage")
        log_info(f"使用 {C.BOLD}{sys.argv[0]} --install <file>{C.NC} 安装第一个应用")
        return

    print(file=sys.stderr)
    print(f"{C.BOLD}  已安装的 AppImage{C.NC}", file=sys.stderr)
    print(f"  {C.DIM}列表文件: {INSTALLED_LIST}{C.NC}", file=sys.stderr)
    print(file=sys.stderr)

    valid = broken = 0

    for app in apps:
        appimage = Path(app["appimage_path"])
        desktop = Path(app["desktop_file"])

        icon_s = f"{C.GREEN}●{C.NC}"
        status = ""
        is_broken = False

        if not appimage.exists():
            icon_s = f"{C.RED}✗{C.NC}"
            status = f"{C.RED}AppImage 文件丢失{C.NC}"
            is_broken = True
        elif not os.access(appimage, os.X_OK):
            icon_s = f"{C.YELLOW}!{C.NC}"
            status = f"{C.YELLOW}文件不可执行{C.NC}"
            is_broken = True
        elif not desktop.exists():
            icon_s = f"{C.YELLOW}!{C.NC}"
            status = f"{C.YELLOW}桌面文件丢失{C.NC}"
            is_broken = True

        broken += 1 if is_broken else 0
        valid += 0 if is_broken else 1

        print(f"  {icon_s}  {C.BOLD}{app['display_name']}{C.NC}", file=sys.stderr)
        print(f"     {C.DIM}标识:{C.NC}   {app['app_id']}", file=sys.stderr)
        print(f"     {C.DIM}WMClass:{C.NC} {app['wmclass']}", file=sys.stderr)
        version = app.get("version", "")
        if version:
            print(f"     {C.DIM}版本:{C.NC}   {version}", file=sys.stderr)
        print(f"     {C.DIM}路径:{C.NC}   {app['appimage_path']}", file=sys.stderr)
        print(f"     {C.DIM}安装:{C.NC}   {app['installed_date']}", file=sys.stderr)
        if status:
            print(f"     {C.DIM}状态:{C.NC}   {status}", file=sys.stderr)
        print(file=sys.stderr)

    print(f"  {C.DIM}{'─' * 32}{C.NC}", file=sys.stderr)
    print(f"  共 {C.BOLD}{len(apps)}{C.NC} 个应用", file=sys.stderr)
    if broken:
        print(f"  {C.GREEN}●{C.NC} 正常 {valid}  {C.RED}✗{C.NC} 异常 {broken}", file=sys.stderr)
        print(f"  {C.DIM}使用 {sys.argv[0]} --verify 检查并清理异常项{C.NC}", file=sys.stderr)
    else:
        print(f"  {C.GREEN}● 全部正常{C.NC}", file=sys.stderr)
    print(file=sys.stderr)


def cmd_remove(name: str, force: bool = False):
    init_config()

    app = (
        find_installed(app_id=f"appimage-{make_id(name)}")
        or find_installed(wmclass=make_id(name))
        or find_installed(name=name)
    )

    if not app:
        log_warn(f"未在安装列表中找到匹配 '{name}' 的应用")
        log_info(f"使用 {C.BOLD}{sys.argv[0]} --list{C.NC} 查看已安装应用")
        sys.exit(1)

    full_remove(app, delete_appimage=True, ask_delete=not force)
    log_ok("移除完成")


def cmd_verify(force: bool = False):
    init_config()
    apps = load_installed()

    if not apps:
        log_info("列表为空，无需验证")
        return

    log_info("正在验证已安装应用...")
    print(file=sys.stderr)

    ibd = icon_base_dir()
    cleaned: list[dict] = []
    ok_count = removed_count = 0

    for app in apps:
        issues: list[str] = []
        appimage = Path(app["appimage_path"])
        desktop = Path(app["desktop_file"])
        icon_name = app["icon_name"]

        if not appimage.exists():
            issues.append(f"AppImage 文件不存在: {appimage}")
        elif not os.access(appimage, os.X_OK):
            issues.append("AppImage 文件不可执行")
        if not desktop.exists():
            issues.append(f"桌面文件不存在: {desktop}")

        icon_256 = ibd / "256x256" / "apps" / f"{icon_name}.png"
        icon_svg = ibd / "scalable" / "apps" / f"{icon_name}.svg"
        if not icon_256.exists() and not icon_svg.exists() and icon_name != "application-x-executable":
            issues.append("图标文件丢失")

        if not issues:
            print(
                f"  {C.GREEN}●{C.NC}  {C.BOLD}{app['display_name']}{C.NC}"
                f"  {C.GREEN}正常{C.NC}",
                file=sys.stderr,
            )
            cleaned.append(app)
            ok_count += 1
        else:
            print(
                f"  {C.RED}✗{C.NC}  {C.BOLD}{app['display_name']}{C.NC}",
                file=sys.stderr,
            )
            for issue in issues:
                print(f"     {C.RED}→ {issue}{C.NC}", file=sys.stderr)

            do_remove = force
            if not do_remove:
                do_remove = ask("  是否移除此记录？[y/N]").lower() == "y"

            if do_remove:
                desktop.unlink(missing_ok=True)
                icon_256.unlink(missing_ok=True)
                icon_svg.unlink(missing_ok=True)
                (xdg_desktop_dir() / desktop.name).unlink(missing_ok=True)
                removed_count += 1
                print(f"  {C.YELLOW}已移除{C.NC}", file=sys.stderr)
            else:
                cleaned.append(app)
                ok_count += 1

    save_installed(cleaned)
    update_system_caches()

    print(file=sys.stderr)
    print(f"  {C.DIM}{'─' * 32}{C.NC}", file=sys.stderr)
    print(
        f"  验证完成: {C.GREEN}正常 {ok_count}{C.NC}"
        f"  {C.RED}已清理 {removed_count}{C.NC}",
        file=sys.stderr,
    )
    print(file=sys.stderr)


def cmd_config():
    init_config()
    cfg = load_config()
    ibd = icon_base_dir()
    dd = desktop_dir()

    print(file=sys.stderr)
    print(f"{C.BOLD}  当前配置{C.NC}", file=sys.stderr)
    print(f"  {C.DIM}配置文件: {CONFIG_FILE}{C.NC}", file=sys.stderr)
    print(f"  {C.DIM}脚本版本: {VERSION}{C.NC}", file=sys.stderr)
    print(file=sys.stderr)

    print(f"  {C.BOLD}── 用户配置（可修改）──{C.NC}", file=sys.stderr)
    print(f"  {C.DIM}编辑文件: {CONFIG_FILE}{C.NC}", file=sys.stderr)
    print(file=sys.stderr)

    for key, desc in [
        ("install_dir", "AppImage 安装目录"),
        ("default_icon_size", "首选图标尺寸"),
        ("auto_detect_wmclass", "自动检测窗口类名"),
        ("create_desktop_shortcut", "创建桌面快捷方式"),
        ("ask_before_delete", "删除前确认提示"),
    ]:
        value = cfg.get("user", {}).get(key, "未设置")
        print(
            f"  {C.BOLD}{key:<28}{C.NC} {str(value):<24}"
            f" {C.DIM}# {desc}{C.NC}",
            file=sys.stderr,
        )

    print(file=sys.stderr)
    print(f"  {C.BOLD}── 系统配置（自动检测，不可修改）──{C.NC}", file=sys.stderr)
    print(file=sys.stderr)

    for key, value, desc in [
        ("config_dir", str(CONFIG_DIR), "配置目录"),
        ("installed_list", str(INSTALLED_LIST), "已安装列表"),
        ("icon_base_dir", str(ibd), "图标目录"),
        ("desktop_dir", str(dd), "桌面文件目录"),
        ("session_type", SESSION_TYPE, "会话类型"),
        ("distro", DISTRO, "发行版"),
    ]:
        print(
            f"  {C.BOLD}{key:<28}{C.NC} {value:<24}"
            f" {C.DIM}# {desc} [系统]{C.NC}",
            file=sys.stderr,
        )
    print(file=sys.stderr)


def _is_appimage_file(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            header = handle.read(40)
            if header[:4] == b"\x7fELF" and len(header) >= 11:
                if header[8:11] == b"\x41\x49\x02":
                    return True
            if header[:4] == b"\x7fELF":
                handle.seek(0)
                head = handle.read(1024)
                if b"AppImage" in head:
                    return True
    except (OSError, PermissionError):
        pass
    return False


def _collect_unmanaged_candidates(
    scan_dirs: list[str] | None = None,
    deep: bool = False,
) -> list[dict]:
    registered_paths = {app["appimage_path"] for app in load_installed()}
    applications_dir = desktop_dir()
    candidates: list[dict] = []

    log_info("扫描 .desktop 文件...")
    desktop_count = 0

    for desktop_file in applications_dir.glob("*.desktop"):
        if desktop_file.name == ".directory":
            continue

        meta = parse_desktop_file(desktop_file)
        exec_line = meta.get("Exec", "")
        if not exec_line:
            continue

        exec_path = ""
        for part in exec_line.split():
            if part.startswith("-") or "%" in part:
                continue
            expanded = Path(part.replace("~", str(HOME)))
            if expanded.exists():
                exec_path = str(expanded.resolve())
                break

        if not exec_path:
            continue

        is_appimage = exec_path.lower().endswith(".appimage")
        if not is_appimage and deep:
            is_appimage = _is_appimage_file(Path(exec_path))
        if not is_appimage:
            continue

        desktop_count += 1

        if exec_path in registered_paths:
            continue
        if any(candidate["appimage_path"] == exec_path for candidate in candidates):
            continue

        candidates.append(
            {
                "appimage_path": exec_path,
                "desktop_file": str(desktop_file),
                "desktop_meta": meta,
                "source": "desktop",
            }
        )

    log_info(f"  扫描了 {desktop_count} 个指向 AppImage 的 .desktop 文件")

    if scan_dirs:
        for scan_dir_str in scan_dirs:
            scan_dir = Path(scan_dir_str).expanduser().resolve()
            if not scan_dir.exists():
                log_warn(f"目录不存在: {scan_dir}")
                continue

            log_info(f"扫描目录: {scan_dir}")
            count = 0

            for found in scan_dir.rglob("*"):
                if not found.is_file():
                    continue
                if not os.access(found, os.X_OK):
                    continue

                is_appimage = found.name.lower().endswith(".appimage")
                if not is_appimage and deep:
                    is_appimage = _is_appimage_file(found)
                if not is_appimage:
                    continue

                count += 1
                path_str = str(found.resolve())

                if path_str in registered_paths:
                    continue
                if any(candidate["appimage_path"] == path_str for candidate in candidates):
                    continue

                candidates.append(
                    {
                        "appimage_path": path_str,
                        "desktop_file": "",
                        "desktop_meta": {},
                        "source": "scan",
                    }
                )

            log_info(f"  找到 {count} 个 AppImage 文件")

    seen: set[str] = set()
    unique: list[dict] = []
    for candidate in candidates:
        if candidate["appimage_path"] not in seen:
            seen.add(candidate["appimage_path"])
            unique.append(candidate)

    return unique


def cmd_scan(
    scan_dirs: list[str] | None = None,
    deep: bool = False,
):
    init_config()
    candidates = _collect_unmanaged_candidates(scan_dirs=scan_dirs, deep=deep)

    if not candidates:
        log_ok("所有 AppImage 均已管理，未发现遗漏")
        return

    ibd = icon_base_dir()

    print(file=sys.stderr)
    print(f"{C.BOLD}  发现 {len(candidates)} 个未管理的 AppImage{C.NC}", file=sys.stderr)
    print(file=sys.stderr)

    for candidate in candidates:
        path = Path(candidate["appimage_path"])
        desktop_file = candidate.get("desktop_file", "")
        meta = candidate.get("desktop_meta", {})

        issues: list[str] = []
        has_desktop = bool(desktop_file) and Path(desktop_file).exists()

        if has_desktop:
            icon_name = meta.get("Icon", "")
            if icon_name:
                icon_256 = ibd / "256x256" / "apps" / f"{icon_name}.png"
                icon_svg = ibd / "scalable" / "apps" / f"{icon_name}.svg"
                if not icon_256.exists() and not icon_svg.exists():
                    issues.append("图标文件缺失")
            if not meta.get("StartupWMClass"):
                issues.append("缺少 StartupWMClass（dock 图标可能异常）")
        else:
            issues.append("无 .desktop 文件")

        status = f"{C.GREEN}●{C.NC}" if not issues else f"{C.YELLOW}!{C.NC}"
        print(f"  {status}  {C.BOLD}{path.stem}{C.NC}", file=sys.stderr)
        print(f"     {C.DIM}路径:{C.NC}     {path}", file=sys.stderr)
        if has_desktop:
            print(f"     {C.DIM}桌面文件:{C.NC} {desktop_file}", file=sys.stderr)
        else:
            print(f"     {C.DIM}桌面文件:{C.NC} {C.YELLOW}无{C.NC}", file=sys.stderr)
        source_label = "桌面文件反查" if candidate["source"] == "desktop" else "目录扫描"
        print(f"     {C.DIM}来源:{C.NC}     {source_label}", file=sys.stderr)

        if issues:
            for issue in issues:
                print(f"     {C.YELLOW}⚠ {issue}{C.NC}", file=sys.stderr)
        else:
            print(f"     {C.GREEN}配置正常，但未被本工具管理{C.NC}", file=sys.stderr)
        print(file=sys.stderr)

    print(f"  {C.DIM}{'─' * 40}{C.NC}", file=sys.stderr)
    print(f"  使用 {C.BOLD}{sys.argv[0]} --import{C.NC}  将以上应用导入管理", file=sys.stderr)
    print(f"  使用 {C.BOLD}{sys.argv[0]} --import --fix{C.NC}  导入并自动修复问题", file=sys.stderr)
    print(f"  使用 {C.BOLD}{sys.argv[0]} --scan --deep{C.NC}  深度扫描（含无后缀文件）", file=sys.stderr)
    print(f"  使用 {C.BOLD}{sys.argv[0]} --scan --scan-dir ~/Downloads{C.NC}  指定扫描目录", file=sys.stderr)
    print(file=sys.stderr)


def cmd_import(
    scan_dirs: list[str] | None = None,
    deep: bool = False,
    fix: bool = False,
    force: bool = False,
):
    del force
    init_config()
    ibd = icon_base_dir()
    applications_dir = desktop_dir()

    candidates = _collect_unmanaged_candidates(scan_dirs=scan_dirs, deep=deep)

    if not candidates:
        log_ok("没有需要导入的 AppImage")
        return

    log_info(f"准备导入 {len(candidates)} 个 AppImage...")
    print(file=sys.stderr)

    imported = 0

    for candidate in candidates:
        path = Path(candidate["appimage_path"])
        name_clean = path.stem
        if name_clean.lower().endswith(".appimage"):
            name_clean = name_clean[: -len(".appimage")]

        base_name = strip_version(name_clean)
        version = extract_version(name_clean)
        app_id = f"appimage-{make_id(name_clean)}"
        desktop_file = candidate.get("desktop_file", "")
        meta = candidate.get("desktop_meta", {})

        wmclass = meta.get("StartupWMClass", "")
        if not wmclass:
            wmclass = make_id(name_clean)
            if fix:
                log_info(f"  修复: 为 {name_clean} 解压获取 StartupWMClass...")
                extract_dir = extract_appimage(path)
                if extract_dir:
                    internal_desktop = find_internal_desktop(extract_dir)
                    if internal_desktop:
                        internal_meta = parse_desktop_file(internal_desktop)
                        if internal_meta.get("StartupWMClass"):
                            wmclass = internal_meta["StartupWMClass"]
                            log_ok(f"  获取到: {wmclass}")
                    shutil.rmtree(extract_dir, ignore_errors=True)

        display_name = meta.get("Name", "") or title_case(name_clean)
        icon_name = meta.get("Icon", "") or wmclass

        if not desktop_file or not Path(desktop_file).exists():
            if fix:
                log_info(f"  修复: 为 {display_name} 创建 .desktop 文件...")
                desktop_file_path = applications_dir / f"{wmclass}.desktop"
                applications_dir.mkdir(parents=True, exist_ok=True)

                categories = meta.get("Categories", "Utility;")
                comment = meta.get("Comment", f"{display_name} AppImage")
                terminal = meta.get("Terminal", "false")

                if not meta.get("Categories"):
                    extract_dir = extract_appimage(path)
                    if extract_dir:
                        internal_desktop = find_internal_desktop(extract_dir)
                        if internal_desktop:
                            internal_meta = parse_desktop_file(internal_desktop)
                            categories = internal_meta.get("Categories", categories)
                            comment = internal_meta.get("Comment", comment)
                            terminal = internal_meta.get("Terminal", terminal)
                        shutil.rmtree(extract_dir, ignore_errors=True)

                desktop_file_path.write_text(
                    "\n".join(
                        [
                            "[Desktop Entry]",
                            f"Name={display_name}",
                            f"Comment={comment}",
                            f"Exec={path} %U",
                            f"Icon={icon_name}",
                            "Type=Application",
                            f"Categories={categories}",
                            f"Terminal={terminal}",
                            f"StartupWMClass={wmclass}",
                            f"Keywords=appimage;{app_id};",
                        ]
                    )
                    + "\n"
                )
                desktop_file_path.chmod(0o644)
                desktop_file = str(desktop_file_path)
                log_ok(f"  已创建: {desktop_file}")
            else:
                log_warn(f"  {display_name}: 无 .desktop 文件，跳过（使用 --fix 自动创建）")
                continue

        icon_256 = ibd / "256x256" / "apps" / f"{icon_name}.png"
        icon_svg = ibd / "scalable" / "apps" / f"{icon_name}.svg"
        if not icon_256.exists() and not icon_svg.exists() and fix:
            log_info(f"  修复: 为 {display_name} 提取/生成图标...")
            ensure_index_theme()
            found = False
            extract_dir = extract_appimage(path)
            if extract_dir:
                search_names = [icon_name, wmclass, strip_version(name_clean)]
                found_icon = find_best_icon(extract_dir, *search_names)
                if found_icon and found_icon.exists():
                    if found_icon.suffix.lower() == ".svg":
                        dest = ibd / "scalable" / "apps" / f"{icon_name}.svg"
                    else:
                        dest = ibd / "256x256" / "apps" / f"{icon_name}.png"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(found_icon, dest)
                    found = True
                    log_ok(f"  已提取图标: {found_icon.name}")
                shutil.rmtree(extract_dir, ignore_errors=True)

            if not found:
                placeholder = ibd / "256x256" / "apps" / f"{icon_name}.png"
                letter = display_name[0].upper() if display_name else "A"
                if try_imagemagick_icon(placeholder, letter):
                    log_ok("  已生成占位图标")
                else:
                    try:
                        generate_placeholder_icon(placeholder)
                        log_ok("  已生成占位图标")
                    except Exception:
                        log_warn("  占位图标生成失败")

        add_installed(
            {
                "app_id": app_id,
                "base_name": base_name,
                "version": version,
                "display_name": display_name,
                "appimage_path": str(path),
                "desktop_file": desktop_file,
                "icon_name": icon_name,
                "wmclass": wmclass,
                "installed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        imported += 1
        log_ok(f"已导入: {display_name} ({wmclass})")

    if imported > 0:
        update_system_caches()
        print(file=sys.stderr)
        log_ok(f"成功导入 {imported} 个 AppImage")
        log_info(f"使用 {C.BOLD}{sys.argv[0]} --list{C.NC} 查看完整列表")
    else:
        print(file=sys.stderr)
        log_info("没有成功导入任何应用")