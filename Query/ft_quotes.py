#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ft_quotes.py —— Firstrade 本地数据读取层（Chart_input.py / Chart_input_single.py 共用）

数据来源（均由 Chrome 插件 + bridge_server.py 落盘）:
    Modules/firstrade_positions.json   持仓快照（覆盖式）
    Modules/firstrade_watchlist.json   自选股「变更%」快照（覆盖式，1800+ 只）

显示优先级（build_market_items）:
    1) 该 symbol 在持仓里  -> 显示 成本 / 日 / 总 / 仓位
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
    target = _norm_key(symbol)
    for k, v in data.items():
        if str(k).startswith('_') or not isinstance(v, dict):
            continue
        if _norm_key(k) == target:
            if FT_DEBUG:
                print(f"[FT] 命中持仓 {k}: {v}")
            return v
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
    day_val = _pick('day_change', 'changePercent')
    gl_val = _pick('gainloss', 'gainlossPercent')
    alloc_val = _pick('allocation', 'allocationPercent')

    items = []
    if cost_val:
        items.append((f"成本 {_fmt_money(cost_val)}", theme['accent_yellow'], 'bold'))
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