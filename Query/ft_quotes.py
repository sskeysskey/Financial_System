#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ft_quotes.py —— Firstrade 本地数据读取层（Chart_input.py）

数据来源（均由 Chrome 插件 + bridge_server.py 落盘）:
    Modules/firstrade_positions.json   持仓快照（覆盖式）
    Modules/firstrade_watchlist.json   自选股「变更%」快照（覆盖式，1800+ 只）

显示优先级（build_market_items）:
    1) 该 symbol 在持仓里  -> 显示 成本 / 损益 / 日 / 总 / 仓位
    2) 不在持仓、但在自选股 -> 显示 盘前变更% / 现价
    3) 都没有              -> 视 FT_SHOW_MISS 决定是否显示灰色占位
"""
import os
import re
import json
import time

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
MODULES_DIR = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules")

FIRSTRADE_POSITIONS_FILE = os.path.join(MODULES_DIR, "firstrade_positions.json")
FIRSTRADE_WATCHLIST_FILE = os.path.join(MODULES_DIR, "firstrade_watchlist.json")

FT_DEBUG = os.environ.get("FT_DEBUG", "") == "1"
FT_SHOW_MISS = os.environ.get("FT_SHOW_MISS", "1") == "1"

# 自选股数据超过该小时数就打「N天前」标记
FT_STALE_HOURS = float(os.environ.get("FT_STALE_HOURS", "20"))

_CACHE = {}          # path -> (mtime, data)


# ----------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------
def _ft_norm_sym(s):
    """AAPL / brk.b / BRK-B 统一成大写且以 '-' 为分隔的形式"""
    return str(s).strip().upper().replace('.', '-')


def _norm_key(s):
    """比较用：去掉一切分隔符 BRK.B / BRK-B / BRKB -> BRKB"""
    return re.sub(r'[^A-Z0-9]', '', str(s).strip().upper())


def _load_json_cached(path):
    """按 mtime 缓存，避免 matplotlib 频繁重画时反复读盘"""
    try:
        mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
    except Exception:
        mtime = 0.0
    ent = _CACHE.get(path)
    if ent and ent[0] == mtime:
        return ent[1]
    data = {}
    if mtime:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except Exception as e:
            print(f"[FT] 读取 {os.path.basename(path)} 失败: {e}")
    _CACHE[path] = (mtime, data)
    return data


def _num(s):
    try:
        m = re.search(r'[-+]?\d[\d,]*\.?\d*', str(s).replace(' ', ''))
        return float(m.group(0).replace(',', '')) if m else None
    except Exception:
        return None


def _fmt_money(s):
    v = _num(s)
    if v is None:
        return str(s)
    if abs(v) >= 1e6:
        return f"{v/1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"{v/1e3:.1f}K"
    return f"{v:.0f}"


def _fmt_gainloss_amount(s):
    """损益金额格式化：自动带正负号，并兼顾大额缩写"""
    v = _num(s)
    if v is None:
        return str(s)
    if abs(v) >= 1e6:
        return f"{v/1e6:+.2f}M"
    if abs(v) >= 1e3:
        return f"{v/1e3:+.1f}K"
    return f"{v:+.2f}"


def _age_hours(ts):
    """兼容秒 / 毫秒时间戳"""
    try:
        t = float(ts)
    except Exception:
        return None
    if t <= 0:
        return None
    if t > 1e11:          # 毫秒
        t /= 1000.0
    return (time.time() - t) / 3600.0


def _sign_color(s, theme):
    v = _num(s)
    if v is None:
        return theme['text_bright']
    if v > 0:
        return theme['accent_red']        # 红涨
    if v < 0:
        return theme['accent_green']      # 绿跌
    return theme['text_bright']


# ----------------------------------------------------------------------
# 持仓
# ----------------------------------------------------------------------
def get_firstrade_position(symbol):
    """读取插件回传的真实持仓数据，返回 dict 或 None"""
    if not symbol:
        return None
    data = _load_json_cached(FIRSTRADE_POSITIONS_FILE)
    if not data:
        if FT_DEBUG:
            print(f"[FT] 持仓文件为空或不存在: {FIRSTRADE_POSITIONS_FILE}")
        return None
    meta_ts = (data.get('_meta') or {}).get('updated_at')
    target = _norm_key(symbol)
    for k, v in data.items():
        if str(k).startswith('_') or not isinstance(v, dict):
            continue
        if _norm_key(k) == target:
            out = dict(v)
            out.setdefault('symbol', str(k).upper())
            if not out.get('updated_at'):        # ★ 逐条 updated_at 已取消，从 _meta 回填
                out['updated_at'] = meta_ts
            if FT_DEBUG:
                print(f"[FT] 命中持仓 {k}: {out}")
            return out
    if FT_DEBUG:
        keys = [k for k in data.keys() if not str(k).startswith('_')]
        print(f"[FT] 持仓未找到 {symbol}（共 {len(keys)} 条）: {keys[:25]}")
    return None


# ----------------------------------------------------------------------
# 自选股行情（变更%）
# ----------------------------------------------------------------------
def get_watchlist_quote(symbol):
    """返回 {'symbol','change_pct','change_pct_num','last','updated_at'} 或 None"""
    if not symbol:
        return None
    data = _load_json_cached(FIRSTRADE_WATCHLIST_FILE)
    if not data:
        return None
    quotes = data.get('quotes')
    if not isinstance(quotes, dict):
        quotes = {k: v for k, v in data.items()
                  if isinstance(v, dict) and not str(k).startswith('_')}
    target = _norm_key(symbol)
    meta_ts = (data.get('_meta') or {}).get('updated_at')
    for k, v in quotes.items():
        if not isinstance(v, dict):
            continue
        if _norm_key(k) == target:
            out = dict(v)
            out.setdefault('symbol', str(k).upper())
            if not out.get('updated_at'):
                out['updated_at'] = meta_ts
            if FT_DEBUG:
                print(f"[FT] 命中自选股行情 {k}: {out}")
            return out
    if FT_DEBUG:
        print(f"[FT] 自选股行情未找到 {symbol}（共 {len(quotes)} 条）")
    return None


# ----------------------------------------------------------------------
# 供图表副标题使用：[(文本, 颜色, 粗细), ...]
# ----------------------------------------------------------------------
def _items_from_position(pos, theme):
    raw = pos.get('raw') or {}

    def _pick(*keys):
        for k in keys:
            v = pos.get(k)
            if v not in (None, '', '--'):
                return str(v)
        for k in keys:
            v = raw.get(k)
            if v not in (None, '', '--'):
                return str(v)
        return None

    cost_val = _pick('cost', 'totalCost')
    
    # 优先获取金额型损益，若从 raw.gainloss 取，需确认不是百分比字符串
    gl_amt_val = _pick('gainloss_amount')
    if not gl_amt_val:
        raw_gl = raw.get('gainloss')
        if raw_gl not in (None, '', '--') and not str(raw_gl).strip().endswith('%'):
            gl_amt_val = str(raw_gl)

    day_val = _pick('day_change', 'changePercent')
    gl_val = _pick('gainloss', 'gainlossPercent')
    alloc_val = _pick('allocation', 'allocationPercent')

    items = []
    if cost_val:
        items.append((f"成本 {_fmt_money(cost_val)}", theme['accent_yellow'], 'bold'))
    if gl_amt_val:
        items.append((f"损益 {_fmt_gainloss_amount(gl_amt_val)}", _sign_color(gl_amt_val, theme), 'bold'))
    if day_val:
        items.append((f"日{day_val}", _sign_color(day_val, theme), 'bold'))
    if gl_val:
        items.append((f"总{gl_val}", _sign_color(gl_val, theme), 'bold'))
    if alloc_val:
        items.append((f"仓{alloc_val}", theme['accent_cyan'], 'normal'))

    age = _age_hours(pos.get('updated_at'))
    if age is not None and age > FT_STALE_HOURS:
        items.append((f"({age/24:.0f}天前)", theme['border'], 'normal'))
    return items


def _items_from_watchlist(q, theme):
    txt = q.get('change_pct')
    if txt in (None, '', '--'):
        n = q.get('change_pct_num')
        txt = f"{float(n):+.2f}%" if isinstance(n, (int, float)) else None
    if not txt:
        return []

    items = [(f"盘前 {txt}", _sign_color(txt, theme), 'bold')]
    last = q.get('last')
    if last not in (None, '', '--'):
        items.append((f"现价 {last}", theme['text_light'], 'normal'))

    age = _age_hours(q.get('updated_at'))
    if age is not None and age > FT_STALE_HOURS:
        items.append((f"({age/24:.0f}天前)", theme['border'], 'normal'))
    return items


def build_market_items(symbol, theme, show_miss=None):
    """
    图表副标题左侧一行的内容。
    持仓优先；无持仓则用自选股「变更%」；都没有按 show_miss 决定占位。
    """
    if show_miss is None:
        show_miss = FT_SHOW_MISS

    pos = get_firstrade_position(symbol)
    if pos:
        items = _items_from_position(pos, theme)
        if items:
            return items

    q = get_watchlist_quote(symbol)
    if q:
        items = _items_from_watchlist(q, theme)
        if items:
            return items

    if show_miss:
        return [("持仓/自选: 无数据", theme['border'], 'normal')]
    return []

# ----------------------------------------------------------------------
# 供 Check_Group.py 使用：整份持仓 + 数值解析 + 格式化
# ----------------------------------------------------------------------
def load_all_positions():
    """返回 (positions: {SYMBOL: rec}, meta: dict)；symbol 统一为大写 '-' 形式"""
    data = _load_json_cached(FIRSTRADE_POSITIONS_FILE)
    meta = data.get('_meta') or {}
    out = {}
    for k, v in data.items():
        if str(k).startswith('_') or not isinstance(v, dict):
            continue
        sym = _ft_norm_sym(v.get('symbol') or k)
        if not sym:
            continue
        rec = dict(v)
        rec['symbol'] = sym
        if not rec.get('updated_at'):
            rec['updated_at'] = meta.get('updated_at')
        out[sym] = rec
    return out, meta


def position_num(rec, *keys):
    """按优先级从记录里取第一个可解析成数字的字段（'+7.16%' -> 7.16, '6,000.00' -> 6000.0）"""
    if not isinstance(rec, dict):
        return None
    for k in keys:
        v = rec.get(k)
        if v in (None, '', '--'):
            continue
        n = _num(v)
        if n is not None:
            return n
    return None


def fmt_money(s):
    """6,000.00 -> 6.0K / 1,234,567 -> 1.23M"""
    return _fmt_money(s)


def fmt_signed(s):
    return _fmt_gainloss_amount(s)

# ----------------------------------------------------------------------
# 自选股「分组归属」：该 symbol 在 Firstrade 哪些 watchlist 分组里
#   数据：Modules/firstrade_wl_membership.json（bridge_server.py 写入）
# ----------------------------------------------------------------------
FIRSTRADE_WL_MEMBERSHIP_FILE = os.path.join(MODULES_DIR, "firstrade_wl_membership.json")
FT_MEMBER_STALE_HOURS = float(os.environ.get("FT_MEMBER_STALE_HOURS", "72"))
_MEMBER_INDEX = {"mtime": None, "index": {}, "order": [], "groups": {}}


def membership_signature():
    """文件 mtime，图表用它判断是否需要重画归属行"""
    try:
        return os.path.getmtime(FIRSTRADE_WL_MEMBERSHIP_FILE) if os.path.exists(FIRSTRADE_WL_MEMBERSHIP_FILE) else 0.0
    except Exception:
        return 0.0


def _membership_index():
    data = _load_json_cached(FIRSTRADE_WL_MEMBERSHIP_FILE)
    mtime = (_CACHE.get(FIRSTRADE_WL_MEMBERSHIP_FILE) or (None,))[0]
    if _MEMBER_INDEX["mtime"] is not None and _MEMBER_INDEX["mtime"] == mtime:
        return _MEMBER_INDEX
    groups = data.get('groups') if isinstance(data.get('groups'), dict) else {}
    idx = {}
    for g, rec in groups.items():
        if not isinstance(rec, dict):
            continue
        for s in rec.get('symbols') or []:
            idx.setdefault(_norm_key(s), []).append(g)
    page = [str(x) for x in (data.get('page_groups') or []) if str(x) in groups]
    order = page + sorted(g for g in groups if g not in page)
    _MEMBER_INDEX.update({"mtime": mtime, "index": idx, "order": order,
                          "groups": {g: groups[g] for g in order if isinstance(groups[g], dict)}})
    return _MEMBER_INDEX


def get_watchlist_membership(symbol):
    """返回 {'groups': [所在分组], 'unsure': [未完整扫描且未命中的分组], 'oldest_age_h': float}
       无任何归属数据时返回 None"""
    if not symbol:
        return None
    ix = _membership_index()
    if not ix["groups"]:
        return None
    hit = set(ix["index"].get(_norm_key(symbol), []))
    inside = [g for g in ix["order"] if g in hit]
    unsure = [g for g in ix["order"] if g not in hit and not ix["groups"].get(g, {}).get('complete')]
    ages = [_age_hours(rec.get('updated_at')) for rec in ix["groups"].values()]
    ages = [a for a in ages if a is not None]
    if FT_DEBUG:
        print(f"[FT] 分组归属 {symbol}: {inside} 未全扫 {unsure}")
    return {"groups": inside, "unsure": unsure, "oldest_age_h": max(ages) if ages else None}


def _group_color(name, theme):
    n = str(name)
    low = n.lower()
    if 'short' in low:
        return theme['accent_purple']
    if '卖' in n:
        return theme['accent_green']
    if '买' in n:
        return theme['accent_red']
    if low == 'watch':
        return theme['accent_cyan']
    if n.upper() == 'ALL':
        return theme['accent_yellow']
    return theme['accent_orange']


def build_membership_items(symbol, theme):
    """图表第三行：[(文本, 颜色, 粗细), ...]"""
    m = get_watchlist_membership(symbol)
    if m is None:
        return [("自选: 未同步(按M扫描)", theme['border'], 'normal')]
    items = []
    if m['groups']:
        items.append(("自选", theme['text_light'], 'normal'))
        for g in m['groups']:
            items.append((f"[{g}]", _group_color(g, theme), 'bold'))
    else:
        items.append(("自选: 未加入", theme['border'], 'normal'))
    if m['unsure']:
        tail = '/'.join(m['unsure'][:3]) + ('…' if len(m['unsure']) > 3 else '')
        items.append((f"(未全扫:{tail})", theme['border'], 'normal'))
    age = m.get('oldest_age_h')
    if age is not None and age > FT_MEMBER_STALE_HOURS:
        items.append((f"(最旧{age/24:.0f}天前,按M刷新)", theme['border'], 'normal'))
    return items