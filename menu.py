import json
import os
import re
from typing import Any, Optional

MENU_DIR = ".local/menus"
DELETED_DIR = ".local/menus/deleted"


def secure_name(filename: str) -> str:
    filename = os.path.basename(filename)
    filename = re.sub(r"[^\w\s\-.]", "", filename).strip()
    return filename or ""


def menu_path(filename: str) -> Optional[str]:
    # Reject any filename that contains path separators or traversal sequences
    if os.sep in filename or "/" in filename or ".." in filename:
        return None
    safe = secure_name(filename)
    if not safe:
        return None
    path = os.path.join(MENU_DIR, safe)
    if not os.path.abspath(path).startswith(os.path.abspath(MENU_DIR)):
        return None
    return path


def list_menu_files() -> list[str]:
    try:
        return sorted(f for f in os.listdir(MENU_DIR) if f.lower().endswith(".json"))
    except FileNotFoundError:
        return []


def load_menu(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [normalize_item(it, i + 1) for i, it in enumerate(raw) if isinstance(it, dict)]


def normalize_item(raw: dict[str, Any], idx: int) -> dict[str, Any]:
    name = raw.get("name") or raw.get("name_de") or raw.get("name_en") or ""
    return {
        "name": str(name).strip(),
        "price": float(raw.get("price", 0)),
        "extras": [str(e) for e in (raw.get("extras") or []) if e],
        "printer": str(raw.get("printer", "")).strip(),
        "bg_color": str(raw.get("bg_color", "")).strip(),
    }


def save_menu(path: str, items: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def soft_delete(filename: str) -> None:
    src = menu_path(filename)
    if not src or not os.path.exists(src):
        raise FileNotFoundError(filename)
    os.makedirs(DELETED_DIR, exist_ok=True)
    dest = os.path.join(DELETED_DIR, os.path.basename(src))
    os.rename(src, dest)
