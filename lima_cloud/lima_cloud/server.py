"""
Servidor HTTP que el nodo de Mallacayan consume (main/transport_http.cpp):

  GET  /cache/<quad>   -> devuelve {"q": {...}, "ts": "...", "crc": "xxxx"}
                          EXACTAMENTE como lo espera http_fetch_cache()
                          (path "/cache/%s" con quad = CONFIG_YAKUX_MY_QUAD).

  POST /result/<quad>  -> recibe {"quad","votes","level","rssi","battery_v"}
                          tal como lo arma http_post_result().

El body de /cache/<quad> se sirve como texto plano ya serializado (el mismo
que crc.build_payload() genero), NO se re-serializa aca -- si FastAPI
reconstruyera el JSON a partir de un dict, la subcadena de "q" podria cambiar
de formato (orden de claves, espacios) y el CRC calculado en acquire.py
dejaria de coincidir con los bytes realmente transmitidos.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse

from . import acquire

STATIC_DIR = Path(__file__).parent / "static"

log = logging.getLogger("server")

# Cache en memoria: {quad_id: payload_json_str}. acquire.run_all() la llena;
# al arrancar el proceso se rellena desde disco por si hubo un restart entre
# corridas del scheduler.
_cache: dict[str, str] = {}


def _load_cache_from_disk() -> None:
    from . import config
    for q in config.build_grid():
        payload = acquire.load_cached_payload(q.id)
        if payload:
            _cache[q.id] = payload
    log.info("cache cargado desde disco: %d cuadrantes", len(_cache))


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _load_cache_from_disk()
    yield


app = FastAPI(title="Servidor emisor de cache - Sequias IAC", lifespan=_lifespan)


def set_cache(results: dict[str, dict]) -> None:
    """Llamado por scheduler.py despues de cada acquire.run_all()."""
    for quad_id, entry in results.items():
        _cache[quad_id] = entry["payload"]


@app.get("/cache/{quad}")
def get_cache(quad: str):
    payload = _cache.get(quad)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"sin cache para el cuadrante '{quad}' todavia")
    return Response(content=payload, media_type="application/json")


@app.post("/result/{quad}")
async def post_result(quad: str, request: Request):
    body = await request.json()
    log.info(
        "resultado recibido de %s: votes=%s level=%s rssi=%s battery_v=%s",
        quad, body.get("votes"), body.get("level"), body.get("rssi"), body.get("battery_v"),
    )
    # TODO(equipo): persistir en una base de datos / timeseries para
    # dashboard historico -- hoy solo se loguea. La nube ya no calcula un
    # nivel propio para comparar contra este "level" (el nodo es la unica
    # fuente de la decision de sequia).
    return {"ok": True}


@app.get("/health")
def health():
    from . import config
    return {"status": "ok", "quadrants_cached": len(_cache), "expected": config.GRID_ROWS * config.GRID_COLS}


@app.get("/api/quadrants")
def api_quadrants():
    """Todos los cuadrantes con cache vigente, con su geometria y el 'q'
    ya parseado (a diferencia de /cache/<quad>, que sirve el payload firmado
    tal cual para el nodo). Pensado para el dashboard, no para el firmware."""
    from . import config
    grid_by_id = {q.id: q for q in config.build_grid()}
    out = []
    for quad_id, payload in _cache.items():
        geom = grid_by_id.get(quad_id)
        if geom is None:
            continue
        parsed = json.loads(payload)
        out.append({
            "id": quad_id,
            "row": geom.row,
            "col": geom.col,
            "lat_min": geom.lat_min, "lat_max": geom.lat_max,
            "lon_min": geom.lon_min, "lon_max": geom.lon_max,
            "q": parsed["q"],
            "ts": parsed["ts"],
        })
    return {
        "grid_rows": config.GRID_ROWS,
        "grid_cols": config.GRID_COLS,
        "node_quadrant_id": config.NODE_QUADRANT_ID,
        "node_lat": (config.BASIN_LAT_MIN + config.BASIN_LAT_MAX) / 2,
        "node_lon": (config.BASIN_LON_MIN + config.BASIN_LON_MAX) / 2,
        "quadrants": out,
    }


@app.get("/")
def dashboard():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="dashboard no encontrado")
    return FileResponse(index)
