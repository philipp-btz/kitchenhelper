import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Optional

import config


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.get_db_path(), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(config.get_db_path()), exist_ok=True)
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_number     INTEGER PRIMARY KEY AUTOINCREMENT,
            id               TEXT UNIQUE NOT NULL,
            customer_id      TEXT NOT NULL,
            kitchen          TEXT NOT NULL,
            items            TEXT NOT NULL,
            notes            TEXT DEFAULT '',
            created_at       TEXT NOT NULL,
            cooked_at        TEXT,
            fulfilled_at     TEXT,
            printed_kitchen  INTEGER DEFAULT 0,
            printed_customer INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def save_order(order: dict[str, Any]) -> dict[str, Any]:
    conn = _connect()
    conn.execute(
        "INSERT INTO orders (id, customer_id, kitchen, items, notes, created_at, printed_kitchen, printed_customer)"
        " VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
        (order["id"], order["customer_id"], order["kitchen"],
         json.dumps(order.get("items", []), ensure_ascii=False),
         order.get("notes", ""), order["created_at"]),
    )
    conn.commit()
    row = conn.execute("SELECT order_number FROM orders WHERE id = ?", (order["id"],)).fetchone()
    conn.close()
    order["order_number"] = row["order_number"]
    return order


def get_orders(from_dt: Optional[str] = None, to_dt: Optional[str] = None) -> list[dict[str, Any]]:
    conn = _connect()
    if from_dt and to_dt:
        rows = conn.execute(
            "SELECT * FROM orders WHERE created_at >= ? AND created_at <= ? ORDER BY order_number DESC",
            (from_dt, to_dt),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM orders ORDER BY order_number DESC").fetchall()
    conn.close()
    return [_row_to_order(r) for r in rows]


def get_order_by_number(order_number: int) -> Optional[dict[str, Any]]:
    conn = _connect()
    row = conn.execute("SELECT * FROM orders WHERE order_number = ?", (order_number,)).fetchone()
    conn.close()
    return _row_to_order(row) if row else None


def get_order_by_id(order_id: str) -> Optional[dict[str, Any]]:
    conn = _connect()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return _row_to_order(row) if row else None


def get_uncooked_orders(kitchen: Optional[str] = None) -> list[dict[str, Any]]:
    conn = _connect()
    if kitchen and kitchen != "all":
        rows = conn.execute(
            "SELECT * FROM orders WHERE cooked_at IS NULL AND kitchen = ? ORDER BY created_at ASC",
            (kitchen,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM orders WHERE cooked_at IS NULL ORDER BY created_at ASC"
        ).fetchall()
    conn.close()
    return [_row_to_order(r) for r in rows]


def get_cooked_unfulfilled() -> list[int]:
    conn = _connect()
    rows = conn.execute(
        "SELECT order_number FROM orders WHERE cooked_at IS NOT NULL AND fulfilled_at IS NULL"
        " ORDER BY order_number ASC"
    ).fetchall()
    conn.close()
    return [r["order_number"] for r in rows]


def toggle_cooked(order_id: str) -> Optional[dict[str, Any]]:
    conn = _connect()
    row = conn.execute("SELECT cooked_at FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        conn.close()
        return None
    new_val = None if row["cooked_at"] else datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE orders SET cooked_at = ? WHERE id = ?", (new_val, order_id))
    conn.commit()
    result = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return _row_to_order(result)


def toggle_fulfilled(order_id: str) -> Optional[dict[str, Any]]:
    conn = _connect()
    row = conn.execute("SELECT fulfilled_at FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        conn.close()
        return None
    new_val = None if row["fulfilled_at"] else datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE orders SET fulfilled_at = ? WHERE id = ?", (new_val, order_id))
    conn.commit()
    result = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return _row_to_order(result)


def get_unprinted_kitchen(printer_name: str) -> list[dict[str, Any]]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM orders WHERE printed_kitchen = 0 AND kitchen = ? ORDER BY order_number ASC",
        (printer_name,),
    ).fetchall()
    conn.close()
    return [_row_to_order(r) for r in rows]


def get_unprinted_customer() -> list[dict[str, Any]]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM orders WHERE printed_customer = 0 ORDER BY order_number ASC"
    ).fetchall()
    conn.close()
    return [_row_to_order(r) for r in rows]


def mark_printed_kitchen(order_number: int) -> None:
    conn = _connect()
    conn.execute("UPDATE orders SET printed_kitchen = 1 WHERE order_number = ?", (order_number,))
    conn.commit()
    conn.close()


def mark_printed_customer(order_number: int) -> None:
    conn = _connect()
    conn.execute("UPDATE orders SET printed_customer = 1 WHERE order_number = ?", (order_number,))
    conn.commit()
    conn.close()


def reset_printed_kitchen(order_number: int) -> None:
    conn = _connect()
    conn.execute("UPDATE orders SET printed_kitchen = 0 WHERE order_number = ?", (order_number,))
    conn.commit()
    conn.close()


def reset_printed_customer(order_number: int) -> None:
    conn = _connect()
    conn.execute("UPDATE orders SET printed_customer = 0 WHERE order_number = ?", (order_number,))
    conn.commit()
    conn.close()


def aggregate_orders(from_dt: str, to_dt: str) -> dict[str, Any]:
    conn = _connect()
    rows = conn.execute(
        "SELECT items FROM orders WHERE created_at >= ? AND created_at <= ?",
        (from_dt, to_dt),
    ).fetchall()
    conn.close()
    item_map: dict[str, dict[str, Any]] = {}
    extras_total: dict[str, int] = {}
    for r in rows:
        try:
            items = json.loads(r["items"]) if r["items"] else []
        except Exception:
            items = []
        for it in items:
            name = it.get("name", "Unknown")
            qty = int(it.get("qty", 1))
            extras = it.get("extras") or []
            if name not in item_map:
                item_map[name] = {"count": 0, "extras": {}}
            item_map[name]["count"] += qty
            for ex in extras:
                item_map[name]["extras"][ex] = item_map[name]["extras"].get(ex, 0) + qty
                extras_total[ex] = extras_total.get(ex, 0) + qty
    return {"from": from_dt, "to": to_dt, "item_map": item_map, "extras_total": extras_total}


def _row_to_order(row: sqlite3.Row) -> dict[str, Any]:
    items = json.loads(row["items"]) if row["items"] else []
    return {
        "order_number": row["order_number"],
        "id": row["id"],
        "customer_id": row["customer_id"],
        "kitchen": row["kitchen"],
        "items": items,
        "notes": row["notes"] or "",
        "created_at": row["created_at"],
        "cooked_at": row["cooked_at"],
        "fulfilled_at": row["fulfilled_at"],
        "printed_kitchen": bool(row["printed_kitchen"]),
        "printed_customer": bool(row["printed_customer"]),
    }
