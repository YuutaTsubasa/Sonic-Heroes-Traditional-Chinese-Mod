"""Translation workflow for Sonic Heroes (GameCube, Japan) text (ja -> zh-TW).

Data (all under text/):
  ja/<FILE>.json      source strings [{id, ja}]
  zh/<FILE>.json      translations {id: zh}
  glossary.json       proper nouns / terms {ja: {"zh": ..., "note": ...}}
  tm.json             sentence memory {ja: zh}

Commands:
  status                         progress per file
  next <FILE> [N]                next N untranslated strings (exact TM hits and strings
                                 without Japanese are filled automatically) + matching
                                 glossary terms and similar TM entries
  commit <FILE> <batch.json>     save translations, update TM and glossary
  lookup <text>                  search glossary + TM
  term <ja> <zh> [note]          add/update a glossary term
  check [FILE]                   re-validate saved translations
"""
import difflib, json, os, re, sys, time
from contextlib import contextmanager

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "text")
GLOSSARY = os.path.join(ROOT, "glossary.json")
TM = os.path.join(ROOT, "tm.json")
LOCK = os.path.join(ROOT, ".lock")

# printf codes in the system messages (menu.json): %02d %d %s
TOKEN = re.compile(r"%[0-9]*[dsx]|%%")
JAPANESE = re.compile(r"[ぁ-ゖァ-ヺ一-鿿々ｦ-ﾝ]")
KANA = re.compile(r"[ぁ-ゖァ-ヺｦ-ﾝ]")


@contextmanager
def locked():
    """Cross-process lock so parallel translators can share glossary/TM."""
    for _ in range(1200):
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY); break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(LOCK) > 60:
                    os.remove(LOCK)
            except FileNotFoundError:
                pass
            time.sleep(0.1)
    else:
        raise RuntimeError("lock timeout")
    try:
        yield
    finally:
        os.close(fd); os.remove(LOCK)


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=isinstance(data, dict))
    os.replace(tmp, path)


def src(name):
    return load(os.path.join(ROOT, "ja", name + ".json"), None)


def zh_path(name):
    return os.path.join(ROOT, "zh", name + ".json")


def units(line):
    """Display width in half-width units (full-width = 2). Tags have no width."""
    line = TOKEN.sub("", line)
    return sum(1 if ord(c) < 0x80 or 0xff61 <= ord(c) <= 0xff9f else 2 for c in line)


def segments(s):
    """Heroes text has no page markers: one page per string."""
    return [s]


def max_units(s):
    return max((units(l) for seg in segments(s) for l in seg.split("\n")), default=0)


def glossary_hits(text, glossary):
    return {k: v for k, v in glossary.items() if k in text}


def enc_len(line):
    """Stored byte length (Chinese characters take 2 bytes, ASCII 1)."""
    return units(line)


def check(ja, zh, row=None):
    """Return list of problems with a translation. row = the text/ja entry (limits)."""
    row = row or {}
    if zh == ja:          # kept in the original on purpose (音樂卡曲名, 人名)
        return []
    errs = []
    a, b = TOKEN.findall(ja), TOKEN.findall(zh)
    if a != b:
        errs.append(f"tokens differ (same tokens, same order): {a} vs {b}")
    if "\\n" in zh:
        errs.append("literal backslash-n; use a real line break")
    if KANA.search(TOKEN.sub("", zh)):
        errs.append("Japanese kana left in translation")
    for ch in set(TOKEN.sub("", zh)):
        if ch == "\n" or 0x20 <= ord(ch) < 0x7f or ch == "·":
            continue
        if re.match(r"[一-鿿]", ch):
            try:
                ch.encode("cp950")
            except UnicodeEncodeError:
                errs.append(f"not a Traditional Chinese (Big5) character: {ch}")
            continue
        try:
            enc = ch.encode("cp932")
        except UnicodeEncodeError:
            enc = b""
        if len(enc) != 2 or enc[0] not in (0x81, 0x82, 0x83, 0x84):
            errs.append(f"symbol not in the game font: {ch!r} (use full-width punctuation such as ，。！？「」…～・)")
    zl = zh.split("\n")
    if a == b:
        for i, (sj, sz) in enumerate(zip(segments(ja), segments(zh))):
            nj, nz = sj.count("\n") + 1, sz.count("\n") + 1
            if nz > nj:
                errs.append(f"page {i}: too many lines ({nz} > {nj}); never add a line break")
    limit = max(row.get("max_units", max_units(ja)), 8)
    if max_units(zh) > limit + 2:
        errs.append(f"line too wide ({max_units(zh)} > {limit} half-width units); rebalance lines")
    if "max_bytes" in row and enc_len(zh.replace("\n", " ")) > row["max_bytes"]:
        errs.append(f"too long for its field ({enc_len(zh)} > {row['max_bytes']} bytes); shorten")
    if "max_bytes_line" in row:
        for l in zl:
            if enc_len(l) > row["max_bytes_line"]:
                errs.append(f"line too long for its field ({enc_len(l)} > {row['max_bytes_line']} bytes)")
    return errs


def cmd_status():
    tot_n = tot_d = 0
    for fn in sorted(os.listdir(os.path.join(ROOT, "ja"))):
        name = fn[:-5]
        rows = src(name); zh = load(zh_path(name), {})
        done = sum(1 for r in rows if r["id"] in zh)
        tot_n += len(rows); tot_d += done
        if done < len(rows) or "-a" in sys.argv:
            print(f"{name:16} {done:5}/{len(rows):5}  {100*done/len(rows):5.1f}%")
    g = load(GLOSSARY, {}); tm = load(TM, {})
    print(f"{'TOTAL':16} {tot_d:5}/{tot_n:5}  {100*tot_d/max(tot_n,1):5.1f}%   glossary={len(g)} tm={len(tm)}")


def cmd_next(name, n=40):
    rows = src(name)
    with locked():
        zh = load(zh_path(name), {}); tm = load(TM, {})
        auto = 0
        for r in rows:
            k = r["id"]
            if k not in zh and (r["ja"] in tm or not JAPANESE.search(r["ja"])):
                zh[k] = tm.get(r["ja"], r["ja"]); auto += 1
        if auto:
            save(zh_path(name), zh)
    glossary = load(GLOSSARY, {})
    todo = [r for r in rows if r["id"] not in zh][:int(n)]
    terms, similar = {}, {}
    tm_keys = list(tm.keys())
    for r in todo:
        terms.update(glossary_hits(r["ja"], glossary))
        if len(r["ja"]) > 8:
            for m in difflib.get_close_matches(r["ja"], tm_keys, n=2, cutoff=0.7):
                similar[m] = tm[m]
    out = {
        "file": name, "auto_filled": auto,
        "remaining": sum(1 for r in rows if r["id"] not in zh),
        "glossary": {k: v["zh"] + (f"  ({v['note']})" if v.get("note") else "") for k, v in terms.items()},
        "similar_tm": similar,
        "strings": [{"id": r["id"], "ja": r["ja"], "max_units": max(r.get("max_units", 0), 8),
                     "lines": r.get("lines", r["ja"].count("\n") + 1),
                     **({k: r[k] for k in ("en", "speaker") if r.get(k)}),
                     **({"max_bytes": r["max_bytes"]} if "max_bytes" in r else {})} for r in todo],
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_commit(name, batch_path):
    batch = load(batch_path, None)
    items = batch["strings"] if isinstance(batch, dict) else batch
    terms = batch.get("terms", {}) if isinstance(batch, dict) else {}
    rows = {r["id"]: r for r in src(name)}
    ja = {k: r["ja"] for k, r in rows.items()}
    ok, bad = {}, []
    for it in items:
        k = str(it["id"])
        if k not in ja:
            bad.append((k, "unknown id")); continue
        errs = check(ja[k], it["zh"], rows[k])
        if errs:
            bad.append((k, "; ".join(errs)))
        else:
            ok[k] = it["zh"]
    with locked():
        zh = load(zh_path(name), {}); tm = load(TM, {}); g = load(GLOSSARY, {})
        zh.update(ok)
        for k, v in ok.items():
            tm[ja[k]] = v
        conflicts = []
        for t, v in terms.items():
            v = v if isinstance(v, dict) else {"zh": v}
            if t in g and g[t]["zh"] != v["zh"]:
                conflicts.append(f"{t}: glossary={g[t]['zh']} batch={v['zh']}")
                continue
            g[t] = {"zh": v["zh"], **({"note": v["note"]} if v.get("note") else {})}
        save(zh_path(name), zh); save(TM, tm); save(GLOSSARY, g)
    print(f"committed {len(ok)} strings, {len(terms) - len(conflicts)} terms")
    for k, e in bad:
        print(f"REJECTED {k}: {e}")
    for c in conflicts:
        print(f"TERM CONFLICT (kept glossary) {c}")


def cmd_lookup(text):
    g = load(GLOSSARY, {}); tm = load(TM, {})
    for k, v in g.items():
        if text in k or text in v["zh"]:
            print(f"[term] {k} => {v['zh']} {v.get('note', '')}")
    n = 0
    for k, v in tm.items():
        if text in k or text in v:
            print(f"[tm] {k!r} => {v!r}"); n += 1
            if n >= 20: break


def cmd_term(ja, zh, note=""):
    with locked():
        g = load(GLOSSARY, {})
        g[ja] = {"zh": zh, **({"note": note} if note else {})}
        save(GLOSSARY, g)
    print(f"{ja} => {zh}")


def cmd_check(name=None):
    names = [name] if name else [f[:-5] for f in sorted(os.listdir(os.path.join(ROOT, "ja")))]
    nbad = 0
    for nm in names:
        rows = {r["id"]: r for r in src(nm)}
        for k, v in load(zh_path(nm), {}).items():
            errs = check(rows[k]["ja"], v, rows[k]) if k in rows else ["unknown id"]
            if errs:
                nbad += 1; print(f"{nm} {k}: {'; '.join(errs)}")
    print(f"{nbad} problems")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd, *args = sys.argv[1:] or ["status"]
    args = [a for a in args if a != "-a"]
    {"status": cmd_status, "next": cmd_next, "commit": cmd_commit,
     "lookup": cmd_lookup, "term": cmd_term, "check": cmd_check}[cmd](*args)
