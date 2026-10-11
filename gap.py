# -*- coding: utf-8 -*-
import sys, os, json
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORK = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work"
PROF = os.path.join(WORK, "prof")

compact = json.loads(open(os.path.join(WORK, "pools_compact.json"), encoding="utf-8").read())
pool_codes = set()
for v in compact.values():
    for m in v["members"]:
        pool_codes.add(m["code"])
print("pool codes:", len(pool_codes))

inc = pd.read_csv(os.path.join(PROF, "income_all.csv"), dtype=str, usecols=["code"])
bal = pd.read_csv(os.path.join(PROF, "balance_all.csv"), dtype=str, usecols=["code"])
got = set(inc["code"].dropna()) | set(bal["code"].dropna())
print("fetched union:", len(got))

# overlap with pool
in_pool_and_got = pool_codes & got
missing = sorted(pool_codes - got)
print("pool codes already fetched:", len(in_pool_and_got))
print("pool codes MISSING financials:", len(missing))
print("missing sample:", missing[:25])

# mktcap status
mc = os.path.join(PROF, "mktcap.csv")
if os.path.exists(mc):
    m = pd.read_csv(mc, dtype=str)
    print("mktcap rows:", len(m), "codes:", m["code"].nunique(), "dates:", m["date"].nunique())
else:
    print("mktcap.csv NOT FOUND")

# save missing list
json.dump(missing, open(os.path.join(WORK, "missing_codes.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("saved missing_codes.json")
