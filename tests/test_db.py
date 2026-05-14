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
