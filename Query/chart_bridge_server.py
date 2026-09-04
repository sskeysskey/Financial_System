#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地极简 HTTP 桥接服务器：
接收 Chrome 插件发来的股票代码，无缝拉起 Stock_Chart.py
监听端口: 18888
"""
import sys
import os
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 18888
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
STOCK_CHART_PY = os.path.join(BASE_CODING_DIR, "Financial_System", "Query", "Stock_Chart.py")
PYTHON_EXEC = sys.executable

class StockRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        # 处理 CORS 预检请求
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/plot':
            params = parse_qs(parsed.query)
            symbol = params.get('symbol', [''])[0].strip().upper()

            if symbol:
                print(f"[ChartBridge] 触发绘制图表: {symbol}")
                try:
                    # 使用当前解释器以非阻塞方式启动 Stock_Chart.py
                    # 传入 paste 参数前将 symbol 设置到剪贴板，或者修改 Stock_Chart 接收直接参数
                    import pyperclip
                    pyperclip.copy(symbol)

                    subprocess.Popen([PYTHON_EXEC, STOCK_CHART_PY, 'paste'])
                    response_body = f'{{"status":"ok","symbol":"{symbol}"}}'
                    status_code = 200
                except Exception as e:
                    print(f"[ChartBridge] 启动错误: {e}")
                    response_body = f'{{"status":"error","message":"{str(e)}"}}'
                    status_code = 500
            else:
                response_body = '{"status":"error","message":"no symbol provided"}'
                status_code = 400

            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response_body.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # 静默常规请求日志，避免刷屏
        sys.stderr.write(f"[BridgeServer] {format % args}\n")

if __name__ == '__main__':
    print(f"==================================================")
    print(f"  Firstrade 本地图表桥接服务已启动在端口: {PORT}")
    print(f"  等待浏览器扩展点击股票代码...")
    print(f"==================================================")
    server = HTTPServer(('127.0.0.1', PORT), StockRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
        server.server_close()