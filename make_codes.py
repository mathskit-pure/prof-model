# -*- coding: utf-8 -*-
"""生成待抓取代码清单：既有财务库 ∪ 季度股池成员"""
import sys, os, json
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

OLD = r"C:/Users/12066/WorkBuddy/2026-10-05-23-13-30"
BASE = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28"

codes = set()
for f in ["income.csv", "balance.csv", "cashflow.csv"]:
    p = os.path.join(OLD, "data", "raw", f)
    if os.path.exists(p):
        d = pd.read_csv(p, dtype=str, usecols=["code"])
        codes |= set(d["code"].dropna())
pool = json.load(open(os.path.join(OLD, "scripts", "codes_pool.json"), encoding="utf-8"))
codes |= set(pool)
codes = sorted(codes)
json.dump(codes, open(os.path.join(BASE, "work", "codes_prof.json"), "w", encoding="utf-8"),
          ensure_ascii=False)
print("codes:", len(codes), codes[:5], codes[-5:])
