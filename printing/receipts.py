import json
import time
from datetime import datetime
from typing import Any


def _parse_items(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, str):
        return json.loads(items)
    return items or []


def format_kitchen(printer: Any, order: dict[str, Any], settings: dict[str, Any]) -> None:
    items = _parse_items(order.get("items", []))
    order_no = order.get("order_number", "?")
    notes = order.get("notes", "")

    printer.set_with_default()

    if len(items) == 1 and items[0].get("qty", 1) == 1:
        printer.set(invert=True, font="a", height=2, width=3, custom_size=True, align="center", bold=True)
        printer.text("EINZELBESTELLUNG")

    printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
    printer.text(f"\n\nNr: {order_no}\n\n")

    printer.set(font="a", align="left", bold=True, normal_textsize=True,
                double_height=True, double_width=True, invert=False)
    printer.text("\u2500" * 24 + "\n")
    for item in items:
        printer.text(f"{item.get('qty', 1)}x {item.get('name', '')}\n")
        for extra in (item.get("extras") or []):
            printer.text(f"  {extra}\n")
    printer.text("\u2500" * 24 + "\n")

    if notes:
        printer.set(align="center", invert=True, bold=True, double_height=True, double_width=True)
        printer.text(f"\n\n{notes}\n\n")

    printer.set(align="left", invert=False, normal_textsize=True)
    printer.text(f"\nBestellzeit: {order.get('created_at', '')}\n")
    printer.text(f"Kunde: {order.get('customer_id', '')}\n")

    printer.ln(4)
    printer._raw(b"\x1D\x56\x42\x00")

    if settings.get("kitchen_buzzer"):
        printer.buzzer(times=2, duration=4)


def format_customer(printer: Any, order: dict[str, Any], settings: dict[str, Any]) -> None:
    items = _parse_items(order.get("items", []))
    order_no = order.get("order_number", "?")
    notes = order.get("notes", "")
    count = 2 if settings.get("print_customer_double") else 1

    for _ in range(count):
        printer.set_with_default()
        printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
        printer.image("static/icon_beifallers.png", center=False)
        time.sleep(0.5)
        printer.text(f"\nNr: {order_no}\n\n")

        printer.set(font="a", align="left", bold=True, normal_textsize=True)
        printer.text("\u2500" * 48 + "\n")
        for item in items:
            printer.text(f"{item.get('qty', 1)}x {item.get('name', '')}\n")
            for extra in (item.get("extras") or []):
                printer.text(f"  {extra}\n")
        printer.text("\u2500" * 48 + "\n")

        if notes:
            printer.set(align="left", bold=True, normal_textsize=True)
            printer.text(f"\n{notes}\n\n")
        else:
            printer.text("\n")

        printer.set(align="center")
        printer.qr("https://share.google/97GUBhxCRPvn9ZpVY", size=5)
        printer.set(align="center", invert=False, bold=True, double_height=False, double_width=True)
        printer.text("Vielen Dank für Ihre \nBestellung!\n")

        printer.set(align="left", normal_textsize=True)
        printer.text(f"\nBestellzeit: {order.get('created_at', '')}\n")
        printer.text(f"Kunde: {order.get('customer_id', '')}\n")
        printer._raw(b"\x1D\x56\x42\x00")

    if settings.get("print_extra_order_nr"):
        printer.set_with_default(font="a", height=2, width=3, custom_size=True,
                                 align="center", bold=True, smooth=True)
        printer.text(f"\n\n\n\nNr: {order_no}\n\n\n\n\n")
        printer._raw(b"\x1D\x56\x42\x00")


def format_report(printer: Any, data: dict[str, Any]) -> None:
    printer.set_with_default()
    printer.set(font="a", height=2, width=3, custom_size=True, align="center", bold=True, smooth=True)
    printer.text(f"\n\nBericht:\n{data.get('from', '')} –\n{data.get('to', '')}\n\n")

    printer.set(font="a", align="left", bold=True, normal_textsize=True,
                double_height=False, double_width=False, invert=False)
    printer.text(f"Gedruckt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    printer.text("\nBestellte Gerichte:\n")

    for name, info in data.get("item_map", {}).items():
        printer.text(f"  {info['count']}x {name}\n")
        for extra, qty in info.get("extras", {}).items():
            printer.text(f"    {qty}x {extra}\n")

    if data.get("extras_total"):
        printer.text("\nExtras gesamt:\n")
        for extra, qty in data["extras_total"].items():
            printer.text(f"  {qty}x {extra}\n")

    printer.ln(5)
    printer._raw(b"\x1D\x56\x42\x00")
