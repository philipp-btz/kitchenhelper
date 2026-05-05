import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

import config
import db
import menu as menu_module
import printing.manager as pm

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def index(request: Request):
    try:
        items = menu_module.load_menu(config.get_active_menu_path())
    except Exception:
        items = []
    return templates.TemplateResponse("index.html", {
        "request": request,
        "menu": items,
        "menu_name": config.get_active_menu_name(),
    })


@router.post("/order")
async def submit_order(
    request: Request,
    items: str = Form(...),
    notes: str = Form(""),
):
    try:
        raw_items = json.loads(items)
    except Exception:
        raw_items = []

    try:
        menu_items = menu_module.load_menu(config.get_active_menu_path())
        menu_map = {it["name"]: it for it in menu_items}
    except Exception:
        menu_map = {}

    enriched: list[dict[str, Any]] = []
    for it in raw_items:
        if isinstance(it, dict):
            name = it.get("name", "")
            if name in menu_map:
                it.setdefault("printer", menu_map[name].get("printer", ""))
            enriched.append(it)

    customer_id = str(uuid.uuid4())
    now = datetime.now().isoformat(timespec="seconds")
    order_numbers: list[str] = []

    printers: set[str] = {it.get("printer", "") for it in enriched}
    if not printers:
        printers = {""}

    for printer in printers:
        printer_items = [it for it in enriched if it.get("printer", "") == printer]
        if not printer_items:
            continue
        order = db.save_order({
            "id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "kitchen": printer,
            "items": printer_items,
            "notes": notes,
            "created_at": now,
        })
        order_numbers.append(str(order["order_number"]))

    order_number_str = " + ".join(order_numbers)
    accept = request.headers.get("Accept", "")
    xhr = request.headers.get("X-Requested-With", "")
    if "application/json" in accept or xhr == "XMLHttpRequest":
        return JSONResponse({"status": "ok", "order_number": order_number_str})
    return RedirectResponse("/orders", status_code=303)


@router.post("/cooked/{order_id}")
async def cooked(order_id: str, request: Request):
    result = db.toggle_cooked(order_id)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    accept = request.headers.get("Accept", "")
    xhr = request.headers.get("X-Requested-With", "")
    if "application/json" in accept or xhr == "XMLHttpRequest":
        return JSONResponse({"status": "ok", "cooked_at": result["cooked_at"]})
    return RedirectResponse("/orders", status_code=303)


@router.post("/fulfilled/{order_id}")
async def fulfilled(order_id: str, request: Request):
    result = db.toggle_fulfilled(order_id)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    accept = request.headers.get("Accept", "")
    xhr = request.headers.get("X-Requested-With", "")
    if "application/json" in accept or xhr == "XMLHttpRequest":
        return JSONResponse({"status": "ok", "fulfilled_at": result["fulfilled_at"]})
    return RedirectResponse("/orders", status_code=303)


@router.get("/orders")
async def orders_view(request: Request, from_dt: str = "", to_dt: str = ""):
    orders = db.get_orders(from_dt or None, to_dt or None)
    return templates.TemplateResponse("orders.html", {
        "request": request,
        "orders": orders,
        "from_dt": from_dt,
        "to_dt": to_dt,
    })


@router.get("/orders/{order_number}/export")
async def order_export(order_number: int):
    order = db.get_order_by_number(order_number)
    if not order:
        return Response("Bestellung nicht gefunden", status_code=404)
    lines = [
        f"Bestell-Nr.: {order['order_number']}",
        f"UUID: {order['id']}",
        f"Zeit: {order['created_at']}",
    ]
    for it in order.get("items", []):
        lines.append(f"{it.get('qty', 1)}x {it.get('name', '')}")
        for ex in (it.get("extras") or []):
            lines.append(f"  Extras: {ex}")
    if order["notes"]:
        lines.append(f"Notiz: {order['notes']}")
    lines.append(f"Gedruckt (Küche): {'Ja' if order['printed_kitchen'] else 'Nein'}")
    lines.append(f"Gedruckt (Kunde): {'Ja' if order['printed_customer'] else 'Nein'}")
    text = "\n".join(lines)
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=order_{order_number}.txt"},
    )


@router.post("/orders/{order_number}/print_kitchen")
async def reprint_kitchen(order_number: int):
    order = db.get_order_by_number(order_number)
    if not order:
        return Response("Bestellung nicht gefunden", status_code=404)
    db.reset_printed_kitchen(order_number)
    return RedirectResponse("/orders", status_code=303)


@router.post("/orders/{order_number}/print_customer")
async def reprint_customer(order_number: int):
    order = db.get_order_by_number(order_number)
    if not order:
        return Response("Bestellung nicht gefunden", status_code=404)
    db.reset_printed_customer(order_number)
    return RedirectResponse("/orders", status_code=303)
