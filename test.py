
import argparse
import sys
import time
from escpos.printer import Network

printer = Network("192.168.8.189", port=9100, profile = "TM-T88V")

printer.text("Hello World\n")
printer.text("This is a test\n")
printer.text("This is a test\n")
printer.text("This is a test\n")
printer.text("This is a test\n")
printer.image("icon.png")
printer.text("This is a test\n")