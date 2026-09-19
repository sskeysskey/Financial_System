#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地极简 HTTP 桥接服务器 v8
    - 针对 Chrome 非激活页面提供主动 Tab 寻找、激活与置顶服务
    - 智能保障远程自动化链路不冻结
"""
import sys
import os
import re
import json
import time
import shutil
import tempfile
import threading
import subprocess
from collections import OrderedDict
from datetime import date, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 18888
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
STOCK_CHART_PY = os.path.join(BASE_CODING_DIR, "Financial_System", "Query", "Stock_Chart.py")
MODULES_DIR = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules")
POSITIONS_JSON_PATH = os.path.join(MODULES_DIR, "firstrade_positions.json")
ORDERS_JSON_PATH = os.path.join(MODULES_DIR, "firstrade_orders.json")
WATCHLIST_JSON_PATH = os.path.join(MODULES_DIR, "firstrade_watchlist.json")
SECTORS_ALL_PATH = os.path.join(MODULES_DIR, "Sectors_All.json")

EARNINGS_RELEASE_PATH = os.path.join(BASE_CODING_DIR, "News", "Earnings_Release_new.txt")

ENABLE_SECTORS_SOURCE = False
DEFAULT_WL_SOURCE = "earnings"

SECTOR_GROUPS_FOR_WATCHLIST = [
    "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
    "Industrials", "Real_Estate", "Technology", "Utilities",
]

WATCHLIST_URL = "https://invest.firstrade.com/app/watchlist"
WATCHLIST_URL_MATCH = "invest.firstrade.com/app/watchlist"
WATCHLIST_GROUPS = ["ALL", "买", "买买", "买买买", "卖卖卖", "Short", "Watch"]

TASK_TTL = 600
TASK_LEASE = 90
AGENT_ALIVE_SEC = 8

_TASKS = OrderedDict()
_TASK_LOCK = threading.Lock()
_TASK_SEQ = [0]
_LAST_AGENT_POLL = [0.0]

ORDER_LEAN_FIELDS = ("symbol", "side", "date", "quantity", "amount", "price", "st")
ORDER_EXTRA_FIELDS = ("order_id", "side_text", "datetime", "status", "price_type",
                      "duration", "instruction", "amount_source", "quantity_text", "raw")
ORDER_VERBOSE_DEFAULT = os.environ.get("FT_ORDER_VERBOSE", "") == "1"

# ---------- 持仓 LEAN schema ----------
POSITION_LEAN_FIELDS = ("symbol", "quantity", "cost", "avg_cost", "market_value",
                        "last_price", "day_change", "day_change_amount",
                        "gainloss", "gainloss_amount", "allocation")
POSITION_JUNK_KEYS = ("raw", "dayTrend", "trend", "chart", "sparkline",
                      "updated_at", "row_id", "actions", "menu")
POSITION_MAX_VALUE_LEN = 40
POSITION_VERBOSE_DEFAULT = os.environ.get("FT_POSITION_VERBOSE", "") == "1"

_ST_FILL = re.compile(r"已成交|已执行|成交|filled|executed|partial", re.I)
_ST_CANCEL = re.compile(r"取消|撤销|撤单|拒绝|失效|过期|无效|作废|cancel|reject|expire|void", re.I)
_ST_PEND = re.compile(r"待|挂单|未成交|排队|已提交|open|pending|queued|working|accept", re.I)

PYTHON_EXEC = os.environ.get("FT_PYTHON") or sys.executable

_FILE_LOCK = threading.Lock()
_ORDER_LOCK = threading.Lock()
_WL_LOCK = threading.Lock()


def _log(msg):
    print(f"[ChartBridge] {msg}", flush=True)


def _atomic_write(path, obj, backup=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if backup and os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except Exception as e:
            _log(f"备份失败(忽略): {e}")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        _log(f"读取 {os.path.basename(path)} 失败: {e}")
        return {}


def _file_size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def _gc_tasks_locked():
    now = time.time()
    for tid in list(_TASKS.keys()):
        t = _TASKS[tid]
        if t["status"] == "taken" and (now - t["taken_at"]) > TASK_LEASE:
            t["status"] = "pending"
            _log(f"[任务] {tid} 租约超时，重新排队")
        if (now - t["created_at"]) > TASK_TTL:
            _TASKS.pop(tid, None)


def _task_public(t):
    return {k: v for k, v in t.items() if k != "event"}


def new_task(action, symbol, group, extra=None):
    with _TASK_LOCK:
        _TASK_SEQ[0] += 1
        tid = "t%d_%d" % (int(time.time() * 1000), _TASK_SEQ[0])
        t = {
            "id": tid, "action": action, "symbol": symbol, "group": group,
            "status": "pending", "created_at": time.time(), "taken_at": 0.0,
            "result": None, "event": threading.Event(),
        }
        if extra:
            t.update(extra)
        _TASKS[tid] = t
        _gc_tasks_locked()
    return t


def take_tasks(limit=3):
    out = []
    with _TASK_LOCK:
        _gc_tasks_locked()
        for t in _TASKS.values():
            if t["status"] != "pending":
                continue
            t["status"] = "taken"
            t["taken_at"] = time.time()
            out.append({"id": t["id"], "action": t["action"],
                        "symbol": t["symbol"], "group": t["group"],
                        "restore": bool(t.get("restore", True))})
            if len(out) >= max(1, limit):
                break
    return out


def finish_task(tid, ok, message, data=None):
    with _TASK_LOCK:
        t = _TASKS.get(str(tid))
        if not t:
            return False
        t["status"] = "done" if ok else "error"
        t["result"] = {"ok": bool(ok), "message": message or "",
                       "data": data or {}, "finished_at": time.time()}
        t["event"].set()
    return True


def pending_count():
    with _TASK_LOCK:
        return sum(1 for t in _TASKS.values() if t["status"] in ("pending", "taken"))


# ★ 增强版 AppleScript：寻找现有 watchlist Tab 并直接切为 active Tab！
_ENSURE_TAB_APPLESCRIPT = '''
on run argv
	set targetURL to item 1 of argv
	set matchStr to "%s"
	tell application "Google Chrome"
		if it is not running then return "not_running"
		repeat with w in windows
			set tabIndex to 1
			repeat with t in tabs of w
				if (URL of t) contains matchStr then
					set active tab index of w to tabIndex
					set index of w to 1
					return "activated_existing"
				end if
				set tabIndex to tabIndex + 1
			end repeat
		end repeat
		-- 如果没找到已有 watchlist tab，检查是否有其他 Firstrade tab
		repeat with w in windows
			set tabIndex to 1
			repeat with t in tabs of w
				if (URL of t) contains "invest.firstrade.com" then
					set URL of t to targetURL
					set active tab index of w to tabIndex
					set index of w to 1
					return "navigated_existing"
				end if
				set tabIndex to tabIndex + 1
			end repeat
		end repeat
		if (count of windows) is 0 then
			make new window
			set URL of active tab of window 1 to targetURL
		else
			tell window 1 to make new tab with properties {URL:targetURL}
		end if
		return "opened_new"
	end tell
end run
''' % WATCHLIST_URL_MATCH

_SCRIPT_PATH = [None]


def _ensure_script_file():
    if _SCRIPT_PATH[0] and os.path.exists(_SCRIPT_PATH[0]):
        return _SCRIPT_PATH[0]
    p = os.path.join(tempfile.gettempdir(), "ft_ensure_watchlist_tab_v8.applescript")
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(_ENSURE_TAB_APPLESCRIPT)
        _SCRIPT_PATH[0] = p
        return p
    except Exception as e:
        _log(f"写入 AppleScript 失败: {e}")
        return None


def ensure_watchlist_tab():
    """在 macOS 下智能唤醒并激活 Watchlist Tab，解除浏览器节流"""
    if sys.platform != "darwin":
        return "unsupported_os"
    sp = _ensure_script_file()
    if not sp:
        return "script_error"
    try:
        p = subprocess.run(["osascript", sp, WATCHLIST_URL],
                           capture_output=True, text=True, timeout=20)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if out == "not_running":
            subprocess.Popen(["open", "-a", "Google Chrome", WATCHLIST_URL])
            return "launched_chrome"
        return out or ("error: " + err if err else "unknown")
    except Exception as e:
        return "error: %s" % e


def load_sector_symbols():
    data = _load_json(SECTORS_ALL_PATH)
    out, seen, per_group = [], set(), {}
    for g in SECTOR_GROUPS_FOR_WATCHLIST:
        arr = data.get(g)
        if not isinstance(arr, list):
            per_group[g] = 0
            continue
        cnt = 0
        for raw in arr:
            sym = str(raw).strip().upper()
            if not sym:
                continue
            key = sym.replace(".", "").replace("-", "")
            if key in seen:
                continue
            seen.add(key)
            out.append(sym)
            cnt += 1
        per_group[g] = cnt
    return out, per_group


_DATE_IN_LINE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_SYM_CLEAN = re.compile(r"[^A-Z0-9.\-]")


def parse_earnings_release(path=None):
    path = path or EARNINGS_RELEASE_PATH
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = _DATE_IN_LINE.search(line)
                if not m:
                    continue
                try:
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    continue
                parts = [p.strip() for p in line.split(":")]
                sym = _SYM_CLEAN.sub("", parts[0].upper())
                session = parts[1].upper() if len(parts) >= 2 else ""
                if not sym:
                    continue
                arr = out.setdefault(d, [])
                if not any(item[0] == sym for item in arr):
                    arr.append((sym, session))
    except Exception as e:
        _log(f"解析 {os.path.basename(path)} 失败: {e}")
    return out


def _target_dates(today, back=1, ahead=0):
    dates = {today}
    for i in range(1, max(0, ahead) + 1):
        dates.add(today + timedelta(days=i))
    got, cur, guard = 0, today, 0
    while got < max(0, back) and guard < 30:
        cur = cur - timedelta(days=1)
        guard += 1
        dates.add(cur)
        if cur.weekday() < 5:
            got += 1
    return dates


def load_earnings_symbols(back=1, ahead=0, fallback=True):
    by_date = parse_earnings_release()
    today = date.today()
    targets = _target_dates(today, back, ahead)
    picked = {d: by_date[d] for d in sorted(targets) if d in by_date}
    used_fallback = False

    if not picked and fallback and by_date:
        past = sorted([d for d in by_date if d <= today], reverse=True)[:max(1, back + 1)]
        picked = {d: by_date[d] for d in sorted(past)}
        used_fallback = True

    symbols, seen = [], set()
    day_map = {}

    for d in sorted(picked.keys()):
        day_syms = []
        for sym, session in picked[d]:
            if d < today:
                if session != "AMC":
                    continue
            elif d == today:
                if session != "BMO":
                    continue
            k = sym.replace(".", "").replace("-", "")
            if k not in seen:
                seen.add(k)
                symbols.append(sym)
            day_syms.append(sym)
        if day_syms:
            day_map[d.isoformat()] = day_syms

    span = f"{min(day_map)}~{max(day_map)}" if day_map else today.isoformat()
    frm = f"财报日历 {span}" + ("（回退到最近财报日）" if used_fallback else "")
    return {
        "status": "ok", "source": "earnings_release",
        "file": EARNINGS_RELEASE_PATH,
        "file_exists": os.path.exists(EARNINGS_RELEASE_PATH),
        "from": frm, "today": today.isoformat(), "back": back, "ahead": ahead,
        "fallback": used_fallback, "dates": day_map,
        "count": len(symbols), "symbols": symbols,
    }


def build_wl_source(src, back=1, ahead=0):
    s = (src or DEFAULT_WL_SOURCE).strip().lower()
    if s in ("earnings", "earnings_release", "er", "release"):
        return load_earnings_symbols(back=back, ahead=ahead)
    if s in ("sectors", "sectors_all", "sector"):
        if not ENABLE_SECTORS_SOURCE:
            return {"status": "disabled", "source": "sectors_all", "symbols": [], "count": 0,
                    "message": "Sectors_All 数据源已停用"}
        symbols, per_group = load_sector_symbols()
        return {"status": "ok", "source": "sectors_all", "file": SECTORS_ALL_PATH,
                "from": "Sectors_All.json", "groups": per_group,
                "count": len(symbols), "symbols": symbols}
    return {"status": "error", "message": f"未知数据源: {src}", "symbols": [], "count": 0}


def _slim_position(sym, rec, verbose=False):
    """持仓记录瘦身：白名单字段 + 去 raw / dayTrend / 逐条 updated_at"""
    out = {"symbol": sym}
    for k in POSITION_LEAN_FIELDS:
        if k == "symbol":
            continue
        v = rec.get(k)
        if v in (None, "", "--", {}, []):
            continue
        if isinstance(v, str):
            v = v.strip()
            if not v or v == "--" or len(v) > POSITION_MAX_VALUE_LEN:
                continue
        out[k] = v
    # 老格式兼容：顶层缺字段时，从残留的 raw 里补一次（补完照样不落 raw）
    raw = rec.get("raw")
    if isinstance(raw, dict):
        alias = {"quantity": "quantity", "totalCost": "cost", "averageCost": "avg_cost",
                 "marketValue": "market_value", "price": "last_price",
                 "changePercent": "day_change", "change": "day_change_amount",
                 "gainlossPercent": "gainloss", "gainloss": "gainloss_amount",
                 "allocationPercent": "allocation"}
        for rk, ak in alias.items():
            if ak in out:
                continue
            v = raw.get(rk)
            if isinstance(v, (int, float)):
                out[ak] = v
            elif isinstance(v, str):
                v = v.strip()
                if v and v != "--" and len(v) <= POSITION_MAX_VALUE_LEN:
                    out[ak] = v
        if verbose:
            clean = {k: v for k, v in raw.items()
                     if k not in POSITION_JUNK_KEYS
                     and isinstance(v, (str, int, float))
                     and len(str(v)) <= POSITION_MAX_VALUE_LEN}
            if clean:
                out["raw"] = clean
    return out


def _write_positions(data, verbose, mode):
    data["_meta"] = {
        "updated_at": time.time(),
        "updated_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len([k for k in data.keys() if not str(k).startswith("_")]),
        "mode": mode,
        "schema": "full_v1" if verbose else "lean_v1",
    }
    # ★ backup=True → 每次写入前把上一期存成 firstrade_positions.json.bak
    _atomic_write(POSITIONS_JSON_PATH, data, backup=True)
    return data["_meta"]["count"]


def save_positions(incoming, overwrite=False, verbose=None):
    if not isinstance(incoming, dict):
        return 0, 0
    if not incoming and not overwrite:
        return 0, 0
    verbose = POSITION_VERBOSE_DEFAULT if verbose is None else bool(verbose)
    with _FILE_LOCK:
        data = {} if overwrite else _load_json(POSITIONS_JSON_PATH)

        # 合并模式下，顺手把历史胖记录洗一遍
        if data:
            for k in list(data.keys()):
                if str(k).startswith("_"):
                    continue
                if isinstance(data[k], dict):
                    data[k] = _slim_position(str(k).strip().upper(), data[k], verbose)
                else:
                    data.pop(k, None)

        old_total = len([k for k in data.keys() if not str(k).startswith("_")])
        n = 0
        for key, val in incoming.items():
            if not isinstance(val, dict):
                continue
            sym = str(key).strip().upper()
            if not sym:
                continue
            slim = _slim_position(sym, val, verbose)
            if len(slim) <= 1:          # 只有 symbol，没有任何有效字段
                continue
            if not overwrite and isinstance(data.get(sym), dict):
                merged = dict(data[sym])
                merged.update(slim)
                slim = merged
            data[sym] = slim
            n += 1

        if overwrite and old_total >= 10 and n < old_total * 0.4:
            _log(f"⚠ 覆盖写入的持仓数({n}) 远少于原有({old_total})，"
                 f"旧数据已备份到 {os.path.basename(POSITIONS_JSON_PATH)}.bak")

        total = _write_positions(data, verbose, "overwrite" if overwrite else "merge")
    return n, total


def compact_positions(verbose=False):
    """一次性给历史胖 firstrade_positions.json 瘦身（写入前自动 .bak）"""
    with _FILE_LOCK:
        before = _file_size(POSITIONS_JSON_PATH)
        data = _load_json(POSITIONS_JSON_PATH)
        if not data:
            return {"status": "skip", "reason": "empty",
                    "before": before, "after": before, "count": 0}
        out, shrunk = {}, 0
        for k, v in data.items():
            if str(k).startswith("_") or not isinstance(v, dict):
                continue
            sym = str(k).strip().upper()
            s = _slim_position(sym, v, verbose)
            if len(s) < len(v):
                shrunk += 1
            out[sym] = s
        cnt = _write_positions(out, verbose, "compact")
        after = _file_size(POSITIONS_JSON_PATH)
    return {"status": "ok", "count": cnt, "shrunk": shrunk,
            "before": before, "after": after,
            "saved_pct": round((1 - (after / before)) * 100, 1) if before else 0.0,
            "schema": "full_v1" if verbose else "lean_v1"}


def _status_code(rec):
    st = rec.get("st") or rec.get("status_code")
    if isinstance(st, str) and st.strip():
        c = st.strip()[:1].upper()
        if c in ("F", "C", "P", "X"):
            return c
    txt = "{} {} {}".format(rec.get("status", ""), rec.get("status_text", ""),
                            (rec.get("raw") or {}).get("statusCategory", "")
                            if isinstance(rec.get("raw"), dict) else "")
    if _ST_FILL.search(txt):
        return "F"
    if _ST_CANCEL.search(txt):
        return "C"
    if _ST_PEND.search(txt):
        return "P"
    return "X"


def _slim_order(rec, verbose=False):
    out = {}
    for k in ORDER_LEAN_FIELDS:
        if k == "st":
            out["st"] = _status_code(rec)
            continue
        v = rec.get(k)
        if k == "quantity" and v in (None, ""):
            v = rec.get("qty")
        if v in (None, "", {}, []):
            continue
        out[k] = v
    if verbose:
        for k in ORDER_EXTRA_FIELDS:
            v = rec.get(k)
            if v in (None, "", {}, []):
                continue
            out[k] = v
    return out


def _extract_orders(data):
    orders = data.get("orders")
    if isinstance(orders, dict):
        return dict(orders)
    return {k: v for k, v in data.items()
            if isinstance(v, dict) and not str(k).startswith("_")}


def _maybe_backup_fat(shrunk):
    if shrunk <= 0:
        return
    fat = ORDERS_JSON_PATH + ".fat.bak"
    if os.path.exists(fat) or not os.path.exists(ORDERS_JSON_PATH):
        return
    try:
        shutil.copy2(ORDERS_JSON_PATH, fat)
        _log(f"已将瘦身前的完整订单备份到 {fat}")
    except Exception as e:
        _log(f"备份完整订单失败: {e}")


def _write_orders(orders, verbose, shrunk):
    _maybe_backup_fat(shrunk)
    out = {
        "_meta": {
            "updated_at": time.time(),
            "updated_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(orders), "mode": "append",
            "schema": "full_v1" if verbose else "lean_v1",
        },
        "orders": orders,
    }
    _atomic_write(ORDERS_JSON_PATH, out, backup=True)


def save_orders(incoming, verbose=None):
    if not isinstance(incoming, dict) or not incoming:
        return 0, 0, 0, 0
    verbose = ORDER_VERBOSE_DEFAULT if verbose is None else bool(verbose)
    with _ORDER_LOCK:
        data = _load_json(ORDERS_JSON_PATH)
        orders = _extract_orders(data)
        old_total = len(orders)
        added = updated = 0
        for key, val in incoming.items():
            if not isinstance(val, dict):
                continue
            k = str(key).strip()
            sym = str(val.get("symbol", "")).strip().upper()
            side = str(val.get("side", "")).strip().lower()
            d = str(val.get("date", "")).strip()
            if not k or not sym or side not in ("buy", "sell") or not d:
                continue
            rec = dict(val)
            rec["symbol"] = sym
            rec["side"] = side
            old = orders.get(k)
            if old:
                merged = dict(old)
                for kk, vv in rec.items():
                    if vv not in (None, "", {}, []):
                        merged[kk] = vv
                orders[k] = merged
                updated += 1
            else:
                orders[k] = rec
                added += 1
        slim, shrunk = {}, 0
        for k, v in orders.items():
            if not isinstance(v, dict):
                continue
            s = _slim_order(v, verbose)
            if len(s) < len(v):
                shrunk += 1
            slim[k] = s
        total = len(slim)
        if total < old_total:
            _log(f"⚠ 拒绝写入：合并后条数 {total} < 原有 {old_total}")
            return 0, 0, old_total, 0
        _write_orders(slim, verbose, shrunk)
    return added, updated, total, shrunk


def compact_orders(verbose=False):
    with _ORDER_LOCK:
        before = _file_size(ORDERS_JSON_PATH)
        data = _load_json(ORDERS_JSON_PATH)
        orders = _extract_orders(data)
        if not orders:
            return {"status": "skip", "reason": "empty", "before": before,
                    "after": before, "count": 0}
        slim, shrunk = {}, 0
        for k, v in orders.items():
            if not isinstance(v, dict):
                continue
            s = _slim_order(v, verbose)
            if len(s) < len(v):
                shrunk += 1
            slim[k] = s
        _write_orders(slim, verbose, shrunk)
        after = _file_size(ORDERS_JSON_PATH)
    return {
        "status": "ok", "count": len(slim), "shrunk": shrunk,
        "before": before, "after": after,
        "saved_pct": round((1 - (after / before)) * 100, 1) if before else 0.0,
        "schema": "full_v1" if verbose else "lean_v1",
    }


def save_watchlist(incoming, overwrite=True):
    if not isinstance(incoming, dict) or not incoming:
        return 0, 0, "empty"
    with _WL_LOCK:
        data = _load_json(WATCHLIST_JSON_PATH)
        quotes = data.get("quotes")
        if not isinstance(quotes, dict):
            quotes = {k: v for k, v in data.items()
                      if isinstance(v, dict) and not str(k).startswith("_")}
        old_total = len(quotes)
        mode = "overwrite" if overwrite else "merge"
        if overwrite and old_total >= 200 and len(incoming) < old_total * 0.5:
            mode = "merge_guard"
            overwrite = False
        base = {} if overwrite else dict(quotes)
        now = time.time()
        n = 0
        for key, val in incoming.items():
            if not isinstance(val, dict):
                continue
            sym = str(key).strip().upper()
            if not sym:
                continue
            rec = dict(val)
            rec["symbol"] = sym
            if overwrite:
                rec.pop("updated_at", None)
            else:
                rec["updated_at"] = rec.get("updated_at") or now
            base[sym] = rec
            n += 1
        out = {
            "_meta": {"updated_at": now,
                      "updated_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "count": len(base), "mode": mode},
            "quotes": base,
        }
        _atomic_write(WATCHLIST_JSON_PATH, out)
    return n, len(base), mode


def launch_chart(symbol):
    try:
        try:
            import pyperclip
            pyperclip.copy(symbol)
        except Exception:
            pass
        subprocess.Popen([PYTHON_EXEC, STOCK_CHART_PY, symbol], start_new_session=True)
        return True, None
    except Exception as e:
        return False, str(e)


def _qint(qs, key, default):
    try:
        return int(qs.get(key, [default])[0])
    except Exception:
        return default


class StockRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _reply(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/sync_positions":
            try:
                body = self._read_json_body()
                incoming = body.get("positions", body) if isinstance(body.get("positions"), dict) else body
                overwrite = bool(body.get("overwrite", False))
                n, total = save_positions(incoming, overwrite=overwrite)
                self._reply(200, {"status": "ok", "saved": n, "total": total, "overwrite": overwrite})
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/sync_orders":
            try:
                body = self._read_json_body()
                incoming = body.get("orders") if isinstance(body.get("orders"), dict) else body
                verbose = body.get("verbose", None)
                added, updated, total, shrunk = save_orders(incoming, verbose=verbose)
                self._reply(200, {"status": "ok", "added": added, "updated": updated,
                                  "total": total, "shrunk": shrunk,
                                  "bytes": _file_size(ORDERS_JSON_PATH)})
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/compact_orders":
            try:
                body = self._read_json_body()
                r = compact_orders(bool(body.get("verbose", False)))
                self._reply(200, r)
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/compact_positions":
            try:
                body = self._read_json_body()
                self._reply(200, compact_positions(bool(body.get("verbose", False))))
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/sync_watchlist":
            try:
                body = self._read_json_body()
                incoming = body.get("quotes") if isinstance(body.get("quotes"), dict) else body
                overwrite = bool(body.get("overwrite", True))
                n, total, mode = save_watchlist(incoming, overwrite=overwrite)
                self._reply(200, {"status": "ok", "saved": n, "total": total, "mode": mode})
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        # ★ Python 下单任务入口：无论何时进来，主动寻找并激活 Tab
        if path == "/wl_add":
            try:
                body = self._read_json_body()
                symbol = str(body.get("symbol", "")).strip().upper()
                group = str(body.get("group", "")).strip()
                wait = float(body.get("wait", 0) or 0)
                restore = bool(body.get("restore", True))
                if not symbol:
                    self._reply(400, {"status": "error", "ok": False, "message": "no symbol"})
                    return

                # ★ 关键改进：不管有没有心跳，都直接通过 AppleScript 激活 Watchlist Tab，唤醒事件循环
                tab = ensure_watchlist_tab()
                _log(f"[任务] 激活并确保 Watchlist 页面状态 -> {tab}")

                t = new_task("add", symbol, group, {"restore": restore})
                _log(f"[任务] 排队 add {symbol} → 「{group or '当前分组'}」 id={t['id']}")

                if wait > 0:
                    t["event"].wait(min(wait, 180))
                res = t.get("result")
                if res:
                    out = {"status": "ok", "id": t["id"], "tab": tab}
                    out.update(res)
                    self._reply(200, out)
                else:
                    self._reply(200, {
                        "status": "pending", "id": t["id"], "tab": tab, "ok": False,
                        "message": "任务已排队，页面已激活。如果在几秒内仍未执行，请检查该页面的网络是否通畅。"})
            except Exception as e:
                _log(f"/wl_add 失败: {e}")
                self._reply(500, {"status": "error", "ok": False, "message": str(e)})
            return

        if path == "/wl_task_result":
            try:
                body = self._read_json_body()
                ok = finish_task(body.get("id"), bool(body.get("ok")),
                                 str(body.get("message", "")), body.get("data"))
                _log(f"[任务] 回报 id={body.get('id')} ok={body.get('ok')} "
                     f"msg={str(body.get('message',''))[:90]}")
                self._reply(200, {"status": "ok" if ok else "unknown_task"})
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/plot":
            try:
                payload = self._read_json_body()
                symbol = str(payload.get("symbol", "")).strip().upper()
                positions = payload.get("positions") or {}
                saved, total = (0, 0)
                if positions:
                    saved, total = save_positions(positions)
                if not symbol:
                    self._reply(400, {"status": "error", "message": "no symbol"})
                    return
                ok, err = launch_chart(symbol)
                if ok:
                    self._reply(200, {"status": "ok", "symbol": symbol, "saved": saved, "total": total})
                else:
                    self._reply(500, {"status": "error", "message": err})
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        self._reply(404, {"status": "error", "message": "not found"})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/ping":
            self._reply(200, {
                "status": "ok", "port": PORT, "python": PYTHON_EXEC,
                "chart_script_exists": os.path.exists(STOCK_CHART_PY),
                "wl_groups": WATCHLIST_GROUPS,
                "wl_tasks_pending": pending_count(),
                "positions_bytes": _file_size(POSITIONS_JSON_PATH),
                "positions_bak_exists": os.path.exists(POSITIONS_JSON_PATH + ".bak"),
                "agent_last_poll_ago": (round(time.time() - _LAST_AGENT_POLL[0], 1)
                                        if _LAST_AGENT_POLL[0] else None),
            })
            return

        if path == "/wl_groups":
            self._reply(200, {"status": "ok", "groups": WATCHLIST_GROUPS, "url": WATCHLIST_URL})
            return

        if path == "/wl_tasks":
            _LAST_AGENT_POLL[0] = time.time()
            tasks = take_tasks(_qint(qs, "max", 3))
            self._reply(200, {"status": "ok", "tasks": tasks, "server_time": time.time()})
            return

        if path == "/wl_task":
            tid = qs.get("id", [""])[0]
            with _TASK_LOCK:
                t = _TASKS.get(tid)
                self._reply(200, _task_public(t) if t else {"status": "error", "message": "unknown task"})
            return

        if path == "/wl_source":
            try:
                src = (qs.get("src", [DEFAULT_WL_SOURCE])[0] or DEFAULT_WL_SOURCE)
                self._reply(200, build_wl_source(src, back=_qint(qs, "back", 1), ahead=_qint(qs, "ahead", 0)))
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/positions":
            self._reply(200, _load_json(POSITIONS_JSON_PATH))
            return

        if path == "/orders":
            self._reply(200, _load_json(ORDERS_JSON_PATH))
            return

        if path == "/watchlist":
            self._reply(200, _load_json(WATCHLIST_JSON_PATH))
            return

        self._reply(404, {"status": "error", "message": "not found"})

    def log_message(self, fmt, *args):
        try:
            line = fmt % args
        except Exception:
            line = str(fmt)
        if "/wl_tasks" in line:
            return
        sys.stderr.write(f"[BridgeServer] {line}\n")


if __name__ == "__main__":
    _er = load_earnings_symbols()
    print("=" * 72)
    print(f"  Firstrade 本地桥接服务已启动: http://127.0.0.1:{PORT}")
    print(f"  远程添加支持全自动寻找与切换标签页")
    print("=" * 72, flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), StockRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
        server.server_close()