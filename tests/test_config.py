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
