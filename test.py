import time
import kitchenhelper as kh
from escpos.printer import Network

printer = Network("192.168.8.188", port=9100, profile="TM-T88V")

while True:
    print(f"Printer is Usable {printer.is_usable()}")
    print(f"Printer is Online {printer.is_online()}")
    print(f"Paper Status {printer.paper_status()}")
    print(printer._raw(b"\x10\x04\x01"))
    time.sleep(0.5)


