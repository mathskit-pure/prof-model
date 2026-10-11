# -*- coding: utf-8 -*-
"""把 PROF 上传成功的页面产物回写为主项目 refresh_page.py 的模板。

背景：19:00 主流水线 refresh_page.py 以 data/page_base.html（= 上次发布成功的产物）为模板
整页重建后再上传。而 16:00/20:00 的 PROF 任务走的是「下载线上最新页面 → 插入 4.3 → 提交」，
并不回写 page_base.html。若不同步，第二天 19:00 会用旧模板整页覆写，
把 PROF 刚更新的 4.3 章节顶掉，页面回退一天。

因此 PROF 每次提交成功后，必须把最终产物回写为 page_base.html。
"""
import os
import re
import sys
import shutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FOLD_PAGE = r"C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work/pool/pool_page_fold.html"
BASE_PAGE = r"C:/Users/12066/WorkBuddy/2026-10-05-23-13-30/data/page_base.html"
BAK = BASE_PAGE + ".bak"

# 页面必须同时具备这些标记，缺一说明产物不完整，绝不能拿去做模板
# 注：原标记 "AFGI仓位" 已随 19:00 主流水线改版失效——该序列现名为「动量×AFGI稳健联合」
# （BT.order 键为「联合仓位」），故改用「联合仓位」做完整性校验。
MUST_HAVE = ["var BT=", "4.1", "4.2", "4.3", "联合仓位"]
MIN_SIZE = 5 * 1024 * 1024


def chart_last_date(path):
    """页面 var BT= 里净值日期数组的最后一天，代表该页面数据更新到哪天。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
    except Exception:
        return None
    m = re.search(r'var BT=\{.*?"dates":\[(.*?)\]', html, re.S)
    if not m:
        return None
    ds = re.findall(r'"(\d{4}-\d{2}-\d{2})"', m.group(1))
    return ds[-1] if ds else None


def main():
    if not os.path.exists(FOLD_PAGE):
        print("!! 产物不存在:", FOLD_PAGE)
        return 1

    size = os.path.getsize(FOLD_PAGE)
    if size < MIN_SIZE:
        print("!! 产物体积异常（%d bytes < %d），放弃回写" % (size, MIN_SIZE))
        return 1

    with open(FOLD_PAGE, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()

    missing = [t for t in MUST_HAVE if t not in html]
    if missing:
        print("!! 产物缺少关键标记:", missing, " 放弃回写")
        return 1

    # 单调性守卫：产物的数据日期必须不早于现有模板。
    # PROF 是在 19:00 主流水线之后跑的，产物只会更新、不会倒退；
    # 一旦倒退说明这份产物是从某个旧基底生成的，回写会让模板永久回退。
    new_d = chart_last_date(FOLD_PAGE)
    old_d = chart_last_date(BASE_PAGE) if os.path.exists(BASE_PAGE) else None
    print("   产物数据日期 =", new_d, "  现有模板数据日期 =", old_d)
    if new_d is None:
        print("!! 无法解析产物的净值日期，放弃回写")
        return 1
    if old_d and new_d < old_d:
        print("!! 产物数据日期（%s）早于现有模板（%s），判定为回退产物，放弃回写"
              % (new_d, old_d))
        return 1

    if os.path.exists(BASE_PAGE):
        shutil.copy2(BASE_PAGE, BAK)
        print("   已备份旧模板 ->", BAK)

    shutil.copy2(FOLD_PAGE, BASE_PAGE)
    print("== 已回写模板:", BASE_PAGE, "（%s chars）" % f"{len(html):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
