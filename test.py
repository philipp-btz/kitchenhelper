import printutil
from escpos.printer import Network
import json

printer = Network("192.168.1.187", port=9100, profile = "TM-T88V")

items = [
  {
    "name": "Schnitzel mit Brötchen",
    "extras": [
      "Extra Soße"
    ],
    "qty": 3,
    "printer": 1
  },
  {
    "name": "Pommes Frites",
    "extras": [],
    "qty": 2,
    "printer": 1
  },
  {
    "name": "Currywurst",
    "extras": [
      "Keine Soße"
    ],
    "qty": 1,
    "printer": 1
  },
  {
    "name": "Currywurst",
    "extras": [
      "Extra Pommes"
    ],
    "qty": 1,
    "printer": 1
  },
  {
    "name": "Currywurst",
    "extras": [],
    "qty": 3,
    "printer": 1
  }
]




# Head
p = printer
# Stelle sicher, dass die Codepage auf PC437 oder CP850 steht
#p.charcode('PC437') 

# Das Zeichen für die horizontale Linie (Box Drawing Light Horizontal)
line_char = u'\u2500' 
p.text(u"\u2500" * 48 + "\n")
p.text("Bestellung #12345\n")
p.text(bytes([196] * 32).decode('cp437') + "\n")
p.text("Tisch: 5\n")

# Cut
printer._raw(b"\x1D\x56\x42\x00")

printer.close()

