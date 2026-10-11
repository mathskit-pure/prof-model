# -*- coding: utf-8 -*-
import json, csv
from collections import Counter

W = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work"

def uniq_codes(path, codecol="code"):
    s = set()
    with open(path, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            c = (row.get(codecol) or "").strip()
            if c:
                s.add(c)
    return s

pool = json.loads(open(W + "/pools_compact.json", encoding="utf-8").read())
pool_codes = set()
for end, v in pool.items():
    for m in v["members"]:
        pool_codes.add(m["code"])
print("pool codes total:", len(pool_codes))
print("periods:", len(pool))

inc = uniq_codes(W + "/prof/income_all.csv")
bal = uniq_codes(W + "/prof/balance_all.csv")
print("income_all unique:", len(inc))
print("balance_all unique:", len(bal))

# how many POOL codes covered
inc_pool = pool_codes & inc
bal_pool = pool_codes & bal
print("pool codes in income_all:", len(inc_pool))
print("pool codes in balance_all:", len(bal_pool))
print("pool codes MISSING from income_all:", len(pool_codes - inc))
print("pool codes MISSING from balance_all:", len(pool_codes - bal))

# mktcap periods
mc = set()
with open(W + "/prof/mktcap.csv", encoding="utf-8") as f:
    r = csv.DictReader(f)
    cols = r.fieldnames
    for row in r:
        mc.add(row.get("date"))
print("mktcap cols:", cols)
print("mktcap distinct dates:", len(mc), sorted(mc)[:5], "...", sorted(mc)[-3:])

# asof dates needed (first trading day after info-available) per period
import datetime
tdays = [l.strip() for l in open(W + "/tdays.txt", encoding="utf-8") if l.strip()]
tdays = sorted(tdays)
need_dates = set()
for end, v in pool.items():
    a = v["asof"]
    nxt = [t for t in tdays if t >= a]
    if nxt:
        need_dates.add(nxt[0])
print("asof first-trading-days needed:", len(need_dates))
print("mktcap missing dates:", sorted(need_dates - mc))
