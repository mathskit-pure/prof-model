# -*- coding: utf-8 -*-
"""Repair income_all.csv / balance_all.csv corrupted by concurrent writers.
Drops rows whose field count != header count, or with any abnormally long
field (merged-row corruption), then dedupes by (code, EndDate)."""
import csv, sys, os

csv.field_size_limit(10 ** 9)
PROF = r"C:\Users\12066\WorkBuddy\2026-10-07-14-39-28\work\prof"
THRESH = 2000  # no legitimate financial field should exceed this length


def repair(path):
    if not os.path.exists(path):
        print(f"  skip (missing): {os.path.basename(path)}")
        return
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if not lines:
        print(f"  empty: {os.path.basename(path)}")
        return
    header = lines[0].rstrip("\n").split(",")
    ncol = len(header)
    kept, dropped_count, huge, badn = [], 0, 0, 0
    seen = set()
    for ln in lines[1:]:
        if not ln.strip():
            continue
        # use csv to parse (handles quoted fields); fall back to split
        try:
            row = next(csv.reader([ln.rstrip("\n")]))
        except Exception:
            row = ln.rstrip("\n").split(",")
        if len(row) != ncol:
            badn += 1
            dropped_count += 1
            continue
        if any(len(c) > THRESH for c in row):
            huge += 1
            dropped_count += 1
            continue
        code = (row[0] if row else "").strip()
        # find EndDate-ish column
        end = ""
        for i, h in enumerate(header):
            if h in ("EndDate", "end_date", "报告期"):
                end = row[i] if i < len(row) else ""
                break
        key = (code, end)
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    out = path + ".repaired"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(kept)
    # replace
    os.replace(out, path)
    codes = set(r[0].strip() for r in kept if r)
    print(f"  {os.path.basename(path)}: header_cols={ncol} kept={len(kept)} "
          f"dropped(bad_n={badn}, huge={huge}) unique_codes={len(codes)}")


if __name__ == "__main__":
    print("Repairing financial CSVs...")
    repair(os.path.join(PROF, "income_all.csv"))
    repair(os.path.join(PROF, "balance_all.csv"))
    print("Done.")
