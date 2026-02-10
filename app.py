from flask import Flask, render_template, request, redirect, url_for
import json
import os
import datetime
import uuid
import sqlite3

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

def load_config():
    defaults = {
        'host': '0.0.0.0',
        'port': 5099,
        'debug': True,
        'menu_path': 'menu.json',
        'db_path': 'orders.db',
        'auto_print_on_open': True
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                defaults.update(cfg)
        except Exception:
            pass
    # normalize paths
    defaults['menu_path'] = os.path.join(os.path.dirname(__file__), defaults['menu_path'])
    defaults['db_path'] = os.path.join(os.path.dirname(__file__), defaults['db_path'])
    return defaults

config = load_config()

MENU_PATH = config['menu_path']
DB_PATH = config['db_path']

app = Flask(__name__)


def load_menu():
    with open(MENU_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        order_number INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT UNIQUE,
        items TEXT,
        notes TEXT,
        created_at TEXT,
        printed INTEGER DEFAULT 0
    )
    ''')
    conn.commit()
    conn.close()
    # attempt migration from legacy schema if needed
    migrate_legacy()


def migrate_legacy():
    """Detect legacy columns (`item`, `extras`) and migrate rows to `items` JSON column.

    This will add an `items` column if missing and populate it for rows that still
    use the old `item`/`extras` fields. It is idempotent.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(orders)")
    cols = [row[1] for row in cur.fetchall()]
    has_items = 'items' in cols
    has_item = 'item' in cols
    has_extras = 'extras' in cols

    if not has_items:
        # add new column to hold JSON array of items
        cur.execute("ALTER TABLE orders ADD COLUMN items TEXT")
        conn.commit()
        has_items = True

    # If legacy single-item columns exist, migrate their values into `items` JSON
    if has_item or has_extras:
        cur.execute('SELECT order_number, item, extras FROM orders')
        rows = cur.fetchall()
        for order_number, item_name, extras_text in rows:
            # skip if items already present
            cur2 = conn.cursor()
            cur2.execute('SELECT items FROM orders WHERE order_number = ?', (order_number,))
            existing = cur2.fetchone()
            if existing and existing[0]:
                continue

            if not item_name:
                continue

            # parse extras (may be JSON or plain string)
            extras = []
            if extras_text:
                try:
                    extras = json.loads(extras_text)
                    if not isinstance(extras, list):
                        extras = [extras]
                except Exception:
                    extras = [extras_text]

            # attach printer info from menu if available
            menu = load_menu()
            menu_map = {m['name']: m for m in menu}
            printer = menu_map.get(item_name, {}).get('printer') if menu_map else None
            items_json = json.dumps([{'name': item_name, 'extras': extras, 'qty': 1, 'printer': printer}], ensure_ascii=False)
            cur.execute('UPDATE orders SET items = ? WHERE order_number = ?', (items_json, order_number))
        conn.commit()

    conn.close()


def save_order(order):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # ensure items carry `printer` metadata before saving
    items = enrich_items(order.get('items', []))
    cur.execute(
        'INSERT INTO orders (id, items, notes, created_at, printed) VALUES (?, ?, ?, ?, ?)',
        (order['id'], json.dumps(items, ensure_ascii=False), order.get('notes', ''), order['created_at'], int(order['printed']))
    )
    conn.commit()
    order_number = cur.lastrowid
    conn.close()
    order['order_number'] = order_number
    return order


def enrich_items(items):
    """Ensure each item dict contains a `printer` attribute taken from the menu when possible."""
    if not items:
        return items
    try:
        menu = load_menu()
        menu_map = {m['name']: m for m in menu}
    except Exception:
        menu_map = {}
    out = []
    for it in items:
        if isinstance(it, dict):
            name = it.get('name')
            if name and name in menu_map:
                it.setdefault('printer', menu_map[name].get('printer'))
            out.append(it)
        else:
            # fallback: convert to dict
            name = str(it)
            printer = menu_map.get(name, {}).get('printer') if menu_map else None
            out.append({'name': name, 'extras': [], 'qty': 1, 'printer': printer})
    return out


def update_order(order_number, items=None, notes=None, printed=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    fields = []
    params = []
    if items is not None:
        # enrich items with printer info before storing
        items = enrich_items(items)
        fields.append('items = ?')
        params.append(json.dumps(items, ensure_ascii=False))
    if notes is not None:
        fields.append('notes = ?')
        params.append(notes)
    if printed is not None:
        fields.append('printed = ?')
        params.append(int(bool(printed)))
    if not fields:
        conn.close()
        return None
    params.append(order_number)
    sql = f"UPDATE orders SET {', '.join(fields)} WHERE order_number = ?"
    cur.execute(sql, tuple(params))
    conn.commit()
    conn.close()
    return get_order_by_number(order_number)


def get_orders():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM orders ORDER BY order_number DESC')
    rows = cur.fetchall()
    conn.close()
    out = []
    for r in rows:
        # Support legacy schema: rows may have 'items' (new) or 'item'+'extras' (old)
        keys = r.keys()
        if 'items' in keys:
            items = json.loads(r['items']) if r['items'] else []
        else:
            # fallback to single-item representation
            item_name = r['item'] if 'item' in keys else None
            extras = json.loads(r['extras']) if 'extras' in keys and r['extras'] else []
            if item_name:
                items = [{'name': item_name, 'extras': extras, 'qty': 1}]
            else:
                items = []

        out.append({
            'order_number': r['order_number'],
            'id': r['id'],
            'items': items,
            'notes': r['notes'] if 'notes' in keys else '',
            'created_at': r['created_at'],
            'printed': bool(r['printed'])
        })
    return out


def get_order_by_number(order_number):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM orders WHERE order_number = ?', (order_number,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    keys = r.keys()
    if 'items' in keys:
        items = json.loads(r['items']) if r['items'] else []
    else:
        item_name = r['item'] if 'item' in keys else None
        extras = json.loads(r['extras']) if 'extras' in keys and r['extras'] else []
        if item_name:
            items = [{'name': item_name, 'extras': extras, 'qty': 1}]
        else:
            items = []

    return {
        'order_number': r['order_number'],
        'id': r['id'],
        'items': items,
        'notes': r['notes'] if 'notes' in keys else '',
        'created_at': r['created_at'],
        'printed': bool(r['printed'])
    }


@app.route('/')
def index():
    menu = load_menu()
    return render_template('index.html', menu=menu)


@app.route('/order', methods=['POST'])
def order():
    # Expect a JSON string in form field 'items' describing an array of ordered dishes
    data = request.form
    items_json = data.get('items')
    notes = data.get('notes', '')
    try:
        items = json.loads(items_json) if items_json else []
    except Exception:
        items = []
    # if order_number provided, update existing draft
    order_number = data.get('order_number')
    if order_number:
        try:
            order_number = int(order_number)
        except Exception:
            order_number = None
    if order_number:
        updated = update_order(order_number, items=items, notes=notes, printed=False)
        saved = updated or {'order_number': order_number}
    else:
        order = {
            'id': str(uuid.uuid4()),
            'items': items,
            'notes': notes,
            'created_at': datetime.datetime.now().isoformat(),
            'printed': False,
        }
        saved = save_order(order)
    # if this is an AJAX request, return JSON so the client can stay on the menu page
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (request.headers.get('Accept') or ''):
        return {'status': 'ok', 'order_number': saved.get('order_number')}
    return redirect(url_for('orders_view'))


@app.route('/order/start', methods=['POST', 'GET'])
def order_start():
    # create a draft order and return its order_number and id
    draft = {
        'id': str(uuid.uuid4()),
        'items': [],
        'notes': '',
        'created_at': datetime.datetime.now().isoformat(),
        'printed': False,
    }
    saved = save_order(draft)
    return {'order_number': saved.get('order_number'), 'id': saved.get('id')}


@app.route('/orders')
def orders_view():
    orders = get_orders()
    return render_template('orders.html', orders=orders)


@app.route('/toggle_printed/<order_id>', methods=['POST'])
def toggle_printed(order_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # flip printed state
    cur.execute('SELECT printed FROM orders WHERE id = ?', (order_id,))
    row = cur.fetchone()
    if row:
        new = 0 if row[0] else 1
        cur.execute('UPDATE orders SET printed = ? WHERE id = ?', (new, order_id))
        conn.commit()
    conn.close()
    return redirect(url_for('orders_view'))


@app.route('/order/print/<int:order_number>')
def order_print(order_number):
    order = get_order_by_number(order_number)
    if not order:
        return "Bestellung nicht gefunden", 404
    return render_template('print.html', order=order)


@app.route('/order/export/<int:order_number>')
def order_export(order_number):
    order = get_order_by_number(order_number)
    if not order:
        return "Bestellung nicht gefunden", 404
    lines = []
    lines.append(f"Bestell-Nr.: {order['order_number']}")
    lines.append(f"UUID: {order['id']}")
    lines.append(f"Zeit: {order['created_at']}")
    # list all ordered items
    for it in order.get('items', []):
        qty = it.get('qty', 1)
        name = it.get('name', '')
        extras = it.get('extras', []) or []
        if qty and qty > 1:
            lines.append(f"{qty}x {name}")
        else:
            lines.append(f"{name}")
        if extras:
            lines.append('Extras: ' + ', '.join(extras))
    if order['notes']:
        lines.append('Notiz: ' + order['notes'])
    lines.append('Gedruckt: ' + ('Ja' if order['printed'] else 'Nein'))
    text = '\n'.join(lines)
    from flask import Response
    resp = Response(text, mimetype='text/plain; charset=utf-8')
    resp.headers['Content-Disposition'] = f'attachment; filename=order_{order_number}.txt'
    return resp


init_db()


if __name__ == '__main__':
    app.run(debug=bool(config.get('debug', True)), host=config.get('host', '0.0.0.0'), port=int(config.get('port', 5099)))
