from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import db
import printing.manager as pm


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = config.load_config()
    db.init_db()
    for name, ip in cfg["printer_dict"].items():
        pm.register(name, ip, cfg["printer_mode"])
    yield
    for m in pm.get_managers().values():
        m.stop()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

from routers import displays, menus, orders, reports, settings  # noqa: E402
app.include_router(orders.router)
app.include_router(displays.router)
app.include_router(menus.router)
app.include_router(settings.router)
app.include_router(reports.router)
