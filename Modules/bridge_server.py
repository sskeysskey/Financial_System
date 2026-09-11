#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地极简 HTTP 桥接服务器 v4
    GET  /ping                        健康检查
    GET  /positions                   查看已保存的持仓 JSON（覆盖式快照）
    GET  /orders                      查看已保存的订单 JSON（追加式流水）
    GET  /plot?symbol=AAPL            拉起 Stock_Chart.py（兼容旧版）
    POST /sync_positions              同步持仓（overwrite=True 全量覆盖）
    POST /sync_orders                 追加订单痕迹（★永不删除已有记录）
    POST /plot  {symbol, positions}   先落盘持仓，再拉起图表（无竞态）
监听端口: 18888
"""
import sys
import os
import json
import time
import shutil
import threading
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 18888
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
STOCK_CHART_PY = os.path.join(BASE_CODING_DIR, "Financial_System", "Query", "Stock_Chart.py")
MODULES_DIR = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules")
POSITIONS_JSON_PATH = os.path.join(MODULES_DIR, "firstrade_positions.json")
ORDERS_JSON_PATH = os.path.join(MODULES_DIR, "firstrade_orders.json")

PYTHON_EXEC = os.environ.get("FT_PYTHON") or sys.executable

_FILE_LOCK = threading.Lock()
_ORDER_LOCK = threading.Lock()


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
        json.dump(obj, f, ensure_ascii=False, indent=2)
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


# ----------------------------------------------------------------------
# 持仓：覆盖 / 合并
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# 订单：只追加 / 就地更新，绝不删除
# ----------------------------------------------------------------------
def save_orders(incoming):
    if not isinstance(incoming, dict) or not incoming:
        return 0, 0, 0

    with _ORDER_LOCK:
        data = _load_json(ORDERS_JSON_PATH)
        orders = data.get("orders")
        if not isinstance(orders, dict):
            # 兼容早期可能直接把订单铺在根上的情况
            orders = {k: v for k, v in data.items()
                      if isinstance(v, dict) and not str(k).startswith("_")}
        old_total = len(orders)

        added = updated = 0
        now = time.time()
        for key, val in incoming.items():
            if not isinstance(val, dict):
                continue
            k = str(key).strip()
            sym = str(val.get("symbol", "")).strip().upper()
            side = str(val.get("side", "")).strip().lower()
            date = str(val.get("date", "")).strip()
            if not k or not sym or side not in ("buy", "sell") or not date:
                continue

            rec = dict(val)
            rec["symbol"] = sym
            rec["side"] = side

            old = orders.get(k)
            if old:
                merged = dict(old)
                for kk, vv in rec.items():
                    if vv not in (None, "", {}):
                        merged[kk] = vv
                merged["first_seen"] = old.get("first_seen", now)
                merged["updated_at"] = now
                orders[k] = merged
                updated += 1
            else:
                rec["first_seen"] = now
                rec["updated_at"] = now
                orders[k] = rec
                added += 1

        total = len(orders)
        # 安全阀：只增不减
        if total < old_total:
            _log(f"⚠ 拒绝写入：合并后条数 {total} < 原有 {old_total}")
            return 0, 0, old_total

        out = {
            "_meta": {
                "updated_at": now,
                "updated_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": total,
                "mode": "append",
            },
            "orders": orders,
        }
        _atomic_write(ORDERS_JSON_PATH, out, backup=True)
    return added, updated, total


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
                added, updated, total = save_orders(incoming)
                _log(f"[追加] 订单 新增 {added} / 更新 {updated} / 累计 {total} -> {ORDERS_JSON_PATH}")
                self._reply(200, {"status": "ok", "added": added, "updated": updated, "total": total})
            except Exception as e:
                _log(f"处理订单同步失败: {e}")
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
            })
            return

        if path == "/positions":
            self._reply(200, _load_json(POSITIONS_JSON_PATH))
            return

        if path == "/orders":
            self._reply(200, _load_json(ORDERS_JSON_PATH))
            return

        if path == "/plot":
            symbol = parse_qs(parsed.query).get("symbol", [""])[0].strip().upper()
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
    print("=" * 62)
    print(f"  Firstrade 本地桥接服务已启动: http://127.0.0.1:{PORT}")
    print(f"  Python      : {PYTHON_EXEC}")
    print(f"  图表脚本    : {STOCK_CHART_PY}  存在={os.path.exists(STOCK_CHART_PY)}")
    print(f"  持仓存储    : {POSITIONS_JSON_PATH}  (覆盖式)")
    print(f"  订单存储    : {ORDERS_JSON_PATH}  (追加式)")
    print("=" * 62, flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), StockRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
        server.server_close()