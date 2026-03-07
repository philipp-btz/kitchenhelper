import kitchenhelper as kh
from escpos.printer import Network

printer = Network("192.168.8.188", port=9100, profile="ITPP047")


