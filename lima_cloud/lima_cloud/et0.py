"""
ET0 (evapotranspiracion de referencia) por el metodo de Hargreaves-Samani
(1985). Se elige Hargreaves y no Penman-Monteith porque solo necesita
temperatura (max/min/media) y radiacion extraterrestre calculable
analiticamente por latitud y dia del anio -- ERA5-Land ya trae Tmax/Tmin
diarios, y evita depender de radiacion solar/viento/humedad medidos, que
son mas dificiles de conseguir por satelite con buena cobertura local.

Referencia: Hargreaves, G.H. & Samani, Z.A. (1985). "Reference crop
evapotranspiration from temperature." Applied Engineering in Agriculture,
1(2), 96-99.
"""
from __future__ import annotations

import math


def extraterrestrial_radiation_mm_day(latitude_deg: float, day_of_year: int) -> float:
    """Ra en mm/dia equivalentes de evaporacion (FAO-56, eq. 21-25)."""
    lat_rad = math.radians(latitude_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    decl = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)

    x = -math.tan(lat_rad) * math.tan(decl)
    x = min(max(x, -1.0), 1.0)  # clamp: evita domain error cerca de los polos / solsticios
    ws = math.acos(x)

    gsc = 0.0820  # constante solar, MJ m-2 min-1
    ra_mj = (24 * 60 / math.pi) * gsc * dr * (
        ws * math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl) * math.sin(ws)
    )
    # 1 MJ/m2/dia de radiacion equivale a 0.408 mm/dia de evaporacion (FAO-56, eq. 20)
    return ra_mj * 0.408


def et0_hargreaves_mm_day(t_mean_c: float, t_max_c: float, t_min_c: float,
                            latitude_deg: float, day_of_year: int) -> float:
    """ET0 diaria (mm/dia). Formula de Hargreaves-Samani:
    ET0 = 0.0023 * (Tmean + 17.8) * sqrt(Tmax - Tmin) * Ra
    """
    ra = extraterrestrial_radiation_mm_day(latitude_deg, day_of_year)
    delta_t = max(t_max_c - t_min_c, 0.0)  # nunca negativo por ruido de datos
    return 0.0023 * (t_mean_c + 17.8) * math.sqrt(delta_t) * ra
