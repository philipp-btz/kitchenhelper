import json
import os
import shutil
from typing import Any

DEFAULTS_DIR = ".defaults"
LOCAL_DIR = ".local"


def setup_local() -> None:
    os.makedirs(f"{LOCAL_DIR}/menus/deleted", exist_ok=True)
    for src_name, dst_name in [
        ("default_settings.json", "settings.json"),
        ("active_menu.json", "active_menu.json"),
    ]:
        src = os.path.join(DEFAULTS_DIR, src_name)
        dst = os.path.join(LOCAL_DIR, dst_name)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)
    backup_src = os.path.join(DEFAULTS_DIR, "backup_menu.json")
    backup_dst = os.path.join(LOCAL_DIR, "menus", "backup_menu.json")
    if os.path.exists(backup_src) and not os.path.exists(backup_dst):
        shutil.copyfile(backup_src, backup_dst)


def get_db_path() -> str:
    return os.environ.get("KITCHENHELPER_DB_PATH", ".local/orders.db")


def get_printer_names() -> list[str]:
    return list(json.loads(os.environ.get("KITCHENHELPER_PRINTER_DICT", "{}")).keys())


def load_config() -> dict[str, Any]:
    setup_local()
    return {
        "printer_dict": json.loads(os.environ.get("KITCHENHELPER_PRINTER_DICT", "{}")),
        "printer_mode": os.environ.get("KITCHENHELPER_PRINTER_MODE", "Dummy"),
        "host": os.environ.get("KITCHENHELPER_HOST", "0.0.0.0"),
        "port": int(os.environ.get("KITCHENHELPER_PORT", "8000")),
        "db_path": get_db_path(),
    }


def load_settings() -> dict[str, Any]:
    path = os.path.join(LOCAL_DIR, "settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict[str, Any]) -> None:
    path = os.path.join(LOCAL_DIR, "settings.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def get_active_menu_path() -> str:
    path = os.path.join(LOCAL_DIR, "active_menu.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("path", f"{LOCAL_DIR}/menus/backup_menu.json")
    except Exception:
        return f"{LOCAL_DIR}/menus/backup_menu.json"


def set_active_menu_path(menu_path: str) -> None:
    path = os.path.join(LOCAL_DIR, "active_menu.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"path": menu_path}, f, indent=2)


def get_active_menu_name() -> str:
    return os.path.splitext(os.path.basename(get_active_menu_path()))[0]
