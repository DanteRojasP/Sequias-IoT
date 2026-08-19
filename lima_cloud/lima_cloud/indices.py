"""
Extraccion de indices satelitales/climaticos por cuadrante via Google Earth
Engine (GEE). Requiere una cuenta de servicio de GEE ya autenticada (ver
README) -- este modulo asume que ee.Initialize() ya corrio (lo hace
gee_auth.py).

Cada funcion hace UNA reduccion server-side (reduceRegion) y trae solo el
numero final a Python -- nunca se descarga la imagen completa, que es la
idea detras de "que solo corra en la nube y extraiga esos datos": el computo
pesado (todas las bandas, todos los pixeles) queda en los servidores de GEE.

Formulas:
  NDVI  = (NIR - RED) / (NIR + RED)                          [estandar]
  NDWI  = (NIR - SWIR) / (NIR + SWIR)                         [Gao, 1996 -- ref. [7] del paper]
  NDDI  = (NDVI - NDWI) / (NDVI + NDWI)                       [Gu et al., 2007 / Irsyad et al. 2025 -- ref. [8]]
  VCI   = (NDVI - NDVI_min_hist) / (NDVI_max_hist - NDVI_min_hist) * 100   [Kogan, 1995 -- ref. [14]]
  LST   = banda LST_Day_1km de MOD11A2, Kelvin*0.02 -> Celsius
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import ee
import numpy as np

from . import config
from .et0 import et0_hargreaves_mm_day
from .spi import count_consecutive_dry_days, spi_from_series


def quadrant_geometry(q: config.Quadrant) -> "ee.Geometry.Rectangle":
    return ee.Geometry.Rectangle([q.lon_min, q.lat_min, q.lon_max, q.lat_max])


def _mask_s2_clouds(img):
    """Enmascara nubes/sombras usando la banda SCL (Scene Classification)
    de Sentinel-2 SR: descarta clases 3 (sombra de nube), 8/9 (nube media/alta
    probabilidad) y 10 (cirro)."""
    scl = img.select("SCL")
    bad = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10))
    return img.updateMask(bad.Not())


def _s2_composite(geom, end_date: "ee.Date", lookback_days: int):
    start = end_date.advance(-lookback_days, "day")
    coll = (
        ee.ImageCollection(config.S2_COLLECTION)
        .filterBounds(geom)
        .filterDate(start, end_date)
        .map(_mask_s2_clouds)
    )
    return coll.median()  # mediana: mas robusta a residuos de nube que la media


def _reduce_mean(image, band: str, geom, scale: int) -> float:
    stat = image.select(band).reduceRegion(
        reducer=ee.Reducer.mean(), geometry=geom, scale=scale, maxPixels=1e9, bestEffort=True,
    )
    val = stat.get(band).getInfo()
    return float(val) if val is not None else float("nan")


def _collection_is_empty(coll: "ee.ImageCollection") -> bool:
    """Chequea el tamano ANTES de tocar bandas. Server-side: una
    ImageCollection vacia produce una imagen de 0 bandas al reducir
    (.mean()/.median()), y cualquier operacion de banda posterior
    (.select()/.multiply()/.normalizedDifference()) revienta con un error
    opaco de EE en vez de devolver NaN. Ver nota en lst_celsius()."""
    return coll.size().getInfo() == 0


def ndvi_ndwi_now(geom, end_date: "ee.Date", lookback_days: int) -> tuple[float, float]:
    start = end_date.advance(-lookback_days, "day")
    raw = (
        ee.ImageCollection(config.S2_COLLECTION)
        .filterBounds(geom).filterDate(start, end_date).map(_mask_s2_clouds)
    )
    if _collection_is_empty(raw):
        return float("nan"), float("nan")
    comp = raw.median()
    ndvi = comp.normalizedDifference(["B8", "B4"]).rename("ndvi")
    ndwi = comp.normalizedDifference(["B8", "B11"]).rename("ndwi")  # Gao 1996: (NIR-SWIR)/(NIR+SWIR)
    return (
        _reduce_mean(ndvi, "ndvi", geom, 20),
        _reduce_mean(ndwi, "ndwi", geom, 20),
    )


def lst_celsius(geom, end_date: "ee.Date", lookback_days: int) -> float:
    """MOD11A2 es un compuesto de 8 dias con latencia de procesamiento real
    de ~2-3 semanas (verificado en produccion: con ventana de 16 dias la
    coleccion vino vacia; la imagen mas reciente disponible estaba a 17 dias
    de "hoy"). LST_LOOKBACK_DAYS en config.py ya deja margen para esto --
    aun asi, si la coleccion viniera vacia (corte de datos, sitio sin
    cobertura), se devuelve NaN en vez de reventar toda la adquisicion del
    cuadrante."""
    start = end_date.advance(-lookback_days, "day")
    coll = ee.ImageCollection(config.MODIS_LST_COLLECTION).filterBounds(geom).filterDate(start, end_date)
    if _collection_is_empty(coll):
        return float("nan")
    img = coll.select("LST_Day_1km").mean().multiply(0.02).subtract(273.15).rename("lst")
    return _reduce_mean(img, "lst", geom, 1000)


def ndvi_series(geom, end_date: "ee.Date", n_days: int, step_days: int = 1) -> np.ndarray:
    """Serie temporal de NDVI (un valor por paso de `step_days`), usada para
    las tendencias a 14 dias. Se resuelve con getRegion sobre un composite
    diario ligero en vez de N llamadas individuales, para minimizar
    round-trips a la API."""
    start = end_date.advance(-n_days, "day")
    coll = (
        ee.ImageCollection(config.S2_COLLECTION)
        .filterBounds(geom)
        .filterDate(start, end_date)
        .map(_mask_s2_clouds)
        .map(lambda img: img.normalizedDifference(["B8", "B4"]).rename("ndvi")
             .copyProperties(img, ["system:time_start"]))
    )
    # getRegion() con la geometria del cuadrante (un rectangulo, no un
    # punto) devuelve filas vacias incluso cuando la coleccion SI tiene
    # imagenes (confirmado en produccion: coleccion no vacia, getRegion
    # sobre el rectangulo -> solo el header, 0 filas). Con el centroide como
    # punto de muestreo funciona correctamente -- es la forma soportada de
    # sacar una serie temporal puntual con getRegion().
    feats = coll.getRegion(geom.centroid(1), scale=20).getInfo()  # [[id,lon,lat,time,ndvi], ...]
    if len(feats) <= 1:
        return np.array([])
    header, rows = feats[0], feats[1:]
    idx = header.index("ndvi")
    vals = [r[idx] for r in rows if r[idx] is not None]
    return np.array(vals, dtype=float)


def linear_trend(series: np.ndarray) -> float:
    """Pendiente de una regresion lineal simple sobre la serie (unidad de la
    variable por paso de muestreo) -- usada para *_trend14. NaN si no hay
    suficientes puntos."""
    if len(series) < 3:
        return float("nan")
    x = np.arange(len(series))
    slope, _ = np.polyfit(x, series, 1)
    return float(slope)


def precip_daily_series(geom, end_date: "ee.Date", n_days: int) -> np.ndarray:
    """CHIRPS tiene ~45 dias de latencia de publicacion (verificado en
    produccion 2026-08-14: la imagen mas reciente disponible era del
    2026-06-30). filterDate(..., end_date) simplemente no trae nada mas
    reciente que eso -- no hace falta ajustar end_date aca, pero SI importa
    para CDD/SPI: la "racha actual" y el SPI del "presente" en realidad
    describen la situacion de hace ~1.5 meses, no la de hoy."""
    start = end_date.advance(-n_days, "day")
    coll = ee.ImageCollection(config.CHIRPS_COLLECTION).filterBounds(geom).filterDate(start, end_date)
    # mismo problema de getRegion() con geometria-rectangulo que en ndvi_series()
    feats = coll.getRegion(geom.centroid(1), scale=5000).getInfo()
    if len(feats) <= 1:
        return np.array([])
    header, rows = feats[0], feats[1:]
    idx = header.index("precipitation")
    vals = [r[idx] for r in rows if r[idx] is not None]
    return np.array(vals, dtype=float)


def era5_temps(geom, end_date: "ee.Date") -> tuple[float, float, float]:
    """Tmax/Tmin/Tmean (C) del dia mas reciente disponible en ERA5-Land,
    para alimentar Hargreaves. ERA5-Land tambien tiene latencia de
    procesamiento (dias a un par de semanas) -- misma proteccion que
    lst_celsius() contra una coleccion vacia en la ventana pedida."""
    coll = (
        ee.ImageCollection(config.ERA5_LAND_COLLECTION)
        .filterBounds(geom)
        .filterDate(end_date.advance(-config.ERA5_LOOKBACK_DAYS, "day"), end_date)
        .sort("system:time_start", False)
    )
    if _collection_is_empty(coll):
        nan = float("nan")
        return nan, nan, nan
    img = ee.Image(coll.first())
    tmax = _reduce_mean(img.select("temperature_2m_max"), "temperature_2m_max", geom, 10000) - 273.15
    tmin = _reduce_mean(img.select("temperature_2m_min"), "temperature_2m_min", geom, 10000) - 273.15
    tmean = (tmax + tmin) / 2.0
    return tmean, tmax, tmin


def ndvi_historical_minmax(geom, end_date: "ee.Date", years: int) -> tuple[float, float]:
    """Min/max de NDVI en la misma ventana +-15 dias del anio, en los
    ultimos `years` anios -- climatologia simple para VCI (Kogan, 1995)."""
    doy = end_date.getRelative("day", "year")
    vals = []
    for y in range(1, years + 1):
        ref = end_date.advance(-y, "year")
        start = ref.advance(-15, "day")
        end = ref.advance(15, "day")
        yearly = ee.ImageCollection(config.S2_COLLECTION).filterBounds(geom).filterDate(start, end).map(_mask_s2_clouds)
        if _collection_is_empty(yearly):
            continue  # ano sin escenas utilizables en la ventana (nubosidad, hueco de cobertura): se omite, no rompe el calculo
        ndvi = yearly.median().normalizedDifference(["B8", "B4"]).rename("ndvi")
        v = _reduce_mean(ndvi, "ndvi", geom, 20)
        if not np.isnan(v):
            vals.append(v)
    if len(vals) < 2:
        return float("nan"), float("nan")
    return float(np.min(vals)), float(np.max(vals))


def classify_cur_class(vci: float) -> int:
    """Clase ordinal de severidad (0=sin sequia .. 4=excepcional), estilo
    U.S. Drought Monitor (D0-D4), a partir de VCI. Ver advertencia sobre
    dsi_score/cur_class en config.py: umbral propio, no el de entrenamiento."""
    edges = config.VCI_CLASS_THRESHOLDS
    if np.isnan(vci):
        return 0
    if vci <= edges[0]:
        return 4
    if vci <= edges[1]:
        return 3
    if vci <= edges[2]:
        return 2
    if vci <= edges[3]:
        return 1
    return 0


def compute_dsi_score(spi3: float, vci: float, nddi: float) -> float:
    """Indice compuesto propio (promedio ponderado, normalizado a favor de
    'peor'=mayor score) combinando SPI3 (meteorologico), VCI (vegetacion) y
    NDDI (compuesto optico). Placeholder documentado -- ver advertencia en
    config.py."""
    parts = []
    weights = []
    if not np.isnan(spi3):
        parts.append(max(-3.0, min(3.0, -spi3)) / 3.0)  # spi mas negativo = peor
        weights.append(0.4)
    if not np.isnan(vci):
        parts.append((100.0 - max(0.0, min(100.0, vci))) / 100.0)
        weights.append(0.35)
    if not np.isnan(nddi):
        parts.append(max(0.0, min(1.0, nddi)))
        weights.append(0.25)
    if not parts:
        return float("nan")
    return float(np.average(parts, weights=weights))


@dataclass
class QuadrantVariables:
    ndvi: float
    ndwi: float
    nddi: float
    lst: float
    vci: float
    dsi_score: float
    cur_class: int
    spi1: float
    spi3: float
    spi6: float
    cdd: int
    et0: float
    nddi_t: float
    ndvi_t: float
    vci_t: float
    lst_t: float

    def to_q_dict(self) -> dict:
        # Ya no se incluye "lvl" -- la nube deja de estimar si hay sequia o
        # no, eso es exclusivamente del modelo embebido en el ESP32-S3.
        # feature_vector.cpp del firmware lee "lvl" con cJSON_IsString(...)
        # y, si no esta, deja fv->lvl_cloud vacio; alert_print_report() ya
        # maneja ese caso (omite el chequeo de discrepancia nube-vs-nodo si
        # lvl_cloud esta vacio) -- quitar este campo no rompe al nodo.
        #
        # Redondeo: mantiene el JSON compacto (importa para el buffer fijo
        # del nodo) sin perder precision relevante para el modelo.
        def r(v, nd=4):
            return None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(v, nd)
        return {
            "ndvi": r(self.ndvi), "ndwi": r(self.ndwi), "nddi": r(self.nddi),
            "lst": r(self.lst, 2), "vci": r(self.vci, 2), "dsi_score": r(self.dsi_score, 3),
            "cur_class": self.cur_class,
            "spi1": r(self.spi1, 3), "spi3": r(self.spi3, 3), "spi6": r(self.spi6, 3),
            "cdd": self.cdd, "et0": r(self.et0, 3),
            "nddi_t": r(self.nddi_t, 4), "ndvi_t": r(self.ndvi_t, 4),
            "vci_t": r(self.vci_t, 3), "lst_t": r(self.lst_t, 3),
        }


def compute_quadrant_variables(q: config.Quadrant, end_date: "ee.Date") -> QuadrantVariables:
    """Orquesta todas las llamadas a GEE + calculo local (SPI/ET0) para UN
    cuadrante. Es la unica funcion que acquire.py necesita llamar."""
    geom = quadrant_geometry(q)

    ndvi, ndwi = ndvi_ndwi_now(geom, end_date, config.S2_LOOKBACK_DAYS)
    nddi = (ndvi - ndwi) / (ndvi + ndwi) if (ndvi + ndwi) not in (0, float("nan")) and not np.isnan(ndvi + ndwi) else float("nan")
    lst = lst_celsius(geom, end_date, config.LST_LOOKBACK_DAYS)

    ndvi_min, ndvi_max = ndvi_historical_minmax(geom, end_date, config.VCI_HISTORY_YEARS)
    vci = (ndvi - ndvi_min) / (ndvi_max - ndvi_min) * 100.0 if (ndvi_max - ndvi_min) not in (0,) and not np.isnan(ndvi_max - ndvi_min) else float("nan")

    precip = precip_daily_series(geom, end_date, max(config.SPI_HISTORY_YEARS * 365, config.CDD_WINDOW_DAYS))
    spi1 = spi_from_series(precip, 1) if len(precip) else float("nan")
    spi3 = spi_from_series(precip, 3) if len(precip) else float("nan")
    spi6 = spi_from_series(precip, 6) if len(precip) else float("nan")
    cdd = count_consecutive_dry_days(precip[-config.CDD_WINDOW_DAYS:], config.CDD_DRY_THRESHOLD_MM) if len(precip) else 0

    tmean, tmax, tmin = era5_temps(geom, end_date)
    lat_center = (q.lat_min + q.lat_max) / 2.0
    doy = dt.datetime.utcnow().timetuple().tm_yday
    et0 = et0_hargreaves_mm_day(tmean, tmax, tmin, lat_center, doy) if not np.isnan(tmean) else float("nan")

    ndvi_series_14 = ndvi_series(geom, end_date, config.TREND_WINDOW_DAYS)
    ndvi_t = linear_trend(ndvi_series_14)
    # nddi/vci/lst trend14 se aproximan con la misma serie de NDVI escalada,
    # salvo lst_t que usa su propia serie MODIS -- ver TODO mas abajo.
    nddi_t = linear_trend(ndvi_series_14) * -1.0 if len(ndvi_series_14) else float("nan")  # TODO(equipo): reemplazar por serie NDDI real si se requiere mayor precision
    vci_t = float("nan")   # TODO(equipo): requiere serie VCI diaria (climatologia por dia), no solo el valor puntual
    lst_t = float("nan")   # TODO(equipo): requiere serie LST de 14 dias (MOD11A2 es compuesto de 8 dias, ventana corta)

    dsi_score = compute_dsi_score(spi3, vci, nddi)
    cur_class = classify_cur_class(vci)

    return QuadrantVariables(
        ndvi=ndvi, ndwi=ndwi, nddi=nddi, lst=lst, vci=vci, dsi_score=dsi_score,
        cur_class=cur_class, spi1=spi1, spi3=spi3, spi6=spi6, cdd=cdd, et0=et0,
        nddi_t=nddi_t, ndvi_t=ndvi_t, vci_t=vci_t, lst_t=lst_t,
    )
