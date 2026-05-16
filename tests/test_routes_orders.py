"""Route tests: order creation, lifecycle (cooked/fulfilled), export, reprint."""
import json
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _submit(client, items, notes=""):
    """POST /order via XHR and return the JSON body."""
    resp = client.post(
        "/order",
        data={"items": json.dumps(items), "notes": notes},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    return resp.json()


BURGER = {"name": "Burger", "qty": 2, "extras": ["Ketchup"], "printer": "kitchen1"}
COLA   = {"name": "Cola",   "qty": 1, "extras": [],          "printer": "customer"}


# ── GET / (index) ─────────────────────────────────────────────────────────────

def test_index_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200


# ── POST /order ───────────────────────────────────────────────────────────────

def test_submit_order_returns_status_ok_and_order_number(client):
    result = _submit(client, [BURGER])
    assert result["status"] == "ok"
    assert result["order_number"] != ""


def test_submit_order_without_xhr_redirects_to_orders(client):
    resp = client.post(
        "/order",
        data={"items": json.dumps([BURGER]), "notes": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/orders"


def test_submit_order_splits_by_printer_creates_two_sub_orders(client):
    """Items for different printers become separate orders in the DB."""
    result = _submit(client, [BURGER, COLA])
    # Two order numbers separated by " + "
    parts = result["order_number"].split(" + ")
    assert len(parts) == 2


def test_submit_order_single_printer_no_split(client):
    extra_burger = {**BURGER, "name": "Fries"}
    result = _submit(client, [BURGER, extra_burger])
    assert "+" not in result["order_number"]


def test_submit_order_empty_items_returns_empty_order_number(client):
    result = _submit(client, [])
    assert result["status"] == "ok"
    assert result["order_number"] == ""


def test_submit_order_invalid_json_treated_as_empty(client):
    resp = client.post(
        "/order",
        data={"items": "NOT_JSON", "notes": ""},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    data = resp.json()
    assert data["status"] == "ok"
    assert data["order_number"] == ""


def test_submitted_order_persists_in_db(client):
    import db
    _submit(client, [BURGER], notes="extra crispy")
    orders = db.get_orders()
    assert len(orders) == 1
    assert orders[0]["notes"] == "extra crispy"
    assert orders[0]["items"][0]["name"] == "Burger"


def test_submit_order_notes_propagate_to_all_sub_orders(client):
    import db
    _submit(client, [BURGER, COLA], notes="table 7")
    for order in db.get_orders():
        assert order["notes"] == "table 7"


def test_submit_order_kitchen_field_set_from_printer(client):
    import db
    _submit(client, [BURGER])
    order = db.get_orders()[0]
    assert order["kitchen"] == "kitchen1"


# ── POST /cooked/{order_id} ───────────────────────────────────────────────────

def test_cooked_toggle_marks_order_cooked(client):
    import db
    _submit(client, [BURGER])
    order = db.get_orders()[0]
    assert order["cooked_at"] is None

    resp = client.post(
        f"/cooked/{order['id']}",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["cooked_at"] is not None


def test_cooked_toggle_twice_unmarks(client):
    import db
    _submit(client, [BURGER])
    oid = db.get_orders()[0]["id"]

    client.post(f"/cooked/{oid}", headers={"X-Requested-With": "XMLHttpRequest"})
    resp = client.post(f"/cooked/{oid}", headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.json()["cooked_at"] is None


def test_cooked_unknown_order_returns_404(client):
    resp = client.post(
        "/cooked/no-such-id",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 404


def test_cooked_without_xhr_redirects(client):
    import db
    _submit(client, [BURGER])
    oid = db.get_orders()[0]["id"]
    resp = client.post(f"/cooked/{oid}", follow_redirects=False)
    assert resp.status_code == 303


# ── POST /fulfilled/{order_id} ────────────────────────────────────────────────

def test_fulfilled_toggle_marks_order_fulfilled(client):
    import db
    _submit(client, [BURGER])
    oid = db.get_orders()[0]["id"]

    resp = client.post(
        f"/fulfilled/{oid}",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["fulfilled_at"] is not None


def test_fulfilled_toggle_twice_unmarks(client):
    import db
    _submit(client, [BURGER])
    oid = db.get_orders()[0]["id"]

    client.post(f"/fulfilled/{oid}", headers={"X-Requested-With": "XMLHttpRequest"})
    resp = client.post(f"/fulfilled/{oid}", headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.json()["fulfilled_at"] is None


def test_fulfilled_unknown_order_returns_404(client):
    resp = client.post(
        "/fulfilled/no-such-id",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 404


# ── GET /orders ────────────────────────────────────────────────────────────────

def test_orders_page_shows_submitted_order_content(client):
    _submit(client, [BURGER], notes="with fries")
    resp = client.get("/orders")
    assert resp.status_code == 200
    assert b"with fries" in resp.content


def test_orders_page_date_filter_excludes_today(client):
    _submit(client, [BURGER])
    resp = client.get("/orders?from_dt=2000-01-01T00:00:00&to_dt=2000-01-01T23:59:59")
    assert resp.status_code == 200
    assert b"Burger" not in resp.content


# ── GET /orders/{order_number}/export ─────────────────────────────────────────

def test_order_export_returns_plain_text_attachment(client):
    import db
    _submit(client, [BURGER], notes="take-away")
    nr = db.get_orders()[0]["order_number"]

    resp = client.get(f"/orders/{nr}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "attachment" in resp.headers["content-disposition"]
    assert f"Bestell-Nr.: {nr}" in resp.text
    assert "Burger" in resp.text
    assert "take-away" in resp.text


def test_order_export_includes_extras(client):
    import db
    _submit(client, [BURGER])  # BURGER has "Ketchup" extra
    nr = db.get_orders()[0]["order_number"]
    resp = client.get(f"/orders/{nr}/export")
    assert "Ketchup" in resp.text


def test_order_export_unknown_returns_404(client):
    resp = client.get("/orders/99999/export")
    assert resp.status_code == 404


# ── POST /orders/{nr}/print_kitchen ───────────────────────────────────────────

def test_reprint_kitchen_resets_print_flag(client):
    import db
    _submit(client, [BURGER])
    nr = db.get_orders()[0]["order_number"]
    db.mark_printed_kitchen(nr)
    assert db.get_order_by_number(nr)["printed_kitchen"] is True

    resp = client.post(f"/orders/{nr}/print_kitchen", follow_redirects=False)
    assert resp.status_code == 303
    assert db.get_order_by_number(nr)["printed_kitchen"] is False


def test_reprint_kitchen_unknown_returns_404(client):
    resp = client.post("/orders/99999/print_kitchen", follow_redirects=False)
    assert resp.status_code == 404


# ── POST /orders/{nr}/print_customer ──────────────────────────────────────────

def test_reprint_customer_resets_print_flag(client):
    import db
    _submit(client, [BURGER])
    nr = db.get_orders()[0]["order_number"]
    db.mark_printed_customer(nr)
    assert db.get_order_by_number(nr)["printed_customer"] is True

    resp = client.post(f"/orders/{nr}/print_customer", follow_redirects=False)
    assert resp.status_code == 303
    assert db.get_order_by_number(nr)["printed_customer"] is False


def test_reprint_customer_unknown_returns_404(client):
    resp = client.post("/orders/99999/print_customer", follow_redirects=False)
    assert resp.status_code == 404