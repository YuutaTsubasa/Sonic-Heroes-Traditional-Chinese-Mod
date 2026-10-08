"""Scoped rename in text/zh + tm + glossary: only rows whose Japanese contains the trigger.

  python tools/rename.py [--dry]
RULES = [(ja_trigger, old_zh, new_zh, ja_exclude)] — a row is touched when its Japanese contains ja_trigger
outside any ja_exclude word (longest names protected first).
"""
import glob
import json
import os
import re
import shutil
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'text')
RULES = [
    ('オメガ', '奧米伽', 'Omega', []),
    ('マスターエメラルド', '主翡翠', '王者翡翠', []),
    ('カオス', '混沌', '卡歐斯', ['カオスエメラルド', 'カオスコントロール', 'カオスインフェルノ', 'カオティクス']),
]


def applies(ja, trig, excl):
    for e in sorted(excl, key=len, reverse=True):
        ja = ja.replace(e, '')
    return trig in ja


def fix(ja, zh):
    for trig, old, new, excl in RULES:
        if applies(ja, trig, excl) and old in zh:
            if trig == 'カオス':
                # keep official compounds
                zh = re.sub('混沌(?!翡翠|控制|煉獄)', new, zh)
            else:
                zh = zh.replace(old, new)
    return zh


def main():
    dry = '--dry' in sys.argv
    if not dry:
        shutil.copytree(ROOT + '/zh', ROOT + f'/../work/zh_backup_{int(time.time())}')
    n = 0
    for p in glob.glob(ROOT + '/ja/*.json'):
        name = os.path.basename(p)
        ja = {r['id']: r['ja'] for r in json.load(open(p, encoding='utf-8'))}
        zp = ROOT + '/zh/' + name
        if not os.path.exists(zp):
            continue
        zh = json.load(open(zp, encoding='utf-8'))
        for k, v in zh.items():
            nv = fix(ja[k], v)
            if nv != v:
                n += 1
                if dry and n <= 15:
                    print(k, v.replace('\n', '/'), '->', nv.replace('\n', '/'))
                zh[k] = nv
        if not dry:
            json.dump(zh, open(zp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
    tm = json.load(open(ROOT + '/tm.json', encoding='utf-8'))
    tm = {k: fix(k, v) for k, v in tm.items()}
    g = json.load(open(ROOT + '/glossary.json', encoding='utf-8'))
    g['オメガ'] = {'zh': 'Omega', 'note': '角色；使用者決定保留英文（同 Shadow 專案）'}
    g['マスターエメラルド'] = {'zh': '王者翡翠', 'note': '用語；與 SADX 專案一致'}
    g['カオス'] = {'zh': '卡歐斯', 'note': '水神 Chaos；使用者決定（SADX）。カオスエメラルド/カオスコントロール 仍作 混沌'}
    if not dry:
        json.dump(tm, open(ROOT + '/tm.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
        json.dump(g, open(ROOT + '/glossary.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
    print('rows changed', n, '(dry run)' if dry else '')


if __name__ == '__main__':
    main()
