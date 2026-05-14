import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_local):
    # Import app inside fixture so tmp_local patches env before app module loads
    from app import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_index_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_orders_loads(client):
    resp = client.get("/orders")
    assert resp.status_code == 200


def test_kitchen_display_loads(client):
    resp = client.get("/kitchen_display")
    assert resp.status_code == 200


def test_customer_display_loads(client):
    resp = client.get("/customer_display")
    assert resp.status_code == 200


def test_menus_loads(client):
    resp = client.get("/menus")
    assert resp.status_code == 200


def test_settings_loads(client):
    resp = client.get("/settings")
    assert resp.status_code == 200


def test_reports_loads(client):
    resp = client.get("/reports")
    assert resp.status_code == 200


def test_api_uncooked_orders(client):
    resp = client.get("/api/uncooked_orders")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_api_cooked_unfulfilled(client):
    resp = client.get("/api/cooked_unfulfilled")
    assert resp.status_code == 200
    data = resp.json()
    assert "order_numbers" in data


def test_submit_order(client):
    import json
    items = json.dumps([{"name": "Test", "qty": 1, "extras": [], "printer": "kitchen"}])
    resp = client.post("/order", data={"items": items, "notes": ""}, follow_redirects=False)
    # Returns JSON (XMLHttpRequest header not set) so redirects to /orders
    assert resp.status_code in (200, 303)
