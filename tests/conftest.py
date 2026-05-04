import os
import shutil
import pytest


@pytest.fixture
def tmp_local(tmp_path, monkeypatch):
    local = tmp_path / ".local"
    (local / "menus" / "deleted").mkdir(parents=True)
    defaults = tmp_path / ".defaults"
    defaults.mkdir()
    (defaults / "default_settings.json").write_text(
        '{"print_customer_double": false, "print_extra_order_nr": false, "kitchen_buzzer": false}'
    )
    (defaults / "active_menu.json").write_text(
        '{"path": ".local/menus/backup_menu.json"}'
    )
    (defaults / "backup_menu.json").write_text("[]")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KITCHENHELPER_DB_PATH", str(local / "orders.db"))
    monkeypatch.setenv("KITCHENHELPER_PRINTER_DICT", '{"kitchen1": "1.2.3.4", "customer": "1.2.3.5"}')
    monkeypatch.setenv("KITCHENHELPER_PRINTER_MODE", "Dummy")
    return local
