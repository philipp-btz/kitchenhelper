# KitchenHelper

Bestellaufnahme, Küchenanzeige und Ausgabemanagement für Veranstaltungen mit ESC/POS-Bondrucker-Integration.

## Schnellstart

```bash
uv sync
uv run uvicorn app:app --reload
```

Öffne dann im Browser `http://localhost:8000`.

## Konfiguration

Einstellungen werden über Umgebungsvariablen gesetzt (`.env`-Datei oder Docker `environment:`):

| Variable | Beschreibung | Standard |
|---|---|---|
| `KITCHENHELPER_PRINTER_MODE` | `Thermo` (Netzwerkdrucker) oder `Dummy` (Testmodus) | `Dummy` |
| `KITCHENHELPER_PRINTER_DICT` | JSON-Mapping: Druckername → IP, z.B. `{"kitchen1": "192.168.1.10", "customer": "192.168.1.11"}` | `{}` |
| `KITCHENHELPER_DB_PATH` | Pfad zur SQLite-Datenbank | `.local/orders.db` |
| `KITCHENHELPER_HOST` | Bind-Adresse | `0.0.0.0` |
| `KITCHENHELPER_PORT` | Port | `8000` |

## Docker

```bash
docker-compose up -d
```

Oder manuell:

```bash
docker build -t kitchen-helper .
docker run -p 8000:8000 -v ./kitchen_data:/app/.local kitchen-helper
```

Das Docker-Image (`philippbtz/kitchen-helper:latest`) wird automatisch via GitHub Actions gebaut und unterstützt ARM64 (Raspberry Pi) und AMD64.

## Datenspeicherung

Persistente Daten liegen in `.local/` (Docker-Volume: `/app/.local`):
- `.local/orders.db` — SQLite-Datenbank mit allen Bestellungen
- `.local/menus/` — Speisekarten als JSON-Dateien
- `.local/settings.json` — Benutzereinstellungen
- `.local/active_menu.json` — Aktive Speisekarte

## Speisekarten-Format

Speisekarten sind JSON-Dateien mit einer Liste von Artikeln:

```json
[
  {
    "name": "Burger",
    "extras": ["ohne Zwiebeln", "extra Käse"],
    "printer": "kitchen1",
    "bg_color": "#f0f0f0"
  }
]
```

## Tests

```bash
uv run pytest
```
