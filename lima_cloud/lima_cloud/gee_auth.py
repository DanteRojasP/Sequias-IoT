"""
Autenticacion de Earth Engine para correr desatendido en la nube (sin
navegador, sin interaccion humana) -- usa una cuenta de servicio, que es el
mecanismo soportado para procesos en background.

Setup (una sola vez, ver README para el detalle paso a paso):
  1. Crear un proyecto de Google Cloud y habilitar la Earth Engine API.
  2. Crear una cuenta de servicio y una clave JSON.
  3. Registrar esa cuenta de servicio para uso no comercial/investigacion en
     https://code.earthengine.google.com/register (Earth Engine exige
     registro incluso para cuentas de servicio).
  4. Poner la ruta al JSON en la variable de entorno GEE_SERVICE_ACCOUNT_KEY.
"""
from __future__ import annotations

import os

import ee


def init_earth_engine() -> None:
    key_path = os.environ.get("GEE_SERVICE_ACCOUNT_KEY")
    project = os.environ.get("GEE_PROJECT", "")

    if key_path:
        if not os.path.exists(key_path):
            raise FileNotFoundError(
                f"GEE_SERVICE_ACCOUNT_KEY apunta a '{key_path}', que no existe. "
                "Revisa la ruta o vuelve a descargar la clave JSON de la cuenta de servicio."
            )
        credentials = ee.ServiceAccountCredentials(email=None, key_file=key_path)
        ee.Initialize(credentials, project=project or None)
    else:
        # Fallback para desarrollo local interactivo (abre el navegador para
        # el login OAuth). No usar este camino en un servidor desatendido.
        ee.Initialize(project=project or None)
