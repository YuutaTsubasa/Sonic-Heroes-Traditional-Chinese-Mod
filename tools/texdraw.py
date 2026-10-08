"""Draw Chinese text into a texture from a spec (text/tex/<id>.json).

Spec:
{"erase":  [{"rect": [x0, y0, x1, y1], "mode": "clear" | "interp" | "interpv" | "fill", "color": "#rrggbbaa"}],
 "blocks": [{"rect": [x0, y0, x1, y1], "zh": "文字",
             "size": 20,                 # px; omitted = fit the rect height
             "weight": 900,              # Noto Sans TC weight 100-900
             "color": "#ffffff" | ["#top", "#bottom"],   # solid or vertical gradient
             "stroke": "#000000", "stroke_w": 2,
             "shadow": {"dx": 1, "dy": 1, "color": "#00000080"},
             "align": "center" | "left" | "right",
             "italic": 0.2,              # horizontal shear
             "squeeze": true,            # compress horizontally to fit the rect (default true)
             "spacing": 0,               # extra px between characters
             "rotate": 90 | 180 | 270}],
 "keep": true}                           # texture has no Japanese: leave it
Rects are [x0, y0, x1, y1), pixels of the base level. Text never draws outside its rect.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

NOTO = 'C:/Windows/Fonts/NotoSansTC-VF.ttf'
SS = 4


def color(c):
    c = c.lstrip('#')
    if len(c) == 6:
        c += 'ff'
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4, 6))


def erase(img, e):
    x0, y0, x1, y1 = e['rect']
    a = img.astype(np.float64)
    mode = e.get('mode', 'interp')
    if mode == 'clear':
        img[y0:y1, x0:x1] = 0
    elif mode == 'fill':
        img[y0:y1, x0:x1] = color(e['color'])
    elif mode == 'interp':
        L = a[y0:y1, max(x0 - 1, 0)]
        R = a[y0:y1, min(x1, img.shape[1] - 1)]
        for x in range(x0, x1):
            t = (x - x0 + 1) / (x1 - x0 + 1)
            img[y0:y1, x] = np.round(L * (1 - t) + R * t)
    elif mode == 'plates':
        # union of rounded rectangles: {"rects": [[x0,y0,x1,y1],...], "radius", "color", "border", "border_color"}
        h, w = img.shape[:2]
        r = e.get('radius', 8) * SS
        bd = e.get('border', 0) * SS
        outer = Image.new('L', (w * SS, h * SS), 0)
        inner = Image.new('L', (w * SS, h * SS), 0)
        do, di = ImageDraw.Draw(outer), ImageDraw.Draw(inner)
        for q in e['rects']:
            q = [v * SS for v in q]
            do.rounded_rectangle([q[0] - bd, q[1] - bd, q[2] + bd, q[3] + bd], r + bd, fill=255)
            di.rounded_rectangle(q, r, fill=255)
        outer = np.array(outer.resize((w, h), Image.LANCZOS), float)[..., None] / 255
        inner = np.array(inner.resize((w, h), Image.LANCZOS), float)[..., None] / 255
        bc = np.array(color(e.get('border_color', '#ffffff')), float)
        fc = np.array(color(e.get('color', '#000000')), float)
        a = a * (1 - outer) + bc * outer
        a = a * (1 - inner) + fc * inner
        img[...] = np.round(a)
    elif mode == 'interpv':
        T = a[max(y0 - 1, 0), x0:x1]
        B = a[min(y1, img.shape[0] - 1), x0:x1]
        for y in range(y0, y1):
            t = (y - y0 + 1) / (y1 - y0 + 1)
            img[y, x0:x1] = np.round(T * (1 - t) + B * t)
    return img


def _text_layer(b, w, h):
    """Render block text as an RGBA image of size (w, h) (supersampled then reduced)."""
    zh = b['zh']
    rot = b.get('rotate', 0)
    if rot in (90, 270):
        w, h = h, w
    W, H = w * SS, h * SS
    size = int(b.get('size', h * 0.86) * SS)
    f = ImageFont.truetype(NOTO, size)
    f.set_variation_by_axes([b.get('weight', 900)])
    sw = int(round(b.get('stroke_w', 0) * SS))
    sp = int(b.get('spacing', 0) * SS)
    # measure
    widths = [f.getbbox(ch, stroke_width=sw)[2] - f.getbbox(ch, stroke_width=sw)[0] for ch in zh]
    adv = [f.getlength(ch) for ch in zh]
    tw = int(sum(adv) + sp * (len(zh) - 1) + 2 * sw)
    asc, desc = f.getmetrics()
    th = asc + desc + 2 * sw
    canvas_w = max(tw, 1)
    mask = Image.new('L', (canvas_w, th), 0)
    smask = Image.new('L', (canvas_w, th), 0)
    d = ImageDraw.Draw(mask)
    ds = ImageDraw.Draw(smask)
    x = sw
    for ch, a in zip(zh, adv):
        if sw:
            ds.text((x, sw), ch, font=f, fill=255, stroke_width=sw, stroke_fill=255)
        d.text((x, sw), ch, font=f, fill=255)
        x += a + sp
    # crop to ink vertically
    bbox = (smask if sw else mask).getbbox() or (0, 0, 1, 1)
    mask = mask.crop((0, bbox[1], canvas_w, bbox[3]))
    smask = smask.crop((0, bbox[1], canvas_w, bbox[3]))
    ink_h = bbox[3] - bbox[1]
    # scale to fit
    scale_y = min(1.0, H / max(ink_h, 1))
    new_w = canvas_w * scale_y
    if new_w > W and b.get('squeeze', True):
        sx = W / new_w
    else:
        sx = 1.0
    tw2 = max(1, int(canvas_w * scale_y * sx)); th2 = max(1, int(ink_h * scale_y))
    mask = mask.resize((tw2, th2), Image.LANCZOS)
    smask = smask.resize((tw2, th2), Image.LANCZOS)
    italic = b.get('italic', 0)
    if italic:
        extra = int(abs(italic) * th2)
        aff = (1, italic, -extra if italic > 0 else 0, 0, 1, 0)
        mask = mask.transform((tw2 + extra, th2), Image.AFFINE, aff, Image.BICUBIC)
        smask = smask.transform((tw2 + extra, th2), Image.AFFINE, aff, Image.BICUBIC)
        tw2 += extra
    # fill colours
    col = b.get('color', '#ffffff')
    if isinstance(col, list):
        c0, c1 = np.array(color(col[0]), float), np.array(color(col[1]), float)
        t = np.linspace(0, 1, th2)[:, None, None]
        fill = (c0 * (1 - t) + c1 * t).repeat(tw2, 1)
    else:
        fill = np.tile(np.array(color(col), float), (th2, tw2, 1))
    layer = np.zeros((th2, tw2, 4), float)
    m = np.array(mask, float)[..., None] / 255
    if sw:
        sm = np.array(smask, float)[..., None] / 255
        sc = np.array(color(b.get('stroke', '#000000')), float)
        layer = sc * sm
        layer[..., 3:] = sm * sc[3] / 255 * 255
        rgb = fill[..., :3] * m + layer[..., :3] * (1 - m)
        alpha = np.maximum(m * fill[..., 3:], sm * sc[3])
        layer = np.concatenate([rgb, alpha], -1)
    else:
        layer = np.concatenate([fill[..., :3], m * fill[..., 3:]], -1)
    out = np.zeros((H, W, 4), float)
    al = b.get('align', 'center')
    ox = 0 if al == 'left' else (W - tw2 if al == 'right' else (W - tw2) // 2)
    oy = (H - th2) // 2
    ox = max(ox, 0) if al != 'right' else ox
    xs, ys = max(ox, 0), max(oy, 0)
    xe, ye = min(ox + tw2, W), min(oy + th2, H)
    out[ys:ye, xs:xe] = layer[ys - oy:ye - oy, xs - ox:xe - ox]
    sh = b.get('shadow')
    im = Image.fromarray(out.clip(0, 255).astype(np.uint8), 'RGBA')
    if sh:
        sc = color(sh.get('color', '#00000080'))
        a = np.array(im)[..., 3].astype(float) / 255
        shadow = np.zeros((H, W, 4), float)
        shadow[..., :3] = sc[:3]
        shadow[..., 3] = a * sc[3]
        shadow = np.roll(shadow, (int(sh.get('dy', 1) * SS), int(sh.get('dx', 1) * SS)), (0, 1))
        base = Image.fromarray(shadow.astype(np.uint8), 'RGBA')
        base.alpha_composite(im)
        im = base
    im = im.resize((w, h), Image.LANCZOS)
    if rot:
        im = im.rotate(rot, expand=True)
    return im


def render(rgba, spec):
    """rgba: (h, w, 4) uint8 -> new (h, w, 4) uint8."""
    img = rgba.copy()
    for e in spec.get('erase', []):
        img = erase(img, e)
    base = Image.fromarray(img, 'RGBA')
    for b in spec.get('blocks', []):
        x0, y0, x1, y1 = b['rect']
        layer = _text_layer(b, x1 - x0, y1 - y0)
        region = base.crop((x0, y0, x1, y1))
        region.alpha_composite(layer)
        base.paste(region, (x0, y0))
    return np.array(base)
