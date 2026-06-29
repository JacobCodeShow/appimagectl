import configparser
import re
import shutil
import struct
import subprocess
import time
import zlib
from pathlib import Path

from appimagectl_core.i18n import tr
from appimagectl_core.shared import HOME, SESSION_TYPE, icon_base_dir, log_info, log_ok
from appimagectl_core.store import get_config


def parse_desktop_file(path: Path) -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return {}
    if "Desktop Entry" in parser:
        return dict(parser["Desktop Entry"])
    return {}


def find_internal_desktop(extract_dir: Path) -> Path | None:
    root = extract_dir / "squashfs-root"
    if not root.exists():
        return None

    def _ok(path: Path) -> bool:
        low = path.name.lower()
        return "uninstall" not in low and "uninst" not in low

    for path in root.rglob("share/applications/*.desktop"):
        if _ok(path):
            return path
    for path in root.rglob("*.desktop"):
        if _ok(path):
            return path
    return None


def is_electron_app(extract_dir: Path) -> bool:
    root = extract_dir / "squashfs-root"
    if not root.exists():
        return False
    if (root / "resources" / "electron.asar").exists():
        return True
    if (root / "resources" / "app.asar").exists():
        return True
    if (root / "chrome-sandbox").exists():
        return True
    return any(root.rglob("*.asar"))


def ensure_index_theme():
    dest = icon_base_dir() / "index.theme"
    if dest.exists():
        return
    system_theme = Path("/usr/share/icons/hicolor/index.theme")
    if system_theme.exists():
        shutil.copy(system_theme, dest)
        log_ok(tr("desktop.index_theme_copied"))
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            "[Icon Theme]\nName=hicolor\n"
            "Comment=Fallback icon theme\n"
            "Directories=256x256/apps,scalable/apps\n\n"
            "[256x256/apps]\nSize=256\nContext=Applications\nType=Fixed\n\n"
            "[scalable/apps]\nSize=48\nMinSize=8\nMaxSize=512\n"
            "Context=Applications\nType=Scalable\n"
        )
        log_ok(tr("desktop.index_theme_created"))


def _search_icon(root: Path, name: str) -> Path | None:
    exts = {".png", ".svg"}

    for path in root.rglob(f"icons/hicolor/scalable/apps/{name}*"):
        if path.suffix.lower() in exts:
            return path

    for size in (512, 256, 192, 128, 96, 64, 48, 32):
        for path in root.rglob(f"icons/hicolor/{size}x{size}/apps/{name}*"):
            if path.suffix.lower() in exts:
                return path

    for path in root.rglob(f"icons/hicolor/*/apps/{name}*"):
        if path.suffix.lower() in exts:
            return path

    for path in root.iterdir():
        if path.is_file() and path.name.startswith(name) and path.suffix.lower() in exts:
            return path

    return None


def find_best_icon(extract_dir: Path, *names: str) -> Path | None:
    root = extract_dir / "squashfs-root"
    if not root.exists():
        return None

    for name in names:
        if not name:
            continue
        result = _search_icon(root, name)
        if result:
            return result

    for path in root.rglob("icons/hicolor/*/apps/*.png"):
        return path
    for path in root.rglob("icons/hicolor/*/apps/*.svg"):
        return path
    for path in root.glob("*.png"):
        return path
    for path in root.glob("*.svg"):
        return path
    return None


def try_imagemagick_icon(icon_path: Path, letter: str) -> bool:
    for cmd_name in ("magick", "convert"):
        if not shutil.which(cmd_name):
            continue
        try:
            subprocess.run(
                [
                    cmd_name,
                    "-size",
                    "256x256",
                    "-define",
                    "gradient:direction=southeast",
                    "gradient:#2d3436-#636e72",
                    "-gravity",
                    "center",
                    "-fill",
                    "white",
                    "-pointsize",
                    "120",
                    "-annotate",
                    "+0+0",
                    letter,
                    str(icon_path),
                ],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return False


def generate_placeholder_icon(icon_path: Path):
    width, height = 256, 256
    color = (45, 52, 54)

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        return (
            struct.pack(">I", len(data))
            + chunk
            + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        )

    raw = b""
    for _ in range(height):
        raw += b"\x00" + bytes(color) * width

    icon_path.parent.mkdir(parents=True, exist_ok=True)
    icon_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def detect_wmclass_runtime(appimage_path: Path) -> str | None:
    if not get_config("auto_detect_wmclass", True):
        return None

    log_info(tr("desktop.detect_wmclass"))

    try:
        proc = subprocess.Popen(
            [str(appimage_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None

    time.sleep(5)
    if proc.poll() is not None:
        return None

    detected = None

    try:
        if SESSION_TYPE == "wayland":
            comm = Path(f"/proc/{proc.pid}/comm")
            if comm.exists():
                detected = comm.read_text().strip()

            if not detected and shutil.which("gdbus"):
                try:
                    result = subprocess.run(
                        [
                            "gdbus",
                            "call",
                            "--session",
                            "--dest",
                            "org.gnome.Shell",
                            "--object-path",
                            "/org/gnome/Shell",
                            "--method",
                            "org.gnome.Shell.Eval",
                            "global.get_window_actors()"
                            ".map(a => a.meta_window.get_wm_class()).join(',')",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        match = re.search(r"'([^']+)'", result.stdout)
                        if match:
                            classes = match.group(1).split(",")
                            if classes and classes[-1]:
                                detected = classes[-1]
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                    pass

        elif SESSION_TYPE == "x11":
            if shutil.which("xdotool"):
                try:
                    result = subprocess.run(
                        ["xdotool", "search", "--pid", str(proc.pid)],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        for wid in result.stdout.strip().split("\n"):
                            wid = wid.strip()
                            if not wid:
                                continue
                            xprop = subprocess.run(
                                ["xprop", "-id", wid, "WM_CLASS"],
                                capture_output=True,
                                text=True,
                                timeout=2,
                            )
                            if xprop.returncode == 0:
                                match = re.search(r'"([^"]+)"', xprop.stdout)
                                if match:
                                    detected = match.group(1)
                                    break
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                    pass

            if not detected and shutil.which("wmctrl"):
                try:
                    result = subprocess.run(
                        ["wmctrl", "-lx"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split("\n"):
                            if str(proc.pid) in line:
                                parts = line.split()
                                if len(parts) >= 3:
                                    detected = parts[2].split(".")[0]
                                    break
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                    pass
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    return detected