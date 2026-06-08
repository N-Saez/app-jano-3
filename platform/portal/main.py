import re

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth import (
    _COOKIE_NAME,
    create_session_cookie,
    get_session_user,
    verify_firebase_token,
)
from db import App, get_db, list_running_apps
from deployer import deploy_zip
from security import is_authorized_uploader, validate_slug, validate_zip

app = FastAPI(docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")

# ── Página principal ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db=Depends(get_db)):
    user = get_session_user(request)
    apps: list[App] = list_running_apps(db) if user else []
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "apps": apps,
            "can_upload": is_authorized_uploader(user),
        },
    )

# ── Autenticación Firebase ────────────────────────────────────────────────────

@app.post("/auth/verify")
async def auth_verify(request: Request):
    """Recibe el ID token de Firebase desde el frontend, lo verifica y crea la sesión."""
    body = await request.json()
    id_token = body.get("token")
    if not id_token:
        raise HTTPException(400, "Token requerido.")

    claims = verify_firebase_token(id_token)
    email = claims.get("email") or claims.get("preferred_username", "")

    response = JSONResponse({"ok": True, "email": email})
    response.set_cookie(
        _COOKIE_NAME,
        create_session_cookie(email),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=8 * 3600,
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/")
    response.delete_cookie(_COOKIE_NAME)
    return response

# ── Upload y despliegue ───────────────────────────────────────────────────────

@app.post("/upload")
async def upload_app(
    request: Request,
    app_name: str = Form(...),
    zip_file: UploadFile = File(...),
    db=Depends(get_db),
):
    user = get_session_user(request)
    if not user:
        raise HTTPException(401, "No autenticado.")
    if not is_authorized_uploader(user):
        raise HTTPException(403, "No tienes permiso para subir aplicaciones.")

    validate_slug(app_name)

    # Verificar que el nombre no esté en uso
    existing = db.query(App).filter(App.name == app_name).first()
    if existing:
        raise HTTPException(409, f"Ya existe una app con el nombre '{app_name}'.")

    zip_bytes = await zip_file.read()
    validate_zip(zip_bytes)

    try:
        record = await deploy_zip(app_name, zip_bytes, user, db)
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    return {
        "status": "ok",
        "url": f"https://pagina.cl/{app_name}/",
        "port": record.port,
        "type": record.app_type,
    }

# ── Estado de una app ─────────────────────────────────────────────────────────

@app.get("/status/{app_name}")
async def app_status(app_name: str, request: Request, db=Depends(get_db)):
    if not get_session_user(request):
        raise HTTPException(401, "No autenticado.")
    record = db.query(App).filter(App.name == app_name).first()
    if not record:
        raise HTTPException(404, "App no encontrada.")
    return {"name": record.name, "status": record.status, "port": record.port}
