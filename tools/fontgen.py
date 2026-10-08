"""Per-file bitmap fonts for event and hint subtitles (font/<name>.txt + <name>NN.bmp + <name>NN.met).

Layout rule, from the game's glyph lookup (main.dol 0x800ce5a0): walking the charset in order, each character
adds 1 (one-byte) or 2 (two-byte) units to the current row; once a row reaches >= 19 units the next character
starts a new row, and after 10 rows a new page (<name>NN). The glyph's number inside its page (32 + n) is its
line in that page's .met, with its pixel rectangle. Pages are 256x256 4bpp BMPs with the Windows default
palette; glyphs use only indices 0 (black), 7 (grey 128), 8 (silver 192) and 15 (white). At most 16 pages per file.

Glyphs: kana, punctuation, ASCII and full-width alphanumerics keep the original Japanese bitmaps (collected
from every original Japanese font); Chinese characters and anything not found there are drawn with
Noto Sans TC Bold-ish (weight 700) at 22 px.
"""
import glob
import io
import os
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
FONTDIR = os.path.join(ROOT, 'work', 'disc', 'files', 'font')
NOTO = 'C:/Windows/Fonts/NotoSansTC-VF.ttf'
CELL = 24
MAX_PAGES = 16


def pages_layout(chars):
    """Split charset into pages following the game's rule. chars: list of (char, code_bytes)."""
    pages = [[]]
    units = 0
    row = 0
    for ch, code in chars:
        w = 1 if len(code) == 1 else 2
        pages[-1].append((ch, code, row, units))
        units += w
        if units >= 19:
            units = 0
            row += 1
            if row >= 10:
                row = 0
                pages.append([])
    if not pages[-1]:
        pages.pop()
    return pages


def read_met(path):
    lines = open(path, 'rb').read().decode('latin-1').split('\r\n')
    rects = []
    for l in lines[3:]:
        p = l.split()
        if len(p) >= 5:
            rects.append(tuple(int(x) for x in p[1:5]))
    return lines[1], lines[2], rects


def original_pool():
    """{char: L-mode glyph image} from the original Japanese fonts (event*_j, hint*, hintmenu)."""
    pool = {}
    names = [os.path.basename(p)[:-4] for p in glob.glob(os.path.join(FONTDIR, '*.txt'))]
    names = [n for n in names if (n.startswith('event') and n.endswith('_j')) or
             (n.startswith('hint') and not n.endswith('k'))]
    for n in sorted(names):
        txt = open(os.path.join(FONTDIR, n + '.txt'), 'rb').read()
        chars = []
        i = 0
        while i < len(txt):
            if txt[i] >= 0x80:
                chars.append(txt[i:i + 2]); i += 2
            else:
                chars.append(txt[i:i + 1]); i += 1
        k = 0
        page = 0
        while k < len(chars) and page < MAX_PAGES:
            mp = os.path.join(FONTDIR, f'{n}{page:02d}.met')
            if not os.path.exists(mp):
                break
            _, _, rects = read_met(mp)
            im = Image.open(os.path.join(FONTDIR, f'{n}{page:02d}.bmp'))
            for r in rects:
                if k >= len(chars):
                    break
                c = chars[k]; k += 1
                try:
                    ch = c.decode('cp932')
                except UnicodeDecodeError:
                    continue
                if ch not in pool:
                    pool[ch] = im.crop(r).copy()
            page += 1
    return pool


class Renderer:
    def __init__(self, size=22, weight=700):
        self.font = ImageFont.truetype(NOTO, size)
        self.font.set_variation_by_axes([weight])
        self.big = ImageFont.truetype(NOTO, size * 4)  # drawn 4x and downsampled
        self.big.set_variation_by_axes([weight])
        self.pool = None

    def coverage(self, ch, w):
        im = Image.new('L', (w * 4, CELL * 4), 0)
        d = ImageDraw.Draw(im)
        d.text((w * 2, CELL * 2), ch, font=self.big, fill=255, anchor='mm')
        return im.resize((w, CELL), Image.LANCZOS)

    def glyph(self, ch, half, keep_all=False):
        """Return a palette-index array (CELL x w). keep_all: original bitmaps for kanji too (round-trip test)."""
        if self.pool is None:
            self.pool = original_pool()
        w = 12 if half else 24
        keep = ch in self.pool and (keep_all or not ('\u4e00' <= ch <= '\u9fff'))
        if keep:
            im = self.pool[ch]
            a = np.array(im, dtype=np.uint8)
            if a.shape[1] != w:
                keep = False
        if not keep:
            cov = np.array(self.coverage(ch, w), dtype=np.int32)
            a = np.zeros(cov.shape, np.uint8)
            # quantise coverage to the 4 levels
            a[cov >= 64] = 7
            a[cov >= 160] = 8
            a[cov >= 224] = 15
        return a


PALETTE = open(os.path.join(FONTDIR, 'hint00100.bmp'), 'rb').read()[54:118]  # Windows default 16 colours


def write_bmp(arr):
    """256x256 4bpp bottom-up BMP with the Windows default 16-colour palette (as the originals)."""
    h, w = arr.shape
    rows = []
    for y in range(h - 1, -1, -1):
        r = arr[y]
        rows.append(bytes((int(r[x]) << 4) | int(r[x + 1]) for x in range(0, w, 2)))
    pix = b''.join(rows)
    head = struct.pack('<2sIHHI', b'BM', 14 + 40 + 64 + len(pix), 0, 0, 14 + 40 + 64)
    info = struct.pack('<IiiHHIIiiII', 40, w, h, 1, 4, 0, len(pix), 0, 0, 16, 16)
    return head + info + PALETTE + pix


def build_font(name, chars, renderer, spacing='5', keep_all=False):
    """chars: ordered list of (char, code_bytes). Returns {filename: bytes}."""
    pages = pages_layout(chars)
    if len(pages) > MAX_PAGES:
        raise ValueError(f'{name}: {len(chars)} characters need {len(pages)} pages (max {MAX_PAGES})')
    files = {name + '.txt': b''.join(c for _, c in chars)}
    for p, glyphs in enumerate(pages):
        arr = np.zeros((256, 256), np.uint8)
        met = ['METRICS1', f'{name}{p:02d}.bmp', spacing]
        for n, (ch, code, row, units) in enumerate(glyphs):
            half = len(code) == 1
            g = renderer.glyph(ch, half, keep_all)
            x0 = units * 12
            y0 = row * CELL
            arr[y0:y0 + CELL, x0:x0 + g.shape[1]] = g
            met.append(f'{32 + n} {x0} {y0} {x0 + g.shape[1]} {y0 + CELL}')
        files[f'{name}{p:02d}.bmp'] = write_bmp(arr)
        files[f'{name}{p:02d}.met'] = ('\r\n'.join(met) + '\r\n').encode('latin-1')
    return files


def charset(strings, cmap):
    """Unique characters in order of first appearance (line breaks excluded), with their codes."""
    seen = {}
    for s in strings:
        for ch in s:
            if ch in '\n\r' or ch in seen:
                continue
            seen[ch] = cmap.code(ch)
    return list(seen.items())
