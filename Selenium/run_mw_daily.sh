#!/bin/bash
# run_mw_daily.sh —— 每日定时：唤醒 → 解锁 → 检测网络 → 运行 MW_Today.py

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"                       # ← 改成你的 python3 路径
SCRIPT="/Users/yanzhang/Coding/Financial_System/Selenium/MW_Today.py"
LOG_DIR="$HOME/Library/Logs/mw_daily"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"
exec >>"$LOG" 2>&1                                   # 所有输出写入日志

# ---------- 防止重复运行 ----------
LOCK="/tmp/mw_daily.lock"
if [ -e "$LOCK" ]; then
    echo "[$(date '+%F %T')] 已有任务在运行，本次退出"
    exit 0
fi
touch "$LOCK"
trap 'rm -f "$LOCK"' EXIT

log() { echo "[$(date '+%F %T')] $*"; }

# 是否锁屏：返回 0 表示已锁定
is_locked() {
    "$PY" -c 'import sys, Quartz
d = Quartz.CGSessionCopyCurrentDictionary()
sys.exit(0 if d and d.get("CGSSessionScreenIsLocked", 0) else 1)' 2>/dev/null
}

# 目标网站是否可达
net_ok() {
    "$PY" -c 'import sys, urllib.request, urllib.error
try:
    urllib.request.urlopen("https://www.marketwatch.com", timeout=10)
    sys.exit(0)
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}，网站可达", file=sys.stderr)
    sys.exit(0)
except Exception as e:
    print(f"{type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)' 
}

log "========== 任务开始 =========="

# ---------- 1. 唤醒屏幕 ----------
caffeinate -u -t 10 &
sleep 5
log "已发送唤醒信号"

# ---------- 2. 解锁（若已锁屏）----------
if is_locked; then
    log "屏幕已锁定，尝试自动解锁"
    PW=$(security find-generic-password -a "$USER" -s mw_mac_login -w 2>/dev/null)
    if [ -z "$PW" ]; then
        log "钥匙串中没有密码，无法自动解锁"
        osascript -e 'display notification "请手动解锁后重试" with title "MW_Today"'
        exit 1
    fi
    osascript -e 'tell application "System Events" to key code 49'   # 空格键唤醒锁屏界面
    sleep 1
    # 把密码作为参数传入，避免特殊字符出错
    osascript -e 'on run argv' \
              -e 'tell application "System Events" to keystroke (item 1 of argv)' \
              -e 'end run' "$PW"
    osascript -e 'tell application "System Events" to key code 36'   # 回车
    sleep 4
    if is_locked; then
        log "自动解锁失败，退出"
        osascript -e 'display notification "自动解锁失败" with title "MW_Today"'
        exit 1
    fi
    log "解锁成功"
else
    log "屏幕未锁定，跳过解锁"
fi

# ---------- 3. 检测网络（最多重试 5 次，约 2.5 分钟）----------
ok=0
for i in $(seq 1 5); do
    if net_ok; then
        ok=1
        log "网络可达（第 $i 次检测）"
        break
    fi
    log "网络不通（第 $i 次），30 秒后重试"
    sleep 30
done
if [ "$ok" -ne 1 ]; then
    log "网络长时间不通，放弃本次任务"
    osascript -e 'display notification "网络不通，任务取消" with title "MW_Today"'
    exit 1
fi

# ---------- 4. 运行主程序（全程防休眠、屏幕常亮）----------
cd "$(dirname "$SCRIPT")" || exit 1
log "开始运行 MW_Today.py"
caffeinate -dimsu "$PY" "$SCRIPT"
rc=$?
log "MW_Today.py 已退出，退出码 $rc"
log "========== 任务结束 =========="