# -*- coding: utf-8 -*-
"""
抓取各报告期「信息可得日后的首个交易日」的历史市值 / PB / PE。
用于 A 股盈利能力评分模型中的 bm_ind、ep_ind、size 三个因子。

输出：work/prof/mktcap.csv  (code, date, close, total_market_cap, pb_ratio, pe_ratio, total_shares)
"""
import subprocess, sys, os, time, json, re
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

EXE = r"C:\Users\12066\.local\bin\westock.exe"
OLD = r"C:/Users/12066/WorkBuddy/2026-10-05-23-13-30"
BASE = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28"
OUT = os.path.join(BASE, "work", "prof", "mktcap.csv")
PROG = os.path.join(BASE, "work", "prof", "mktcap_progress.json")

KEEP = ["code", "price", "pe_ratio", "pb_ratio", "total_market_cap", "total_shares"]


def parse(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return []
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    out = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        out.append(dict(zip(header, cells)))
    return out


def main():
    codes = json.load(open(os.path.join(BASE, "work", "codes_prof.json"), encoding="utf-8"))
    pools = json.load(open(os.path.join(OLD, "data", "pools.json"), encoding="utf-8"))
    px = pd.read_csv(os.path.join(OLD, "data", "prices_full_v2.csv"), dtype={"code": str},
                     usecols=["date"])
    tdays = pd.to_datetime(pd.Series(px["date"].unique())).sort_values().reset_index(drop=True)

    asofs = sorted({v["asof"] for v in pools.values() if v.get("asof")})
    dates = []
    for a in asofs:
        ts = pd.Timestamp(a)
        nxt = tdays[tdays >= ts]
        if len(nxt):
            dates.append(str(nxt.iloc[0].date()))
    dates = sorted(set(dates))
    # 追加最新交易日（供最新一期评分/展示）
    dates.append(str(tdays.iloc[-1].date()))
    dates = sorted(set(dates))
    print("dates:", len(dates), dates, flush=True)

    prog = json.load(open(PROG, encoding="utf-8")) if os.path.exists(PROG) else {}
    rows = []
    if os.path.exists(OUT):
        old = pd.read_csv(OUT, dtype=str)
        rows = old.to_dict("records")
        print("resume rows:", len(rows), flush=True)

    seen = {(r["code"], r["date"]) for r in rows}
    for dt in dates:
        todo = [c for c in codes if (c, dt) not in seen]
        if not todo:
            continue
        got = 0
        batch, sleep_s = 30, 0.8
        i = 0
        fails = 0
        while i < len(todo):
            chunk = todo[i:i + batch]
            try:
                res = subprocess.run([EXE, "quote", ",".join(chunk), "--date", dt],
                                     capture_output=True, timeout=180)
            except subprocess.TimeoutExpired:
                res = None
            txt = res.stdout.decode("utf-8", errors="replace") if res else ""
            if "服务限频" in txt:
                fails += 1
                sleep_s = min(30.0, sleep_s * 2)
                if batch > 5:
                    batch = max(5, batch // 2)
                time.sleep(sleep_s)
                if fails > 40:
                    break
                continue
            recs = parse(txt)
            if not recs:
                fails += 1
                if batch > 5:
                    batch = max(5, batch // 2)
                    continue
                i += len(chunk)
                continue
            for r in recs:
                c = r.get("code")
                if not c or (c, dt) in seen:
                    continue
                rows.append({"code": c, "date": dt,
                             "close": r.get("price", ""),
                             "pe_ratio": r.get("pe_ratio", ""),
                             "pb_ratio": r.get("pb_ratio", ""),
                             "total_market_cap": r.get("total_market_cap", ""),
                             "total_shares": r.get("total_shares", "")})
                seen.add((c, dt))
                got += 1
            fails = 0
            i += len(chunk)
            time.sleep(sleep_s)
        pd.DataFrame(rows).to_csv(OUT, index=False, encoding="utf-8-sig")
        prog[dt] = got
        json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"[ok] {dt} got={got} total_rows={len(rows)}", flush=True)
    print("[done] rows:", len(rows), flush=True)


if __name__ == "__main__":
    main()
