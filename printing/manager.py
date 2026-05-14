import logging
import threading
import time
from typing import Any, Optional

import config
import db
from printing import receipts

_managers: dict[str, "QueueManager"] = {}


def register(name: str, ip: str, mode: str) -> "QueueManager":
    m = QueueManager(name, ip, mode)
    _managers[name] = m
    return m


def get_managers() -> dict[str, "QueueManager"]:
    return _managers


def get_manager(name: str) -> Optional["QueueManager"]:
    return _managers.get(name)


class QueueManager:
    def __init__(self, printer_name: str, printer_ip: str, printer_mode: str = "Dummy"):
        self.printer_name = printer_name
        self.printer_ip = printer_ip
        self.printer_mode = printer_mode
        self._printer = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._queue: list[tuple[str, dict]] = []
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"printer-{printer_name}"
        )
        self._thread.start()
        logging.info(f"QueueManager started: {printer_name} @ {printer_ip} ({printer_mode})")

    def enqueue(self, job: str, kwargs: dict | None = None) -> None:
        with self._lock:
            self._queue.append((job, kwargs or {}))

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    def _get_printer(self) -> Any:
        from escpos.printer import Dummy, Network
        if self._printer is None:
            if self.printer_mode == "Thermo":
                self._printer = Network(self.printer_ip, port=9100, profile="TM-T88V")
            else:
                self._printer = Dummy()
        return self._printer

    def _run(self) -> None:
        while not self._stop.is_set():
            job = None
            with self._lock:
                if self._queue:
                    job = self._queue[0]

            if job:
                func, kwargs = job
                ok = self._dispatch(func, kwargs)
                if ok:
                    with self._lock:
                        if self._queue and self._queue[0] == job:
                            self._queue.pop(0)
                if self._stop.wait(0.5):
                    break
            else:
                try:
                    self._poll_db()
                except Exception:
                    logging.exception(f"DB poll error ({self.printer_name})")
                if self._stop.wait(1):
                    break

    def _poll_db(self) -> None:
        with self._lock:
            queued_nrs = {
                kw.get("order", {}).get("order_number")
                for _, kw in self._queue
                if "order" in kw
            }
        if self.printer_name == "customer":
            orders = db.get_unprinted_customer()
            job_name = "customer"
        else:
            orders = db.get_unprinted_kitchen(self.printer_name)
            job_name = "kitchen"
        for order in orders:
            if order["order_number"] not in queued_nrs:
                self.enqueue(job_name, {"order": order})

    def _dispatch(self, func: str, kwargs: dict) -> bool:
        try:
            printer = self._get_printer()
            settings = config.load_settings()
            if func == "kitchen":
                receipts.format_kitchen(printer, kwargs["order"], settings)
                nr = kwargs["order"].get("order_number")
                if nr is not None:
                    db.mark_printed_kitchen(nr)
            elif func == "customer":
                receipts.format_customer(printer, kwargs["order"], settings)
                nr = kwargs["order"].get("order_number")
                if nr is not None:
                    db.mark_printed_customer(nr)
            elif func == "report":
                receipts.format_report(printer, kwargs["data"])
            else:
                logging.warning(f"Unknown job type: {func}")
            return True
        except Exception:
            logging.exception(f"Print error ({self.printer_name}, {func})")
            self._printer = None
            return False
