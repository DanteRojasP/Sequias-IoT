# -*- coding: utf-8 -*-
"""Extrae la frecuencia de uso de cada variable como criterio de corte en los
40 arboles de drought_onset_model.h (dato real, no inventado) y genera un
grafico de barras 'tipo paper' con los nombres reales de las 20 variables."""
import re
import json

src_path = r"C:\Users\Dante\AppData\Local\Temp\claude\C--Users-Dante-Documents-IAC-Sequias\a83e4011-80f0-49da-b429-a656624fcf52\scratchpad\zip\module\YakuX_Modulo\main\drought_onset_model.h"
text = open(src_path, encoding="utf-8").read()

start_marker = "uint8_t votesForOnset(float *x) {"
start = text.index(start_marker) + len(start_marker)
depth = 1
i = start
while depth > 0:
    if text[i] == '{':
        depth += 1
    elif text[i] == '}':
        depth -= 1
    i += 1
body = text[start:i-1]
body = re.sub(r'//[^\n]*', '', body) + '\n}'

n = len(body)

def skip_ws(p):
    while p < n and body[p].isspace():
        p += 1
    return p

def parse_block(p):
    stmts = []
    while True:
        p = skip_ws(p)
        if body[p] == '}':
            return stmts, p + 1
        if body.startswith('if', p) and not body[p+2].isalnum():
            p = skip_ws(p + 2)
            close = body.index(')', p)
            cond = body[p+1:close].strip()
            p = skip_ws(close + 1)
            then_block, p = parse_block(p + 1)
            p = skip_ws(p)
            else_block = None
            if body.startswith('else', p):
                p = skip_ws(p + 4)
                else_block, p = parse_block(p + 1)
            stmts.append(('if', cond, then_block, else_block))
            continue
        if body.startswith('votes[', p):
            semi = body.index(';', p)
            p = semi + 1
            stmts.append(('vote',))
            continue
        if body.startswith('return', p):
            semi = body.index(';', p)
            p = semi + 1
            stmts.append(('return',))
            continue
        if body.startswith('uint8_t votes[2]', p):
            semi = body.index(';', p)
            p = semi + 1
            stmts.append(('init',))
            continue
        raise Exception("unexpected: " + repr(body[p:p+40]))

stmts, _ = parse_block(0)
trees = [s for s in stmts if s[0] == 'if']
print("trees found:", len(trees))

split_count = [0] * 20          # cuantas veces aparece x[i] como variable de corte
depth_weight = [0.0] * 20       # peso 1/2^profundidad (mas cerca de la raiz = mas peso)

def walk(node, depth):
    if node[0] != 'if':
        return
    _, cond, then_b, else_b = node
    m = re.match(r'x\[(\d+)\]', cond)
    idx = int(m.group(1))
    split_count[idx] += 1
    depth_weight[idx] += 1.0 / (2 ** depth)
    for s in then_b:
        walk(s, depth + 1)
    if else_b:
        for s in else_b:
            walk(s, depth + 1)

for t in trees:
    walk(t, 0)

names = ["ndvi", "ndwi", "nddi", "lst", "vci", "dsi_score", "cur_class", "spi1", "spi3", "spi6",
         "cdd", "et0", "nddi_t", "ndvi_t", "vci_t", "lst_t", "q_row", "q_col", "month_sin", "month_cos"]

result = sorted(zip(names, split_count, depth_weight), key=lambda r: -r[2])
for r in result:
    print(f"{r[0]:10s}  cortes={r[1]:3d}  peso_prof={r[2]:.3f}")

json.dump(
    {"names": [r[0] for r in result], "split_count": [r[1] for r in result], "depth_weight": [round(r[2],4) for r in result]},
    open(r"C:\Users\Dante\AppData\Local\Temp\claude\C--Users-Dante-Documents-IAC-Sequias\a83e4011-80f0-49da-b429-a656624fcf52\scratchpad\feature_importance.json", "w"),
    indent=2,
)
