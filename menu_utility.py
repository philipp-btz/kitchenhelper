import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from werkzeug.utils import secure_filename


def list_menu_files(dir_path: str | None = None) -> list:
    """Return a sorted list of file names in `dir_path`.

    If `dir_path` is None, the function uses the `menu_list` directory
    located next to this file. Works on Windows and Linux.
    """
    if dir_path:
        base = Path(dir_path)
    else:
        base = Path(__file__).resolve().parent / ".local" / "menu_list"

    try:
        base = base.resolve()
    except Exception:
        base = Path(dir_path) if dir_path else Path(".local/menu_list")

    if not base.exists() or not base.is_dir():
        return []

    files = [p.name for p in sorted(base.iterdir()) if p.is_file()]
    return files




def menu_path_from_file(*, menu_file: str, menu_dir) -> Optional[str]:
    safe_file = secure_filename(menu_file or "")
    if not safe_file.lower().endswith(".json"):
        return None
    full_path = os.path.abspath(os.path.join(menu_dir, safe_file))
    menu_root = os.path.abspath(menu_dir)
    if not full_path.startswith(menu_root + os.sep) and full_path != menu_root:
        return None
    return full_path


def normalize_menu_item(raw: Dict[str, Any], item_id: int) -> Dict[str, Any]:
    extras_raw = raw.get("extras", [])
    if isinstance(extras_raw, str):
        extras = [e.strip() for e in extras_raw.replace("\r", "").split("\n") if e.strip()]
    elif isinstance(extras_raw, list):
        extras = [str(e).strip() for e in extras_raw if str(e).strip()]
    else:
        extras = []
    printer_raw = raw.get("printer", 1)
    try:
        printer = int(printer_raw)
    except Exception:
        printer = 1
    printer = 1 if printer not in (1, 2) else printer

    item: Dict[str, Any] = {
        "id": item_id,
        "name": str(raw.get("name", "")).strip(),
        "printer": printer,
        "extras": extras,
    }
    bg_color = str(raw.get("bg_color", "")).strip()
    if bg_color:
        item["bg_color"] = bg_color
    return item