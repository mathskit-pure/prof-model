# -*- coding: utf-8 -*-
"""
一体化断点续跑抓取：
  1) 利润表+资产负债表（--fields all 一次返回两张表），仅补抓股池内缺失的个股；
  2) 各报告期 asof 交易日市值（quote --date），仅补抓缺失日期。
保守 pacing + 高阈值，避免被限频后过早 abort。日志同时写 stdout 与 catchup.log。
"""
import subprocess, sys, os, time, json, re, csv

csv.field_size_limit(10 ** 9)  # never choke on a large field during read-back
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import WORK, WESTOCK as EXE  # noqa: E402  路径：本机 Windows 与云端 Linux 通用

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROF = os.path.join(WORK, "prof")
INCOME = os.path.join(PROF, "income_all.csv")
BALANCE = os.path.join(PROF, "balance_all.csv")
MKTCAP = os.path.join(PROF, "mktcap.csv")
PROG_INC = os.path.join(PROF, "catchup_inc.json")
PROG_MC = os.path.join(PROF, "catchup_mc.json")
LOG = os.path.join(PROF, "catchup.log")
START, END = "2017-01-01", "2026-12-31"

# ---- 单实例锁：防止并发 catchup 进程竞写导致 income/balance/mktcap 被截断/损坏 ----
LOCK_PATH = os.path.join(PROF, ".catchup.lock")


def _pid_alive(pid):
    if os.name == "nt":
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x400, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
        except Exception:
            return False
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock():
    # 单实例锁已禁用：当前由人工串行前台运行，避免 os.remove 触发沙箱安全删除守护。
    return True


def release_lock():
    pass


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_pool():
    compact = json.loads(open(os.path.join(WORK, "pools_compact.json"), encoding="utf-8").read())
    tdays = sorted(l.strip() for l in open(os.path.join(WORK, "tdays.txt"), encoding="utf-8") if l.strip())
    members_by_period, asof_date = {}, {}
    allcodes = set()
    for end, v in compact.items():
        a = v["asof"]
        nxt = [t for t in tdays if t >= a]
        d = nxt[0] if nxt else None
        members_by_period[end] = [m["code"] for m in v["members"]]
        asof_date[end] = d
        for m in v["members"]:
            allcodes.add(m["code"])
    return allcodes, members_by_period, asof_date


def covered_codes(path, require_fields=None):
    s = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                c = (row.get("code") or "").strip()
                if not c:
                    continue
                if require_fields:
                    ok = all((row.get(fld) or "").strip() not in ("", "nan", "None")
                             for fld in require_fields)
                    if not ok:
                        continue
                s.add(c)
    return s


def parse_tables(text):
    out = {}
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"\*\*(.+?)\*\*", text)]
    for idx, (pos, title) in enumerate(marks):
        kind = {"利润表": "income", "资产负债表": "balance"}.get(title)
        if not kind:
            continue
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(text)
        lines = [ln.strip() for ln in text[pos:end].splitlines() if ln.strip().startswith("|")]
        if len(lines) < 2:
            continue
        header = [c.strip() for c in lines[0].strip("|").split("|")]
        rows = []
        for ln in lines[2:]:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) != len(header):
                continue
            rows.append(dict(zip(header, cells)))
        if rows:
            out[kind] = (header, rows)
    return out


def append_rows(kind, header, rows):
    # Append by COLUMN NAME to a canonical header. Never rewrites the whole
    # file (avoids os.replace lock errors on the large CSV under antivirus).
    path = INCOME if kind == "income" else BALANCE
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    if not exists:
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return
    with open(path, encoding="utf-8") as f:
        canon = next(csv.reader(f))
    for attempt in range(6):
        try:
            with open(path, "a", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=canon, extrasaction="ignore")
                for r in rows:
                    w.writerow(r)
            return
        except PermissionError:
            time.sleep(1.0 + attempt)
    raise PermissionError(f"append failed after retries: {path}")


def fetch_finance(codes):
    cmd = [EXE, "finance", ",".join(codes), "--start", START, "--end", END, "--fields", "all"]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=300)
    except Exception:
        return None, "timeout"
    txt = res.stdout.decode("utf-8", errors="replace")
    err = res.stderr.decode("utf-8", errors="replace")
    if "服务限频" in txt or "服务限频" in err:
        return None, "ratelimit"
    if not txt.strip():
        return None, "empty"
    return txt, None


def run_income(allcodes):
    # A code counts as covered only if BOTH tables have it with the required
    # PROF fields populated (income expense fields + balance RetainedProfit).
    inc_cov = covered_codes(INCOME, ["OperatingExpense", "TotalAdminExpense", "FinancialExpense"])
    # OLD cached balance.csv supplies TotalShareholderEquity (the field `prof`
    # divides by) for all pool codes; only RetainedProfit is missing there, and
    # that is handled by prof_score's missing-factor renormalization. So treat a
    # code as balance-covered once it has TotalShareholderEquity.
    bal_cov = covered_codes(BALANCE, ["TotalShareholderEquity"])
    covered = inc_cov & bal_cov
    prog = json.load(open(PROG_INC, encoding="utf-8")) if os.path.exists(PROG_INC) else {"done": []}
    done = set(prog["done"])
    todo = [c for c in allcodes if c not in covered and c not in done]
    log(f"[inc-start] 股池={len(allcodes)} 已覆盖={len(covered)} 已完成={len(done)} 待抓={len(todo)}")
    batch, sleep_s = 5, 6.0
    fails = 0
    t0 = time.time()
    t_start = time.time()
    BUDGET = 75  # seconds; clean-exit before the foreground ~90s kill
    i = 0
    while i < len(todo):
        chunk = todo[i:i + batch]
        txt, err = fetch_finance(chunk)
        if err:
            fails += 1
            prev = sleep_s
            sleep_s = min(120.0, sleep_s * 1.8)
            if fails % 3 == 0 and batch > 2:
                batch = max(2, batch - 1)
            log(f"[inc-fail] {err} batch={batch} sleep {prev:.1f}->{sleep_s:.1f} done={len(done)} fails={fails}")
            time.sleep(sleep_s)
            if fails > 800:
                log("[inc-abort] 失败过多，停止"); break
            continue
        tables = parse_tables(txt)
        if not tables:
            fails += 1
            if batch > 1:
                batch = max(1, batch // 2)
            time.sleep(sleep_s)
            continue
        for kind, (header, rows) in tables.items():
            # balance 已由 OLD 缓存合并补齐，本次只补 income 费用字段，避免重复写入。
            if kind == "income":
                append_rows(kind, header, rows)
        got = set()
        for _, (_, rows) in tables.items():
            for rr in rows:
                if rr.get("code"):
                    got.add(rr["code"])
        for c in got:
            if c not in done:
                done.add(c)
                prog["done"].append(c)
        json.dump(prog, open(PROG_INC, "w", encoding="utf-8"), ensure_ascii=False)
        fails = 0
        sleep_s = max(4.0, sleep_s * 0.9)
        i += len(chunk)
        if time.time() - t_start > BUDGET:
            log(f"[inc-budget] reached {BUDGET}s budget, clean exit (done={len(done)})")
            break
        eta = (len(allcodes) - len(done)) * (time.time() - t0) / max(1, len(done)) / 60
        log(f"[inc-ok] got={len(got)} done={len(done)}/{len(allcodes)} batch={batch} eta={eta:.1f}min")
        time.sleep(sleep_s)
    log(f"[inc-end] done={len(done)}")


def parse_quote(text):
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


def run_mktcap(members_by_period, asof_date):
    present = set()
    rows = []
    if os.path.exists(MKTCAP):
        with open(MKTCAP, encoding="utf-8") as f:
            r = csv.DictReader(f)
            rows = list(r)
            for row in rows:
                present.add(row.get("date"))
    seen = {(r.get("code"), r.get("date")) for r in rows}
    prog = json.load(open(PROG_MC, encoding="utf-8")) if os.path.exists(PROG_MC) else {}
    log(f"[mc-start] 已存在日期={len(present)} 待补={sum(1 for e in members_by_period if not prog.get(e) and asof_date[e] not in present)}")
    for end in sorted(members_by_period):
        d = asof_date[end]
        if not d or prog.get(end) or d in present:
            if d and d in present and not prog.get(end):
                prog[end] = len(members_by_period[end])
                json.dump(prog, open(PROG_MC, "w", encoding="utf-8"), ensure_ascii=False)
            continue
        members = members_by_period[end]
        todo = [c for c in members if (c, d) not in seen]
        got = 0
        batch, sleep_s = 20, 1.0
        fails = 0
        i = 0
        while i < len(todo):
            chunk = todo[i:i + batch]
            try:
                res = subprocess.run([EXE, "quote", ",".join(chunk), "--date", d],
                                     capture_output=True, timeout=180)
            except Exception:
                res = None
            txt = res.stdout.decode("utf-8", errors="replace") if res else ""
            if "服务限频" in txt:
                fails += 1
                sleep_s = min(60.0, sleep_s * 2)
                if batch > 5:
                    batch = max(5, batch // 2)
                time.sleep(sleep_s)
                if fails > 120:
                    log(f"[mc-failbreak] {end} 限频过多"); break
                continue
            recs = parse_quote(txt)
            if not recs:
                fails += 1
                if batch > 5:
                    batch = max(5, batch // 2)
                time.sleep(sleep_s)
                continue
            for r in recs:
                c = r.get("code")
                if not c or (c, d) in seen:
                    continue
                rows.append({"code": c, "date": d,
                             "close": r.get("price", ""),
                             "pe_ratio": r.get("pe_ratio", ""),
                             "pb_ratio": r.get("pb_ratio", ""),
                             "total_market_cap": r.get("total_market_cap", ""),
                             "total_shares": r.get("total_shares", "")})
                seen.add((c, d))
                got += 1
            fails = 0
            i += len(chunk)
            time.sleep(sleep_s)
        tmp = MKTCAP + ".tmp"
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["code", "date", "close", "pe_ratio", "pb_ratio",
                                              "total_market_cap", "total_shares"])
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, MKTCAP)
        prog[end] = got
        json.dump(prog, open(PROG_MC, "w", encoding="utf-8"), ensure_ascii=False)
        log(f"[mc-ok] {end} date={d} got={got}/{len(members)} total_rows={len(rows)}")
    log(f"[mc-end] rows={len(rows)}")


def main():
    if not acquire_lock():
        print("[lock] 检测到另一 catchup 实例正在运行，本实例退出以避免并发写损坏文件。")
        sys.exit(0)
    try:
        allcodes, members_by_period, asof_date = load_pool()
        run_income(allcodes)   # 仅补 income 费用字段（balance 已通过 OLD 缓存合并补齐）
        log("[catchup-done]")  # run_mktcap 已完整（23/23 日期），跳过以免重写触发安全删除守护
    finally:
        release_lock()


if __name__ == "__main__":
    main()
