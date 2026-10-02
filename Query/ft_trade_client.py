#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ft_trade_client.py —— 从 Mac 的 Python 端驱动 Firstrade 网页「快速交易」

链路: 本脚本 → bridge_server.py /wl_trade → Chrome watchlist 页 wl_agent.js → ft_trade.js → 交易面板

用法:
  python ft_trade_client.py plan [--amount 1000] [--buy-groups 买,买买,买买买] [--sell-groups 卖卖卖]
  python ft_trade_client.py run  [同上] [--dry] [--keep-going] [--gap 4] [--scan] [--keep]
  python ft_trade_client.py buy  AAPL 2000 [--dry] [--keep]
  python ft_trade_client.py sell AAPL [股数|all] [--dry] [--keep]

安全：
  * 是否真正下单由浏览器 popup「下单模式」决定（预演 / 下单前确认 / 实盘），--dry 可强制预演
  * 每笔串行；任一笔失败/结果未知立即停止（--keep-going 可继续）
  * 同一 symbol 有交易在途时，bridge 会复用旧任务，不会重复下单
"""
import os
import re
import sys
import json
import time
import argparse
from urllib import request

BRIDGE_BASE = os.environ.get("FT_BRIDGE", "http://127.0.0.1:18888")
MODULES_DIR = os.path.join(os.path.expanduser("~"), "Coding", "Financial_System", "Modules")
POSITIONS_FILE = os.path.join(MODULES_DIR, "firstrade_positions.json")
MEMBERSHIP_FILE = os.path.join(MODULES_DIR, "firstrade_wl_membership.json")

BUY_GROUPS = ["买", "买买", "买买买"]
SELL_GROUPS = ["卖卖卖"]


def _key(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _post(path, payload, timeout):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(BRIDGE_BASE.rstrip("/") + path, data=data,
                          headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def load_positions():
    data = _load(POSITIONS_FILE)
    out = {}
    for k, v in data.items():
        if str(k).startswith("_") or not isinstance(v, dict):
            continue
        q = str(v.get("quantity", "")).replace(",", "").strip()
        try:
            if float(q) > 0:
                out[_key(k)] = q
        except ValueError:
            continue
    return out, data.get("_meta") or {}


def load_membership():
    data = _load(MEMBERSHIP_FILE)
    g = data.get("groups") if isinstance(data.get("groups"), dict) else {}
    return {n: list((r or {}).get("symbols") or []) for n, r in g.items() if isinstance(r, dict)}, g


def trade(symbol, side, amount=None, qty=None, remove=True, dry=False, wait=240):
    payload = {"symbol": symbol, "side": side, "remove": bool(remove), "dry": bool(dry), "wait": int(wait)}
    if side == "buy":
        payload["amount"] = float(amount)
    else:
        payload["qty"] = str(qty if qty not in (None, "") else "all")
    try:
        return _post("/wl_trade", payload, timeout=int(wait) + 30)
    except Exception as e:
        return {"ok": False, "message": f"连不上桥接服务 {BRIDGE_BASE}：{e}（先运行 bridge_server.py）"}


def scan_groups(wait=300):
    try:
        return _post("/wl_scan_groups", {"wait": wait}, timeout=wait + 20)
    except Exception as e:
        return {"ok": False, "message": str(e)}


def build_plan(amount, buy_groups, sell_groups):
    groups, raw = load_membership()
    pos, meta = load_positions()
    find = lambda name: next((g for g in groups if g.strip().upper() == name.strip().upper()), None)
    plan, skipped, seen = [], [], set()
    sell_keys = set()
    for gname in sell_groups:
        g = find(gname)
        if g:
            sell_keys |= {_key(s) for s in groups[g]}
    for gname in sell_groups:                         # 先卖（回笼资金），再买
        g = find(gname)
        if not g:
            continue
        for s in groups[g]:
            k = _key(s)
            if k in seen:
                continue
            seen.add(k)
            q = pos.get(k)
            if not q:
                skipped.append((s, g, "无持仓，无法卖出"))
                continue
            plan.append({"symbol": s, "side": "sell", "qty": q, "group": g})
    for gname in buy_groups:
        g = find(gname)
        if not g:
            continue
        for s in groups[g]:
            k = _key(s)
            if k in sell_keys:
                if k not in seen:
                    skipped.append((s, g, "同时在卖出分组，冲突跳过"))
                seen.add(k)
                continue
            if k in seen:
                continue
            seen.add(k)
            plan.append({"symbol": s, "side": "buy", "amount": amount, "group": g})
    incomplete = [find(g) for g in buy_groups + sell_groups if find(g) and not (raw.get(find(g)) or {}).get("complete")]
    return plan, skipped, incomplete, meta


def _print_plan(plan, skipped, incomplete, meta):
    print(f"持仓数据更新时间：{meta.get('updated_at_str', '?')}")
    if incomplete:
        print(f"⚠ 这些分组的归属数据不完整（建议先 --scan）：{', '.join(incomplete)}")
    for i, p in enumerate(plan, 1):
        what = f"买进 ${p['amount']:.0f}" if p["side"] == "buy" else f"卖出 {p['qty']} 股（全卖）"
        print(f"  {i:>3}. [{p['group']}] {p['symbol']:<8} {what}")
    for s, g, why in skipped:
        print(f"  跳过 [{g}] {s}: {why}")
    print(f"共 {len(plan)} 笔，跳过 {len(skipped)} 只")


def main():
    ap = argparse.ArgumentParser(description="Firstrade 快速交易客户端")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--amount", type=float, default=1000)
        p.add_argument("--buy-groups", default=",".join(BUY_GROUPS))
        p.add_argument("--sell-groups", default=",".join(SELL_GROUPS))
        if name == "run":
            p.add_argument("--dry", action="store_true")
            p.add_argument("--keep-going", action="store_true")
            p.add_argument("--keep", action="store_true", help="成交后不移出分组")
            p.add_argument("--gap", type=float, default=4)
            p.add_argument("--scan", action="store_true", help="先扫描全部分组归属")
            p.add_argument("--yes", action="store_true", help="跳过 YES 确认")
    b = sub.add_parser("buy"); b.add_argument("symbol"); b.add_argument("amount", type=float)
    s = sub.add_parser("sell"); s.add_argument("symbol"); s.add_argument("qty", nargs="?", default="all")
    for p in (b, s):
        p.add_argument("--dry", action="store_true")
        p.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    if a.cmd in ("buy", "sell"):
        r = trade(a.symbol.upper(), a.cmd, amount=getattr(a, "amount", None), qty=getattr(a, "qty", None),
                  remove=not a.keep, dry=a.dry)
        d = r.get("data") or {}
        print(("✅ " if r.get("ok") else "❌ ") + str(r.get("message")), d.get("orderNo") or "")
        sys.exit(0 if r.get("ok") else 1)

    split = lambda s: [x.strip() for x in re.split(r"[,，]", s) if x.strip()]
    if a.cmd == "run" and a.scan:
        print("正在扫描全部分组归属…")
        print(scan_groups().get("message"))
    plan, skipped, incomplete, meta = build_plan(a.amount, split(a.buy_groups), split(a.sell_groups))
    _print_plan(plan, skipped, incomplete, meta)
    if a.cmd == "plan" or not plan:
        return
    print("\n真正是否下单取决于浏览器 popup 的「下单模式」" + ("（本次 --dry 强制预演）" if a.dry else ""))
    if not a.yes and input("输入 YES 开始执行：").strip() != "YES":
        print("已取消")
        return
    ok_n = 0
    for i, p in enumerate(plan, 1):
        print(f"[{i}/{len(plan)}] {p['side']} {p['symbol']} …", flush=True)
        r = trade(p["symbol"], p["side"], amount=p.get("amount"), qty=p.get("qty"),
                  remove=not a.keep, dry=a.dry)
        d = r.get("data") or {}
        print(("   ✅ " if r.get("ok") else "   ❌ ") + str(r.get("message")) +
              (f"  订单号 {d.get('orderNo')}" if d.get("orderNo") else "") +
              (f"  已移出 {'/'.join(d.get('removed') or [])}" if d.get("removed") else ""))
        if r.get("ok"):
            ok_n += 1
        elif not a.keep_going:
            print("遇到失败/结果未知，已停止（--keep-going 可继续）")
            break
        time.sleep(a.gap)
    print(f"完成：成功 {ok_n} / {len(plan)}")


if __name__ == "__main__":
    main()