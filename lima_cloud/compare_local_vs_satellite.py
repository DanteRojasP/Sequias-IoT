"""
Comparacion validacion: datos locales medidos en Mallacayan (01-13 ago 2026)
vs. estimaciones climaticas/satelitales (ERA5-Land) para el mismo periodo y
punto. Corre UNA vez, imprime resultados y guarda un JSON con las series
para graficar despues. No modifica nada del pipeline de produccion
(acquire.py, indices.py) -- es un script de analisis aparte.
"""
from __future__ import annotations

import datetime as dt
import json

import ee
import openpyxl
from dotenv import load_dotenv

load_dotenv()

from lima_cloud import config, gee_auth

LOCAL_XLSX = r"C:\Users\Dante\Downloads\Mallacayan_clima_ago2026_1min.xlsx"


def load_local_daily():
    wb = openpyxl.load_workbook(LOCAL_XLSX, data_only=True)
    ws = wb["Resumen diario"]
    rows = list(ws.iter_rows(values_only=True))[1:]
    out = []
    for r in rows:
        fecha, tmin, tmax, tavg, hmin, hmax, pavg = r
        out.append({
            "fecha": str(fecha), "t_min": tmin, "t_max": tmax, "t_avg": tavg,
            "h_min": hmin, "h_max": hmax, "p_avg": pavg,
        })
    return out


def era5_daily_for_point(geom, date_iso: str):
    d = ee.Date(date_iso)
    coll = (
        ee.ImageCollection(config.ERA5_LAND_COLLECTION)
        .filterBounds(geom)
        .filterDate(d, d.advance(1, "day"))
    )
    if coll.size().getInfo() == 0:
        return None
    img = ee.Image(coll.first())
    stat = img.select([
        "temperature_2m_max", "temperature_2m_min", "temperature_2m",
        "dewpoint_temperature_2m", "surface_pressure",
    ]).reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=10000, bestEffort=True).getInfo()
    if not stat or stat.get("temperature_2m_max") is None:
        return None
    tmax = stat["temperature_2m_max"] - 273.15
    tmin = stat["temperature_2m_min"] - 273.15
    tmean = stat["temperature_2m"] - 273.15
    dewp = stat["dewpoint_temperature_2m"] - 273.15
    psurf_hpa = stat["surface_pressure"] / 100.0
    # Humedad relativa aproximada (formula Magnus) a partir de T media y punto de rocio
    import math
    a, b = 17.625, 243.04
    rh = 100.0 * math.exp((a * dewp) / (b + dewp)) / math.exp((a * tmean) / (b + tmean))
    return {
        "t_max": tmax, "t_min": tmin, "t_mean": tmean,
        "rh_approx": rh, "p_surf_hpa": psurf_hpa,
    }


def main():
    gee_auth.init_earth_engine()
    quads = config.build_grid()
    q = next(x for x in quads if x.id == config.NODE_QUADRANT_ID)
    geom = ee.Geometry.Rectangle([q.lon_min, q.lat_min, q.lon_max, q.lat_max]).centroid(1)

    local = load_local_daily()
    results = []
    print(f"{'fecha':12} {'T_min_local':>11} {'T_max_local':>11} {'T_avg_local':>11} | {'T_min_ERA5':>10} {'T_max_ERA5':>10} {'T_avg_ERA5':>10} | {'dT_avg':>7}")
    for d in local:
        era5 = era5_daily_for_point(geom, d["fecha"])
        row = {"fecha": d["fecha"], "local": d, "era5": era5}
        results.append(row)
        if era5:
            dT = d["t_avg"] - era5["t_mean"]
            print(f"{d['fecha']:12} {d['t_min']:11.2f} {d['t_max']:11.2f} {d['t_avg']:11.2f} | "
                  f"{era5['t_min']:10.2f} {era5['t_max']:10.2f} {era5['t_mean']:10.2f} | {dT:7.2f}")
        else:
            print(f"{d['fecha']:12} {d['t_min']:11.2f} {d['t_max']:11.2f} {d['t_avg']:11.2f} | (sin dato ERA5)")

    with open("compare_output.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("\nGuardado en compare_output.json")


if __name__ == "__main__":
    main()
