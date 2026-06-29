import os

from appimagectl_core.locales.en import MESSAGES as EN_MESSAGES
from appimagectl_core.locales.zh import MESSAGES as ZH_MESSAGES

LOCALES: dict[str, dict[str, str]] = {
    "en": EN_MESSAGES,
    "zh": ZH_MESSAGES,
}


def current_language() -> str:
    for key in ("APPIMAGECTL_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        normalized = value.split(".", 1)[0].replace("-", "_").lower()
        if normalized.startswith("zh"):
            return "zh"
        return "en"
    return "en"


def tr(key: str, **kwargs) -> str:
    lang = current_language()
    catalog = LOCALES.get(lang, EN_MESSAGES)
    template = catalog.get(key) or EN_MESSAGES.get(key) or key
    return template.format(**kwargs)