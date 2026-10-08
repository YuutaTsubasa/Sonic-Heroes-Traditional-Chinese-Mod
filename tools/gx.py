"""GameCube GX texture codecs: decode to RGBA numpy arrays and encode back.

Formats used by Sonic Heroes TXDs: C4 (8), C8 (9) with an RGB565 / RGB5A3 / IA8 palette (tlut 1 / 2 / 0),
CMPR (14, GC-ordered DXT1), RGB5A3 (5), RGB565 (4). Mip levels follow the base level.
"""
import numpy as np
from PIL import Image

BLOCK = {0: (8, 8), 1: (8, 4), 2: (8, 4), 3: (4, 4), 4: (4, 4), 5: (4, 4), 6: (4, 4), 8: (8, 8), 9: (8, 4), 14: (8, 8)}
BPP = {0: 4, 1: 8, 2: 8, 3: 16, 4: 16, 5: 16, 6: 32, 8: 4, 9: 8, 14: 4}


def level_size(fmt, w, h):
    bw, bh = BLOCK[fmt]
    W = (w + bw - 1) // bw * bw
    H = (h + bh - 1) // bh * bh
    return W * H * BPP[fmt] // 8


# ------------------------------------------------------------ 16-bit colours
def rgb565_to_rgba(v):
    v = v.astype(np.uint32)
    r = (v >> 11) & 31; g = (v >> 5) & 63; b = v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), np.full_like(r, 255)], -1).astype(np.uint8)


def rgb5a3_to_rgba(v):
    v = v.astype(np.uint32)
    op = (v & 0x8000) != 0
    r5 = (v >> 10) & 31; g5 = (v >> 5) & 31; b5 = v & 31
    r4 = (v >> 8) & 15; g4 = (v >> 4) & 15; b4 = v & 15; a3 = (v >> 12) & 7
    r = np.where(op, (r5 << 3) | (r5 >> 2), r4 * 17)
    g = np.where(op, (g5 << 3) | (g5 >> 2), g4 * 17)
    b = np.where(op, (b5 << 3) | (b5 >> 2), b4 * 17)
    a = np.where(op, 255, (a3 << 5) | (a3 << 2) | (a3 >> 1))
    return np.stack([r, g, b, a], -1).astype(np.uint8)


def ia8_to_rgba(v):
    v = v.astype(np.uint32)
    i = v & 255; a = v >> 8
    return np.stack([i, i, i, a], -1).astype(np.uint8)


def rgba_to_rgb565(c):
    c = c.astype(np.uint32)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def rgba_to_rgb5a3(c):
    c = c.astype(np.uint32)
    op = c[..., 3] >= 0xE0
    v1 = 0x8000 | ((c[..., 0] >> 3) << 10) | ((c[..., 1] >> 3) << 5) | (c[..., 2] >> 3)
    v0 = ((c[..., 3] >> 5) << 12) | ((c[..., 0] >> 4) << 8) | ((c[..., 1] >> 4) << 4) | (c[..., 2] >> 4)
    return np.where(op, v1, v0)


PAL_DEC = {0: ia8_to_rgba, 1: rgb565_to_rgba, 2: rgb5a3_to_rgba}


def palette_rgba(pal, tlut):
    v = np.frombuffer(pal, '>u2')
    return PAL_DEC[tlut](v)


# ------------------------------------------------------------ tiling
def untile(blocks, w, h, bw, bh):
    """blocks: array (nblocks, bh, bw, ...) in GX order -> image (H, W, ...)."""
    W = (w + bw - 1) // bw * bw; H = (h + bh - 1) // bh * bh
    nx = W // bw; ny = H // bh
    b = blocks.reshape(ny, nx, bh, bw, *blocks.shape[3:])
    img = b.swapaxes(1, 2).reshape(H, W, *blocks.shape[3:])
    return img[:h, :w]


def tile(img, bw, bh):
    h, w = img.shape[:2]
    W = (w + bw - 1) // bw * bw; H = (h + bh - 1) // bh * bh
    pad = np.zeros((H, W, *img.shape[2:]), img.dtype)
    pad[:h, :w] = img
    return pad.reshape(H // bh, bh, W // bw, bw, *img.shape[2:]).swapaxes(1, 2).reshape(-1, bh, bw, *img.shape[2:])


# ------------------------------------------------------------ decode
def decode(fmt, data, w, h, pal=None, tlut=1):
    if fmt in (8, 9):
        if fmt == 8:
            raw = np.frombuffer(data[:level_size(8, w, h)], np.uint8)
            idx = np.stack([raw >> 4, raw & 15], -1).reshape(-1, 8, 8)
        else:
            idx = np.frombuffer(data[:level_size(9, w, h)], np.uint8).reshape(-1, 4, 8)
        bw, bh = BLOCK[fmt]
        ind = untile(idx, w, h, bw, bh)
        return palette_rgba(pal, tlut)[ind], ind
    if fmt in (4, 5):
        v = np.frombuffer(data[:level_size(fmt, w, h)], '>u2').reshape(-1, 4, 4)
        img = untile(v, w, h, 4, 4)
        return (rgb565_to_rgba if fmt == 4 else rgb5a3_to_rgba)(img), None
    if fmt == 14:
        return cmpr_decode(data, w, h), None
    raise NotImplementedError(fmt)


def dxt1_block(b):
    c0 = int.from_bytes(b[0:2], 'big'); c1 = int.from_bytes(b[2:4], 'big')
    cols = rgb565_to_rgba(np.array([c0, c1], np.uint16)).astype(np.int32)
    if c0 > c1:
        c2 = (2 * cols[0] + cols[1]) // 3; c3 = (cols[0] + 2 * cols[1]) // 3
    else:
        c2 = (cols[0] + cols[1]) // 2; c3 = np.array([0, 0, 0, 0])
        c2[3] = 255
    pal = np.stack([cols[0], cols[1], c2, c3]).astype(np.uint8)
    idx = []
    for y in range(4):
        byte = b[4 + y]
        idx.append([(byte >> (6 - 2 * x)) & 3 for x in range(4)])
    return pal[np.array(idx)]


def cmpr_decode(data, w, h):
    W = (w + 7) // 8 * 8; H = (h + 7) // 8 * 8
    img = np.zeros((H, W, 4), np.uint8)
    o = 0
    for by in range(0, H, 8):
        for bx in range(0, W, 8):
            for sy in (0, 4):
                for sx in (0, 4):
                    img[by + sy:by + sy + 4, bx + sx:bx + sx + 4] = dxt1_block(data[o:o + 8]); o += 8
    return img[:h, :w]


# ------------------------------------------------------------ encode
def nearest_palette(img, pal_rgba, allowed=None):
    """Map RGBA pixels to palette indices (optionally restricted to `allowed` indices)."""
    cand = np.arange(len(pal_rgba)) if allowed is None else np.array(sorted(allowed))
    p = pal_rgba[cand].astype(np.int32)
    flat = img.reshape(-1, 4).astype(np.int32)
    out = np.empty(len(flat), np.int64)
    for s in range(0, len(flat), 65536):
        d = flat[s:s + 65536, None, :] - p[None, :, :]
        w = np.array([2, 4, 3, 3])  # perceptual-ish weights, alpha matters
        out[s:s + 65536] = cand[np.argmin((d * d * w).sum(-1), 1)]
    return out.reshape(img.shape[:2])


def encode_indexed(fmt, ind):
    bw, bh = BLOCK[fmt]
    t = tile(ind.astype(np.uint8), bw, bh)
    if fmt == 9:
        return t.tobytes()
    t = t.reshape(-1, 2)
    return ((t[:, 0] << 4) | t[:, 1]).astype(np.uint8).tobytes()


def encode_16(fmt, img):
    v = (rgba_to_rgb565 if fmt == 4 else rgba_to_rgb5a3)(img).astype('>u2')
    return tile(v, 4, 4).tobytes()


def _dxt1_encode_block(px):
    """px: (16, 4) uint8. Principal-axis endpoints refined by least squares; 1-bit alpha via 3-colour mode."""
    a = px[:, 3]
    trans = a < 128
    rgb = px[:, :3].astype(np.float64)
    op = rgb[~trans]
    if len(op) == 0:
        return bytes([0, 0, 0, 0, 255, 255, 255, 255])
    mean = op.mean(0)
    if len(op) > 1:
        cov = np.cov((op - mean).T)
        axis = np.linalg.eigh(cov)[1][:, -1] if np.ptp(op, 0).max() > 0 else np.array([1., 1., 1.])
    else:
        axis = np.array([1., 1., 1.])
    t = (op - mean) @ axis
    e0 = mean + axis * t.max(); e1 = mean + axis * t.min()
    use3 = trans.any()
    best = None
    for _ in range(2):
        c = np.clip(np.stack([e0, e1]), 0, 255)
        q = rgba_to_rgb565(np.concatenate([c, np.full((2, 1), 255)], 1).astype(np.uint8)).astype(np.int64)
        c0, c1 = int(q[0]), int(q[1])
        if use3:
            if c0 > c1:
                c0, c1 = c1, c0
        else:
            if c0 < c1:
                c0, c1 = c1, c0
            if c0 == c1:
                if c0 > 0:
                    c1 = c0 - 1
                else:
                    c0 = 1
        cols = rgb565_to_rgba(np.array([c0, c1], np.uint16)).astype(np.float64)[:, :3]
        if c0 > c1:
            pal = np.stack([cols[0], cols[1], (2 * cols[0] + cols[1]) / 3, (cols[0] + 2 * cols[1]) / 3])
            n = 4
        else:
            pal = np.stack([cols[0], cols[1], (cols[0] + cols[1]) / 2])
            n = 3
        d = ((rgb[:, None, :] - pal[None, :n, :]) ** 2).sum(-1)
        idx = d.argmin(1)
        if use3:
            idx[trans] = 3
        err = d[np.arange(16), np.minimum(idx, n - 1)][~trans].sum()
        if best is None or err < best[0]:
            best = (err, c0, c1, idx.copy())
        # least-squares refit of endpoints
        wts = {0: 1., 1: 0., 2: 2 / 3, 3: 1 / 3} if n == 4 else {0: 1., 1: 0., 2: .5}
        m = ~trans
        al = np.array([wts.get(int(i), 0.) for i in idx])[m]
        A = np.stack([al, 1 - al], 1)
        if np.linalg.matrix_rank(A) < 2:
            break
        sol = np.linalg.lstsq(A, rgb[m], rcond=None)[0]
        e0, e1 = sol[0], sol[1]
    _, c0, c1, idx = best
    out = bytearray(int(c0).to_bytes(2, 'big') + int(c1).to_bytes(2, 'big'))
    for y in range(4):
        b = 0
        for x in range(4):
            b |= int(idx[y * 4 + x]) << (6 - 2 * x)
        out.append(b)
    return bytes(out)


def cmpr_encode(img):
    h, w = img.shape[:2]
    W = (w + 7) // 8 * 8; H = (h + 7) // 8 * 8
    pad = np.zeros((H, W, 4), np.uint8); pad[:h, :w] = img
    out = bytearray()
    for by in range(0, H, 8):
        for bx in range(0, W, 8):
            for sy in (0, 4):
                for sx in (0, 4):
                    out += _dxt1_encode_block(pad[by + sy:by + sy + 4, bx + sx:bx + sx + 4].reshape(16, 4))
    return bytes(out)


# ------------------------------------------------------------ re-encode an edited texture
def encode_like(fmt, orig_data, w, h, orig_rgba, new_rgba, pal=None, tlut=1):
    """Encode new_rgba in the original format, keeping the original bytes wherever pixels did not change
    (so padding and untouched areas stay bit-exact). Indexed formats keep the palette and map changed
    pixels to the nearest palette entry. Returns (bytes, max_error)."""
    n = level_size(fmt, w, h)
    changed = np.any(orig_rgba != new_rgba, -1)
    bw, bh = BLOCK[fmt]
    W = (w + bw - 1) // bw * bw; H = (h + bh - 1) // bh * bh
    err = 0
    if fmt in (8, 9):
        prgba = palette_rgba(pal, tlut)
        _, ind = decode(fmt, orig_data, w, h, pal, tlut)
        full = untile(_raw_indices(fmt, orig_data, w, h), W, H, bw, bh).copy()
        if changed.any():
            near = nearest_palette(new_rgba, prgba)
            full[:h, :w] = np.where(changed, near, full[:h, :w])
            err = int(np.abs(prgba[near][changed].astype(int) - new_rgba[changed].astype(int)).max())
        return encode_indexed(fmt, full), err
    if fmt in (4, 5):
        words = untile(np.frombuffer(orig_data[:n], '>u2').reshape(-1, 4, 4), W, H, 4, 4).copy()
        neww = (rgba_to_rgb565 if fmt == 4 else rgba_to_rgb5a3)(new_rgba)
        words[:h, :w] = np.where(changed, neww, words[:h, :w])
        return tile(words.astype('>u2'), 4, 4).tobytes(), 0
    if fmt == 14:
        out = bytearray(orig_data[:n])
        pad = np.zeros((H, W, 4), np.uint8); pad[:h, :w] = new_rgba
        ch = np.zeros((H, W), bool); ch[:h, :w] = changed
        o = 0
        for by in range(0, H, 8):
            for bx in range(0, W, 8):
                for sy in (0, 4):
                    for sx in (0, 4):
                        y, x = by + sy, bx + sx
                        if ch[y:y + 4, x:x + 4].any():
                            out[o:o + 8] = _dxt1_encode_block(pad[y:y + 4, x:x + 4].reshape(16, 4))
                        o += 8
        return bytes(out), 0
    raise NotImplementedError(fmt)


def _raw_indices(fmt, data, w, h):
    if fmt == 8:
        raw = np.frombuffer(data[:level_size(8, w, h)], np.uint8)
        return np.stack([raw >> 4, raw & 15], -1).reshape(-1, 8, 8)
    return np.frombuffer(data[:level_size(9, w, h)], np.uint8).reshape(-1, 4, 8)


def encode_full(fmt, rgba, pal=None, tlut=1):
    """Encode a whole level from scratch (used for regenerated mip levels)."""
    if fmt in (8, 9):
        return encode_indexed(fmt, nearest_palette(rgba, palette_rgba(pal, tlut)))
    if fmt in (4, 5):
        return encode_16(fmt, rgba)
    if fmt == 14:
        return cmpr_encode(rgba)
    raise NotImplementedError(fmt)


def requantize(fmt, rgba, tlut):
    """New palette + indices for an indexed texture whose colours changed. Returns (palette_bytes, indices)."""
    n = 16 if fmt == 8 else 256
    im = Image.fromarray(rgba, 'RGBA')
    if tlut == 1:
        q = im.convert('RGB').quantize(n, method=Image.MEDIANCUT)
        pal = np.array(q.getpalette()[:3 * n] + [0] * max(0, 3 * n - len(q.getpalette())), np.uint8).reshape(n, 3)
        pal = np.concatenate([pal, np.full((n, 1), 255, np.uint8)], 1)
        words = rgba_to_rgb565(pal)
    else:
        q = im.quantize(n, method=Image.FASTOCTREE)
        flat = q.getpalette(rawmode='RGBA')
        pal = np.array(flat[:4 * n] + [0] * max(0, 4 * n - len(flat)), np.uint8).reshape(n, 4)
        words = rgba_to_rgb5a3(pal) if tlut == 2 else ((pal[..., 3].astype(np.uint32) << 8) | pal[..., 0])
    ind = np.array(q)
    return words.astype('>u2').tobytes(), ind


def encode_extend_palette(fmt, orig_data, w, h, orig_rgba, new_rgba, pal, tlut, max_err=24):
    """Keep every palette entry still used by unchanged pixels; put the colours of changed pixels into the
    free slots (median cut over the changed pixels only). Returns (palette_bytes, data, max_error) or None."""
    n = 16 if fmt == 8 else 256
    bw, bh = BLOCK[fmt]
    W = (w + bw - 1) // bw * bw; H = (h + bh - 1) // bh * bh
    full = untile(_raw_indices(fmt, orig_data, w, h), W, H, bw, bh).copy()
    changed = np.any(orig_rgba != new_rgba, -1)
    keep_mask = np.ones((H, W), bool); keep_mask[:h, :w] = ~changed
    used = set(np.unique(full[keep_mask]).tolist())
    free = [i for i in range(n) if i not in used]
    prgba = palette_rgba(pal, tlut).copy()
    cpx = new_rgba[changed]
    if len(cpx) == 0:
        return pal, encode_indexed(fmt, full), 0
    # existing colours may already match well
    near = nearest_palette(cpx[None], prgba[sorted(used)] if used else prgba)[0]
    base_idx = np.array(sorted(used))[near] if used else near
    err0 = np.abs(prgba[base_idx].astype(int) - cpx.astype(int)).max(1)
    need = cpx[err0 > max_err]
    if len(need) and free:
        k = min(len(free), len(np.unique(need.view('u4'))))
        q = Image.fromarray(need.reshape(1, -1, 4), 'RGBA').quantize(k, method=Image.FASTOCTREE)
        flat = q.getpalette(rawmode='RGBA')[:4 * k]
        cols = np.array(flat + [0] * (4 * k - len(flat)), np.uint8).reshape(k, 4)
        for slot, c in zip(free, cols):
            prgba[slot] = c
    elif len(need):
        return None
    cand = sorted(used) + free[:len(free)]
    idx = nearest_palette(cpx[None], prgba[cand])[0]
    newi = np.array(cand)[idx]
    if tlut == 1:
        words = rgba_to_rgb565(prgba)
    elif tlut == 2:
        words = rgba_to_rgb5a3(prgba)
    else:
        words = (prgba[..., 3].astype(np.uint32) << 8) | prgba[..., 0]
    newpal = words.astype('>u2').tobytes()
    # unchanged entries must keep their exact original words
    newpal = b''.join(pal[2 * i:2 * i + 2] if i in used else newpal[2 * i:2 * i + 2] for i in range(n))
    sub = full[:h, :w]
    sub[changed] = newi
    full[:h, :w] = sub
    data = encode_indexed(fmt, full)
    back, _ = decode(fmt, data, w, h, newpal, tlut)
    err = int(np.abs(back[changed].astype(int) - new_rgba[changed].astype(int)).max())
    return newpal, data, err
