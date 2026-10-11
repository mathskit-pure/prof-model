# -*- coding: utf-8 -*-
"""
把「季度股池整体折叠」改动发布到资料库页面（create → download → edit → upload → commit）。
幂等：重复运行只会重复上传同一效果（折叠壳检测到已存在便跳过），不会叠加。

用法：
  python publish_pool_fold.py            # 正常发布
  python publish_pool_fold.py --dry-run  # 只下载+本地生成，不上传提交
"""
import sys, os, json, re, subprocess, argparse, urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORK = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work"
PAGE_NODE = "iB8I58mCTooLicPQ0Kyq0M"
LIB_PAGE = r"C:/Users/12066/AppData/Local/Programs/WorkBuddy/resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/library/page"
PY = r"C:/Users/12066/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
LIVE = os.path.join(WORK, "pool", "pool_page_live.html")
EDITED = os.path.join(WORK, "pool", "pool_page_fold.html")
MSG = "季度股池模块新增整体折叠（默认收起，点击展开）"


def _download(url, rel, dest):
    full = url.rstrip("/") + "/" + rel.lstrip("/")
    req = urllib.request.Request(full, headers={"User-Agent": "workbuddy"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read().decode("utf-8", errors="replace")
    if len(data) < 1000:
        raise SystemExit("!! 下载的页面过小，异常")
    with open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    print("已下载线上页面:", f"{len(data):,}", "chars ->", dest)
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 1) 开事务
    out = subprocess.run([PY, os.path.join(LIB_PAGE, "create_page_transaction.py"),
                          "--node-id", PAGE_NODE], capture_output=True, text=True)
    if "KS_PAGE_TX_OPEN" not in (out.stdout or ""):
        print("!! 开事务失败:\n", out.stdout[-800:], out.stderr[-800:])
        return 1
    tx = json.loads(out.stdout.split("KS_PAGE_TX_OPEN ", 1)[1].splitlines()[0])
    tx_id, htmls, url = tx.get("transactionId"), tx.get("html") or [], tx.get("url")
    if not tx_id or not htmls:
        print("!! 事务响应异常:", tx)
        return 1
    print("事务开启:", tx_id, "| html:", htmls[0])

    # 2) 下载线上最新版作为基底
    live = _download(url, htmls[0], LIVE)

    # 3) 生成折叠版
    rc = subprocess.run([PY, os.path.join(WORK, "gen_pool_fold.py"),
                         "--base", LIVE, "--out", EDITED])
    if rc.returncode != 0:
        print("!! 生成失败")
        return 1
    new = open(EDITED, encoding='utf-8').read()

    # 4) 上传前最后把关
    n_sec_new = len(re.findall(r'<section\b', new))
    n_sec_live = len(re.findall(r'<section\b', live))
    if n_sec_new != n_sec_live or new.count('<details class="blk-fold">') != 1:
        print("!! 上传前把关失败，终止")
        return 1
    print(f"把关 OK：section {n_sec_live}→{n_sec_new}，折叠壳 1 个")

    if args.dry_run:
        print("\n--dry-run：未上传提交")
        return 0

    # 5) 上传
    up = subprocess.run([PY, os.path.join(LIB_PAGE, "upload_page_artifact.py"),
                         "--transaction-id", tx_id, "--path", htmls[0], "--file", EDITED],
                        capture_output=True, text=True)
    print("upload:", (up.stdout or up.stderr).strip())
    if "KS_PAGE_UPLOAD" not in (up.stdout or ""):
        print("!! 上传失败:", up.stdout[-600:], up.stderr[-600:])
        return 1

    # 6) 提交
    cm = subprocess.run([PY, os.path.join(LIB_PAGE, "commit_page_transaction.py"),
                         "--transaction-id", tx_id, "--message", MSG],
                        capture_output=True, text=True)
    print("commit:", (cm.stdout or cm.stderr).strip())
    if "KS_PAGE_COMMIT" not in (cm.stdout or ""):
        print("!! 提交可能失败:", cm.stdout[-600:], cm.stderr[-600:])
        return 1
    print("\n=== 发布完成 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
