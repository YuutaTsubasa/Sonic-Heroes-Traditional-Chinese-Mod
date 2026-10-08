"""Build the Chinese files into work/build/files (same layout as the disc's files/).

  python tools/build.py            text, fonts, UTX + sega.prs font
  python tools/build.py --report   also print per-file sizes

Picks each string as zh (text/zh) -> TM (text/tm.json) -> original Japanese.
Writes work/build_report.json.
"""
import json
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import formats as F  # noqa: E402
import fontgen as FG  # noqa: E402
import prs  # noqa: E402
import segafont  # noqa: E402
from charmap import CharMap  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DISC = os.path.join(ROOT, 'work', 'disc', 'files')
OUT = os.path.join(ROOT, 'work', 'build', 'files')
TEXT = os.path.join(ROOT, 'text')


def load(p, d=None):
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else d


TM = load(os.path.join(TEXT, 'tm.json'), {})
REPORT = {'files': {}, 'untranslated': {}, 'errors': []}


def pick(name):
    """{id: (ja, final_text)} for a text/ja file."""
    rows = load(os.path.join(TEXT, 'ja', name + '.json'))
    zh = load(os.path.join(TEXT, 'zh', name + '.json'), {})
    out = {}
    miss = 0
    for r in rows:
        t = zh.get(r['id']) or TM.get(r['ja'])
        if t is None:
            t = r['ja']; miss += 1
        out[r['id']] = (r['ja'], t)
    REPORT['untranslated'][name] = miss
    return out


def write(rel, data):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(data)
    REPORT['files'][rel.replace('\\', '/')] = len(data)


def orig(rel):
    return open(os.path.join(DISC, rel), 'rb').read()


# ---------------------------------------------------------------- event subtitles (REL tables + fonts)
def build_events(cmap, R):
    text = pick('event')
    by_ev = {}
    for k, (ja, t) in text.items():
        ev = int(k[2:6]); ln = int(k[7:])
        by_ev.setdefault(ev, {})[ln] = t
    # fonts, one per event
    for ev, lines in sorted(by_ev.items()):
        name = f'event{ev:04d}_j'
        if not os.path.exists(os.path.join(DISC, 'font', name + '.txt')):
            REPORT['errors'].append(f'no font file for event {ev}')
            continue
        strings = [lines[k] for k in sorted(lines)]
        files = FG.build_font(name, FG.charset(strings, cmap), R)
        old = [f for f in os.listdir(os.path.join(DISC, 'font')) if f.startswith(name)]
        for fn, data in files.items():
            write('font/' + fn, data)
        REPORT.setdefault('removed', []).extend('font/' + f for f in old if f not in files)
    # REL tables
    for fn in sorted(os.listdir(DISC)):
        if not fn.endswith('D.rel'):
            continue
        data = bytearray(orig(fn))
        try:
            T = F.event_table(bytes(data))
        except TypeError:
            continue
        r = T['rel']
        relocs = list(r.relocs(with_pos=True))
        ts = T['rows'][0][3]
        so = r.sections[ts][0]
        addends = sorted({x[4] for x in T['rows']})
        lo = addends[0]
        hi = max(a + data.index(b'\0', so + a) - (so + a) + 1 for a in addends)
        pool = bytearray()
        where = {}
        for ev, ln, k, _, a, raw in T['rows']:
            enc = cmap.encode(by_ev[ev][ln]) + b'\0'
            if enc not in where:
                where[enc] = lo + len(pool)
                pool += enc
            struct.pack_into('>I', data, relocs[k][6] + 4, where[enc])
        if len(pool) > hi - lo:
            REPORT['errors'].append(f'{fn}: event strings need {len(pool)} bytes, room {hi - lo}')
            continue
        data[so + lo:so + hi] = pool + bytes(hi - lo - len(pool))
        write(fn, bytes(data))
        REPORT.setdefault('event_pool', {})[fn] = [len(pool), hi - lo]


# ---------------------------------------------------------------- hint subtitles (.bin + fonts)
def build_hints(cmap, R):
    names = sorted(f[:-5] for f in os.listdir(os.path.join(TEXT, 'ja')) if f.startswith('hint'))
    for name in names:
        text = pick(name)
        raw = orig(f'font/{name}.bin')
        recs, base, texts = F.hint_parse(raw)
        new = {}
        strings = []
        for o, b in texts.items():
            k = f'{name}:{o:05x}'
            t = text[k][1] if k in text else b.decode('cp932').replace('\\n', '\n')
            strings.append(t)
            new[o] = cmap.encode(t.replace('\n', '\\n'))
        out = F.hint_build(recs, new)
        write(f'font/{name}.bin', out)
        files = FG.build_font(name, FG.charset(strings, cmap), R)
        for fn, data in files.items():
            write('font/' + fn, data)
        old = [f for f in os.listdir(os.path.join(DISC, 'font'))
               if f.startswith(name) and f[len(name):len(name) + 2].isdigit() and len(f) == len(name) + 6]
        REPORT.setdefault('removed', []).extend('font/' + f for f in old if f not in files)
        REPORT.setdefault('hint_size', {})[name] = [len(out), len(raw)]


# ---------------------------------------------------------------- system messages (UTX + Unicode font)
def build_menu():
    text = pick('menu')
    sizes, _, ja = F.utx_parse(orig('text/TextJapanese.utx'))
    strings = []
    i = 0
    for g, n in enumerate(sizes):
        for k in range(n):
            strings.append(text[f'{g}.{k}'][1]); i += 1
    write('text/TextJapanese.utx', F.utx_build(sizes, strings))
    font, info = segafont.patch(prs.decompress(orig('advertise/sega.prs')), strings, ja)
    comp = prs.compress(font)
    if len(comp) > segafont.MAX_COMPRESSED:
        REPORT['errors'].append(f'sega.prs compressed to {len(comp)} > {segafont.MAX_COMPRESSED}')
    write('advertise/sega.prs', comp)
    REPORT['sega_font'] = info


# ---------------------------------------------------------------- mission captions (stgtitle/mission/*J00.bmp)
def build_missions(cmap, R):
    """512x64 4bpp BMPs, one line of white text drawn with the subtitle glyphs (text/mission.json)."""
    import numpy as np
    for m in load(os.path.join(TEXT, 'mission.json'), []):
        arr = np.zeros((64, 512), np.uint8)
        x = 0
        for ch in m['zh']:
            half = len(cmap.code(ch)) == 1
            if ch in ' 　':
                x += 12 if half else 24
                continue
            g = R.glyph(ch, half)
            if x + g.shape[1] > 512:
                REPORT['errors'].append(f'mission caption too long: {m["zh"]}')
                break
            arr[0:24, x:x + g.shape[1]] = g
            x += g.shape[1]
        data = FG.write_bmp(arr)
        for f in m['files']:
            write('stgtitle/mission/' + f, data)


# ---------------------------------------------------------------- disc banner + memory card comment (IPL, SJIS)
BANNER = [('索尼克英雄', 32), ('世嘉', 32), ('索尼克英雄', 64), ('世嘉', 64),
          ('(C) SONICTEAM / SEGA, 2003' + chr(10) + '１２名英雄展開的超音速小隊動作遊戲', 128)]
NUL = bytes(1)
DOL_STRINGS = [('ソニックヒーローズ　：　%s', '索尼克英雄　：　%s'), ('エンブレム枚数　：　%s枚', '徽章數　：　%s個')]


def build_banner():
    b = bytearray(orig('opening.bnr'))
    o = 0x1820
    for text, n in BANNER:
        enc = text.encode('cp932')
        assert len(enc) < n, text
        b[o:o + n] = enc.ljust(n, NUL)
        o += n
    write('opening.bnr', bytes(b))
    dol = bytearray(open(os.path.join(ROOT, 'work', 'disc', 'sys', 'main.dol'), 'rb').read())
    for ja, zh in DOL_STRINGS:
        a = ja.encode('cp932'); z = zh.encode('cp932')
        assert dol.count(a) == 1 and len(z) <= len(a), ja
        i = dol.index(a)
        dol[i:i + len(a)] = z.ljust(len(a), NUL)
    p = os.path.join(ROOT, 'work', 'build', 'sys', 'main.dol')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(bytes(dol))


# ---------------------------------------------------------------- boss title cards (letters -> Chinese name)
def build_bosses():
    import boss
    import one
    import txd
    for stage in boss.BOSSES:
        rel = f'stgtitle/{stage}title_disp.one'
        src = os.path.join(OUT, rel)
        raw = open(src if os.path.exists(src) else os.path.join(DISC, rel), 'rb').read()
        ver, names, ents = one.parse(raw)
        files = {n: prs.decompress(c) for n, c in ents}
        anm_name = next(n for n in files if n.upper().endswith('.ANM') and 'BOSS' in n.upper())
        txd_name = next(n for n in files if n.upper().endswith('.TXD'))
        anm, tx = boss.patch(stage, files[anm_name], files[txd_name], txd.parse)
        new = [(n, prs.compress(anm) if n == anm_name else prs.compress(tx) if n == txd_name else c) for n, c in ents]
        write(rel, one.build(ver, names, new))


def main():
    if os.path.exists(os.path.dirname(OUT)):
        shutil.rmtree(os.path.dirname(OUT))
    cmap = CharMap()
    R = FG.Renderer()
    build_events(cmap, R)
    build_hints(cmap, R)
    build_menu()
    build_missions(cmap, R)
    build_banner()
    import texbuild
    texbuild.build(write, REPORT)
    build_bosses()
    cmap.save()
    REPORT['removed'] = sorted(set(REPORT.get('removed', [])))
    json.dump(REPORT, open(os.path.join(ROOT, 'work', 'build_report.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('files', len(REPORT['files']), 'removed', len(REPORT['removed']),
          'untranslated', sum(REPORT['untranslated'].values()))
    for e in REPORT['errors']:
        print('ERROR', e)
    if REPORT['errors']:
        sys.exit(1)


if __name__ == '__main__':
    main()
