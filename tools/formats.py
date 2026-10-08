"""Sonic Heroes (GameCube, G9SJ8P) text containers.

utx   text/TextJapanese.utx   big-endian: u32 ngroups, u32 sizes[ngroups], u32 offsets[sum], UTF-16BE NUL-terminated
hint  font/hint*.bin          little-endian 12-byte records (u16 hint, u16 who, u32 text_off, u32 extra) ending with
                              an all-zero record, then NUL-terminated SJIS text; line breaks are the two chars "\\n"
event *D.rel                  .data table of (u32 event, u32 line, char *text) ending with (-1, -1, 0); pointers are
                              ADDR32 relocations, so the string pool can be repacked by rewriting relocation addends
font  font/<name>.txt         per-file charset (glyph n = n-th char) + <name>NN.bmp pages (256x256 4bpp, 10x10 cells
                              of 24 px) + <name>NN.met metrics ("METRICS1", bmp name, spacing, "code x0 y0 x1 y1")
"""
import re
import struct

from rel import Rel


# ---------------------------------------------------------------- UTX
def utx_parse(data: bytes):
    n = struct.unpack_from('>I', data, 0)[0]
    sizes = list(struct.unpack_from('>%dI' % n, data, 4))
    offs = struct.unpack_from('>%dI' % sum(sizes), data, 4 + 4 * n)
    strings = []
    for o in offs:
        e = o
        while data[e:e + 2] != b'\0\0':
            e += 2
        strings.append(data[o:e].decode('utf-16-be'))
    return sizes, list(offs), strings


def utx_build(sizes, strings):
    """Rebuild: every string in order, NUL-terminated and padded to 4 bytes (byte-identical for the originals)."""
    n = len(sizes)
    head = 4 + 4 * n + 4 * len(strings)
    body = bytearray()
    new = []
    for s in strings:
        new.append(head + len(body))
        body += s.encode('utf-16-be') + b'\0\0'
        while len(body) % 4:
            body += b'\0'
    return struct.pack('>%dI' % (1 + n + len(strings)), n, *sizes, *new) + bytes(body)


# ---------------------------------------------------------------- hint .bin
def hint_parse(data: bytes):
    recs = []
    i = 0
    while True:
        r = struct.unpack_from('<HHII', data, i)
        i += 12
        if r == (0, 0, 0, 0):
            break
        recs.append(list(r))
    base = i
    texts = {}
    for r in recs:
        o = r[2]
        if o not in texts:
            e = data.index(b'\0', base + o)
            texts[o] = data[base + o:e]
    return recs, base, texts


def hint_build(recs, texts_by_off, order=None):
    """texts_by_off: {old_off: bytes}. Strings are written in old-offset order."""
    order = order or sorted(texts_by_off)
    head = bytearray()
    body = bytearray()
    remap = {}
    for o in order:
        remap[o] = len(body)
        body += texts_by_off[o] + b'\0'
    for r in recs:
        head += struct.pack('<HHII', r[0], r[1], remap[r[2]], r[3])
    head += b'\0' * 12
    return bytes(head + body)


# ---------------------------------------------------------------- event table in REL
JP = re.compile('[ぁ-ヺ一-龯]')


def event_table(data: bytes):
    """Locate the Japanese event subtitle table. Returns dict with rel, table section/offset and rows
    [(event, line, reloc_index, string_offset_in_section, raw_bytes)]."""
    r = Rel(data)
    relocs = list(r.relocs())
    by_pos = {}
    for k, (mod, sec, pos, t, ts, a) in enumerate(relocs):
        if t == 1 and mod == r.id:
            by_pos[(sec, pos)] = (k, ts, a)
    best = None
    for (sec, pos) in sorted(by_pos):
        so = r.sections[sec][0]
        if not so or pos < 8:
            continue
        # walk a run of records starting here
        rows = []
        p = pos
        while (sec, p) in by_pos:
            ev, ln = struct.unpack_from('>II', data, so + p - 8)
            k, ts, a = by_pos[(sec, p)]
            to = r.sections[ts][0] + a
            raw = data[to:data.index(b'\0', to)]
            rows.append((ev, ln, k, ts, a, raw))
            p += 12
        if len(rows) > 100:
            try:
                txt = ''.join(x[5].decode('cp932') for x in rows[:20])
            except UnicodeDecodeError:
                continue
            if JP.search(txt) and struct.unpack_from('>ii', data, so + p - 8) == (-1, -1):
                if best is None or len(rows) > len(best[2]):
                    best = (sec, pos - 8, rows)
    sec, start, rows = best
    return {'rel': r, 'relocs': relocs, 'sec': sec, 'start': start, 'rows': rows}
