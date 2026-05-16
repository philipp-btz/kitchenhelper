"""Route tests: kitchen/customer display pages and their polling JSON APIs."""
import json
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _submit(client, items, notes=""):
    resp = client.post(
        "/order",
        data={"items": json.dumps(items), "notes": notes},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    return resp.json()


BURGER = {"name": "Burger", "qty": 1, "extras": [],    "printer": "kitchen1"}
DRINK  = {"name": "Cola",   "qty": 1, "extras": [],    "printer": "customer"}


# ── display pages ──────────────────────────────────────────────────────────────

def test_kitchen_display_page_renders(client):
    resp = client.get("/kitchen_display")
    assert resp.status_code == 200


def test_customer_display_page_renders(client):
    resp = client.get("/customer_display")
    assert resp.status_code == 200


# ── GET /api/uncooked_orders ───────────────────────────────────────────────────

def test_api_uncooked_orders_empty_initially(client):
    resp = client.get("/api/uncooked_orders")
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_uncooked_orders_contains_submitted_order(client):
    _submit(client, [BURGER])
    orders = client.get("/api/uncooked_orders").json()
    assert len(orders) == 1
    assert orders[0]["items"][0]["name"] == "Burger"


def test_api_uncooked_orders_filters_by_kitchen(client):
    _submit(client, [BURGER, DRINK])
    k1 = client.get("/api/uncooked_orders?kitchen=kitchen1").json()
    assert all(o["kitchen"] == "kitchen1" for o in k1)
    cust = client.get("/api/uncooked_orders?kitchen=customer").json()
    assert all(o["kitchen"] == "customer" for o in cust)


def test_api_uncooked_orders_all_returns_all_kitchens(client):
    _submit(client, [BURGER, DRINK])
    orders = client.get("/api/uncooked_orders?kitchen=all").json()
    assert len(orders) == 2


def test_api_uncooked_orders_excludes_cooked(client):
    import db
    _submit(client, [BURGER])
    db.toggle_cooked(db.get_orders()[0]["id"])
    assert client.get("/api/uncooked_orders").json() == []


def test_api_uncooked_orders_items_preserve_extras(client):
    item = {"name": "Burger", "qty": 1, "extras": ["Ketchup", "Sauce"], "printer": "kitchen1"}
    _submit(client, [item])
    orders = client.get("/api/uncooked_orders").json()
    assert orders[0]["items"][0]["extras"] == ["Ketchup", "Sauce"]


# ── GET /api/cooked_unfulfilled ────────────────────────────────────────────────

def test_api_cooked_unfulfilled_empty_initially(client):
    resp = client.get("/api/cooked_unfulfilled")
    assert resp.status_code == 200
    assert resp.json() == {"order_numbers": []}


def test_api_cooked_unfulfilled_returns_cooked_order_numbers(client):
    import db
    _submit(client, [BURGER])
    order = db.get_orders()[0]
    db.toggle_cooked(order["id"])

    nums = client.get("/api/cooked_unfulfilled").json()["order_numbers"]
    assert order["order_number"] in nums


def test_api_cooked_unfulfilled_excludes_fulfilled_orders(client):
    import db
    _submit(client, [BURGER])
    order = db.get_orders()[0]
    db.toggle_cooked(order["id"])
    db.toggle_fulfilled(order["id"])

    assert client.get("/api/cooked_unfulfilled").json()["order_numbers"] == []


def test_api_cooked_unfulfilled_excludes_uncooked_orders(client):
    _submit(client, [BURGER])
    assert client.get("/api/cooked_unfulfilled").json()["order_numbers"] == []


def test_api_cooked_unfulfilled_order_is_ascending(client):
    import db
    _submit(client, [BURGER])
    _submit(client, [DRINK])
    for order in db.get_orders():
        db.toggle_cooked(order["id"])

    nums = client.get("/api/cooked_unfulfilled").json()["order_numbers"]
    assert nums == sorted(nums)