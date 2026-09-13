#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地极简 HTTP 桥接服务器 v7
    GET  /ping                        健康检查
    GET  /wl_source?src=earnings|sectors&back=1&ahead=0
    GET  /earnings_release?back=1
    GET  /sectors_all
    GET  /positions                   持仓 JSON（覆盖式快照）
    GET  /orders                      订单 JSON（追加式流水，LEAN schema）
    GET  /watchlist                   自选股行情 JSON（覆盖式快照）
    GET  /plot?symbol=AAPL            拉起 Stock_Chart.py
    POST /sync_positions / /sync_orders / /sync_watchlist / /compact_orders
    POST /plot  {symbol, positions}

    ★ v7 新增「Python → 浏览器」任务队列（一键把 symbol 加入指定自选股分组）
    POST /wl_add        {symbol, group, wait, restore}  Python 下单（wait>0 时阻塞等结果）
    GET  /wl_tasks?max=3                                Chrome 扩展领任务（带租约）
    POST /wl_task_result{id, ok, message, data}         Chrome 扩展回报结果
    GET  /wl_task?id=xxx                                查询单个任务
    GET  /wl_groups                                     可用分组白名单
监听端口: 18888
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

# ======================================================================
# ★ v7：自选股「远程添加」任务队列
# ======================================================================
WATCHLIST_URL = "https://invest.firstrade.com/app/watchlist"
WATCHLIST_URL_MATCH = "invest.firstrade.com/app/watchlist"
# 允许 Python 端投递的分组白名单（不在名单内只告警，不拦截）
WATCHLIST_GROUPS = ["买", "买买", "买买买", "卖卖卖"]

TASK_TTL = 600          # 任务保留时间（秒）
TASK_LEASE = 90         # 被领取但未回报的租约时间，超时重新排队
AGENT_ALIVE_SEC = 8     # 多久没心跳就认为「没有活着的 watchlist 标签页」

_TASKS = OrderedDict()
_TASK_LOCK = threading.Lock()
_TASK_SEQ = [0]
_LAST_AGENT_POLL = [0.0]

# ---------------------------------------------------------------------------
# 订单字段白名单（瘦身核心）
# ---------------------------------------------------------------------------
ORDER_LEAN_FIELDS = ("symbol", "side", "date", "quantity", "amount", "price", "st")
ORDER_EXTRA_FIELDS = ("order_id", "side_text", "datetime", "status", "price_type",
                      "duration", "instruction", "amount_source", "quantity_text", "raw")
ORDER_VERBOSE_DEFAULT = os.environ.get("FT_ORDER_VERBOSE", "") == "1"

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
        _log(f"读取 {os.path.basename(path)} 失败（将重建）: {e}")
        return {}


def _file_size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


# ======================================================================
# ★ 任务队列实现
# ======================================================================
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


# ---------------- 后台确保存在 watchlist 标签页（macOS / Chrome） ----------------
_ENSURE_TAB_APPLESCRIPT = '''
on run argv
	set targetURL to item 1 of argv
	set matchStr to "%s"
	tell application "Google Chrome"
		if it is not running then return "not_running"
		set wasFound to false
		repeat with w in windows
			repeat with t in tabs of w
				if (URL of t) contains matchStr then
					set wasFound to true
					exit repeat
				end if
			end repeat
			if wasFound then exit repeat
		end repeat
		if wasFound then return "exists"
		if (count of windows) is 0 then
			make new window
			set URL of active tab of window 1 to targetURL
		else
			tell window 1 to make new tab with properties {URL:targetURL}
		end if
		return "opened"
	end tell
end run
''' % WATCHLIST_URL_MATCH

_SCRIPT_PATH = [None]


def _ensure_script_file():
    if _SCRIPT_PATH[0] and os.path.exists(_SCRIPT_PATH[0]):
        return _SCRIPT_PATH[0]
    p = os.path.join(tempfile.gettempdir(), "ft_ensure_watchlist_tab.applescript")
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(_ENSURE_TAB_APPLESCRIPT)
        _SCRIPT_PATH[0] = p
        return p
    except Exception as e:
        _log(f"写入 AppleScript 失败: {e}")
        return None


def ensure_watchlist_tab():
    """尽量在后台（不抢焦点）保证有一个 watchlist 标签页"""
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
            # Chrome 没开：后台启动（-g 不抢焦点）
            subprocess.Popen(["open", "-g", "-a", "Google Chrome", WATCHLIST_URL])
            return "launched_chrome"
        return out or ("error: " + err if err else "unknown")
    except Exception as e:
        return "error: %s" % e


# ======================================================================
# 数据源 A: Sectors_All.json（默认屏蔽）
# ======================================================================
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


# ======================================================================
# 数据源 B: Earnings_Release_new.txt
# ======================================================================
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
                    "message": "Sectors_All 数据源已在 bridge_server.py 停用；"
                               "把 ENABLE_SECTORS_SOURCE 改成 True 并重启即可启用。"}
        symbols, per_group = load_sector_symbols()
        return {"status": "ok", "source": "sectors_all", "file": SECTORS_ALL_PATH,
                "from": "Sectors_All.json", "groups": per_group,
                "count": len(symbols), "symbols": symbols}
    return {"status": "error", "message": f"未知数据源: {src}", "symbols": [], "count": 0}


# ======================================================================
# 持仓
# ======================================================================
def save_positions(incoming, overwrite=False):
    if not isinstance(incoming, dict):
        return 0, 0
    if not incoming and not overwrite:
        return 0, 0
    with _FILE_LOCK:
        data = {} if overwrite else _load_json(POSITIONS_JSON_PATH)
        n = 0
        for key, val in incoming.items():
            if not isinstance(val, dict):
                continue
            sym = str(key).strip().upper()
            if not sym:
                continue
            val = dict(val)
            val.setdefault("symbol", sym)
            data[sym] = val
            n += 1
        data["_meta"] = {
            "updated_at": time.time(),
            "updated_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len([k for k in data.keys() if not k.startswith("_")]),
            "mode": "overwrite" if overwrite else "merge",
        }
        _atomic_write(POSITIONS_JSON_PATH, data)
        total = data["_meta"]["count"]
    return n, total


# ======================================================================
# 订单
# ======================================================================
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
        _log(f"备份完整订单失败(忽略): {e}")


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


# ======================================================================
# 自选股行情
# ======================================================================
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
            _log(f"⚠ 覆盖被降级为合并：本次 {len(incoming)} 条 < 原有 {old_total} 的一半")
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

    # ------------------------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/sync_positions":
            try:
                body = self._read_json_body()
                if "positions" in body and isinstance(body["positions"], dict):
                    incoming = body["positions"]
                    overwrite = bool(body.get("overwrite", False))
                else:
                    incoming, overwrite = body, False
                n, total = save_positions(incoming, overwrite=overwrite)
                mode_str = "全量覆盖" if overwrite else "增量合并"
                _log(f"[{mode_str}] 同步持仓 {n} 条（文件当前共 {total} 条）")
                self._reply(200, {"status": "ok", "saved": n, "total": total,
                                  "overwrite": overwrite})
            except Exception as e:
                _log(f"处理持仓同步失败: {e}")
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/sync_orders":
            try:
                body = self._read_json_body()
                incoming = body.get("orders") if isinstance(body.get("orders"), dict) else body
                verbose = body.get("verbose", None)
                added, updated, total, shrunk = save_orders(incoming, verbose=verbose)
                _log(f"[追加/{'full' if verbose else 'lean'}] 订单 新增 {added} / 更新 {updated} / "
                     f"累计 {total} / 顺手瘦身 {shrunk}  文件 {_file_size(ORDERS_JSON_PATH)/1024:.1f}KB")
                self._reply(200, {"status": "ok", "added": added, "updated": updated,
                                  "total": total, "shrunk": shrunk,
                                  "bytes": _file_size(ORDERS_JSON_PATH)})
            except Exception as e:
                _log(f"处理订单同步失败: {e}")
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/compact_orders":
            try:
                body = self._read_json_body()
                r = compact_orders(bool(body.get("verbose", False)))
                _log(f"[压缩] 订单 JSON {r.get('before',0)/1024:.1f}KB -> {r.get('after',0)/1024:.1f}KB "
                     f"({r.get('saved_pct',0)}%)，共 {r.get('count',0)} 笔")
                self._reply(200, r)
            except Exception as e:
                _log(f"压缩订单失败: {e}")
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/sync_watchlist":
            try:
                body = self._read_json_body()
                incoming = body.get("quotes") if isinstance(body.get("quotes"), dict) else body
                overwrite = bool(body.get("overwrite", True))
                n, total, mode = save_watchlist(incoming, overwrite=overwrite)
                _log(f"[{mode}] 自选股行情 写入 {n} 条（文件当前共 {total} 条）")
                self._reply(200, {"status": "ok", "saved": n, "total": total, "mode": mode})
            except Exception as e:
                _log(f"处理自选股同步失败: {e}")
                self._reply(500, {"status": "error", "message": str(e)})
            return

        # ---------------- ★ v7 新增：Python 下单添加自选股 ----------------
        if path == "/wl_add":
            try:
                body = self._read_json_body()
                symbol = str(body.get("symbol", "")).strip().upper()
                group = str(body.get("group", "")).strip()
                wait = float(body.get("wait", 0) or 0)
                restore = bool(body.get("restore", True))
                if not symbol:
                    self._reply(400, {"status": "error", "ok": False,
                                      "message": "no symbol"})
                    return
                if group and WATCHLIST_GROUPS and group not in WATCHLIST_GROUPS:
                    _log(f"⚠ 分组「{group}」不在白名单 {WATCHLIST_GROUPS}，仍继续尝试")

                gap = time.time() - _LAST_AGENT_POLL[0]
                tab = ""
                if gap > AGENT_ALIVE_SEC:
                    tab = ensure_watchlist_tab()
                    _log(f"[任务] 无浏览器心跳({gap:.0f}s)，确保标签页 -> {tab}")

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
                        "message": "任务已排队，但未在等待时间内收到浏览器回报。"
                                   "请确认：①Chrome 打开了 /app/watchlist 且已登录；"
                                   "②扩展 popup 里「允许远程添加」是勾选状态。"})
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
                    _log(f"随画图同步持仓 {saved} 条（累计 {total} 条）")
                if not symbol:
                    self._reply(400, {"status": "error", "message": "no symbol"})
                    return
                ok, err = launch_chart(symbol)
                if ok:
                    _log(f"触发绘制图表: {symbol}")
                    self._reply(200, {"status": "ok", "symbol": symbol,
                                      "saved": saved, "total": total})
                else:
                    _log(f"启动图表错误: {err}")
                    self._reply(500, {"status": "error", "message": err})
            except Exception as e:
                _log(f"/plot POST 失败: {e}")
                self._reply(500, {"status": "error", "message": str(e)})
            return

        self._reply(404, {"status": "error", "message": "not found"})

    # ------------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/ping":
            self._reply(200, {
                "status": "ok", "port": PORT, "python": PYTHON_EXEC,
                "chart_script": STOCK_CHART_PY,
                "chart_script_exists": os.path.exists(STOCK_CHART_PY),
                "positions_file": POSITIONS_JSON_PATH,
                "positions_file_exists": os.path.exists(POSITIONS_JSON_PATH),
                "orders_file": ORDERS_JSON_PATH,
                "orders_file_exists": os.path.exists(ORDERS_JSON_PATH),
                "orders_bytes": _file_size(ORDERS_JSON_PATH),
                "orders_schema_default": "full_v1" if ORDER_VERBOSE_DEFAULT else "lean_v1",
                "watchlist_file": WATCHLIST_JSON_PATH,
                "watchlist_file_exists": os.path.exists(WATCHLIST_JSON_PATH),
                "default_wl_source": DEFAULT_WL_SOURCE,
                "earnings_release": EARNINGS_RELEASE_PATH,
                "earnings_release_exists": os.path.exists(EARNINGS_RELEASE_PATH),
                "sectors_all": SECTORS_ALL_PATH,
                "sectors_all_exists": os.path.exists(SECTORS_ALL_PATH),
                "sectors_source_enabled": ENABLE_SECTORS_SOURCE,
                # ★ v7
                "wl_groups": WATCHLIST_GROUPS,
                "wl_tasks_pending": pending_count(),
                "agent_last_poll_ago": (round(time.time() - _LAST_AGENT_POLL[0], 1)
                                        if _LAST_AGENT_POLL[0] else None),
            })
            return

        if path == "/wl_groups":
            self._reply(200, {"status": "ok", "groups": WATCHLIST_GROUPS,
                              "url": WATCHLIST_URL})
            return

        if path == "/wl_tasks":
            _LAST_AGENT_POLL[0] = time.time()
            tasks = take_tasks(_qint(qs, "max", 3))
            if tasks:
                _log(f"[任务] 下发 {len(tasks)} 个给浏览器: "
                     f"{[t['symbol'] + '->' + (t['group'] or '当前') for t in tasks]}")
            self._reply(200, {"status": "ok", "tasks": tasks, "server_time": time.time()})
            return

        if path == "/wl_task":
            tid = qs.get("id", [""])[0]
            with _TASK_LOCK:
                t = _TASKS.get(tid)
                self._reply(200, _task_public(t) if t
                            else {"status": "error", "message": "unknown task"})
            return

        if path == "/wl_source":
            try:
                src = (qs.get("src", [DEFAULT_WL_SOURCE])[0] or DEFAULT_WL_SOURCE)
                self._reply(200, build_wl_source(src, back=_qint(qs, "back", 1),
                                                 ahead=_qint(qs, "ahead", 0)))
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/earnings_release":
            try:
                self._reply(200, load_earnings_symbols(_qint(qs, "back", 1),
                                                       _qint(qs, "ahead", 0)))
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/sectors_all":
            try:
                self._reply(200, build_wl_source("sectors"))
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

        if path == "/plot":
            symbol = qs.get("symbol", [""])[0].strip().upper()
            if not symbol:
                self._reply(400, {"status": "error", "message": "no symbol provided"})
                return
            ok, err = launch_chart(symbol)
            if ok:
                _log(f"触发绘制图表(GET): {symbol}")
                self._reply(200, {"status": "ok", "symbol": symbol})
            else:
                self._reply(500, {"status": "error", "message": err})
            return

        self._reply(404, {"status": "error", "message": "not found"})

    def log_message(self, fmt, *args):
        # 任务轮询很频繁，别刷屏
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
    print(f"  Python        : {PYTHON_EXEC}")
    print(f"  图表脚本      : {STOCK_CHART_PY}  存在={os.path.exists(STOCK_CHART_PY)}")
    print(f"  持仓存储      : {POSITIONS_JSON_PATH}  (覆盖式)")
    print(f"  订单存储      : {ORDERS_JSON_PATH}  (追加式, "
          f"{'full' if ORDER_VERBOSE_DEFAULT else 'LEAN 精简'}, "
          f"{_file_size(ORDERS_JSON_PATH)/1024:.1f}KB)")
    print(f"  自选股行情    : {WATCHLIST_JSON_PATH}  (覆盖式)")
    print(f"  ★默认数据源   : {DEFAULT_WL_SOURCE}")
    print(f"  财报日历      : {EARNINGS_RELEASE_PATH}  存在={_er['file_exists']}")
    print(f"                  {_er['from']}  待同步={_er['count']}  {_er['symbols'][:20]}")
    print(f"  Sectors_All   : {SECTORS_ALL_PATH}  启用={ENABLE_SECTORS_SOURCE}")
    print(f"  ★远程添加分组 : {WATCHLIST_GROUPS}   POST /wl_add")
    print("=" * 72, flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), StockRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
        server.server_close()