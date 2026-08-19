# lima_cloud — adquisición satelital periódica (lado Lima)

Corre **solo en la nube**: cada `ACQUIRE_INTERVAL_HOURS` horas descarga/calcula
las 16 variables satelitales/climáticas + nivel de alerta por cada uno de los
36 cuadrantes (grilla 6×6) de la cuenca, las firma con el mismo CRC32 que
espera el firmware, y las sirve por HTTP para que la Raspberry Pi 4 (con el
LILYGO T-SIM7000 de Lima) las reenvíe al nodo de Mallacayán.

No descarga imágenes completas: todo el cómputo pesado (bandas, máscara de
nubes, reducción espacial) corre en los servidores de Google Earth Engine;
este proceso solo pide el número final por cuadrante.

## Instalación

```bash
pip install -r requirements.txt
cp .env.example .env   # editar con tus valores reales
```

### Cuenta de Earth Engine (una sola vez)

1. Crear un proyecto en Google Cloud y habilitar la Earth Engine API.
2. Crear una cuenta de servicio + clave JSON.
3. Registrar la cuenta de servicio en https://code.earthengine.google.com/register
   (Earth Engine lo exige incluso para cuentas de servicio, uso no comercial).
4. Poner la ruta de la clave en `GEE_SERVICE_ACCOUNT_KEY` dentro de `.env`.

## Correr

```bash
python -m lima_cloud.main
```

Esto arranca el scheduler (adquisición periódica en background) **y** el
servidor HTTP en el mismo proceso, puerto `8080` por defecto.

- `GET /cache/<quad>` → lo que consume `http_fetch_cache()` del firmware.
- `POST /result/<quad>` → lo que manda `http_post_result()` del firmware.
- `GET /health` → cuántos cuadrantes tienen cache vigente.

Para correr solo una adquisición manual (sin levantar el servidor):

```bash
python -m lima_cloud.acquire
```

## Docker

```bash
docker build -t lima-cloud .
docker run --env-file .env -p 8080:8080 -v $(pwd)/cache:/app/cache lima-cloud
```

## Tests

```bash
pytest tests/ -v
```

18 pruebas, todas corren **sin conexión a Earth Engine** (CRC, SPI, ET0, la
grilla de cuadrantes y el servidor HTTP con un caché simulado). Ese es
exactamente el código que se pudo ejecutar y verificar en este entorno.

**Lo que NO se pudo probar aquí:** las llamadas reales a Earth Engine
(`indices.py`) — este entorno no tiene una cuenta de servicio de GEE
autenticada. La sintaxis sigue el patrón estándar de `earthengine-api`, pero
la primera corrida real (`python -m lima_cloud.acquire` con `.env` completo)
va a ser la primera verificación end-to-end contra datos reales. Revisar los
logs de esa corrida cuadrante por cuadrante antes de confiar en el cache.

## Variables que produce (por cuadrante)

Los 16 campos numéricos que espera `feature_vector.cpp`, más `ts` (fecha) y
`crc` (firma). **La nube solo entrega datos crudos/derivados de entrada al
modelo — no calcula ningún nivel de alerta ni estima si hay sequía.** Esa
decisión es exclusivamente del modelo Random Forest embebido en el
ESP32-S3 (`drought_onset_model.h`), con estos valores como entrada.

| Campo | Fuente | Método |
|---|---|---|
| `ndvi`, `ndwi` | Sentinel-2 SR | NDVI estándar; NDWI de Gao 1996 (NIR-SWIR) — mismo que ref. [7] del paper |
| `nddi` | derivado | `(ndvi-ndwi)/(ndvi+ndwi)`, ref. [8] |
| `lst` | MODIS MOD11A2 | banda LST_Day_1km, compuesto 8 días |
| `vci` | Sentinel-2 + climatología | Kogan 1995, ref. [14]: `(ndvi-min_hist)/(max_hist-min_hist)*100` |
| `spi1`/`spi3`/`spi6` | CHIRPS | SPI estándar (McKee et al. 1993), ajuste gamma |
| `cdd` | CHIRPS | racha actual de días secos (<1 mm/día) |
| `et0` | ERA5-Land | Hargreaves-Samani 1985 |
| `dsi_score`, `cur_class` | **heurística propia** | features de entrada al modelo, ver advertencia abajo |
| `nddi_t`, `ndvi_t`, `vci_t`, `lst_t` | series 14 días | pendiente de regresión lineal |

## ⚠️ Advertencias que hay que resolver antes de producción

1. **`dsi_score` y `cur_class` son una propuesta mía, no la definición de
   entrenamiento.** El modelo `drought_onset_model.h` ya fue entrenado con
   estas variables definidas de alguna forma específica (GridSearch +
   TimeSeriesSplit, según el paper). Si esas fórmulas no coinciden
   exactamente con las de acá, el modelo va a recibir entradas fuera de la
   distribución de entrenamiento y sus predicciones no van a ser confiables.
   **Hay que conseguir la fórmula exacta del equipo de ML y reemplazarla en
   `indices.py`.**
2. **`vci_t` y `lst_t` quedaron en `NaN`** — necesitan una serie temporal de
   14 días de VCI y de LST respectivamente, no solo el valor puntual actual
   (VCI requiere climatología día a día; LST es un compuesto de 8 días, la
   ventana de 14 días da como máximo 2 puntos). Están marcados con
   `TODO(equipo)` en `indices.py`.
3. **El bounding box de la cuenca en `config.py`** está centrado en las
   coordenadas GPS reales del nodo (lat=-9.718924, lon=-77.598083), pero
   sigue siendo un cuadrado alrededor del punto, no la extensión real de la
   cuenca de la laguna Mullaca.
