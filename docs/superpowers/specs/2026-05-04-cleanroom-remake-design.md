# KitchenHelper — Clean Room Remake Design

**Date:** 2026-05-04
**Status:** Approved

## Overview

A ground-up rewrite of KitchenHelper, a lightweight restaurant order management system with thermal printer integration. Designed to run on Raspberry Pi 4/5. All existing features are preserved; architectural ballast is removed.

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Web framework | FastAPI + Uvicorn | Async, lightweight, handles concurrent polling displays without blocking |
| Frontend | HTMX + Jinja2 | No build tooling, partial page updates for live displays, minimal JS |
| Database | SQLite (WAL mode) | Zero server overhead, Pi-friendly, WAL eliminates read/write locking |
| Print queue | Thread-based (one daemon thread per printer) | ESC/POS is synchronous/blocking — a dedicated thread is the honest model |
| Deployment | Single Docker container, single process | No gunicorn multi-worker, no separate printer service |

## Module Structure

```
kitchenhelper/
├── app.py              # FastAPI app, lifespan (starts printer threads), mounts routers
├── config.py           # Load config from env vars + .local/ files; copy defaults on first run
├── db.py               # SQLite connection (WAL mode), all queries as typed functions
├── menu.py             # Menu file I/O, validation, normalization
├── printing/
│   ├── manager.py      # QueueManager: daemon thread per printer, polls DB, retries on failure
│   └── receipts.py     # ESC/POS receipt formatting (kitchen, customer, report)
├── routers/
│   ├── orders.py       # POST /order, /fulfilled, /cooked, /export, /print_kitchen, /print_customer
│   ├── displays.py     # /kitchen_display, /customer_display, /api/uncooked_orders, /api/cooked_unfulfilled
│   ├── menus.py        # /menus/* — list, select, editor, save, upload, delete
│   ├── settings.py     # GET/POST /settings
│   └── reports.py      # /reports — stats view, range print, order list by range
├── templates/          # Jinja2 templates, one per view
└── static/             # CSS, images, icons
```

## Data Layout

```
.local/                        # Docker volume — persists across restarts
├── orders.db                  # SQLite database
├── settings.json              # Runtime UI settings
├── active_menu.json           # Currently selected menu path
└── menus/
    ├── *.json                 # User-created menus
    └── deleted/               # Soft-deleted menus (moved, not destroyed)

.defaults/                     # Shipped with image, never written to
├── default_settings.json
├── active_menu.json
└── backup_menu.json           # Built-in starter menu
```

`config.py` copies any missing `.defaults/` files into `.local/` on startup — **never overwrites** existing files.

Printer IPs and mode stay in environment variables (`.env` or Docker env) — deployment config, not user config.

## Database Schema

```sql
CREATE TABLE orders (
    order_number     INTEGER PRIMARY KEY AUTOINCREMENT,
    id               TEXT UNIQUE NOT NULL,
    customer_id      TEXT NOT NULL,
    kitchen          TEXT NOT NULL,
    items            TEXT NOT NULL,        -- JSON array
    notes            TEXT DEFAULT '',
    created_at       TEXT NOT NULL,        -- ISO 8601: 2026-05-04T14:30:00
    cooked_at        TEXT,                 -- NULL = not cooked, timestamp = cooked
    fulfilled_at     TEXT,                 -- NULL = not fulfilled, timestamp = fulfilled
    printed_kitchen  INTEGER DEFAULT 0,    -- 0 = unprinted, 1 = printed
    printed_customer INTEGER DEFAULT 0     -- 0 = unprinted, 1 = printed
)
```

**Changes from current schema:**
- `cooked` / `fulfilled` renamed to `cooked_at` / `fulfilled_at`; NULL replaces `'--'` sentinel
- No print state `2` (reserved) — single process eliminates reservation race entirely
- ISO 8601 timestamps everywhere — no more `YYYY_mm_dd-HH:MM:SS` vs `YYYY_mm_dd-HH_MM_SS` mismatch

## Print Queue Design

One `QueueManager` instance per configured printer, created in FastAPI's lifespan and kept for the lifetime of the process.

Each `QueueManager` runs a daemon thread that:
1. Polls SQLite every 1s for unprinted orders matching its printer (`printed_kitchen = 0 AND kitchen = ?` or `printed_customer = 0`)
2. On successful print: sets the relevant flag to `1`
3. On failure: leaves at `0`, logs the error, retries next cycle
4. Also processes an in-memory queue for explicit jobs (test print, report print)

Since there is exactly one process and one thread per printer, there is no reservation race and no need for print state `2`. On restart, unprinted orders (still at `0`) are picked up naturally.

Receipt formatting is separated into `receipts.py` — `QueueManager` calls formatting functions, keeping print logic out of the thread management code.

## Settings

`settings.json` holds runtime-configurable toggles, editable via the `/settings` UI:
- `print_customer_double` — print customer receipt twice
- `print_extra_order_nr` — print a large order number slip after the customer receipt
- `kitchen_buzzer` — trigger printer buzzer after kitchen print

## Dynamic Printer Configuration

The number of printers is fully dynamic, driven by `KITCHENHELPER_PRINTER_DICT` in the environment:

```
KITCHENHELPER_PRINTER_DICT={"kitchen1":"192.168.1.10","kitchen2":"192.168.1.11","customer":"192.168.1.12"}
```

`config.py` parses this at startup and exposes the printer names (keys) to the rest of the app.

**Menu editor integration:** When editing a menu item, the printer assignment dropdown is populated from the live printer names — not hardcoded values. If 5 printers are configured, the dropdown shows 5 options. If the config changes, the editor reflects it on the next page load.

`menu.py` reads printer names from config when rendering the editor; no printer names are stored in `settings.json` or hardcoded anywhere in templates. Menu items store the printer name as a plain string (e.g. `"kitchen2"`), which is matched against active printer names at order time.

## Routing

```
GET  /                              # Order taking (menu)
POST /order                         # Submit order (AJAX-friendly, returns JSON)

GET  /kitchen_display               # Kitchen screen (polls via HTMX)
GET  /customer_display              # Pickup screen (polls via HTMX)
GET  /api/uncooked_orders           # JSON — uncooked orders (with ?kitchen= filter)
GET  /api/cooked_unfulfilled        # JSON — cooked but not yet fulfilled order numbers
POST /cooked/{id}                   # Toggle cooked_at
POST /fulfilled/{id}                # Toggle fulfilled_at

GET  /menus                         # Menu selector
GET  /menus/editor                  # Menu editor
POST /menus/save                    # Save edited menu
POST /menus/select                  # Set active menu
POST /menus/delete                  # Soft-delete menu
POST /menus/upload                  # Upload JSON menu file

GET  /settings                      # Settings view
POST /settings                      # Update settings

GET  /reports                       # Stats + range print UI
GET  /api/reports                   # JSON aggregation (?from=&to=)
POST /reports/print                 # Send aggregated report to printer

GET  /orders                        # Order list (admin view)
GET  /orders/{id}/export            # Download order as text file
POST /orders/{id}/print_kitchen     # Re-queue kitchen print for this order
POST /orders/{id}/print_customer    # Re-queue customer print for this order
```

## New Features vs Current

| Feature | Current | New |
|---|---|---|
| Daily report | Fixed to today | Custom date range via date picker with presets (Today, Yesterday, This Week, custom) |
| Statistics | None | `/reports` view: items sold, extras, totals for any time range |
| Order list by range | None | Filter order list by date range |
| Timestamps | Custom format, inconsistent | ISO 8601 throughout |
| Print reservation | State 2, race-prone | Eliminated |

## Key Bug Fixes

- `row_factory` on cursor caused `sqlite3.Row` objects passed to print functions instead of dicts — fixed by consistent use of `dict(row)` in `db.py`
- `order['printed']` key crash in export — fixed by consistent order dict schema from `db.py`
- `clear_db_reservations` race between web workers and printer service — eliminated by single-process design
- Timestamp format mismatch between write path and read path — fixed by ISO 8601 everywhere
- `backup_menu.json` unconditionally overwritten on startup — fixed, only copied if missing

## Deployment

```yaml
# docker-compose.yml
services:
  kitchenhelper:
    image: philippbtz/kitchen-helper:latest
    ports:
      - "80:80"
    volumes:
      - ./kitchen_data:/app/.local
    environment:
      - KITCHENHELPER_PRINTER_MODE=Thermo
      - KITCHENHELPER_PRINTER_DICT={"1":"192.168.1.10","customer":"192.168.1.11"}
```

Single container, single process (`uvicorn`), no gunicorn. GitHub Actions builds for ARM64 (Pi) and AMD64.