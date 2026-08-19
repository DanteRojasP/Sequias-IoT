"""
Punto de entrada: arranca el scheduler de adquisicion (en background) y el
servidor HTTP (en primer plano, vía uvicorn), en un solo proceso.

Uso:
    python -m lima_cloud.main
"""
from __future__ import annotations

import logging
import os

import uvicorn

from . import scheduler
from .server import app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    scheduler.start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
