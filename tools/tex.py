"""Texture inventory for the Japanese-text textures.

  python tools/tex.py scan            index every texture in the candidate archives -> work/tex/index.json + PNGs
  python tools/tex.py sheet <k>/<n>   contact sheet k of n of not-yet-marked textures -> work/tex/sheet_k.png
  python tools/tex.py status          how many textures are marked (text/tex/<id>.json, keep or spec)
  python tools/tex.py show <id>       zoomed original with a 10 px grid -> work/tex/show_<id>.png
  python tools/tex.py preview <id>    original above, spec result below (zoomed) -> work/tex/prev_<id>.png

Texture id = first 10 hex digits of sha1(pixel data + palette). One spec applies to every copy.
"""
import glob
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import gx  # noqa: E402
import one  # noqa: E402
import txd  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DISC = os.path.join(ROOT, 'work', 'disc', 'files')
WORK = os.path.join(ROOT, 'work', 'tex')
SPECS = os.path.join(ROOT, 'text', 'tex')


def candidates():
    """Archives the Japanese game shows: language-neutral or J variants only."""
    out = sorted(glob.glob(os.path.join(DISC, 'advertise', 'J', '*.one')))
    out += sorted(glob.glob(os.path.join(DISC, 'advertise', '*.one')))
    for p in sorted(glob.glob(os.path.join(DISC, 'stgtitle', '*.one'))):
        b = os.path.basename(p)[:-4]
        if not b.endswith('E'):  # stgNNtitle_dispE = English
            out.append(p)
    for p in sorted(glob.glob(os.path.join(DISC, '*.one'))):
        b = os.path.basename(p)[:-4]
        if 'disp' in b and b[-1] not in 'EFGIKS':
            out.append(p)
    return out


def texture_rgba(t):
    return gx.decode(t.gx, t.data, t.w, t.h, t.palette, t.tlut)[0]


def tex_id(t):
    return hashlib.sha1(t.data[:gx.level_size(t.gx, t.w, t.h)] + t.palette).hexdigest()[:10]


def scan():
    os.makedirs(WORK, exist_ok=True)
    index = {}
    for p in candidates():
        rel = os.path.relpath(p, DISC).replace('\\', '/')
        for name, data in one.files(open(p, 'rb').read()):
            if not name.upper().endswith('.TXD'):
                continue
            for t in txd.parse(data):
                i = tex_id(t)
                e = index.setdefault(i, {'w': t.w, 'h': t.h, 'gx': t.gx, 'levels': t.levels, 'name': t.name, 'locs': []})
                e['locs'].append(f'{rel}:{name}:{t.name}')
                png = os.path.join(WORK, i + '.png')
                if not os.path.exists(png):
                    Image.fromarray(texture_rgba(t)).save(png)
    json.dump(index, open(os.path.join(WORK, 'index.json'), 'w'), indent=1)
    print(len(index), 'unique textures')


def marked(i):
    return os.path.exists(os.path.join(SPECS, i + '.json'))


def sheet(arg, only=None):
    """only: JSON list of ids to restrict to (e.g. work/tex/lang_ids.json)."""
    k, n = map(int, arg.split('/'))
    index = json.load(open(os.path.join(WORK, 'index.json')))
    ids = sorted(i for i in index if not marked(i))
    if only:
        keep = set(json.load(open(only)))
        ids = [i for i in ids if i in keep]
    ids = ids[(k - 1) * len(ids) // n:k * len(ids) // n]
    cell = 160
    cols = 8
    rows = (len(ids) + cols - 1) // cols
    im = Image.new('RGB', (cols * cell, rows * (cell + 14)), (60, 60, 60))
    d = ImageDraw.Draw(im)
    for j, i in enumerate(ids):
        t = Image.open(os.path.join(WORK, i + '.png')).convert('RGBA')
        t.thumbnail((cell - 4, cell - 4))
        bg = Image.new('RGBA', t.size, (60, 60, 60, 255))
        bg.alpha_composite(t)
        x, y = (j % cols) * cell, (j // cols) * (cell + 14)
        im.paste(bg.convert('RGB'), (x + 2, y + 2))
        d.text((x + 2, y + cell), f'{i} {index[i]["w"]}x{index[i]["h"]}', fill=(255, 255, 0))
    out = os.path.join(WORK, f'sheet_{k}.png')
    im.save(out)
    print(out, len(ids))


def _zoom(rgba, z, grid=False):
    h, w = rgba.shape[:2]
    bg = np.zeros((h, w, 4), np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    chk = ((yy // 4 + xx // 4) % 2).astype(bool)
    bg[...] = (90, 90, 90, 255); bg[chk] = (130, 130, 130, 255)
    im = Image.fromarray(bg, 'RGBA'); im.alpha_composite(Image.fromarray(rgba, 'RGBA'))
    im = im.convert('RGB').resize((w * z, h * z), Image.NEAREST)
    if grid:
        d = ImageDraw.Draw(im)
        for x in range(0, w, 10):
            d.line([(x * z, 0), (x * z, h * z)], fill=(255, 0, 255) if x % 50 == 0 else (0, 160, 160))
        for y in range(0, h, 10):
            d.line([(0, y * z), (w * z, y * z)], fill=(255, 0, 255) if y % 50 == 0 else (0, 160, 160))
    return im


def zoom_for(w):
    return max(1, min(6, 1200 // max(w, 1)))


def show(i):
    rgba = np.array(Image.open(os.path.join(WORK, i + '.png')).convert('RGBA'))
    out = os.path.join(WORK, f'show_{i}.png')
    _zoom(rgba, zoom_for(rgba.shape[1]), True).save(out)
    print(out, rgba.shape[1], 'x', rgba.shape[0], 'zoom', zoom_for(rgba.shape[1]))


def preview(i):
    import texdraw
    rgba = np.array(Image.open(os.path.join(WORK, i + '.png')).convert('RGBA'))
    spec = json.load(open(os.path.join(SPECS, i + '.json'), encoding='utf-8'))
    new = texdraw.render(rgba, spec)
    z = zoom_for(rgba.shape[1])
    a, b = _zoom(rgba, z), _zoom(new, z)
    im = Image.new('RGB', (a.width, a.height * 2 + 6), (255, 0, 0))
    im.paste(a, (0, 0)); im.paste(b, (0, a.height + 6))
    out = os.path.join(WORK, f'prev_{i}.png')
    im.save(out)
    print(out)


def status():
    index = json.load(open(os.path.join(WORK, 'index.json')))
    keep = spec = 0
    for i in index:
        p = os.path.join(SPECS, i + '.json')
        if os.path.exists(p):
            if json.load(open(p, encoding='utf-8')).get('keep'):
                keep += 1
            else:
                spec += 1
    print(f'textures {len(index)}  keep {keep}  spec {spec}  unmarked {len(index) - keep - spec}')


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd in ('show', 'preview'):
        {'show': show, 'preview': preview}[cmd](sys.argv[2])
    else:
        {'scan': scan, 'status': status}.get(cmd, lambda: sheet(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))()


def readback(rel, out_png):
    """Decode every texture of a built archive (work/build/files/<rel>) into one sheet."""
    B = os.path.join(ROOT, 'work', 'build', 'files')
    ims = []
    for name, data in one.files(open(os.path.join(B, rel), 'rb').read()):
        if name.upper().endswith('.TXD'):
            for t in txd.parse(data):
                ims.append(texture_rgba(t))
    w = max(i.shape[1] for i in ims)
    sheet = Image.new('RGBA', (w, sum(i.shape[0] + 2 for i in ims)), (70, 70, 70, 255))
    y = 0
    for i in ims:
        sheet.alpha_composite(Image.fromarray(i, 'RGBA'), (0, y)); y += i.shape[0] + 2
    sheet.save(out_png)
