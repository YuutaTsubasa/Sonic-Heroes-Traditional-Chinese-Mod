"""Write out/SonicHeroes_zh-TW.iso from work/orig.iso + work/build/files (run tools/build.py first)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import gciso  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
BUILD = os.path.join(ROOT, 'work', 'build', 'files')


def main():
    rep = json.load(open(os.path.join(ROOT, 'work', 'build_report.json'), encoding='utf-8'))
    changes = {}
    for dp, _, fs in os.walk(BUILD):
        for f in fs:
            p = os.path.join(dp, f)
            changes[os.path.relpath(p, BUILD).replace(os.sep, '/')] = open(p, 'rb').read()
    for r in rep.get('removed', []):
        changes.setdefault(r, None)
    os.makedirs(os.path.join(ROOT, 'out'), exist_ok=True)
    dst = os.path.join(ROOT, 'out', 'SonicHeroes_zh-TW.iso')
    info = gciso.patch(os.path.join(ROOT, 'work', 'orig.iso'), dst, changes)
    dol = os.path.join(ROOT, 'work', 'build', 'sys', 'main.dol')
    if os.path.exists(dol):
        import struct
        data = open(dol, 'rb').read()
        with open(dst, 'r+b') as f:
            f.seek(0x420)
            off = struct.unpack('>I', f.read(4))[0]
            f.seek(off)
            old = f.read(len(data))
            assert len(old) == len(data)
            f.seek(off)
            f.write(data)
    print(dst, info, 'changed', sum(v is not None for v in changes.values()), 'removed',
          sum(v is None for v in changes.values()))


if __name__ == '__main__':
    main()
