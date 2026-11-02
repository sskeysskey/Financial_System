#!/bin/bash
# run_pipeline.sh —— 日更流水线：TE_Merged → Check_yesterday → MW_Today
# 用法:
#   bash run_pipeline.sh                  # 手动完整执行
#   bash run_pipeline.sh --from check     # 从 Check_yesterday 开始
#   bash run_pipeline.sh --from mw        # 只跑 MW_Today
#   bash run_pipeline.sh --unattended     # 无人值守（定时器用）：所有弹窗改为通知，结束后熄屏锁定
# 运行中随时 Ctrl+C 可终止整个流水线（会先让 Python 正常退出并关闭 Chrome）。
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1          # 关键：经过管道后输出依然实时显示
export PYTHONIOENCODING=utf-8

PY="/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
FS_DIR="$HOME/Coding/Financial_System"
TE_SCRIPT="$FS_DIR/Selenium/TE_Merged.py"
CHECK_SCRIPT="$FS_DIR/Query/Check_yesterday.py"
MW_SCRIPT="$FS_DIR/Selenium/MW_Today.py"
EMPTY_JSON="$FS_DIR/Modules/Sectors_empty.json"
LOG_DIR="$HOME/Library/Logs/mw_daily"
LOCK_DIR="/tmp/mw_daily.lock"
KEEP_LOG_DAYS=30
RELOCK_AFTER_DONE=1                # 无人值守模式结束后熄屏（有密码时会自动锁屏），保证安全

FROM="te"; UNATTENDED=0
while [ $# -gt 0 ]; do
    case "$1" in
        --from)       FROM="${2:-te}"; shift 2 ;;
        --unattended) UNATTENDED=1; shift ;;
        -h|--help)    sed -n '2,9p' "$0"; exit 0 ;;
        *)            echo "未知参数: $1"; exit 2 ;;
    esac
done
case "$FROM" in
    te) START=1 ;; check) START=2 ;; mw) START=3 ;;
    *)  echo "--from 只能是 te / check / mw"; exit 2 ;;
esac
export FS_UNATTENDED="$UNATTENDED"   # Python 脚本据此把阻塞式弹窗改为通知

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%F_%H%M%S)_pipeline.log"
find "$LOG_DIR" -type f -name '*.log' -mtime +"$KEEP_LOG_DAYS" -delete 2>/dev/null
find "$LOG_DIR" -type f -name '.done_*' -mtime +7 -delete 2>/dev/null

log()    { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
notify() { osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title "MW_Daily"' \
                     -e 'end run' "$1" >/dev/null 2>&1 || true; }

# ---------- 单实例锁（mkdir 是原子操作；进程被强杀后可识别残留锁） ----------
acquire_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then echo $$ >"$LOCK_DIR/pid"; return 0; fi
    local old; old=$(cat "$LOCK_DIR/pid" 2>/dev/null)
    if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then return 1; fi
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR" 2>/dev/null && echo $$ >"$LOCK_DIR/pid"
}
release_lock() { [ "$(cat "$LOCK_DIR/pid" 2>/dev/null)" = "$$" ] && rm -rf "$LOCK_DIR"; }

if ! acquire_lock; then
    echo "⚠️ 已有流水线在运行（PID $(cat "$LOCK_DIR/pid" 2>/dev/null)），本次退出。"
    exit 0
fi
trap release_lock EXIT
trap 'log "⛔ 用户中断 (Ctrl+C)，流水线终止。重跑: bash $0 --from te|check|mw"; notify "流水线已被手动中断"; exit 130' INT TERM

caffeinate -dimsu -w $$ >/dev/null 2>&1 &    # 整个流水线期间：不睡眠、屏幕常亮（避免锁屏影响滑块）

SUMMARY=""
ALL_OK=1
run_step() {
    local idx="$1" name="$2"; shift 2
    if [ "$idx" -lt "$START" ]; then log "⏭  [$idx/3] 跳过 $name"; return 0; fi
    log "▶▶▶ [$idx/3] 开始 $name"
    local t0; t0=$(date +%s)
    # tee 忽略 SIGINT：Ctrl+C 时 Python 还能把收尾日志写完并关闭 Chrome（否则会 BrokenPipe）
    "$@" 2>&1 | ( trap '' INT; exec tee -a "$LOG" )
    local rc=${PIPESTATUS[0]}
    log "◀◀◀ [$idx/3] $name 结束，退出码 ${rc}，耗时 $(( $(date +%s) - t0 )) 秒"
    SUMMARY="$SUMMARY $name=$rc"
    [ "$rc" -ne 0 ] && ALL_OK=0
    return 0      # 单步失败不中断后续（每一步都是幂等的，后续步骤仍有意义）
}

cd "$FS_DIR/Selenium" || exit 1
log "================ 流水线开始（起点: ${FROM} | 无人值守: ${UNATTENDED}）================"
log "日志文件: $LOG    （Ctrl+C 可随时终止）"

run_step 1 "TE_Merged"       "$PY" -u "$TE_SCRIPT" --skipetf
run_step 2 "Check_yesterday" "$PY" -u "$CHECK_SCRIPT" --nopop
run_step 3 "MW_Today"        "$PY" -u "$MW_SCRIPT" --headful

EMPTY_OK=0
if "$PY" -c 'import json,sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if all(not v for v in d.values()) else 1)' "$EMPTY_JSON" 2>/dev/null; then
    EMPTY_OK=1
fi

log "================ 流水线结束 ================"
log "各步骤退出码:$SUMMARY | Sectors_empty 已清空: $([ $EMPTY_OK -eq 1 ] && echo 是 || echo 否)"

if [ "$ALL_OK" -eq 1 ] && [ "$EMPTY_OK" -eq 1 ]; then
    touch "$LOG_DIR/.done_$(date +%F)"
    notify "✅ 今日数据全部完成"
    log "✅ 今日数据全部完成"
else
    notify "⚠️ 流水线有未完成项，请查看 Terminal / 日志"
    log "⚠️ 有未完成项。可重跑: bash $0 --from mw"
fi

if [ "$UNATTENDED" -eq 1 ] && [ "$RELOCK_AFTER_DONE" -eq 1 ]; then
    log "60 秒后熄屏锁定（无人值守模式）"
    sleep 60
    pmset displaysleepnow
fi