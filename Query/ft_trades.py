#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firstrade 买入/卖出痕迹读取与聚合（供 Chart_input.py / Chart_input_single.py 共用）

数据来源: ~/Coding/Financial_System/Modules/firstrade_orders.json

★ 同时兼容两种 schema：
  LEAN (v6+，默认，体积小 90%)
    { "symbol":"KRMN","side":"buy","date":"2026-09-10",
      "amount":1000,"price":34.79,"st":"F" }
      st: F=已成交 C=取消/拒绝 P=待成交 X=未知
  FULL (旧版，含 raw / datetime / status 等)

环境变量:
  FT_TRADE_DEBUG=1        打印调试信息
  FT_ORDER_INCLUDE_ALL=1  连"已取消/已拒绝"的订单也画出来（默认剔除）
  FT_ORDER_ONLY_FILLED=1  只画已成交(st=F)，挂单/未知一律不画
"""
import os
import re
import json
from datetime import datetime

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
ORDERS_FILE = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "firstrade_orders.json")

# 图上颜色/形状
BUY_COLOR = '#5E81AC'      # 蓝色 ▲ 买入
SELL_COLOR = '#D08770'     # 橙色 ▼ 卖出
BUY_MARKER = '^'
SELL_MARKER = 'v'

FT_TRADE_DEBUG = os.environ.get("FT_TRADE_DEBUG", "") == "1"
FT_ORDER_INCLUDE_ALL = os.environ.get("FT_ORDER_INCLUDE_ALL", "") == "1"
FT_ORDER_ONLY_FILLED = os.environ.get("FT_ORDER_ONLY_FILLED", "") == "1"

_FILL_RE = re.compile(r"已成交|已执行|成交|filled|executed|partial", re.I)
_CANCEL_RE = re.compile(r"取消|撤销|撤单|拒绝|失效|过期|无效|作废|cancel|reject|expire|void", re.I)
_PEND_RE = re.compile(r"待|挂单|未成交|排队|已提交|open|pending|queued|working|accept", re.I)

_ST_LABEL = {'F': '已成交', 'C': '已取消', 'P': '待成交', 'X': ''}

_CACHE = {"mtime": None, "map": None}


# ----------------------------------------------------------------------
def _norm_sym(s):
    return str(s).strip().upper().replace('.', '-')


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r'-?\d[\d,]*\.?\d*', str(v).replace(' ', ''))
    return float(m.group(0).replace(',', '')) if m else None


def _to_date(s):
    if not s:
        return None
    head = str(s).split(',')[0].strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%m/%d/%y"):
        try:
            return datetime.strptime(head, fmt).date()
        except ValueError:
            continue
    return None


def _status_code(o):
    """LEAN 用 st 字段；FULL 回落到文本正则"""
    st = o.get('st') or o.get('status_code')
    if isinstance(st, str) and st.strip():
        c = st.strip()[:1].upper()
        if c in ('F', 'C', 'P', 'X'):
            return c
    raw = o.get('raw') if isinstance(o.get('raw'), dict) else {}
    txt = "{} {} {}".format(o.get('status', ''), o.get('status_text', ''),
                            raw.get('statusCategory', ''))
    if _FILL_RE.search(txt):
        return 'F'
    if _CANCEL_RE.search(txt):
        return 'C'
    if _PEND_RE.search(txt):
        return 'P'
    return 'X'


def _is_effective(order):
    if FT_ORDER_INCLUDE_ALL:
        return True
    code = _status_code(order)
    if FT_ORDER_ONLY_FILLED:
        return code == 'F'
    return code != 'C'


def _load_orders_raw():
    if not os.path.exists(ORDERS_FILE):
        if FT_TRADE_DEBUG:
            print(f"[FT-TRADE] 订单文件不存在: {ORDERS_FILE}")
        return {}
    try:
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[FT-TRADE] 读取订单文件失败: {e}")
        return {}
    if not isinstance(data, dict):
        return {}
    orders = data.get('orders')
    if isinstance(orders, dict):
        return orders
    return {k: v for k, v in data.items()
            if isinstance(v, dict) and not str(k).startswith('_')}


# ----------------------------------------------------------------------
def load_trade_map(force=False):
    """返回 { 'AAPL': { date: {'buy': agg, 'sell': agg} } }
       agg = {'amount': float|None, 'quantity': float, 'count': int, 'items': [...]}"""
    try:
        mtime = os.path.getmtime(ORDERS_FILE) if os.path.exists(ORDERS_FILE) else 0
    except OSError:
        mtime = 0
    if (not force) and _CACHE["map"] is not None and _CACHE["mtime"] == mtime:
        return _CACHE["map"]

    out = {}
    skipped = 0
    for _key, o in _load_orders_raw().items():
        if not isinstance(o, dict):
            continue
        if not _is_effective(o):
            skipped += 1
            continue

        sym = _norm_sym(o.get('symbol', ''))
        d = _to_date(o.get('date') or o.get('datetime') or o.get('updated'))
        side = str(o.get('side', '')).strip().lower()
        if side not in ('buy', 'sell'):
            t = str(o.get('side_text') or o.get('transaction') or '')
            if re.search(r'买|buy|bought', t, re.I):
                side = 'buy'
            elif re.search(r'卖|sell|sold', t, re.I):
                side = 'sell'
            else:
                continue
        if not sym or d is None:
            continue

        amount = _to_float(o.get('amount'))
        qty = _to_float(o.get('quantity') if o.get('quantity') is not None else o.get('qty'))
        price = _to_float(o.get('price'))
        if amount is None and qty and price:
            amount = qty * price

        code = _status_code(o)
        node = out.setdefault(sym, {}).setdefault(d, {})
        agg = node.setdefault(side, {'amount': None, 'quantity': 0.0, 'count': 0, 'items': []})
        if amount is not None:
            agg['amount'] = (agg['amount'] or 0.0) + amount
        if qty:
            agg['quantity'] += qty
        agg['count'] += 1
        agg['items'].append({
            'time': str(o.get('datetime') or o.get('date') or ''),
            'quantity': qty,
            'amount': amount,
            'price': price,
            'status': str(o.get('status') or _ST_LABEL.get(code, '')),
            'price_type': str(o.get('price_type', '')),
            'source': str(o.get('amount_source', '')),
        })

    for sym in out:
        for d in out[sym]:
            for side in out[sym][d]:
                out[sym][d][side]['items'].sort(key=lambda x: x.get('time') or '')

    if FT_TRADE_DEBUG:
        print(f"[FT-TRADE] 载入 {sum(len(v) for v in out.values())} 个交易日，"
              f"覆盖 {len(out)} 只标的，剔除无效 {skipped} 笔")

    _CACHE["mtime"] = mtime
    _CACHE["map"] = out
    return out


def get_trades_for_symbol(symbol):
    """返回 { date: {'buy': agg, 'sell': agg} }；兼容 BRK.B / BRK-B"""
    if not symbol:
        return {}
    return load_trade_map().get(_norm_sym(symbol), {})


# ----------------------------------------------------------------------
def fmt_money(v):
    if v is None:
        return '--'
    a = abs(v)
    if a >= 1e6:
        return f"${v/1e6:.2f}M"
    if a >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.0f}"


def short_trade_label(side, agg, close_price=None):
    """一行短标签，给 hover 汇总用：'买入 $3.1K'"""
    amount = agg.get('amount')
    est = False
    if amount is None and agg.get('quantity') and close_price:
        amount = float(agg['quantity']) * float(close_price)
        est = True
    label = '买入' if side == 'buy' else '卖出'
    return f"{label} {fmt_money(amount)}{'(估)' if est else ''}"


def build_marker_text(side, d, agg, close_price=None):
    """浮框完整文案"""
    label = '买入' if side == 'buy' else '卖出'
    amount = agg.get('amount')
    est = False
    if amount is None and agg.get('quantity') and close_price:
        amount = float(agg['quantity']) * float(close_price)
        est = True

    day = d.isoformat() if hasattr(d, 'isoformat') else str(d)
    lines = [f"● {label}  {day}"]

    money = fmt_money(amount) + ('(按收盘价估算)' if est else '')
    qty = agg.get('quantity') or 0
    lines.append(f"{money}" + (f"  /  {qty:.0f}股" if qty else ""))

    cnt = agg.get('count', 1)
    if cnt > 1:
        lines.append(f"当日共 {cnt} 笔")
        for it in agg.get('items', [])[:5]:
            bits = []
            if it.get('quantity'):
                bits.append(f"{it['quantity']:.0f}股")
            if it.get('amount') is not None:
                bits.append(fmt_money(it['amount']))
            if it.get('price'):
                bits.append(f"@{it['price']:.2f}")
            if it.get('status'):
                bits.append(str(it['status']))
            if bits:
                lines.append("  · " + " ".join(bits))
    else:
        it = (agg.get('items') or [{}])[0]
        bits = []
        if it.get('price'):
            bits.append(f"@{it['price']:.2f}")
        if it.get('status'):
            bits.append(str(it['status']))
        if bits:
            lines.append("  · " + " ".join(bits))
    return "\n".join(lines)