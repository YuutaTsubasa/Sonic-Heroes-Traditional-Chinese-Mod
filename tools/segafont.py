"""advertise/sega.prs: the Unicode bitmap font used for the system messages (text/TextJapanese.utx).

Decompressed layout ("FONT CREATER by NEOS"): 0x100-byte header (0x49 width, 0x4a height, 0x67 bits per pixel),
then 8176 records of 160 bytes: u16 code (little-endian Unicode), 7 fixed bytes, u8 advance (21 for full-width),
6 zero bytes, 24x24 pixels at 2 bits (MSB first, 3 = ink). The game searches the records linearly by code
(main.dol 0x8012f4e4), so a record can be given any code.

The loader reads the compressed file into a 0x96000-byte buffer (main.dol 0x8012fe50), so the recompressed file
must stay within MAX_COMPRESSED; the decompressed size must not change (0x13F700 buffer).

patch(): every Chinese character in the new strings gets a glyph drawn with Noto Sans TC. Characters the font
already has keep their record (redrawn if they are ideographs, for Traditional shapes); missing ones take the
record of a kanji used by neither the Japanese nor the Chinese strings.
"""
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFont

NOTO = 'C:/Windows/Fonts/NotoSansTC-VF.ttf'
REC = 160
HEAD = 0x100
MAX_COMPRESSED = 0x96000


def is_ideograph(ch):
    return '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf'


class Drawer:
    def __init__(self, size=20, weight=450):
        self.f = ImageFont.truetype(NOTO, size * 4)
        self.f.set_variation_by_axes([weight])

    def glyph(self, ch):
        im = Image.new('L', (96, 96), 0)
        ImageDraw.Draw(im).text((42, 46), ch, font=self.f, fill=255, anchor='mm')  # centre (10.5, 11.5)
        a = np.array(im.resize((24, 24), Image.LANCZOS), dtype=np.int32)
        return np.clip((a + 42) // 85, 0, 3).astype(np.uint8)


def pack(a):
    out = bytearray()
    for y in range(24):
        for x in range(0, 24, 4):
            out.append((a[y, x] << 6) | (a[y, x + 1] << 4) | (a[y, x + 2] << 2) | a[y, x + 3])
    return bytes(out)


def unpack(b):
    a = np.zeros((24, 24), np.uint8)
    for y in range(24):
        for x in range(24):
            a[y, x] = (b[y * 6 + x // 4] >> (6 - 2 * (x % 4))) & 3
    return a


def patch(font: bytes, zh_strings, ja_strings):
    font = bytearray(font)
    n = (len(font) - HEAD) // REC
    code_at = {struct.unpack_from('<H', font, HEAD + i * REC)[0]: i for i in range(n)}
    need = []
    for s in zh_strings:
        for ch in s:
            if ch not in '\n\r' and ord(ch) >= 0x80 and ch not in need:
                need.append(ch)
    keep = set(need) | {ch for s in ja_strings for ch in s}
    victims = [c for c in sorted(code_at, reverse=True)
               if is_ideograph(chr(c)) and chr(c) not in keep]
    template = font[HEAD + code_at[ord('中')] * REC:HEAD + code_at[ord('中')] * REC + 16]
    d = Drawer()
    redrawn = added = 0
    for ch in need:
        if ord(ch) in code_at:
            if not is_ideograph(ch):
                continue
            i = code_at[ord(ch)]
            redrawn += 1
        else:
            if not victims:
                raise RuntimeError('no free glyph records left')
            v = victims.pop(0)
            i = code_at.pop(v)
            code_at[ord(ch)] = i
            added += 1
        p = HEAD + i * REC
        hdr = bytearray(template)
        struct.pack_into('<H', hdr, 0, ord(ch))
        font[p:p + 16] = hdr
        font[p + 16:p + REC] = pack(d.glyph(ch))
    return bytes(font), {'chars': len(need), 'redrawn': redrawn, 'added': added, 'free_left': len(victims)}
