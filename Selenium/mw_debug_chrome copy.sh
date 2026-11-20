#!/bin/bash
# mw_debug_chrome.sh —— 管理 MarketWatch 附着模式用的调试 Chrome
# 用法: bash mw_debug_chrome.sh start | stop
set -u
CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE_DIR="$HOME/Downloads/backup/mw_chrome_debug_profile"
PORT=9222
PROBE_URL="http://127.0.0.1:${PORT}/json/version"
MARK="/tmp/mw_debug_chrome.started"    # 标记：由本脚本启动的窗口才会在 stop 时关闭

is_up() { curl -s -m 2 "$PROBE_URL" >/dev/null 2>&1; }

case "${1:-}" in
    start)
        if is_up; then
            echo "调试 Chrome 已在运行，直接复用（不会在结束时关闭它）"
            exit 0
        fi
        mkdir -p "$PROFILE_DIR"
        nohup "$CHROME_BIN" --remote-debugging-port=$PORT \
            --user-data-dir="$PROFILE_DIR" --lang=en-US >/dev/null 2>&1 &
        for i in $(seq 1 60); do
            if is_up; then
                touch "$MARK"
                echo "调试 Chrome 已启动（约 ${i} 秒就绪）"
                exit 0
            fi
            sleep 1
        done
        echo "⚠️ 调试 Chrome 启动超时"
        exit 1 ;;
    stop)
        if [ -f "$MARK" ]; then
            pkill -f "user-data-dir=$PROFILE_DIR"
            rm -f "$MARK"
            sleep 2
            echo "已关闭本次启动的调试 Chrome"
        else
            echo "调试 Chrome 不是本次流水线启动的，保留不关"
        fi
        exit 0 ;;
    *)
        echo "用法: $0 start|stop"; exit 2 ;;
esac