#!/bin/bash
# run_verify_yf.sh —— 手动执行：Verify_wrong（交互确认）→ YF_Today（自动）
# 用法: bash ~/Coding/Financial_System/Selenium/run_verify_yf.sh
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

PY="/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
FS_DIR="$HOME/Coding/Financial_System"
VERIFY_SCRIPT="$FS_DIR/Selenium/Verify_wrong.py"
YF_SCRIPT="$FS_DIR/Selenium/YF_Today.py"
WRONG_TXT="$HOME/Coding/News/wrong.txt"
PIPE_LOCK="/tmp/mw_daily.lock"            # run_mw_yf_pipeline.sh 使用的锁
MY_LOCK="/tmp/mw_verify_yf.lock"          # 本脚本自己的锁

log() { echo "[$(date '+%F %T')] $*"; }
has_entries() { [ -s "$WRONG_TXT" ] && grep -qvE '^[[:space:]]*(#|$)' "$WRONG_TXT"; }

# 单实例锁
if ! mkdir "$MY_LOCK" 2>/dev/null; then
    log "已有补验证在运行，本次退出"
    exit 1
fi
trap 'rm -rf "$MY_LOCK"' EXIT

# 避免与主流水线并发（两者都会写 Sectors_empty.json / Finance.db）
pid=$(cat "$PIPE_LOCK/pid" 2>/dev/null)
if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    log "主流水线仍在运行（PID $pid），请等它结束后再执行"
    exit 1
fi

caffeinate -i -w $$ >/dev/null 2>&1 &     # 运行期间防止睡眠
cd "$FS_DIR/Selenium" || exit 1

# ---------- 1. Verify_wrong：交互确认（不加 --unattended） ----------
if has_entries; then
    log "▶ 1/2 Verify_wrong（交互确认模式）"
    "$PY" -u "$VERIFY_SCRIPT" --mode confirm
    log "◀ Verify_wrong 退出码 $?（2 = 仍有未解决条目，属正常）"
else
    log "wrong.txt 为空或不存在，跳过 Verify_wrong"
fi

# ---------- 2. YF_Today：无论第 1 步结果如何都执行 ----------
log "▶ 2/2 YF_Today"
"$PY" -u "$YF_SCRIPT"
log "◀ YF_Today 退出码 $?"

log "================ 全部结束 ================"