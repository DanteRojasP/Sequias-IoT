import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

with open("compare_output.json", encoding="utf-8") as f:
    data = json.load(f)

fechas = [d["fecha"][5:] for d in data]
t_local = [d["local"]["t_avg"] for d in data]
tmin_local = [d["local"]["t_min"] for d in data]
tmax_local = [d["local"]["t_max"] for d in data]
t_era5 = [d["era5"]["t_mean"] if d["era5"] else None for d in data]

pairs = [(l, e) for l, e in zip(t_local, t_era5) if e is not None]
loc_arr = np.array([p[0] for p in pairs])
era_arr = np.array([p[1] for p in pairs])
bias = float(np.mean(loc_arr - era_arr))
rmse = float(np.sqrt(np.mean((loc_arr - era_arr) ** 2)))
corr = float(np.corrcoef(loc_arr, era_arr)[0, 1])
print(f"n={len(pairs)} bias={bias:.2f} rmse={rmse:.2f} corr={corr:.2f}")

plt.rcParams.update({"font.family": "Times New Roman", "font.size": 11})
fig, ax = plt.subplots(figsize=(7.0, 3.3), dpi=200)

x = np.arange(len(fechas))
ax.fill_between(x, tmin_local, tmax_local, color="#4C72B0", alpha=0.18, label="Rango diario local (mín-máx)")
ax.plot(x, t_local, "o-", color="#4C72B0", linewidth=1.8, markersize=4, label="T. promedio local (BME280, Mallacayán)")
x_era = [xi for xi, e in zip(x, t_era5) if e is not None]
y_era = [e for e in t_era5 if e is not None]
ax.plot(x_era, y_era, "s--", color="#C44E52", linewidth=1.8, markersize=4, label="T. promedio ERA5-Land (reanálisis, 0.1°)")

ax.set_xticks(x)
ax.set_xticklabels(fechas, rotation=0)
ax.set_xlabel("Fecha (agosto 2026)")
ax.set_ylabel("Temperatura (°C)")
ax.yaxis.set_major_locator(MaxNLocator(integer=True))
ax.legend(fontsize=8, loc="upper right", framealpha=0.9)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(axis="y", linewidth=0.4, alpha=0.5)
ax.set_title(f"Sesgo medio = {bias:+.2f} °C · RMSE = {rmse:.2f} °C · r = {corr:.2f}  (n={len(pairs)} días con dato ERA5-Land disponible)", fontsize=9)

fig.tight_layout()
out = r"C:\Users\Dante\AppData\Local\Temp\claude\C--Users-Dante-Documents-IAC-Sequias\a83e4011-80f0-49da-b429-a656624fcf52\scratchpad\figs\fig_validacion_local_vs_era5.png"
fig.savefig(out, bbox_inches="tight")
print("guardado:", out)

with open("compare_stats.json", "w") as f:
    json.dump({"n": len(pairs), "bias": bias, "rmse": rmse, "corr": corr}, f, indent=2)
