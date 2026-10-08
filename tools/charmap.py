"""Two-byte codes for the SJIS-side text (event subtitles, hint subtitles).

The game treats any byte >= 0x80 as the lead of a two-byte character and looks the pair up in the per-file
charset (font/<name>.txt), so a code is only a key. A character that cp932 can encode keeps its cp932 code;
any other character (Traditional forms such as 說, 這) gets a free code from lead bytes 0xF0-0xFC, stored in
text/charmap.json so the assignment never changes between builds.
"""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'text', 'charmap.json')


def _free_codes():
    for lead in range(0xF0, 0xFD):
        for trail in range(0x40, 0xFD):
            if trail in (0x5C, 0x7F):  # never a backslash trail ("\\n" is a two-char line break in hint text)
                continue
            yield bytes([lead, trail])


class CharMap:
    def __init__(self):
        self.extra = {}
        if os.path.exists(PATH):
            self.extra = json.load(open(PATH, encoding='utf-8'))['extra']
        self.extra = {k: bytes.fromhex(v) for k, v in self.extra.items()}
        self.dirty = False

    def code(self, ch):
        if ch in self.extra:
            return self.extra[ch]
        try:
            b = ch.encode('cp932')
            if len(b) == 1 or b[0] < 0xF0:
                return b
        except UnicodeEncodeError:
            pass
        used = set(self.extra.values())
        for c in _free_codes():
            if c not in used:
                self.extra[ch] = c
                self.dirty = True
                return c
        raise RuntimeError('out of free codes')

    def encode(self, s):
        return b''.join(self.code(ch) for ch in s)

    def decode(self, data):
        rev = {v: k for k, v in self.extra.items()}
        out = []
        i = 0
        while i < len(data):
            if data[i] >= 0x80:
                c = data[i:i + 2]
                out.append(rev.get(c) or c.decode('cp932'))
                i += 2
            else:
                out.append(chr(data[i]))
                i += 1
        return ''.join(out)

    def save(self):
        if not self.dirty:
            return
        n = sum(1 for _ in _free_codes())
        json.dump({'extra': {k: v.hex().upper() for k, v in sorted(self.extra.items(), key=lambda kv: kv[1])},
                   'free_codes_left': n - len(self.extra)},
                  open(PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        self.dirty = False
