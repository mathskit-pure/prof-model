# -*- coding: utf-8 -*-
"""Rebuild balance_all.csv: prefer fetched rows (include RetainedProfit) for codes
already covered, fill the rest from OLD cached balance.csv (5 of 6 PROF fields).
Dedup at (code, EndDate), preferring the row that has TotalShareholderEquity."""
import csv, os, json

WORK = r"C:\Users\12066\WorkBuddy\2026-10-07-14-39-28\work"
PROF = os.path.join(WORK, "prof")
OLD_BAL = r"C:\Users\12066\WorkBuddy\2026-10-05-23-13-30\data\raw\balance.csv"
BAL = os.path.join(PROF, "balance_all.csv")


def load_pool():
    p = json.loads(open(os.path.join(WORK, "pools_compact.json"), encoding="utf-8").read())
    s = set()
    for end, v in p.items():
        for m in v["members"]:
            s.add(m["code"])
    return s


def main():
    pool = load_pool()

    # 1) fetched balance rows (current balance_all.csv) keyed by (code, EndDate)
    fetched = {}
    bal_header = None
    if os.path.exists(BAL) and os.path.getsize(BAL) > 0:
        with open(BAL, encoding="utf-8") as f:
            r = csv.DictReader(f)
            bal_header = r.fieldnames
            for row in r:
                c = (row.get("code") or "").strip()
                if not c:
                    continue
                ed = row.get("EndDate") or row.get("end_date") or ""
                fetched[(c, ed)] = row

    # 2) OLD balance rows keyed by (code, EndDate)
    old = {}
    old_header = None
    with open(OLD_BAL, encoding="utf-8") as f:
        r = csv.DictReader(f)
        old_header = r.fieldnames
        for row in r:
            c = (row.get("code") or "").strip()
            if c not in pool:
                continue
            ed = row.get("EndDate") or row.get("end_date") or ""
            old[(c, ed)] = row

    # 3) union header
    union = list(bal_header) if bal_header else list(old_header)
    for c in old_header:
        if c not in union:
            union.append(c)

    # 4) build preferred rows per (code, EndDate)
    keys = set(fetched) | set(old)
    # restrict to pool
    chosen = {}
    for (c, ed) in keys:
        if c not in pool:
            continue
        fr = fetched.get((c, ed))
        ol = old.get((c, ed))
        # prefer fetched if it has TotalShareholderEquity, else OLD, else fetched
        if fr and (fr.get("TotalShareholderEquity") or "").strip() not in ("", "nan", "None"):
            chosen[(c, ed)] = fr
        elif ol and (ol.get("TotalShareholderEquity") or "").strip() not in ("", "nan", "None"):
            chosen[(c, ed)] = ol
        elif fr:
            chosen[(c, ed)] = fr
        elif ol:
            chosen[(c, ed)] = ol

    # 5) write
    tmp = BAL + ".merge_tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=union, extrasaction="ignore")
        w.writeheader()
        for (c, ed) in sorted(chosen):
            w.writerow(chosen[(c, ed)])

    # stats
    cov_te = sum(1 for row in chosen.values()
                 if (row.get("TotalShareholderEquity") or "").strip() not in ("", "nan", "None"))
    cov_rp = sum(1 for row in chosen.values()
                 if (row.get("RetainedProfit") or "").strip() not in ("", "nan", "None"))
    codes_covered = len(set(c for (c, ed) in chosen))
    os.replace(tmp, BAL)
    print(f"balance_all.csv rebuilt: rows={len(chosen)} pool_codes={codes_covered}/560")
    print(f"  with TotalShareholderEquity={cov_te}, with RetainedProfit={cov_rp}")


if __name__ == "__main__":
    main()
