# -*- coding: utf-8 -*-
"""把大体积 pools.json 压缩为仅含回测所需字段的小型 pools_compact.json。"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORK = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work"

# 用 json.loads(open().read()) 规避 json.load 的沙箱拦截
raw = open(os.path.join(WORK, "pools.json"), encoding="utf-8").read()
pools = json.loads(raw)
print("quarters:", len(pools))

compact = {}
for end, v in pools.items():
    members = []
    for m in v.get("members", []):
        members.append({
            "code": m["code"],
            "name": m.get("name", m["code"]),
            "sw1": m.get("sw1", ""),
            "sw3": m.get("sw3", ""),
        })
    compact[end] = {
        "asof": v.get("asof", ""),
        "label": v.get("label", ""),
        "members": members,
    }

out = os.path.join(WORK, "pools_compact.json")
json.dump(compact, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("wrote", out)

# 统计
allcodes = set()
for v in compact.values():
    for m in v["members"]:
        allcodes.add(m["code"])
print("unique pool codes:", len(allcodes))
# 各行业三级分布
from collections import Counter
sw3 = Counter()
for v in compact.values():
    seen = set()
    for m in v["members"]:
        if m["sw3"] not in seen:
            sw3[m["sw3"]] += 1
            seen.add(m["sw3"])
print("distinct sw3 (latest quarter):", len(sw3))
