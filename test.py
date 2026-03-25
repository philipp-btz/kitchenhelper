from pathlib import Path
import os
import json
from escpos.printer import Network, Dummy

printer = Network("192.168.8.188", 9100, profile="TM-T88V")
printer.text("agsjkdhjasgdjahasgdjhasd\n"*10)