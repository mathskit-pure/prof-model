# -*- coding: utf-8 -*-
"""三条流水线的数据一致性巡检（只读，不写任何数据、不碰页面）。

三条定时任务（AFGI 07:30 / 主刷新 08:40 / PROF 09:40，均为 T+1 处理 T 日）
彼此靠文件耦合，任一环节漏跑都会在页面上表现为「某条曲线不往前走」。
本脚本把各数据源的最新日期摊平对比，不一致或超出容许滞后时给出告警。

容许滞后（tolerance）：
  PROF 排在「主刷新」之后，页面上的盈利能力 Top40 曲线要等下一轮主刷新才会
  画上去，因此 PROF 两个源天然比主流水线落后 1 个交易日 —— 这是流水线顺序
  决定的正常现象，不算故障；落后 ≥2 个交易日才告警。

用法：
  python healthcheck.py            # 打印体检表，退出码 0 正常 / 1 有告警
"""
import os
import sys
import json
import datetime as dt

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MAIN = r"C:/Users/12066/WorkBuddy/2026-10-05-23-13-30"
PROF = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work"
AFGI = r"C:/Users/12066/WorkBuddy/2026-10-05-14-50-58/afgi_tdx"


def csv_last_date(path, date_col=0):
    """取 csv 最后一行的日期字段（这些文件均按日期升序追加）。"""
    if not os.path.exists(path):
        return None
    last = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) > date_col:
                last = parts[date_col].lstrip("\ufeff").strip()
    return last


def load_trading_days():
    """用主项目回测净值 nav.csv 的日期列当交易日历（真实交易日，含最新一天）。"""
    p = os.path.join(MAIN, "data", "nav.csv")
    days = []
    if not os.path.exists(p):
        return days
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.split(",")[0].lstrip("\ufeff").strip()
            if len(s) == 10 and s[4] == "-":
                days.append(s)
    return days


def trading_gap(newer, older, days):
    """older 落后 newer 几个交易日（同日 = 0）；无法判定时返回 None。"""
    if not days:
        return None
    try:
        i = days.index(newer)
        j = days.index(older)
    except ValueError:
        return None
    return max(i - j, 0)


def pools_last_period():
    p = os.path.join(MAIN, "data", "pools.json")
    try:
        d = json.load(open(p, encoding="utf-8"))
        return max(d.keys())
    except Exception:
        return None


def expected_next_pool():
    """按 5/1→一季报、9/1→中报、11/1→三季报 推断下一个应出现的报告期与信息可得日。"""
    today = dt.date.today()
    y = today.year
    # (触发月, 报告期截止日) —— 信息可得日 = 触发月 1 号
    marks = [(5, dt.date(y, 3, 31)), (9, dt.date(y, 6, 30)), (11, dt.date(y, 9, 30))]
    for m, end in marks:
        if today < dt.date(y, m, 1):
            return str(end), str(dt.date(y, m, 1))
    return str(dt.date(y + 1, 3, 31)), str(dt.date(y + 1, 5, 1))


def main():
    today = dt.date.today()
    # （名称, 最新日期, 容许落后的交易日数）
    # PROF 排在主刷新之后，天然落后 1 个交易日，容差设为 1
    rows = [
        ("主项目回测净值 nav.csv", csv_last_date(os.path.join(MAIN, "data", "nav.csv")), 0),
        ("主项目 hfq 行情 prices_full_v2.csv",
         csv_last_date(os.path.join(MAIN, "data", "prices_full_v2.csv"), 1), 0),
        ("AFGI 情绪指数 afgi_timeseries.csv",
         csv_last_date(os.path.join(AFGI, "output", "afgi_timeseries.csv")), 0),
        ("AFGI 仓位组合净值 afgi_combo_nav.csv",
         csv_last_date(os.path.join(MAIN, "data", "afgi_combo_nav.csv")), 0),
        ("PROF 回测净值 prof_nav.csv",
         csv_last_date(os.path.join(PROF, "prof", "prof_nav.csv")), 1),
        ("PROF 本地行情副本 prices_full_v2.csv",
         csv_last_date(os.path.join(PROF, "prices_full_v2.csv"), 1), 1),
    ]
    tdays = load_trading_days()

    print("数据一致性巡检  ·  今天 %s" % today)
    print("-" * 62)
    print("%-38s %s" % ("数据源", "最新日期"))
    print("-" * 62)
    dates = []
    for name, d, _tol in rows:
        print("%-38s %s" % (name, d or "缺失"))
        if d:
            dates.append(d)
    print("-" * 62)

    warn = []

    if not dates:
        warn.append("所有数据源均缺失")
    else:
        newest = max(dates)
        oldest = min(dates)
        print("最新 = %s   最旧 = %s" % (newest, oldest))
        for name, d, tol in rows:
            if not d:
                continue
            gap = trading_gap(newest, d, tdays)
            if gap is None:          # 交易日历里查不到，退化为严格比对
                if d != newest:
                    warn.append("%s 落后于最新日期（%s vs %s）—— 该曲线/数据已停止更新"
                                % (name, d, newest))
                continue
            if gap <= tol:
                if gap:
                    print("  · %s 落后 %d 个交易日（%s）—— 流水线顺序决定的正常滞后"
                          % (name, gap, d))
                continue
            warn.append("%s 落后 %d 个交易日（%s vs %s）—— 超出容许的 %d 个交易日，"
                        "该曲线/数据可能已停止更新" % (name, gap, d, newest, tol))

        # 阈值放宽到 12 天：国庆 / 春节等长假期间休市属正常，不应误报
        lag = (today - dt.date.fromisoformat(newest)).days
        if lag > 12:
            warn.append("全部数据最新日期 %s 距今 %d 天，流水线可能已停摆" % (newest, lag))

    last_pool = pools_last_period()
    nxt, asof = expected_next_pool()
    print("季度股池最新报告期 = %s   下一个 = %s（信息可得日 %s）" % (last_pool, nxt, asof))
    if last_pool and last_pool < nxt and today >= dt.date.fromisoformat(asof):
        warn.append("已过信息可得日 %s，股池仍缺 %s 报告期——季度任务可能失败，需人工补跑"
                    % (asof, nxt))

    print("-" * 62)
    if warn:
        print("发现 %d 项告警：" % len(warn))
        for w in warn:
            print("  ! " + w)
        return 1
    print("全部一致，无告警")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
