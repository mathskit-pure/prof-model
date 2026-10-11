# -*- coding: utf-8 -*-
"""对比不同方向组合对「模型页 Top24 排序」的复现度"""
import sys, re, itertools
import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

p = 'C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work/model/report.html'
s = open(p, encoding='utf-8').read()
i = s.find('三、最新一期 Top 持仓')
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', s[i:], flags=re.S)
recs = []
for r in rows:
    cells = re.findall(r'<t[dh][^>]*>(?:<!--.*?-->)?(.*?)</t[dh]>', r, flags=re.S)
    cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
    if len(cells) == 12 and cells[0].endswith(('.SH', '.SZ')):
        recs.append(cells)
cols = ['ts_code', 'score', 'prof', 'prof_chg', 'prof_stab', 'asset_growth',
        'net_issue', 'bm_ind', 'ep_ind', 'size', 'industry', 'total_mv']
df = pd.DataFrame(recs, columns=cols)
for c in cols[1:10]:
    df[c] = pd.to_numeric(df[c], errors='coerce')

fac = ['prof', 'prof_chg', 'prof_stab', 'asset_growth', 'net_issue', 'bm_ind', 'ep_ind', 'size']
W = dict(zip(fac, [0.35, 0.10, 0.10, 0.12, 0.08, 0.09, 0.06, 0.10]))
Z = (df[fac] - df[fac].mean()) / df[fac].std(ddof=0)
rank_true = df['score'].rank(ascending=False)

print('%-28s %-10s %s' % ('方向组合', 'Spearman', 'Kendall-ish'))
best = None
for sa, sn, ss in itertools.product([1, -1], repeat=3):
    sgn = {'prof': 1, 'prof_chg': 1, 'prof_stab': 1, 'asset_growth': sa,
           'net_issue': sn, 'bm_ind': 1, 'ep_ind': 1, 'size': ss}
    comp = sum(W[c] * sgn[c] * Z[c] for c in fac)
    rho = np.corrcoef(comp.rank(), rank_true)[0, 1]
    lab = 'ag=%+d ni=%+d size=%+d' % (sa, sn, ss)
    print('%-28s %+10.3f' % (lab, rho))
    if best is None or rho > best[1]:
        best = (lab, rho)
print('\n最优：', best)
