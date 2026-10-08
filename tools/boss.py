"""Boss title cards (stgtitle/stgNNtitle_disp.one): EGG HAWK etc. are spelled from per-letter tiles, and a letter
that repeats is one shape drawn twice by the animation, so the letters cannot spell Chinese.

Instead, for each boss one letter that occurs only once and sits near the middle of the name ("anchor") gets:
  - its quad in the Maestro animation (BOSSSTGTITLE.ANM, shape chunk 0x1A1: 5 path nodes of
    (flags, x, y, nx, ny, length)) widened from 32x32 to 128x32 around the same centre;
  - its texture replaced by a new 256x64 RGB5A3 texture with the Chinese name;
and every other letter tile in that archive is made transparent. The Chinese name then flies in with the
anchor letter's animation. The small name bar (Japanese -> Chinese, done by a texture spec) is unchanged.
"""
import re
import struct

import numpy as np

import gx
import texdraw

BOSSES = {
    'stg20': ('egghwk', 'EGHAWK', 'H', '蛋頭鷹號'),
    'stg22': ('carnival', 'ROBTCANIVL', 'C', '機器人嘉年華'),
    'stg23': ('albatrs', 'EGALBTROS', 'B', '蛋頭信天翁號'),
    'stg25': ('storm', 'ROBTSM', 'S', '機器人風暴'),
    'stg26': ('emperor', 'EGMPRO', 'M', '蛋頭皇帝號'),
    'stg27': ('madness', 'METALDNS', 'L', '金屬瘋狂'),
    'stg28': ('overload', 'METALOVRD', 'V', '金屬霸王'),
}
NAME_W, NAME_H = 256, 64
STYLE = {'weight': 900, 'color': ['#a9b8d4', '#ffffff'], 'stroke': '#3a424e', 'stroke_w': 2.5,
         'shadow': {'dx': 2, 'dy': 2, 'color': '#101418d0'}, 'spacing': 4}

V = 0x1400FFFF
NAME = re.compile(rb'[a-z0-9]+_[0-9]{3}')


# ---------------------------------------------------------------- Maestro animation
def anm_shapes(a):
    """[(offset_of_0x1A1_chunk, texture_name)] in order."""
    out = []
    i = 0
    while True:
        i = a.find(struct.pack('<I', 0x1A1), i)
        if i < 0:
            break
        t, s, v = struct.unpack_from('<III', a, i)
        if v == V and s == 148:
            # the brush's texture name is the first 0x02 string chunk after this shape
            name = NAME.search(a, i).group().decode()
            out.append((i, name))
        i += 4
    return out


def widen(a, off, half_w):
    """Scale the quad of the shape chunk at `off` horizontally to +-half_w and recompute path lengths."""
    a = bytearray(a)
    body = off + 12
    nodes = []
    for k in range(5):
        p = body + 20 + k * 24  # 4 header words, then per node: flags, x, y, nx, ny, length
        x, y, nx, ny, ln = struct.unpack_from('<5f', a, p)
        nodes.append([p, x, y, nx, ny])
    for n in nodes:
        n[1] = half_w if n[1] > 0 else -half_w
    dist = 0.0
    for k, n in enumerate(nodes):
        if k:
            dist += abs(n[1] - nodes[k - 1][1]) + abs(n[2] - nodes[k - 1][2])
        struct.pack_into('<5f', a, n[0], n[1], n[2], n[3], n[4], dist)
    return bytes(a)


# ---------------------------------------------------------------- TXD rewrite with new sizes
def _chunks(d, o, end):
    while o < end:
        t, s, v = struct.unpack_from('<III', d, o)
        yield t, o, s
        o += 12 + s


def native_rgb5a3(old_struct, w, h, data):
    """Texture native struct body: header copied from the old one, format fields set to RGB5A3."""
    hdr = bytearray(old_struct[:88])
    fmt = struct.pack('>IHHBBBBI', 0x304, w, h, 16, 1, 5, 0xFF, 1)
    return bytes(hdr) + fmt + struct.pack('>I', len(data)) + data


def rebuild_txd(d, replace):
    """replace: {texture_name: (w, h, rgb5a3_bytes)}; other textures are copied unchanged."""
    t, o, s = next(_chunks(d, 0, len(d)))
    out = bytearray()
    for t2, o2, s2 in _chunks(d, o + 12, o + 12 + s):
        chunk = d[o2:o2 + 12 + s2]
        if t2 == 0x15:
            t3, o3, s3 = next(_chunks(d, o2 + 12, o2 + 12 + s2))
            st = d[o3 + 12:o3 + 12 + s3]
            name = st[24:56].split(bytes(1))[0].decode()
            if name in replace:
                w, h, data = replace[name]
                body = native_rgb5a3(st, w, h, data)
                rest = d[o3 + 12 + s3:o2 + 12 + s2]  # extension chunk(s)
                inner = struct.pack('<III', 1, len(body), V) + body + rest
                chunk = struct.pack('<III', 0x15, len(inner), V) + inner
        out += chunk
    return struct.pack('<III', 0x16, len(out), V) + bytes(out) + d[o + 12 + s:]


def name_texture(zh):
    img = np.zeros((NAME_H, NAME_W, 4), np.uint8)
    img = texdraw.render(img, {'blocks': [dict(rect=[4, 2, NAME_W - 4, NAME_H - 2], zh=zh, **STYLE)]})
    return img, gx.encode_16(5, img)


def patch(stage, anm, txd_bytes, txd_parse):
    prefix, letters, anchor, zh = BOSSES[stage]
    shapes = anm_shapes(anm)
    assert len(shapes) == len(letters) + 1, (stage, len(shapes))
    k = letters.index(anchor)
    off, tname = shapes[k]
    anm = widen(anm, off, 64.0)
    _, data = name_texture(zh)
    texs = {t.name: t for t in txd_parse(txd_bytes)}
    txd_bytes = bytearray(txd_bytes)
    for j, (_, n) in enumerate(shapes[:-1]):
        if j == k:
            continue
        t = texs[n]
        # transparent: every index 0, palette entry 0 fully transparent (RGB5A3, alpha bits 0)
        txd_bytes[t.data_off:t.data_off + t.size] = bytes(t.size)
        txd_bytes[t.pal_off:t.pal_off + 2] = bytes(2)
    txd_bytes = rebuild_txd(bytes(txd_bytes), {tname: (NAME_W, NAME_H, data)})
    return anm, txd_bytes
