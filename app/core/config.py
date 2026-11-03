"""Configuración central de Productividad Pro.

La aplicación está pensada para ejecutarse en local (offline-first), por lo que
la base de datos por defecto vive dentro del propio proyecto. Todas las rutas se
resuelven de forma absoluta para que `run.py`, Alembic y pytest compartan la
misma configuración.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = BASE_DIR / "data"
BACKUP_DIR: Path = DATA_DIR / "backups"


class Settings(BaseSettings):
    """Configuración tipada leída de variables de entorno o `.env`."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Productividad Pro"
    app_version: str = "4.0.0"
    schema_version: int = 4
    debug: bool = False

    secret_key: str = Field(
        default="productividad-pro-local-dev-secret-change-me-2026",
        description="Clave HS256 para firmar JWT. Cambiar en producción.",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    cookie_name: str = "prodpro_access_token"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    database_url: str = Field(
        default=f"sqlite:///{(DATA_DIR / 'productividad_pro.db').as_posix()}",
        description="URL SQLAlchemy. Por defecto SQLite local.",
    )
    logical_cutoff_hour: int = 4
    backup_rotation_slots: int = 2

    max_import_bytes: int = 25 * 1024 * 1024

    @property
    def data_dir(self) -> Path:
        return DATA_DIR

    @property
    def backup_dir(self) -> Path:
        return BACKUP_DIR

    def ensure_directories(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings


settings: Settings = get_settings()
