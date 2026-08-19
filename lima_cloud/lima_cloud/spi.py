"""
Standardized Precipitation Index (SPI), calculo estandar (McKee et al. 1993):
ajustar una distribucion gamma a la precipitacion acumulada de la ventana
(1/3/6 meses) sobre el historico, y transformar el percentil resultante a un
z-score de la normal estandar.

No depende de earthengine: recibe una serie de precipitacion diaria (mm) ya
descargada, para poder testearse con datos sinteticos sin GEE.
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def _monthly_totals(daily_precip_mm: np.ndarray, days_per_month: int = 30) -> np.ndarray:
    """Convierte una serie diaria en totales por bloques de ~30 dias
    (aproximacion suficiente para SPI operativo cuando no se dispone del
    calendario exacto de meses)."""
    n_full = len(daily_precip_mm) // days_per_month
    trimmed = daily_precip_mm[: n_full * days_per_month]
    return trimmed.reshape(n_full, days_per_month).sum(axis=1)


def rolling_sum(monthly_totals: np.ndarray, scale_months: int) -> np.ndarray:
    """Suma movil de `scale_months` meses (p.ej. SPI3 = suma movil de 3 meses)."""
    if len(monthly_totals) < scale_months:
        return np.array([])
    kernel = np.ones(scale_months)
    return np.convolve(monthly_totals, kernel, mode="valid")


def spi_from_series(daily_precip_mm: np.ndarray, scale_months: int, days_per_month: int = 30) -> float:
    """SPI del ultimo periodo de `scale_months` meses, ajustado contra el
    historico completo recibido en daily_precip_mm.

    Devuelve np.nan si no hay suficiente historico para un ajuste confiable
    (se requieren al menos ~8 valores de la serie acumulada, minimo docente
    para un ajuste gamma razonable; en produccion se recomienda >= 20 anios
    de historico, muy por encima de este piso).
    """
    monthly = _monthly_totals(daily_precip_mm, days_per_month)
    accum = rolling_sum(monthly, scale_months)
    if len(accum) < 8:
        return float("nan")

    current = accum[-1]

    # La gamma no esta definida en 0: la practica estandar (McKee et al.)
    # es separar la probabilidad de precipitacion cero y mezclarla con la
    # gamma ajustada solo sobre los valores > 0.
    zeros = accum[accum <= 0]
    nonzero = accum[accum > 0]
    q_zero = len(zeros) / len(accum)

    if len(nonzero) < 4:
        return float("nan")

    shape, loc, scale = stats.gamma.fit(nonzero, floc=0)

    if current <= 0:
        cdf = q_zero
    else:
        cdf = q_zero + (1 - q_zero) * stats.gamma.cdf(current, shape, loc=loc, scale=scale)

    cdf = min(max(cdf, 1e-6), 1 - 1e-6)  # evita +-inf en la inversa normal
    return float(stats.norm.ppf(cdf))


def count_consecutive_dry_days(daily_precip_mm: np.ndarray, dry_threshold_mm: float = 1.0) -> int:
    """CDD: dias secos consecutivos hasta el final de la serie (racha
    actual, no la maxima historica) -- es la definicion relevante para una
    senal de alerta temprana."""
    count = 0
    for v in daily_precip_mm[::-1]:
        if v < dry_threshold_mm:
            count += 1
        else:
            break
    return count
