"""out/SonicHeroes_zh-TW.iso -> release files: xdelta patch (verified by applying it), player README, zip.

  python tools/package.py [version]
xdelta3 3.1.0 (github.com/jmacd/xdelta-gpl): set XDELTA3, or it is taken from work/bin/xdelta3.exe.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
import zlib

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ORIG = os.path.join(ROOT, 'work', 'orig.iso')
ISO = os.path.join(ROOT, 'out', 'SonicHeroes_zh-TW.iso')
NAME = 'Sonic.Heroes.Japan.zh-TW'
XDELTA = os.environ.get('XDELTA3') or os.path.join(ROOT, 'work', 'bin', 'xdelta3.exe')


def hashes(path):
    md5, sha1, crc = hashlib.md5(), hashlib.sha1(), 0
    with open(path, 'rb') as f:
        while True:
            b = f.read(1 << 22)
            if not b:
                break
            md5.update(b); sha1.update(b); crc = zlib.crc32(b, crc)
    return {'size': os.path.getsize(path), 'crc32': f'{crc:08X}', 'md5': md5.hexdigest(), 'sha1': sha1.hexdigest()}


README = '''索尼克英雄（Sonic Heroes）台灣繁體中文化補丁 {version}
==================================================

補丁檔：{patch}

■ 需要的原版遊戲
  Sonic Heroes (Japan) (En,Ja,Fr,De,Es,It)　GameCube 日版，遊戲代碼 G9SJ8P
  必須是未修改的 ISO（{o[size]:,} bytes）：
    CRC32  {o[crc32]}
    MD5    {o[md5]}
    SHA-1  {o[sha1]}

  如果手上是 .rvz / .gcz 等壓縮格式，先用 Dolphin 轉回 ISO：
    遊戲清單上按右鍵 →「轉換檔案…」→ 格式選「ISO」
  或用命令列：
    DolphinTool.exe convert -i "原檔.rvz" -o "Sonic Heroes (Japan).iso" -f iso

■ 套用補丁
  任選一種：
  ・Delta Patcher（Windows 圖形介面）：Original file 選原版 ISO，
    XDelta patch 選本補丁，按「Apply patch」
  ・xdelta3 命令列：
    xdelta3 -d -s "Sonic Heroes (Japan).iso" "{patch}" "Sonic Heroes (zh-TW).iso"

  套用後的 ISO：
    SHA-1  {n[sha1]}

■ 遊玩
  ・用 Dolphin 或支援 ISO 的 GameCube 載入器開啟。
  ・中文取代的是遊戲的「日文」：選項的語言請維持日文（選單上顯示為「中文」）。
  ・語音不變。

■ 內容
  ・全部 11,661 句文字：過場字幕、關卡中的語音字幕與玩具巧歐提示、系統／記憶卡訊息
  ・標題 LOGO、主選單／選項／故事／挑戰／雙人對戰等介面圖片、隊伍名牌、結算畫面
  ・關卡標題卡（關卡名、任務、特別關卡、Boss 名稱）、122 張任務說明
  ・光碟橫幅、記憶卡存檔說明
  ・譯名依 SEGA 官方繁體中文（索尼克、塔爾斯、納克魯斯、夏特、露姬、蛋頭博士、混沌翡翠……），
    Omega 保留英文，卡歐斯（Chaos），王者翡翠

■ 尚未中文化
  ・預錄影片（.sfd）中的日文

《Sonic Heroes》及其文字、圖片、音樂的權利屬於 SEGA；本補丁為非官方的粉絲作品，不含遊戲本體。
原始碼與譯文：https://github.com/YuutaTsubasa/Sonic-Heroes-Traditional-Chinese-Mod
'''


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else 'v1.0'
    out = os.path.join(ROOT, 'out')
    patch = os.path.join(out, NAME + '.xdelta')
    if os.path.exists(patch):
        os.remove(patch)
    # -A= : no application header (it would record local file paths)
    subprocess.run([XDELTA, '-e', '-9', '-A=', '-S', 'djw', '-B', str(512 << 20), '-s', ORIG, ISO, patch], check=True)
    check = os.path.join(ROOT, 'work', 'patch_check.iso')
    subprocess.run([XDELTA, '-d', '-f', '-s', ORIG, patch, check], check=True)
    o, n, c = hashes(ORIG), hashes(ISO), hashes(check)
    os.remove(check)
    if c['sha1'] != n['sha1']:
        sys.exit('patch check failed: applied ISO differs from the built ISO')
    readme = os.path.join(out, 'README.txt')
    open(readme, 'w', encoding='utf-8-sig', newline='\r\n').write(
        README.format(version=version, patch=os.path.basename(patch), o=o, n=n))
    z = os.path.join(out, f'SonicHeroes-zh-TW-{version}.zip')
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as f:
        f.write(patch, os.path.basename(patch))
        f.write(readme, 'README.txt')
    print('patch', os.path.getsize(patch), 'bytes; verified; original sha1', o['sha1'], '-> ', n['sha1'])
    print(z)


if __name__ == '__main__':
    main()
