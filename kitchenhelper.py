import json
import os
import sqlite3
import datetime
import logging
import dotenv
from typing import Any, Dict, List, Optional, cast
import shutil



# Default DB path (can be overridden by importing module and setting DB_PATH)
def get_db_path():
    return os.environ.get("KITCHENHELPER_DB_PATH", ".local/orders.db")


def get_menu_name():
    return os.environ.get("KITCHENHELPER_MENU_NAME", "BITTE SPEISEKARTE WAHLEN")


def set_menu_name(new) -> None:
    os.environ["KITCHENHELPER_MENU_NAME"] = new
    return


def get_menu_path():
    return os.environ.get("KITCHENHELPER_MENU_PATH", ".defaults/backup_menu.json")


def setup_folders():
    os.makedirs(".local", exist_ok=True)
    os.makedirs(".local/user_settings", exist_ok=True)
    os.makedirs(".local/menu_list", exist_ok=True)
    os.makedirs(".local/menu_list/deleted", exist_ok=True)

    # files
    shutil.copyfile(".defaults/backup_menu.json", ".local/menu_list/backup_menu.json")
    shutil.copyfile(".defaults/default.env", ".local/user_settings/user.env")
    shutil.copyfile(".defaults/default.json", ".local/user_settings/user_settings.json")
    if not os.path.isfile(".local/user_settings/current_menu_path.json"):
        shutil.copyfile(".defaults/current_menu_path_template.json", ".local/user_settings/current_menu_path.json")

def load_config() -> Dict[str, Any]:
    setup_folders()

    #load .env
    dotenv.load_dotenv(".defaults/default.env", override=True)
    dotenv.load_dotenv(".local/user_settings/user.env", override=True)
    defaults = {}
    pd = os.environ["KITCHENHELPER_PRINTER_DICT"]
    defaults["printer_dict"] = json.loads(pd)

    #load json
    with open(".local/user_settings/user_settings.json", "r", encoding="utf-8") as f:
        settings_dict = json.load(f)
        defaults.update(settings_dict)
        for key, value in settings_dict.items():
            os.environ[key] = str(value)
    with open(".local/user_settings/current_menu_path.json", "r", encoding="utf-8") as f:
        settings_dict = json.load(f)
        defaults.update(settings_dict)
        for key, value in settings_dict.items():
            os.environ[key] = str(value)

    return defaults


def init_db() -> None:
    print(f"DB PATH: {get_db_path()}")
    os.makedirs(os.path.dirname(get_db_path()), exist_ok=True)
    conn = sqlite3.connect(get_db_path())
    cur = conn.cursor()
    cur.execute("""
                CREATE TABLE IF NOT EXISTS orders
                (
                    order_number     INTEGER PRIMARY KEY AUTOINCREMENT,
                    id               TEXT UNIQUE,
                    customer_id      TEXT,
                    items            LIST,
                    notes            TEXT,
                    created_at       TEXT,
                    fulfilled        TEXT    DEFAULT '--',
                    cooked           TEXT    DEFAULT '--',
                    printed_kitchen  BOOLEAN DEFAULT 0,
                    printed_customer BOOLEAN DEFAULT 0,
                    kitchen          Text
                )
                """)
    conn.commit()
    conn.close()


# Clear any leftover "reserved" state (2) from previous runs so managers
# will pick up orders normally. This resets both customer and kitchen flags.
def clear_db_reservations() -> None:
    try:
        conn = sqlite3.connect(get_db_path())
        cur = conn.cursor()
        cur.execute("UPDATE orders SET printed_customer = 0 WHERE printed_customer = 2")
        cur.execute("UPDATE orders SET printed_kitchen = 0 WHERE printed_kitchen = 2")
        conn.commit()
        conn.close()
    except Exception:
        import logging
        logging.exception("Failed to clear reserved print flags on startup")


def load_menu() -> List[Dict[str, Any]]:
    with open(get_menu_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def enrich_items(items: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Ensure each item dict contains a `printer` attribute taken from the menu when possible."""
    if not items:
        return []
    try:
        menu = load_menu()
        menu_map: Dict[str, Dict[str, Any]] = {m["name"]: m for m in menu}
    except Exception:
        menu_map = {}
    out: List[Dict[str, Any]] = []
    for raw in items:
        if isinstance(raw, dict):
            it: Dict[str, Any] = cast(Dict[str, Any], raw)
            name = it.get("name")
            if name and name in menu_map:
                it.setdefault("printer", menu_map[name].get("printer"))
            out.append(it)
        else:
            # fallback: convert to dict
            name = str(raw)
            printer = menu_map.get(name, {}).get("printer") if menu_map else None
            out.append({"name": name, "extras": [], "qty": 1, "printer": printer})
    return out


def format_timestamp(raw: Optional[str]) -> str:
    """Format a stored timestamp string into a human-readable form.

    Stored format: "YYYY_mm_dd-HH_MM_SS" (e.g. 2026_02_16-14_30_00).
    Returns empty string for missing/placeholder values.
    """
    if not raw or raw == "no" or raw == "--":
        return ""
    try:
        dt = datetime.datetime.strptime(raw, "%Y_%m_%d-%H_%M_%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def aggregate_day(date_str: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate item and extra counts for a given day.

    date_str: "YYYY-MM-DD" (ISO) or None for today.
    Returns dict with "date", "items" (name->count), "extras" (extra->count).
    """
    if date_str:
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            dt = datetime.datetime.now()
    else:
        dt = datetime.datetime.now()
    prefix = dt.strftime("%Y_%m_%d") + "-"
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT items FROM orders WHERE created_at LIKE ?", (prefix + "%",))
    rows = cur.fetchall()
    conn.close()

    # build nested structure: items -> {count, extras: {extra: count}}
    items_map: Dict[str, Dict[str, Any]] = {}
    extras_totals: Dict[str, int] = {}
    for r in rows:
        try:
            items = cast(List[Dict[str, Any]], json.loads(r["items"])) if r["items"] else []
        except Exception:
            items = []
        for it in items:
            name = it.get("name", "Unbekannt")
            qty = it.get("qty", 1)
            extras = it.get("extras", []) or []
            if name not in items_map:
                items_map[name] = {"count": 0, "extras": {}}
            items_map[name]["count"] += qty
            for ex in extras:
                if ex not in items_map[name]["extras"]:
                    items_map[name]["extras"][ex] = 0
                items_map[name]["extras"][ex] += qty
                if ex not in extras_totals:
                    extras_totals[ex] = 0
                extras_totals[ex] += qty

    return {
        "date": dt.strftime("%Y-%m-%d"),
        "item_map": items_map,
        "extras_total": extras_totals,
    }


def save_order(order: Dict[str, Any]) -> Dict[str, Any]:
    conn = sqlite3.connect(get_db_path())
    cur = conn.cursor()
    # ensure items carry `printer` metadata before saving
    items = order.get("items", [])
    cur.execute(
        "INSERT INTO orders (id, customer_id, items, notes, created_at, printed_kitchen, printed_customer, kitchen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (order["id"], order.get("customer_id"), json.dumps(items, ensure_ascii=False),
         order.get("notes", "Notes unobtainable"), order["created_at"], int(order["printed_kitchen"]),
         int(order["printed_customer"]), order.get("kitchen", ""))
    )
    conn.commit()
    order_number = cur.lastrowid
    conn.close()
    order["order_number"] = order_number
    return order


'''
def update_order(
        order_number: int, items: Optional[List[Dict[str, Any]]] = None, notes: Optional[str] = None,
        printed: Optional[bool] = None
        ) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(get_db_path())
    cur = conn.cursor()
    fields: List[str] = []
    params: List[Any] = []
    if items is not None:
        # enrich items with printer info before storing
        items = enrich_items(items)
        fields.append('items = ?')
        params.append(json.dumps(items, ensure_ascii=False))
    if notes is not None:
        fields.append('notes = ?')
        params.append(notes)
    if printed is not None:
        fields.append('printed = ?')
        params.append(int(bool(printed)))
    if not fields:
        conn.close()
        return None
    params.append(order_number)
    sql = f"UPDATE orders SET {', '.join(fields)} WHERE order_number = ?"
    cur.execute(sql, tuple(params))
    conn.commit()
    conn.close()
    return get_order_by_number(order_number)
    
'''

def get_orders() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY order_number DESC")
    rows = cur.fetchall()
    conn.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        items: List[Dict[str, Any]] = cast(List[Dict[str, Any]], json.loads(r["items"])) if r["items"] else []
        # format fulfilled and cooked timestamps if present (stored as "YYYY_mm_dd-HH_MM_SS"), otherwise marker
        fulfilled_raw = r["fulfilled"] if "fulfilled" in r.keys() and r["fulfilled"] is not None else "no"
        cooked_raw = r["cooked"] if "cooked" in r.keys() and r["cooked"] is not None else "no"

        out.append({
            "order_number": r["order_number"],
            "id": r["id"],
            "items": items,
            "notes": r["notes"],
            "created_at": r["created_at"],
            "printed_kitchen": bool(r["printed_kitchen"]),
            "printed_customer": bool(r["printed_customer"]),
            "fulfilled": fulfilled_raw,
            "cooked": cooked_raw,
        })
    return out


def get_order_by_number(order_number: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE order_number = ?", (order_number,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    items: List[Dict[str, Any]] = cast(List[Dict[str, Any]], json.loads(r["items"])) if r["items"] else []
    #logging.info(f"Raw FULFILLED: {r["fulfilled"] if "fulfilled" in r.keys() and r["fulfilled"] is not None else "no"}, \nRAW COOKED: {r["cooked"] if "cooked" in r.keys() and r["cooked"] is not None else "no"}")
    return {
        "order_number": r["order_number"],
        "id": r["id"],
        "items": items,
        "notes": r["notes"],
        "customer_id": r["customer_id"],
        "created_at": r["created_at"],
        "printed_kitchen": bool(r["printed_kitchen"]),
        "printed_customer": bool(r["printed_customer"]),
        "fulfilled": format_timestamp(
            r["fulfilled"] if "fulfilled" in r.keys() and r["fulfilled"] is not None else "no"),
        "cooked": format_timestamp(r["cooked"] if "cooked" in r.keys() and r["cooked"] is not None else "no")
    }
