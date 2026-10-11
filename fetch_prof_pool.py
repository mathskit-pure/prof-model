# -*- coding: utf-8 -*-
"""
抓取「盈利能力评分模型」所需的全字段利润表 / 资产负债表 —— 仅针对季度股池成员中尚未抓取的部分。
输出：work/prof/income_all.csv, work/prof/balance_all.csv （追加式，可断点续跑）
"""
import subprocess, sys, os, time, json, re, csv
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

EXE = r"C:\Users\12066\.local\bin\westock.exe"
WORK = r"C:\Users\12066\WorkBuddy\2026-10-07-14-39-28\work"
PROF = os.path.join(WORK, "prof")
os.makedirs(PROF, exist_ok=True)

FILES = {"income": os.path.join(PROF, "income_all.csv"),
         "balance": os.path.join(PROF, "balance_all.csv")}
TITLE2KIND = {"利润表": "income", "资产负债表": "balance"}
PROGRESS_F = os.path.join(PROF, "progress_pool.json")
START, END = "2017-01-01", "2026-12-31"


def load_progress():
    if os.path.exists(PROGRESS_F):
        try:
            return json.load(open(PROGRESS_F, encoding="utf-8"))
        except Exception:
            pass
    return {"done": []}


def save_progress(p):
    tmp = PROGRESS_F + ".tmp"
    json.dump(p, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, PROGRESS_F)


def parse_tables(text):
    out = {}
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"\*\*(.+?)\*\*", text)]
    for idx, (pos, title) in enumerate(marks):
        kind = TITLE2KIND.get(title)
        if not kind:
            continue
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(text)
        lines = [ln.strip() for ln in text[pos:end].splitlines() if ln.strip().startswith("|")]
        if len(lines) < 2:
            continue
        header = [c.strip() for c in lines[0].strip("|").split("|")]
        rows = []
        for ln in lines[2:]:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) != len(header):
                continue
            rows.append(dict(zip(header, cells)))
        if rows:
            out[kind] = (header, rows)
    return out


def append_rows(kind, header, rows):
    path = FILES[kind]
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    if exists:
        with open(path, encoding="utf-8") as f:
            old = f.readline().rstrip("\n").split(",")
        if old != header:
            with open(path, encoding="utf-8") as f:
                body = list(csv.reader(f))[1:]
            union = list(old) + [h for h in header if h not in old]
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(union)
                for parts in body:
                    row = dict(zip(old, parts))
                    w.writerow([row.get(h, "") for h in union])
            header = union
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def run_batch(codes):
    cmd = [EXE, "finance", ",".join(codes), "--start", START, "--end", END, "--fields", "all"]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    txt = res.stdout.decode("utf-8", errors="replace")
    err = res.stderr.decode("utf-8", errors="replace")
    if "服务限频" in txt or "服务限频" in err:
        return None, "ratelimit"
    if not txt.strip():
        return None, "empty"
    return txt, None


def main():
    todo = json.load(open(os.path.join(WORK, "missing_codes.json"), encoding="utf-8"))
    prog = load_progress()
    done = set(prog["done"])
    todo = [c for c in todo if c not in done]
    batch, sleep_s = 6, 1.0
    fails = 0
    t0 = time.time()
    print(f"[start] todo={len(todo)}", flush=True)
    i = 0
    while i < len(todo):
        chunk = todo[i:i + batch]
        txt, err = run_batch(chunk)
        if err is not None:
            fails += 1
            prev = sleep_s
            sleep_s = min(90.0, sleep_s * 1.7)
            if fails % 4 == 0 and batch > 2:
                batch = max(2, batch - 2)
            print(f"[fail] {err} batch={batch} sleep {prev:.1f}->{sleep_s:.1f} done={len(done)}", flush=True)
            time.sleep(sleep_s)
            if fails > 400:
                print("[abort]", flush=True)
                break
            continue
        tables = parse_tables(txt)
        if not tables:
            fails += 1
            if batch > 1:
                batch = max(1, batch // 2)
                print(f"[nofmt] shrink batch={batch}", flush=True)
                continue
            i += len(chunk)
            continue
        for kind, (header, rows) in tables.items():
            append_rows(kind, header, rows)
        got = set()
        for _, (_, rows) in tables.items():
            for r in rows:
                if r.get("code"):
                    got.add(r["code"])
        if not got:
            got = set(chunk) if len(tables) == len(TITLE2KIND) else set()
        for c in got:
            if c not in done:
                done.add(c)
                prog["done"].append(c)
        save_progress(prog)
        print(f"[ok] got={len(got)} done={len(done)}/{len(todo)+len(done)} "
              f"batch={batch} eta={(len(todo)+len(done)-len(done)) * (time.time()-t0) / max(1,len(done)) / 60:.1f}min", flush=True)
        fails = 0
        if sleep_s > 1.0:
            sleep_s = max(1.0, sleep_s * 0.85)
        i += len(chunk)
        time.sleep(sleep_s)
    print(f"[done] fetched={len(done)}", flush=True)


if __name__ == "__main__":
    main()
