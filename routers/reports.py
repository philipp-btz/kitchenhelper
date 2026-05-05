from datetime import date, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import config
import db
import printing.manager as pm

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _today_range() -> tuple[str, str]:
    today = date.today().isoformat()
    return f"{today}T00:00:00", f"{today}T23:59:59"


@router.get("/reports")
async def reports_view(request: Request, from_dt: str = "", to_dt: str = ""):
    if not from_dt or not to_dt:
        from_dt, to_dt = _today_range()
    data = db.aggregate_orders(from_dt, to_dt)
    orders = db.get_orders(from_dt, to_dt)
    return templates.TemplateResponse("reports.html", {
        "request": request,
        "data": data,
        "orders": orders,
        "from_dt": from_dt,
        "to_dt": to_dt,
    })


@router.get("/api/reports")
async def api_reports(from_dt: str = "", to_dt: str = ""):
    if not from_dt or not to_dt:
        from_dt, to_dt = _today_range()
    return JSONResponse(db.aggregate_orders(from_dt, to_dt))


@router.post("/reports/print")
async def reports_print(from_dt: str = Form(""), to_dt: str = Form("")):
    if not from_dt or not to_dt:
        from_dt, to_dt = _today_range()
    data = db.aggregate_orders(from_dt, to_dt)
    managers = pm.get_managers()
    customer_mgr = managers.get("customer") or (next(iter(managers.values()), None))
    if customer_mgr:
        customer_mgr.enqueue("report", {"data": data})
    return RedirectResponse("/reports", status_code=303)
