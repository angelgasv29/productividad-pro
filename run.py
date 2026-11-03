"""Arranque local de Productividad Pro.

Uso:
    python run.py
    python run.py --host 0.0.0.0 --port 8080
    python run.py --reload
"""

from __future__ import annotations

import argparse

import uvicorn

from app.core.config import settings
from app.core.database import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor local de Productividad Pro")
    parser.add_argument("--host", default="127.0.0.1", help="Host de escucha")
    parser.add_argument("--port", type=int, default=8000, help="Puerto de escucha")
    parser.add_argument("--reload", action="store_true", help="Recarga automática en desarrollo")
    args = parser.parse_args()

    settings.ensure_directories()
    init_db()

    print("=" * 64)
    print(f"  {settings.app_name} v{settings.app_version}")
    print(f"  URL: http://{args.host}:{args.port}")
    print(f"  Base de datos: {settings.database_url}")
    print(f"  Backups: {settings.backup_dir}")
    print("=" * 64)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
