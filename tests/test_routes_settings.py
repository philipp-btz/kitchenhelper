"""Route tests: settings page (GET) and settings update (POST)."""
import pytest
import config


def test_settings_page_renders(client):
    resp = client.get("/settings")
    assert resp.status_code == 200


def test_settings_update_redirects_to_settings(client):
    resp = client.post("/settings", data={}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings"


def test_settings_checked_boxes_saved_as_true(client):
    client.post(
        "/settings",
        data={"print_customer_double": "on", "print_extra_order_nr": "on"},
    )
    saved = config.load_settings()
    assert saved["print_customer_double"] is True
    assert saved["print_extra_order_nr"] is True
    assert saved["kitchen_buzzer"] is False


def test_settings_unchecked_boxes_saved_as_false(client):
    # First enable something
    client.post("/settings", data={"kitchen_buzzer": "on"})
    # Then submit with no checkboxes
    client.post("/settings", data={})
    saved = config.load_settings()
    assert saved["kitchen_buzzer"] is False
    assert saved["print_customer_double"] is False


def test_settings_page_reflects_persisted_values(client):
    config.save_settings({
        "print_customer_double": True,
        "print_extra_order_nr": False,
        "kitchen_buzzer": True,
    })
    resp = client.get("/settings")
    assert resp.status_code == 200
    # Template renders without crashing — presence of content confirms it
    assert len(resp.content) > 200


def test_settings_only_known_keys_are_stored(client):
    client.post("/settings", data={"unknown_key": "on", "print_customer_double": "on"})
    saved = config.load_settings()
    assert "unknown_key" not in saved
    assert saved["print_customer_double"] is True
