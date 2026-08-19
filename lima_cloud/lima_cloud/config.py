"""
Configuracion del pipeline de adquisicion satelital (lado Lima).

Todo lo que dependa del sitio real (extension de la cuenca, cuenta de
Google Earth Engine, umbrales de clasificacion) se ajusta aca o por
variable de entorno -- no hay nada hardcodeado en acquire.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    return float(v) if v not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    return int(v) if v not in (None, "") else default


# --- Extension geografica de la cuenca (grilla 6x6 = 36 cuadrantes) --------
# Centrado en las coordenadas GPS reales del nodo de Mallacayan
# (lat=-9.718924, lon=-77.598083, dadas por el equipo de campo -- reemplazan
# el placeholder anterior, que por error habia quedado ~20 km al este del
# sitio real). El rectangulo es +-0.075 grados (~8.3 km en latitud, ~8.2 km
# en longitud a esta latitud) alrededor de ese punto.
# TODO(equipo): esto sigue siendo un cuadrado centrado en el nodo, no la
# extension real de la cuenca que alimenta la laguna Mullaca. Ajustar si se
# delimita la cuenca real con una capa vectorial.
BASIN_LAT_MIN = _env_float("BASIN_LAT_MIN", -9.793924)
BASIN_LAT_MAX = _env_float("BASIN_LAT_MAX", -9.643924)
BASIN_LON_MIN = _env_float("BASIN_LON_MIN", -77.673083)
BASIN_LON_MAX = _env_float("BASIN_LON_MAX", -77.523083)

GRID_ROWS = _env_int("GRID_ROWS", 6)
GRID_COLS = _env_int("GRID_COLS", 6)

# Cuadrante donde vive el nodo de Mallacayan (fila, columna), 0-indexado.
# Calculado a partir de las coordenadas GPS reales del nodo
# (lat=-9.718924, lon=-77.598083) sobre la grilla 6x6 de arriba: cae justo
# en el borde de las celdas 3_3 (fila 3, columna 3).
NODE_QUADRANT_ROW = _env_int("NODE_QUADRANT_ROW", 3)
NODE_QUADRANT_COL = _env_int("NODE_QUADRANT_COL", 3)
NODE_QUADRANT_ID = os.environ.get("NODE_QUADRANT_ID", "3_3")

# --- Cadencia de adquisicion ------------------------------------------------
# El comentario del firmware dice "el dato satelital solo cambia cada 5-10
# dias" (revisita de Sentinel-2 ~5 dias con las dos plataformas). Se deja
# configurable, no fijo, para poder ajustarlo sin tocar codigo.
ACQUIRE_INTERVAL_HOURS = _env_int("ACQUIRE_INTERVAL_HOURS", 24 * 5)

# --- Ventanas temporales para cada variable --------------------------------
S2_LOOKBACK_DAYS = _env_int("S2_LOOKBACK_DAYS", 10)      # composite Sentinel-2 (evita huecos por nubes)
# MOD11A2 es compuesto de 8 dias, pero en produccion se observo latencia de
# procesamiento real de ~17 dias (verificado 2026-08-14: con ventana de 16
# dias la coleccion vino vacia; la imagen mas reciente disponible estaba a
# 17 dias de "hoy"). 35 dias deja margen para esa latencia + el propio
# periodo de compuesto de 8 dias.
LST_LOOKBACK_DAYS = _env_int("LST_LOOKBACK_DAYS", 35)
ERA5_LOOKBACK_DAYS = _env_int("ERA5_LOOKBACK_DAYS", 20)   # ERA5-Land tambien tiene latencia de publicacion
TREND_WINDOW_DAYS = _env_int("TREND_WINDOW_DAYS", 14)     # ventana para *_trend14
CDD_WINDOW_DAYS = _env_int("CDD_WINDOW_DAYS", 60)         # ventana para contar dias secos consecutivos
# SPI (McKee et al. 1993) ajusta una gamma sobre el HISTORICO climatologico,
# no sobre la ventana reciente -- verificado en produccion: con solo 6 meses
# de precipitacion, spi_from_series() no tenia suficientes periodos
# acumulados (min. 8) para el ajuste y devolvia NaN en los tres SPI. CHIRPS
# arranca en 1981; 15 anios da un registro climatologicamente razonable sin
# que la consulta a GEE se vuelva excesivamente lenta.
SPI_HISTORY_YEARS = _env_int("SPI_HISTORY_YEARS", 15)
VCI_HISTORY_YEARS = _env_int("VCI_HISTORY_YEARS", 6)      # anios de historia NDVI para el min/max de VCI
CDD_DRY_THRESHOLD_MM = _env_float("CDD_DRY_THRESHOLD_MM", 1.0)  # <1mm/dia = "dia seco" (umbral usual en literatura)

# --- Datasets de Earth Engine ----------------------------------------------
GEE_PROJECT = os.environ.get("GEE_PROJECT", "")  # requerido por la API nueva de earthengine-api
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
MODIS_LST_COLLECTION = "MODIS/061/MOD11A2"
CHIRPS_COLLECTION = "UCSB-CHG/CHIRPS/DAILY"
ERA5_LAND_COLLECTION = "ECMWF/ERA5_LAND/DAILY_AGGR"

# --- Umbrales de clasificacion (heuristica propia, NO la del entrenamiento) ---
# ADVERTENCIA -- leer antes de usar en produccion:
# dsi_score y cur_class son features de ingenieria que el equipo de ML ya
# definio al entrenar drought_onset_model.h (ver GridSearch/TimeSeriesSplit
# mencionados en el paper). Las formulas de este archivo son una propuesta
# razonable, NO la definicion original de entrenamiento. Si no coinciden
# exactamente, el modelo embebido va a recibir variables fuera de la
# distribucion con la que fue entrenado y sus predicciones no seran
# confiables. Antes de desplegar: pedir al equipo de ML la formula exacta de
# dsi_score/cur_class usada al generar el dataset de entrenamiento y
# reemplazarla aca.
VCI_CLASS_THRESHOLDS = (10.0, 20.0, 35.0, 50.0)  # bordes de clase D4..D0 (menor VCI = peor)
# Ya no hay umbrales de alerta (SPI3_ALERT_THRESHOLD / VCI_ALERT_THRESHOLD)
# ni un "lvl" calculado en la nube: la decision de si hay sequia o no es
# exclusivamente del modelo embebido (drought_onset_model.h) en el ESP32-S3.
# La nube solo entrega datos crudos/derivados como entrada al modelo.


@dataclass(frozen=True)
class Quadrant:
    row: int
    col: int
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    @property
    def id(self) -> str:
        return f"{self.row}_{self.col}"


def build_grid() -> list[Quadrant]:
    """Genera la grilla GRID_ROWS x GRID_COLS sobre el bounding box de la cuenca."""
    lat_step = (BASIN_LAT_MAX - BASIN_LAT_MIN) / GRID_ROWS
    lon_step = (BASIN_LON_MAX - BASIN_LON_MIN) / GRID_COLS
    quads = []
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            quads.append(Quadrant(
                row=r, col=c,
                lat_min=BASIN_LAT_MIN + r * lat_step,
                lat_max=BASIN_LAT_MIN + (r + 1) * lat_step,
                lon_min=BASIN_LON_MIN + c * lon_step,
                lon_max=BASIN_LON_MIN + (c + 1) * lon_step,
            ))
    return quads
