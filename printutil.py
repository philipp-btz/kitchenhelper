from escpos.printer import Network
import datetime

def print_test(*, text = "Testdruck", printer_ip: str = "192.168.1.187") -> None:
    printer = Network(printer_ip, port=9100, profile = "POS-5890")
    printer.text(str(text) + "\n")
    printer.close()


def print_customer(*, order: dict, printer_ip: str ) -> None:
    print("PRINTING CUSTOMER")
    order_NO = order.get("order_number", "Unbekannt")
    notes = order.get("notes", "")
    items = order.get("items", [])

    printer = Network(printer_ip, port=9100, profile = "POS-5890")

    #HEADER
    printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
    printer.text("Bei Fallers\n")
    printer.image("icon.png", center=True)

    # Order NR
    printer.text(f"\n\nNr: {order_NO}\n\n")

    # order items
    printer.set(font="a",align="left", bold=True, normal_textsize=True)
    for item in items:
        printer.text(f"{item['qty']}x {item['name']}\n")
        for extra in item["extras"]:
            printer.text(f"  {extra}\n")

    # Notes
    printer.set(align="center", invert=True, bold=True, double_height=True, double_width=True)
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

def print_kitchen(*, order: dict, printer_ip: str) -> None:
    print("PRINTING KITCHEN")
    order_NO = order.get("order_number", "Unbekannt")
    notes = order.get("notes", "")
    items = order.get("items", [])

    

    printer = Network(printer_ip, port=9100, profile = "POS-5890")

    if len(items) == 1 and items[0]["qty"] ==1:
        printer.set(invert=True)
    
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

def print_report(*,  order: dict, printer_ip: str) -> None:
    print("PRINTING REPORT")
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