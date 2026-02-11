from flask import Flask, render_template, request, redirect, url_for, Response
import json
import os
import datetime
import uuid
import sqlite3
from typing import Any, Dict, List, Optional, cast

CONFIG_PATH: str = os.path.join(os.path.dirname(__file__), 'config.json')

def load_config() -> Dict[str, Any]:
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
    # normalize paths (ensure values are strings before joining)
    defaults['menu_path'] = os.path.join(os.path.dirname(__file__), str(defaults['menu_path']))
    defaults['db_path'] = os.path.join(os.path.dirname(__file__), str(defaults['db_path']))
    return defaults

config: Dict[str, Any] = load_config()

MENU_PATH: str = str(config['menu_path'])
DB_PATH: str = str(config['db_path'])

app = Flask(__name__)


def load_menu() -> List[Dict[str, Any]]:
    with open(MENU_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def init_db() -> None:
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
    # no legacy migration required; assume `items` JSON column is used





def save_order(order: Dict[str, Any]) -> Dict[str, Any]:
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


def enrich_items(items: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Ensure each item dict contains a `printer` attribute taken from the menu when possible."""
    if not items:
        return []
    try:
        menu = load_menu()
        menu_map: Dict[str, Dict[str, Any]] = {m['name']: m for m in menu}
    except Exception:
        menu_map = {}
    out: List[Dict[str, Any]] = []
    for raw in items:
        if isinstance(raw, dict):
            it: Dict[str, Any] = cast(Dict[str, Any], raw)
            name = it.get('name')
            if name and name in menu_map:
                it.setdefault('printer', menu_map[name].get('printer'))
            out.append(it)
        else:
            # fallback: convert to dict
            name = str(raw)
            printer = menu_map.get(name, {}).get('printer') if menu_map else None
            out.append({'name': name, 'extras': [], 'qty': 1, 'printer': printer})
    return out


def update_order(order_number: int, items: Optional[List[Dict[str, Any]]] = None, notes: Optional[str] = None, printed: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    fields: List[str] = []
    params: List[Any] = []
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


def get_orders() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM orders ORDER BY order_number DESC')
    rows = cur.fetchall()
    conn.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        items: List[Dict[str, Any]] = cast(List[Dict[str, Any]], json.loads(r['items'])) if r['items'] else []
        out.append({
            'order_number': r['order_number'],
            'id': r['id'],
            'items': items,
            'notes': r['notes'],
            'created_at': r['created_at'],
            'printed': bool(r['printed'])
        })
    return out


def get_order_by_number(order_number: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM orders WHERE order_number = ?', (order_number,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    items: List[Dict[str, Any]] = cast(List[Dict[str, Any]], json.loads(r['items'])) if r['items'] else []
    return {
        'order_number': r['order_number'],
        'id': r['id'],
        'items': items,
        'notes': r['notes'],
        'created_at': r['created_at'],
        'printed': bool(r['printed'])
    }


@app.route('/')
def index() -> Any:
    menu = load_menu()
    return render_template('index.html', menu=menu)


@app.route('/order', methods=['POST'])
def order() -> Any:
    # Expect a JSON string in form field 'items' describing an array of ordered dishes
    data = request.form
    items_json = data.get('items')
    notes = data.get('notes', '')
    try:
        items = cast(List[Dict[str, Any]], json.loads(items_json)) if items_json else []
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
        order: Dict[str, Any] = {
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
def order_start() -> Any:
    # create a draft order and return its order_number and id
    draft: Dict[str, Any] = {
        'id': str(uuid.uuid4()),
        'items': [],
        'notes': '',
        'created_at': datetime.datetime.now().isoformat(),
        'printed': False,
    }
    saved = save_order(draft)
    return {'order_number': saved.get('order_number'), 'id': saved.get('id')}


@app.route('/orders')
def orders_view() -> Any:
    orders = get_orders()
    return render_template('orders.html', orders=orders)


@app.route('/toggle_printed/<order_id>', methods=['POST'])
def toggle_printed(order_id: str) -> Any:
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
def order_print(order_number: int) -> Any:
    order = get_order_by_number(order_number)
    if not order:
        return "Bestellung nicht gefunden", 404
    return render_template('print.html', order=order)


@app.route('/order/export/<int:order_number>')
def order_export(order_number: int) -> Response:
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
