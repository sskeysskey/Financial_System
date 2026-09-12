#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地极简 HTTP 桥接服务器 v6
    GET  /ping                        健康检查
    GET  /wl_source?src=earnings|sectors&back=1&ahead=0
                                      自选股补齐的 symbol 数据源（统一入口）
    GET  /earnings_release?back=1      /wl_source?src=earnings 的别名
    GET  /sectors_all                 兼容旧接口（受 ENABLE_SECTORS_SOURCE 控制）
    GET  /positions                   查看持仓 JSON（覆盖式快照）
    GET  /orders                      查看订单 JSON（追加式流水，LEAN schema）
    GET  /watchlist                   查看自选股行情 JSON（覆盖式快照）
    GET  /plot?symbol=AAPL            拉起 Stock_Chart.py（兼容旧版）
    POST /sync_positions              同步持仓（overwrite=True 全量覆盖）
    POST /sync_orders                 追加订单痕迹（★永不删除记录；默认按 LEAN 白名单瘦身）
    POST /sync_watchlist              同步自选股「变更%」（overwrite=True 覆盖 / False 合并）
    POST /compact_orders              一次性把历史订单 JSON 压缩成 LEAN（自动备份 .fat.bak）
    POST /plot  {symbol, positions}   先落盘持仓，再拉起图表（无竞态）
监听端口: 18888
"""
import sys
import os
import re
import json
import time
import shutil
import threading
import subprocess
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

# ★ 新数据源：财报日历
EARNINGS_RELEASE_PATH = os.path.join(BASE_CODING_DIR, "News", "Earnings_Release_new.txt")

# ★ 是否启用 Sectors_All 作为自选股补齐数据源（按需求暂时屏蔽；改成 True 即可恢复）
ENABLE_SECTORS_SOURCE = False

# 默认数据源
DEFAULT_WL_SOURCE = "earnings"

# ★ 需要同步进 Firstrade 自选股的「有效板块」（仅当 ENABLE_SECTORS_SOURCE=True 时生效）
SECTOR_GROUPS_FOR_WATCHLIST = [
    "Basic_Materials",
    "Communication_Services",
    "Consumer_Cyclical",
    "Consumer_Defensive",
    "Energy",
    "Financial_Services",
    "Healthcare",
    "Industrials",
    "Real_Estate",
    "Technology",
    "Utilities",
]

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
# 数据源 B: Earnings_Release_new.txt（新，默认）
#   行格式:  RH     : AMC : 2026-09-10
# ======================================================================
_DATE_IN_LINE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_SYM_CLEAN = re.compile(r"[^A-Z0-9.\-]")


def parse_earnings_release(path=None):
    """-> { date对象: [SYM, ...] }"""
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
                sym = _SYM_CLEAN.sub("", line.split(":")[0].strip().upper())
                if not sym:
                    continue
                arr = out.setdefault(d, [])
                if sym not in arr:
                    arr.append(sym)
    except Exception as e:
        _log(f"解析 {os.path.basename(path)} 失败: {e}")
    return out


def _target_dates(today, back=1, ahead=0):
    """今天 + 向前 back 个『工作日』(跨过周末) + 向后 ahead 个自然日"""
    dates = {today}
    for i in range(1, max(0, ahead) + 1):
        dates.add(today + timedelta(days=i))
    got, cur, guard = 0, today, 0
    while got < max(0, back) and guard < 30:
        cur = cur - timedelta(days=1)
        guard += 1
        dates.add(cur)
        if cur.weekday() < 5:      # 0=周一 ... 4=周五
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
    for d in sorted(picked.keys()):
        for s in picked[d]:
            k = s.replace(".", "").replace("-", "")
            if k in seen:
                continue
            seen.add(k)
            symbols.append(s)

    day_map = {d.isoformat(): picked[d] for d in sorted(picked.keys())}
    if day_map:
        span = f"{min(day_map)}~{max(day_map)}"
    else:
        span = today.isoformat()
    frm = f"财报日历 {span}" + ("（回退到最近财报日）" if used_fallback else "")
    return {
        "status": "ok",
        "source": "earnings_release",
        "file": EARNINGS_RELEASE_PATH,
        "file_exists": os.path.exists(EARNINGS_RELEASE_PATH),
        "from": frm,
        "today": today.isoformat(),
        "back": back,
        "ahead": ahead,
        "fallback": used_fallback,
        "dates": day_map,
        "count": len(symbols),
        "symbols": symbols,
    }


def build_wl_source(src, back=1, ahead=0):
    s = (src or DEFAULT_WL_SOURCE).strip().lower()
    if s in ("earnings", "earnings_release", "er", "release"):
        return load_earnings_symbols(back=back, ahead=ahead)
    if s in ("sectors", "sectors_all", "sector"):
        if not ENABLE_SECTORS_SOURCE:
            return {
                "status": "disabled",
                "source": "sectors_all",
                "symbols": [],
                "count": 0,
                "message": "Sectors_All 数据源已在 bridge_server.py 停用；"
                           "把 ENABLE_SECTORS_SOURCE 改成 True 并重启即可启用。",
            }
        symbols, per_group = load_sector_symbols()
        return {
            "status": "ok",
            "source": "sectors_all",
            "file": SECTORS_ALL_PATH,
            "from": "Sectors_All.json",
            "groups": per_group,
            "count": len(symbols),
            "symbols": symbols,
        }
    return {"status": "error", "message": f"未知数据源: {src}", "symbols": [], "count": 0}


# ======================================================================
# 持仓：覆盖 / 合并
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
# 订单：只追加 / 就地更新，绝不删除；★字段白名单瘦身
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
    """按白名单裁剪单条订单；None/空值直接省略以进一步减小体积"""
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
    """第一次真正裁剪掉字段之前，完整备份一次原文件（只备份一次）"""
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
            "count": len(orders),
            "mode": "append",
            "schema": "full_v1" if verbose else "lean_v1",
        },
        "orders": orders,
    }
    _atomic_write(ORDERS_JSON_PATH, out, backup=True)


def save_orders(incoming, verbose=None):
    """returns (added, updated, total, shrunk)"""
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

        # ★ 全表统一按白名单瘦身（老的胖记录也会被顺手压掉）
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
    """一次性把整个文件压成 LEAN"""
    with _ORDER_LOCK:
        before = _file_size(ORDERS_JSON_PATH)
        data = _load_json(ORDERS_JSON_PATH)
        orders = _extract_orders(data)
        if not orders:
            return {"status": "skip", "reason": "empty", "before": before, "after": before, "count": 0}
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
# 自选股行情（变更%）
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
        # 安全阀：声称覆盖但数量骤降 → 降级为合并
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
            # 覆盖模式：行级时间戳由 _meta 统一提供，省体积；合并模式才逐行打戳
            if overwrite:
                rec.pop("updated_at", None)
            else:
                rec["updated_at"] = rec.get("updated_at") or now
            base[sym] = rec
            n += 1

        out = {
            "_meta": {
                "updated_at": now,
                "updated_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(base),
                "mode": mode,
            },
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
                if "positions" in body and isinstance(body["positions"], dict):
                    incoming = body["positions"]
                    overwrite = bool(body.get("overwrite", False))
                else:
                    incoming, overwrite = body, False
                n, total = save_positions(incoming, overwrite=overwrite)
                mode_str = "全量覆盖" if overwrite else "增量合并"
                _log(f"[{mode_str}] 同步持仓 {n} 条（文件当前共 {total} 条）")
                self._reply(200, {"status": "ok", "saved": n, "total": total, "overwrite": overwrite})
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
                    self._reply(200, {"status": "ok", "symbol": symbol, "saved": saved, "total": total})
                else:
                    _log(f"启动图表错误: {err}")
                    self._reply(500, {"status": "error", "message": err})
            except Exception as e:
                _log(f"/plot POST 失败: {e}")
                self._reply(500, {"status": "error", "message": str(e)})
            return

        self._reply(404, {"status": "error", "message": "not found"})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/ping":
            self._reply(200, {
                "status": "ok",
                "port": PORT,
                "python": PYTHON_EXEC,
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
            })
            return

        if path == "/wl_source":
            try:
                src = (qs.get("src", [DEFAULT_WL_SOURCE])[0] or DEFAULT_WL_SOURCE)
                back = _qint(qs, "back", 1)
                ahead = _qint(qs, "ahead", 0)
                self._reply(200, build_wl_source(src, back=back, ahead=ahead))
            except Exception as e:
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/earnings_release":
            try:
                self._reply(200, load_earnings_symbols(_qint(qs, "back", 1), _qint(qs, "ahead", 0)))
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
        sys.stderr.write(f"[BridgeServer] {fmt % args}\n")


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
    print("=" * 72, flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), StockRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
        server.server_close()