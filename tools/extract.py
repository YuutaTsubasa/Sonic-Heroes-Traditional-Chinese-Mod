"""Extract the Japanese text into translation units: text/ja/{menu,event,hint}.json.

Each unit: {id, ja, lines, max_units, en, ...}. `en` is the English version of the same string, for context.
Run from the repo root:  python tools/extract.py
"""
import glob
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import formats as F  # noqa: E402
from tl import units  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DISC = os.path.join(ROOT, 'work', 'disc', 'files')
OUT = os.path.join(ROOT, 'text', 'ja')


def limits(s):
    ls = s.split('\n')
    return {'lines': len(ls), 'max_units': max(units(x) for x in ls)}


def menu():
    sizes, _, ja = F.utx_parse(open(os.path.join(DISC, 'text', 'TextJapanese.utx'), 'rb').read())
    _, _, en = F.utx_parse(open(os.path.join(DISC, 'text', 'TextEnglish.utx'), 'rb').read())
    out = []
    i = 0
    for g, n in enumerate(sizes):
        for k in range(n):
            out.append({'id': f'{g}.{k}', 'ja': ja[i], **limits(ja[i]), 'en': en[i]})
            i += 1
    return out


def event_rows(path, lang_start=None):
    data = open(path, 'rb').read()
    T = F.event_table(data)
    return {(ev, ln): raw for ev, ln, k, ts, a, raw in T['rows']}


def event_en(path):
    """English table: the first (event, line, ptr) table in .data with ASCII text."""
    from rel import Rel
    data = open(path, 'rb').read()
    r = Rel(data)
    by = {}
    for mod, sec, pos, t, ts, a in r.relocs():
        if t == 1 and mod == r.id:
            by[(sec, pos)] = (ts, a)
    for sec, (so, size, _) in enumerate(r.sections):
        if not so or not size:
            continue
        d = data[so:so + size]
        for off in range(0, size - 12, 4):
            if d[off:off + 8] == b'\xff' * 8 and d[off + 8:off + 12] == b'\0' * 4:
                q = off - 12
                while q >= 0 and (sec, q + 8) in by:
                    q -= 12
                rows = {}
                for p in range(q + 12, off, 12):
                    ev, ln = struct.unpack_from('>II', d, p)
                    ts, a = by[(sec, p + 8)]
                    to = r.sections[ts][0] + a
                    rows[(ev, ln)] = data[to:data.index(b'\0', to)]
                txt = b''.join(rows.values())
                if b'Sonic' in txt and max(txt) < 0x80:
                    return {k: v.decode('ascii') for k, v in rows.items()}
    return {}


def event():
    rels = sorted(glob.glob(os.path.join(DISC, '*D.rel')))
    base = None
    locs = {}
    for p in rels:
        try:
            rows = event_rows(p)
        except TypeError:
            continue  # no event table (advertiseD, autosaveD)
        name = os.path.basename(p)
        if base is None:
            base = rows
        assert rows == base, f'{name}: event table differs'
        locs[name] = True
    en = event_en(os.path.join(DISC, 'movieD.rel'))
    out = []
    for (ev, ln), raw in base.items():
        ja = raw.decode('cp932')
        u = {'id': f'ev{ev:04d}.{ln:02d}', 'ja': ja, **limits(ja), 'en': en.get((ev, ln), '')}
        out.append(u)
    out.sort(key=lambda u: u['id'])
    return out, sorted(locs)


# who field of the hint records
SPEAKERS = {0: 'Sonic', 1: 'Knuckles', 2: 'Tails', 3: 'Shadow', 4: 'Omega', 5: 'Rouge', 6: 'Amy', 7: 'Big',
            8: 'Cream', 9: 'Espio', 10: 'Vector', 11: 'Charmy', 12: 'mission giver (old man, ～じゃ)',
            13: 'Omochao', 14: 'Metal Sonic', 65535: 'narrator/tutorial'}


def hint():
    out = {}
    for p in sorted(glob.glob(os.path.join(DISC, 'font', 'hint*.bin'))):
        name = os.path.basename(p)[:-4]
        if name[-1] in 'efgiks':
            continue
        recs, base, texts = F.hint_parse(open(p, 'rb').read())
        erecs, ebase, etexts = F.hint_parse(open(os.path.join(DISC, 'font', name + 'e.bin'), 'rb').read())
        eby = {(r[0], r[1]): etexts[r[2]] for r in erecs}
        who = {}
        for r in recs:
            who.setdefault(r[2], []).append((r[0], r[1]))
        for o, raw in sorted(texts.items()):
            ja = raw.decode('cp932').replace('\\n', '\n')
            if not ja:
                continue
            keys = who[o]
            en = eby.get(keys[0], b'').decode('latin-1').replace('\\n', '\n')
            out.setdefault(name, []).append({
                'id': f'{name}:{o:05x}', 'ja': ja, **limits(ja), 'en': en,
                'speaker': ' / '.join(SPEAKERS.get(w, str(w)) for w in sorted({k[1] for k in keys})),
                'hint': sorted({k[0] for k in keys})})
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    m = menu()
    ev, rels = event()
    h = hint()
    for name, data in (('menu', m), ('event', ev), *sorted(h.items())):
        with open(os.path.join(OUT, name + '.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print(name, len(data), 'strings', sum(len(u['ja']) for u in data), 'chars')
    print('event table found in', len(rels), 'REL files')


if __name__ == '__main__':
    main()
