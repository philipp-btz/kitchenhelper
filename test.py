import printutil
from escpos.printer import Network

printer = Network("192.168.1.187", port=9100, profile = "POS-5890")
print(type(printer.paper_status()))