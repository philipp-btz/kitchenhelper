```
***** this is outdated *****
```



# KitchenHelper - Bestellaufnahme

### KITCHENHELPER_DB_PATH="/app/data/orders.db"

Kleines Beispiel: Flask-App, die die Speisekarte aus `menu.json` lädt und Bestellungen annimmt.

Schnellstart (venv aktivieren, dann):

```bash
pip install -r requirements.txt
python app.py
```

Öffne dann im Browser `http://localhost:5000`.


Die Speisekarte ist in der Datei [backup_menu.json](menu_list/backup_menu.json) und kann einfach ausgetauscht oder geändert werden.

Einstellungen sind in `config.json` konfigurierbar. Standardwerte sind:

```json
{
	"host": "0.0.0.0",
	"port": 5099,
	"debug": true,
	"menu_path": "menu.json",
	"db_path": "app/data/orders.db",
	"auto_print_on_open": true
}
```

Bestellungen werden in einer eingebetteten SQLite-Datenbank (standard: `orders.db`) im Projektverzeichnis gespeichert.
Jede Bestellung enthält Metadaten wie `order_number` (autoincrement), `id` (uuid), `created_at`, `extras`, `notes` und `printed`.

Für einfache Backups reicht das Kopieren der angegebenen DB-Datei.

**Production / WSGI**

This project includes a WSGI entrypoint at `wsgi.py` exposing the Flask app as the callable `application`.

- Windows (recommended): install `waitress` and run:

```powershell
pip install -r requirements.txt
waitress-serve --listen=*:5099 wsgi:application
```

- Linux / WSL / container: install `gunicorn` and run:

```bash
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:5099 wsgi:application
```

Make sure `config.json` has `debug` set to `false` for production and adjust `port`/`host` as needed.

For containers, prefer running with Gunicorn inside the container or using a process manager + reverse proxy (e.g., Nginx).

