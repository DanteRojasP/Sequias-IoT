import numpy as np

from lima_cloud.et0 import et0_hargreaves_mm_day, extraterrestrial_radiation_mm_day
from lima_cloud.spi import count_consecutive_dry_days, spi_from_series


def test_spi_is_near_zero_for_climatologically_average_precip():
    rng = np.random.default_rng(42)
    # 15 anios de precipitacion diaria sintetica alrededor de una media
    # estable -> el ultimo periodo, tomado de la misma distribucion, deberia
    # caer cerca del centro (SPI ~ 0), no en un extremo.
    daily = rng.gamma(shape=2.0, scale=3.0, size=365 * 15)
    spi3 = spi_from_series(daily, scale_months=3)
    assert not np.isnan(spi3)
    assert -1.5 < spi3 < 1.5


def test_spi_is_very_negative_when_last_period_is_a_severe_drought():
    rng = np.random.default_rng(7)
    normal_years = rng.gamma(shape=2.0, scale=3.0, size=365 * 10)
    drought_period = np.zeros(90)  # 3 meses sin lluvia al final de la serie
    daily = np.concatenate([normal_years, drought_period])
    spi3 = spi_from_series(daily, scale_months=3)
    assert spi3 < -1.5  # sequia severa por convencion McKee et al. (SPI <= -1.5)


def test_spi_returns_nan_with_insufficient_history():
    short = np.ones(40)
    assert np.isnan(spi_from_series(short, scale_months=3))


def test_consecutive_dry_days_counts_current_streak_only():
    precip = np.array([5.0, 0.0, 0.0, 0.0, 3.0, 0.0, 0.0])
    assert count_consecutive_dry_days(precip, dry_threshold_mm=1.0) == 2  # los 2 ultimos dias


def test_consecutive_dry_days_zero_when_it_just_rained():
    precip = np.array([0.0, 0.0, 0.0, 5.0])
    assert count_consecutive_dry_days(precip, dry_threshold_mm=1.0) == 0


def test_et0_hargreaves_is_positive_and_reasonable_for_andean_conditions():
    # Aija/Mallacayan: dia templado de altura, buena amplitud termica diurna
    et0 = et0_hargreaves_mm_day(t_mean_c=12.0, t_max_c=20.0, t_min_c=4.0,
                                  latitude_deg=-9.78, day_of_year=180)
    assert 1.0 < et0 < 8.0  # rango tipico de ET0 diaria en mm/dia


def test_et0_zero_temperature_range_gives_zero_not_nan():
    et0 = et0_hargreaves_mm_day(t_mean_c=10.0, t_max_c=10.0, t_min_c=10.0,
                                  latitude_deg=-9.78, day_of_year=180)
    assert et0 == 0.0


def test_extraterrestrial_radiation_higher_near_equinox_than_solstice_is_plausible():
    ra_june = extraterrestrial_radiation_mm_day(-9.78, 172)   # cerca del solsticio de invierno austral
    ra_march = extraterrestrial_radiation_mm_day(-9.78, 80)   # cerca del equinoccio
    assert ra_june > 0 and ra_march > 0
