from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import config

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SETTING_KEYS = ["print_customer_double", "print_extra_order_nr", "kitchen_buzzer"]


@router.get("/settings")
async def settings_view(request: Request):
    settings = config.load_settings()
    return templates.TemplateResponse(request, "settings.html", {
        "settings": settings,
    })


@router.post("/settings")
async def settings_update(request: Request):
    form = await request.form()
    settings = {key: (form.get(key) == "on") for key in SETTING_KEYS}
    config.save_settings(settings)
    return RedirectResponse("/settings", status_code=303)
