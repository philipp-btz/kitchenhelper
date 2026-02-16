from flask import Flask, render_template, request, redirect, url_for, Response
import json
import os
import datetime
import time
import uuid
import sqlite3
import tempfile
from werkzeug.utils import secure_filename
from typing import Any, Dict, List, Optional, cast
import menu_picker as mp

CONFIG_PATH: str = os.path.join(os.path.dirname(__file__), 'config.json')

def load_config() -> Dict[str, Any]:
    defaults = {
        'host': '0.0.0.0',
        'port': 5099,
        'debug': True,
        'menu_path': 'backup_menu.json',
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
    menu_path = mp.list_menu_files()
    defaults['menu_path'] = os.path.join(os.path.dirname(__file__), str(defaults['menu_path']))
    defaults['db_path'] = os.path.join(os.path.dirname(__file__), str(defaults['db_path']))
    return defaults

config: Dict[str, Any] = load_config()

MENU_PATH: str = str(config['menu_path'])
DB_PATH: str = str(config['db_path'])
MENU_NAME: str = str(os.path.splitext(os.path.basename(MENU_PATH))[0]) if MENU_PATH else "Unbekannt"

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
        customer_id TEXT,
        items TEXT,
        notes TEXT,
        created_at TEXT,
        fulfilled TEXT DEFAULT '--',
        cooked TEXT DEFAULT '--',
        printed INTEGER DEFAULT 0
    )
    ''')
    conn.commit()
    conn.close()





def save_order(order: Dict[str, Any]) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # ensure items carry `printer` metadata before saving
    items = order.get('items', [])
    cur.execute(
        'INSERT INTO orders (id, customer_id, items, notes, created_at, printed) VALUES (?, ?, ?, ?, ?, ?)',
        (order['id'], order.get('customer_id'), json.dumps(items, ensure_ascii=False), order.get('notes', 'Notes unobtainable'), order['created_at'], int(order['printed']))
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


def format_timestamp(raw: Optional[str]) -> str:
    """Format a stored timestamp string into a human-readable form.

    Stored format: "YYYY_mm_dd-HH_MM_SS" (e.g. 2026_02_16-14_30_00).
    Returns empty string for missing/placeholder values.
    """
    if not raw or raw == 'no' or raw == '--':
        return ''
    try:
        dt = datetime.datetime.strptime(raw, "%Y_%m_%d-%H_%M_%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ''


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
        # format fulfilled and cooked timestamps if present (stored as "YYYY_mm_dd-HH_MM_SS"), otherwise marker
        fulfilled_raw = r['fulfilled'] if 'fulfilled' in r.keys() and r['fulfilled'] is not None else 'no'
        cooked_raw = r['cooked'] if 'cooked' in r.keys() and r['cooked'] is not None else 'no'

        out.append({
            'order_number': r['order_number'],
            'id': r['id'],
            'items': items,
            'notes': r['notes'],
            'created_at': r['created_at'],
            'printed': bool(r['printed']),
            'fulfilled': fulfilled_raw,
            'cooked': cooked_raw,
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
    print(f"Raw FULFILLED: {r['fulfilled'] if 'fulfilled' in r.keys() and r['fulfilled'] is not None else 'no'}, \nRAW COOKED: {r['cooked'] if 'cooked' in r.keys() and r['cooked'] is not None else 'no'}")
    return {
        'order_number': r['order_number'],
        'id': r['id'],
        'items': items,
        'notes': r['notes'],
        'created_at': r['created_at'],
        'printed': bool(r['printed']),
        'fulfilled': format_timestamp(r['fulfilled'] if 'fulfilled' in r.keys() and r['fulfilled'] is not None else 'no'),
        'cooked': format_timestamp(r['cooked'] if 'cooked' in r.keys() and r['cooked'] is not None else 'no')
    }


@app.route('/')
def index() -> Any:
    menu = load_menu()
    return render_template('index.html', menu=menu, menu_name=MENU_NAME)


@app.route('/order', methods=['POST'])
def order() -> Any:
    # Expect a JSON string in form field 'items' describing an array of ordered dishes
    data = request.form
    items_json = data.get('items')
    notes = data.get('notes', '')
    try:
        items = enrich_items(cast(List[Dict[str, Any]], json.loads(items_json)) if items_json else [])
    except Exception:
        items = []
    # if order_number provided, update existing draft
    order_number = data.get('order_number')
    order_numbers: str = ""
    if order_number:
        try:
            order_number = int(order_number)
        except Exception:
            order_number = None
    if order_number:
        print("ORDER NUMBER PROVIDED, UPDATING EXISTING ORDER", order_number)
        updated = update_order(order_number, items=items, notes=notes, printed=False)
        saved = updated or {'order_number': order_number}
    else:
        customer_id = str(uuid.uuid4())

        # group items by printer and create separate order for each printer
        for printer in set(it.get('printer') for it in items if it.get('printer')):
            items_for_printer = [it for it in items if it.get('printer') == printer]
            order: Dict[str, Any] = {
                'id': str(uuid.uuid4()),
                'items': items_for_printer,
                'notes': notes,
                'created_at': time.strftime("%Y_%m_%d-%H:%M:%S"),
                'printed': False,
                'customer_id': customer_id,
            }
            order_numbers = order_numbers + " + " + str(save_order(order).get('order_number'))


    # if this is an AJAX request, return JSON so the client can stay on the menu page
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (request.headers.get('Accept') or ''):
        return {'status': 'ok', 'order_number': order_numbers.lstrip(' + ')}
    return redirect(url_for('orders_view'))


@app.route('/order/start', methods=['POST', 'GET'])
def order_start() -> Any:
    # create a draft order and return its order_number and id
    draft: Dict[str, Any] = {
        'id': str(uuid.uuid4()),
        'items': [],
        'notes': '',
        'created_at': time.strftime("%Y_%m_%d-%H:%M:%S"),
        'printed': False,
    }
    saved = save_order(draft)
    return {'order_number': saved.get('order_number'), 'id': saved.get('id')}


@app.route('/orders')
def orders_view() -> Any:
    orders = get_orders()
    return render_template('orders.html', orders=orders)


@app.route('/menus')
def menus_view() -> Any:
    # list available menu files from the `menu_list` folder
    files = mp.list_menu_files()
    menus = []
    base_dir = os.path.join(os.path.dirname(__file__), 'menu_list')
    for f in files:
        if f.lower().endswith('.json'):
            menus.append({'file': f, 'title': os.path.splitext(f)[0]})
    # optional confirmation from querystring
    selected = request.args.get('selected')
    return render_template('menu_selector.html', menus=menus, selected=selected)


@app.route('/menus/select', methods=['POST'])
def menus_select() -> Any:
    global MENU_NAME, MENU_PATH
    selected = request.form.get('menu_file')
    if not selected:
        return redirect(url_for('menus_view'))
    src = os.path.join(os.path.dirname(__file__), 'menu_list', selected)
    try:
        # Do NOT modify any files in `menu_list` — set the active menu path to the selected file instead.
        MENU_PATH = os.path.join(os.path.dirname(__file__), 'menu_list', selected)
        MENU_NAME = os.path.splitext(selected)[0]
        # persist the choice into config.json so next run uses the selected menu
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg['menu_path'] = os.path.join('menu_list', selected)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Fehler beim Auswählen der Speisekarte: {e}", 500
    # redirect back to selector with confirmation
    return redirect(url_for('menus_view', selected=MENU_NAME))


@app.route('/menus/upload', methods=['POST'])
def menus_upload() -> Any:
    # handle JSON file uploads to the menu_list folder
    # First, support replace/cancel actions from the confirmation page (these posts may not include a file)
    replace = request.form.get('replace')
    form_filename = request.form.get('filename')
    menu_dir = os.path.join(os.path.dirname(__file__), 'menu_list')
    os.makedirs(menu_dir, exist_ok=True)

    if replace in ('1', '2') and form_filename:
        filename = secure_filename(form_filename)
        dest = os.path.join(menu_dir, filename)
        tmpflag = os.path.join(menu_dir, filename + '.upload')
        if replace == '1':
            # user confirmed replace; move temp upload if present
            if os.path.exists(tmpflag):
                os.replace(tmpflag, dest)
            return redirect(url_for('menus_view', selected=os.path.splitext(filename)[0]))
        else:
            # user cancelled: remove temporary upload if exists
            if os.path.exists(tmpflag):
                os.remove(tmpflag)

            return redirect(url_for('menus_view'))

    # Otherwise expect a file upload
    if 'menu_file' not in request.files:
        return redirect(url_for('menus_view'))
    f = request.files['menu_file']
    if not f or f.filename == '':
        return redirect(url_for('menus_view'))
    filename = secure_filename(f.filename)
    if not filename.lower().endswith('.json'):
        return "Nur .json Dateien erlaubt", 400

    dest = os.path.join(menu_dir, filename)

    # If file exists, save uploaded file to a temp and ask for confirmation
    tmpflag = os.path.join(menu_dir, filename + '.upload')
    if os.path.exists(dest):
        f.save(tmpflag)
        return render_template('menu_upload_confirm.html', filename=filename)

    # otherwise save directly
    f.save(dest)
    return redirect(url_for('menus_view', selected=os.path.splitext(filename)[0]))


@app.route('/fulfilled/<order_id>', methods=['POST'])
def fulfilled(order_id: str) -> Any:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # flip printed state
    cur.execute('SELECT fulfilled FROM orders WHERE id = ?', (order_id,))
    row = cur.fetchone()
    if row:
        new = time.strftime("%Y_%m_%d-%H:%M:%S") if row[0] == '--' else '--'
        cur.execute('UPDATE orders SET fulfilled = ? WHERE id = ?', (new, order_id))
        conn.commit()
    conn.close()
    # If this is an AJAX request, return JSON so the client can update in place
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (request.headers.get('Accept') or ''):
        return {'status': 'ok', 'fulfilled': (new if row else "--")}
    return redirect(url_for('orders_view'))


@app.route('/cooked/<order_id>', methods=['POST'])
def cooked(order_id: str) -> Any:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT cooked FROM orders WHERE id = ?', (order_id,))
    row = cur.fetchone()
    if row:
        new = time.strftime("%Y_%m_%d-%H:%M:%S") if row[0] == '--' else '--'
        cur.execute('UPDATE orders SET cooked = ? WHERE id = ?', (new, order_id))
        conn.commit()
    conn.close()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (request.headers.get('Accept') or ''):
        return {'status': 'ok', 'cooked': (new if row else "--")}
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
        lines.append(f"{qty}x {name}")
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
