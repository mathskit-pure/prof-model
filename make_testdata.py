# -*- coding: utf-8 -*-
import os
import pandas as pd
PROF = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work/prof"
rows = []
for rep, day in [("2019-09-30", "2019-11-01"), ("2019-12-31", "2020-05-06")]:
    for k in range(1, 21):
        rows.append({"报告期": rep, "调仓日": day, "次序": k,
                     "代码": "sh60%04d" % (1000 + k), "名称": "测试%d" % k,
                     "申万三级": "行业%d" % (k % 5), "PS得分": round(1.0 - k * 0.02, 3),
                     "建仓权重": 0.05, "状态": "新增" if k <= 3 else "持有"})
pd.DataFrame(rows).to_csv(os.path.join(PROF, "prof_top20.csv"), index=False, encoding="utf-8-sig")
rm = [{"调仓日": "2020-05-06", "代码": "sh601000", "名称": "剔除A", "申万三级": "行业1",
       "建仓日": "2019-11-01", "区间涨跌幅": 0.123}]
pd.DataFrame(rm).to_csv(os.path.join(PROF, "prof_removed.csv"), index=False, encoding="utf-8-sig")
pd.DataFrame([{"组合": "盈利能力Top20等权", "累计收益": 0.85, "年化收益": 0.18, "年化波动": 0.22,
               "最大回撤": -0.21, "夏普比率": 0.82, "卡玛比率": 0.86, "交易日数": 1600}]).to_csv(
    os.path.join(PROF, "prof_summary.csv"), index=False, encoding="utf-8-sig")
print("synthetic csv written")
