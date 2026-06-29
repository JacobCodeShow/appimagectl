import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from appimagectl_core.__about__ import __version__ as VERSION
from appimagectl_core.desktop import (
    ensure_index_theme,
    find_best_icon,
    find_internal_desktop,
    generate_placeholder_icon,
    parse_desktop_file,
    try_imagemagick_icon,
)
from appimagectl_core.i18n import tr
from appimagectl_core.install import extract_appimage, full_remove
from appimagectl_core.shared import (
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
from appimagectl_core.store import (
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
        log_info(tr("commands.list.empty"))
        log_info(tr("commands.list.install_first", script=f"{C.BOLD}{sys.argv[0]}{C.NC}"))
        return

    print(file=sys.stderr)
    print(f"{C.BOLD}{tr('commands.list.header')}{C.NC}", file=sys.stderr)
    print(f"  {C.DIM}{tr('commands.list.file')}: {INSTALLED_LIST}{C.NC}", file=sys.stderr)
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
            status = f"{C.RED}{tr('commands.list.status_missing_appimage')}{C.NC}"
            is_broken = True
        elif not os.access(appimage, os.X_OK):
            icon_s = f"{C.YELLOW}!{C.NC}"
            status = f"{C.YELLOW}{tr('commands.list.status_not_executable')}{C.NC}"
            is_broken = True
        elif not desktop.exists():
            icon_s = f"{C.YELLOW}!{C.NC}"
            status = f"{C.YELLOW}{tr('commands.list.status_missing_desktop')}{C.NC}"
            is_broken = True

        broken += 1 if is_broken else 0
        valid += 0 if is_broken else 1

        print(f"  {icon_s}  {C.BOLD}{app['display_name']}{C.NC}", file=sys.stderr)
        print(f"     {C.DIM}{tr('commands.list.id')}:{C.NC}   {app['app_id']}", file=sys.stderr)
        print(f"     {C.DIM}{tr('commands.list.wmclass')}:{C.NC} {app['wmclass']}", file=sys.stderr)
        version = app.get("version", "")
        if version:
            print(f"     {C.DIM}{tr('commands.list.version')}:{C.NC}   {version}", file=sys.stderr)
        print(f"     {C.DIM}{tr('commands.list.path')}:{C.NC}   {app['appimage_path']}", file=sys.stderr)
        print(f"     {C.DIM}{tr('commands.list.installed_at')}:{C.NC}   {app['installed_date']}", file=sys.stderr)
        if status:
            print(f"     {C.DIM}{tr('commands.list.status')}:{C.NC}   {status}", file=sys.stderr)
        print(file=sys.stderr)

    print(f"  {C.DIM}{'─' * 32}{C.NC}", file=sys.stderr)
    print(f"  {tr('commands.list.total', count=f'{C.BOLD}{len(apps)}{C.NC}')}", file=sys.stderr)
    if broken:
        print(
            f"  {tr('commands.list.summary_broken', ok_icon=f'{C.GREEN}●{C.NC}', valid=valid, bad_icon=f'{C.RED}✗{C.NC}', broken=broken)}",
            file=sys.stderr,
        )
        print(
            f"  {C.DIM}{tr('commands.list.verify_hint', script=sys.argv[0])}{C.NC}",
            file=sys.stderr,
        )
    else:
        print(f"  {tr('commands.list.summary_ok', ok_icon=f'{C.GREEN}●{C.NC}')}", file=sys.stderr)
    print(file=sys.stderr)


def cmd_remove(name: str, force: bool = False):
    init_config()

    app = (
        find_installed(app_id=f"appimage-{make_id(name)}")
        or find_installed(wmclass=make_id(name))
        or find_installed(name=name)
    )

    if not app:
        log_warn(tr("commands.remove.not_found", name=name))
        log_info(tr("commands.remove.list_hint", script=f"{C.BOLD}{sys.argv[0]}{C.NC}"))
        sys.exit(1)

    full_remove(app, delete_appimage=True, ask_delete=not force)
    log_ok(tr("commands.remove.done"))


def cmd_verify(force: bool = False):
    init_config()
    apps = load_installed()

    if not apps:
        log_info(tr("commands.verify.empty"))
        return

    log_info(tr("commands.verify.start"))
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
            issues.append(tr("commands.verify.issue_missing_appimage", path=appimage))
        elif not os.access(appimage, os.X_OK):
            issues.append(tr("commands.verify.issue_not_executable"))
        if not desktop.exists():
            issues.append(tr("commands.verify.issue_missing_desktop", path=desktop))

        icon_256 = ibd / "256x256" / "apps" / f"{icon_name}.png"
        icon_svg = ibd / "scalable" / "apps" / f"{icon_name}.svg"
        if not icon_256.exists() and not icon_svg.exists() and icon_name != "application-x-executable":
            issues.append(tr("commands.verify.issue_missing_icon"))

        if not issues:
            print(
                tr(
                    "commands.verify.ok_entry",
                    ok_icon=f"{C.GREEN}●{C.NC}",
                    name=f"{C.BOLD}{app['display_name']}{C.NC}",
                ),
                file=sys.stderr,
            )
            cleaned.append(app)
            ok_count += 1
        else:
            print(
                tr(
                    "commands.verify.bad_entry",
                    bad_icon=f"{C.RED}✗{C.NC}",
                    name=f"{C.BOLD}{app['display_name']}{C.NC}",
                ),
                file=sys.stderr,
            )
            for issue in issues:
                print(f"     {C.RED}→ {issue}{C.NC}", file=sys.stderr)

            do_remove = force
            if not do_remove:
                do_remove = ask(tr("commands.verify.remove_prompt")).lower() == "y"

            if do_remove:
                desktop.unlink(missing_ok=True)
                icon_256.unlink(missing_ok=True)
                icon_svg.unlink(missing_ok=True)
                (xdg_desktop_dir() / desktop.name).unlink(missing_ok=True)
                removed_count += 1
                print(f"  {C.YELLOW}{tr('commands.verify.removed')}{C.NC}", file=sys.stderr)
            else:
                cleaned.append(app)
                ok_count += 1

    save_installed(cleaned)
    update_system_caches()

    print(file=sys.stderr)
    print(f"  {C.DIM}{'─' * 32}{C.NC}", file=sys.stderr)
    print(
        f"  {tr('commands.verify.summary_prefix')} "
        f"{C.GREEN}{tr('commands.verify.summary_ok')} {ok_count}{C.NC}  "
        f"{C.RED}{tr('commands.verify.summary_removed')} {removed_count}{C.NC}",
        file=sys.stderr,
    )
    print(file=sys.stderr)


def cmd_config():
    init_config()
    cfg = load_config()
    ibd = icon_base_dir()
    dd = desktop_dir()

    print(file=sys.stderr)
    print(f"{C.BOLD}{tr('commands.config.header')}{C.NC}", file=sys.stderr)
    print(f"  {C.DIM}{tr('commands.config.file')}: {CONFIG_FILE}{C.NC}", file=sys.stderr)
    print(f"  {C.DIM}{tr('commands.config.script_version')}: {VERSION}{C.NC}", file=sys.stderr)
    print(file=sys.stderr)

    print(f"{C.BOLD}{tr('commands.config.user_header')}{C.NC}", file=sys.stderr)
    print(f"  {C.DIM}{tr('commands.config.edit_file')}: {CONFIG_FILE}{C.NC}", file=sys.stderr)
    print(file=sys.stderr)

    for key, desc in [
        ("install_dir", tr("commands.config.desc.install_dir")),
        ("default_icon_size", tr("commands.config.desc.default_icon_size")),
        ("auto_detect_wmclass", tr("commands.config.desc.auto_detect_wmclass")),
        ("create_desktop_shortcut", tr("commands.config.desc.create_desktop_shortcut")),
        ("ask_before_delete", tr("commands.config.desc.ask_before_delete")),
    ]:
        value = cfg.get("user", {}).get(key, tr("commands.config.not_set"))
        print(
            f"  {C.BOLD}{key:<28}{C.NC} {str(value):<24}"
            f" {C.DIM}# {desc}{C.NC}",
            file=sys.stderr,
        )

    print(file=sys.stderr)
    print(f"{C.BOLD}{tr('commands.config.system_header')}{C.NC}", file=sys.stderr)
    print(file=sys.stderr)

    for key, value, desc in [
        ("config_dir", str(CONFIG_DIR), tr("commands.config.desc.config_dir")),
        ("installed_list", str(INSTALLED_LIST), tr("commands.config.desc.installed_list")),
        ("icon_base_dir", str(ibd), tr("commands.config.desc.icon_base_dir")),
        ("desktop_dir", str(dd), tr("commands.config.desc.desktop_dir")),
        ("session_type", SESSION_TYPE, tr("commands.config.desc.session_type")),
        ("distro", DISTRO, tr("commands.config.desc.distro")),
    ]:
        print(
            f"  {C.BOLD}{key:<28}{C.NC} {value:<24}"
            f" {C.DIM}# {desc} {tr('commands.config.system_tag')}{C.NC}",
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

    log_info(tr("commands.scan.desktop_scan"))
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

    log_info(tr("commands.scan.desktop_scan_count", count=desktop_count))

    if scan_dirs:
        for scan_dir_str in scan_dirs:
            scan_dir = Path(scan_dir_str).expanduser().resolve()
            if not scan_dir.exists():
                log_warn(tr("commands.scan.dir_missing", path=scan_dir))
                continue

            log_info(tr("commands.scan.scanning_dir", path=scan_dir))
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

            log_info(tr("commands.scan.found_appimages", count=count))

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
        log_ok(tr("commands.scan.no_candidates"))
        return

    ibd = icon_base_dir()

    print(file=sys.stderr)
    print(f"{C.BOLD}{tr('commands.scan.header', count=len(candidates))}{C.NC}", file=sys.stderr)
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
                    issues.append(tr("commands.scan.issue_missing_icon"))
            if not meta.get("StartupWMClass"):
                issues.append(tr("commands.scan.issue_missing_wmclass"))
        else:
            issues.append(tr("commands.scan.issue_missing_desktop"))

        status = f"{C.GREEN}●{C.NC}" if not issues else f"{C.YELLOW}!{C.NC}"
        print(f"  {status}  {C.BOLD}{path.stem}{C.NC}", file=sys.stderr)
        print(f"     {C.DIM}{tr('commands.scan.path')}:{C.NC}     {path}", file=sys.stderr)
        if has_desktop:
            print(f"     {C.DIM}{tr('commands.scan.desktop_file')}:{C.NC} {desktop_file}", file=sys.stderr)
        else:
            print(f"     {C.DIM}{tr('commands.scan.desktop_file')}:{C.NC} {C.YELLOW}{tr('commands.scan.desktop_file_none')}{C.NC}", file=sys.stderr)
        source_label = tr("commands.scan.source_desktop") if candidate["source"] == "desktop" else tr("commands.scan.source_scan")
        print(f"     {C.DIM}{tr('commands.scan.source')}:{C.NC}     {source_label}", file=sys.stderr)

        if issues:
            for issue in issues:
                print(f"     {C.YELLOW}⚠ {issue}{C.NC}", file=sys.stderr)
        else:
            print(f"     {C.GREEN}{tr('commands.scan.config_ok')}{C.NC}", file=sys.stderr)
        print(file=sys.stderr)

    print(f"  {C.DIM}{'─' * 40}{C.NC}", file=sys.stderr)
    print(f"  {tr('commands.scan.import_hint', script=f'{C.BOLD}{sys.argv[0]}{C.NC}')}", file=sys.stderr)
    print(f"  {tr('commands.scan.import_fix_hint', script=f'{C.BOLD}{sys.argv[0]}{C.NC}')}", file=sys.stderr)
    print(f"  {tr('commands.scan.deep_hint', script=f'{C.BOLD}{sys.argv[0]}{C.NC}')}", file=sys.stderr)
    print(f"  {tr('commands.scan.dir_hint', script=f'{C.BOLD}{sys.argv[0]}{C.NC}')}", file=sys.stderr)
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
        log_ok(tr("commands.import.none"))
        return

    log_info(tr("commands.import.preparing", count=len(candidates)))
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
                log_info(tr("commands.import.fix_wmclass", name=name_clean))
                extract_dir = extract_appimage(path)
                if extract_dir:
                    internal_desktop = find_internal_desktop(extract_dir)
                    if internal_desktop:
                        internal_meta = parse_desktop_file(internal_desktop)
                        if internal_meta.get("StartupWMClass"):
                            wmclass = internal_meta["StartupWMClass"]
                            log_ok(tr("commands.import.got_wmclass", wmclass=wmclass))
                    shutil.rmtree(extract_dir, ignore_errors=True)

        display_name = meta.get("Name", "") or title_case(name_clean)
        icon_name = meta.get("Icon", "") or wmclass

        if not desktop_file or not Path(desktop_file).exists():
            if fix:
                log_info(tr("commands.import.fix_desktop", name=display_name))
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
                log_ok(tr("commands.import.created", path=desktop_file))
            else:
                log_warn(tr("commands.import.skip_no_desktop", name=display_name))
                continue

        icon_256 = ibd / "256x256" / "apps" / f"{icon_name}.png"
        icon_svg = ibd / "scalable" / "apps" / f"{icon_name}.svg"
        if not icon_256.exists() and not icon_svg.exists() and fix:
            log_info(tr("commands.import.fix_icon", name=display_name))
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
                    log_ok(tr("commands.import.icon_extracted", icon=found_icon.name))
                shutil.rmtree(extract_dir, ignore_errors=True)

            if not found:
                placeholder = ibd / "256x256" / "apps" / f"{icon_name}.png"
                letter = display_name[0].upper() if display_name else "A"
                if try_imagemagick_icon(placeholder, letter):
                    log_ok(tr("commands.import.placeholder_generated"))
                else:
                    try:
                        generate_placeholder_icon(placeholder)
                        log_ok(tr("commands.import.placeholder_generated"))
                    except Exception:
                        log_warn(tr("commands.import.placeholder_failed"))

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
        log_ok(tr("commands.import.imported", name=display_name, wmclass=wmclass))

    if imported > 0:
        update_system_caches()
        print(file=sys.stderr)
        log_ok(tr("commands.import.success", count=imported))
        log_info(tr("commands.import.list_hint", script=f"{C.BOLD}{sys.argv[0]}{C.NC}"))
    else:
        print(file=sys.stderr)
        log_info(tr("commands.import.none_done"))