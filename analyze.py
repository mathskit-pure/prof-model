import re, json, io, sys

p = 'C:/Users/12066/WorkBuddy/2026-10-07-14-39-28/work/pool/pool_page.html'
s = open(p, encoding='utf-8').read()
i = s.find('三、动量轮动回测')
j = s.find('四、持仓变动明细')
seg = s[i:j]
start = seg.find('var BT=') + len('var BT=')
d = 0
end = None
for off, ch in enumerate(seg[start:]):
    if ch == '{':
        d += 1
    elif ch == '}':
        d -= 1
        if d == 0:
            end = start + off + 1
            break
raw = seg[start:end]
print('BT raw len', len(raw))
obj = json.loads(raw)
print('keys:', list(obj.keys()))
for k, v in obj.items():
    if isinstance(v, list):
        print(' ', k, 'list', len(v), str(v[:4])[:300])
    elif isinstance(v, dict):
        print(' ', k, 'dict n=', len(v), list(v.keys())[:10])
    else:
        print(' ', k, repr(v)[:200])
