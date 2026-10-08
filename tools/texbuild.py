"""Apply text/tex/<id>.json specs to every copy of each texture and rebuild the .one archives.

build(write, report): write(rel_path, bytes) is build.py's writer. Mip levels after the base are
regenerated from the edited base by box downscaling.
"""
import json
import os

import numpy as np
from PIL import Image

import gx
import one
import prs
import texdraw
import txd
from tex import DISC, SPECS, WORK, tex_id


def load_specs():
    specs = {}
    if os.path.isdir(SPECS):
        for f in os.listdir(SPECS):
            if f.endswith('.json'):
                s = json.load(open(os.path.join(SPECS, f), encoding='utf-8'))
                if not s.get('keep'):
                    specs[f[:-5]] = s
    return specs


def patch_txd(data, specs, report):
    data = bytearray(data)
    changed = False
    for t in txd.parse(bytes(data)):
        i = tex_id(t)
        if i not in specs:
            continue
        orig, _ = gx.decode(t.gx, t.data, t.w, t.h, t.palette, t.tlut)
        new = texdraw.render(orig, specs[i])
        base, err = gx.encode_like(t.gx, t.data, t.w, t.h, orig, new, t.palette, t.tlut)
        pal = t.palette
        ext = gx.encode_extend_palette(t.gx, t.data, t.w, t.h, orig, new, t.palette, t.tlut)             if err > 24 and t.gx in (8, 9) else None
        if ext and ext[2] <= 40:
            pal, base, err = ext
            data[t.pal_off:t.pal_off + len(pal)] = pal
            report.setdefault('tex_extended', []).append(f'{i} max error {err}')
        elif err > 24 and t.gx in (8, 9):
            pal, ind = gx.requantize(t.gx, new, t.tlut)
            base = gx.encode_indexed(t.gx, ind)
            data[t.pal_off:t.pal_off + len(pal)] = pal
            back, _ = gx.decode(t.gx, base, t.w, t.h, pal, t.tlut)
            err = int(np.abs(back.astype(int) - new.astype(int)).max())
            report.setdefault('tex_requantized', []).append(f'{i} max error {err}')
        out = bytearray(base)
        w, h = t.w, t.h
        img = Image.fromarray(new, 'RGBA')
        for lv in range(1, t.levels):
            w, h = max(1, w // 2), max(1, h // 2)
            out += gx.encode_full(t.gx, np.array(img.resize((w, h), Image.BOX)), pal, t.tlut)
        if len(out) > t.size:
            raise ValueError(f'{i}: encoded {len(out)} > {t.size}')
        out += t.data[len(out):]
        data[t.data_off:t.data_off + t.size] = out
        changed = True
        report.setdefault('textures', {})[i] = report.get('textures', {}).get(i, 0) + 1
    return bytes(data), changed


def build(write, report):
    specs = load_specs()
    if not specs:
        return
    index = json.load(open(os.path.join(WORK, 'index.json')))
    archives = sorted({loc.split(':')[0] for i in specs for loc in index.get(i, {}).get('locs', [])})
    missing = [i for i in specs if i not in index]
    if missing:
        report.setdefault('errors', []).extend(f'texture spec without texture: {i}' for i in missing)
    for rel in archives:
        raw = open(os.path.join(DISC, rel), 'rb').read()
        ver, names, ents = one.parse(raw)
        new_ents = []
        any_change = False
        for name, comp in ents:
            if name.upper().endswith('.TXD'):
                data, ch = patch_txd(prs.decompress(comp), specs, report)
                if ch:
                    comp = prs.compress(data)
                    any_change = True
            new_ents.append((name, comp))
        if any_change:
            write(rel, one.build(ver, names, new_ents))
