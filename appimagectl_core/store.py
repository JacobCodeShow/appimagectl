import json
from pathlib import Path

from appimagectl_core.i18n import tr
from appimagectl_core.shared import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULTS,
    HOME,
    INSTALLED_LIST,
    log_ok,
)


def init_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(
            json.dumps(
                {"version": 1, "user": DEFAULTS.copy()},
                indent=2,
                ensure_ascii=False,
            )
        )
        log_ok(tr("store.default_config_created", path=CONFIG_FILE))
    if not INSTALLED_LIST.exists():
        INSTALLED_LIST.write_text("[]")


def load_config() -> dict:
    init_config()
    return json.loads(CONFIG_FILE.read_text())


def get_config(key: str, default=None):
    cfg = load_config()
    value = cfg.get("user", {}).get(key, default)
    if isinstance(value, str):
        return value.replace("~", str(HOME))
    return value


def resolve_install_dir() -> Path:
    return Path(get_config("install_dir", str(HOME / ".AppImage")))


def load_installed() -> list[dict]:
    init_config()
    return json.loads(INSTALLED_LIST.read_text())


def save_installed(apps: list[dict]):
    INSTALLED_LIST.write_text(json.dumps(apps, indent=2, ensure_ascii=False))


def find_installed(
    app_id: str = "",
    wmclass: str = "",
    name: str = "",
) -> dict | None:
    apps = load_installed()
    if app_id:
        for app in apps:
            if app.get("app_id") == app_id:
                return app
    if wmclass:
        for app in apps:
            if app.get("wmclass") == wmclass:
                return app
    if name:
        low = name.lower()
        for app in apps:
            if low in app.get("display_name", "").lower() or \
               low in app.get("app_id", "").lower():
                return app
    return None


def find_installed_by_base(base_name: str) -> dict | None:
    if not base_name:
        return None
    low = base_name.lower()
    for app in load_installed():
        if app.get("base_name", "").lower() == low:
            return app
    return None


def add_installed(app: dict):
    apps = load_installed()
    apps = [existing for existing in apps if existing["app_id"] != app["app_id"]]
    apps.append(app)
    save_installed(apps)


def remove_installed(app_id: str):
    apps = load_installed()
    apps = [app for app in apps if app["app_id"] != app_id]
    save_installed(apps)