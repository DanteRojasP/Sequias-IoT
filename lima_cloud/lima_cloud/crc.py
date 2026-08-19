"""
CRC32 e integridad del mensaje "q", espejo exacto de main/feature_vector.cpp
(crc32_bitwise + find_q_object) para que el nodo pueda validar el mensaje
sin re-serializar el JSON.

Contrato (segun el comentario textual en feature_vector.cpp):
    "crc = CRC32 (IEEE, el de zlib) sobre los bytes exactos del objeto q tal
    como viajan, truncado a 16 bits. NO re-serialices el JSON para calcular
    el CRC."

Esto implica: el CRC se calcula sobre la subcadena literal `{...}` de "q"
como queda escrita en el JSON de salida, no sobre una reinterpretacion. Por
eso build_payload() calcula el CRC directamente sobre los bytes que genero,
antes de insertarlos en el sobre final -- nunca sobre un dict re-serializado
despues.
"""
from __future__ import annotations

import json
import zlib
from typing import Any


def crc16_of_bytes(data: bytes) -> int:
    """CRC32 IEEE (identico al zlib.crc32 estandar, mismo polinomio 0xEDB88320,
    init/xor final 0xFFFFFFFF que usa la implementacion bitwise del firmware),
    truncado a 16 bits -- replica exacta de crc32_bitwise(...) & 0xFFFF."""
    return zlib.crc32(data) & 0xFFFF


def _compact_json(obj: Any) -> str:
    # Separadores sin espacios: minimiza bytes (importa para el buffer fijo
    # de 1536 bytes del nodo) y da una serializacion determinista.
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def build_payload(q: dict, ts: str) -> tuple[str, dict]:
    """Arma el JSON final {"q": {...}, "ts": ..., "crc": "..."} y devuelve
    (json_str, info) donde info trae el crc calculado y el tamano en bytes,
    utiles para logging/tests.

    q y ts deben venir ya completos -- esta funcion no valida contenido,
    solo serializa y firma.
    """
    q_str = _compact_json(q)
    crc = crc16_of_bytes(q_str.encode("utf-8"))
    crc_hex = f"{crc:04x}"

    # Construccion manual del sobre final (no json.dumps del dict completo)
    # para que la subcadena de "q" que viaja sea EXACTAMENTE q_str, ya que
    # find_q_object() del firmware ubica "q":{...} contando llaves sobre el
    # cuerpo crudo -- si json.dumps reformateara q al serializar el dict
    # completo, seguiria siendo el mismo texto porque ya es compacto y
    # determinista, pero se arma explicito para dejar la garantia por escrito.
    ts_str = _compact_json(ts)
    payload = f'{{"q":{q_str},"ts":{ts_str},"crc":"{crc_hex}"}}'

    return payload, {"crc_hex": crc_hex, "crc_int": crc, "size_bytes": len(payload.encode("utf-8"))}
