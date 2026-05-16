"""Route tests: reports page, reports API, and print trigger."""
import json
import pytest


def _submit(client, items):
    client.post(
        "/order",
        data={"items": json.dumps(items), "notes": ""},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )


BURGER = {"name": "Burger", "qty": 2, "extras": ["Ketchup"], "printer": "kitchen1"}


# ── GET /reports ───────────────────────────────────────────────────────────────

def test_reports_page_renders(client):
    assert client.get("/reports").status_code == 200


def test_reports_page_with_custom_date_range(client):
    assert client.get(
        "/reports?from_dt=2026-05-01T00:00:00&to_dt=2026-05-01T23:59:59"
    ).status_code == 200


# ── GET /api/reports ──────────────────────────────────────────────────────────

def test_api_reports_returns_json_structure(client):
    resp = client.get("/api/reports")
    assert resp.status_code == 200
    data = resp.json()
    assert "item_map" in data
    assert "extras_total" in data
    assert "from" in data
    assert "to" in data


def test_api_reports_aggregates_todays_orders(client):
    import db
    _submit(client, [BURGER])
    order = db.get_orders()[0]
    day = order["created_at"][:10]

    resp = client.get(
        f"/api/reports?from_dt={day}T00:00:00&to_dt={day}T23:59:59"
    )
    data = resp.json()
    assert "Burger" in data["item_map"]
    assert data["item_map"]["Burger"]["count"] == 2
    assert data["extras_total"]["Ketchup"] == 2


def test_api_reports_empty_for_past_date(client):
    _submit(client, [BURGER])
    data = client.get(
        "/api/reports?from_dt=2000-01-01T00:00:00&to_dt=2000-01-01T23:59:59"
    ).json()
    assert data["item_map"] == {}


def test_api_reports_no_params_defaults_to_today(client):
    resp = client.get("/api/reports")
    data = resp.json()
    # Both from/to should be present and non-empty
    assert data["from"] != ""
    assert data["to"] != ""


# ── POST /reports/print ───────────────────────────────────────────────────────

def test_reports_print_redirects_to_reports(client):
    resp = client.post("/reports/print", data={}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/reports"


def test_reports_print_with_date_range_redirects(client):
    resp = client.post(
        "/reports/print",
        data={"from_dt": "2026-05-01T00:00:00", "to_dt": "2026-05-01T23:59:59"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
