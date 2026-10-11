# -*- coding: utf-8 -*-
"""对 income_all / balance_all 按 (code, EndDate) 去重，保留字段最完整的一行；
并校验股池覆盖率。结果写入 .dedupe 临时文件，由调用方 mv 覆盖原文件。"""
import csv, json, os

WORK = r"C:\Users\12066\WorkBuddy\2026-10-07-14-39-28\work"
PROF = os.path.join(WORK, "prof")
INCOME = os.path.join(PROF, "income_all.csv")
BALANCE = os.path.join(PROF, "balance_all.csv")

NEED = ["OperatingExpense", "TotalAdminExpense", "FinancialExpense"]  # income 必需
BAL_NEED = ["TotalShareholderEquity"]                                  # balance 必需


def nonempty(v):
    return (v or "").strip() not in ("", "nan", "None")


def dedupe(path):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 0, 0, 0
    canon = list(rows[0].keys())
    groups = {}
    for r in rows:
        k = (r.get("code"), r.get("EndDate"))
        groups.setdefault(k, []).append(r)
    out, dups = [], 0
    for grp in groups.values():
        if len(grp) > 1:
            dups += len(grp) - 1
        # 保留非空字段最多的一行（完整行优先）
        best = max(grp, key=lambda r: sum(1 for v in r.values() if nonempty(v)))
        out.append(best)
    tmp = path + ".dedupe"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=canon, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    return len(rows), len(out), dups


def cov_count(path, req):
    s = set()
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c = (r.get("code") or "").strip()
            if not c:
                continue
            if req and not all(nonempty(r.get(x)) for x in req):
                continue
            s.add(c)
    return s


for p in (INCOME, BALANCE):
    before, after, dups = dedupe(p)
    print(f"{os.path.basename(p)}: before={before} after={after} removed_dups={dups}")

# 校验股池覆盖率
pool = set()
compact = json.loads(open(os.path.join(WORK, "pools_compact.json"), encoding="utf-8").read())
for end, v in compact.items():
    for m in v["members"]:
        pool.add(m["code"])

inc = cov_count(INCOME, NEED)
bal = cov_count(BALANCE, BAL_NEED)
both = inc & bal
print(f"pool={len(pool)} income(exp)={len(inc)} balance(TE)={len(bal)} both={len(both)} missing={len(pool-both)}")
if pool - both:
    print("MISSING:", sorted(pool - both)[:20])
