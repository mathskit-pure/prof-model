# -*- coding: utf-8 -*-
"""
盈利能力评分模型（PROF）数据自动更新 + 回测 + 页面刷新 一体化脚本。

流程：
  1) 增量补抓财务三表（income+balance 一次返回）+ 各报告期 asof 交易日市值（catchup.py，可断点续跑）
  2) 重算 PROF 评分（prof_score.py）
  3) 重算盈利能力 Top20 等权回测（backtest_prof.py）
  4) 生成 4.3 持仓变动明细，并就地插入【当前线上页面】（先开事务下载最新版，避免覆盖本地过期副本），
     经由 library 页面事务协议上传提交（create → upload → commit）

用法：
  python update_prof_data.py                 # 跑全流程（含页面提交）
  python update_prof_data.py --no-page      # 只跑数据+评分+回测，不碰页面
  python update_prof_data.py --page-only    # 假设 csv 已就绪，只生成并上传页面
"""
import sys, os, json, subprocess, argparse, urllib.request, urllib.parse
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORK = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work"
PROF = os.path.join(WORK, "prof")
PAGE_NODE = "iB8I58mCTooLicPQ0Kyq0M"
LIB_PAGE = r"C:/Users/12066/AppData/Local/Programs/WorkBuddy/resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/library/page"
PY = r"C:/Users/12066/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
LOCAL_PAGE = os.path.join(WORK, "pool", "pool_page.html")
TMP_PAGE = os.path.join(WORK, "pool", "pool_page_live.html")
EDITED_PAGE = os.path.join(WORK, "pool", "pool_page_prof.html")
FOLD_PAGE = os.path.join(WORK, "pool", "pool_page_fold.html")   # gen_prof_section → gen_pool_fold 后的最终产物


def run(script, *args):
    cmd = [PY, os.path.join(WORK, script)] + list(args)
    print("\n>>> ", script, *args, flush=True)
    r = subprocess.run(cmd)
    return r.returncode


def step1_fetch():
    return run("catchup.py")


def step2_score_backtest():
    rc = run("prof_score.py")
    if rc != 0:
        return rc
    return run("backtest_prof.py")


def _download_live_page(tx):
    """从事务返回的 CDN url + html 相对路径下载当前线上页面。"""
    url = (tx.get("url") or "").strip()
    htmls = tx.get("html") or []
    if not url or not htmls:
        return None
    rel = htmls[0]
    # 相对路径可能含中文（如「舞弊调整质量因子季度动态股池.html」），
    # 必须逐段 percent-encode 后再拼接，否则 urllib 在 ASCII 化 URL 时抛 UnicodeEncodeError。
    full = url.rstrip("/") + "/" + urllib.parse.quote(rel.lstrip("/"))
    try:
        req = urllib.request.Request(full, headers={"User-Agent": "workbuddy"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read().decode("utf-8", errors="replace")
        if len(data) < 1000:
            return None
        with open(TMP_PAGE, "w", encoding="utf-8", newline="") as f:
            f.write(data)
        print("已下载线上页面:", len(data), "chars ->", TMP_PAGE)
        return TMP_PAGE
    except Exception as e:
        print("!! 下载线上页面失败:", e)
        return None


def step3_page():
    # 1) 开事务
    out = subprocess.run([PY, os.path.join(LIB_PAGE, "create_page_transaction.py"),
                          "--node-id", PAGE_NODE], capture_output=True, text=True)
    tx = None
    for line in out.stdout.splitlines():
        if line.startswith("KS_PAGE_TX_OPEN"):
            tx = json.loads(line.split(" ", 1)[1])
    if not tx:
        print("!! 开事务失败:", out.stdout[-600:], out.stderr[-600:])
        return 1
    tx_id = tx.get("transactionId")
    htmls = tx.get("html") or []
    if not tx_id or not htmls:
        print("!! 事务响应异常:", tx)
        return 1
    rel = htmls[0]
    print("事务开启:", tx_id, "html:", rel, "url:", tx.get("url"))

    # 2) 获取「当前线上」页面作为插入基底。
    #    注意：绝不能退化为本地 pool_page.html —— 那份是 10/7 的旧副本，
    #    拿它当基底上传会把线上已有的交互时间轴、AFGI 仓位曲线整段抹掉，属于破坏性回退。
    #    拿不到线上最新版就中止，本次不提交，等下次重跑。
    base = _download_live_page(tx)
    if not base:
        print("!! 下载线上页面失败：已中止，未提交任何改动（不要用本地旧副本兜底）")
        return 1

    # 3) 在最新页面基底上生成 4.3（先做盈利能力章节，再做季度股池折叠）
    rc = run("gen_prof_section.py", "--base", base, "--out", EDITED_PAGE)
    if rc != 0:
        return rc

    # 3b) 季度股池模块整体折叠（默认收起）；幂等，线上若已带壳则跳过
    rc = run("gen_pool_fold.py", "--base", EDITED_PAGE, "--out", FOLD_PAGE)
    if rc != 0:
        return rc
    final = FOLD_PAGE

    # 4) 上传
    up = subprocess.run([PY, os.path.join(LIB_PAGE, "upload_page_artifact.py"),
                         "--transaction-id", tx_id, "--path", rel, "--file", final],
                        capture_output=True, text=True)
    print("upload:", (up.stdout or up.stderr).strip())
    if "KS_PAGE_UPLOAD" not in (up.stdout or ""):
        print("!! 上传失败:", up.stdout[-500:], up.stderr[-500:])
        return 1

    # 5) 提交
    cm = subprocess.run([PY, os.path.join(LIB_PAGE, "commit_page_transaction.py"),
                         "--transaction-id", tx_id,
                         "--message", "轮动回测图例顺序对齐上方表格组合顺序"],
                        capture_output=True, text=True)
    print("commit:", (cm.stdout or cm.stderr).strip())
    if "KS_PAGE_COMMIT" not in (cm.stdout or ""):
        print("!! 提交可能失败:", cm.stdout[-500:], cm.stderr[-500:])
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-page", action="store_true")
    ap.add_argument("--page-only", action="store_true")
    args = ap.parse_args()

    if not args.page_only:
        step1_fetch()
        step2_score_backtest()
    if not args.no_page:
        step3_page()
    print("\n=== PROF 数据更新流程结束 ===")


if __name__ == "__main__":
    main()
