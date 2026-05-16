import os
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Absolute path to the project root (one level above tests/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(tmp_local):
    """Shared HTTP test client.  Raises on 5xx so failures are visible."""
    from app import app
    with TestClient(app) as c:
        yield c


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

    # Symlink static and templates so FastAPI can find them after chdir
    (tmp_path / "static").symlink_to(_PROJECT_ROOT / "static")
    (tmp_path / "templates").symlink_to(_PROJECT_ROOT / "templates")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KITCHENHELPER_DB_PATH", str(local / "orders.db"))
    monkeypatch.setenv("KITCHENHELPER_PRINTER_DICT", '{"kitchen1": "1.2.3.4", "customer": "1.2.3.5"}')
    monkeypatch.setenv("KITCHENHELPER_PRINTER_MODE", "Dummy")
    return local
