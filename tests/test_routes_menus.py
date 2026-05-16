"""Route tests: menu editor, save, select, delete, and upload."""
import json
import pytest
import config


SAMPLE_ITEMS = [
    {"name": "Pizza",  "extras": ["extra cheese"], "printer": "kitchen1", "bg_color": ""},
    {"name": "Water",  "extras": [],               "printer": "",          "bg_color": ""},
]


def _write_menu(tmp_local, filename, items=None):
    path = tmp_local / "menus" / filename
    path.write_text(json.dumps(items or SAMPLE_ITEMS))
    return filename


# ── GET /menus ─────────────────────────────────────────────────────────────────

def test_menus_page_renders(client):
    resp = client.get("/menus")
    assert resp.status_code == 200


def test_menus_page_lists_existing_files(client, tmp_local):
    _write_menu(tmp_local, "alpha.json")
    resp = client.get("/menus")
    assert b"alpha" in resp.content


# ── GET /menus/editor ─────────────────────────────────────────────────────────

def test_menus_editor_renders_empty_without_file(client):
    resp = client.get("/menus/editor")
    assert resp.status_code == 200


def test_menus_editor_loads_specified_file(client, tmp_local):
    _write_menu(tmp_local, "my_menu.json")
    resp = client.get("/menus/editor?menu_file=my_menu.json")
    assert resp.status_code == 200
    assert b"Pizza" in resp.content


def test_menus_editor_unknown_file_redirects(client):
    resp = client.get("/menus/editor?menu_file=ghost.json", follow_redirects=False)
    assert resp.status_code == 303


# ── POST /menus/save ──────────────────────────────────────────────────────────

def test_menus_save_creates_json_file(client, tmp_local):
    resp = client.post(
        "/menus/save",
        data={
            "menu_name": "new_menu",
            "items_json": json.dumps(SAMPLE_ITEMS),
            "loaded_file": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert (tmp_local / "menus" / "new_menu.json").exists()


def test_menus_save_appends_json_extension(client, tmp_local):
    client.post(
        "/menus/save",
        data={"menu_name": "noext", "items_json": json.dumps(SAMPLE_ITEMS), "loaded_file": ""},
    )
    assert (tmp_local / "menus" / "noext.json").exists()


def test_menus_save_normalizes_items(client, tmp_local):
    """Price and unknown fields must be stripped; name must be preserved."""
    raw = [{"name": "Schnitzel", "price": 15.0, "extras": ["Sauce"], "printer": "kitchen1"}]
    client.post(
        "/menus/save",
        data={"menu_name": "schnitzel_menu", "items_json": json.dumps(raw), "loaded_file": ""},
    )
    saved = json.loads((tmp_local / "menus" / "schnitzel_menu.json").read_text())
    assert saved[0]["name"] == "Schnitzel"
    assert "price" not in saved[0]


def test_menus_save_empty_name_error_redirect(client):
    resp = client.post(
        "/menus/save",
        data={"menu_name": "", "items_json": json.dumps(SAMPLE_ITEMS), "loaded_file": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]


def test_menus_save_invalid_json_error_redirect(client):
    resp = client.post(
        "/menus/save",
        data={"menu_name": "bad", "items_json": "NOT_JSON", "loaded_file": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]


def test_menus_save_items_without_name_error_redirect(client):
    resp = client.post(
        "/menus/save",
        data={"menu_name": "bad", "items_json": json.dumps([{"price": 9}]), "loaded_file": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error" in resp.headers["location"]


def test_menus_save_overwrites_existing_file(client, tmp_local):
    _write_menu(tmp_local, "editable.json", items=[{"name": "Old", "printer": "k"}])
    client.post(
        "/menus/save",
        data={
            "menu_name": "editable",
            "items_json": json.dumps([{"name": "New", "printer": "k"}]),
            "loaded_file": "editable.json",
        },
    )
    saved = json.loads((tmp_local / "menus" / "editable.json").read_text())
    assert saved[0]["name"] == "New"


# ── POST /menus/select ────────────────────────────────────────────────────────

def test_menus_select_updates_active_menu(client, tmp_local):
    _write_menu(tmp_local, "picked.json")
    resp = client.post(
        "/menus/select",
        data={"menu_file": "picked.json"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "picked.json" in config.get_active_menu_path()


def test_menus_select_empty_filename_redirects(client):
    resp = client.post("/menus/select", data={"menu_file": ""}, follow_redirects=False)
    assert resp.status_code == 303


def test_menus_select_traversal_filename_redirects(client):
    resp = client.post(
        "/menus/select",
        data={"menu_file": "../../etc/passwd"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


# ── POST /menus/delete ────────────────────────────────────────────────────────

def test_menus_delete_moves_file_to_deleted(client, tmp_local):
    _write_menu(tmp_local, "bye.json")
    client.post("/menus/delete", data={"menu_file": "bye.json"}, follow_redirects=False)
    assert not (tmp_local / "menus" / "bye.json").exists()
    assert (tmp_local / "menus" / "deleted" / "bye.json").exists()


def test_menus_delete_nonexistent_file_still_redirects(client):
    resp = client.post("/menus/delete", data={"menu_file": "ghost.json"}, follow_redirects=False)
    assert resp.status_code == 303


def test_menus_delete_empty_filename_redirects(client):
    resp = client.post("/menus/delete", data={"menu_file": ""}, follow_redirects=False)
    assert resp.status_code == 303


# ── POST /menus/upload ────────────────────────────────────────────────────────

def test_menus_upload_new_file_saves_and_redirects(client, tmp_local):
    content = json.dumps(SAMPLE_ITEMS).encode()
    resp = client.post(
        "/menus/upload",
        files={"menu_file": ("uploaded.json", content, "application/json")},
        data={"replace": "", "filename": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert (tmp_local / "menus" / "uploaded.json").exists()


def test_menus_upload_existing_file_shows_confirm_page(client, tmp_local):
    _write_menu(tmp_local, "exists.json")
    content = json.dumps(SAMPLE_ITEMS).encode()
    resp = client.post(
        "/menus/upload",
        files={"menu_file": ("exists.json", content, "application/json")},
        data={"replace": "", "filename": ""},
    )
    assert resp.status_code == 200
    assert b"exists.json" in resp.content


def test_menus_upload_confirm_replace_overwrites(client, tmp_local):
    _write_menu(tmp_local, "replace_me.json", items=[{"name": "Old", "printer": "k"}])
    new_content = json.dumps([{"name": "New", "printer": "k"}]).encode()
    # Stage the upload
    client.post(
        "/menus/upload",
        files={"menu_file": ("replace_me.json", new_content, "application/json")},
        data={"replace": "", "filename": ""},
    )
    # Confirm replacement
    resp = client.post(
        "/menus/upload",
        data={"replace": "1", "filename": "replace_me.json"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    saved = json.loads((tmp_local / "menus" / "replace_me.json").read_text())
    assert saved[0]["name"] == "New"


def test_menus_upload_cancel_replace_keeps_original(client, tmp_local):
    _write_menu(tmp_local, "keep_me.json", items=[{"name": "Original", "printer": "k"}])
    new_content = json.dumps([{"name": "Replacement", "printer": "k"}]).encode()
    # Stage the upload
    client.post(
        "/menus/upload",
        files={"menu_file": ("keep_me.json", new_content, "application/json")},
        data={"replace": "", "filename": ""},
    )
    # Cancel replacement
    client.post(
        "/menus/upload",
        data={"replace": "2", "filename": "keep_me.json"},
    )
    saved = json.loads((tmp_local / "menus" / "keep_me.json").read_text())
    assert saved[0]["name"] == "Original"


def test_menus_upload_non_json_returns_400(client):
    resp = client.post(
        "/menus/upload",
        files={"menu_file": ("photo.png", b"binarydata", "image/png")},
        data={"replace": "", "filename": ""},
    )
    assert resp.status_code == 400
