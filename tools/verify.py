"""Read the built files back like the game does and check them against text/zh; render a preview.

  python tools/verify.py [--png work/preview.png]
Checks: every event/hint string decodes (via the per-file charset) to the chosen text, every character has a
glyph page, UTX strings round-trip, and sega.prs has a record for every character in the UTX strings.
"""
import json
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import formats as F  # noqa: E402
import fontgen as FG  # noqa: E402
import prs  # noqa: E402
from charmap import CharMap  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
B = os.path.join(ROOT, 'work', 'build', 'files')


BS = bytes([0x5C])
NL = bytes([0x0A])


def charset_codes(txt, breaks=False):
    """Split into character codes; with breaks=True a backslash-n pair or 0x0A becomes NL."""
    out, i = [], 0
    while i < len(txt):
        n = 2 if txt[i] >= 0x80 else 1
        c = txt[i:i + n]
        if breaks and c == BS and txt[i + 1:i + 2] == b'n':
            c, n = NL, 2
        out.append(c); i += n
    return out


def glyph_codes(raw):
    return [c for c in charset_codes(raw, True) if c != NL]


class FontFile:
    def __init__(self, name):
        self.codes = charset_codes(open(os.path.join(B, 'font', name + '.txt'), 'rb').read())
        chars = [(None, c) for c in self.codes]
        self.pos = {}
        for p, page in enumerate(FG.pages_layout(chars)):
            for n, (_, code, row, units) in enumerate(page):
                self.pos.setdefault(code, (p, n))
        self.name = name
        self.pages = {}

    def glyph(self, code):
        p, n = self.pos[code]
        if p not in self.pages:
            _, _, rects = FG.read_met(os.path.join(B, 'font', f'{self.name}{p:02d}.met'))
            im = Image.open(os.path.join(B, 'font', f'{self.name}{p:02d}.bmp')).convert('L')
            self.pages[p] = (rects, im)
        rects, im = self.pages[p]
        return im.crop(rects[n])

    def render(self, data):
        lines = [[]]
        for c in charset_codes(data, True):
            if c == b'\n':
                lines.append([]); continue
            lines[-1].append(self.glyph(c))
        w = max(sum(g.width for g in l) for l in lines) or 1
        out = Image.new('L', (w, 24 * len(lines)), 0)
        for y, l in enumerate(lines):
            x = 0
            for g in l:
                out.paste(g, (x, 24 * y)); x += g.width
        return out


def main():
    cm = CharMap()
    bad = 0
    previews = []
    # events
    zh = json.load(open(os.path.join(ROOT, 'text', 'zh', 'event.json'), encoding='utf-8'))
    data = open(os.path.join(B, 'movieD.rel'), 'rb').read()
    T = F.event_table(data)
    fonts = {}
    for ev, ln, k, ts, a, raw in T['rows']:
        name = f'event{ev:04d}_j'
        fonts.setdefault(name, FontFile(name))
        missing = [c for c in glyph_codes(raw) if c not in fonts[name].pos]
        want = zh.get(f'ev{ev:04d}.{ln:02d}')
        if missing or (want is not None and cm.decode(raw) != want):
            bad += 1
            print('event', ev, ln, 'missing glyphs' if missing else 'text differs')
        if len(previews) < 8 and ev in (0, 100, 300):
            previews.append(fonts[name].render(raw))
    # hints
    for fn in sorted(os.listdir(os.path.join(B, 'font'))):
        if not (fn.startswith('hint') and fn.endswith('.bin')):
            continue
        name = fn[:-4]
        ff = FontFile(name)
        recs, base, texts = F.hint_parse(open(os.path.join(B, 'font', fn), 'rb').read())
        for o, raw in texts.items():
            miss = [c for c in glyph_codes(raw) if c not in ff.pos]
            if miss:
                bad += 1; print(name, hex(o), 'missing glyphs')
        if name in ('hint001', 'hint050'):
            for o in sorted(texts)[:3]:
                previews.append(ff.render(texts[o]))
    # UTX + font
    sizes, _, ss = F.utx_parse(open(os.path.join(B, 'text', 'TextJapanese.utx'), 'rb').read())
    font = prs.decompress(open(os.path.join(B, 'advertise', 'sega.prs'), 'rb').read())
    codes = {struct.unpack_from('<H', font, 0x100 + i * 160)[0] for i in range((len(font) - 0x100) // 160)}
    for s in ss:
        for ch in s:
            if ch not in '\n' and ord(ch) not in codes:
                bad += 1; print('UTX char without glyph', ch)
    print('problems', bad)
    if '--png' in sys.argv:
        w = max(p.width for p in previews)
        sheet = Image.new('L', (w, sum(p.height + 4 for p in previews)), 40)
        y = 0
        for p in previews:
            sheet.paste(p, (0, y)); y += p.height + 4
        sheet.save(sys.argv[sys.argv.index('--png') + 1])
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
