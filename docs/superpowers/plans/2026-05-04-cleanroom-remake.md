# KitchenHelper Clean Room Remake — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Flask/gunicorn/multi-process KitchenHelper with a clean FastAPI/uvicorn single-process rewrite, preserving all features and fixing known bugs.

**Architecture:** Single FastAPI process with one daemon thread per printer. SQLite with WAL mode. HTMX + Jinja2 for most UI; vanilla JS polling for live kitchen/customer displays (unchanged approach, JSON API). All config from env vars; user settings and menus in `.local/`.

**Tech Stack:** FastAPI, uvicorn, Jinja2, python-multipart, python-escpos, python-dotenv, pytest, httpx

---

## File Map

**New files (create):**
- `config.py` — env loading, settings I/O, menu path I/O
- `db.py` — all SQLite queries, WAL mode
- `menu.py` — menu file I/O, normalization, secure path
- `printing/__init__.py` — empty
- `printing/receipts.py` — ESC/POS formatting functions
- `printing/manager.py` — QueueManager class + module-level registry
- `routers/__init__.py` — empty
- `routers/orders.py` — GET /, POST /order, /cooked, /fulfilled, /export, /print_*
- `routers/displays.py` — /kitchen_display, /customer_display, /api/uncooked_orders, /api/cooked_unfulfilled
- `routers/menus.py` — /menus/* routes
- `routers/settings.py` — GET/POST /settings
- `routers/reports.py` — /reports, /api/reports, /reports/print
- `app.py` — FastAPI app, lifespan, router mounts (replaces old app.py)
- `templates/base.html`
- `templates/index.html`
- `templates/kitchen_display.html`
- `templates/customer_display.html`
- `templates/orders.html`
- `templates/menu_selector.html`
- `templates/menu_editor.html`
- `templates/menu_upload_confirm.html`
- `templates/settings.html`
- `templates/reports.html`
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/test_config.py`
- `tests/test_db.py`
- `tests/test_menu.py`
- `.defaults/default_settings.json`
- `.defaults/active_menu.json`

**Modified:**
- `pyproject.toml` — swap Flask/gunicorn for FastAPI/uvicorn, add pytest/httpx
- `Dockerfile` — uvicorn instead of gunicorn, remove wsgi.py reference
- `docker-compose.yml` — no changes needed to structure

**Deleted at end:**
- `kitchenhelper.py`, `printutil.py`, `printer_service.py`, `menu_utility.py`, `wsgi.py`, `test.py`

---

## Task 1: Update pyproject.toml and install dependencies

**Files:** `pyproject.toml`

- [ ] **Step 1: Replace pyproject.toml contents**

```toml
[project]
name = "kitchenhelper"
version = "2.0.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "python-escpos>=3.1",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
    "pytest-asyncio>=0.23",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Sync dependencies**

```bash
uv sync
```

Expected: resolves fastapi, uvicorn, jinja2, python-multipart, python-escpos, python-dotenv; dev group gets pytest, httpx, pytest-asyncio.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: swap to FastAPI/uvicorn, add test deps"
```

---

## Task 2: config.py

**Files:** `config.py`, `.defaults/default_settings.json`, `.defaults/active_menu.json`, `tests/conftest.py`, `tests/test_config.py`

- [ ] **Step 1: Create `.defaults/default_settings.json`**

```json
{
  "print_customer_double": false,
  "print_extra_order_nr": false,
  "kitchen_buzzer": false
}
```

- [ ] **Step 2: Create `.defaults/active_menu.json`**

```json
{
  "path": ".local/menus/backup_menu.json"
}
```

- [ ] **Step 3: Create `tests/conftest.py`**

```python
import os
import shutil
import pytest


@pytest.fixture
def tmp_local(tmp_path, monkeypatch):
    local = tmp_path / ".local"
    (local / "menus" / "deleted").mkdir(parents=True)
    defaults = tmp_path / ".defaults"
    defaults.mkdir()
    (defaults / "default_settings.json").write_text(
        '{"print_customer_double": false, "print_extra_order_nr": false, "kitchen_buzzer": false}'
    )
    (defaults / "active_menu.json").write_text(
        '{"path": ".local/menus/backup_menu.json"}'
    )
    (defaults / "backup_menu.json").write_text("[]")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KITCHENHELPER_DB_PATH", str(local / "orders.db"))
    monkeypatch.setenv("KITCHENHELPER_PRINTER_DICT", '{"kitchen1": "1.2.3.4", "customer": "1.2.3.5"}')
    monkeypatch.setenv("KITCHENHELPER_PRINTER_MODE", "Dummy")
    return local
```

- [ ] **Step 4: Write failing tests**

```python
# tests/test_config.py
import json
import os
import pytest
import config


def test_get_printer_names(tmp_local, monkeypatch):
    monkeypatch.setenv("KITCHENHELPER_PRINTER_DICT", '{"kitchen1":"1.1.1.1","customer":"2.2.2.2"}')
    assert config.get_printer_names() == ["kitchen1", "customer"]


def test_setup_local_copies_defaults(tmp_local):
    config.setup_local()
    assert (tmp_local / "settings.json").exists()
    assert (tmp_local / "active_menu.json").exists()
    assert (tmp_local / "menus" / "backup_menu.json").exists()


def test_setup_local_does_not_overwrite(tmp_local):
    (tmp_local / "settings.json").write_text('{"kitchen_buzzer": true}')
    config.setup_local()
    data = json.loads((tmp_local / "settings.json").read_text())
    assert data["kitchen_buzzer"] is True


def test_load_settings_returns_defaults_when_missing(tmp_local):
    config.setup_local()
    s = config.load_settings()
    assert "print_customer_double" in s


def test_save_and_load_settings(tmp_local):
    config.setup_local()
    config.save_settings({"print_customer_double": True, "print_extra_order_nr": False, "kitchen_buzzer": False})
    s = config.load_settings()
    assert s["print_customer_double"] is True


def test_get_set_active_menu_path(tmp_local):
    config.setup_local()
    config.set_active_menu_path(".local/menus/test.json")
    assert config.get_active_menu_path() == ".local/menus/test.json"


def test_load_config_parses_printer_dict(tmp_local):
    cfg = config.load_config()
    assert "kitchen1" in cfg["printer_dict"]
    assert cfg["printer_dict"]["kitchen1"] == "1.2.3.4"
```

- [ ] **Step 5: Run tests — verify all fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 6: Create `config.py`**

```python
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
```

- [ ] **Step 7: Run tests — verify all pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 7 passed.

- [ ] **Step 8: Commit**

```bash
git add config.py tests/conftest.py tests/test_config.py .defaults/default_settings.json .defaults/active_menu.json
git commit -m "feat: add config module with settings and menu path management"
```

---

## Task 3: db.py

**Files:** `db.py`, `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db.py
import pytest
import db


def test_init_db_creates_table(tmp_local):
    db.init_db()
    import sqlite3, config
    conn = sqlite3.connect(config.get_db_path())
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    assert any(t[0] == "orders" for t in tables)


def test_save_and_get_order(tmp_local):
    db.init_db()
    order = db.save_order({
        "id": "test-uuid-1",
        "customer_id": "cust-1",
        "kitchen": "kitchen1",
        "items": [{"name": "Burger", "qty": 1, "extras": []}],
        "notes": "no onions",
        "created_at": "2026-05-04T12:00:00",
    })
    assert order["order_number"] is not None
    fetched = db.get_order_by_number(order["order_number"])
    assert fetched["notes"] == "no onions"
    assert fetched["items"][0]["name"] == "Burger"


def test_toggle_cooked(tmp_local):
    db.init_db()
    order = db.save_order({
        "id": "test-uuid-2", "customer_id": "c", "kitchen": "k",
        "items": [], "notes": "", "created_at": "2026-05-04T12:00:00",
    })
    result = db.toggle_cooked(order["id"])
    assert result["cooked_at"] is not None
    result2 = db.toggle_cooked(order["id"])
    assert result2["cooked_at"] is None


def test_toggle_fulfilled(tmp_local):
    db.init_db()
    order = db.save_order({
        "id": "test-uuid-3", "customer_id": "c", "kitchen": "k",
        "items": [], "notes": "", "created_at": "2026-05-04T12:00:00",
    })
    result = db.toggle_fulfilled(order["id"])
    assert result["fulfilled_at"] is not None


def test_get_uncooked_orders(tmp_local):
    db.init_db()
    db.save_order({"id": "u1", "customer_id": "c", "kitchen": "kitchen1",
                   "items": [], "notes": "", "created_at": "2026-05-04T12:00:00"})
    db.save_order({"id": "u2", "customer_id": "c", "kitchen": "kitchen2",
                   "items": [], "notes": "", "created_at": "2026-05-04T12:01:00"})
    all_orders = db.get_uncooked_orders()
    assert len(all_orders) == 2
    k1_only = db.get_uncooked_orders(kitchen="kitchen1")
    assert len(k1_only) == 1 and k1_only[0]["kitchen"] == "kitchen1"


def test_aggregate_orders(tmp_local):
    db.init_db()
    db.save_order({
        "id": "a1", "customer_id": "c", "kitchen": "k",
        "items": [{"name": "Pizza", "qty": 2, "extras": ["extra cheese"]}],
        "notes": "", "created_at": "2026-05-04T12:00:00",
    })
    result = db.aggregate_orders("2026-05-04T00:00:00", "2026-05-04T23:59:59")
    assert result["item_map"]["Pizza"]["count"] == 2
    assert result["item_map"]["Pizza"]["extras"]["extra cheese"] == 2
    assert result["extras_total"]["extra cheese"] == 2


def test_get_unprinted_kitchen(tmp_local):
    db.init_db()
    db.save_order({"id": "p1", "customer_id": "c", "kitchen": "kitchen1",
                   "items": [], "notes": "", "created_at": "2026-05-04T12:00:00"})
    orders = db.get_unprinted_kitchen("kitchen1")
    assert len(orders) == 1
    db.mark_printed_kitchen(orders[0]["order_number"])
    assert db.get_unprinted_kitchen("kitchen1") == []


def test_get_unprinted_customer(tmp_local):
    db.init_db()
    db.save_order({"id": "p2", "customer_id": "c", "kitchen": "k",
                   "items": [], "notes": "", "created_at": "2026-05-04T12:00:00"})
    orders = db.get_unprinted_customer()
    assert len(orders) == 1
    db.mark_printed_customer(orders[0]["order_number"])
    assert db.get_unprinted_customer() == []
```

- [ ] **Step 2: Run tests — verify fail**

```bash
uv run pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Create `db.py`**

```python
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
```

- [ ] **Step 4: Run tests — verify pass**

```bash
uv run pytest tests/test_db.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add database layer with WAL mode and ISO 8601 timestamps"
```

---

## Task 4: menu.py

**Files:** `menu.py`, `tests/test_menu.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_menu.py
import json
import pytest
import menu


def test_normalize_item_basic():
    raw = {"name": "Burger", "price": 9.5, "extras": ["Cheese"], "printer": "kitchen1"}
    result = menu.normalize_item(raw, 1)
    assert result["name"] == "Burger"
    assert result["price"] == 9.5
    assert result["extras"] == ["Cheese"]
    assert result["printer"] == "kitchen1"
    assert result["bg_color"] == ""


def test_normalize_item_name_de_fallback():
    raw = {"name_de": "Schnitzel", "price": 12.0, "extras": [], "printer": "k"}
    result = menu.normalize_item(raw, 1)
    assert result["name"] == "Schnitzel"


def test_normalize_item_strips_whitespace():
    raw = {"name": "  Pizza  ", "price": 8.0, "extras": [], "printer": " kitchen1 "}
    result = menu.normalize_item(raw, 1)
    assert result["name"] == "Pizza"
    assert result["printer"] == "kitchen1"


def test_menu_path_safe(tmp_local):
    path = menu.menu_path("my_menu.json")
    assert path is not None
    assert "my_menu.json" in path
    assert ".." not in path


def test_menu_path_blocks_traversal(tmp_local):
    assert menu.menu_path("../../etc/passwd") is None


def test_list_menu_files(tmp_local):
    (tmp_local / "menus" / "alpha.json").write_text("[]")
    (tmp_local / "menus" / "beta.json").write_text("[]")
    files = menu.list_menu_files()
    assert "alpha.json" in files
    assert "beta.json" in files


def test_load_menu(tmp_local):
    data = [{"name": "Pizza", "price": 8.0, "extras": [], "printer": "k", "bg_color": ""}]
    (tmp_local / "menus" / "test.json").write_text(json.dumps(data))
    items = menu.load_menu(str(tmp_local / "menus" / "test.json"))
    assert len(items) == 1
    assert items[0]["name"] == "Pizza"


def test_soft_delete_moves_file(tmp_local):
    (tmp_local / "menus" / "old.json").write_text("[]")
    menu.soft_delete("old.json")
    assert not (tmp_local / "menus" / "old.json").exists()
    assert (tmp_local / "menus" / "deleted" / "old.json").exists()
```

- [ ] **Step 2: Run tests — verify fail**

```bash
uv run pytest tests/test_menu.py -v
```

Expected: `ModuleNotFoundError: No module named 'menu'`

- [ ] **Step 3: Create `menu.py`**

```python
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
```

- [ ] **Step 4: Run tests — verify pass**

```bash
uv run pytest tests/test_menu.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add menu.py tests/test_menu.py
git commit -m "feat: add menu module with safe path handling and normalization"
```

---

## Task 5: printing/receipts.py

**Files:** `printing/__init__.py`, `printing/receipts.py`

No unit tests for ESC/POS formatting (requires physical hardware). Verify by inspection.

- [ ] **Step 1: Create `printing/__init__.py`**

Empty file:
```python
```

- [ ] **Step 2: Create `printing/receipts.py`**

```python
import json
import time
from datetime import datetime
from typing import Any


def _parse_items(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, str):
        return json.loads(items)
    return items or []


def format_kitchen(printer: Any, order: dict[str, Any], settings: dict[str, Any]) -> None:
    items = _parse_items(order.get("items", []))
    order_no = order.get("order_number", "?")
    notes = order.get("notes", "")

    printer.set_with_default()

    if len(items) == 1 and items[0].get("qty", 1) == 1:
        printer.set(invert=True, font="a", height=2, width=3, custom_size=True, align="center", bold=True)
        printer.text("EINZELBESTELLUNG")

    printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
    printer.text(f"\n\nNr: {order_no}\n\n")

    printer.set(font="a", align="left", bold=True, normal_textsize=True,
                double_height=True, double_width=True, invert=False)
    printer.text("\u2500" * 24 + "\n")
    for item in items:
        printer.text(f"{item.get('qty', 1)}x {item.get('name', '')}\n")
        for extra in (item.get("extras") or []):
            printer.text(f"  {extra}\n")
    printer.text("\u2500" * 24 + "\n")

    if notes:
        printer.set(align="center", invert=True, bold=True, double_height=True, double_width=True)
        printer.text(f"\n\n{notes}\n\n")

    printer.set(align="left", invert=False, normal_textsize=True)
    printer.text(f"\nBestellzeit: {order.get('created_at', '')}\n")
    printer.text(f"Kunde: {order.get('customer_id', '')}\n")

    printer.ln(4)
    printer._raw(b"\x1D\x56\x42\x00")

    if settings.get("kitchen_buzzer"):
        printer.buzzer(times=2, duration=4)


def format_customer(printer: Any, order: dict[str, Any], settings: dict[str, Any]) -> None:
    items = _parse_items(order.get("items", []))
    order_no = order.get("order_number", "?")
    notes = order.get("notes", "")
    count = 2 if settings.get("print_customer_double") else 1

    for _ in range(count):
        printer.set_with_default()
        printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
        printer.image("static/icon_beifallers.png", center=False)
        time.sleep(0.5)
        printer.text(f"\nNr: {order_no}\n\n")

        printer.set(font="a", align="left", bold=True, normal_textsize=True)
        printer.text("\u2500" * 48 + "\n")
        for item in items:
            printer.text(f"{item.get('qty', 1)}x {item.get('name', '')}\n")
            for extra in (item.get("extras") or []):
                printer.text(f"  {extra}\n")
        printer.text("\u2500" * 48 + "\n")

        if notes:
            printer.set(align="left", bold=True, normal_textsize=True)
            printer.text(f"\n{notes}\n\n")
        else:
            printer.text("\n")

        printer.set(align="center")
        printer.qr("https://share.google/97GUBhxCRPvn9ZpVY", size=5)
        printer.set(align="center", invert=False, bold=True, double_height=False, double_width=True)
        printer.text("Vielen Dank für Ihre \nBestellung!\n")

        printer.set(align="left", normal_textsize=True)
        printer.text(f"\nBestellzeit: {order.get('created_at', '')}\n")
        printer.text(f"Kunde: {order.get('customer_id', '')}\n")
        printer._raw(b"\x1D\x56\x42\x00")

    if settings.get("print_extra_order_nr"):
        printer.set_with_default(font="a", height=2, width=3, custom_size=True,
                                 align="center", bold=True, smooth=True)
        printer.text(f"\n\n\n\nNr: {order_no}\n\n\n\n\n")
        printer._raw(b"\x1D\x56\x42\x00")


def format_report(printer: Any, data: dict[str, Any]) -> None:
    printer.set_with_default()
    printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
    printer.text(f"\n\nBericht:\n{data.get('from', '')} –\n{data.get('to', '')}\n\n")

    printer.set(font="a", align="left", bold=True, normal_textsize=True,
                double_height=False, double_width=False, invert=False)
    printer.text(f"Gedruckt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    printer.text("\nBestellte Gerichte:\n")

    for name, info in data.get("item_map", {}).items():
        printer.text(f"  {info['count']}x {name}\n")
        for extra, qty in info.get("extras", {}).items():
            printer.text(f"    {qty}x {extra}\n")

    if data.get("extras_total"):
        printer.text("\nExtras gesamt:\n")
        for extra, qty in data["extras_total"].items():
            printer.text(f"  {qty}x {extra}\n")

    printer.ln(5)
    printer._raw(b"\x1D\x56\x42\x00")
```

- [ ] **Step 3: Commit**

```bash
git add printing/__init__.py printing/receipts.py
git commit -m "feat: add ESC/POS receipt formatting module"
```

---

## Task 6: printing/manager.py

**Files:** `printing/manager.py`

- [ ] **Step 1: Create `printing/manager.py`**

```python
import logging
import threading
import time
from typing import Any, Optional

import config
import db
from printing import receipts

_managers: dict[str, "QueueManager"] = {}


def register(name: str, ip: str, mode: str) -> "QueueManager":
    m = QueueManager(name, ip, mode)
    _managers[name] = m
    return m


def get_managers() -> dict[str, "QueueManager"]:
    return _managers


def get_manager(name: str) -> Optional["QueueManager"]:
    return _managers.get(name)


class QueueManager:
    def __init__(self, printer_name: str, printer_ip: str, printer_mode: str = "Dummy"):
        self.printer_name = printer_name
        self.printer_ip = printer_ip
        self.printer_mode = printer_mode
        self._printer = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._queue: list[tuple[str, dict]] = []
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"printer-{printer_name}"
        )
        self._thread.start()
        logging.info(f"QueueManager started: {printer_name} @ {printer_ip} ({printer_mode})")

    def enqueue(self, job: str, kwargs: dict | None = None) -> None:
        with self._lock:
            self._queue.append((job, kwargs or {}))

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    def _get_printer(self) -> Any:
        from escpos.printer import Dummy, Network
        if self._printer is None:
            if self.printer_mode == "Thermo":
                self._printer = Network(self.printer_ip, port=9100, profile="TM-T88V")
            else:
                self._printer = Dummy()
        return self._printer

    def _run(self) -> None:
        while not self._stop.is_set():
            job = None
            with self._lock:
                if self._queue:
                    job = self._queue[0]

            if job:
                func, kwargs = job
                ok = self._dispatch(func, kwargs)
                if ok:
                    with self._lock:
                        if self._queue and self._queue[0] == job:
                            self._queue.pop(0)
                if self._stop.wait(0.5):
                    break
            else:
                try:
                    self._poll_db()
                except Exception:
                    logging.exception(f"DB poll error ({self.printer_name})")
                if self._stop.wait(1):
                    break

    def _poll_db(self) -> None:
        with self._lock:
            queued_nrs = {
                kw.get("order", {}).get("order_number")
                for _, kw in self._queue
                if "order" in kw
            }
        if self.printer_name == "customer":
            orders = db.get_unprinted_customer()
            job_name = "customer"
        else:
            orders = db.get_unprinted_kitchen(self.printer_name)
            job_name = "kitchen"
        for order in orders:
            if order["order_number"] not in queued_nrs:
                self.enqueue(job_name, {"order": order})

    def _dispatch(self, func: str, kwargs: dict) -> bool:
        try:
            printer = self._get_printer()
            settings = config.load_settings()
            if func == "kitchen":
                receipts.format_kitchen(printer, kwargs["order"], settings)
                nr = kwargs["order"].get("order_number")
                if nr is not None:
                    db.mark_printed_kitchen(nr)
            elif func == "customer":
                receipts.format_customer(printer, kwargs["order"], settings)
                nr = kwargs["order"].get("order_number")
                if nr is not None:
                    db.mark_printed_customer(nr)
            elif func == "report":
                receipts.format_report(printer, kwargs["data"])
            else:
                logging.warning(f"Unknown job type: {func}")
            return True
        except Exception:
            logging.exception(f"Print error ({self.printer_name}, {func})")
            self._printer = None
            return False
```

- [ ] **Step 2: Commit**

```bash
git add printing/manager.py
git commit -m "feat: add QueueManager with daemon thread and DB polling"
```

---

## Task 7: app.py

**Files:** `app.py` (replaces existing)

- [ ] **Step 1: Replace `app.py` with the new FastAPI app**

```python
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import db
import printing.manager as pm


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = config.load_config()
    db.init_db()
    for name, ip in cfg["printer_dict"].items():
        pm.register(name, ip, cfg["printer_mode"])
    yield
    for m in pm.get_managers().values():
        m.stop()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

from routers import displays, menus, orders, reports, settings  # noqa: E402
app.include_router(orders.router)
app.include_router(displays.router)
app.include_router(menus.router)
app.include_router(settings.router)
app.include_router(reports.router)
```

- [ ] **Step 2: Create `routers/__init__.py`** (empty file)

- [ ] **Step 3: Verify app imports without error**

```bash
uv run python -c "import app; print('OK')"
```

Expected: fails with `ModuleNotFoundError: No module named 'routers.orders'` — that's correct, routers don't exist yet.

- [ ] **Step 4: Commit**

```bash
git add app.py routers/__init__.py
git commit -m "feat: add FastAPI app with lifespan printer startup"
```

---

## Task 8: routers/orders.py

**Files:** `routers/orders.py`

- [ ] **Step 1: Create `routers/orders.py`**

```python
import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

import config
import db
import menu as menu_module
import printing.manager as pm

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def index(request: Request):
    try:
        items = menu_module.load_menu(config.get_active_menu_path())
    except Exception:
        items = []
    return templates.TemplateResponse("index.html", {
        "request": request,
        "menu": items,
        "menu_name": config.get_active_menu_name(),
    })


@router.post("/order")
async def submit_order(
    request: Request,
    items: str = Form(...),
    notes: str = Form(""),
):
    try:
        raw_items = json.loads(items)
    except Exception:
        raw_items = []

    try:
        menu_items = menu_module.load_menu(config.get_active_menu_path())
        menu_map = {it["name"]: it for it in menu_items}
    except Exception:
        menu_map = {}

    enriched: list[dict[str, Any]] = []
    for it in raw_items:
        if isinstance(it, dict):
            name = it.get("name", "")
            if name in menu_map:
                it.setdefault("printer", menu_map[name].get("printer", ""))
            enriched.append(it)

    customer_id = str(uuid.uuid4())
    now = datetime.now().isoformat(timespec="seconds")
    order_numbers: list[str] = []

    printers: set[str] = {it.get("printer", "") for it in enriched}
    if not printers:
        printers = {""}

    for printer in printers:
        printer_items = [it for it in enriched if it.get("printer", "") == printer]
        if not printer_items:
            continue
        order = db.save_order({
            "id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "kitchen": printer,
            "items": printer_items,
            "notes": notes,
            "created_at": now,
        })
        order_numbers.append(str(order["order_number"]))

    order_number_str = " + ".join(order_numbers)
    accept = request.headers.get("Accept", "")
    xhr = request.headers.get("X-Requested-With", "")
    if "application/json" in accept or xhr == "XMLHttpRequest":
        return JSONResponse({"status": "ok", "order_number": order_number_str})
    return RedirectResponse("/orders", status_code=303)


@router.post("/cooked/{order_id}")
async def cooked(order_id: str, request: Request):
    result = db.toggle_cooked(order_id)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    accept = request.headers.get("Accept", "")
    xhr = request.headers.get("X-Requested-With", "")
    if "application/json" in accept or xhr == "XMLHttpRequest":
        return JSONResponse({"status": "ok", "cooked_at": result["cooked_at"]})
    return RedirectResponse("/orders", status_code=303)


@router.post("/fulfilled/{order_id}")
async def fulfilled(order_id: str, request: Request):
    result = db.toggle_fulfilled(order_id)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    accept = request.headers.get("Accept", "")
    xhr = request.headers.get("X-Requested-With", "")
    if "application/json" in accept or xhr == "XMLHttpRequest":
        return JSONResponse({"status": "ok", "fulfilled_at": result["fulfilled_at"]})
    return RedirectResponse("/orders", status_code=303)


@router.get("/orders")
async def orders_view(request: Request, from_dt: str = "", to_dt: str = ""):
    orders = db.get_orders(from_dt or None, to_dt or None)
    return templates.TemplateResponse("orders.html", {
        "request": request,
        "orders": orders,
        "from_dt": from_dt,
        "to_dt": to_dt,
    })


@router.get("/orders/{order_number}/export")
async def order_export(order_number: int):
    order = db.get_order_by_number(order_number)
    if not order:
        return Response("Bestellung nicht gefunden", status_code=404)
    lines = [
        f"Bestell-Nr.: {order['order_number']}",
        f"UUID: {order['id']}",
        f"Zeit: {order['created_at']}",
    ]
    for it in order.get("items", []):
        lines.append(f"{it.get('qty', 1)}x {it.get('name', '')}")
        for ex in (it.get("extras") or []):
            lines.append(f"  Extras: {ex}")
    if order["notes"]:
        lines.append(f"Notiz: {order['notes']}")
    lines.append(f"Gedruckt (Küche): {'Ja' if order['printed_kitchen'] else 'Nein'}")
    lines.append(f"Gedruckt (Kunde): {'Ja' if order['printed_customer'] else 'Nein'}")
    text = "\n".join(lines)
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=order_{order_number}.txt"},
    )


@router.post("/orders/{order_number}/print_kitchen")
async def reprint_kitchen(order_number: int):
    order = db.get_order_by_number(order_number)
    if not order:
        return Response("Bestellung nicht gefunden", status_code=404)
    db.reset_printed_kitchen(order_number)
    return RedirectResponse("/orders", status_code=303)


@router.post("/orders/{order_number}/print_customer")
async def reprint_customer(order_number: int):
    order = db.get_order_by_number(order_number)
    if not order:
        return Response("Bestellung nicht gefunden", status_code=404)
    db.reset_printed_customer(order_number)
    return RedirectResponse("/orders", status_code=303)
```

- [ ] **Step 2: Commit**

```bash
git add routers/orders.py
git commit -m "feat: add order routes (submit, cooked, fulfilled, export, reprint)"
```

---

## Task 9: routers/displays.py

**Files:** `routers/displays.py`

- [ ] **Step 1: Create `routers/displays.py`**

```python
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

import config
import db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/kitchen_display")
async def kitchen_display(request: Request):
    printer_names = config.get_printer_names()
    kitchen_printers = [p for p in printer_names if p != "customer"]
    return templates.TemplateResponse("kitchen_display.html", {
        "request": request,
        "kitchen_printers": kitchen_printers,
    })


@router.get("/customer_display")
async def customer_display(request: Request):
    return templates.TemplateResponse("customer_display.html", {"request": request})


@router.get("/api/uncooked_orders")
async def api_uncooked_orders(kitchen: str = "all"):
    orders = db.get_uncooked_orders(kitchen if kitchen != "all" else None)
    import json
    return Response(
        content=json.dumps(orders, ensure_ascii=False),
        media_type="application/json",
    )


@router.get("/api/cooked_unfulfilled")
async def api_cooked_unfulfilled():
    nums = db.get_cooked_unfulfilled()
    return JSONResponse({"order_numbers": nums})
```

- [ ] **Step 2: Commit**

```bash
git add routers/displays.py
git commit -m "feat: add display routes and polling API endpoints"
```

---

## Task 10: routers/menus.py

**Files:** `routers/menus.py`

- [ ] **Step 1: Create `routers/menus.py`**

```python
import os

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import config
import menu as menu_module

router = APIRouter()
templates = Jinja2Templates(directory="templates")
MENU_DIR = ".local/menus"


@router.get("/menus")
async def menus_view(request: Request, selected: str = "", saved: str = ""):
    files = menu_module.list_menu_files()
    menus = [{"file": f, "title": os.path.splitext(f)[0]} for f in files]
    settings = config.load_settings()
    return templates.TemplateResponse("menu_selector.html", {
        "request": request,
        "menus": menus,
        "selected": selected,
        "saved": saved,
        "settings": settings,
        "active_menu_name": config.get_active_menu_name(),
    })


@router.get("/menus/editor")
async def menus_editor(request: Request, menu_file: str = "", menu_name: str = "", error: str = ""):
    items = []
    loaded_file = ""
    printer_names = config.get_printer_names()
    if menu_file:
        path = menu_module.menu_path(menu_file)
        if path and os.path.exists(path):
            try:
                items = menu_module.load_menu(path)
                loaded_file = os.path.basename(path)
                if not menu_name:
                    menu_name = os.path.splitext(loaded_file)[0]
            except Exception:
                error = "Die ausgewählte Menüdatei konnte nicht geladen werden."
        else:
            return RedirectResponse("/menus", status_code=303)
    return templates.TemplateResponse("menu_editor.html", {
        "request": request,
        "items": items,
        "menu_name": menu_name,
        "loaded_file": loaded_file,
        "error": error,
        "printer_names": printer_names,
    })


@router.post("/menus/save")
async def menus_save(
    menu_name: str = Form(""),
    items_json: str = Form(""),
    loaded_file: str = Form(""),
):
    import json
    menu_name = menu_name.strip()
    if not menu_name:
        return RedirectResponse(f"/menus/editor?menu_file={loaded_file}&error=Bitte+einen+Menü-Namen+angeben.", status_code=303)

    safe_name = menu_module.secure_name(menu_name)
    if not safe_name:
        return RedirectResponse(f"/menus/editor?menu_file={loaded_file}&error=Ungültiger+Menü-Name.", status_code=303)
    if not safe_name.lower().endswith(".json"):
        safe_name += ".json"

    path = menu_module.menu_path(safe_name)
    if not path:
        return RedirectResponse(f"/menus/editor?menu_file={loaded_file}&error=Ungültiger+Dateiname.", status_code=303)

    try:
        raw = json.loads(items_json) if items_json.strip() else []
    except Exception:
        return RedirectResponse(f"/menus/editor?menu_file={loaded_file}&error=Menüdaten+ungültig.", status_code=303)

    items = [menu_module.normalize_item(it, i + 1) for i, it in enumerate(raw) if isinstance(it, dict) and it.get("name")]
    if not items:
        return RedirectResponse(f"/menus/editor?menu_file={loaded_file}&error=Mindestens+ein+Item+mit+Namen+erforderlich.", status_code=303)

    os.makedirs(MENU_DIR, exist_ok=True)
    menu_module.save_menu(path, items)
    return RedirectResponse(f"/menus?selected={os.path.splitext(safe_name)[0]}&saved={safe_name}", status_code=303)


@router.post("/menus/select")
async def menus_select(menu_file: str = Form("")):
    if not menu_file:
        return RedirectResponse("/menus", status_code=303)
    menu_path = os.path.join(MENU_DIR, menu_file)
    config.set_active_menu_path(menu_path)
    menu_name = os.path.splitext(menu_file)[0]
    return RedirectResponse(f"/menus?selected={menu_name}", status_code=303)


@router.post("/menus/delete")
async def menus_delete(menu_file: str = Form("")):
    if not menu_file:
        return RedirectResponse("/menus", status_code=303)
    try:
        menu_module.soft_delete(menu_file)
    except FileNotFoundError:
        pass
    return RedirectResponse("/menus", status_code=303)


@router.post("/menus/upload")
async def menus_upload(
    request: Request,
    replace: str = Form(""),
    filename: str = Form(""),
    menu_file: UploadFile = None,
):
    os.makedirs(MENU_DIR, exist_ok=True)

    if replace in ("1", "2") and filename:
        safe = menu_module.secure_name(filename)
        dest = os.path.join(MENU_DIR, safe)
        tmp = dest + ".upload"
        if replace == "1":
            if os.path.exists(tmp):
                os.replace(tmp, dest)
            return RedirectResponse(f"/menus?selected={os.path.splitext(safe)[0]}", status_code=303)
        else:
            if os.path.exists(tmp):
                os.remove(tmp)
            return RedirectResponse("/menus", status_code=303)

    if not menu_file or not menu_file.filename:
        return RedirectResponse("/menus", status_code=303)

    safe = menu_module.secure_name(menu_file.filename)
    if not safe.lower().endswith(".json"):
        from fastapi.responses import Response
        return Response("Nur .json Dateien erlaubt", status_code=400)

    dest = os.path.join(MENU_DIR, safe)
    content = await menu_file.read()

    if os.path.exists(dest):
        tmp = dest + ".upload"
        with open(tmp, "wb") as f:
            f.write(content)
        return templates.TemplateResponse("menu_upload_confirm.html", {
            "request": request,
            "filename": safe,
        })

    with open(dest, "wb") as f:
        f.write(content)
    return RedirectResponse(f"/menus?selected={os.path.splitext(safe)[0]}", status_code=303)
```

- [ ] **Step 2: Commit**

```bash
git add routers/menus.py
git commit -m "feat: add menu management routes with dynamic printer name support"
```

---

## Task 11: routers/settings.py and routers/reports.py

**Files:** `routers/settings.py`, `routers/reports.py`

- [ ] **Step 1: Create `routers/settings.py`**

```python
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import config

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SETTING_KEYS = ["print_customer_double", "print_extra_order_nr", "kitchen_buzzer"]


@router.get("/settings")
async def settings_view(request: Request):
    settings = config.load_settings()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
    })


@router.post("/settings")
async def settings_update(request: Request):
    form = await request.form()
    settings = {key: (form.get(key) == "on") for key in SETTING_KEYS}
    config.save_settings(settings)
    return RedirectResponse("/settings", status_code=303)
```

- [ ] **Step 2: Create `routers/reports.py`**

```python
from datetime import date, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import config
import db
import printing.manager as pm

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _today_range() -> tuple[str, str]:
    today = date.today().isoformat()
    return f"{today}T00:00:00", f"{today}T23:59:59"


@router.get("/reports")
async def reports_view(request: Request, from_dt: str = "", to_dt: str = ""):
    if not from_dt or not to_dt:
        from_dt, to_dt = _today_range()
    data = db.aggregate_orders(from_dt, to_dt)
    orders = db.get_orders(from_dt, to_dt)
    return templates.TemplateResponse("reports.html", {
        "request": request,
        "data": data,
        "orders": orders,
        "from_dt": from_dt,
        "to_dt": to_dt,
    })


@router.get("/api/reports")
async def api_reports(from_dt: str = "", to_dt: str = ""):
    if not from_dt or not to_dt:
        from_dt, to_dt = _today_range()
    return JSONResponse(db.aggregate_orders(from_dt, to_dt))


@router.post("/reports/print")
async def reports_print(from_dt: str = Form(""), to_dt: str = Form("")):
    if not from_dt or not to_dt:
        from_dt, to_dt = _today_range()
    data = db.aggregate_orders(from_dt, to_dt)
    managers = pm.get_managers()
    customer_mgr = managers.get("customer") or (next(iter(managers.values()), None))
    if customer_mgr:
        customer_mgr.enqueue("report", {"data": data})
    return RedirectResponse("/reports", status_code=303)
```

- [ ] **Step 3: Commit**

```bash
git add routers/settings.py routers/reports.py
git commit -m "feat: add settings and reports routes"
```

---

## Task 12: Verify app starts

- [ ] **Step 1: Check all imports resolve**

```bash
uv run python -c "import app; print('OK')"
```

Expected: `OK` (templates don't exist yet but imports should resolve)

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest -v
```

Expected: all existing tests still pass.

---

## Task 13: Templates — base.html and index.html

**Files:** `templates/base.html`, `templates/index.html`

- [ ] **Step 1: Replace `templates/base.html`** (create if missing)

```html
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}KitchenHelper{% endblock %}</title>
  <link rel="stylesheet" href="/static/theme.css">
  {% block head %}{% endblock %}
</head>
<body>
  {% block body %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Replace `templates/index.html`**

Keep the existing JS logic exactly — it works well. Only change: the form action and the `url_for` calls.

```html
{% extends "base.html" %}
{% block title %}{{ menu_name }}{% endblock %}
{% block head %}
<style>
  .layout{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:14px;align-items:start}
  .menu-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
  .dish-btn{min-height:72px;padding:12px;border:1px solid #b7c1d6;border-radius:12px;font-size:16px;font-weight:650;display:flex;align-items:center;justify-content:center;text-align:center;background:#fff;touch-action:manipulation}
  .dish-btn.selected-dish{box-shadow:inset 0 0 0 3px #1f7a1f,0 8px 18px rgba(0,0,0,0.12);transform:translateY(-1px)}
  .config-panel{position:sticky;top:12px}
  #selected-area h3{margin:0 0 6px 0}
  #selected-area{display:none}
  .extras-wrap{display:flex;flex-wrap:wrap;gap:6px}
  .extra-btn{min-height:42px;padding:8px 10px;border-radius:999px;border:1px solid #b8c2d8;background:#eef1f8;font-size:15px}
  .extra-btn.selected{background:#1f7a1f;color:#fff;border-color:#1f7a1f}
  .qty-row{display:flex;align-items:center;gap:8px}
  #selected-area #sel-extras{margin-top:6px}
  #selected-area .qty-row{margin-top:10px}
  #selected-area .actions-row{margin-top:10px}
  .qty-val{font-size:18px;min-width:24px;text-align:center}
  #cart-items{display:flex;flex-direction:column;gap:8px}
  .cart-item{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;padding:10px;border:1px solid #e2e8f4;border-radius:10px;background:#fafcff}
  .cart-text{font-size:15px;line-height:1.35}
  .cart-actions{display:flex;gap:6px}
  .small-btn{min-height:38px;padding:6px 10px;font-size:15px}
  .actions-row{display:flex;gap:8px;flex-wrap:wrap}
  #notes{margin-top:4px}
  #toast-container{pointer-events:none}
  .toast-message{pointer-events:auto}
  @media(max-width:980px){.layout{grid-template-columns:1fr}.config-panel{position:static}}
</style>
{% endblock %}
{% block body %}
<div class="wrap stack">
  <header class="topbar">
    <h1>{{ menu_name }}</h1>
    <div class="actions-row">
      <a href="/menus" class="btn">Speisekarten Auswahl</a>
      <a href="/orders" class="btn">Bestellungen</a>
    </div>
  </header>
  <div class="layout">
    <section class="card stack">
      <div id="menu-grid" class="menu-grid">
        {% for it in menu %}
        <button class="dish-btn" data-name="{{ it.name }}" data-extras='{{ it.extras|tojson }}'
          {% if it.bg_color %}style="background:{{ it.bg_color }};"{% endif %}>
          {{ it.name }}
        </button>
        {% endfor %}
      </div>
    </section>
    <aside id="config-panel" class="stack config-panel">
      <section id="selected-area" class="card stack">
        <h3 id="sel-name"></h3>
        <div id="sel-extras" class="extras-wrap"></div>
        <div class="qty-row">
          <span>Menge:</span>
          <button id="qty-decr" class="btn small-btn" type="button">−</button>
          <span id="qty" class="qty-val">1</span>
          <button id="qty-incr" class="btn small-btn" type="button">+</button>
        </div>
        <div class="actions-row">
          <button id="add-to-cart" class="btn primary" type="button">Zum Bestellkorb hinzufügen</button>
          <button id="cancel-item" class="btn" type="button">Abbrechen</button>
        </div>
      </section>
      <section id="cart" class="card stack">
        <h3>Aktueller Bestellkorb</h3>
        <div id="cart-items"></div>
        <div>
          <label for="notes">Bestell-Notiz (optional)</label>
          <input id="notes" placeholder="z. B. ohne Zwiebeln">
        </div>
        <div class="actions-row">
          <button id="send-order" class="btn secondary" type="button">Bestellung absenden</button>
        </div>
      </section>
    </aside>
  </div>
</div>
<div id="toast-container" aria-live="polite" style="position:fixed;left:50%;transform:translateX(-50%);bottom:18px;z-index:9999"></div>
<script>
  const menu = {{ menu|tojson }};
  const menuGrid = document.getElementById('menu-grid');
  const selectedArea = document.getElementById('selected-area');
  const selName = document.getElementById('sel-name');
  const selExtras = document.getElementById('sel-extras');
  const qtyEl = document.getElementById('qty');
  const addToCartBtn = document.getElementById('add-to-cart');
  const cancelItemBtn = document.getElementById('cancel-item');
  const cartItemsDiv = document.getElementById('cart-items');
  const notesInput = document.getElementById('notes');
  let current = null;
  let cart = [];

  function showSelected(name, extras){
    current = {name, extras: extras||[], qty:1};
    selName.textContent = name;
    selExtras.innerHTML = '';
    (extras||[]).forEach(e=>{
      const btn=document.createElement('button');
      btn.type='button';btn.className='extra-btn';btn.dataset.value=e;btn.textContent=e;
      btn.addEventListener('click',()=>btn.classList.toggle('selected'));
      selExtras.appendChild(btn);
    });
    qtyEl.textContent='1';
    selectedArea.style.display='block';
  }

  menuGrid.addEventListener('click',ev=>{
    const btn=ev.target.closest('.dish-btn');
    if(!btn)return;
    showSelected(btn.dataset.name,JSON.parse(btn.dataset.extras||'[]'));
    document.querySelectorAll('.dish-btn').forEach(b=>b.classList.remove('selected-dish'));
    btn.classList.add('selected-dish');
    setContrastForTiles();
  });

  document.getElementById('qty-incr').addEventListener('click',()=>{if(current){current.qty++;qtyEl.textContent=String(current.qty);}});
  document.getElementById('qty-decr').addEventListener('click',()=>{if(current&&current.qty>1){current.qty--;qtyEl.textContent=String(current.qty);}});

  cancelItemBtn.addEventListener('click',()=>{
    selectedArea.style.display='none';current=null;
    document.querySelectorAll('.dish-btn').forEach(b=>b.classList.remove('selected-dish'));
    setContrastForTiles();
  });

  function sameExtras(a,b){a=a||[];b=b||[];if(a.length!==b.length)return false;return a.slice().sort().join('|')===b.slice().sort().join('|');}

  function renderCart(){
    cartItemsDiv.innerHTML='';
    if(!cart.length){cartItemsDiv.innerHTML='<div class="muted">(leer)</div>';return;}
    cart.forEach((it,idx)=>{
      const d=document.createElement('div');d.className='cart-item';
      const txt=document.createElement('div');txt.className='cart-text';
      txt.textContent=(it.qty>1?it.qty+'x ':'')+it.name+(it.extras&&it.extras.length?' ('+it.extras.join(', ')+')':'');
      d.appendChild(txt);
      const actions=document.createElement('div');actions.className='cart-actions';
      const rem=document.createElement('button');rem.type='button';rem.className='btn small-btn';rem.textContent='−';
      rem.addEventListener('click',()=>{if(it.qty>1)it.qty--;else cart.splice(idx,1);renderCart();});
      const add=document.createElement('button');add.type='button';add.className='btn small-btn';add.textContent='+';
      add.addEventListener('click',()=>{it.qty++;renderCart();});
      actions.appendChild(rem);actions.appendChild(add);d.appendChild(actions);
      cartItemsDiv.appendChild(d);
    });
  }

  addToCartBtn.addEventListener('click',()=>{
    if(!current)return;
    const chosen=Array.from(selExtras.querySelectorAll('.extra-btn.selected')).map(b=>b.dataset.value);
    const found=cart.find(c=>c.name===current.name&&sameExtras(c.extras,chosen));
    if(found)found.qty+=current.qty;else cart.push({name:current.name,extras:chosen,qty:current.qty});
    selectedArea.style.display='none';current=null;
    document.querySelectorAll('.dish-btn').forEach(b=>b.classList.remove('selected-dish'));
    setContrastForTiles();renderCart();
  });

  function showToast(msg,type){
    const c=document.getElementById('toast-container');
    const el=document.createElement('div');el.className='toast-message';
    el.style.cssText=`background:${type==='error'?'#ffefef':'#1f2430'};color:${type==='error'?'#7c1111':'#fff'};border:1px solid ${type==='error'?'#f3bcbc':'#2f3b4f'};padding:10px 14px;border-radius:10px;box-shadow:0 4px 14px rgba(0,0,0,0.16);margin-top:8px;min-width:220px;text-align:center`;
    el.textContent=msg;c.appendChild(el);
    setTimeout(()=>{el.style.transition='opacity 250ms';el.style.opacity='0';setTimeout(()=>el.remove(),260);},2600);
  }

  document.getElementById('send-order').addEventListener('click',async()=>{
    if(!cart.length){showToast('Der Bestellkorb ist leer','error');return;}
    const formData=new FormData();
    formData.append('items',JSON.stringify(cart.map(c=>({name:c.name,extras:c.extras,qty:c.qty}))));
    formData.append('notes',notesInput.value||'');
    try{
      const resp=await fetch('/order',{method:'POST',body:formData,headers:{'X-Requested-With':'XMLHttpRequest','Accept':'application/json'}});
      if(resp.ok){
        const data=await resp.json();
        cart=[];notesInput.value='';renderCart();
        showToast('Bestellung aufgenommen (Nr. '+(data.order_number||'?')+')');
      }else{showToast('Fehler beim Absenden','error');}
    }catch(e){showToast('Netzwerkfehler','error');}
  });

  function parseRgb(v){const m=v.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);return m?[+m[1],+m[2],+m[3]]:null;}
  function hexToRgb(h){h=h.replace('#','');if(h.length===3)h=h.split('').map(x=>x+x).join('');const n=parseInt(h,16);return[(n>>16)&255,(n>>8)&255,n&255];}
  function luminance(r,g,b){return 0.2126*c(r)+0.7152*c(g)+0.0722*c(b);function c(v){v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);}}
  function contrastRatio(l1,l2){const a=Math.max(l1,l2),b=Math.min(l1,l2);return(a+0.05)/(b+0.05);}
  function setContrastForTiles(){
    document.querySelectorAll('.dish-btn').forEach(btn=>{
      const s=getComputedStyle(btn);let rgb=parseRgb(s.backgroundColor);
      if(!rgb){const m=(btn.getAttribute('style')||'').match(/background:\s*([^;]+)/i);if(m&&m[1].trim().startsWith('#'))rgb=hexToRgb(m[1].trim());}
      if(rgb){const lum=luminance(...rgb);const cw=contrastRatio(1,lum),cb=contrastRatio(lum,0);btn.style.color=cw>=cb?'#fff':'#000';}
    });
  }

  renderCart();setContrastForTiles();
</script>
{% endblock %}
```

- [ ] **Step 3: Commit**

```bash
git add templates/base.html templates/index.html
git commit -m "feat: add base template and order taking UI"
```

---

## Task 14: Templates — kitchen_display.html and customer_display.html

**Files:** `templates/kitchen_display.html`, `templates/customer_display.html`

- [ ] **Step 1: Replace `templates/kitchen_display.html`**

Keep existing JS polling logic. Add dynamic kitchen selector from server-provided `kitchen_printers`.

```html
{% extends "base.html" %}
{% block title %}Küchendisplay{% endblock %}
{% block head %}
<style>
  html,body{height:100%}body{margin:0}
  .screen{min-height:100vh;display:flex;flex-direction:column;padding:14px}
  .topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
  .title{font-size:clamp(32px,5vw,42px);margin:0}
  .title a{color:inherit;text-decoration:none}
  .header-actions{display:flex;gap:8px;align-items:center}
  .grid-wrap{flex:1;min-height:0}
  .grid{height:100%;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));grid-auto-rows:max-content;gap:12px}
  .order{border-radius:14px;border:1px solid #d7dfef;background:#fff;padding:16px;cursor:pointer}
  .order.single-item{background-color:#ffb799}
  .order-header{font-size:18px;font-weight:bold;margin-bottom:10px}
  .order-items{list-style:none;padding:0;margin:0}
  .order-item{margin-bottom:8px}
  .item-name{font-weight:bold}
  .item-extras{list-style:none;padding-left:20px;margin:0}
  .order-notes{margin-top:10px;font-style:italic;color:red;font-weight:bold}
  .empty{grid-column:1/-1;font-size:24px;font-weight:500;color:#556173;background:#f8fbff;text-align:center;padding:20px}
  .dialog-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center}
  .dialog{background:#fff;padding:20px;border-radius:10px;text-align:center}
  .dialog-buttons{margin-top:20px}
  #confirm-button{border:2px solid green}
  #cancel-button{border:2px solid red}
  #kitchen-selector{padding:6px;border-radius:6px}
  @media(max-width:700px){.screen{padding:10px}.topbar{flex-direction:column;gap:10px}.title{text-align:center}.header-actions{justify-content:center}.grid{gap:10px}}
</style>
{% endblock %}
{% block body %}
<div class="screen">
  <header class="topbar">
    <h1 class="title"><a href="/orders">Küchendisplay</a></h1>
    <div class="header-actions">
      <a href="/orders" class="btn">Bestellübersicht</a>
      <select id="kitchen-selector">
        <option value="all">Alle</option>
        {% for name in kitchen_printers %}
        <option value="{{ name }}">{{ name }}</option>
        {% endfor %}
      </select>
    </div>
  </header>
  <section class="grid-wrap">
    <div id="order-grid" class="grid"><div class="empty">(Lädt...)</div></div>
  </section>
</div>
<div class="dialog-overlay" id="confirmation-dialog" style="display:none">
  <div class="dialog">
    <p id="dialog-order-id"></p>
    <p>Bestellung als gekocht markieren?</p>
    <div class="dialog-buttons">
      <button id="confirm-button" class="btn">Bestätigen</button>
      <button id="cancel-button" class="btn">Abbrechen</button>
    </div>
  </div>
</div>
<script>
  let orderToCook=null;
  function showConfirmation(id,nr){orderToCook=id;document.getElementById('dialog-order-id').textContent='#'+nr;document.getElementById('confirmation-dialog').style.display='flex';}
  function hideConfirmation(){orderToCook=null;document.getElementById('confirmation-dialog').style.display='none';}
  async function markAsCooked(){
    if(!orderToCook)return;
    try{await fetch('/cooked/'+orderToCook,{method:'POST'});fetchOrders();}catch(e){console.error(e);}finally{hideConfirmation();}
  }
  async function fetchOrders(){
    try{
      const kitchen=document.getElementById('kitchen-selector').value;
      const resp=await fetch('/api/uncooked_orders?kitchen='+kitchen,{headers:{'Accept':'application/json'}});
      if(!resp.ok)return;
      const orders=await resp.json();
      const grid=document.getElementById('order-grid');
      grid.innerHTML='';
      if(!orders.length){grid.innerHTML='<div class="empty">Keine offenen Bestellungen.</div>';return;}
      orders.forEach(o=>{
        const div=document.createElement('div');
        div.className='order'+(o.items.length===1&&o.items[0].qty===1?' single-item':'');
        div.addEventListener('click',()=>showConfirmation(o.id,o.order_number));
        div.innerHTML='<div class="order-header">#'+o.order_number+'</div>';
        const ul=document.createElement('ul');ul.className='order-items';
        o.items.forEach(it=>{
          const li=document.createElement('li');li.className='order-item';
          li.innerHTML='<div class="item-name">'+(it.qty>1?it.qty+'x ':'')+it.name+'</div>';
          if(it.extras&&it.extras.length){const el=document.createElement('ul');el.className='item-extras';it.extras.forEach(e=>{const eli=document.createElement('li');eli.textContent=e;el.appendChild(eli);});li.appendChild(el);}
          ul.appendChild(li);
        });
        div.appendChild(ul);
        if(o.notes){const n=document.createElement('div');n.className='order-notes';n.textContent='Notiz: '+o.notes;div.appendChild(n);}
        grid.appendChild(div);
      });
    }catch(e){console.error(e);}
  }
  document.getElementById('kitchen-selector').addEventListener('change',fetchOrders);
  document.getElementById('confirm-button').addEventListener('click',markAsCooked);
  document.getElementById('cancel-button').addEventListener('click',hideConfirmation);
  fetchOrders();setInterval(fetchOrders,3000);
</script>
{% endblock %}
```

- [ ] **Step 2: Replace `templates/customer_display.html`**

Keep existing JS logic exactly, only change `url_for` references.

```html
{% extends "base.html" %}
{% block title %}Fertige Bestellungen{% endblock %}
{% block head %}
<style>
  html,body{height:100%;margin:0}
  .screen{height:100vh;display:flex;flex-direction:column;padding:14px;box-sizing:border-box}
  .title{font-size:clamp(42px,6vw,72px);text-align:center;margin:0 0 12px}
  .title a{color:inherit;text-decoration:none}
  .grid-wrap{flex:1;min-height:0}
  .grid-container{height:100%;display:grid;gap:12px;grid-auto-flow:column}
  .tile{box-sizing:border-box;border-radius:14px;border:1px solid #d7dfef;background:#fff;padding:16px;display:flex;align-items:center;justify-content:center;font-size:clamp(34px,7vw,76px);font-weight:800;letter-spacing:0.02em;min-height:0}
  .tile.empty{grid-row:1/-1;grid-column:1/-1;font-size:24px;font-weight:500;color:#556173;background:#f8fbff}
  @keyframes highlight{0%{transform:scale(1.04);box-shadow:0 8px 20px rgba(255,153,0,0.2);background:#fff5e8}100%{transform:none;box-shadow:none;background:#fff}}
  .tile.new{animation:highlight 1200ms ease-out;border-color:#f0b469}
</style>
{% endblock %}
{% block body %}
<div class="screen">
  <header><h1 class="title"><a href="/orders">Bereit zur Abholung</a></h1></header>
  <section class="grid-wrap">
    <div id="order-grid" class="grid-container"><div class="tile empty">(Lädt...)</div></div>
  </section>
</div>
<script>
  let prevNums=null,initial=true;
  function updateGridLayout(n){
    const g=document.getElementById('order-grid');
    if(!n){g.style.gridTemplateRows='1fr';g.style.gridTemplateColumns='1fr';return;}
    let cols=1,rows=n;
    if(n>4){cols=2;rows=Math.ceil(n/2);}if(n>8){cols=3;rows=Math.ceil(n/3);}
    g.style.gridTemplateRows='repeat('+rows+',1fr)';
    g.style.gridTemplateColumns='repeat('+cols+',1fr)';
  }
  async function fetchList(){
    try{
      const resp=await fetch('/api/cooked_unfulfilled',{headers:{'Accept':'application/json'}});
      if(!resp.ok)return;
      const data=await resp.json();
      const nums=(data&&data.order_numbers)||[];
      if(JSON.stringify(nums)===JSON.stringify(prevNums)){initial=false;return;}
      const g=document.getElementById('order-grid');g.innerHTML='';
      if(!nums.length){updateGridLayout(0);g.innerHTML='<div class="tile empty">Keine fertigen Bestellungen.</div>';prevNums=nums;initial=false;return;}
      updateGridLayout(nums.length);
      nums.forEach(n=>{
        const t=document.createElement('div');t.className='tile';t.textContent=n;
        if(!initial&&prevNums&&prevNums.indexOf(n)===-1){t.classList.add('new');setTimeout(()=>t.classList.remove('new'),3000);}
        g.appendChild(t);
      });
      prevNums=nums;initial=false;
    }catch(e){console.error(e);}
  }
  fetchList();setInterval(fetchList,3000);
</script>
{% endblock %}
```

- [ ] **Step 3: Commit**

```bash
git add templates/kitchen_display.html templates/customer_display.html
git commit -m "feat: add kitchen and customer display templates"
```

---

## Task 15: Templates — orders.html, settings.html, menu templates

**Files:** `templates/orders.html`, `templates/settings.html`, `templates/menu_selector.html`, `templates/menu_editor.html`, `templates/menu_upload_confirm.html`

- [ ] **Step 1: Replace `templates/orders.html`**

```html
{% extends "base.html" %}
{% block title %}Bestellungen{% endblock %}
{% block body %}
<div class="wrap stack">
  <header class="topbar">
    <h1>Bestellungen</h1>
    <div class="actions-row">
      <a href="/" class="btn">Neue Bestellung</a>
      <a href="/reports" class="btn">Berichte</a>
    </div>
  </header>

  <section class="card stack">
    <form method="get" action="/orders" class="actions-row">
      <label>Von: <input type="datetime-local" name="from_dt" value="{{ from_dt }}"></label>
      <label>Bis: <input type="datetime-local" name="to_dt" value="{{ to_dt }}"></label>
      <button class="btn" type="submit">Filtern</button>
      <a href="/orders" class="btn">Zurücksetzen</a>
    </form>
  </section>

  <section class="card">
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr>
          <th style="text-align:left;padding:8px">Nr.</th>
          <th style="text-align:left;padding:8px">Zeit</th>
          <th style="text-align:left;padding:8px">Drucker</th>
          <th style="text-align:left;padding:8px">Items</th>
          <th style="text-align:left;padding:8px">Notiz</th>
          <th style="text-align:left;padding:8px">Gekocht</th>
          <th style="text-align:left;padding:8px">Abgeholt</th>
          <th style="text-align:left;padding:8px">Aktionen</th>
        </tr>
      </thead>
      <tbody>
        {% for o in orders %}
        <tr style="border-top:1px solid #e2e8f4">
          <td style="padding:8px">{{ o.order_number }}</td>
          <td style="padding:8px">{{ o.created_at }}</td>
          <td style="padding:8px">{{ o.kitchen }}</td>
          <td style="padding:8px">
            {% for it in o.items %}
            {{ it.qty }}x {{ it.name }}{% if it.extras %} ({{ it.extras|join(', ') }}){% endif %}<br>
            {% endfor %}
          </td>
          <td style="padding:8px">{{ o.notes }}</td>
          <td style="padding:8px">{{ o.cooked_at or '—' }}</td>
          <td style="padding:8px">{{ o.fulfilled_at or '—' }}</td>
          <td style="padding:8px">
            <div class="actions-row">
              <a href="/orders/{{ o.order_number }}/export" class="btn small-btn">Export</a>
              <form method="post" action="/orders/{{ o.order_number }}/print_kitchen" style="display:inline">
                <button class="btn small-btn" type="submit">🖨 Küche</button>
              </form>
              <form method="post" action="/orders/{{ o.order_number }}/print_customer" style="display:inline">
                <button class="btn small-btn" type="submit">🖨 Kunde</button>
              </form>
            </div>
          </td>
        </tr>
        {% else %}
        <tr><td colspan="8" style="padding:16px;text-align:center;color:#556173">Keine Bestellungen.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </section>
</div>
{% endblock %}
```

- [ ] **Step 2: Replace `templates/settings.html`**

```html
{% extends "base.html" %}
{% block title %}Einstellungen{% endblock %}
{% block body %}
<div class="wrap stack">
  <header class="topbar">
    <h1>Einstellungen</h1>
    <a href="/" class="btn">Zurück</a>
  </header>
  <section class="card stack">
    <form method="post" action="/settings" class="stack">
      <label style="display:flex;align-items:center;gap:10px">
        <input type="checkbox" name="print_customer_double" {% if settings.get('print_customer_double') %}checked{% endif %}>
        Kundenbon doppelt drucken
      </label>
      <label style="display:flex;align-items:center;gap:10px">
        <input type="checkbox" name="print_extra_order_nr" {% if settings.get('print_extra_order_nr') %}checked{% endif %}>
        Extra-Bestellnummer-Bon drucken
      </label>
      <label style="display:flex;align-items:center;gap:10px">
        <input type="checkbox" name="kitchen_buzzer" {% if settings.get('kitchen_buzzer') %}checked{% endif %}>
        Küchensummer aktivieren
      </label>
      <button class="btn primary" type="submit">Speichern</button>
    </form>
  </section>
</div>
{% endblock %}
```

- [ ] **Step 3: Replace `templates/menu_selector.html`**

```html
{% extends "base.html" %}
{% block title %}Speisekarten{% endblock %}
{% block body %}
<div class="wrap stack">
  <header class="topbar">
    <h1>Speisekarten</h1>
    <div class="actions-row">
      <a href="/" class="btn">Zurück</a>
      <a href="/settings" class="btn">Einstellungen</a>
    </div>
  </header>

  {% if saved %}<div class="card" style="background:#e8f5e9;border-color:#4caf50">„{{ saved }}" gespeichert.</div>{% endif %}
  {% if selected %}<div class="card" style="background:#e3f2fd;border-color:#2196f3">Aktive Speisekarte: <strong>{{ selected }}</strong></div>{% endif %}

  <section class="card stack">
    <h2>Neue Speisekarte hochladen</h2>
    <form method="post" action="/menus/upload" enctype="multipart/form-data" class="actions-row">
      <input type="file" name="menu_file" accept=".json" required>
      <button class="btn primary" type="submit">Hochladen</button>
    </form>
  </section>

  <section class="card stack">
    <h2>Neue Speisekarte erstellen</h2>
    <a href="/menus/editor" class="btn">Neue Speisekarte</a>
  </section>

  <section class="card stack">
    <h2>Vorhandene Speisekarten</h2>
    {% if not menus %}
    <p class="muted">Keine Speisekarten vorhanden.</p>
    {% else %}
    {% for m in menus %}
    <div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #e2e8f4">
      <span style="flex:1;font-weight:{% if m.title == active_menu_name %}bold{% else %}normal{% endif %}">
        {{ m.title }}{% if m.title == active_menu_name %} ✓{% endif %}
      </span>
      <form method="post" action="/menus/select" style="display:inline">
        <input type="hidden" name="menu_file" value="{{ m.file }}">
        <button class="btn small-btn" type="submit">Aktivieren</button>
      </form>
      <a href="/menus/editor?menu_file={{ m.file }}" class="btn small-btn">Bearbeiten</a>
      <form method="post" action="/menus/delete" style="display:inline" onsubmit="return confirm('Löschen?')">
        <input type="hidden" name="menu_file" value="{{ m.file }}">
        <button class="btn small-btn" type="submit" style="color:#c0392b">Löschen</button>
      </form>
    </div>
    {% endfor %}
    {% endif %}
  </section>
</div>
{% endblock %}
```

- [ ] **Step 4: Replace `templates/menu_editor.html`**

```html
{% extends "base.html" %}
{% block title %}Speisekarte bearbeiten{% endblock %}
{% block head %}
<style>
  .item-row{display:flex;gap:8px;align-items:flex-start;padding:10px 0;border-bottom:1px solid #e2e8f4;flex-wrap:wrap}
  .item-row input,.item-row select{padding:6px;border:1px solid #ccc;border-radius:6px;font-size:14px}
  .item-name-input{flex:2;min-width:120px}
  .item-price-input{width:80px}
  .item-printer-select{min-width:100px}
  .item-color-input{width:60px;padding:2px}
  .item-extras-input{flex:3;min-width:160px}
</style>
{% endblock %}
{% block body %}
<div class="wrap stack">
  <header class="topbar">
    <h1>Speisekarte bearbeiten</h1>
    <a href="/menus" class="btn">Zurück</a>
  </header>

  {% if error %}<div class="card" style="background:#ffefef;border-color:#f3bcbc">{{ error }}</div>{% endif %}

  <form method="post" action="/menus/save" class="stack">
    <input type="hidden" name="loaded_file" value="{{ loaded_file }}">
    <section class="card stack">
      <label>Menü-Name:<input type="text" name="menu_name" value="{{ menu_name }}" required style="margin-left:8px;padding:6px;border:1px solid #ccc;border-radius:6px"></label>
    </section>

    <section class="card stack">
      <h2>Items</h2>
      <div id="items-container">
        {% for it in items %}
        <div class="item-row" data-idx="{{ loop.index0 }}">
          <input class="item-name-input" type="text" placeholder="Name" value="{{ it.name }}">
          <input class="item-price-input" type="number" step="0.01" placeholder="Preis" value="{{ it.price }}">
          <select class="item-printer-select">
            <option value="">— kein Drucker —</option>
            {% for p in printer_names %}
            <option value="{{ p }}" {% if it.printer == p %}selected{% endif %}>{{ p }}</option>
            {% endfor %}
          </select>
          <input class="item-color-input" type="color" value="{{ it.bg_color or '#ffffff' }}">
          <input class="item-extras-input" type="text" placeholder="Extras (Komma-getrennt)" value="{{ it.extras|join(', ') }}">
          <button type="button" class="btn small-btn remove-item">✕</button>
        </div>
        {% endfor %}
      </div>
      <button type="button" id="add-item" class="btn">+ Item hinzufügen</button>
    </section>

    <input type="hidden" name="items_json" id="items-json">
    <button type="submit" class="btn primary" onclick="buildJson()">Speichern</button>
  </form>
</div>
<script>
  const printerNames = {{ printer_names|tojson }};

  function buildJson(){
    const rows = document.querySelectorAll('.item-row');
    const items = Array.from(rows).map(r=>{
      const extras = r.querySelector('.item-extras-input').value.split(',').map(e=>e.trim()).filter(Boolean);
      return {
        name: r.querySelector('.item-name-input').value.trim(),
        price: parseFloat(r.querySelector('.item-price-input').value)||0,
        printer: r.querySelector('.item-printer-select').value,
        bg_color: r.querySelector('.item-color-input').value,
        extras,
      };
    }).filter(it=>it.name);
    document.getElementById('items-json').value = JSON.stringify(items);
  }

  function makeRow(it){
    it = it || {name:'',price:0,printer:'',bg_color:'#ffffff',extras:[]};
    const div = document.createElement('div');
    div.className = 'item-row';
    const printerOpts = '<option value="">— kein Drucker —</option>' +
      printerNames.map(p=>'<option value="'+p+'"'+(it.printer===p?' selected':'')+'>'+p+'</option>').join('');
    div.innerHTML = `
      <input class="item-name-input" type="text" placeholder="Name" value="${it.name}">
      <input class="item-price-input" type="number" step="0.01" placeholder="Preis" value="${it.price}">
      <select class="item-printer-select">${printerOpts}</select>
      <input class="item-color-input" type="color" value="${it.bg_color||'#ffffff'}">
      <input class="item-extras-input" type="text" placeholder="Extras (Komma-getrennt)" value="${(it.extras||[]).join(', ')}">
      <button type="button" class="btn small-btn remove-item">✕</button>
    `;
    div.querySelector('.remove-item').addEventListener('click', ()=>div.remove());
    return div;
  }

  document.getElementById('add-item').addEventListener('click', ()=>{
    document.getElementById('items-container').appendChild(makeRow());
  });

  document.querySelectorAll('.remove-item').forEach(btn=>{
    btn.addEventListener('click', ()=>btn.closest('.item-row').remove());
  });
</script>
{% endblock %}
```

- [ ] **Step 5: Replace `templates/menu_upload_confirm.html`**

```html
{% extends "base.html" %}
{% block title %}Datei ersetzen?{% endblock %}
{% block body %}
<div class="wrap stack">
  <header class="topbar"><h1>Datei bereits vorhanden</h1></header>
  <section class="card stack">
    <p>Die Datei <strong>{{ filename }}</strong> existiert bereits. Ersetzen?</p>
    <div class="actions-row">
      <form method="post" action="/menus/upload">
        <input type="hidden" name="replace" value="1">
        <input type="hidden" name="filename" value="{{ filename }}">
        <button class="btn primary" type="submit">Ersetzen</button>
      </form>
      <form method="post" action="/menus/upload">
        <input type="hidden" name="replace" value="2">
        <input type="hidden" name="filename" value="{{ filename }}">
        <button class="btn" type="submit">Abbrechen</button>
      </form>
    </div>
  </section>
</div>
{% endblock %}
```

- [ ] **Step 6: Commit**

```bash
git add templates/orders.html templates/settings.html templates/menu_selector.html templates/menu_editor.html templates/menu_upload_confirm.html
git commit -m "feat: add orders, settings, and menu management templates"
```

---

## Task 16: Template — reports.html

**Files:** `templates/reports.html`

- [ ] **Step 1: Create `templates/reports.html`**

```html
{% extends "base.html" %}
{% block title %}Berichte{% endblock %}
{% block body %}
<div class="wrap stack">
  <header class="topbar">
    <h1>Berichte</h1>
    <a href="/" class="btn">Zurück</a>
  </header>

  <section class="card stack">
    <h2>Zeitraum auswählen</h2>
    <form method="get" action="/reports" class="actions-row" style="flex-wrap:wrap;gap:8px">
      <label>Von: <input type="datetime-local" name="from_dt" value="{{ from_dt }}"></label>
      <label>Bis: <input type="datetime-local" name="to_dt" value="{{ to_dt }}"></label>
      <button class="btn" type="submit">Anzeigen</button>
      <button class="btn" type="button" onclick="setPreset('today')">Heute</button>
      <button class="btn" type="button" onclick="setPreset('yesterday')">Gestern</button>
      <button class="btn" type="button" onclick="setPreset('week')">Diese Woche</button>
    </form>
  </section>

  <section class="card stack">
    <h2>Statistik: {{ data.from }} – {{ data.to }}</h2>
    {% if data.item_map %}
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr>
          <th style="text-align:left;padding:8px">Gericht</th>
          <th style="text-align:left;padding:8px">Anzahl</th>
          <th style="text-align:left;padding:8px">Extras</th>
        </tr>
      </thead>
      <tbody>
        {% for name, info in data.item_map.items() %}
        <tr style="border-top:1px solid #e2e8f4">
          <td style="padding:8px">{{ name }}</td>
          <td style="padding:8px">{{ info.count }}</td>
          <td style="padding:8px">
            {% for ex, qty in info.extras.items() %}{{ qty }}x {{ ex }}{% if not loop.last %}, {% endif %}{% endfor %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p class="muted">Keine Bestellungen im gewählten Zeitraum.</p>
    {% endif %}

    {% if data.extras_total %}
    <h3>Extras gesamt</h3>
    <ul>{% for ex, qty in data.extras_total.items() %}<li>{{ qty }}x {{ ex }}</li>{% endfor %}</ul>
    {% endif %}

    <form method="post" action="/reports/print" style="margin-top:12px">
      <input type="hidden" name="from_dt" value="{{ from_dt }}">
      <input type="hidden" name="to_dt" value="{{ to_dt }}">
      <button class="btn primary" type="submit">Bericht drucken</button>
    </form>
  </section>

  <section class="card stack">
    <h2>Einzelbestellungen im Zeitraum ({{ orders|length }})</h2>
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr>
          <th style="text-align:left;padding:8px">Nr.</th>
          <th style="text-align:left;padding:8px">Zeit</th>
          <th style="text-align:left;padding:8px">Items</th>
          <th style="text-align:left;padding:8px">Notiz</th>
        </tr>
      </thead>
      <tbody>
        {% for o in orders %}
        <tr style="border-top:1px solid #e2e8f4">
          <td style="padding:8px">{{ o.order_number }}</td>
          <td style="padding:8px">{{ o.created_at }}</td>
          <td style="padding:8px">{% for it in o.items %}{{ it.qty }}x {{ it.name }}<br>{% endfor %}</td>
          <td style="padding:8px">{{ o.notes }}</td>
        </tr>
        {% else %}
        <tr><td colspan="4" style="padding:16px;text-align:center;color:#556173">Keine Bestellungen.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </section>
</div>
<script>
  function setPreset(p){
    const now=new Date();
    let from,to;
    if(p==='today'){from=dayStart(now);to=dayEnd(now);}
    else if(p==='yesterday'){const y=new Date(now);y.setDate(y.getDate()-1);from=dayStart(y);to=dayEnd(y);}
    else if(p==='week'){const w=new Date(now);w.setDate(w.getDate()-w.getDay());from=dayStart(w);to=dayEnd(now);}
    document.querySelector('[name=from_dt]').value=toLocal(from);
    document.querySelector('[name=to_dt]').value=toLocal(to);
  }
  function dayStart(d){return new Date(d.getFullYear(),d.getMonth(),d.getDate(),0,0,0);}
  function dayEnd(d){return new Date(d.getFullYear(),d.getMonth(),d.getDate(),23,59,59);}
  function toLocal(d){const pad=n=>String(n).padStart(2,'0');return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'T'+pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds());}
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/reports.html
git commit -m "feat: add reports template with date range picker and print button"
```

---

## Task 17: Dockerfile, docker-compose, and static assets

**Files:** `Dockerfile`, `docker-compose.yml`

- [ ] **Step 1: Replace `Dockerfile`**

```dockerfile
FROM python:3.11-slim

LABEL authors="philipp"

WORKDIR /app

COPY . .

RUN pip install uv
RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Note: uses Python 3.11-slim (smaller image, well-supported on Pi 5). If Pi 5 ARM64 needs 3.14, change the base image tag — but 3.11 is the safest choice for library compatibility with python-escpos.

- [ ] **Step 2: Verify `docker-compose.yml` still works**

The existing `docker-compose.yml` should need no changes. Verify that the port, volume mount, and environment variables still match:

```yaml
services:
  kitchenhelper:
    image: philippbtz/kitchen-helper:latest
    ports:
      - "80:8000"
    volumes:
      - ./kitchen_data:/app/.local
    environment:
      - KITCHENHELPER_PRINTER_MODE=Thermo
      - KITCHENHELPER_PRINTER_DICT={"1":"192.168.1.10","customer":"192.168.1.11"}
```

If the existing file maps port 80 to 80, change the CMD in Dockerfile to `--port 80` or adjust the compose file to `"80:8000"`.

- [ ] **Step 3: Copy static assets from old codebase**

The `static/` directory and `static/icon_beifallers.png` already exist — no action needed. Verify:

```bash
ls static/
```

Expected: `theme.css`, `icon_beifallers.png` (and any other assets) are present.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "chore: switch Dockerfile to uvicorn single-process"
```

---

## Task 18: Smoke test the full app

- [ ] **Step 1: Run the app locally**

```bash
KITCHENHELPER_PRINTER_MODE=Dummy KITCHENHELPER_PRINTER_DICT='{}' uv run uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Expected: starts without errors, logs `QueueManager started` for each printer (empty if dict is `{}`).

- [ ] **Step 2: Check each route loads**

Open in browser:
- `http://localhost:8000/` — order taking page with menu
- `http://localhost:8000/orders` — orders list
- `http://localhost:8000/kitchen_display` — kitchen display
- `http://localhost:8000/customer_display` — customer display
- `http://localhost:8000/menus` — menu selector
- `http://localhost:8000/menus/editor` — empty menu editor
- `http://localhost:8000/settings` — settings toggles
- `http://localhost:8000/reports` — reports with today's date

- [ ] **Step 3: Submit a test order**

On `/`, add an item to the cart and submit. Verify:
- Toast shows order number
- `/orders` shows the new order
- `/api/uncooked_orders` returns the order as JSON

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

---

## Task 19: Delete old files

- [ ] **Step 1: Remove old source files**

```bash
git rm kitchenhelper.py printutil.py printer_service.py menu_utility.py wsgi.py test.py
```

- [ ] **Step 2: Verify app still starts**

```bash
KITCHENHELPER_PRINTER_MODE=Dummy KITCHENHELPER_PRINTER_DICT='{}' uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

Expected: starts cleanly.

- [ ] **Step 3: Run full test suite one final time**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete clean room remake — FastAPI, WAL SQLite, single-process printer, dynamic printer config"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] All routes from spec → Tasks 8–12
- [x] Dynamic printer names in menu editor → Task 10 (`menus_editor` passes `printer_names`), Task 15 (`menu_editor.html` renders dynamic dropdown)
- [x] Custom date range reports → Task 12 (`reports.py`), Task 16 (`reports.html` with preset buttons)
- [x] WAL mode SQLite → Task 3 (`db.py` `_connect()`)
- [x] Single process, no reservation state → Task 6 (`manager.py` has no state=2)
- [x] ISO 8601 timestamps → Task 3 (`datetime.now().isoformat(timespec="seconds")`)
- [x] No overwrite of defaults → Task 2 (`setup_local` checks `os.path.exists`)
- [x] `printed` key always present → Task 3 (`_row_to_order` returns `printed_kitchen`/`printed_customer`)
- [x] Dockerfile → Task 17
- [x] Settings → Task 11

**Type consistency check:**
- `db.save_order` takes a dict and returns a dict with `order_number` added ✓
- `db.get_order_by_number` returns `Optional[dict]` ✓
- `db.toggle_cooked` / `toggle_fulfilled` return `Optional[dict]` ✓
- `QueueManager.enqueue(job, kwargs)` called consistently in manager.py ✓
- `receipts.format_kitchen(printer, order, settings)` — all three args present in `_dispatch` ✓
- `receipts.format_report(printer, data)` — called as `enqueue("report", {"data": data})` → `_dispatch` passes `kwargs["data"]` ✓
- `config.get_printer_names()` used in `displays.py` and `menus.py` ✓
