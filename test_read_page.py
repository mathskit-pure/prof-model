# -*- coding: utf-8 -*-
import os
p = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work/pool/pool_page.html"
print("exists", os.path.exists(p), "size", os.path.getsize(p))
try:
    with open(p, encoding="utf-8", errors="replace") as f:
        head = f.read(2000)
    print("open().read head OK, len sample", len(head))
    # locate anchors via streaming search (no full load needed)
    import re
    targets = ["4.2　质量Top20等权组合", "4.1　动量轮动策略", "五、如何更新最新一季股池", "四、持仓变动明细"]
    with open(p, encoding="utf-8", errors="replace") as f:
        pos = 0
        found = {t: -1 for t in targets}
        for line in f:
            for t in targets:
                if found[t] < 0 and t in line:
                    found[t] = pos
            pos += len(line)
    print("anchor positions:", found)
except Exception as e:
    print("ERROR", type(e).__name__, e)
