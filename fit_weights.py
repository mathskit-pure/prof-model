# -*- coding: utf-8 -*-
"""从「A 股盈利能力评分模型」页面的最新一期 Top 持仓表反推各因子方向。"""
import sys, re
import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

p = 'C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work/model/report.html'
s = open(p, encoding='utf-8').read()
i = s.find('三、最新一期 Top 持仓')
seg = s[i:]
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', seg, flags=re.S)
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
print(df.to_string(index=False))
print()
fac = ['prof', 'prof_chg', 'prof_stab', 'asset_growth', 'net_issue', 'bm_ind', 'ep_ind', 'size']
for c in fac:
    rho = np.corrcoef(df['score'].rank(), df[c].rank())[0, 1]
    print('%-13s spearman vs score = %+.3f' % (c, rho))

# 标准化后做最小二乘（含截距），看符号
Z = df[fac].copy()
Z = (Z - Z.mean()) / Z.std(ddof=0)
X = np.column_stack([np.ones(len(Z))] + [Z[c].values for c in fac])
y = df['score'].values
beta, *_ = np.linalg.lstsq(X, y, rcond=None)
print('\nOLS 系数（标准化因子，因变量 score）：')
for c, b in zip(['const'] + fac, beta):
    print('  %-13s %+8.3f' % (c, b))
print('\nR2 =', 1 - ((y - X @ beta) ** 2).sum() / ((y - y.mean()) ** 2).sum())
