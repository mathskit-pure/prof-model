# -*- coding: utf-8 -*-
"""
A 股盈利能力评分模型（PROF）—— 仅对「舞弊调整质量因子 · 季度动态股池」内个股赋分。
理论来源：Novy-Marx & Medhat (2025, NBER WP 33601)
  PROF = (营业收入 − 营业成本 − 销售费用 − 管理费用(不含研发) − 利息费用) / (归母权益 + 少数股东权益)
八因子权重与方向严格依照资料库《A 股盈利能力评分模型》报告页：
  prof 0.35 +1 | prof_chg 0.10 +1 | prof_stab 0.10 +1 | asset_growth 0.12 −1
  net_issue 0.08 −1 | bm_ind 0.09 +1(申万一级行业中性) | ep_ind 0.06 +1(申万一级行业中性) | size 0.10 −1
截面标准化：1%/99% 缩尾 →（价值因子先做申万一级行业中位数中心化）→ z-score → ±3 截尾
综合分按权重加权，缺失因子按剩余权重归一化（与报告页口径一致）
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import WORK  # noqa: E402  路径：本机 Windows 与云端 Linux 通用

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROF = os.path.join(WORK, "prof")

FIRST_PERIOD = "2019-03-31"   # 与股池口径一致，从一季报开始

# 因子 → (权重, 方向)
FACTORS = {
    "prof":         (0.35, +1),
    "prof_chg":     (0.10, +1),
    "prof_stab":    (0.10, +1),
    "asset_growth": (0.12, -1),
    "net_issue":    (0.08, -1),
    "bm_ind":       (0.09, +1),
    "ep_ind":       (0.06, +1),
    "size":         (0.10, -1),
}
IND_NEUTRAL = {"bm_ind", "ep_ind"}
NUM = lambda s: pd.to_numeric(s, errors="coerce")


def load_raw():
    inc = pd.read_csv(os.path.join(PROF, "income_all.csv"), dtype=str,
                      engine="python", on_bad_lines="skip")
    bal = pd.read_csv(os.path.join(PROF, "balance_all.csv"), dtype=str,
                      engine="python", on_bad_lines="skip")
    for d in (inc, bal):
        d["EndDate"] = d["EndDate"].astype(str).str.strip()
        d["code"] = d["code"].astype(str).str.strip()
        d["key"] = d["code"] + "|" + d["EndDate"]
    inc = inc.drop_duplicates("key").set_index("key")
    bal = bal.drop_duplicates("key").set_index("key")
    return inc, bal


def col(df, n):
    return NUM(df[n]) if n in df.columns else pd.Series(np.nan, index=df.index)


def build(pool_codes):
    inc, bal = load_raw()
    # 仅保留股池成员，减少计算量并让截面 z-score 在股池内计算
    inc = inc[inc.index.map(lambda k: k.split("|")[0] in pool_codes)]
    bal = bal[bal.index.map(lambda k: k.split("|")[0] in pool_codes)]
    idx = sorted(set(inc.index) | set(bal.index))
    p = pd.DataFrame(index=pd.MultiIndex.from_tuples(
        [tuple(k.split("|")) for k in idx], names=["code", "EndDate"]))

    for src, dst in [("TotalOperatingRevenue", "rev"), ("OperatingCost", "cogs"),
                     ("OperatingExpense", "sell"), ("TotalAdminExpense", "admin"),
                     ("FinancialExpense", "fin"), ("RAndD", "rd"),
                     ("NPParentCompanyOwnersTTM", "ni_ttm")]:
        p[dst] = col(inc, src).reindex(idx).values
    for src, dst in [("TotalShareholderEquity", "be"), ("SEWithoutMI", "se"),
                     ("InterestBearDebt", "ibd"), ("RetainedProfit", "re"),
                     ("TotalCurrentAssets", "ca"), ("TotalNonCurrentAssets", "nca")]:
        p[dst] = col(bal, src).reindex(idx).values

    p = p.reset_index()
    p["pdate"] = pd.to_datetime(p["EndDate"])
    p["total_assets"] = p["ca"] + p["nca"]
    return p.sort_values(["code", "pdate"]).reset_index(drop=True)


def ttm_series(g, c):
    s = g.set_index("pdate")[c]
    if s.notna().sum() == 0:
        return pd.Series(np.nan, index=g.index)
    out = {}
    for d in s.index:
        v = s.get(d, np.nan)
        if pd.isna(v):
            out[d] = np.nan
            continue
        fy_prev = pd.Timestamp(year=d.year - 1, month=12, day=31)
        same_prev = pd.Timestamp(year=d.year - 1, month=d.month, day=d.day)
        a = s.get(fy_prev, np.nan)
        b = s.get(same_prev, np.nan)
        out[d] = v + a - b if (pd.notna(a) and pd.notna(b)) else np.nan
    return pd.Series(out).reindex(g["pdate"]).values


def add_factors(p):
    p = p.copy()
    ttm_cols = ["rev", "cogs", "sell", "admin", "fin"]
    for c in ttm_cols:
        p[c + "_ttm"] = np.nan
    p["ni_ttm_v"] = np.nan
    for code, g in p.groupby("code", sort=False):
        gi = g.index
        for c in ttm_cols:
            p.loc[gi, c + "_ttm"] = ttm_series(g, c)
        p.loc[gi, "ni_ttm_v"] = g["ni_ttm"].values

    be = p["be"].astype(float)
    num = (p["rev_ttm"] - p["cogs_ttm"] - p["sell_ttm"] - p["admin_ttm"] - p["fin_ttm"])
    p["prof"] = np.where(be > 0, num / be, np.nan)

    g = p.groupby("code", sort=False)
    p["prof_y"] = g["prof"].shift(4)
    p["prof_chg"] = p["prof"] - p["prof_y"]

    def stab(x):
        v = pd.Series(x).dropna()
        if len(v) < 6:
            return np.nan
        sd = v.std(ddof=0)
        return v.mean() / sd if sd and sd > 1e-12 else np.nan
    p["prof_stab"] = (g["prof"]
                      .rolling(8, min_periods=6)
                      .apply(stab, raw=True)
                      .reset_index(level=0, drop=True))

    ta = p["total_assets"].astype(float)
    p["ta_y"] = g["total_assets"].shift(4)
    p["asset_growth"] = np.where((p["ta_y"] > 0) & (ta > 0), np.log(ta / p["ta_y"]), np.nan)

    d_se = p["be"] - g["be"].shift(4)
    d_re = p["re"] - g["re"].shift(4)
    d_ibd = p["ibd"] - p["ibd"].shift(4)
    external = d_se.fillna(0) - d_re.fillna(0) + d_ibd.fillna(0)
    p["net_issue"] = np.where(ta > 0, external / ta, np.nan)
    return p


def zs(s, ind=None):
    s = pd.to_numeric(s, errors="coerce")
    if s.notna().sum() < 10:
        return pd.Series(np.nan, index=s.index)
    lo, hi = s.quantile(0.01), s.quantile(0.99)
    s = s.clip(lo, hi)
    if ind is not None:
        s = s - s.groupby(ind).transform("median")
    mu, sd = s.mean(), s.std(ddof=0)
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=s.index)
    return ((s - mu) / sd).clip(-3, 3)


def main():
    compact = json.loads(open(os.path.join(WORK, "pools_compact.json"), encoding="utf-8").read())
    tdays = pd.to_datetime(pd.Series([l.strip() for l in open(os.path.join(WORK, "tdays.txt"), encoding="utf-8") if l.strip()])).sort_values().reset_index(drop=True)
    pool_codes = set()
    # 报告期 → 该期股池成员 & asof 交易日
    period_members, period_date = {}, {}
    for end, v in compact.items():
        a = pd.Timestamp(v["asof"])
        nxt = tdays[tdays >= a]
        d = str(nxt.iloc[0].date()) if len(nxt) else None
        period_members[end] = {m["code"]: m for m in v["members"]}
        period_date[end] = d
        for m in v["members"]:
            pool_codes.add(m["code"])
    print("pool codes:", len(pool_codes), flush=True)

    p = build(pool_codes)
    p = add_factors(p)
    print("panel:", p.shape, "codes:", p["code"].nunique(), flush=True)

    # 市值快照
    mc = pd.DataFrame()
    mc_path = os.path.join(PROF, "mktcap.csv")
    if os.path.exists(mc_path):
        mc = pd.read_csv(mc_path, dtype=str)
        mc["total_market_cap"] = NUM(mc["total_market_cap"])
        mc = mc.dropna(subset=["total_market_cap"]).drop_duplicates(["code", "date"])
    print("mktcap rows:", len(mc), flush=True)

    rows = []
    for end in sorted(period_members, reverse=False):
        if end < FIRST_PERIOD:
            continue
        mem = period_members[end]
        d = period_date[end]
        sub = p[p["EndDate"] == end]
        if sub.empty:
            print("skip (no financials):", end, flush=True)
            continue
        sub = sub[sub["code"].isin(mem)]
        if sub.empty:
            continue
        # 市值
        if len(mc):
            m = mc.set_index(["code", "date"])["total_market_cap"]
            sub = sub.copy()
            sub["mktcap"] = [m.get((c, d), np.nan) for c, d in zip(sub["code"], [d] * len(sub))]
        else:
            sub["mktcap"] = np.nan
        sub["bm"] = np.where(sub["mktcap"] > 0, sub["se"] / sub["mktcap"], np.nan)
        sub["ep"] = np.where(sub["mktcap"] > 0, sub["ni_ttm_v"] / sub["mktcap"], np.nan)
        sub["size"] = np.where(sub["mktcap"] > 0, np.log(sub["mktcap"]), np.nan)
        sub["sw1"] = sub["code"].map(lambda c: mem[c].get("sw1") or "未分类")
        sub["sw3"] = sub["code"].map(lambda c: mem[c].get("sw3") or "未分类")
        sub["name"] = sub["code"].map(lambda c: mem[c].get("name") or c)

        RAW = {"prof": "prof", "prof_chg": "prof_chg", "prof_stab": "prof_stab",
               "asset_growth": "asset_growth", "net_issue": "net_issue",
               "bm_ind": "bm", "ep_ind": "ep", "size": "size"}
        Z = {}
        for f in FACTORS:
            s = pd.to_numeric(sub[RAW[f]], errors="coerce")
            Z[f] = zs(s, sub["sw1"] if f in IND_NEUTRAL else None)

        score = pd.Series(0.0, index=sub.index)
        wsum = pd.Series(0.0, index=sub.index)
        for f, (w, d_) in FACTORS.items():
            v = Z[f]
            ok = v.notna()
            score[ok] += d_ * w * v[ok]
            wsum[ok] += w
        sub["PS_score"] = np.where(wsum > 0, score / wsum, np.nan)
        sub["PS_w"] = wsum
        sub["报告期"] = end
        sub["调仓日"] = d
        for f in FACTORS:
            sub["Z_" + f] = Z[f].values
        rows.append(sub)
        print(f"scored {end} ({d}) members={len(sub)} scoreN={sub['PS_score'].notna().sum()}", flush=True)

    out = pd.concat(rows, ignore_index=True)
    keep = (["报告期", "调仓日", "code", "name", "sw1", "sw3", "mktcap", "PS_score", "PS_w"]
            + ["prof", "prof_chg", "prof_stab", "asset_growth", "net_issue", "bm", "ep", "size"]
            + ["Z_" + f for f in FACTORS])
    out = out[keep].sort_values(["报告期", "PS_score"], ascending=[True, False])
    outpath = os.path.join(PROF, "prof_scores.csv")
    out.to_csv(outpath, index=False, encoding="utf-8-sig")
    print("\n写出:", outpath, out.shape, flush=True)
    print(out.groupby("报告期")["PS_score"].agg(["count", "mean"]).to_string(), flush=True)
    cov = out[["prof", "prof_chg", "prof_stab", "asset_growth", "net_issue", "bm", "ep", "size"]].notna().mean()
    print("\n因子覆盖率:\n", cov.to_string(), flush=True)
    return out


if __name__ == "__main__":
    main()
