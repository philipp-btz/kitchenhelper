from escpos.printer import Network
import datetime
import threading
import logging
import sqlite3
import json

# Default DB path (can be overridden by importing module and setting DB_PATH)
DB_PATH = globals().get("DB_PATH", "orders.db")

class Quemanager:
    def __init__(self, printer_ip: str, printer_name: str):
        self.printer_ip = printer_ip
        self.printer_name = printer_name
        self.queue = []
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

        # WHERE String configuration
        if self.printer_name == "customer":
            self.WHERE_string = " WHERE (printed_customer = 0 OR printed_customer = 'False' OR printed_customer = 'false')"
        else:
            self.WHERE_string = f" WHERE (printed_kitchen = 0 OR printed_kitchen = 'False' OR printed_kitchen = 'false') AND kitchen = '{self.printer_name}' "

        # UPDATE String configuration
        if self.printer_name == "customer":
            self.UPDATE_string = "UPDATE orders SET printed_customer = 1 WHERE order_number = ?"
        else:
            self.UPDATE_string = "UPDATE orders SET printed_kitchen = 1 WHERE order_number = ?"

    def add_to_queue(self, func, kwargs: dict | None = None):
        """Add a callable print job to the queue.

        func: a callable like `print_test` or `print_customer`.
        kwargs: a dict of keyword args to pass to func when executed.
        """
        if kwargs is None:
            kwargs = {}
        with self.lock:
            self.queue.append((func, kwargs))
    
    def process_queue(self):
        """Immediately process all queued jobs (blocking).

        This is kept for manual / test usage. The background worker
        processes one job per minute automatically.
        """
        while True:
            with self.lock:
                if not self.queue:
                    break
                func, kwargs = self.queue.pop(0)
            try:
                #func(**kwargs)
                processing_thread = threading.Thread(target=func, kwargs=kwargs)
                processing_thread.start()
            except Exception:
                logging.exception("Error while processing print job")

    def _worker(self):
        """Background worker: process one job, then wait up to 60s."""
        while not self._stop_event.is_set():
            
            job = None
            with self.lock:
                if self.queue:
                    job = self.queue[0]  # Peek at the first job without popping
            if job:
                func, kwargs = job
                successful = func(**(kwargs or {}))
                if successful:
                    # Remove job from queue
                    self.queue.pop(0)
                    print("Job completed successfully, removed from queue.")

                    # If job contained an order, try to mark it as printed in DB
                    try:
                        order_no = None
                        if kwargs:
                            if "order" in kwargs and isinstance(kwargs["order"], dict):
                                order_no = kwargs["order"].get("order_number")
                            elif "order_number" in kwargs:
                                order_no = kwargs.get("order_number")

                        if order_no is not None:
                            conn_upd = sqlite3.connect(DB_PATH)
                            cur_upd = conn_upd.cursor()
                            cur_upd.execute(
                                self.UPDATE_string,
                                (order_no,)
                            )
                            conn_upd.commit()
                            conn_upd.close()
                    except Exception:
                        logging.exception("Failed to update printed_customer for order %s", order_no)

                if self._stop_event.wait(2):
                    break
            else:
                # no job, sleep briefly and check again
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                # Select order_numbers for orders matching this manager's WHERE clause
                cur.execute(
                    "SELECT order_number FROM orders "
                    f"{self.WHERE_string}"
                    "ORDER BY order_number ASC"
                )

                rows = cur.fetchall()
                #print(f"Found {len(rows)} unprinted orders for printer {self.printer_name} with WHERE clause: {self.WHERE_string}")
                for r in rows:
                    order_no = r[0]
                    # try to atomically reserve the order for this manager
                    try:
                        if self.printer_name == "customer":
                            reserve_sql = (
                                "UPDATE orders SET printed_customer = 2 "
                                "WHERE order_number = ? AND (printed_customer = 0 OR printed_customer = 'False' OR printed_customer = 'false')"
                            )
                            cur.execute(reserve_sql, (order_no,))
                        else:
                            reserve_sql = (
                                "UPDATE orders SET printed_kitchen = 2 "
                                "WHERE order_number = ? AND (printed_kitchen = 0 OR printed_kitchen = 'False' OR printed_kitchen = 'false') AND kitchen = ?"
                            )
                            cur.execute(reserve_sql, (order_no, self.printer_name))

                        if cur.rowcount:
                            conn.commit()
                            # fetch full row to enqueue
                            cur2 = conn.cursor()
                            cur2.row_factory = sqlite3.Row
                            cur2.execute('SELECT * FROM orders WHERE order_number = ?', (order_no,))
                            full = cur2.fetchone()
                            order_dict = dict(full) if full else None
                            print(f"Reserved order {order_no} for printer {self.printer_name}: {order_dict}")
                            if order_dict:
                                if self.printer_name == "customer":
                                    self.add_to_queue(print_customer, kwargs={'order': order_dict, 'printer_ip': self.printer_ip})
                                else:
                                    self.add_to_queue(print_kitchen, kwargs={'order': order_dict, 'printer_ip': self.printer_ip})
                        # else: another worker reserved it already
                    except Exception:
                        logging.exception("Error reserving order %s", order_no)

                conn.close()

                if self._stop_event.wait(1):
                    break

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the background worker thread."""
        self._stop_event.set()
        try:
            self._worker_thread.join(timeout)
        except RuntimeError:
            pass






def print_test(*, text = "Testdruck", printer_ip: str = "192.168.1.187") -> None:
    try:
        printer = Network(printer_ip, port=9100, profile = "POS-5890")
        if printer.paper_status == "0":
            print("Printer is out of paper!")
            return False
        printer.text(str(text) + "\n")
        printer.close()
        return True
    except Exception as e:
        print("Error while printing test receipt:" + str(e))
        return False



def print_customer(*, order: dict, printer_ip: str ) -> None:
    print(f"PRINTING CUSTOMER for printer {printer_ip}")
    try:
        
        order_NO = order.get("order_number", "Unbekannt")
        notes = order.get("notes", "")
        items = order.get("items", [])

        printer = Network(printer_ip, port=9100, profile = "POS-5890")
        print(f"printer.paper_status: {printer.paper_status()}, type: {type(printer.paper_status())}")
        if printer.paper_status == 0:
            print("Printer is out of paper!")
            return False
        
        
        #HEADER
        printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
        printer.text("Bei Fallers\n")
        printer.image("icon.png", center=True)

        # Order NR
        printer.text(f"\n\nNr: {order_NO}\n\n")

        # order items
        printer.set(font="a",align="left", bold=True, normal_textsize=True)
        if type(items) != list:
            items = json.loads(items)  # Try to convert to list if it's not already

        for item in items:
            printer.text(f"{item['qty']}x {item['name']}\n")
            for extra in item["extras"]:
                printer.text(f"  {extra}\n")

        # Notes
        printer.set(align="left", invert=False, bold=True, double_height=True, double_width=True)
        printer.text(f"\n\n{notes}\n\n") if notes else printer.text("\n")


        printer.set(align="center")
        printer.qr("https://youtu.be/dQw4w9WgXcQm", size=4)
        printer.set(align="center", invert=False, bold=True, double_height=True, double_width=True)
        printer.text("Vielen Dank für Ihre \nBestellung!\n")

        # aux Infos
        printer.set(align="left", normal_textsize=True)
        printer.text(f"\n\nBestellzeit: {order.get('created_at', 'Unbekannt')}\n")
        printer.text(f"customer: {order.get('customer_id', 'Unbekannt')}\n")

        # Cut
        printer._raw(b"\x1D\x56\x42\x00")

        printer.close()

        return True
    
    except Exception:
        print("Error while printing customer receipt:" + str(Exception))
        return False

def print_kitchen(*, order: dict, printer_ip: str) -> None:
    print(f"PRINTING KITCHEN for printer {printer_ip}")
    try:
        order_NO = order.get("order_number", "Unbekannt")
        notes = order.get("notes", "")
        items = order.get("items", [])

        

        printer = Network(printer_ip, port=9100, profile = "POS-5890")

        if printer.paper_status == 0:
            print("Printer is out of paper!")
            return False
        
        if type(items) != list:
            items = json.loads(items)  # Try to convert to list if it's not already

        if len(items) == 1 and items[0]["qty"] ==1:
            printer.set(invert=True, font="a", height=2, width=3, custom_size=True, align="center", bold=True)
            printer.text("XXXXXXXXXXXXXXXX")
        
        
        # Order NR
        printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
        printer.text(f"\n\nNr: {order_NO}\n\n")

        # order items
        printer.set(font="a",align="left", bold=True, normal_textsize=True, double_height=True, double_width=True, invert=False)

        for item in items:
            printer.text(f"{item['qty']}x {item['name']}\n")
            for extra in item["extras"]:
                printer.text(f"  {extra}\n")

        # Notes
        printer.set(align="center", invert=True, bold=True, double_height=True, double_width=True)
        printer.text(f"\n\n{notes}\n\n") if notes else printer.text("\n")


        printer.set(align="center")

        # aux Infos
        printer.set(align="left", invert=False, normal_textsize=True)
        printer.text(f"\n\nBestellzeit: {order.get('created_at', 'Unbekannt')}\n")
        printer.text(f"customer: {order.get('customer_id', 'Unbekannt')}\n")

        # Cut and buzzer
        printer.ln(5)
        printer._raw(b"\x1D\x56\x42\x00")
        printer.buzzer(times = 2, duration=4)

        printer.close()

        return True
    
    except Exception:
        print("Error while printing kitchen receipt:" + str(Exception))
        return False

def print_report(*,  order: dict, printer_ip: str) -> None:
    print("PRINTING REPORT")
    try:
        date = order.get("date", "Unbekannt")
        item_map = order.get("item_map", {})
        extras_total = order.get("extras_total", {})

        

        printer = Network(printer_ip, port=9100, profile = "POS-5890")



        printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
        printer.text(f"\n\nTagesbericht: \n{date}\n\n")
        printer.set(font="a",align="left", bold=True, normal_textsize=True, double_height=False, double_width=False, invert=False)
        printer.text(f"Gedruckt am: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        printer.text("\nBestellte Gerichte:\n")
        for key in item_map.keys():
            qty = item_map[key]["count"]
            printer.text(f"  {str(qty)}x {str(key)}\n")
            for extra in item_map[key]["extras"].keys():
                printer.text(f"    {item_map[key]['extras'][extra]}x {str(extra)}\n")

        if extras_total:
            printer.text("\nExtras gesammt:\n")
            for extra, qty in extras_total.items():
                printer.text(f"  {str(qty)}x {str(extra)}\n")

        

        # Cut and buzzer
        printer.ln(5)
        printer._raw(b"\x1D\x56\x42\x00")

        printer.close()

        return True
    
    except Exception:
        print("Error while printing report:" + str(Exception))
        return False


