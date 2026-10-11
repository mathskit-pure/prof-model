# -*- coding: utf-8 -*-
"""
给「二、季度股池」整个模块加一层原生 <details> 折叠外壳（默认收起，点击展开）。

设计要点：
  1) 只包裹 23 个 <section class="card">（每期一个季报），<h2> 标题保持在外部常显，
     避免把块级标题塞进 <summary> 触发平台规范化重排。
  2) 外壳 <details> 不写 open 属性 → 默认收起；内部每个季报的 <details> 一律保持原样
     （同样无 open 属性），因此"每个季报默认收起"的行为完全不变。
  3) 不需要任何 JS：全部由浏览器原生 <details> 行为驱动，最稳。
  4) 幂等：检测到已加过外壳就直接原样返回，可重复运行（适配每周定时重跑）。

用法：
  python gen_pool_fold.py [--base <html>] [--out <html>] [--check]
"""
import sys, os, re, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import WORK  # noqa: E402  路径：本机 Windows 与云端 Linux 通用

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.join(WORK, "pool", "pool_page_live.html")
OUT = os.path.join(WORK, "pool", "pool_page_fold.html")

H2_POOL = '二、季度股池'
H2_NEXT = '三、动量轮动回测'
# 注意：平台上传后会重写 HTML（补 data-page-node-id、调整 style 空格），因此
# 绝对不能用精确字符串定位已生成的内容，必须用「按 class 匹配」的正则。
WRAP_RE = re.compile(r'<details\b[^>]*\bclass="[^"]*\bblk-fold\b[^"]*"[^>]*>')
SUM_RE = re.compile(r'<summary\b[^>]*\bclass="[^"]*\bblk-fold-s\b[^"]*"[^>]*>')
# 4.3 里「更早 N 期」也复用同一套样式（blk-fold-more），检测时必须排除，只认
# 位于「二、季度股池 → 三、动量轮动回测」之间的那一个。
POOL_MARK = 'blk-fold-pool'


def module_span(page):
    """返回季度股池模块的 body 区间 (body_s, nxt)；定位失败返回 None。"""
    hi, ni = page.find(H2_POOL), page.find(H2_NEXT)
    if hi < 0 or ni < 0 or ni <= hi:
        return None
    h2e = page.find('</h2>', hi)
    nxt = page.rfind('<h2', 0, ni)
    if h2e < 0 or nxt < 0 or h2e >= nxt:
        return None
    return h2e + len('</h2>'), nxt


def pool_wraps(page):
    """仅统计季度股池模块内的折叠外壳（兼容旧版只写 blk-fold 的写法）。"""
    sp = module_span(page)
    if not sp:
        return []
    blk = page[sp[0]:sp[1]]
    return [m for m in WRAP_RE.finditer(blk)
            if POOL_MARK in m.group(0) or 'blk-fold-more' not in m.group(0)]

# ===== 新增 CSS：追加到既有 <style> 块末尾 =====
CSS = (
    "\n.blk-fold{margin:0 0 14px}"
    ".blk-fold>.blk-fold-s{display:flex;align-items:center;gap:10px;flex-wrap:wrap;"
    "list-style:none;cursor:pointer;user-select:none;background:var(--card);"
    "border:1px solid var(--bd);border-radius:10px;padding:11px 16px;"
    "color:var(--tx);font-size:14px;font-weight:600;outline:none}"
    ".blk-fold>.blk-fold-s::-webkit-details-marker{display:none}"
    ".blk-fold>.blk-fold-s::marker{content:\"\"}"
    ".blk-fold>.blk-fold-s .blk-fold-i{display:inline-block;color:var(--ac2);"
    "font-size:11px;line-height:1;transition:transform .15s ease}"
    ".blk-fold[open]>.blk-fold-s .blk-fold-i{transform:rotate(90deg)}"
    ".blk-fold>.blk-fold-s .blk-fold-n{color:var(--mut);font-weight:400}"
    ".blk-fold>.blk-fold-s .blk-fold-a{margin-left:auto;color:var(--ac2);"
    "font-size:13px;font-weight:400}"
    ".blk-fold[open]>.blk-fold-s .blk-fold-off{display:none}"
    ".blk-fold:not([open])>.blk-fold-s .blk-fold-on{display:none}"
    ".blk-fold-b{margin-top:2px}\n"
)


def _text(raw):
    """去掉标签与 pnid 注释，取纯文本。"""
    t = re.sub(r'<!--.*?-->', '', raw, flags=re.S)
    t = re.sub(r'<[^>]+>', ' ', t)
    return ' '.join(t.split())


def wrap_page(page):
    """把季度股池模块的 23 个 <section> 包进一层默认收起的 <details>。"""
    # ---------- 幂等检查（按 class 正则 + 限定模块区间，兼容平台规范化后的写法） ----------
    n_wrap = len(pool_wraps(page))
    if n_wrap:
        if n_wrap != 1:
            raise SystemExit(f"!! 检测到 {n_wrap} 处折叠外壳，页面可能已损坏，终止")
        print("  [skip] 折叠外壳已存在（幂等），保持原样")
        page = ensure_css(page)          # 外壳在但样式丢了的话补回来
        return page, False

    # ---------- 定位模块边界 ----------
    hi = page.find(H2_POOL)
    ni = page.find(H2_NEXT)
    if hi < 0 or ni < 0 or ni <= hi:
        raise SystemExit("!! 定位不到「季度股池」模块边界，终止")

    h2o = page.rfind('<h2', 0, hi)                  # 本模块 h2 起始
    h2e = page.find('</h2>', hi)                    # 本模块 h2 结束
    nxt = page.rfind('<h2', 0, ni)                  # 下一节 h2 起始
    if h2o < 0 or h2e < 0 or nxt < 0 or not (h2e < nxt):
        raise SystemExit("!! 模块边界异常，终止")
    body_s = h2e + len('</h2>')
    body = page[body_s:nxt]

    secs = [m.start() for m in re.finditer(r'<section\b', body)]
    dets = [m.start() for m in re.finditer(r'<details\b', body)]
    h3s = [m.start() for m in re.finditer(r'<h3\b', body)]
    if not secs or len(secs) != len(dets) or len(secs) != len(h3s):
        raise SystemExit(f"!! 模块内结构异常：section={len(secs)} "
                         f"details={len(dets)} h3={len(h3s)}，终止")
    if '<h2' in body or '</h2>' in body:
        raise SystemExit("!! 模块内意外出现二级标题，边界判定不可靠，终止")
    print(f"  模块定位 OK：{len(secs)} 个季报 <section>（pid ？） "
          f"| body {len(body):,} chars")

    # ---------- 摘要文案：期数 + 起止区间（自动随季报增加而变化） ----------
    titles = []
    for m in re.finditer(r'<h3[^>]*>(.*?)</h3>', body, re.S):
        t = _text(m.group(1))
        t = re.sub(r'信息可得.*$', '', t).strip()
        if t:
            titles.append(t)
    if not titles:
        titles = [f"第 {i+1} 期" for i in range(len(secs))]
    span = titles[0]
    if len(titles) > 1:
        span = f"{titles[0]} → {titles[-1]}"

    summary = (
        '<details class="blk-fold blk-fold-pool"><summary class="blk-fold-s">'
        '<span class="blk-fold-i">&#9654;</span>'
        '<span class="blk-fold-t">季报明细</span>'
        f'<span class="blk-fold-n">共 {len(secs)} 期 · {span}</span>'
        '<span class="blk-fold-a">'
        '<span class="blk-fold-off">点击展开</span>'
        '<span class="blk-fold-on">点击收起</span>'
        '</span>'
        '</summary>'
        '<div class="blk-fold-b">'
    )
    # body 前后空白放到外壳外面，保持原有排版
    lead = re.match(r'\s*', body).group(0)
    tail = re.search(r'\s*$', body).group(0)
    inner = body[len(lead):len(body) - len(tail)] if len(body) > len(lead) + len(tail) else body.strip()

    page = (page[:body_s] + lead + summary + inner + '</div></details>' + tail
            + page[nxt:])

    page = ensure_css(page)
    return page, True


def ensure_css(page):
    """向既有 <style> 块末尾追加折叠外壳样式；已有则原样返回。"""
    si = page.find('</style>')
    if si < 0:
        raise SystemExit("!! 找不到 </style>，无法注入样式")
    if '.blk-fold{' not in page[:si]:
        return page[:si] + CSS + page[si:]
    return page


def verify(old, new, changed):
    """离线验证：结构完整性 / 默认收起 / 内层不受影响 / 其余部分逐字不变。"""
    print("\n=== 离线验证 ===")
    ok = True

    hi = new.find(H2_POOL)
    h2e = new.find('</h2>', hi)
    body_s = h2e + len('</h2>')
    ni = new.find(H2_NEXT)
    nxt = new.rfind('<h2', 0, ni)
    blk = new[body_s:nxt]

    def chk(cond, msg):
        nonlocal ok
        print(("  [OK] " if cond else "  [NG] ") + msg)
        if not cond:
            ok = False

    # 1) 外壳数量与默认状态
    wraps = [m.group(0) for m in pool_wraps(new)]
    sp = module_span(new)
    sums = [m for m in SUM_RE.finditer(new) if sp and sp[0] <= m.start() < sp[1]]
    chk(len(wraps) == 1, f"季度股池折叠外壳数量 = 1（实测 {len(wraps)}）")
    chk(len(sums) == 1, f"季度股池折叠 summary 数量 = 1（实测 {len(sums)}）")
    if wraps:
        chk(not re.search(r'\bopen\b', wraps[0]), "外壳默认收起（无 open 属性）")
        chk(hi < new.find(wraps[0]) < ni, "外壳位于「二、季度股池」与「三、动量轮动回测」之间")
    # summary 必须是 details 的第一个子元素（否则浏览器不会把它当标题）
    # 注意兼容旧版外壳（只写 class="blk-fold"，当时还没有 blk-fold-pool 标记）
    # 注意：pool_wraps 的匹配是在「模块区间子串」上做的，需换算成整页偏移
    wm = pool_wraps(new)
    tail = new[sp[0] + wm[0].end(): sp[0] + wm[0].end() + 200] if (wm and sp) else ''
    chk(bool(wm) and re.match(r'\s*<summary\b[^>]*\bclass="[^"]*\bblk-fold-s\b', tail) is not None,
        "summary 是 details 的第一个子元素（浏览器才会渲染为折叠标题）")
    # 4.3 的「更早 N 期」折叠条不应被误当作模块外壳
    chk(new.count('blk-fold-more') <= 2, "4.3 更早期折叠条未与模块外壳混淆")

    # 2) 内部季报全部保留且仍默认收起
    # 排除外壳：兼容 class="blk-fold" / class="blk-fold blk-fold-pool" 两种写法
    _no_wrap = r'(?![^>]*\bclass="[^"]*\bblk-fold\b)'
    n_det = len(re.findall(r'<details\b' + _no_wrap, blk))
    n_det_open = len(re.findall(r'<details\b' + _no_wrap + r'[^>]*\bopen\b', blk))
    n_sec = len(re.findall(r'<section\b', blk))
    chk(n_sec == 23, f"模块内仍有 23 个季报 <section>（实测 {n_sec}）")
    chk(n_det == 23, f"模块内仍有 23 个内层 <details>（实测 {n_det}）")
    chk(n_det_open == 0, f"内层季报 all default-collapsed（open 数 = {n_det_open}）")

    # 3) 标签配平
    for tag, op, cl in (("details", r'<details\b', '</details>'),
                        ("div", r'<div\b', '</div>'),
                        ("summary", r'<summary\b', '</summary>'),
                        ("section", r'<section\b', '</section>')):
        o, c = len(re.findall(op, new)), len(re.findall(cl, new))
        oo, cc = len(re.findall(op, old)), len(re.findall(cl, old))
        chk(o - oo == c - cc, f"<{tag}> 增量配平：open +{o-oo} / close +{c-cc}")

    # 4) 模块内容逐字保留（兼容平台规范化后的属性写法）
    old_hi = old.find(H2_POOL)
    old_h2e = old.find('</h2>', old_hi) + len('</h2>')
    old_ni = old.find(H2_NEXT)
    old_nxt = old.rfind('<h2', 0, old_ni)
    old_body = old[old_h2e:old_nxt].strip()
    new_body = blk.strip()
    mb = re.search(r'<div\b[^>]*\bclass="blk-fold-b"[^>]*>', new_body)
    if changed:
        # 输入未带壳 → old_body 是裸的 23 个 section，应与壳内文本完全一致
        new_inner = (new_body[mb.end():new_body.rfind('</div></details>')].strip()
                     if mb else '')
        chk(mb is not None and new_inner == old_body,
            f"23 个季报内容逐字保留（{len(old_body):,} chars）")
    else:
        # 输入已带壳 → 本轮应零变化
        chk(new_body == old_body, f"已带壳：模块区内容零变化（{len(old_body):,} chars）")
        chk(new == old, "整页零变化（幂等）")

    # 5) 后续章节（三、四、五）完全未动
    chk(new[nxt:] == old[old_nxt:], "三/四/五章节及其后全部内容逐字未变")

    # 6) CSS 只注入一次
    chk(new.count('.blk-fold{') == 1, "新增 CSS 注入且仅注入一次")

    # 7) 幂等：再跑一次必须零变化
    again, changed2 = wrap_page(new)
    chk(changed2 is False and again == new, "幂等复跑 = 零变化")

    print("\n验证结果:", "ALL OK" if ok else "存在 NG")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check", action="store_true", help="只验证不写出")
    args = ap.parse_args()

    old = open(args.base, encoding='utf-8').read()
    print(f"读取 {args.base}: {len(old):,} chars")
    new, changed = wrap_page(old)
    if not verify(old, new, changed):
        raise SystemExit("!! 离线验证未通过，未写出")
    if args.check:
        print("\n--check 模式，未写出文件")
        return
    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        f.write(new)
    print(f"\n已写出 {args.out}: {len(new):,} chars (Δ {len(new)-len(old):+,})")


if __name__ == "__main__":
    main()
