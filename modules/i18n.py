import os

import oyaml as yaml

from modules.app_logger import app_logger

# translation files: i18n/<lang>.yaml (e.g. i18n/pt.yaml for LANG = PT)
# English strings are used as keys, so internal names (item names, page names)
# stay in English and only the displayed text is translated.
I18N_DIR = "i18n"

LANGUAGES = {
    "EN": "English",
    "PT": "Português",
}

_translations = {}


def load_translations(lang):
    _translations.clear()
    if not lang or lang.upper() == "EN":
        return

    path = os.path.join(I18N_DIR, f"{lang.lower()}.yaml")
    try:
        with open(path, encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
    except FileNotFoundError:
        app_logger.warning(f"translation file not found: {path}")
        return

    _translations.update({str(k): str(v) for k, v in data.items() if v is not None})
    app_logger.info(f"load translations: {path} ({len(_translations)} items)")


def tr(text):
    if not isinstance(text, str):
        return text
    return _translations.get(text, text)
