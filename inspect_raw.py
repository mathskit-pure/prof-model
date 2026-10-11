# -*- coding: utf-8 -*-
import sys, os, json
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r"C:/Users/12066/WorkBuddy/2026-10-05-23-13-30"
RAW = BASE + "/data/raw"

for f in ['income.csv', 'balance.csv', 'cashflow.csv']:
    d = pd.read_csv(os.path.join(RAW, f), dtype=str)
    ds = sorted(d['EndDate'].dropna().unique())
    print(f, d.shape, 'codes', d['code'].nunique(), 'ndates', len(ds))
    print('   ', ds[:5], '...', ds[-4:])
    print('   cols:', list(d.columns)[:80])

d = pd.read_csv(os.path.join(RAW, 'income.csv'), dtype=str)
print()
print('income EndDate value counts:')
print(d['EndDate'].value_counts().sort_index().to_string())

meta = json.load(open(BASE + "/scripts/meta.json", encoding='utf-8'))
print('meta n=', len(meta), list(meta.items())[:2])
caps = json.load(open(BASE + "/data/caps.json", encoding='utf-8'))
print('caps n=', len(caps), list(caps.items())[:3])
codes_pool = json.load(open(BASE + "/scripts/codes_pool.json", encoding='utf-8'))
print('codes_pool n=', len(codes_pool), codes_pool[:5])
