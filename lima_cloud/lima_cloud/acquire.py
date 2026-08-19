"""
Orquestador de una corrida de adquisicion completa: recorre los 36
cuadrantes de la grilla, calcula sus variables via indices.py, arma+firma el
payload de cada uno con crc.py, y actualiza el cache en memoria/disco que
server.py sirve por HTTP/MQTT.

Este es el modulo que scheduler.py llama cada ACQUIRE_INTERVAL_HOURS.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path

import ee

from . import config
from .crc import build_payload
from .indices import compute_quadrant_variables

log = logging.getLogger("acquire")

CACHE_DIR = Path(os.environ.get("CACHE_DIR", "./cache"))


def run_all(ee_already_initialized: bool = True) -> dict[str, dict]:
    """Corre la adquisicion para todos los cuadrantes de la grilla.
    Devuelve {quad_id: {"payload": str_json, "info": {...}}}.

    Los errores de UN cuadrante no abortan la corrida completa -- un
    cuadrante con nubes persistentes o un timeout de GEE no debe tumbar el
    cache de los otros 35.
    """
    if not ee_already_initialized:
        from .gee_auth import init_earth_engine
        init_earth_engine()

    end_date = ee.Date(dt.datetime.utcnow().strftime("%Y-%m-%d"))
    ts_str = dt.datetime.utcnow().strftime("%Y-%m-%d")

    results: dict[str, dict] = {}
    quads = config.build_grid()
    log.info("iniciando adquisicion: %d cuadrantes", len(quads))

    for q in quads:
        try:
            variables = compute_quadrant_variables(q, end_date)
            q_dict = variables.to_q_dict()
            payload, info = build_payload(q_dict, ts_str)
            results[q.id] = {"payload": payload, "info": info, "computed_at": dt.datetime.utcnow().isoformat()}
            log.info("cuadrante %s OK (%d bytes, crc=%s)", q.id, info["size_bytes"], info["crc_hex"])
        except Exception:
            log.exception("cuadrante %s: fallo la adquisicion, se conserva el cache anterior si existe", q.id)

    _persist(results)
    return results


def _persist(results: dict[str, dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for quad_id, entry in results.items():
        (CACHE_DIR / f"{quad_id}.json").write_text(entry["payload"], encoding="utf-8")
    manifest = {
        "updated_at": dt.datetime.utcnow().isoformat(),
        "quadrants": sorted(results.keys()),
    }
    (CACHE_DIR / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def load_cached_payload(quad_id: str) -> str | None:
    """Lee el ultimo payload firmado desde disco (usado por server.py al
    arrancar, o si el cache en memoria del proceso se perdio por un
    restart)."""
    path = CACHE_DIR / f"{quad_id}.json"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_all(ee_already_initialized=False)
