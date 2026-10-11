# -*- coding: utf-8 -*-
import sys, os, json
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORK = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work"
PROF = os.path.join(WORK, "prof")

# 1) pool member codes
pools = json.load(open(os.path.join(WORK, "pools.json"), encoding="utf-8"))
pool_codes = set()
for k, v in pools.items():
    for m in v.get("members", []):
        pool_codes.add(m["code"])
print("pool quarters:", len(pools), "unique pool codes:", len(pool_codes))

# 2) already fetched
inc = pd.read_csv(os.path.join(PROF, "income_all.csv"), dtype=str, usecols=["code"])
bal = pd.read_csv(os.path.join(PROF, "balance_all.csv"), dtype=str, usecols=["code"])
got = set(inc["code"].dropna()) | set(bal["code"].dropna())
print("fetched codes (union):", len(got))

missing = sorted(pool_codes - got)
print("pool codes missing financials:", len(missing))
print("missing sample:", missing[:20])

# 3) sectors present
from collections import Counter
sw1 = Counter()
for k, v in pools.items():
    for m in v.get("members", []):
        sw1[m.get("sw1","?")] += 1
print("sw1 sectors:", len(sw1), "top:", sw1.most_common(8))

# 4) mktcap status
mc_path = os.path.join(PROF, "mktcap.csv")
if os.path.exists(mc_path):
    mc = pd.read_csv(mc_path, dtype=str)
    print("mktcap rows:", len(mc), "codes:", mc["code"].nunique(), "dates:", sorted(mc["date"].unique())[:6], "...", sorted(mc["date"].unique())[-3:])
else:
    print("mktcap.csv: NOT FOUND")

# 5) meta.json presence
meta_path = os.path.join(WORK, "meta.json")
print("meta.json exists:", os.path.exists(meta_path))
