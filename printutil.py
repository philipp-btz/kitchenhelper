from escpos.printer import Network
import datetime
import time
import threading
import logging
import sqlite3
import json
import os

import kitchenhelper as kh


class Queuemanager:

    def __init__(self, printer_ip: str, printer_name: str):
        self.printer_ip = printer_ip
        self.printer_name = printer_name
        self.printer_model = "TM-T88V"
        print(f"Initialized Queuemanager for printer '{self.printer_name}' at IP {self.printer_ip}")
        self.queue = []
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self._printer = None
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)

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

        self._worker_thread.start()

    @property
    def printer(self):
        """
        Gibt das Drucker-Objekt zurück. Prüft vorher, ob es existiert und online ist.
        Baut die Verbindung bei Bedarf automatisch neu auf.
        """
        # Prüfe zuerst auf None, um AttributeError beim allerersten Aufruf zu vermeiden
        try:
            if self._printer is None or self._printer.is_online() is False:
                try:
                    self._printer = Network(self.printer_ip, port=9100, profile=self.printer_model)
                except Exception as e:
                    logging.error(f"Fehler bei der Drucker-Verbindung ({self.printer_name}): {e}")
            return self._printer
        except:
            self._printer=Network(self.printer_ip, port=9100, profile=self.printer_model)
            return self._printer


    def add_to_queue(self, func: str, kwargs: dict | None = None):
        """Add a callable print job to the queue.

        func: a callable like `print_test` or `print_customer`.
        kwargs: a dict of keyword args to pass to func when executed.
        """
        if kwargs is None:
            kwargs = {}
        with self.lock:
            self.queue.append((func, kwargs))

    def _worker(self):
        """Background worker: process one job, then wait up to 60 Seconds."""
        id = threading.get_ident()
        time_checkpoint = time.time()
        while not self._stop_event.is_set():
            #print(f"_worker {id} working; printer: {self.printer_name}, online: {self.printer.is_online()}, paper status: {self.printer.paper_status()}")
            if time.time() - time_checkpoint > 60:
                #self.printer.text(" ")
                self.printer.set_with_default()
                time_checkpoint = time.time()
                print(f"{datetime.datetime.now()} PRINTER keepalive check; by {self.printer_name}")
            job = None
            db_path = kh.get_db_path()
            with self.lock:
                if self.queue:
                    job = self.queue[0]  # Peek at the first job without popping
            if job:
                func, kwargs = job

                successful = False
                if func == "customer":
                    successful = self.print_customer(**(kwargs or {}))
                elif func == "kitchen":
                    successful = self.print_kitchen(**(kwargs or {}))
                elif func == "report":
                    successful = self.print_report(**(kwargs or {}))
                elif func == "test":
                    successful = self.print_test(**(kwargs or {}))
                else:
                    print("ABCABCABC")
                    logging.warning(f"Unknown job function: {func}")
                    successful = self.print_test(
                        text=f"Unknown job function: {func}\n" * 20 + "Please check the printer configuration and logs." + "\n" * 20)
                if successful:
                    # Remove job from queue
                    self.queue.pop(0)
                    logging.info("Job completed successfully, removed from queue.")

                    # If job contained an order, try to mark it as printed in DB
                    order_no = None
                    try:
                        if kwargs:
                            if "order" in kwargs and isinstance(kwargs["order"], dict):
                                order_no = kwargs["order"].get("order_number")
                            elif "order_number" in kwargs:
                                order_no = kwargs.get("order_number")

                        if order_no is not None:
                            conn_upd = sqlite3.connect(db_path)
                            cur_upd = conn_upd.cursor()
                            cur_upd.execute(
                                self.UPDATE_string,
                                (order_no,)
                            )
                            conn_upd.commit()
                            conn_upd.close()
                    except Exception as e:
                        print("RRRRRRRRRRR")
                        logging.exception(f"Failed to update printed_customer for order {order_no}: {e}")

                if self._stop_event.wait(0.5):
                    break
            else:
                # no job, sleep briefly and check again
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                # Select order_numbers for orders matching this manager's WHERE clause
                cur.execute(
                    "SELECT order_number FROM orders "
                    f"{self.WHERE_string}"
                    "ORDER BY order_number ASC"
                )

                rows = cur.fetchall()
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
                            if order_dict:
                                if self.printer_name == "customer":
                                    self.add_to_queue("customer", kwargs={'order': order_dict})
                                else:
                                    self.add_to_queue("kitchen", kwargs={'order': order_dict})
                        # else: another worker reserved it already
                    except Exception as e:
                        logging.exception(f"Error reserving order {order_no}: {e}")

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
        return

    def print_test(self, *, text="Testdruck") -> bool:
        printer = self.printer
        try:
            try:
                if printer.paper_status() == "0":
                    logging.warning("Printer is out of paper!")
                    return False
            except Exception as e:
                logging.error(f"Error checking printer status for {self.printer_name}: {e}")
                return False
            printer.text(str(text) + "\n")

            return True
        except Exception as e:
            logging.exception(f"Error while printing test receipt: {e}")
            return False

    def print_customer(self, *, order: dict) -> bool:
        printer = self.printer
        logging.info(f"PRINTING CUSTOMER for printer {printer}")
        try:

            order_no = order.get("order_number", "Unbekannt")
            notes = order.get("notes", "")
            items = order.get("items", [])

            try:
                if printer.paper_status() == 0 or not printer.is_online():
                    logging.warning(f"Printer {self.printer_name} is offline or out of paper.")
                    return False
            except Exception as e:
                logging.error(f"Error checking printer status for {self.printer_name}: {e}")
                return False

            # reset Font
            printer.set_with_default()

            # Head
            printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
            printer.image("icon.png", center=False)
            time.sleep(0.5)  # Short delay to ensure image is processed before printing text
            printer.text(f"\nNr: {order_no}\n\n")

            # order items
            printer.set(font="a", align="left", bold=True, normal_textsize=True)
            if type(items) != list:
                items = json.loads(items)  # Try to convert to list if it's not already

            printer.text(u"\u2500" * 48 + "\n")

            for item in items:
                printer.text(f"{item['qty']}x {item['name']}\n")
                for extra in item["extras"]:
                    printer.text(f"  {extra}\n")

            printer.text(u"\u2500" * 48 + "\n")

            # Notes
            printer.set(align="left", bold=True, normal_textsize=True)
            printer.text(f"\n{notes}\n\n") if notes else printer.text("\n")

            # TODO wenn es eine webseite gibt, hier Qr Code
            printer.set(align="center")
            printer.qr("https://youtu.be/dQw4w9WgXcQm", size=4)
            printer.set(align="center", invert=False, bold=True, double_height=False, double_width=True)
            printer.text("Vielen Dank für Ihre \nBestellung!\n")

            # aux Infos
            printer.set(align="left", normal_textsize=True)
            printer.text(f"\nBestellzeit: {order.get('created_at', 'Unbekannt')}\n")
            printer.text(f"customer: {order.get('customer_id', 'Unbekannt')}\n")

            # Cut
            printer._raw(b"\x1D\x56\x42\x00")

            return True

        except Exception as e:
            logging.exception(f"Error while printing customer receipt: {e}")
            return False

    def print_kitchen(self, *, order: dict) -> bool:
        printer = self.printer
        time.sleep(1)  # Short delay to ensure printer is ready
        logging.info(f"PRINTING KITCHEN for printer {printer}")
        try:
            order_no = order.get("order_number", "Unbekannt")
            notes = order.get("notes", "")
            items = order.get("items", [])

            try:
                if printer.paper_status() == 0 or not printer.is_online():
                    logging.warning(f"Printer {self.printer_name} is offline or out of paper.")
                    return False
            except Exception as e:
                logging.error(f"Error checking printer status for {self.printer_name}: {e}")
                return False

            # reset Font
            printer.set_with_default()

            if type(items) != list:
                items = json.loads(items)  # Try to convert to list if it's not already

            if len(items) == 1 and items[0]["qty"] == 1:
                printer.set(invert=True, font="a", height=2, width=3, custom_size=True, align="center", bold=True)
                printer.text("EINZELBESTELLUNG")

            # Order NR
            printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
            printer.text(f"\n\nNr: {order_no}\n\n")

            # order items
            printer.set(font="a", align="left", bold=True, normal_textsize=True, double_height=True, double_width=True,
                        invert=False)

            printer.text(u"\u2500" * 24 + "\n")

            for item in items:
                printer.text(f"{item['qty']}x {item['name']}\n")
                for extra in item["extras"]:
                    printer.text(f"  {extra}\n")

            printer.text(u"\u2500" * 24 + "\n")

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
            printer.buzzer(times=2, duration=4)

            return True

        except Exception as e:
            logging.exception(f"Error while printing kitchen receipt: {e}")
            return False

    def print_report(self, *, order: dict) -> bool:
        printer = self.printer
        time.sleep(1)  # Short delay to ensure printer is ready
        logging.info("PRINTING REPORT")
        try:
            date = order.get("date", "Unbekannt")
            item_map = order.get("item_map", {})
            extras_total = order.get("extras_total", {})

            # reset Font
            printer.set_with_default()

            printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
            printer.text(f"\n\nTagesbericht: \n{date}\n\n")
            printer.set(font="a", align="left", bold=True, normal_textsize=True, double_height=False,
                        double_width=False, invert=False)
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

            return True

        except Exception as e:
            logging.exception(f"Error while printing report: {e}")
            return False
