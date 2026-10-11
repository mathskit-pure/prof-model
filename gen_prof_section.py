# -*- coding: utf-8 -*-
"""
把「盈利能力Top20等权组合」结果并入回测页面，三处改动（全部幂等，可重复运行）：
  1) 回测模块组合列表：在「质量Top20等权」下一行插入该组合的绩效指标行；
  2) 回测净值图：向 BT 数据加入该组合净值序列，并在 SVG 中补画曲线 + 图例；
  3) 4.3 节：仅保留持仓变动明细（绩效指标已归入上表，不再重复展示 KPI 卡片）。
"""
import sys, os, json, html, re, string, random, argparse
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import WORK  # noqa: E402  路径：本机 Windows 与云端 Linux 通用

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROF = os.path.join(WORK, "prof")
PAGE = os.path.join(WORK, "pool", "pool_page.html")
OUT = os.path.join(WORK, "pool", "pool_page_prof.html")
N_SHOW_QUAL = 8          # 与质量Top20一致：最近 8 个调仓日
PROF_KEY = '盈利能力Top40'          # 表格/图例中的名称
PROF_COLOR = '#00acc1'                  # 与其他 7 条曲线均可区分
SECTION_MARK = '4.3　盈利能力Top40组合'
ANCHOR5 = '五、如何更新最新一季股池'


# ===== 以下 change_table / pct_span 与线上 4.2 渲染逻辑逐字一致 =====
def pct_span(v, d=2):
    """涨跌幅按 A 股习惯：涨红、跌绿。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "<span class='mut'>-</span>"
    col = "up" if v > 0 else ("dn" if v < 0 else "mut")
    sign = "+" if v > 0 else ""
    return f"<span class='{col}'>{sign}{v * 100:.{d}f}%</span>"


def change_table(days, hold_df, rm_df, n_label, note_map=None, show_join=False,
                 start_idx=0, with_legend=True):
    """一行一期的持仓变动表：调仓日 | 本期持仓（新增标红）| 本期剔除（标绿+累计涨跌幅）"""
    if hold_df is None or hold_df.empty or not days:
        return "<p class='muted'>暂无数据</p>"
    rows5 = []
    for di, day in enumerate(days):
        h = hold_df[hold_df["调仓日"] == day].sort_values("次序")
        names, n_new = [], 0
        for _, r in h.iterrows():
            nm = html.escape(str(r["名称"]))
            is_new = str(r.get("状态", "")) == "新增"
            n_new += int(is_new)
            wv = r.get("建仓权重")
            ws = "" if (wv is None or pd.isna(wv)) else \
                f"<span class='wt'>{float(wv) * 100:.2f}%</span>"
            names.append(f"<span class='nm-new'>{nm}</span>{ws}" if is_new
                         else f"<span class='nm'>{nm}</span>{ws}")
        outs, n_out = [], 0
        if rm_df is None or rm_df.empty:
            g = None
        else:
            g = rm_df[rm_df["调仓日"] == day].sort_values("区间涨跌幅", ascending=False)
            n_out = len(g)
            for _, r in g.iterrows():
                join = ""
                if show_join:
                    ed = r.get("建仓日")
                    if ed is not None and not pd.isna(ed) and str(ed) != "nan":
                        join = (f"<span class='join'>建仓 {html.escape(str(ed))}</span>")
                outs.append(f"<span class='nm-out'>{html.escape(str(r['名称']))}</span>"
                            f"{join} {pct_span(r['区间涨跌幅'])}")
        # start_idx：本段在全表中的起始行号，保证「倒数第 N 期」跨段连续编号
        tag = "最新一期" if (di + start_idx) == 0 else f"倒数第 {di + start_idx + 1} 期"
        note = f"<span class='cnt'>{(note_map or {}).get(day, '')}</span>" if note_map else ""
        rows5.append(
            f"<tr><td class='day'>{day}<span class='pill'>{tag}</span>{note}</td>"
            f"<td class='cell'>{'、'.join(names)}"
            f"<span class='cnt'>{len(h)} 只 · 新增 {n_new}</span></td>"
            f"<td class='cell'>{'、'.join(outs) if outs else '<span class=\"mut\">—</span>'}"
            f"<span class='cnt'>{n_out} 只</span></td></tr>")
    join_tip = ("；其后「建仓 xxxx-xx-xx」为加入持仓的调仓日，数字为「建仓日 → 剔除日」累计涨跌幅"
                if show_join else
                "，其后数字为「建仓日 → 剔除日」累计涨跌幅")
    legend = (
        "<div class='legend'>"
        "<span class='nm-new'>红色</span> = 本期相较上期新纳入"
        "<span class='nm-out' style='margin-left:14px'>绿色</span> = 本期被剔除"
        f"{join_tip}"
        "<span class='mut' style='margin-left:14px'>股票名称后百分比＝建仓权重"
        "（40 只等权，每只 2.50%）</span>"
        "<span class='mut' style='margin-left:14px'>（涨跌幅按 A 股习惯：红涨绿跌）</span></div>"
        if with_legend else "")
    return (
        legend +
        "<table class='tbl tbl5'><thead><tr>"
        f"<th class='c-day'>调仓日</th><th class='c-hold'>本期持仓（{n_label}）</th>"
        "<th class='c-out'>本期剔除（较上期卖出 · 累计涨跌幅）</th>"
        f"</tr></thead><tbody>{''.join(rows5)}</tbody></table>")


# ===== 通用工具 =====
_AL = string.ascii_letters + string.digits


def nid_maker(page):
    used = set(re.findall(r'data-page-node-id="([A-Za-z0-9]{22})"', page)) | \
           set(re.findall(r'<!--pnid:([A-Za-z0-9]{22})-->', page))

    def make():
        while True:
            v = ''.join(random.choice(_AL) for _ in range(22))
            if v not in used:
                used.add(v)
                return v
    return make


def load_metrics():
    """从 prof_summary.csv 读取六项指标，按页面既有格式渲染。"""
    sp = os.path.join(PROF, "prof_summary.csv")
    if not os.path.exists(sp):
        raise SystemExit("!! 缺少 prof_summary.csv，请先跑 backtest_prof.py")
    r = pd.read_csv(sp).iloc[0]

    def pc(x):
        return f"{float(x)*100:.2f}%"

    def nm(x):
        return f"{float(x):.2f}"
    return [pc(r['累计收益']), pc(r['年化收益']), pc(r['年化波动']),
            pc(r['最大回撤']), nm(r['夏普比率']), nm(r['卡玛比率'])]


# ===== 改动 1：组合列表插入绩效行 =====
def upsert_metrics_row(page):
    mk = page.find('累计收益')
    if mk < 0:
        raise SystemExit("!! 未找到组合列表表头「累计收益」")
    ts = page.rfind('<table', 0, mk)
    te = page.find('</table>', mk)
    tbl = page[ts:te + 8]
    make_id = nid_maker(page)

    rows = list(re.finditer(r'<tr data-page-node-id="([^"]+)">(.*?)</tr>', tbl, re.S))
    names = [re.sub(r'<[^>]+>|<!--.*?-->', '', m.group(2).split('</td>')[0]).strip()
             for m in rows]

    new_row = None
    # 已存在则更新数值
    if any(n.startswith(PROF_KEY) for n in names):
        # 已存在则整体重建该行。注意线上平台会在单元格内容里注入 <!--pnid--> 注释，
        # 逐个解析内容易失效，这里改为直接重建，避免依赖内容的任何格式假设。
        m = rows[[i for i, n in enumerate(names) if n.startswith(PROF_KEY)][0]]
        vals = load_metrics()
        make_id = nid_maker(page)
        own = {int(x) for x in re.findall(r'id="r(\d+)_\d"', m.group(2))}
        if own:
            ri = own.pop()
        else:
            used_idx = {int(x) for x in re.findall(r'id="r(\d+)_\d"', tbl)}
            ri = max(used_idx) + 1 if used_idx else 0
        name_cell = (f'<td data-page-node-id="{make_id()}">'
                     f'<b data-page-node-id="{make_id()}">{PROF_KEY}</b></td>')
        num_cells = ''.join(
            f'<td data-page-node-id="{make_id()}" class="num" id="r{ri}_{c}">{v}</td>'
            for c, v in enumerate(vals))
        new_row = f'<tr data-page-node-id="{make_id()}">{name_cell}{num_cells}</tr>'
        return page[:ts] + tbl[:m.start()] + new_row + tbl[m.end():] + page[te + 8:]

    # 否则插到「质量Top20等权」之后
    qidx = [i for i, n in enumerate(names) if n.startswith('质量Top28组合')]
    if not qidx:
        raise SystemExit("!! 组合列表中未找到「质量Top28组合」行")
    qi = qidx[0]
    vals = load_metrics()
    anchor_row = rows[qi]
    # 新行沿用 0..6 之外的最小可用索引
    used_idx = {int(x) for x in re.findall(r'id="r(\d+)_\d"', tbl)}
    ri = max(used_idx) + 1
    name_cell = (f'<td data-page-node-id="{make_id()}">'
                 f'<b data-page-node-id="{make_id()}">{PROF_KEY}</b></td>')
    num_cells = ''.join(
        f'<td data-page-node-id="{make_id()}" class="num" id="r{ri}_{c}">{v}</td>'
        for c, v in enumerate(vals))
    new_row = f'<tr data-page-node-id="{make_id()}">{name_cell}{num_cells}</tr>'
    ins_at = anchor_row.end()
    return page[:ts] + tbl[:ins_at] + new_row + tbl[ins_at:] + page[te + 8:]


# ===== 改动 2：图表数据 + 曲线 + 图例 =====
def _bt_span(page):
    a = page.find('var BT=')
    if a < 0:
        raise SystemExit("!! 未找到图表数据 var BT=")
    i = page.index('{', a)
    depth = 0
    instr = esc = False
    for k in range(i, len(page)):
        ch = page[k]
        if instr:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                instr = False
        else:
            if ch == '"':
                instr = True
            elif ch in '{[':
                depth += 1
            elif ch in '}]':
                depth -= 1
                if depth == 0:
                    return i, k + 1
    raise SystemExit("!! BT 数据括号不匹配")


# ===== 改动 4：组合列表行 id 必须与 BT.order 下标一致 =====
def fix_row_ids(page):
    """页面 JS 的 update() 用 setRow(s,...) 写 id="r{s}_{c}"，s 是 BT.order 的下标，
    与行的【显示位置】无关（旧版「动量轮动·AFGI仓位」显示第 2 行、id 却是 r6）。
    插入 PROF 到 order 第 3 位后，其后所有组合下标 +1，若不同步重排 id：
      · PROF 行会被写进 AFGI 仓位的数据；
      · AFGI 起算日为 2023-02-09，区间结束日早于它时该行被置 '—'
        → 表现为「2019–2022 盈利能力Top20 数据缺失」。
    因此这里按 order 下标统一重排全部行 id（幂等、可自愈）。"""
    i0, i1 = _bt_span(page)
    bt = json.loads(page[i0:i1])
    order, label = bt['order'], bt['label']
    name2idx = {}
    for k, v in label.items():
        if k in order:
            name2idx[str(v).strip()] = order.index(k)

    mk = page.find('累计收益')
    ts = page.rfind('<table', 0, mk)
    te = page.find('</table>', mk)
    if mk < 0 or ts < 0 or te < 0:
        raise SystemExit("!! 未找到组合列表表格")

    def _name(row):
        m = re.search(r'<td\b[^>]*>(.*?)</td>', row, re.S)
        return re.sub(r'<[^>]+>|<!--.*?-->', '', m.group(1)).strip() if m else ''

    seen = {}

    def _fix(m):
        row = m.group(0)
        nm = _name(row)
        if not nm or nm not in name2idx:
            return row                       # 表头行 / 未识别行：原样保留
        idx = name2idx[nm]
        seen[nm] = idx
        return re.sub(r'id="r\d+_(\d)"', lambda x: 'id="r%d_%s"' % (idx, x.group(1)), row)

    tbl = page[ts:te + 8]
    new_tbl = re.sub(r'<tr\b[^>]*>.*?</tr>', _fix, tbl, flags=re.S)
    page = page[:ts] + new_tbl + page[te + 8:]

    # 校验：每个组合都拿到正确下标，且下标互不重复
    if len(set(seen.values())) != len(seen):
        raise SystemExit("!! 行 id 下标重复，终止：" + str(seen))
    missing = [k for k in order if label.get(k, '').strip() not in seen]
    if missing:
        raise SystemExit("!! 以下组合未在表格中匹配到行：" + str(missing))
    print("  行 id 对齐:", {k: v for k, v in sorted(seen.items(), key=lambda x: x[1])})
    return page


def upsert_chart(page):
    # --- nav 数据 ---
    nvp = os.path.join(PROF, "prof_nav.csv")
    if not os.path.exists(nvp):
        raise SystemExit("!! 缺少 prof_nav.csv")
    nv = pd.read_csv(nvp, index_col=0)
    nv.index = pd.to_datetime(nv.index).strftime('%Y-%m-%d')
    nav = list(nv.iloc[:, 0].astype(float))

    i0, i1 = _bt_span(page)
    bt = json.loads(page[i0:i1])
    dates = bt['dates']
    if list(nv.index) != dates:
        raise SystemExit("!! prof_nav 日期与图表 dates 不一致")
    vals = [round(float(v), 4) for v in nav]

    # --- 更新 BT ---
    if PROF_KEY not in bt['order']:
        pos = bt['order'].index('质量Top28组合') + 1
        bt['order'].insert(pos, PROF_KEY)
    bt.setdefault('label', {})[PROF_KEY] = PROF_KEY
    bt.setdefault('color', {})[PROF_KEY] = PROF_COLOR
    bt.setdefault('series', {})[PROF_KEY] = vals
    page = page[:i0] + json.dumps(bt, ensure_ascii=False,
                                  separators=(',', ':')) + page[i1:]

    # --- 更新 SVG 曲线（与既有 confirmed 线性映射一致）---
    A, B = 317.5600, -42.2861
    X0, X1 = 56.0, 770.0
    n = len(dates)
    pts = ' '.join(
        f"{X0 + k * (X1 - X0) / (n - 1):.1f},{A + B * vals[k]:.1f}" for k in range(n))
    make_id = nid_maker(page)
    new_pl = (f'<polyline data-page-node-id="{make_id()}" fill="none" points="{pts}" '
              f'stroke="{PROF_COLOR}" stroke-width="2"></polyline>')

    old = re.search(r'<polyline[^>]*stroke="%s"[^>]*>(?:</polyline>)?' % PROF_COLOR, page)
    if old:
        page = page[:old.start()] + new_pl + page[old.end():]
    else:
        # 放在「质量Top20等权」之后，与 order 一致
        ref = re.search(r'<polyline[^>]*stroke="#0f9d58"[^>]*>(?:</polyline>)?', page)
        if not ref:
            raise SystemExit("!! SVG 中未找到质量Top20等权曲线")
        page = page[:ref.end()] + new_pl + page[ref.end():]

    # --- 更新图例（插到质量Top20等权之后，其后条目下移 22px；已存在则跳过）---
    sv = page.find('<svg', page.find('id="btChart"') - 200)
    sve = page.find('</svg>', sv)
    svg = page[sv:sve]
    lines = list(re.finditer(r'<line[^>]*x1="782"[^>]*>', svg))
    texts = list(re.finditer(r'<text[^>]*x="806"[^>]*>[\s\S]*?</text>', svg))
    if len(lines) != len(texts) or not lines:
        raise SystemExit("!! 图例结构与预期不符")
    if not any(PROF_KEY in m.group(0) for m in texts):
        qi = 2   # BT.order 中第 3 项 = 质量Top20等权
        base_y = float(re.search(r'y1="([\d.]+)"', lines[qi].group(0)).group(1))
        cut_y = base_y + 22
        # 自后向前替换，保证靠前的偏移量始终有效
        for grp in (lines, texts):
            for m in reversed(grp):
                yv = float(re.search(r'(?:y1|y)="([\d.]+)"', m.group(0)).group(1))
                if yv >= cut_y - 0.01:
                    tag = m.group(0)
                    for pat in (r'(y1=")[\d.]+(")', r'(y2=")[\d.]+(")', r'( y=")[\d.]+(")'):
                        tag = re.sub(pat, lambda mm: mm.group(1) + f'{yv + 22:g}' + mm.group(2), tag)
                    svg = svg[:m.start()] + tag + svg[m.end():]
        # 以「质量Top20等权」的图例为模板，保持属性与 pnid 注释风格一致
        tmpl_l = lines[qi].group(0)
        head_t = texts[qi].group(0)[:texts[qi].group(0).index('>') + 1]
        new_l = re.sub(r'data-page-node-id="[^"]*"', f'data-page-node-id="{make_id()}"', tmpl_l)
        new_l = re.sub(r'stroke="#[0-9a-fA-F]{6}"', f'stroke="{PROF_COLOR}"', new_l)
        new_l = re.sub(r'y1="[\d.]+"', f'y1="{base_y + 22:g}"', new_l)
        new_l = re.sub(r'y2="[\d.]+"', f'y2="{base_y + 22:g}"', new_l)
        new_head = re.sub(r'data-page-node-id="[^"]*"', f'data-page-node-id="{make_id()}"', head_t)
        new_head = re.sub(r' y="[\d.]+"', f' y="{base_y + 26:g}"', new_head)
        new_t = new_head + f'<!--pnid:{make_id()}-->' + PROF_KEY + '</text>'
        ins = texts[qi].end()   # 该位置之前的内容未被修改，偏移仍有效
        svg = svg[:ins] + new_l + new_t + svg[ins:]
    return page[:sv] + svg + page[sve:]


# ===== 改动 5：图例顺序 = 上方表格的组合顺序 =====
def _table_names(page):
    """按【显示顺序】返回组合列表表格里的行名称。"""
    mk = page.find('累计收益')
    ts = page.rfind('<table', 0, mk)
    te = page.find('</table>', mk)
    if mk < 0 or ts < 0 or te < 0:
        raise SystemExit("!! 未找到组合列表表格")
    out = []
    for m in re.finditer(r'<tr\b[^>]*>(.*?)</tr>', page[ts:te], re.S):
        tds = re.findall(r'<td\b[^>]*>(.*?)</td>', m.group(1), re.S)
        if not tds:
            continue
        nm = re.sub(r'<[^>]+>|<!--.*?-->', '', tds[0]).strip()
        if nm:
            out.append(nm)
    return out


def sync_order_to_table(page):
    """让 BT.order（决定折线图图例顺序）与组合列表表格的显示顺序一致。
    注意：order 下标同时决定 setRow(s) 写入 r{s}，因此本函数之后必须再跑 fix_row_ids。"""
    i0, i1 = _bt_span(page)
    bt = json.loads(page[i0:i1])
    label = bt['label']
    name2key = {str(v).strip(): k for k, v in label.items()}
    new_order = [name2key[n] for n in _table_names(page) if n in name2key]
    if len(new_order) != len(bt['order']) or set(new_order) != set(bt['order']):
        raise SystemExit(f"!! 表格顺序与 BT.order 组合集合不一致\n表格={new_order}\norder={bt['order']}")
    if new_order == bt['order']:
        print("  图例顺序已与表格一致，无需调整")
        return page
    bt['order'] = new_order
    page = page[:i0] + json.dumps(bt, ensure_ascii=False, separators=(',', ':')) + page[i1:]
    print("  图例顺序 → 表格顺序:", [bt['label'][k] for k in new_order])
    return page


def sync_svg_legend(page):
    """同步静态 SVG 图例（颜色色块 + 文字）到 BT.order 的顺序。
    JS 的 draw() 加载时会重绘图例，此处同步是为了首屏/无 JS 时也一致。"""
    i0, i1 = _bt_span(page)
    bt = json.loads(page[i0:i1])
    order, label, color = bt['order'], bt['label'], bt['color']

    anchor = page.find('id="btChart"')
    sv = page.find('<svg', max(0, anchor - 200))
    sve = page.find('</svg>', sv)
    svg = page[sv:sve]
    lines = list(re.finditer(r'<line[^>]*x1="782"[^>]*>', svg))
    texts = list(re.finditer(r'<text[^>]*x="806"[^>]*>[\s\S]*?</text>', svg))
    # 注：BT.order 可能包含由 19:00 主流水线新增、但其静态 SVG 图例尚未补齐的序列
    # （如「联合仓位」）。JS 的 draw() 在加载时会依据 BT.order 重绘图例，因此此处静态图例
    # 只需同步【已有】条目，不再强求 len(lines)==len(order)；缺失条目的序列直接跳过。
    if not lines or len(lines) != len(texts):
        raise SystemExit(f"!! 图例结构异常：line={len(lines)} text={len(texts)} order={len(order)}")

    def tname(m):
        return re.sub(r'<[^>]+>|<!--.*?-->', '', m.group(0)).strip()

    by_name = {}
    for l, t in zip(lines, texts):
        yl = float(re.search(r'y1="([\d.]+)"', l.group(0)).group(1))
        yt = float(re.search(r'\by="([\d.]+)"', t.group(0)).group(1))
        by_name[tname(t)] = {'line': l.group(0), 'text': t.group(0), 'dy': yt - yl}

    make_id = nid_maker(page)
    parts = []
    for p, k in enumerate(order):
        it = by_name.get(str(label[k]).strip())
        if it is None:
            # 静态图例中无该序列条目（如主流水线新增的「联合仓位」），跳过；
            # 该序列由 JS draw() 动态绘制，不影响首屏外的展示。
            continue
        yl = 42 + p * 22
        ln = re.sub(r'stroke="#[0-9a-fA-F]{6}"', f'stroke="{color[k]}"', it['line'])
        ln = re.sub(r'y1="[\d.]+"', f'y1="{yl:g}"', ln)
        ln = re.sub(r'y2="[\d.]+"', f'y2="{yl:g}"', ln)

        def repl(m, _k=k):
            pn = re.search(r'<!--pnid:[^>]*-->', m.group(2))
            pnid = pn.group(0) if pn else f'<!--pnid:{make_id()}-->'
            return m.group(1) + pnid + label[_k] + m.group(3)
        tx = re.sub(r'\by="([\d.]+)"', f'y="{yl + it["dy"]:g}"', it['text'], count=1)
        tx = re.sub(r'(>)([\s\S]*?)(</text>)', repl, tx, count=1)
        parts.append(ln + tx)

    svg = svg[:lines[0].start()] + ''.join(parts) + svg[texts[-1].end():]
    print("  SVG 图例顺序:", [str(label[k]) for k in order])
    return page[:sv] + svg + page[sve:]


# ===== 改动 3：4.3 持仓明细章节（去掉 KPI 卡片）=====
def upsert_holdings(page):
    hold = pd.read_csv(os.path.join(PROF, "prof_top40.csv"), dtype={"代码": str})
    hold["调仓日"] = hold["调仓日"].astype(str)
    rm = None
    rp = os.path.join(PROF, "prof_removed.csv")
    if os.path.exists(rp):
        rm = pd.read_csv(rp, dtype={"代码": str})
        rm["调仓日"] = rm["调仓日"].astype(str)
    # 注意：这里必须渲染【全部调仓期】，不能只取最近 N_SHOW_QUAL 期 ——
    # 早期版本只取 8 期，导致 2019-11-01 → 2023-11-01 的 13 期在页面上看不到
    #（净值曲线是完整的，于是出现「图正常、表缺数据」的错觉）。
    days_all = sorted(hold["调仓日"].unique())[::-1]        # 最新在前
    days_recent = days_all[:N_SHOW_QUAL]
    days_older = days_all[N_SHOW_QUAL:]
    note_map = {r["调仓日"]: r["报告期"] for _, r in hold.iterrows()}
    q_recent = change_table(days_recent, hold, rm, "40 只", note_map,
                            show_join=True, start_idx=0)
    q_older = change_table(days_older, hold, rm, "40 只", note_map,
                           show_join=True, start_idx=N_SHOW_QUAL, with_legend=False)
    span = f"{days_all[-1]} → {days_all[0]}" if days_all else ""

    # 更早的期放在默认收起的折叠里：数据完整保留，又不撑长页面
    older_block = ""
    if days_older:
        # 用 blk-fold-more 与季度股池大模块的 blk-fold-pool 区分，避免互相误判
        older_block = (
            '<details class="blk-fold blk-fold-more"><summary class="blk-fold-s">'
            '<span class="blk-fold-i">&#9654;</span>'
            f'<span class="blk-fold-t">更早 {len(days_older)} 期</span>'
            f'<span class="blk-fold-n">{days_older[-1]} → {days_older[0]}</span>'
            '<span class="blk-fold-a">'
            '<span class="blk-fold-off">点击展开</span>'
            '<span class="blk-fold-on">点击收起</span>'
            '</span></summary>'
            f'<div class="blk-fold-b">{q_older}</div></details>')
    q5 = q_recent + older_block

    section = (
        f'<div class="sub-h" style="font-size:15px;margin-top:26px">'
        f'{SECTION_MARK}（持仓 40 只 · 季度买入持有 · 共 {len(days_all)} 期 · {span}）</div>'
        '<div class="note" style="margin-bottom:10px">评分来源：<b>A 股盈利能力评分模型（PROF）</b>'
        '—— 八因子综合分（盈利能力 55% / 保守投资 20% / 价值 15% / 规模 10%）。'
        '选股与换仓规则：当期股池内按 PROF 综合得分降序取前 40 只，'
        '单个申万三级行业最多 2 只（出现第 3 只时跳过其中得分最低者并按序补录）；'
        '<b>每个季度调仓一次</b>（调仓日＝报告期信息可得日后的首个交易日），'
        '同一季度内持仓与成分不变，换仓同样权重滞后 1 日。'
        '该组合的六项绩效指标见<b>第三节组合列表</b>，净值曲线见<b>回测净值曲线图</b>。'
        f'下方列出<b>全部 {len(days_all)} 期</b>（{span}）：'
        f'最近 {len(days_recent)} 期常显，'
        + (f'更早 {len(days_older)} 期收在折叠里，点击「更早 {len(days_older)} 期」展开。'
           if days_older else '') + '</div>'
        f'{q5}')

    # 移除已存在的旧 4.3 区块（含早期误放的 KPI 卡片）。
    # 注意：线上平台会对上传页面重新规范化（补 data-page-node-id、调整 style 空格），
    # 因此不能用固定字符串匹配开标签，改为按 class 属性做兼容查找。
    while True:
        mi = page.find(SECTION_MARK)
        if mi < 0:
            break
        cands = [m.start() for m in
                 re.finditer(r'<div[^>]*\bclass="[^"]*\bsub-h\b[^"]*"[^>]*>', page)
                 if m.start() < mi]
        ai = page.find(ANCHOR5)
        h2 = page.rfind('<h2', 0, ai)
        if not cands or h2 < 0 or h2 <= cands[-1]:
            raise SystemExit("!! 无法定位已有 4.3 区块边界，终止以免损坏页面")
        page = page[:cands[-1]] + page[h2:]
    ai = page.find(ANCHOR5)
    if ai < 0:
        raise SystemExit("!! 未找到插入锚点：" + ANCHOR5)
    h2 = page.rfind('<h2', 0, ai)
    return page[:h2] + "\n" + section + "\n" + page[h2:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=PAGE)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--holdings-only", action="store_true",
                    help="只重建 4.3 持仓明细（图表/统计表/图例由 refresh_page.py 负责）")
    args = ap.parse_args()

    page = open(args.base, encoding="utf-8", errors="replace").read()
    if args.holdings_only:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from gen_pool_fold import ensure_css
        page = upsert_holdings(page)
        page = ensure_css(page)
        open(args.out, "w", encoding="utf-8", newline="").write(page)
        print("已生成（仅 4.3 持仓明细）:", args.out, len(page), "chars")
        print("  4.3 区块数:", page.count(SECTION_MARK), "(应为 1)")
        return

    # 4.3 的「更早 N 期」折叠条复用 gen_pool_fold 的 .blk-fold 样式，
    # 这里保证样式一定存在（与 gen_pool_fold 的注入互相幂等）。
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gen_pool_fold import ensure_css

    page = open(args.base, encoding="utf-8", errors="replace").read()
    page = upsert_metrics_row(page)
    page = upsert_chart(page)
    page = sync_order_to_table(page)   # 图例顺序 = 表格顺序（须在表格行插入之后）
    page = sync_svg_legend(page)
    page = upsert_holdings(page)
    page = fix_row_ids(page)      # 必须在 sync_order_to_table 之后：行 id = order 下标
    page = ensure_css(page)
    open(args.out, "w", encoding="utf-8", newline="").write(page)

    print("已生成:", args.out, len(page), "chars")
    print("  组合列表含 PROF 行:", PROF_KEY in page.split('</table>')[0]
          if False else PROF_KEY in page)
    i0, i1 = _bt_span(page)
    bt = json.loads(page[i0:i1])
    print("  BT.order:", bt['order'])
    print("  PROF 序列点数:", len(bt['series'][PROF_KEY]), "色值:", bt['color'][PROF_KEY])
    pl = re.search(r'<polyline[^>]*stroke="%s"[^>]*>' % PROF_COLOR, page)
    print("  SVG 曲线点数:", len(re.findall(r'-?\d+\.\d', pl.group(0))) // 2)
    print("  图例含 PROF:", PROF_KEY in page[page.find('id="btChart"'):page.find('</svg>', page.find('id="btChart"'))])
    _cnt = page.count(SECTION_MARK)
    _mk = page.find(SECTION_MARK)
    ai0 = page.find(ANCHOR5)
    h2i = page.rfind('<h2', 0, ai0)
    _blk = page[_mk:h2i] if (0 < _mk < h2i) else ''
    print(f"  4.3 区块数: {_cnt} (应为 1) | 区块内残留 KPI 卡片: {'class=\"kpis\"' in _blk}")
    if _cnt != 1 or 'class="kpis"' in _blk:
        raise SystemExit("!! 4.3 区块数量或内容异常，已终止（未写出的半成品更安全）")


if __name__ == "__main__":
    main()
