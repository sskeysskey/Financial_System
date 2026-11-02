#!/bin/bash
# run_mw_daily.sh —— launchd 入口：唤醒 → 解锁 → 等网络 → 在 Terminal 新窗口中启动 run_pipeline.sh
# 本脚本只做"准备工作"，真正的抓取流程在 run_pipeline.sh 里（可见、可中断、可重跑）。
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG="${LANG:-en_US.UTF-8}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="/Library/Frameworks/Python.framework/Versions/Current/bin/python3"   # 与快捷键使用同一个 python
PIPELINE="$SELF_DIR/run_pipeline.sh"
LOG_DIR="$HOME/Library/Logs/mw_daily"
LOCK_DIR="/tmp/mw_daily.lock"           # 与 run_pipeline.sh 共用
KEYCHAIN_SERVICE="mw_mac_login"
ME="$(id -un)"
NET_URLS=("https://www.marketwatch.com" "https://tradingeconomics.com")
NET_MAX_TRIES=10                        # 每 30 秒一次，最多约 5 分钟（刚唤醒时 Wi-Fi 重连较慢）

mkdir -p "$LOG_DIR"
exec >>"$LOG_DIR/$(date +%F)_launcher.log" 2>&1

log()    { echo "[$(date '+%F %T')] $*"; }
notify() { osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title "MW_Daily"' \
                     -e 'end run' "$1" >/dev/null 2>&1 || true; }

pipeline_running() {
    local pid
    pid=$(cat "$LOCK_DIR/pid" 2>/dev/null) || return 1
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# 返回 0=已锁屏  1=未锁屏  2=无法判断（无法判断时绝不输入密码，防止密码被敲进普通窗口）
screen_lock_state() {
    local r
    r=$("$PY" -c 'import Quartz
d = Quartz.CGSessionCopyCurrentDictionary()
if d is None:
    print("unknown")
else:
    print("locked" if d.get("CGSSessionScreenIsLocked", 0) else "unlocked")' 2>/dev/null)
    case "$r" in
        locked)   return 0 ;;
        unlocked) return 1 ;;
    esac
    # 兜底：Quartz(pyobjc) 不可用时尝试 ioreg
    if ioreg -n Root -d1 2>/dev/null | grep -q '"CGSSessionScreenIsLocked"=Yes'; then
        return 0
    fi
    return 2
}

sys_events() { osascript -e "tell application \"System Events\" to $1" >/dev/null 2>&1; }

type_password() {
    # 通过环境变量传给 osascript，而不是命令行参数（命令行参数任何用户都能用 ps 看到）
    MW_PW="$1" osascript -e 'tell application "System Events" to keystroke (system attribute "MW_PW")' \
        >/dev/null 2>&1
}

unlock_screen() {
    local pw st i t
    pw=$(security find-generic-password -a "$ME" -s "$KEYCHAIN_SERVICE" -w 2>/dev/null) || pw=""
    if [ -z "$pw" ]; then
        log "钥匙串中没有服务名为 $KEYCHAIN_SERVICE 的密码，无法自动解锁"
        return 1
    fi
    for i in 1 2 3; do
        caffeinate -u -t 10 >/dev/null 2>&1 &
        sleep 2
        sys_events 'key code 56'          # 轻按 Shift 唤出密码框（不会像空格那样往密码框里输入字符）
        sleep 1.5
        screen_lock_state; st=$?
        if [ $st -eq 1 ]; then pw=""; log "屏幕已处于解锁状态"; return 0; fi
        if [ $st -ne 0 ]; then pw=""; log "锁屏状态无法判断，出于安全考虑不输入密码"; return 1; fi
        sys_events 'repeat 30 times
key code 51
end repeat'                               # 清空密码框里可能残留的字符
        type_password "$pw"
        sleep 0.3
        sys_events 'key code 36'          # 回车
        for t in $(seq 1 10); do
            sleep 1
            screen_lock_state
            if [ $? -eq 1 ]; then pw=""; log "解锁成功（第 $i 次尝试）"; return 0; fi
        done
        log "第 $i 次解锁未成功"
    done
    pw=""
    return 1
}

net_ok() {
    local u code
    for u in "${NET_URLS[@]}"; do
        code=$(curl -sS -o /dev/null -m 15 -A "Mozilla/5.0" -w '%{http_code}' "$u" 2>/dev/null)
        if [ -z "$code" ] || [ "$code" = "000" ]; then
            log "不可达: $u"
            return 1
        fi
    done
    return 0      # 任何 HTTP 状态码（包括 403 反爬）都说明网络是通的
}

launch_in_terminal() {
    local cmd
    cmd="/bin/bash $(printf %q "$PIPELINE") --unattended"
    osascript - "$cmd" <<'APPLESCRIPT'
on run argv
    set cmd to item 1 of argv
    tell application "Terminal"
        set wasRunning to it is running
        activate
        if not wasRunning then delay 1.5
        set reused to false
        if (not wasRunning) and ((count of windows) > 0) then
            try
                if busy of selected tab of front window is false then
                    do script cmd in front window
                    set reused to true
                end if
            end try
        end if
        if not reused then do script cmd
        activate
    end tell
end run
APPLESCRIPT
}

# ======================= 主流程 =======================
log "================ launcher 开始 ================"

if pipeline_running; then
    log "流水线已在运行（PID $(cat "$LOCK_DIR/pid")），本次退出"
    exit 0
fi
if [ -f "$LOG_DIR/.done_$(date +%F)" ]; then
    log "今天的流水线已成功完成过，本次退出（如需重跑请手动执行 run_pipeline.sh）"
    exit 0
fi

caffeinate -dimsu -w $$ >/dev/null 2>&1 &     # 启动器存活期间不睡眠
caffeinate -u -t 20 >/dev/null 2>&1 &         # 点亮屏幕
sleep 5
log "已发送唤醒信号"

# ---------- 1. 解锁 ----------
screen_lock_state; st=$?
case $st in
    0) log "屏幕已锁定，尝试自动解锁"
       if ! unlock_screen; then
           log "自动解锁失败，退出"
           notify "自动解锁失败，请手动解锁后运行 run_pipeline.sh"
           exit 1
       fi ;;
    1) log "屏幕未锁定，跳过解锁" ;;
    *) log "⚠️ 无法判断锁屏状态（请安装 pyobjc-framework-Quartz），不自动输入密码，直接继续" ;;
esac
sleep 2

# ---------- 2. 网络 ----------
ok=0
for i in $(seq 1 "$NET_MAX_TRIES"); do
    if net_ok; then ok=1; log "网络可达（第 $i 次检测）"; break; fi
    log "网络不通（第 $i/$NET_MAX_TRIES 次），30 秒后重试"
    sleep 30
done
if [ "$ok" -ne 1 ]; then
    log "网络长时间不通，放弃本次任务"
    notify "网络不通，任务取消"
    exit 1
fi

# ---------- 3. 在 Terminal 中启动流水线 ----------
if launch_in_terminal; then
    log "已请求 Terminal 启动流水线"
else
    log "⚠️ 无法控制 Terminal（检查 自动化 权限）"
fi

# 确认流水线确实启动了；没启动就退化为后台运行（看不到界面，但任务不丢）
for i in $(seq 1 30); do
    pipeline_running && break
    sleep 1
done
if pipeline_running; then
    log "流水线已启动（PID $(cat "$LOCK_DIR/pid")）"
else
    log "Terminal 中未检测到流水线，改为后台运行"
    nohup /bin/bash "$PIPELINE" --unattended >/dev/null 2>&1 &
    notify "无法打开 Terminal，已在后台运行，日志见 ~/Library/Logs/mw_daily"
fi
log "================ launcher 结束 ================"