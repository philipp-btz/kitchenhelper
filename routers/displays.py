import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

import config
import db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/kitchen_display")
async def kitchen_display(request: Request):
    printer_names = config.get_printer_names()
    kitchen_printers = [p for p in printer_names if p != "customer"]
    return templates.TemplateResponse("kitchen_display.html", {
        "request": request,
        "kitchen_printers": kitchen_printers,
    })


@router.get("/customer_display")
async def customer_display(request: Request):
    return templates.TemplateResponse("customer_display.html", {"request": request})


@router.get("/api/uncooked_orders")
async def api_uncooked_orders(kitchen: str = "all"):
    orders = db.get_uncooked_orders(kitchen if kitchen != "all" else None)
    return Response(
        content=json.dumps(orders, ensure_ascii=False),
        media_type="application/json",
    )


@router.get("/api/cooked_unfulfilled")
async def api_cooked_unfulfilled():
    nums = db.get_cooked_unfulfilled()
    return JSONResponse({"order_numbers": nums})
