# 索尼克英雄（Sonic Heroes）GameCube 日版 繁體中文化

非官方粉絲翻譯。《Sonic Heroes》及其文字、圖片的權利屬於 SEGA；本 MOD 為非官方的粉絲作品。

**本 repo 不含任何遊戲資料**（原文、貼圖、光碟映像都不在這裡）。只有工具、譯文（以字串 id 對應）、貼圖重繪規格與用語表；建置時從你自己的光碟映像讀出原始資料。

- 對象：`Sonic Heroes (Japan)`，遊戲 ID `G9SJ8P`（GameCube）
- 成品：`out/SonicHeroes_zh-TW.iso`（與原版同大小 1,459,978,240 位元組），Dolphin 或實機皆可載入
- 遊戲語言請用**日文**（中文取代的是日文的文字檔）

## 已中文化

| 內容 | 檔案 | 作法 |
| --- | --- | --- |
| 過場字幕（67 段劇情，492 句） | 16 個 `*D.rel` 內的字幕表 + `font/event*_j.*` | 重排 REL 的日文字串池、改寫重定位 addend；每段劇情重新產生字型頁 |
| 關卡中語音字幕、玩具巧歐提示（27 檔） | `font/hint*.bin` + `font/hint*.txt/NN.bmp/NN.met` | 重建 .bin；每檔重新產生字型頁（最多 16 頁） |
| 系統／記憶卡訊息（238 句） | `text/TextJapanese.utx` + `advertise/sega.prs` | UTF-16 文字；在 Unicode 點陣字型中重繪或替換字形 |
| 選單、關卡名、隊伍、結算等貼圖（258 張，326 個副本） | `advertise/J/*.one`、`stgtitle/*.one`、`*_disp*.one` | 每張一份 `text/tex/<id>.json`（擦除＋重畫），重新編碼回原 GX 格式（C4/C8 沿用調色盤並把新色放進空槽、CMPR 只重壓有變動的區塊），重算 mipmap，PRS 重壓 |
| 關卡標題卡（MISSION、EXTRA MISSION、SUPER HARD、Stage） | `stgtitle/*title_disp*.one` | 關卡名與 Boss 名的大字維持英文：日版本來就是「大字英文＋日文名稱條」，名稱條已改成中文，避免同一名稱出現兩次（`tools/boss.py` 保留錨點字母法作參考，未啟用） |
| 任務說明（78 句，122 檔） | `stgtitle/mission/*J00.bmp` | `text/mission.json`，用字幕字型重畫 |
| 光碟橫幅、記憶卡存檔說明 | `opening.bnr`、`main.dol` | Shift-JIS 可表示的繁體字 |

**尚未處理／未驗證**：預錄影片（`.sfd`）中的日文；尚未在 Dolphin 實機遊玩測試（只做了讀回驗證）。

## 下載與安裝

到 [Releases](../../releases) 下載 `.xdelta` 補丁（壓縮檔內附 README）：

1. 準備未修改的日版 ISO（`.rvz` 先用 Dolphin「轉換檔案」轉回 ISO）。
2. 用 Delta Patcher 或 `xdelta3 -d -s 原版.iso 補丁.xdelta 中文版.iso` 套用。
3. 用 Dolphin 開啟，遊戲語言維持日文。

## 建置

需要：Python 3.12（Pillow、numpy、capstone）、Noto Sans TC（`C:/Windows/Fonts/NotoSansTC-VF.ttf`）、Dolphin 的 `DolphinTool.exe`。

```bash
DolphinTool.exe extract -i "Sonic Heroes (Japan).rvz" -o work/disc        # 解出檔案系統
DolphinTool.exe convert -i "Sonic Heroes (Japan).rvz" -o work/orig.iso -f iso
PYTHONUTF8=1 python tools/extract.py      # text/ja/*.json（不進版控）
PYTHONUTF8=1 python tools/tex.py scan     # work/tex/index.json：貼圖 id 索引
PYTHONUTF8=1 python tools/build.py        # work/build/files
PYTHONUTF8=1 python tools/verify.py --png work/preview.png
PYTHONUTF8=1 python tools/make_iso.py     # out/SonicHeroes_zh-TW.iso
PYTHONUTF8=1 python tools/package.py v1.0 # out/*.xdelta（套用驗證）+ README.txt + zip；需要 xdelta3（work/bin/xdelta3.exe 或 XDELTA3）
```

貼圖流程見 `TEXTURES.md`（`tools/tex.py show / preview`）。翻譯流程見 `TRANSLATE.md`（`tools/tl.py next / commit`）。用語表 `text/glossary.json`，翻譯記憶 `text/tm.json`，譯文 `text/zh/*.json`，中文字碼表 `text/charmap.json`（不可變動）。

## 格式筆記

- `.one`：小端 RW 區塊、PRS 壓縮（`tools/one.py`，727 檔來回重建一致）。
- 事件字幕：`.data` 中 `(u32 event, u32 line, char*)` 表，以 `(-1,-1,0)` 結尾；日、英、法、德、義、韓、西各一張。
- 每檔字型：`.txt` 是字元順序；排版規則（main.dol 0x800ce5a0）＝每列累計 ≥19 個半形單位換列、10 列換頁；位元組 ≥0x80 一律當雙位元組字首，所以 cp932 沒有的繁體字配到 F0–FC 區的空碼。
- `sega.prs`：「FONT CREATER by NEOS」，8176 筆 160 位元組紀錄（Unicode 碼、寬度、24×24 2bpp）；讀檔緩衝 0x96000，壓縮後不得超過。
- ISO：原版 FST 之後有約 175 MB 空隙，變大的檔案放進去（`tools/gciso.py`，無變更時輸出與原檔完全相同）。
