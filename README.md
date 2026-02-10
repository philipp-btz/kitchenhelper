# KitchenHelper - Bestellaufnahme


Kleines Beispiel: Flask-App, die die Speisekarte aus `menu.json` lädt und Bestellungen annimmt.

Schnellstart (venv aktivieren, dann):

```bash
pip install -r requirements.txt
python app.py
```

Öffne dann im Browser `http://localhost:5000`.


Die Speisekarte ist in der Datei [menu.json](menu.json) und kann einfach ausgetauscht oder geändert werden.

Einstellungen sind in `config.json` konfigurierbar. Standardwerte sind:

```json
{
	"host": "0.0.0.0",
	"port": 5099,
	"debug": true,
	"menu_path": "menu.json",
	"db_path": "orders.db",
	"auto_print_on_open": true
}
```

Bestellungen werden in einer eingebetteten SQLite-Datenbank (standard: `orders.db`) im Projektverzeichnis gespeichert.
Jede Bestellung enthält Metadaten wie `order_number` (autoincrement), `id` (uuid), `created_at`, `extras`, `notes` und `printed`.

Für einfache Backups reicht das Kopieren der angegebenen DB-Datei.

