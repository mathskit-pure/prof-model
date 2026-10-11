# -*- coding: utf-8 -*-
"""
盈利能力 Top40 等权回测 —— 标的池 = 舞弊调整质量因子季度动态股池。
选股与换仓规则与「质量Top20等权」完全一致（仅评分来源由 FAQ 换成 A 股盈利能力评分 PROF）：
  · 当期股池内按 PROF 综合得分降序取前 40 只；
  · 单个申万三级行业最多 2 只（出现第 3 只时跳过其中得分最低者并按序补录）；
  · 季度买入持有：只在季度股池更新日（信息可得日后的首个交易日）换仓并等权建仓；
  · 同一季度内不再平衡，权重随价格自然漂移，直到下个季度重新等权建仓；
  · 换仓同样权重滞后 1 日（T 日决策、T+1 日执行）。
回测自 2019-11-01 起。
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import WORK  # noqa: E402  路径：本机 Windows 与云端 Linux 通用

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROF = os.path.join(WORK, "prof")
PRICE_FILE = os.path.join(WORK, "prices_full_v2.csv")

LQ = 40            # 持仓数量
MAX_PER_IND_Q = 2  # 单申万三级行业最多 2 只
START = "2019-11-01"   # 用户指定回测起点
MIN_LISTED = 60        # 次新股过滤（与质量Top20一致）


def load():
    px = pd.read_csv(PRICE_FILE, dtype={"code": str})
    px["date"] = pd.to_datetime(px["date"])
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px = px.dropna(subset=["close"]).drop_duplicates(["code", "date"])
    close = px.pivot(index="date", columns="code", values="close").sort_index()

    scores = pd.read_csv(os.path.join(PROF, "prof_scores.csv"), dtype={"code": str})
    scores["PS_score"] = pd.to_numeric(scores["PS_score"], errors="coerce")
    scores = scores.dropna(subset=["PS_score"])
    sw3 = dict(zip(scores["code"], scores["sw3"]))
    name = dict(zip(scores["code"], scores["name"]))

    compact = json.loads(open(os.path.join(WORK, "pools_compact.json"), encoding="utf-8").read())
    tdays = pd.to_datetime(pd.Series([l.strip() for l in open(os.path.join(WORK, "tdays.txt"), encoding="utf-8") if l.strip()])).sort_values().reset_index(drop=True)

    asof = []
    score_by_period = {}
    for end, v in compact.items():
        a = pd.Timestamp(v["asof"])
        nxt = tdays[tdays >= a]
        d = str(nxt.iloc[0].date()) if len(nxt) else None
        asof.append((v["asof"], end))
        rows = scores[scores["报告期"] == end]
        score_by_period[end] = sorted(
            ((r["code"], float(r["PS_score"])) for _, r in rows.iterrows()),
            key=lambda x: -x[1])
    asof.sort()
    return close, sw3, name, asof, score_by_period


def active_period(d, asof):
    cur = None
    for a, period in asof:
        if pd.Timestamp(a) <= d:
            cur = period
    return cur


def select_by_score(d, asof, score_by_period, sw3, close, ok=None):
    """当期股池内按 PROF 得分降序 → 单行业最多 2 只 → 取前 LQ 只等权。
    同行业出现第 3 只时跳过（即剔除其中得分最低者）并继续按序补录。"""
    period = active_period(d, asof)
    if not period:
        return []
    cand = [(c, s) for c, s in score_by_period.get(period, [])
            if c in close.columns and (ok is None or c in ok)]
    picked, ind_cnt = [], {}
    for c, s in cand:                       # 已按得分降序排好
        if len(picked) >= LQ:
            break
        ind = sw3.get(c, "未分类")
        if ind_cnt.get(ind, 0) >= MAX_PER_IND_Q:
            continue                        # 第 3 只同行业 → 剔除（得分最低者）
        ind_cnt[ind] = ind_cnt.get(ind, 0) + 1
        picked.append(c)
    return picked


def perf(ret, label):
    ret = ret.dropna()
    if len(ret) == 0:
        return {}
    eq = (1 + ret).cumprod()
    n = len(ret)
    ann = eq.iloc[-1] ** (252 / n) - 1
    vol = ret.std(ddof=0) * np.sqrt(252)
    mdd = (eq / eq.cummax() - 1).min()
    sharpe = ann / vol if vol else np.nan
    calmar = ann / abs(mdd) if mdd else np.nan
    return {"组合": label, "累计收益": eq.iloc[-1] - 1, "年化收益": ann, "年化波动": vol,
            "最大回撤": mdd, "夏普比率": sharpe, "卡玛比率": calmar, "交易日数": n}


def main():
    close, sw3, name, asof, score_by_period = load()
    print("价格矩阵:", close.shape, close.index.min().date(), "→", close.index.max().date(), flush=True)
    print("评分覆盖报告期:", [k for k in score_by_period if score_by_period[k]], flush=True)

    ret = close.pct_change()
    listed = close.notna().cumsum()
    dates = close.index
    start_pos = int(np.searchsorted(dates.values, np.datetime64(START)))
    print(f"回测起点 {dates[start_pos].date()} | 总交易日 {len(dates)}", flush=True)

    def price_at(code, d):
        s = close[code]
        v = s.get(d, np.nan) if d in s.index else np.nan
        if pd.notna(v):
            return float(v)
        ss = s.loc[:d].dropna()
        return float(ss.iloc[-1]) if len(ss) else np.nan

    Wq = pd.DataFrame(0.0, index=dates, columns=close.columns)
    qual_rows, qual_removed = [], []
    prev_qw = pd.Series(0.0, index=close.columns)
    q_prev_set, q_entry_of = set(), {}
    last_q_period = None

    for pos in range(start_pos, len(dates)):
        d = dates[pos]
        per = active_period(d, asof)
        if per != last_q_period:                       # 新季度 → 换仓、等权重新建仓
            last_q_period = per
            ok_q = {c for c in close.columns
                    if listed.iloc[pos].get(c, 0) >= MIN_LISTED}
            qcodes = select_by_score(d, asof, score_by_period, sw3, close, ok_q)
            w = pd.Series(0.0, index=close.columns)
            if qcodes:
                w[qcodes] = 1.0 / len(qcodes)
            qset = set(qcodes)

            for c in sorted(q_prev_set - qset):
                e = q_entry_of.pop(c, None)
                p0 = price_at(c, e) if e is not None else np.nan
                p1 = price_at(c, d)
                chg = (p1 / p0 - 1) if (p0 and p1 and np.isfinite(p0) and np.isfinite(p1)) else np.nan
                qual_removed.append({"调仓日": d.date(), "代码": c, "名称": name.get(c, c),
                                     "申万三级": sw3.get(c, "未分类"),
                                     "建仓日": e.date() if e is not None else None,
                                     "区间涨跌幅": chg})

            smap = dict(score_by_period.get(per, []))
            for rank, c in enumerate(qcodes, 1):
                if c not in q_prev_set:
                    q_entry_of[c] = d
                qual_rows.append({"报告期": per, "调仓日": d.date(), "次序": rank,
                                  "代码": c, "名称": name.get(c, c),
                                  "申万三级": sw3.get(c, "未分类"),
                                  "PS得分": smap.get(c), "建仓权重": 1.0 / len(qcodes) if qcodes else 0,
                                  "状态": "新增" if c not in q_prev_set else "持有"})
            q_prev_set = qset
        else:                                          # 季度内不动，权重自然漂移
            r = ret.iloc[pos].reindex(close.columns).fillna(0.0)
            w = prev_qw * (1.0 + r)
            s = float(w.sum())
            w = (w / s) if s else prev_qw
        Wq.iloc[pos] = w.values
        prev_qw = w

    mask = dates >= pd.Timestamp(START)
    qual = (Wq.shift(1) * ret).sum(axis=1)[mask]

    summary = pd.DataFrame([perf(qual, "盈利能力Top40")])
    print("\n=== 绩效汇总 ===", flush=True)
    print(summary.to_string(index=False), flush=True)

    prof_top20 = pd.DataFrame(qual_rows)
    prof_removed = pd.DataFrame(qual_removed)
    prof_top20.to_csv(os.path.join(PROF, "prof_top40.csv"), index=False, encoding="utf-8-sig")
    prof_removed.to_csv(os.path.join(PROF, "prof_removed.csv"), index=False, encoding="utf-8-sig")
    summary.to_csv(os.path.join(PROF, "prof_summary.csv"), index=False, encoding="utf-8-sig")
    nav = pd.DataFrame({"盈利能力Top40": (1 + qual).cumprod()})
    nav.to_csv(os.path.join(PROF, "prof_nav.csv"), encoding="utf-8-sig")
    print(f"\n持仓明细 {len(qual_rows)} 行 · 剔除记录 {len(qual_removed)} 行", flush=True)
    print("已保存 prof_top40.csv / prof_removed.csv / prof_summary.csv / prof_nav.csv", flush=True)


if __name__ == "__main__":
    main()
