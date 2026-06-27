import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


HOME = Path.home()
CONFIG_DIR = HOME / ".config" / "appimage-installer"
CONFIG_FILE = CONFIG_DIR / "config.json"
INSTALLED_LIST = CONFIG_DIR / "installed.json"

SCRIPT_NAME = Path(sys.argv[0]).name

DEFAULTS: dict = {
    "install_dir": "~/.AppImage",
    "default_icon_size": 256,
    "auto_detect_wmclass": True,
    "create_desktop_shortcut": True,
    "ask_before_delete": True,
}


class C:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    NC = "\033[0m"


def log_info(msg: str):
    print(f"{C.CYAN}[INFO]{C.NC} {msg}", file=sys.stderr)


def log_ok(msg: str):
    print(f"{C.GREEN}[OK]{C.NC}   {msg}", file=sys.stderr)


def log_warn(msg: str):
    print(f"{C.YELLOW}[WARN]{C.NC} {msg}", file=sys.stderr)


def log_error(msg: str):
    print(f"{C.RED}[ERROR]{C.NC} {msg}", file=sys.stderr)


def ask(prompt: str, default: str = "n") -> str:
    try:
        return input(f"{prompt} ").strip() or default
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return default


def print_kv(key: str, value: str):
    print(f"  {C.BOLD}{key}:{C.NC}  {value}", file=sys.stderr)


def detect_distro() -> str:
    if Path("/etc/fedora-release").exists():
        return "fedora"
    if Path("/etc/debian_version").exists() or shutil.which("apt"):
        return "ubuntu"
    return "unknown"


def detect_session() -> str:
    if os.environ.get("XDG_SESSION_TYPE"):
        return os.environ["XDG_SESSION_TYPE"]
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


DISTRO = detect_distro()
SESSION_TYPE = detect_session()


def icon_base_dir() -> Path:
    return HOME / ".local" / "share" / "icons" / "hicolor"


def desktop_dir() -> Path:
    return HOME / ".local" / "share" / "applications"


def xdg_desktop_dir() -> Path:
    try:
        result = subprocess.run(
            ["xdg-user-dir", "DESKTOP"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.stdout.strip():
            return Path(result.stdout.strip())
    except Exception:
        pass
    return HOME / "Desktop"


def make_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def title_case(name: str) -> str:
    return " ".join(w.capitalize() for w in re.split(r"[-_]", name) if w)


def strip_version(name: str) -> str:
    return re.sub(r"[-_]?v?\d+(?:[._-]\d+)*$", "", name).rstrip("-_") or name


def extract_version(name: str) -> str:
    match = re.search(r"[-_]?v?(\d+(?:\.\d+)+)", name)
    if match:
        return match.group(1)
    match = re.search(r"[-_]?v?(\d+)$", name)
    if match:
        return match.group(1)
    return ""


def compare_versions(v1: str, v2: str) -> int:
    def normalize(version: str) -> list[int]:
        return [int(part) for part in re.split(r"[._-]", version) if part.isdigit()]

    p1, p2 = normalize(v1), normalize(v2)
    length = max(len(p1), len(p2))
    p1.extend([0] * (length - len(p1)))
    p2.extend([0] * (length - len(p2)))
    for left, right in zip(p1, p2):
        if left != right:
            return left - right
    return 0


def safe_mkdir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def update_system_caches():
    subprocess.run(
        ["gtk-update-icon-cache", "-f", str(icon_base_dir())],
        capture_output=True,
    )
    subprocess.run(
        ["update-desktop-database", str(desktop_dir())],
        capture_output=True,
    )


def check_dependencies():
    log_info("检查依赖...")
    missing: list[str] = []

    if not shutil.which("gtk-update-icon-cache"):
        missing.append("gtk3" if DISTRO == "fedora" else "libgtk-3-0")
    if not shutil.which("update-desktop-database"):
        missing.append("desktop-file-utils")

    if not missing:
        log_ok("依赖检查完成")
        return

    log_warn(f"缺少依赖: {', '.join(missing)}")
    match DISTRO:
        case "fedora":
            cmd = ["sudo", "dnf", "install", "-y"] + missing
        case "ubuntu":
            cmd = ["sudo", "apt", "install", "-y"] + missing
        case _:
            log_warn("未知发行版，请手动安装上述依赖")
            return

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        log_warn("依赖安装失败，部分功能可能不可用")
    log_ok("依赖检查完成")