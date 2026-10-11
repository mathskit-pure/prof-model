# -*- coding: utf-8 -*-
"""
抓取各报告期「信息可得日后的首个交易日」的历史市值，用于盈利能力评分模型的 bm_ind / ep_ind / size 因子。
只抓每个报告期自身的股池成员，避免全宇宙 × 全日期的浪费。
输出：work/prof/mktcap.csv (code, date, close, total_market_cap, pb_ratio, pe_ratio, total_shares)
"""
import subprocess, sys, os, time, json, re
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

EXE = r"C:\Users\12066\.local\bin\westock.exe"
WORK = r"C:\Users\12066\WorkBuddy\2026-10-07-14-39-28\work"
PROF = os.path.join(WORK, "prof")
OUT = os.path.join(PROF, "mktcap.csv")
PROG = os.path.join(PROF, "mktcap_progress.json")

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
    compact = json.loads(open(os.path.join(WORK, "pools_compact.json"), encoding="utf-8").read())
    tdays = pd.to_datetime(pd.Series([l.strip() for l in open(os.path.join(WORK, "tdays.txt"), encoding="utf-8") if l.strip()])).sort_values().reset_index(drop=True)

    # 每个报告期 -> 首个交易日
    periods = []
    for end, v in compact.items():
        a = pd.Timestamp(v["asof"])
        nxt = tdays[tdays >= a]
        if len(nxt):
            periods.append((end, str(nxt.iloc[0].date()), [m["code"] for m in v["members"]]))
    periods.sort()
    print("periods:", len(periods), flush=True)

    prog = json.load(open(PROG, encoding="utf-8")) if os.path.exists(PROG) else {}
    rows = []
    if os.path.exists(OUT):
        old = pd.read_csv(OUT, dtype=str)
        rows = old.to_dict("records")
        print("resume rows:", len(rows), flush=True)
    seen = {(r["code"], r["date"]) for r in rows}

    for end, dt, members in periods:
        if prog.get(end):  # 该期已完成
            continue
        todo = [c for c in members if (c, dt) not in seen]
        if not todo:
            prog[end] = len(members)
            json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False)
            continue
        got = 0
        batch, sleep_s = 30, 0.6
        fails = 0
        i = 0
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
                sleep_s = min(40.0, sleep_s * 2)
                if batch > 5:
                    batch = max(5, batch // 2)
                time.sleep(sleep_s)
                if fails > 60:
                    break
                continue
            recs = parse(txt)
            if not recs:
                fails += 1
                if batch > 5:
                    batch = max(5, batch // 2)
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
        prog[end] = got
        json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"[ok] {end} date={dt} got={got}/{len(members)} total_rows={len(rows)}", flush=True)
    print("[done] rows:", len(rows), flush=True)


if __name__ == "__main__":
    main()
