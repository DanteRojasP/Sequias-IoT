"""
Verifica que crc.crc16_of_bytes() (basado en zlib.crc32) produce EXACTAMENTE
el mismo resultado que la implementacion bitwise del firmware
(main/feature_vector.cpp::crc32_bitwise), portada aca linea por linea desde
el C++ original para comparar. Si algun dia cambia el firmware, este test
es la forma de detectar que el cloud dejo de calzar con el nodo.
"""
import json

from lima_cloud.crc import build_payload, crc16_of_bytes


def crc32_bitwise_reference(data: bytes) -> int:
    """Puerto linea por linea de crc32_bitwise() en feature_vector.cpp."""
    c = 0xFFFFFFFF
    for byte in data:
        c ^= byte
        for _ in range(8):
            mask = -(c & 1) & 0xFFFFFFFF
            c = (c >> 1) ^ (0xEDB88320 & mask)
    return c ^ 0xFFFFFFFF


def test_bitwise_reference_matches_zlib_based_implementation():
    samples = [
        b"",
        b"a",
        b'{"ndvi":0.17,"ndwi":-0.09}',
        b'{"quad":"3_2","votes":37,"level":"ROJO"}',
        bytes(range(256)),
    ]
    for s in samples:
        expected = crc32_bitwise_reference(s) & 0xFFFF
        got = crc16_of_bytes(s)
        assert got == expected, f"mismatch para {s!r}: esperado {expected:04x}, obtuvo {got:04x}"


def test_build_payload_crc_is_over_the_exact_q_substring():
    q = {"ndvi": 0.17, "ndwi": -0.09, "nddi": 2.1, "cur_class": 1, "lvl": "ROJO"}
    payload, info = build_payload(q, "2026-06-30")

    # El firmware ubica "q":{...} contando llaves sobre el body crudo y
    # calcula el CRC sobre esa subcadena exacta -- replicamos esa ubicacion
    # aca para confirmar que el crc reportado coincide con esos bytes.
    start = payload.index('"q":') + len('"q":')
    depth = 0
    end = None
    for i in range(start, len(payload)):
        if payload[i] == "{":
            depth += 1
        elif payload[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    q_substring = payload[start:end]

    assert crc16_of_bytes(q_substring.encode("utf-8")) == info["crc_int"]

    # y que el JSON completo es valido y trae los tres campos esperados
    parsed = json.loads(payload)
    assert set(parsed.keys()) == {"q", "ts", "crc"}
    assert parsed["ts"] == "2026-06-30"
    assert parsed["crc"] == info["crc_hex"]


def test_payload_size_fits_the_node_fixed_buffer():
    # buffer fijo del nodo: 1536 bytes (GSM_PLAN_ESP_IDF.md, seccion 4)
    q = {
        "ndvi": 0.1726, "ndwi": -0.09, "nddi": 2.1, "lst": 24.5, "vci": 12.4,
        "dsi_score": 2.0, "cur_class": 1, "spi1": -0.9, "spi3": -1.902, "spi6": -0.4,
        "cdd": 40, "et0": 3.292, "nddi_t": 0.31, "ndvi_t": -0.02, "vci_t": -8.1,
        "lst_t": 2.4, "lvl": "ROJO",
    }
    payload, info = build_payload(q, "2026-06-30")
    assert info["size_bytes"] < 1536
    # referencia del informe: "~315 bytes/cuadrante" -- damos margen amplio
    assert info["size_bytes"] < 500
