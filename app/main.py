"""Aplicación FastAPI de Productividad Pro."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.v1.router import api_router
from app.core.config import BASE_DIR, settings
from app.core.database import get_db, init_db
from app.core.exceptions import register_exception_handlers
from app.core.security import resolve_user_from_request


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_directories()
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Sistema personal de productividad con Hábitos, Rutinas, Backlog, "
    "Objetivos, Timer Pro y analítica avanzada.",
    lifespan=lifespan,
)

register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _page_user(request: Request, db: Session):
    return resolve_user_from_request(request, db)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = _page_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "app_version": settings.app_version},
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = _page_user(request, db)
    if user is not None:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"app_version": settings.app_version},
    )


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    user = _page_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "app_version": settings.app_version, "open_profile": True},
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}
