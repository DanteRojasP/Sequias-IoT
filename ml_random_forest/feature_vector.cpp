#include "feature_vector.hpp"
#include "cJSON.h"
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cmath>

// --- CRC32 (IEEE, el mismo de zlib) bitwise, sin tabla (no gastar RAM en
// lookup). Del contrato del equipo, textual: "crc = CRC32 (IEEE, el de
// zlib) sobre los bytes exactos del objeto q tal como viajan, truncado a 16
// bits. NO re-serialices el JSON para calcular el CRC." ---
static uint32_t crc32_bitwise(const uint8_t *d, size_t n) {
    uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; i++) {
        c ^= d[i];
        for (int k = 0; k < 8; k++) {
            c = (c >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(c & 1)));
        }
    }
    return c ^ 0xFFFFFFFFu;
}

// Localiza la subcadena del valor de "q" (desde su '{' hasta la '}' que
// casa, contando llaves y respetando strings/escapes), SIN pasar por el
// parser JSON -- el CRC se calcula sobre los bytes exactos tal como
// viajaron, no sobre una re-serialización. Devuelve -1 si no la encuentra.
static int find_q_object(const char *body, size_t body_len, size_t *ini, size_t *fin) {
    const char *key = "\"q\":";
    const char *k = strstr(body, key);
    if (k == nullptr) return -1;
    const char *b = strchr(k, '{');
    if (b == nullptr) return -1;

    int depth = 0;
    bool in_str = false, esc = false;
    size_t start = (size_t)(b - body);
    for (size_t i = start; i < body_len; i++) {
        char c = body[i];
        if (esc) { esc = false; continue; }
        if (c == '\\') { esc = true; continue; }
        if (c == '"') { in_str = !in_str; continue; }
        if (in_str) continue;
        if (c == '{') depth++;
        else if (c == '}') {
            depth--;
            if (depth == 0) { *ini = start; *fin = i; return 0; }
        }
    }
    return -1;
}

bool feature_vector_verify_crc(const char *json_body, size_t body_len,
                                uint16_t *out_calc_crc, uint16_t *out_recv_crc) {
    *out_calc_crc = 0;
    *out_recv_crc = 0;

    size_t q_ini, q_fin;
    if (find_q_object(json_body, body_len, &q_ini, &q_fin) != 0) {
        return false; // no se ubico el objeto "q": descartar el mensaje completo
    }
    uint32_t calc_crc = crc32_bitwise((const uint8_t *)(json_body + q_ini), q_fin - q_ini + 1);

    cJSON *root = cJSON_ParseWithLength(json_body, body_len);
    if (root == nullptr) {
        return false;
    }
    const cJSON *crc_field = cJSON_GetObjectItemCaseSensitive(root, "crc");
    if (!cJSON_IsString(crc_field) || crc_field->valuestring == nullptr) {
        cJSON_Delete(root);
        return false; // falta el campo "crc": descartar el mensaje completo
    }
    uint32_t recv_crc = (uint32_t)strtoul(crc_field->valuestring, nullptr, 16);
    cJSON_Delete(root);

    *out_calc_crc = (uint16_t)(calc_crc & 0xFFFF);
    *out_recv_crc = (uint16_t)(recv_crc & 0xFFFF);
    return *out_calc_crc == *out_recv_crc;
}

bool feature_vector_parse(const char *json_body, size_t body_len,
                           float q_row, float q_col, FeatureVector *out) {
    memset(out, 0, sizeof(*out));

    cJSON *root = cJSON_ParseWithLength(json_body, body_len);
    if (root == nullptr) {
        return false;
    }

    const cJSON *q = cJSON_GetObjectItemCaseSensitive(root, "q");
    const cJSON *ts = cJSON_GetObjectItemCaseSensitive(root, "ts");
    if (!cJSON_IsObject(q) || !cJSON_IsString(ts) || ts->valuestring == nullptr) {
        cJSON_Delete(root);
        return false; // estructura inesperada: falta "q" o "ts"
    }

    auto num = [&](const char *key) -> double {
        const cJSON *item = cJSON_GetObjectItemCaseSensitive(q, key);
        return cJSON_IsNumber(item) ? item->valuedouble : 0.0;
    };

    // Orden EXACTO del contrato (18 campos del JSON + q_row/q_col constantes
    // de este nodo + month_sin/cos calculados). dsi_score/cur_class/cdd se
    // guardan como float aunque el JSON los traiga como enteros.
    out->x[0] = (float)num("ndvi");
    out->x[1] = (float)num("ndwi");
    out->x[2] = (float)num("nddi");
    out->x[3] = (float)num("lst");
    out->x[4] = (float)num("vci");
    out->x[5] = (float)num("dsi_score");
    out->x[6] = (float)num("cur_class");
    out->x[7] = (float)num("spi1");
    out->x[8] = (float)num("spi3");
    out->x[9] = (float)num("spi6");
    out->x[10] = (float)num("cdd");
    out->x[11] = (float)num("et0");
    out->x[12] = (float)num("nddi_t");
    out->x[13] = (float)num("ndvi_t");
    out->x[14] = (float)num("vci_t");
    out->x[15] = (float)num("lst_t");
    out->x[16] = q_row;
    out->x[17] = q_col;

    // "ts" formato "2026-06-30" -> mes = 6. sin(PI) no es exactamente 0 en
    // float, por eso se calcula con sinf()/cosf() y nunca se hardcodea.
    int year = 0, mon = 0, day = 0;
    sscanf(ts->valuestring, "%d-%d-%d", &year, &mon, &day);
    out->x[18] = sinf(2.0f * (float)M_PI * (float)mon / 12.0f);
    out->x[19] = cosf(2.0f * (float)M_PI * (float)mon / 12.0f);

    const cJSON *lvl = cJSON_GetObjectItemCaseSensitive(q, "lvl");
    if (cJSON_IsString(lvl) && lvl->valuestring != nullptr) {
        strncpy(out->lvl_cloud, lvl->valuestring, sizeof(out->lvl_cloud) - 1);
    }

    cJSON_Delete(root);
    return true;
}
