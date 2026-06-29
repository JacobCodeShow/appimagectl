import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from appimagectl_core.__about__ import __version__ as VERSION
from appimagectl_core.desktop import (
    detect_wmclass_runtime,
    ensure_index_theme,
    find_best_icon,
    find_internal_desktop,
    generate_placeholder_icon,
    is_electron_app,
    parse_desktop_file,
    try_imagemagick_icon,
)
from appimagectl_core.i18n import tr
from appimagectl_core.shared import (
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
from appimagectl_core.store import (
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

    log_info(tr("install.removing", name=app["display_name"], wmclass=app.get("wmclass", "?")))

    desktop_path = Path(app["desktop_file"])
    if desktop_path.exists():
        desktop_path.unlink()
        log_ok(tr("install.desktop_deleted"))

    (ibd / "256x256" / "apps" / f"{app['icon_name']}.png").unlink(missing_ok=True)
    (ibd / "scalable" / "apps" / f"{app['icon_name']}.svg").unlink(missing_ok=True)

    shortcut = xdg_desktop_dir() / desktop_path.name
    if shortcut.exists():
        shortcut.unlink()
        log_ok(tr("install.shortcut_deleted"))

    appimage = Path(app["appimage_path"])
    if delete_appimage and appimage.exists():
        should_delete = True
        if ask_delete and get_config("ask_before_delete", True):
            print(f"  {C.YELLOW}{tr('install.ask_delete_title')}{C.NC}", file=sys.stderr)
            print(f"  {C.DIM}{appimage}{C.NC}", file=sys.stderr)
            should_delete = ask("  [y/N]").lower() == "y"
        if should_delete:
            appimage.unlink()
            log_ok(tr("install.appimage_deleted", path=appimage))
        else:
            log_info(tr("install.keep_appimage"))

    remove_installed(app["app_id"])

    update_system_caches()
    log_ok(tr("install.removed", name=app["display_name"]))


def cmd_install(
    appimage_str: str,
    custom_name: str | None = None,
    reinstall: bool = False,
    force: bool = False,
):
    appimage_path = Path(appimage_str).resolve()

    if not appimage_path.exists():
        log_error(tr("install.file_missing", path=appimage_path))
        sys.exit(1)

    if not appimage_path.name.lower().endswith(".appimage"):
        if not force:
            response = ask(f"{C.YELLOW}{tr('install.extension_prompt')}{C.NC}")
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
            log_info(tr("install.remove_existing_reinstall", name=existing["display_name"]))
            full_remove(existing, delete_appimage=True, ask_delete=False)

        elif version and existing_version:
            comparison = compare_versions(version, existing_version)
            if comparison > 0:
                log_info(tr("install.upgrade_detected", old=existing_version, new=version))
                log_info(tr("install.remove_old_version", name=existing["display_name"]))
                full_remove(existing, delete_appimage=True, ask_delete=False)
            elif comparison == 0:
                if force:
                    full_remove(existing, delete_appimage=True, ask_delete=False)
                else:
                    log_warn(tr("install.same_version_installed", version=version))
                    log_info(tr("install.reinstall_hint"))
                    log_info(tr("install.reinstall_hint_cmd", script=sys.argv[0], path=appimage_path))
                    log_info(tr("install.reinstall_force_hint_cmd", script=sys.argv[0], path=appimage_path))
                    sys.exit(0)
            else:
                if force:
                    log_warn(tr("install.downgrade", old=existing_version, new=version))
                    full_remove(existing, delete_appimage=True, ask_delete=False)
                else:
                    log_warn(tr("install.older_version_installed", old=existing_version, new=version))
                    log_info(tr("install.downgrade_hint"))
                    sys.exit(1)
        else:
            if force or reinstall:
                log_info(tr("install.remove_existing", name=existing["display_name"]))
                full_remove(existing, delete_appimage=True, ask_delete=not force)
            else:
                log_warn(tr("install.already_installed", name=existing["display_name"]))
                log_info(tr("install.reinstall_or_force_hint"))
                sys.exit(0)

    action_word = tr("install.action_reinstall") if reinstall else tr("install.action_install")
    log_info("=" * 41)
    log_info(tr("install.banner_title", version=VERSION))
    log_info(tr("install.banner_system", distro=DISTRO, session=SESSION_TYPE))
    log_info(tr("install.banner_dir", path=install_dir))
    log_info("=" * 41)
    print(file=sys.stderr)

    log_info(tr("install.step1"))
    install_dir.mkdir(parents=True, exist_ok=True)
    target = install_dir / appimage_path.name

    if appimage_path != target:
        shutil.copy2(appimage_path, target)
        log_ok(tr("install.copied", path=target))
    else:
        log_ok(tr("install.file_already_target"))
    target.chmod(target.stat().st_mode | 0o111)

    log_info(tr("install.step2"))
    extract_dir = extract_appimage(target)
    if extract_dir:
        log_ok(tr("install.parse_ok"))
    else:
        log_warn(tr("install.parse_failed"))

    log_info(tr("install.step3"))
    meta: dict[str, str] = {}
    electron = False

    if extract_dir:
        electron = is_electron_app(extract_dir)
        if electron:
            log_ok(tr("install.electron_detected"))

        internal_desktop = find_internal_desktop(extract_dir)
        if internal_desktop:
            meta = parse_desktop_file(internal_desktop)
            log_ok(tr("install.metadata_loaded", name=internal_desktop.name))
            for key in ("Name", "StartupWMClass", "Icon", "Categories"):
                if meta.get(key):
                    log_info(tr("install.metadata_line", key=key, value=meta[key]))
        else:
            log_warn(tr("install.desktop_not_found"))

    log_info(tr("install.step4"))
    wmclass_fallback = make_id(name_clean)
    wmclass = ""
    wmclass_source = ""

    if meta.get("StartupWMClass"):
        wmclass = meta["StartupWMClass"]
        wmclass_source = tr("install.wmclass_source_desktop")
    else:
        detected = detect_wmclass_runtime(target)
        if detected:
            wmclass = detected
            wmclass_source = tr("install.wmclass_source_runtime")
        else:
            wmclass = wmclass_fallback
            wmclass_source = tr("install.wmclass_source_filename")

    if wmclass_source == tr("install.wmclass_source_filename"):
        log_warn(tr("install.wmclass_fallback", wmclass=wmclass))
    else:
        log_ok(tr("install.wmclass_detected", source=wmclass_source, wmclass=wmclass))

    match True:
        case _ if custom_name:
            display_name = custom_name
        case _ if meta.get("Name"):
            display_name = meta["Name"]
        case _ if wmclass_source != tr("install.wmclass_source_filename"):
            display_name = title_case(wmclass)
        case _:
            display_name = name_clean.replace("-", " ").replace("_", " ")

    log_info(tr("install.step5"))
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
            log_ok(tr("install.icon_extracted", icon=found_icon.name))

    if not icon_found:
        log_warn(tr("install.icon_missing_generate"))
        placeholder = ibd / "256x256" / "apps" / f"{icon_name}.png"
        letter = display_name[0].upper() if display_name else "A"
        if try_imagemagick_icon(placeholder, letter):
            log_ok(tr("install.placeholder_generated_im"))
            icon_found = True
        else:
            try:
                generate_placeholder_icon(placeholder)
                log_ok(tr("install.placeholder_generated"))
                icon_found = True
            except Exception:
                log_warn(tr("install.placeholder_failed"))
                icon_name = "application-x-executable"

    log_info(tr("install.step6"))
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
    log_ok(tr("install.desktop_created", path=desktop_file))

    update_system_caches()
    log_ok(tr("install.icon_cache_updated"))
    log_ok(tr("install.desktop_db_updated"))

    shortcut_file: Path | None = None
    if get_config("create_desktop_shortcut", True):
        log_info(tr("install.create_shortcut"))
        desk_dir = xdg_desktop_dir()
        if desk_dir.exists() or safe_mkdir(desk_dir):
            shortcut_file = desk_dir / f"{wmclass}.desktop"
            shutil.copy2(desktop_file, shortcut_file)
            shortcut_file.chmod(0o755)
            subprocess.run(
                ["gio", "set", str(shortcut_file), "metadata::trusted", "true"],
                capture_output=True,
            )
            log_ok(tr("install.shortcut_created", path=shortcut_file))
        else:
            log_warn(tr("install.desktop_dir_failed", path=desk_dir))
    else:
        log_info(tr("install.shortcut_disabled"))

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
    log_ok(tr("install.recorded"))

    if extract_dir and extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)

    print(file=sys.stderr)
    print(f"{C.GREEN}========================================={C.NC}", file=sys.stderr)
    print(f"{C.GREEN}  {tr('install.completed', action=action_word)}{C.NC}", file=sys.stderr)
    print(f"{C.GREEN}========================================={C.NC}", file=sys.stderr)
    print(file=sys.stderr)
    print_kv(tr("install.kv.app_name"), display_name)
    print_kv(tr("install.kv.wmclass"), wmclass)
    print_kv(tr("install.kv.internal_id"), app_id)
    if version:
        print_kv(tr("install.kv.version"), version)
    print_kv(tr("install.kv.install_location"), str(target))
    print_kv(tr("install.kv.desktop_file"), str(desktop_file))
    print_kv(tr("install.kv.desktop_shortcut"), str(shortcut_file) if shortcut_file else tr("install.kv.not_created"))
    print_kv(tr("install.kv.icon"), icon_name)
    if electron:
        print_kv(tr("install.kv.electron"), tr("install.kv.electron_enabled"))
    print(file=sys.stderr)
    print(f"  {C.CYAN}{tr('install.tips_title')}{C.NC}", file=sys.stderr)
    print(f"  {tr('install.tips.dock')}", file=sys.stderr)
    print(f"  {tr('install.tips.shortcut')}", file=sys.stderr)
    print(f"  {tr('install.tips.list', script=f'{C.BOLD}{sys.argv[0]}{C.NC}')}", file=sys.stderr)
    print(f"  {tr('install.tips.config', script=f'{C.BOLD}{sys.argv[0]}{C.NC}')}", file=sys.stderr)
    print(f"  {tr('install.tips.remove', script=f'{C.BOLD}{sys.argv[0]}{C.NC}', name=wmclass)}", file=sys.stderr)
    print(file=sys.stderr)