import os

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import config
import menu as menu_module

router = APIRouter()
templates = Jinja2Templates(directory="templates")
MENU_DIR = ".local/menus"


@router.get("/menus")
async def menus_view(request: Request, selected: str = "", saved: str = ""):
    files = menu_module.list_menu_files()
    menus = [{"file": f, "title": os.path.splitext(f)[0]} for f in files]
    settings = config.load_settings()
    return templates.TemplateResponse("menu_selector.html", {
        "request": request,
        "menus": menus,
        "selected": selected,
        "saved": saved,
        "settings": settings,
        "active_menu_name": config.get_active_menu_name(),
    })


@router.get("/menus/editor")
async def menus_editor(request: Request, menu_file: str = "", menu_name: str = "", error: str = ""):
    items = []
    loaded_file = ""
    printer_names = config.get_printer_names()
    if menu_file:
        path = menu_module.menu_path(menu_file)
        if path and os.path.exists(path):
            try:
                items = menu_module.load_menu(path)
                loaded_file = os.path.basename(path)
                if not menu_name:
                    menu_name = os.path.splitext(loaded_file)[0]
            except Exception:
                error = "Die ausgewählte Menüdatei konnte nicht geladen werden."
        else:
            return RedirectResponse("/menus", status_code=303)
    return templates.TemplateResponse("menu_editor.html", {
        "request": request,
        "items": items,
        "menu_name": menu_name,
        "loaded_file": loaded_file,
        "error": error,
        "printer_names": printer_names,
    })


@router.post("/menus/save")
async def menus_save(
    menu_name: str = Form(""),
    items_json: str = Form(""),
    loaded_file: str = Form(""),
):
    import json
    menu_name = menu_name.strip()
    if not menu_name:
        return RedirectResponse(f"/menus/editor?menu_file={loaded_file}&error=Bitte+einen+Menü-Namen+angeben.", status_code=303)

    safe_name = menu_module.secure_name(menu_name)
    if not safe_name:
        return RedirectResponse(f"/menus/editor?menu_file={loaded_file}&error=Ungültiger+Menü-Name.", status_code=303)
    if not safe_name.lower().endswith(".json"):
        safe_name += ".json"

    path = menu_module.menu_path(safe_name)
    if not path:
        return RedirectResponse(f"/menus/editor?menu_file={loaded_file}&error=Ungültiger+Dateiname.", status_code=303)

    try:
        raw = json.loads(items_json) if items_json.strip() else []
    except Exception:
        return RedirectResponse(f"/menus/editor?menu_file={loaded_file}&error=Menüdaten+ungültig.", status_code=303)

    items = [menu_module.normalize_item(it) for it in raw if isinstance(it, dict) and it.get("name")]
    if not items:
        return RedirectResponse(f"/menus/editor?menu_file={loaded_file}&error=Mindestens+ein+Item+mit+Namen+erforderlich.", status_code=303)

    os.makedirs(MENU_DIR, exist_ok=True)
    menu_module.save_menu(path, items)
    return RedirectResponse(f"/menus?selected={os.path.splitext(safe_name)[0]}&saved={safe_name}", status_code=303)


@router.post("/menus/select")
async def menus_select(menu_file: str = Form("")):
    if not menu_file:
        return RedirectResponse("/menus", status_code=303)
    path = menu_module.menu_path(menu_file)
    if not path:
        return RedirectResponse("/menus", status_code=303)
    config.set_active_menu_path(path)
    menu_name = os.path.splitext(menu_file)[0]
    return RedirectResponse(f"/menus?selected={menu_name}", status_code=303)


@router.post("/menus/delete")
async def menus_delete(menu_file: str = Form("")):
    if not menu_file:
        return RedirectResponse("/menus", status_code=303)
    try:
        menu_module.soft_delete(menu_file)
    except FileNotFoundError:
        pass
    return RedirectResponse("/menus", status_code=303)


@router.post("/menus/upload")
async def menus_upload(
    request: Request,
    replace: str = Form(""),
    filename: str = Form(""),
    menu_file: UploadFile = None,
):
    os.makedirs(MENU_DIR, exist_ok=True)

    if replace in ("1", "2") and filename:
        safe = menu_module.secure_name(filename)
        dest = os.path.join(MENU_DIR, safe)
        tmp = dest + ".upload"
        if replace == "1":
            if os.path.exists(tmp):
                os.replace(tmp, dest)
            return RedirectResponse(f"/menus?selected={os.path.splitext(safe)[0]}", status_code=303)
        else:
            if os.path.exists(tmp):
                os.remove(tmp)
            return RedirectResponse("/menus", status_code=303)

    if not menu_file or not menu_file.filename:
        return RedirectResponse("/menus", status_code=303)

    safe = menu_module.secure_name(menu_file.filename)
    if not safe.lower().endswith(".json"):
        from fastapi.responses import Response
        return Response("Nur .json Dateien erlaubt", status_code=400)

    dest = os.path.join(MENU_DIR, safe)
    content = await menu_file.read()

    if os.path.exists(dest):
        tmp = dest + ".upload"
        with open(tmp, "wb") as f:
            f.write(content)
        return templates.TemplateResponse("menu_upload_confirm.html", {
            "request": request,
            "filename": safe,
        })

    with open(dest, "wb") as f:
        f.write(content)
    return RedirectResponse(f"/menus?selected={os.path.splitext(safe)[0]}", status_code=303)
