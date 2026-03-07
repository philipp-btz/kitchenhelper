from flask import Flask, render_template, request, redirect, url_for, Response
import json
import os
import datetime
import time
import uuid
import sqlite3
from werkzeug.utils import secure_filename
from typing import Any, Dict, List, Optional, cast
import menu_picker as mp
import logging
from logging.handlers import RotatingFileHandler
import sys

import printutil
import kitchenhelper as kh

# --- optionally set a secret key if you later want sessions/CSRF ---
# app.secret_key = os.environ.get("FLASK_SECRET_KEY", "CHANGE_ME")


LOGGING_DEBUG = False

if LOGGING_DEBUG:
    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d) %(funcName)s() - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler = RotatingFileHandler(
        "log.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

logging.info("Starting Kitchen Helper application")

config: Dict[str, Any] = kh.load_config()

kh.init_db()
kh.clear_db_reservations()

printer_manager_dict = {}

# Only initialize printer managers in the main Flask worker process,
# to avoid spawning multiple threads when Flask's reloader is active.
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not config.get('debug', True):
    for key in config.get("printer_dict", {}):
        print(f"Creating printer manager for key: {key}")
        printer_manager_dict[key] = printutil.Queuemanager(printer_ip=config["printer_dict"][key], printer_name=key)
    logging.info(f"printer_manager_dict: {printer_manager_dict}")


printer_dict = config.get("printer_dict", {})
logging.info(f"printer_dict: {printer_dict}")

app = Flask(__name__)


def update_order(
        order_number: int, items: Optional[List[Dict[str, Any]]] = None, notes: Optional[str] = None,
        printed: Optional[bool] = None
        ) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(kh.get_db_path())
    cur = conn.cursor()
    fields: List[str] = []
    params: List[Any] = []
    if items is not None:
        # enrich items with printer info before storing
        items = kh.enrich_items(items)
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
    sql = f"UPDATE orders SET {', '.join(fields)}ù WHERE order_number = ?"
    cur.execute(sql, tuple(params))
    conn.commit()
    conn.close()
    return kh.get_order_by_number(order_number)


@app.route('/')
def index() -> Any:
    menu = kh.load_menu()
    return render_template('index.html', menu=menu, menu_name=kh.get_menu_name())


@app.route('/order', methods=['POST'])
def order() -> Any:
    global printer_manager_dict
    # Expect a JSON string in form field 'items' describing an array of ordered dishes
    data = request.form
    items_json = data.get('items')
    notes = data.get('notes', '')
    try:
        items = kh.enrich_items(cast(List[Dict[str, Any]], json.loads(items_json)) if items_json else [])
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
        logging.info(f"ORDER NUMBER PROVIDED, UPDATING EXISTING ORDER {order_number}")
        updated = update_order(order_number, items=items, notes=notes, printed=False)
        order_number = updated.get('order_number') if updated else order_number
    else:
        customer_id = str(uuid.uuid4())

        # group items by printer and create a separate order for each printer
        for printer in set(it.get('printer') for it in items if it.get('printer')):
            items_for_printer = [it for it in items if it.get('printer') == printer]
            order: Dict[str, Any] = {
                'id': str(uuid.uuid4()),
                'items': items_for_printer,
                'notes': notes,
                'created_at': time.strftime("%Y_%m_%d-%H:%M:%S"),
                'printed_kitchen': False,
                'printed_customer': False,
                'customer_id': customer_id,
                'kitchen': str(printer),
            }
            order = kh.save_order(order)
            current_order_nr = str(order.get('order_number'))

            order_numbers = order_numbers + " + " + current_order_nr

    # if this is an AJAX request, return JSON so the client can stay on the menu page
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (
            request.headers.get('Accept') or ''):
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
        'printed_kitchen': False,
        'printed_customer': False,
    }
    saved = kh.save_order(draft)
    return {'order_number': saved.get('order_number'), 'id': saved.get('id')}


@app.route('/orders')
def orders_view() -> Any:
    orders = kh.get_orders()
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
    # optional confirmation from query string
    selected = request.args.get('selected')
    return render_template('menu_selector.html', menus=menus, selected=selected)


@app.route('/menus/select', methods=['POST'])
def menus_select() -> Any:
    selected = request.form.get('menu_file')
    if not selected:
        return redirect(url_for('menus_view'))
    src = os.path.join(os.path.dirname(__file__), 'menu_list', selected)
    try:
        os.environ["KITCHENHELPER_MENU_PATH"] = os.path.join(os.path.dirname(__file__), 'menu_list', selected)
        menu_name = os.path.splitext(selected)[0]
        os.environ["KITCHENHELPER_MENU_NAME"] = menu_name

        # persist the choice into config.json so next run uses the selected menu
        try:
            with open(os.environ.get("KITCHENHELPER_CONFIG_PATH", "config.json"), 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg['menu_path'] = os.path.join('menu_list', selected)
        with open(os.environ.get("KITCHENHELPER_CONFIG_PATH", "config.json"), 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Fehler beim Auswählen der Speisekarte: {e}", 500
    # redirect back to the selector with confirmation
    return redirect(url_for('menus_view', selected=menu_name))


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
            # user canceled: remove temporary upload if exists
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

    # If the file exists, save the uploaded file to a temp and ask for confirmation
    tmpflag = os.path.join(menu_dir, filename + '.upload')
    if os.path.exists(dest):
        f.save(tmpflag)
        return render_template('menu_upload_confirm.html', filename=filename)

    # otherwise save directly
    f.save(dest)
    return redirect(url_for('menus_view', selected=os.path.splitext(filename)[0]))


@app.route('/fulfilled/<order_id>', methods=['POST'])
def fulfilled(order_id: str) -> Any:
    conn = sqlite3.connect(kh.get_db_path())
    cur = conn.cursor()
    # flip printed state
    cur.execute('SELECT fulfilled FROM orders WHERE id = ?', (order_id,))
    row = cur.fetchone()
    timestamp = time.strftime("%Y_%m_%d-%H:%M:%S") if row[0] == '--' else '--'
    if row:
        cur.execute('UPDATE orders SET fulfilled = ? WHERE id = ?', (timestamp, order_id))
        conn.commit()
    conn.close()
    # If this is an AJAX request, return JSON so the client can update in place
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (
            request.headers.get('Accept') or ''):
        return {'status': 'ok', 'fulfilled': (timestamp if row else "--")}
    return redirect(url_for('orders_view'))


@app.route('/cooked/<order_id>', methods=['POST'])
def cooked(order_id: str) -> Any:
    conn = sqlite3.connect(kh.get_db_path())
    cur = conn.cursor()
    cur.execute('SELECT cooked FROM orders WHERE id = ?', (order_id,))
    row = cur.fetchone()
    timestamp = time.strftime("%Y_%m_%d-%H:%M:%S") if row[0] == '--' else '--'
    if row:
        cur.execute('UPDATE orders SET cooked = ? WHERE id = ?', (timestamp, order_id))
        conn.commit()
    conn.close()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (
            request.headers.get('Accept') or ''):
        return {'status': 'ok', 'cooked': (timestamp if row else "--")}
    return redirect(url_for('orders_view'))


@app.route('/api/cooked_unfulfilled')
def api_cooked_unfulfilled() -> Any:
    """Return a JSON list of order_numbers that are cooked but not yet fulfilled."""
    conn = sqlite3.connect(kh.get_db_path())
    cur = conn.cursor()
    cur.execute("SELECT order_number FROM orders WHERE cooked IS NOT NULL AND cooked != '--' AND (fulfilled IS NULL OR fulfilled = '--') ORDER BY order_number ASC")
    rows = cur.fetchall()
    conn.close()
    nums = [r[0] for r in rows]
    return {'order_numbers': nums}


@app.route('/customer_display')
def customer_display_view() -> Any:
    # render the customer-facing page showing cooked-but-not-fulfilled orders
    return render_template('customer_display.html')


@app.route('/report/daily')
def report_daily() -> Any:
    # optional query param ?date=YYYY-MM-DD
    date = request.args.get('date')
    global printer_manager_dict
    for key, value in printer_manager_dict.items():
        print(f"Checking printer manager for key: {key}")
        if key == "customer":
            value.add_to_queue("report", kwargs={'order': kh.aggregate_day(date)})
    return redirect(url_for('orders_view'))


@app.route('/api/report/daily')
def api_report_daily() -> Any:
    date = request.args.get('date')
    data = kh.aggregate_day(date)
    return data


@app.route('/order/print_customer/<int:order_number>')
def order_print(order_number: int) -> Any:
    order = kh.get_order_by_number(order_number)
    if not order:
        return "Bestellung nicht gefunden", 404
    # Set printed_customer back to 0 for this order
    try:
        conn = sqlite3.connect(kh.get_db_path())
        cur = conn.cursor()
        cur.execute('UPDATE orders SET printed_customer = 0 WHERE order_number = ?', (order_number,))
        conn.commit()
        conn.close()
    except Exception:
        logging.exception("Failed to reset printed_customer for order %s", order_number)

    return redirect(url_for('orders_view'))


@app.route('/order/print_kitchen/<int:order_number>')
def order_print_kitchen(order_number: int) -> Any:
    order = kh.get_order_by_number(order_number)

    if not order:
        return "Bestellung nicht gefunden", 404
    # Set printed_kitchen back to 0 for this order
    try:
        conn = sqlite3.connect(kh.get_db_path())
        cur = conn.cursor()
        cur.execute('UPDATE orders SET printed_kitchen = 0 WHERE order_number = ?', (order_number,))
        conn.commit()
        conn.close()
    except Exception:
        import logging
        logging.exception("Failed to reset printed_kitchen for order %s", order_number)

    return redirect(url_for('orders_view'))


@app.route('/order/export/<int:order_number>')
def order_export(order_number: int) -> Response:
    order = kh.get_order_by_number(order_number)
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


# run the app
if __name__ == '__main__':
    app.run(debug=bool(config.get('debug', True)), host=config.get('host', '0.0.0.0'),
            port=int(config.get('port', 5099)))
