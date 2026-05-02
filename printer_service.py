"""
Standalone printer service.
Run this as a separate process/container. It owns all TCP connections to the
thermal printers and polls the shared SQLite DB for unprinted orders.
The web workers write orders to the DB; this process picks them up and prints.
"""
import os
import time
import logging

import kitchenhelper as kh
import printutil


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

config = kh.load_config()
kh.init_db()
kh.clear_db_reservations()

printer_mode = os.environ.get("KITCHENHELPER_PRINTER_MODE", "Thermo")
managers = {}
for key, ip in config.get("printer_dict", {}).items():
    logging.info(f"Starting printer manager: {key} @ {ip} ({printer_mode})")
    managers[key] = printutil.Queuemanager(
        printer_name=key,
        printer_ip=ip,
        printer_mode=printer_mode,
    )

logging.info("Printer service running.")

try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    logging.info("Shutting down printer service.")
    for m in managers.values():
        m.stop()