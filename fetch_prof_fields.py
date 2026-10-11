# -*- coding: utf-8 -*-
"""
抓取「A 股盈利能力评分模型」所需的全字段利润表 / 资产负债表。

相比既有 data/raw/*.csv（core 窄表），本脚本额外需要：
  利润表：OperatingExpense(销售费用)、TotalAdminExpense(管理费用)、
          FinancialExpense(财务费用)、RAndD(研发)、InfoPublDate(公告日)
  资产负债表：TotalShareholderEquity、SEWithoutMI、InterestBearDebt、
          RetainedProfit(未分配利润)、NAPS

输出：data/prof/income_all.csv, data/prof/balance_all.csv
"""
import subprocess, sys, os, time, json, re, csv

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

EXE = r"C:\Users\12066\.local\bin\westock.exe"
BASE = r"C:\Users\12066\WorkBuddy\2026-10-07-14-39-28"
OUT_DIR = os.path.join(BASE, "work", "prof")
os.makedirs(OUT_DIR, exist_ok=True)

FILES = {"income": os.path.join(OUT_DIR, "income_all.csv"),
         "balance": os.path.join(OUT_DIR, "balance_all.csv")}
TITLE2KIND = {"利润表": "income", "资产负债表": "balance"}

PROGRESS_F = os.path.join(OUT_DIR, "progress.json")
START, END = "2018-01-01", "2026-12-31"


def load_progress():
    if os.path.exists(PROGRESS_F):
        with open(PROGRESS_F, encoding="utf-8") as f:
            return json.load(f)
    return {"done": [], "failed": {}}


def save_progress(p):
    tmp = PROGRESS_F + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False)
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
    cmd = [EXE, "finance", ",".join(codes), "--start", START, "--end", END,
           "--fields", "all"]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=240)
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
    codes = json.load(open(os.path.join(BASE, "work", "codes_prof.json"), encoding="utf-8"))
    prog = load_progress()
    done = set(prog["done"])
    todo = [c for c in codes if c not in done]
    batch, sleep_s = 8, 1.0
    fails = 0
    t0 = time.time()
    print(f"[start] total={len(codes)} todo={len(todo)}", flush=True)
    i = 0
    while i < len(todo):
        chunk = todo[i:i + batch]
        txt, err = run_batch(chunk)
        if err is not None:
            fails += 1
            prev = sleep_s
            sleep_s = min(60.0, sleep_s * 1.8)
            if fails % 3 == 0 and batch > 2:
                batch = max(2, batch - 2)
            print(f"[fail] {err} batch={batch} sleep {prev:.1f}->{sleep_s:.1f} done={len(prog['done'])}", flush=True)
            time.sleep(sleep_s)
            if fails > 150:
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
            prog["failed"].pop(c, None)
            if c not in prog["done"]:
                prog["done"].append(c)
        save_progress(prog)
        print(f"[ok] got={len(got)} done={len(prog['done'])}/{len(codes)} "
              f"batch={batch} eta={ (len(codes)-len(prog['done'])) * (time.time()-t0) / max(1,len(prog['done'])) / 60:.1f}min", flush=True)
        fails = 0
        if sleep_s > 1.0:
            sleep_s = max(1.0, sleep_s * 0.85)
        i += len(chunk)
        time.sleep(sleep_s)
    print(f"[done] fetched={len(prog['done'])}", flush=True)


if __name__ == "__main__":
    main()
