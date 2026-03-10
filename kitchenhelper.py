import json
import os
import sqlite3
import datetime
import logging
from typing import Any, Dict, List, Optional, cast

import menu_picker as mp

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
os.environ["KITCHENHELPER_CONFIG_PATH"] = CONFIG_PATH


# Default DB path (can be overridden by importing module and setting DB_PATH)
def get_db_path():
    return os.environ.get("KITCHENHELPER_DB_PATH", "orders.db")


def get_menu_name():
    return os.environ.get("KITCHENHELPER_MENU_NAME", "NICHT BEKANNT #env-error")


def set_menu_name(new) -> None:
    os.environ["KITCHENHELPER_MENU_NAME"] = new
    return


def get_menu_path():
    return os.environ.get("KITCHENHELPER_MENU_PATH", "backup_menu.json")


def load_config() -> Dict[str, Any]:
    defaults = {
        "host": "0.0.0.0",
        "port": 5099,
        "debug": True,
        "menu_path": "backup_menu.json",
        "db_path": "orders.db",
        "printer_dict": {
            "customer": "192.168.8.187",
            "1": "192.168.8.188",
            "2": "192.168.8.189"
        }
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                defaults.update(cfg)
        except Exception:
            pass
    # normalize paths (ensure values are strings before joining)
    menu_path = mp.list_menu_files()
    defaults["menu_path"] = os.path.join(os.path.dirname(__file__), str(defaults["menu_path"]))
    defaults["db_path"] = os.path.join(os.path.dirname(__file__), str(defaults["db_path"]))
    if "KITCHENHELPER_DB_PATH" not in os.environ.keys():
        os.environ["KITCHENHELPER_DB_PATH"] = str(defaults["db_path"])
        print("FALLBACK DB PATH ERROR")
    os.environ["KITCHENHELPER_MENU_PATH"] = str(defaults["menu_path"])
    os.environ["KITCHENHELPER_MENU_NAME"] = str(os.path.splitext(os.path.basename(defaults["menu_path"]))[0])
    return defaults


def init_db() -> None:
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
    with open(os.environ.get("KITCHENHELPER_MENU_PATH", "backup_menu.json"), "r", encoding="utf-8") as f:
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
