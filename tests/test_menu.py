import json
import pytest
import menu


def test_normalize_item_basic():
    raw = {"name": "Burger", "price": 9.5, "extras": ["Cheese"], "printer": "kitchen1"}
    result = menu.normalize_item(raw)
    assert result["name"] == "Burger"
    assert "price" not in result
    assert result["extras"] == ["Cheese"]
    assert result["printer"] == "kitchen1"
    assert result["bg_color"] == ""


def test_normalize_item_name_de_fallback():
    raw = {"name_de": "Schnitzel", "price": 12.0, "extras": [], "printer": "k"}
    result = menu.normalize_item(raw)
    assert result["name"] == "Schnitzel"


def test_normalize_item_strips_whitespace():
    raw = {"name": "  Pizza  ", "price": 8.0, "extras": [], "printer": " kitchen1 "}
    result = menu.normalize_item(raw)
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
    assert "price" not in items[0]


def test_soft_delete_moves_file(tmp_local):
    (tmp_local / "menus" / "old.json").write_text("[]")
    menu.soft_delete("old.json")
    assert not (tmp_local / "menus" / "old.json").exists()
    assert (tmp_local / "menus" / "deleted" / "old.json").exists()
