#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地极简 HTTP 桥接服务器 v3
    GET  /ping                      健康检查
    GET  /positions                 查看已保存的持仓 JSON（调试用）
    GET  /plot?symbol=AAPL          拉起 Stock_Chart.py（兼容旧版）
    POST /sync_positions            仅同步持仓数据
    POST /plot  {symbol, positions} ★推荐：先落盘持仓，再拉起图表（无竞态）
监听端口: 18888
"""
import sys
import os
import json
import time
import threading
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 18888
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
STOCK_CHART_PY = os.path.join(BASE_CODING_DIR, "Financial_System", "Query", "Stock_Chart.py")
POSITIONS_JSON_PATH = os.path.join(
    BASE_CODING_DIR, "Financial_System", "Modules", "firstrade_positions.json"
)
# 需要用另一个解释器跑 GUI 时：export FT_PYTHON=/path/to/python
PYTHON_EXEC = os.environ.get("FT_PYTHON") or sys.executable

_FILE_LOCK = threading.Lock()


def _log(msg):
    print(f"[ChartBridge] {msg}", flush=True)


def _load_positions():
    if not os.path.exists(POSITIONS_JSON_PATH):
        return {}
    try:
        with open(POSITIONS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        _log(f"读取旧持仓文件失败（将重建）: {e}")
        return {}


def save_positions(incoming):
    """增量合并 + 原子写盘。返回 (新增/更新条数, 总条数)"""
    if not isinstance(incoming, dict) or not incoming:
        return 0, 0

    with _FILE_LOCK:
        data = _load_positions()
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
        }

        os.makedirs(os.path.dirname(POSITIONS_JSON_PATH), exist_ok=True)
        tmp = POSITIONS_JSON_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, POSITIONS_JSON_PATH)

        total = data["_meta"]["count"]
    return n, total


def launch_chart(symbol):
    try:
        try:
            import pyperclip
            pyperclip.copy(symbol)
        except Exception:
            pass
        subprocess.Popen(
            [PYTHON_EXEC, STOCK_CHART_PY, symbol],
            start_new_session=True,
        )
        return True, None
    except Exception as e:
        return False, str(e)


class StockRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---------- 公共响应工具 ----------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        # ★★★ 关键：Chrome Private Network Access 预检必须要这个头，
        #          否则 https 页面向 127.0.0.1 发 POST 会被直接拦掉。
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

    # ---------- 路由 ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/sync_positions":
            try:
                incoming = self._read_json_body()
                n, total = save_positions(incoming)
                _log(f"同步持仓 {n} 条（文件累计 {total} 条）-> {POSITIONS_JSON_PATH}")
                self._reply(200, {"status": "ok", "saved": n, "total": total})
            except Exception as e:
                _log(f"处理持仓同步失败: {e}")
                self._reply(500, {"status": "error", "message": str(e)})
            return

        if path == "/plot":
            try:
                payload = self._read_json_body()
                symbol = str(payload.get("symbol", "")).strip().upper()
                positions = payload.get("positions") or {}

                saved, total = (0, 0)
                if positions:
                    saved, total = save_positions(positions)   # ★ 先落盘
                    _log(f"随画图同步持仓 {saved} 条（累计 {total} 条）")

                if not symbol:
                    self._reply(400, {"status": "error", "message": "no symbol"})
                    return

                ok, err = launch_chart(symbol)                  # ★ 再启动
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
            })
            return

        if path == "/positions":
            self._reply(200, _load_positions())
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
    print("=" * 58)
    print(f"  Firstrade 本地桥接服务已启动: http://127.0.0.1:{PORT}")
    print(f"  Python      : {PYTHON_EXEC}")
    print(f"  图表脚本    : {STOCK_CHART_PY}  存在={os.path.exists(STOCK_CHART_PY)}")
    print(f"  持仓存储    : {POSITIONS_JSON_PATH}")
    print("=" * 58, flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), StockRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
        server.server_close()