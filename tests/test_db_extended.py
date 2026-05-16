"""Additional DB layer tests: edge cases, error handling, and missing coverage."""
import sqlite3
import uuid
import pytest
import config
import db


def _order(**kw):
    base = {
        "id": str(uuid.uuid4()),
        "customer_id": str(uuid.uuid4()),
        "kitchen": "kitchen1",
        "items": [{"name": "Burger", "qty": 1, "extras": []}],
        "notes": "",
        "created_at": "2026-05-10T12:00:00",
    }
    base.update(kw)
    return base


# ── lookup helpers ─────────────────────────────────────────────────────────────

def test_get_order_by_id(tmp_local):
    db.init_db()
    saved = db.save_order(_order(id="find-me"))
    fetched = db.get_order_by_id("find-me")
    assert fetched is not None
    assert fetched["order_number"] == saved["order_number"]


def test_get_order_by_id_missing_returns_none(tmp_local):
    db.init_db()
    assert db.get_order_by_id("no-such-id") is None


def test_get_order_by_number_missing_returns_none(tmp_local):
    db.init_db()
    assert db.get_order_by_number(99999) is None


# ── date filtering ─────────────────────────────────────────────────────────────

def test_get_orders_date_filter_excludes_out_of_range(tmp_local):
    db.init_db()
    db.save_order(_order(id="old", created_at="2024-01-01T12:00:00"))
    db.save_order(_order(id="new", created_at="2026-05-10T12:00:00"))
    result = db.get_orders("2026-05-10T00:00:00", "2026-05-10T23:59:59")
    assert len(result) == 1
    assert result[0]["id"] == "new"


def test_get_orders_no_filter_returns_all(tmp_local):
    db.init_db()
    db.save_order(_order(id="a", created_at="2024-01-01T12:00:00"))
    db.save_order(_order(id="b", created_at="2026-05-10T12:00:00"))
    assert len(db.get_orders()) == 2


def test_get_orders_ordered_descending(tmp_local):
    db.init_db()
    db.save_order(_order(id="first",  created_at="2026-05-10T10:00:00"))
    db.save_order(_order(id="second", created_at="2026-05-10T11:00:00"))
    orders = db.get_orders()
    assert orders[0]["id"] == "second"
    assert orders[1]["id"] == "first"


# ── cooked / fulfilled lifecycle ───────────────────────────────────────────────

def test_get_cooked_unfulfilled_lifecycle(tmp_local):
    db.init_db()
    o = db.save_order(_order())
    assert o["order_number"] not in db.get_cooked_unfulfilled()
    db.toggle_cooked(o["id"])
    assert o["order_number"] in db.get_cooked_unfulfilled()
    db.toggle_fulfilled(o["id"])
    assert o["order_number"] not in db.get_cooked_unfulfilled()


def test_toggle_cooked_unknown_id_returns_none(tmp_local):
    db.init_db()
    assert db.toggle_cooked("no-such-id") is None


def test_toggle_fulfilled_unknown_id_returns_none(tmp_local):
    db.init_db()
    assert db.toggle_fulfilled("no-such-id") is None


# ── print status ──────────────────────────────────────────────────────────────

def test_reset_printed_kitchen_clears_flag(tmp_local):
    db.init_db()
    o = db.save_order(_order())
    db.mark_printed_kitchen(o["order_number"])
    assert db.get_order_by_number(o["order_number"])["printed_kitchen"] is True
    db.reset_printed_kitchen(o["order_number"])
    assert db.get_order_by_number(o["order_number"])["printed_kitchen"] is False


def test_reset_printed_customer_clears_flag(tmp_local):
    db.init_db()
    o = db.save_order(_order())
    db.mark_printed_customer(o["order_number"])
    assert db.get_order_by_number(o["order_number"])["printed_customer"] is True
    db.reset_printed_customer(o["order_number"])
    assert db.get_order_by_number(o["order_number"])["printed_customer"] is False


def test_get_unprinted_kitchen_respects_printer_name(tmp_local):
    db.init_db()
    db.save_order(_order(id="k1", kitchen="kitchen1"))
    db.save_order(_order(id="k2", kitchen="kitchen2"))
    assert len(db.get_unprinted_kitchen("kitchen1")) == 1
    assert len(db.get_unprinted_kitchen("kitchen2")) == 1
    assert db.get_unprinted_kitchen("kitchen3") == []


# ── corrupt data resilience ────────────────────────────────────────────────────

def test_row_to_order_handles_corrupt_items_json(tmp_local):
    db.init_db()
    o = db.save_order(_order())
    conn = sqlite3.connect(config.get_db_path())
    conn.execute(
        "UPDATE orders SET items = ? WHERE order_number = ?",
        ("NOT_VALID_JSON", o["order_number"]),
    )
    conn.commit()
    conn.close()
    fetched = db.get_order_by_number(o["order_number"])
    assert fetched["items"] == []


def test_aggregate_orders_skips_corrupt_items_rows(tmp_local):
    db.init_db()
    db.save_order(_order(id="corrupt", created_at="2026-05-10T12:00:00"))
    conn = sqlite3.connect(config.get_db_path())
    conn.execute("UPDATE orders SET items = 'BAD' WHERE id = 'corrupt'")
    conn.commit()
    conn.close()
    result = db.aggregate_orders("2026-05-10T00:00:00", "2026-05-10T23:59:59")
    assert result["item_map"] == {}


# ── aggregate details ─────────────────────────────────────────────────────────

def test_aggregate_orders_sums_quantities(tmp_local):
    db.init_db()
    items = [{"name": "Pizza", "qty": 3, "extras": ["Sauce"]}]
    db.save_order(_order(items=items, created_at="2026-05-10T12:00:00"))
    db.save_order(_order(items=items, created_at="2026-05-10T13:00:00"))
    result = db.aggregate_orders("2026-05-10T00:00:00", "2026-05-10T23:59:59")
    assert result["item_map"]["Pizza"]["count"] == 6
    assert result["extras_total"]["Sauce"] == 6
