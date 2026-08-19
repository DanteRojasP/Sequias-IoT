"""
Corre acquire.run_all() cada ACQUIRE_INTERVAL_HOURS (config.py), y empuja el
resultado al cache en memoria del servidor HTTP (server.set_cache).

Se ejecuta una corrida inmediata al arrancar (para no esperar el primer
intervalo completo con el cache vacio) y luego queda en background dentro
del mismo proceso de uvicorn.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from . import acquire, config, server
from .gee_auth import init_earth_engine

log = logging.getLogger("scheduler")


def _run_and_publish() -> None:
    try:
        results = acquire.run_all(ee_already_initialized=True)
        server.set_cache(results)
        log.info("adquisicion completa: %d/%d cuadrantes actualizados",
                  len(results), config.GRID_ROWS * config.GRID_COLS)
    except Exception:
        log.exception("corrida de adquisicion fallida por completo (se conserva el cache anterior)")


def start() -> BackgroundScheduler:
    init_earth_engine()  # una sola vez por proceso; compartida por todas las corridas

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        _run_and_publish,
        trigger="interval",
        hours=config.ACQUIRE_INTERVAL_HOURS,
        next_run_time=None,  # se dispara manualmente abajo para la corrida inicial
        id="acquire_job",
        max_instances=1,       # nunca dos corridas GEE en paralelo
        coalesce=True,         # si se atrasa, no acumula corridas pendientes
    )
    sched.start()
    log.info("scheduler iniciado: cada %d horas", config.ACQUIRE_INTERVAL_HOURS)

    _run_and_publish()  # corrida inicial sincrona, para no arrancar con cache vacio
    return sched
