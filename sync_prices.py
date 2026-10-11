# -*- coding: utf-8 -*-
"""把主项目每日增量更新的 hfq 后复权日线同步到 PROF 项目。

背景：PROF 的回测 backtest_prof.py 读 work/prices_full_v2.csv（hfq 口径），
该文件此前只是主项目 data/prices_full_v2.csv 的一次性副本，没有任何脚本每天更新它，
导致盈利能力 Top40 的净值曲线会冻结在复制当天。

主项目那份由 19:00 的 daily_refresh.py 增量维护，因此 PROF 只需单向同步即可，
无需重复调用行情接口（省时、也不受接口限频影响）。

安全性：源文件的最大日期必须 >= 本地，且行数不得减少，否则拒绝覆盖。
"""
import os
import sys
import shutil
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import MAIN, WORK  # noqa: E402  路径：本机 Windows 与云端 Linux 通用

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = str(MAIN / "data" / "prices_full_v2.csv")
DST = str(WORK / "prices_full_v2.csv")
BAK = DST + ".bak"


def last_date(path):
    """返回文件里最大的日期（不依赖行末顺序）。"""
    df = pd.read_csv(path, dtype={"code": str}, usecols=["code", "date"])
    return str(df["date"].max()), len(df)


def main():
    if not os.path.exists(SRC):
        print("!! 源文件不存在，放弃同步:", SRC)
        return 1

    s_date, s_rows = last_date(SRC)
    print("源  :", SRC)
    print("      最大日期 =", s_date, " 行数 =", f"{s_rows:,}")

    if os.path.exists(DST):
        d_date, d_rows = last_date(DST)
        print("本地:", DST)
        print("      最大日期 =", d_date, " 行数 =", f"{d_rows:,}")

        if s_date < d_date:
            print("!! 源数据比本地旧（%s < %s），拒绝覆盖" % (s_date, d_date))
            return 1
        if s_rows < d_rows:
            print("!! 源行数比本地少（%d < %d），拒绝覆盖" % (s_rows, d_rows))
            return 1
        if s_date == d_date and s_rows == d_rows:
            print("== 本地已是最新，无需同步")
            return 0
        shutil.copy2(DST, BAK)
        print("   已备份旧文件 ->", BAK)
    else:
        print("本地: 不存在，首次同步")

    shutil.copy2(SRC, DST)
    n_date, n_rows = last_date(DST)
    print("== 同步完成：最大日期 =", n_date, " 行数 =", f"{n_rows:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
