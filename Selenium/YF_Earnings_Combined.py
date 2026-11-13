import os
import re
import sys
import shutil
import json
import time
import random
import socket
from urllib.parse import quote
import subprocess
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta, date
from urllib.request import build_opener, ProxyHandler, Request, getproxies
import platform
from playwright.sync_api import sync_playwright   # Part C 使用

# 第三方模块
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException

SCRIPT_NAME = os.path.basename(__file__)

# ================= 配置区域 (跨平台) =================

USER_HOME = os.path.expanduser("~")

BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
NEWS_DIR = os.path.join(BASE_CODING_DIR, "News")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")

if platform.system() == 'Darwin':
    CHROME_BINARY_PATH = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver_beta")
elif platform.system() == 'Windows':
    CHROME_BINARY_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(CHROME_BINARY_PATH):
        CHROME_BINARY_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver.exe")
else:
    CHROME_BINARY_PATH = "/usr/bin/google-chrome"
    CHROME_DRIVER_PATH = "/usr/bin/chromedriver"

SECTORS_ALL_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, 'Modules', 'Sectors_All.json')
SECTORS_PANEL_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, 'Modules', 'Sectors_panel.json')
SYMBOL_MAPPING_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, 'Modules', 'Symbol_mapping.json')
POLYMARKET_FILE_PATH = os.path.join(NEWS_DIR, "earning_polymarket.txt")
POLYMARKET_URL = "https://polymarket.com/earnings"

BACKUP_ROOT_DIR = os.path.join(NEWS_DIR, 'backup', 'backup')
EARNINGS_ARCHIVE_PATH = os.path.join(NEWS_DIR, 'backup', 'Earnings_Release.txt')
ECONOMIC_ARCHIVE_PATH = os.path.join(NEWS_DIR, 'backup', 'Economic_Events.txt')
EARNINGS_DIFF_EXPIRED_PATH = os.path.join(BACKUP_ROOT_DIR, 'Earnings_Release_diff_expired.txt')

# 分组顺序 = 相对本周的周偏移 (new=0, next=1, ...)
EARNINGS_GROUPS = ['new', 'next', 'third', 'fourth', 'fifth']
ECONOMIC_GROUPS = ['new', 'next']

def earnings_file(group):
    return os.path.join(NEWS_DIR, f'Earnings_Release_{group}.txt')

def earnings_diff_file(group):
    return os.path.join(NEWS_DIR, f'Earnings_Release_diff_{group}.txt')

def economic_file(group):
    return os.path.join(NEWS_DIR, f'Economic_Events_{group}.txt')

# 不在 fifth 轮次收录的股票黑名单（可随时扩充）
EXCLUDE_FROM_FIFTH = {"HDB", "IBN", "BRK-B"}

# 经济事件过滤器
EVENT_FILTER_BASES = {
    "GDP 2nd Estimate", "GDP Advance", "GDP Final", "GDP Cons Spending Prelim",
    "GDP Cons Spending Final", "Non-Farm Payrolls", "ISM N-Mfg PMI", "ISM Manufacturing PMI",
    "ADP National Employment", "Unemployment Rate", "International Trade", "Import Prices MM",
    "Import Prices YY", "CPI MM, SA", "CPI YY, NSA", "Core CPI MM, SA", "Core CPI YY, NSA",
    "Fed Funds Tgt Rate", "PPI Final Demand YY", "PPI exFood/Energy MM", "PPI exFood/Energy YY",
    "PPI ex Food/Energy/Tr MM", "PPI Final Demand MM", "PCE Prices Final", "PCE Price Index MM",
    "PCE Price Index YY", "Core PCE Prices Final", "Core PCE Prices Prelim", "Core PCE Price Index MM",
    "Core PCE Price Index YY", "U Mich Sentiment Prelim", "Retail Sales MM", "Initial Jobless Clm",
    "U Mich Sentiment Final", "New Home Sales Chg MM", "New Home Sales-Units",
}
# 长的优先匹配，保证结果确定（set 迭代顺序不固定）
EVENT_FILTER_ORDERED = sorted(EVENT_FILTER_BASES, key=len, reverse=True)

# 整个运行过程统一使用启动时的日期，避免跨午夜导致周归属前后不一致
RUN_TODAY = datetime.now().date()
YAHOO_PROBE_URL = f"https://finance.yahoo.com/calendar/earnings?day={RUN_TODAY.strftime('%Y-%m-%d')}"

# ================= 浏览器 / 网络配置 =================
# cdp      : (默认) 启动"正常的有界面 Chrome"(独立 profile + 调试端口)，Selenium 附着上去操作；
#            遇到同意页/人机验证/网络异常时提醒你在窗口里手动处理，恢复后自动继续
# headless : 旧方式，无头 Chrome（无人值守时用，遇到验证无法人工处理）
BROWSER_MODE = os.environ.get("YF_BROWSER_MODE", "cdp").strip().lower()
CDP_PORT = int(os.environ.get("YF_CDP_PORT", "9225"))     # 与 shangxidq(9222)/312f(9223)/dzfwjd(9224) 错开
YF_PROFILE_DIR = os.path.join(USER_HOME, ".yf_chrome_profile")
ATTACH_ONLY = False                                        # 命令行 cdp：只附着，不自动启动
KEEP_BROWSER_OPEN = os.environ.get("YF_KEEP_BROWSER") == "1"
DISABLE_IMAGES = True

# 日常 Chrome 若靠扩展(SwitchyOmega 等)或固定端口翻墙，在此填写，例如 "http://127.0.0.1:7890"
YF_PROXY_DEFAULT = ""

def _detect_proxy():
    for k in ("YF_PROXY", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return YF_PROXY_DEFAULT

YF_PROXY = _detect_proxy()

PAGE_LOAD_TIMEOUT = 40
NAV_RETRIES = 3
RECOVERY_WAIT_INTERACTIVE = 600   # 有界面模式下等你手动处理的最长时间(秒)
RECOVERY_WAIT_AUTO = 90           # 无人值守/无头模式下的最长恢复等待
RECOVERY_POLL = 2
STALL_SECONDS = 3   # 空白页持续多久判定为卡住

# ================= 通用工具函数 =================

DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2})')

def week_start(d: date) -> date:
    """返回 d 所在周的周日（周日~周六为一周，周日属于其后的那个周一所在周）"""
    return d - timedelta(days=(d.weekday() + 1) % 7)

def week_index_of(d: date, today: date = None) -> int:
    """d 相对 today 所在周的周偏移：<0 已过期，0 本周(new)，1 下周(next)..."""
    today = today or RUN_TODAY
    return (week_start(d) - week_start(today)).days // 7

def extract_date(line: str, use_last: bool = True):
    found = DATE_RE.findall(line)
    if not found:
        return None
    try:
        return datetime.strptime(found[-1] if use_last else found[0], '%Y-%m-%d').date()
    except ValueError:
        return None

def read_clean_lines(path):
    """读取非空行（去除行尾空白）。surrogateescape 保证任意字节都能原样写回。"""
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8', errors='surrogateescape') as f:
        return [ln.rstrip() for ln in f if ln.strip()]

def file_has_dated_entries(path, use_last=True):
    return any(extract_date(ln, use_last) for ln in read_clean_lines(path))

def atomic_write_lines(path, lines):
    """原子写入：先写临时文件再替换，避免中途崩溃导致文件损坏"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', errors='surrogateescape') as f:
        if lines:
            f.write('\n'.join(lines) + '\n')
    os.replace(tmp, path)

def atomic_write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=4)
    os.replace(tmp, path)

def _file_needs_newline(path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, 'rb') as f:
            f.seek(-1, os.SEEK_END)
            return f.read(1) != b'\n'
    return False

def append_archive_lines(path, lines):
    """追加到汇总文件（沿用原格式：与前文以换行分隔，末行不加换行）"""
    if not lines:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    need_newline = _file_needs_newline(path)
    with open(path, 'a', encoding='utf-8', errors='surrogateescape') as f:
        f.write(('\n' if need_newline else '') + '\n'.join(lines))

AUTO = os.environ.get("PIPELINE_AUTO") == "1"

def show_alert(message):
    """跨平台弹窗提示（自动化流水线模式下只打印）"""
    if AUTO:
        print(f"[AUTO] {message}")
        return
    if platform.system() == 'Darwin':
        try:
            safe_msg = str(message).replace('\\', '\\\\').replace('"', '\\"')
            applescript_code = f'display dialog "{safe_msg}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        except Exception as e:
            print(f"弹窗提示失败: {e}")
    else:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("提示", message)
            root.destroy()
        except Exception as e:
            print(f"弹窗提示失败: {e}")

def mac_notify(title, message):
    """非阻塞系统通知（不会卡住脚本）"""
    if platform.system() != 'Darwin':
        return
    try:
        s = str(message).replace('\\', '\\\\').replace('"', '\\"')
        t = str(title).replace('\\', '\\\\').replace('"', '\\"')
        subprocess.run(['osascript', '-e', f'display notification "{s}" with title "{t}" sound name "Glass"'],
                       check=False, capture_output=True, timeout=5)
    except Exception:
        pass


# ================= Part A: 按日期自动对账/归档 =================

class PartA_Reconciler:
    """
    每次运行都根据"每行数据自身的日期"把数据放进正确的文件：
      - 早于本周      -> 汇总(归档)文件
      - 本周          -> *_new.txt
      - 下周          -> *_next.txt
      - +2/+3/+4 周   -> *_third / *_fourth / *_fifth
    幂等：无论哪天运行、运行几次、之前漏跑几次，结果都一致。
    """

    def __init__(self, today: date = None):
        self.today = today or RUN_TODAY
        self.snapshot_dir = None

    def _snapshot(self, paths):
        if self.snapshot_dir is None:
            self.snapshot_dir = os.path.join(
                BACKUP_ROOT_DIR, 'reconcile_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
            os.makedirs(self.snapshot_dir, exist_ok=True)
        for p in paths:
            if os.path.exists(p):
                dst = os.path.join(self.snapshot_dir, os.path.basename(p))
                if not os.path.exists(dst):
                    shutil.copy2(p, dst)

    def _reconcile(self, label, group_paths, archive_path, use_last_date,
                   key_fn, archive_line_fn, prefer_new_fn=None):
        n = len(group_paths)
        placed = [dict() for _ in range(n)]       # key -> (line, date)，保持插入顺序
        unparsed = [[] for _ in range(n)]
        archive_candidates = {}                    # key -> archive line
        moved, overflow = 0, 0

        for gi, (gname, path) in enumerate(group_paths):
            for ln in read_clean_lines(path):
                d = extract_date(ln, use_last_date)
                key = key_fn(ln, d) if d else None
                if key is None:
                    unparsed[gi].append(ln)
                    print(f"   [警告] {os.path.basename(path)} 中无法识别日期的行已原样保留: {ln}")
                    continue

                idx = week_index_of(d, self.today)
                if idx < 0:
                    archive_candidates.setdefault(key, archive_line_fn(ln, d))
                    continue
                if idx >= n:
                    overflow += 1
                    print(f"   [警告] {ln} 日期超出最远分组，暂放入 {group_paths[-1][0]}")
                    idx = n - 1
                if idx != gi:
                    moved += 1

                bucket = placed[idx]
                if key in bucket:
                    old_line = bucket[key][0]
                    if prefer_new_fn and prefer_new_fn(ln, old_line):
                        bucket[key] = (ln, d)
                else:
                    bucket[key] = (ln, d)

        new_contents = []
        for i in range(n):
            items = sorted(placed[i].values(), key=lambda x: x[1])
            new_contents.append(unparsed[i] + [ln for ln, _ in items])

        to_append = []
        if archive_path:
            existing_keys = set()
            for ln in read_clean_lines(archive_path):
                d = extract_date(ln, use_last_date)
                if d:
                    k = key_fn(ln, d)
                    if k is not None:
                        existing_keys.add(k)
            to_append = [line for k, line in archive_candidates.items() if k not in existing_keys]

        changed = bool(to_append) or any(
            new_contents[i] != read_clean_lines(p) for i, (_, p) in enumerate(group_paths))

        if not changed:
            print(f"[{label}] 已是正确状态，无需调整。")
            return

        all_paths = [p for _, p in group_paths] + ([archive_path] if archive_path else [])
        self._snapshot(all_paths)

        if to_append:
            append_archive_lines(archive_path, to_append)
        for i, (_, p) in enumerate(group_paths):
            if new_contents[i] or os.path.exists(p):
                atomic_write_lines(p, new_contents[i])

        print(f"[{label}] 调整完成：归档 {len(to_append)} 条（过期共 {len(archive_candidates)} 条），"
              f"跨文件移动 {moved} 条，超范围 {overflow} 条。")
        for i, (g, _) in enumerate(group_paths):
            print(f"      {g:<7}: {len(new_contents[i])} 行")

    @staticmethod
    def _earn_key(ln, d):
        if ':' not in ln:
            return None
        sym = ln.split(':', 1)[0].strip()
        return (sym, d) if sym else None

    @staticmethod
    def _earn_prefer_new(new_ln, old_ln):
        return 'N/A' in old_ln and 'N/A' not in new_ln

    def run(self):
        print("\n" + "=" * 50)
        print(">>> 正在启动 Part A (按日期自动对账/归档)")
        print(f"    基准日期: {self.today}  本周: {week_start(self.today)} ~ "
              f"{week_start(self.today) + timedelta(days=6)}")
        print("=" * 50)
        try:
            self._reconcile(
                "Earnings_Release",
                [(g, earnings_file(g)) for g in EARNINGS_GROUPS],
                EARNINGS_ARCHIVE_PATH,
                use_last_date=True,
                key_fn=self._earn_key,
                archive_line_fn=lambda ln, d: f"{ln.split(':', 1)[0].strip():<7}: {d.strftime('%Y-%m-%d')}",
                prefer_new_fn=self._earn_prefer_new,
            )
            self._reconcile(
                "Earnings_Release_diff",
                [(g, earnings_diff_file(g)) for g in EARNINGS_GROUPS],
                EARNINGS_DIFF_EXPIRED_PATH,
                use_last_date=True,
                key_fn=lambda ln, d: ln,
                archive_line_fn=lambda ln, d: ln,
            )
            self._reconcile(
                "Economic_Events",
                [(g, economic_file(g)) for g in ECONOMIC_GROUPS],
                ECONOMIC_ARCHIVE_PATH,
                use_last_date=False,
                key_fn=lambda ln, d: ln,
                archive_line_fn=lambda ln, d: ln,
            )
            if self.snapshot_dir:
                print(f"调整前的原始文件已备份至: {self.snapshot_dir}")
        except Exception as e:
            msg = f"Part A 对账出错（原文件已备份，未完成的部分下次运行会自动续做）: {e}"
            print(msg)
            show_alert(msg)
        print("Part A 执行结束.\n")


# ================= 浏览器管理（有界面 Chrome + CDP 附着 / 无头回退） =================

class SiteUnavailable(Exception):
    """网络/站点持续不可用（已重试且等待人工处理超时），上层应停止该站点的后续抓取"""


READY_STATES = ("rows", "empty")
BLOCK_STATES = ("neterror", "consent", "challenge", "ratelimit")
BLOCK_DESC = {
    "neterror": "网络连接失败（浏览器显示错误页）",
    "consent": "Yahoo 隐私 / Cookie 同意页",
    "challenge": "人机验证 / 访问被拒",
    "ratelimit": "Yahoo 限流（Too Many Requests）",
}
_SESSION_DEAD_MARKERS = (
    "invalid session id", "disconnected", "no such window", "target window already closed",
    "chrome not reachable", "session deleted", "not connected to devtools", "web view not found",
)

# 一次 JS 调用判断当前页面状态
PAGE_STATE_JS = r"""
try {
  if (location.protocol === 'chrome-error:') return 'neterror';
  const host = location.hostname || '';
  if (/(^|\.)(consent|guce)\.yahoo\.com$/i.test(host)) return 'consent';
  if (document.querySelector('table tbody > tr')) return 'rows';
  const body = document.body ? (document.body.innerText || '') : '';
  if (/We couldn.t find any results/i.test(body)) return 'empty';
  if (!body.trim()) return 'blank';          // 新增：空白页，即你描述的"卡住"状态
  const head = (document.title || '') + ' ' + body.slice(0, 2000);
  if (/captcha|are you a robot|unusual traffic|verify you are human|just a moment|access denied/i.test(head)) return 'challenge';
  if (/too many requests|will be right back|rate limit/i.test(head)) return 'ratelimit';
  return 'unknown';
} catch (e) { return 'unknown'; }
"""

CONSENT_CLICK_JS = r"""
const b = document.querySelector('button[name="reject"], button.reject-all, button[name="agree"], button.accept-all, button[value="agree"]');
if (b) { b.click(); return true; }
return false;
"""


def _local_opener():
    """访问 127.0.0.1 时绕过系统代理"""
    return build_opener(ProxyHandler({}))

def cdp_alive(port=None, timeout=1.0):
    port = port or CDP_PORT
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            pass
        with _local_opener().open(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as r:
            json.loads(r.read().decode("utf-8", "ignore"))
        return True
    except Exception:
        return False

def cdp_ensure_page(port=None):
    """调试 Chrome 没有任何标签页时(窗口被关)新建一个，否则 chromedriver 附着会失败"""
    port = port or CDP_PORT
    try:
        op = _local_opener()
        with op.open(f"http://127.0.0.1:{port}/json/list", timeout=2) as r:
            targets = json.loads(r.read().decode("utf-8", "ignore"))
        if any(t.get("type") == "page" for t in targets):
            return
        op.open(Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT"), timeout=3).close()
    except Exception:
        pass

def _chrome_proxy_arg(p):
    p = p.strip().rstrip("/")
    return p.replace("socks5h://", "socks5://")

def _make_service():
    if os.path.exists(CHROME_DRIVER_PATH):
        return Service(executable_path=CHROME_DRIVER_PATH)
    tqdm.write(f"[浏览器] 未找到驱动 {CHROME_DRIVER_PATH}，改用 Selenium Manager 自动匹配（需 Selenium ≥ 4.6）")
    return Service()

def launch_cdp_chrome(url="about:blank"):
    """启动带调试端口的有界面 Chrome。返回 (端口是否可用, 本次启动的进程或 None)"""
    if cdp_alive():
        return True, None
    if not os.path.exists(CHROME_BINARY_PATH):
        tqdm.write(f"[浏览器] 未找到 Chrome: {CHROME_BINARY_PATH}")
        return False, None
    os.makedirs(YF_PROFILE_DIR, exist_ok=True)
    args = [
        CHROME_BINARY_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={YF_PROFILE_DIR}",      # Chrome 136+ 要求调试端口必须配独立 profile
        "--no-first-run", "--no-default-browser-check",
        "--disable-session-crashed-bubble", "--hide-crash-restore-bubble",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--window-size=1280,900",
    ]
    if DISABLE_IMAGES:
        args.append("--blink-settings=imagesEnabled=false")
    if YF_PROXY:
        args.append(f"--proxy-server={_chrome_proxy_arg(YF_PROXY)}")
        tqdm.write(f"[浏览器] 使用代理: {YF_PROXY}")
    args.append(url)
    try:
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=(os.name != "nt"))
    except Exception as e:
        tqdm.write(f"[浏览器] 启动 Chrome 失败: {e}")
        return False, None
    for _ in range(60):
        time.sleep(0.5)
        if cdp_alive():
            return True, (proc if proc.poll() is None else None)
        if proc.poll() is not None and not cdp_alive():
            time.sleep(1)
            if not cdp_alive():
                break
    tqdm.write(f"[浏览器] 等待调试端口 {CDP_PORT} 超时（profile 可能被另一个 Chrome 占用）")
    try:
        proc.terminate()
    except Exception:
        pass
    return False, None

def create_headless_driver():
    """无头模式（回退用）。不再伪造过时 UA，只把 HeadlessChrome 替换为 Chrome，保证与真实版本一致。"""
    options = Options()
    if os.path.exists(CHROME_BINARY_PATH):
        options.binary_location = CHROME_BINARY_PATH
    else:
        tqdm.write(f"警告：未找到 Chrome 路径 {CHROME_BINARY_PATH}，使用系统默认。")
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    if platform.system() == "Linux":
        options.add_argument("--no-sandbox")
    if DISABLE_IMAGES:
        options.add_argument("--blink-settings=imagesEnabled=false")
    if YF_PROXY:
        options.add_argument(f"--proxy-server={_chrome_proxy_arg(YF_PROXY)}")
    options.page_load_strategy = 'eager'

    driver = webdriver.Chrome(service=_make_service(), options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    try:
        ua = (driver.execute_script("return navigator.userAgent") or "").replace("HeadlessChrome", "Chrome")
        if ua:
            driver.execute_cdp_cmd("Emulation.setUserAgentOverride",
                                   {"userAgent": ua, "acceptLanguage": "en-US,en;q=0.9"})
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception:
        pass
    return driver


class BrowserManager:
    """
    整个运行只用一个浏览器：
      - 默认启动(或附着)一个正常的有界面 Chrome，Selenium 通过 debuggerAddress 附着；
      - load() 负责：导航 + 网络错误重试 + 识别同意页/验证/限流 + 通知你手动处理 + 恢复后自动继续；
      - 持续不可用时抛 SiteUnavailable，上层立刻停止，不做无意义的重试。
    """

    def __init__(self):
        self.driver = None
        self.proc = None
        self.own_tab = None
        self.mode = BROWSER_MODE
        self.interactive = False
        self._start_error = None
        self._preflight_ok = False
        self._preflight_error = None

    # ---------- 启动 ----------
    def start(self, preflight=True):
        if self._start_error is not None:
            raise SiteUnavailable(f"浏览器不可用: {self._start_error}")
        if self.driver is None:
            try:
                self._create()
            except Exception as e:
                self._start_error = e
                raise SiteUnavailable(f"无法启动浏览器: {e}") from e
        if preflight:
            if self._preflight_error is not None:
                raise self._preflight_error
            if not self._preflight_ok:
                try:
                    self._preflight()
                except SiteUnavailable as e:
                    self._preflight_error = e
                    raise
        return self.driver

    def _ensure_driver(self):
        if self.driver is None:
            self.start(preflight=False)

    def _create(self):
        if self.mode == "cdp":
            try:
                self.driver = self._create_cdp()
                self.interactive = True
                return
            except Exception as e:
                if ATTACH_ONLY:
                    raise
                tqdm.write(f"[浏览器] 有界面模式启动失败({e})，回退到无头模式")
                self.mode = "headless"
        tqdm.write("[浏览器] 启动无头 Chrome ...")
        self.driver = create_headless_driver()
        self.interactive = False

    def _create_cdp(self):
        launched_now = False
        if not cdp_alive():
            if ATTACH_ONLY:
                raise RuntimeError(f"端口 {CDP_PORT} 没有调试 Chrome，请先执行: python {SCRIPT_NAME} open")
            tqdm.write("[浏览器] 启动独立的有界面 Chrome（独立 profile，不影响你日常使用的 Chrome）...")
            ok, proc = launch_cdp_chrome()
            if not ok:
                raise RuntimeError("调试端口未就绪")
            self.proc = proc
            launched_now = proc is not None
        else:
            tqdm.write(f"[浏览器] 检测到端口 {CDP_PORT} 上已有调试 Chrome，直接附着（结束时不会关闭它）")
        cdp_ensure_page()

        options = Options()
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{CDP_PORT}")
        options.page_load_strategy = "eager"
        driver = webdriver.Chrome(service=_make_service(), options=options)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        if not launched_now and self.proc is None:
            try:
                driver.switch_to.new_window("tab")   # 在别人的窗口里另开一个标签页干活
                self.own_tab = driver.current_window_handle
            except Exception:
                self.own_tab = None
        try:
            ua = driver.execute_script("return navigator.userAgent")
            tqdm.write(f"[浏览器] 已附着。UA: {ua}")
        except Exception:
            pass
        return driver

    def _rebuild(self):
        try:
            self.driver.quit()
        except Exception:
            pass
        self.driver = None
        self._create()

    def _preflight(self):
        tqdm.write(f"[预检] 打开 {YAHOO_PROBE_URL} 检查连通性 ...")
        st = self.load(YAHOO_PROBE_URL, timeout=15)
        if st in READY_STATES:
            tqdm.write("[预检] ✅ Yahoo Finance 可正常访问")
        else:
            tqdm.write("[预检] ⚠️ 页面已打开但未识别到日历表格（可能页面结构有变化），继续尝试抓取")
        self._preflight_ok = True

    # ---------- 导航 ----------
    def _navigate(self, url):
        """成功返回 None；网络错误返回 'ERR_XXX'"""
        for _ in range(2):
            try:
                self.driver.get(url)
                return None
            except TimeoutException:
                try:
                    self.driver.execute_script("window.stop();")
                except Exception:
                    pass
                return None
            except WebDriverException as e:
                msg = str(e)
                m = re.search(r"net::(ERR_[A-Z0-9_]+)", msg)
                if m:
                    return m.group(1)
                if any(k in msg.lower() for k in _SESSION_DEAD_MARKERS):
                    tqdm.write("[浏览器] 会话已断开（浏览器或标签页被关闭？），正在重建 ...")
                    self._rebuild()
                    continue
                raise
        return "SESSION_LOST"

    def _page_state(self):
        try:
            return self.driver.execute_script(PAGE_STATE_JS) or "unknown"
        except Exception:
            return "blank"   # 渲染进程无响应时 JS 执行失败，按卡住处理

    def _nudge(self, url):
        """等同于在地址栏按回车：对同一 URL 重新导航（不等待加载完成）"""
        try:
            self.driver.execute_cdp_cmd("Page.navigate", {"url": url})
        except Exception:
            self.driver.get(url)

    def _replace_tab(self, url):
        """新开一个标签页加载 URL，并关闭卡住的旧标签页（仅 cdp 模式可用）"""
        op = _local_opener()
        old = self.driver.current_window_handle
        req = Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{quote(url, safe='')}", method="PUT")
        with op.open(req, timeout=5) as r:
            new_id = json.loads(r.read().decode("utf-8", "ignore"))["id"]
        time.sleep(1.5)
        self.driver.switch_to.window(new_id)     # 在 ChromeDriver 中，window handle 即 CDP target id
        try:
            op.open(f"http://127.0.0.1:{CDP_PORT}/json/close/{old}", timeout=5).close()
        except Exception:
            pass
        if self.own_tab == old:
            self.own_tab = new_id

    def _wait_state(self, timeout, url=None):
        timeout = max(timeout, 25)           # 给卡住检测留出时间
        start = time.time()
        blank_since, stalls = None, 0
        while time.time() - start < timeout:
            st = self._page_state()
            if st in READY_STATES or st in BLOCK_STATES:
                return st
            if st == "blank" and url:
                blank_since = blank_since or time.time()
                if time.time() - blank_since >= self.STALL_SECONDS:
                    stalls += 1
                    blank_since = time.time()
                    try:
                        if stalls <= 2:
                            tqdm.write(f"    [卡住] 页面空白超过 {self.STALL_SECONDS}s，自动重新加载（等同于地址栏回车）")
                            self._nudge(url)
                        else:
                            tqdm.write("    [卡住] 重新加载无效，改为新开标签页加载")
                            self._replace_tab(url)
                            stalls = 0
                    except Exception as e:
                        tqdm.write(f"    [卡住] 自动处理失败: {e}")
            else:
                blank_since = None
            time.sleep(0.5)
        return None

    def open_url(self, url):
        """普通导航（非 Yahoo 页面用），只做网络重试"""
        self._ensure_driver()
        err = None
        for attempt in range(1, NAV_RETRIES + 1):
            err = self._navigate(url)
            if not err:
                return
            tqdm.write(f"    [网络] {err}（第 {attempt}/{NAV_RETRIES} 次）: {url}")
            time.sleep(2 * attempt)
        raise SiteUnavailable(f"{err}: {url}")

    def load(self, url, timeout=10):
        """
        打开 Yahoo 日历页并等待就绪。返回 'rows' / 'empty' / 'unknown' / None(超时)。
        被拦或网络异常时进入恢复流程；恢复失败抛 SiteUnavailable。
        """
        self._ensure_driver()
        for _ in range(3):
            err = None
            for attempt in range(1, NAV_RETRIES + 1):
                err = self._navigate(url)
                if not err:
                    break
                tqdm.write(f"    [网络] {err}（第 {attempt}/{NAV_RETRIES} 次）: {url}")
                if attempt < NAV_RETRIES:
                    time.sleep(2 * attempt)
            state = "neterror" if err else self._wait_state(timeout, url)
            if state not in BLOCK_STATES:
                return state
            if not self.wait_for_recovery(url, state, err):
                raise SiteUnavailable(f"{BLOCK_DESC[state]}{f'（{err}）' if err else ''}，等待恢复超时: {url}")
        raise SiteUnavailable(f"多次恢复后仍被拦截: {url}")

    # ---------- 被拦 / 网络异常时的人工介入 ----------
    def _bring_to_front(self):
        try:
            self.driver.execute_cdp_cmd("Page.bringToFront", {})
        except Exception:
            pass
        if platform.system() == "Darwin" and self.proc is not None and self.proc.poll() is None:
            try:
                script = (f'tell application "System Events" to set frontmost of '
                          f'(first process whose unix id is {self.proc.pid}) to true')
                subprocess.run(["osascript", "-e", script], check=False, capture_output=True, timeout=5)
            except Exception:
                pass

    def _try_click_consent(self):
        try:
            return bool(self.driver.execute_script(CONSENT_CLICK_JS))
        except Exception:
            return False

    def _notify_user(self, url, state, desc, max_wait):
        tqdm.write("\a\n" + "=" * 72)
        tqdm.write(f"  ⚠️  {desc}")
        tqdm.write(f"      URL: {url}")
        if self.interactive and not AUTO:
            tqdm.write("  👉  请切到弹出的 Chrome 窗口处理：")
            tqdm.write("      · 同意页：点 Accept / Reject 均可（脚本也会自动尝试点击）")
            tqdm.write("      · 人机验证：手动完成验证")
            tqdm.write("      · 网络错误：检查代理/VPN 后，在窗口里刷新页面，确认能看到日历表格")
            tqdm.write(f"  ⏳  脚本每 {RECOVERY_POLL}s 自动检测，恢复后自动继续（最长等 {max_wait}s）")
        else:
            tqdm.write(f"  ⏳  无人值守/无头模式：自动重试，最长 {max_wait}s")
        if state == "neterror":
            tqdm.write("  💡  排查：")
            tqdm.write(f"      · 当前传给 Chrome 的代理 YF_PROXY = {YF_PROXY or '未设置（跟随系统代理）'}")
            tqdm.write(f"      · 系统代理: {getproxies() or '无'}")
            tqdm.write("      · 日常 Chrome 若靠扩展翻墙，请设置 YF_PROXY=http://127.0.0.1:端口，")
            tqdm.write(f"        或执行 python {SCRIPT_NAME} open 在专用窗口里装好代理扩展（会保留）")
            tqdm.write(f"      · 更多诊断：python {SCRIPT_NAME} diag")
        tqdm.write("=" * 72 + "\n")
        mac_notify("YF 爬虫需要你处理", desc)
        self._bring_to_front()

    def wait_for_recovery(self, url, state, err=None):
        if not self.interactive and state == "challenge":
            tqdm.write("    ✗ 无头模式无法人工完成验证，请改用默认有界面模式运行")
            return False
        desc = BLOCK_DESC.get(state, state) + (f"（{err}）" if err else "")
        max_wait = RECOVERY_WAIT_INTERACTIVE if (self.interactive and not AUTO) else RECOVERY_WAIT_AUTO
        self._notify_user(url, state, desc, max_wait)

        start = last_nav = last_tip = time.time()
        consent_at = 0.0
        reload_every = 60 if state == "ratelimit" else 15
        while time.time() - start < max_wait:
            time.sleep(RECOVERY_POLL)
            st = self._page_state()
            if st in READY_STATES:
                tqdm.write("    ✅ 已恢复，继续抓取\n")
                time.sleep(1)
                return True
            if st == "consent":
                if time.time() - consent_at > 10:
                    consent_at = time.time()
                    if self._try_click_consent():
                        tqdm.write("    [自动] 已尝试点击同意页按钮")
            elif st != "challenge" and time.time() - last_nav >= reload_every:
                # 网络错误/限流/未知页面：定期自动重载；验证页不重载，以免打断你操作
                last_nav = time.time()
                try:
                    if not self._navigate(url) and self._wait_state(10) in READY_STATES:
                        tqdm.write("    ✅ 已恢复，继续抓取\n")
                        return True
                except Exception:
                    pass
            if time.time() - last_tip >= 30:
                last_tip = time.time()
                tqdm.write(f"    ... 仍在等待恢复（当前页面状态: {st}，剩余 {int(max_wait - (time.time() - start))}s）")
        tqdm.write("    ✗ 等待恢复超时")
        return False

    # ---------- 关闭 ----------
    def close(self):
        d, self.driver = self.driver, None
        launched = self.proc is not None and self.proc.poll() is None
        if d is not None:
            if self.own_tab and not launched:
                try:
                    handles = d.window_handles
                    if self.own_tab in handles and len(handles) > 1:
                        d.switch_to.window(self.own_tab)
                        d.close()
                except Exception:
                    pass
            try:
                d.quit()     # 附着模式下 quit 只断开 chromedriver，不会关掉浏览器
            except Exception:
                pass
        if launched:
            if KEEP_BROWSER_OPEN:
                tqdm.write("[浏览器] 按设置保留 Chrome 窗口（下次运行会自动附着复用）")
            else:
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=10)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
                tqdm.write("[浏览器] 已关闭本次启动的 Chrome")
        self.proc = None
        self.own_tab = None


def move_mouse_periodically():
    """后台周期性移动鼠标，防止系统休眠（当前未启用）。"""
    import pyautogui  # 延迟导入：无图形界面环境下不影响主程序
    while True:
        try:
            screen_width, screen_height = pyautogui.size()
            x = random.randint(100, screen_width - 100)
            y = random.randint(100, screen_height - 100)
            pyautogui.moveTo(x, y, duration=1)
            time.sleep(random.randint(30, 60))
        except Exception:
            time.sleep(30)


# ================= Part B: Selenium 爬虫 =================

# --- B.1: Economic Events Task ---

ECON_ROWS_JS = r"""
const box = document.querySelector('div.table-container') || document;
const clean = el => el ? ((el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim()) : '';
const out = [];
box.querySelectorAll('tr').forEach(tr => {
  if (tr.getAttribute('role') === 'columnheader') return;
  const tds = tr.querySelectorAll('td');
  if (tds.length < 2) return;
  out.push([clean(tds[0]), clean(tds[1])]);
});
return out;
"""

def update_sectors_panel():
    """根据 Economic_Events new/next 文件刷新 sectors_panel 的 Economics 分组"""
    event_files = [(tag, economic_file(tag)) for tag in ('new', 'next') if os.path.exists(economic_file(tag))]

    if not event_files:
        tqdm.write("未找到 Economic_Events 文件，未执行更新。")
        show_alert("未找到 Economic_Events 文件，未执行更新。")
        return

    try:
        with open(SYMBOL_MAPPING_JSON_PATH, 'r', encoding='utf-8') as f:
            symbol_mapping = json.load(f)
        with open(SECTORS_PANEL_JSON_PATH, 'r', encoding='utf-8') as f:
            sectors_panel = json.load(f)

        sectors_panel['Economics'] = {}

        for tag, filepath in event_files:
            for event in read_clean_lines(filepath):
                event = event.strip()
                if ' : ' not in event:
                    tqdm.write(f"Warning: 跳过格式不对的行：{event}")
                    continue
                date_part, desc_part = event.split(' : ', 1)
                day_field = date_part.split('-')[-1].strip()
                description = desc_part.split(' [')[0].strip()
                if description not in symbol_mapping:
                    continue
                economics_key = symbol_mapping[description]
                combined_value = f"{day_field} {economics_key}"
                existing = sectors_panel['Economics'].get(economics_key)
                if existing is None:
                    sectors_panel['Economics'][economics_key] = combined_value
                elif existing != combined_value and tag == 'next':
                    sectors_panel['Economics'][economics_key] = combined_value

        atomic_write_json(SECTORS_PANEL_JSON_PATH, sectors_panel)
        tqdm.write("Economic Events JSON 更新已完成！")
    except Exception as e:
        error_message = f"更新 Economic Events JSON 错误: {e}"
        tqdm.write(error_message)
        show_alert(error_message)

def crawl_economic_week(bm, week_idx, file_path):
    """抓取相对本周偏移 week_idx 的那一周（周日~周六）的经济事件，追加到 file_path"""
    start_date = week_start(RUN_TODAY) + timedelta(weeks=week_idx)
    end_date = start_date + timedelta(days=6)
    tqdm.write(f"抓取经济事件: {start_date} ~ {end_date} -> {os.path.basename(file_path)}")

    if os.path.exists(file_path):
        timestamp = datetime.now().strftime('%y%m%d')
        os.makedirs(BACKUP_ROOT_DIR, exist_ok=True)
        base = os.path.splitext(os.path.basename(file_path))[0]
        shutil.copy2(file_path, os.path.join(BACKUP_ROOT_DIR, f'{base}_{timestamp}.txt'))
    existing_content = set(read_clean_lines(file_path))

    target_countries = {"US"}
    date_list = [start_date + timedelta(days=i) for i in range(7)]
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    MAX_OFFSET = 2000  # 防死循环保险
    added = 0

    need_nl = _file_needs_newline(file_path)
    with open(file_path, 'a', encoding='utf-8', errors='surrogateescape') as output_file:
        if need_nl:
            output_file.write("\n")
        pbar = tqdm(date_list, desc="Eco Events", unit="day")
        try:
            for change_date in pbar:
                formatted_change_date = change_date.strftime('%Y-%m-%d')
                pbar.set_description(f"正在抓取: {formatted_change_date}")
                offset = 0
                last_signature = None
                while offset <= MAX_OFFSET:
                    pbar.set_postfix(offset=offset)
                    url = (f"https://finance.yahoo.com/calendar/economic?from={start_date.strftime('%Y-%m-%d')}"
                           f"&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100")
                    state = bm.load(url, timeout=10)
                    data_rows = []
                    if state == "rows":
                        try:
                            data_rows = [tuple(x) for x in (bm.driver.execute_script(ECON_ROWS_JS) or [])]
                        except Exception:
                            data_rows = []
                    if not data_rows:
                        break
                    signature = tuple(data_rows)
                    if signature == last_signature:  # 翻页后内容相同，说明已到末尾
                        break
                    last_signature = signature

                    for event, country in data_rows:
                        if event and country and country in target_countries:
                            matched = next((b for b in EVENT_FILTER_ORDERED if event.startswith(b)), None)
                            if matched:
                                entry = f"{formatted_change_date} : {matched} [{country}]"
                                if entry not in existing_content:
                                    output_file.write(entry + "\n")
                                    output_file.flush()
                                    existing_content.add(entry)
                                    added += 1
                    offset += 100
        finally:
            pbar.close()
    tqdm.write(f"经济事件新增 {added} 条 -> {os.path.basename(file_path)}")

def run_economic_events_task(bm):
    tqdm.write("\n" + "=" * 50)
    tqdm.write(">>> 开始执行任务: Economic Events")
    tqdm.write("=" * 50)

    today_weekday = RUN_TODAY.weekday()
    weeks_to_crawl = []
    if not file_has_dated_entries(economic_file('new'), use_last=False):
        tqdm.write("检测到 Economic_Events_new 为空，将补抓本周数据。")
        weeks_to_crawl.append((0, economic_file('new')))
    if today_weekday in (4, 5):
        weeks_to_crawl.append((1, economic_file('next')))

    if weeks_to_crawl:
        try:
            bm.start()
            for week_idx, path in weeks_to_crawl:
                crawl_economic_week(bm, week_idx, path)
        except SiteUnavailable as e:
            tqdm.write(f"Economic Events 跳过/中断：{e}")
        except Exception as e:
            tqdm.write(f"Economic Events 爬虫出错: {e}")
    else:
        tqdm.write("今天无需抓取 Economic Events（仅周五/周六抓取下周，或本周缺数据时补抓）。")

    update_sectors_panel()

# --- B.2: Stock Splits Task ---

SPLITS_ROWS_JS = r"""
const trs = document.querySelectorAll('table tbody > tr');
const clean = el => el ? ((el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim()) : '';
const out = [];
trs.forEach(tr => {
  const a = tr.querySelector('a.loud-link.fin-size-small') || tr.querySelector('a[href*="/quote/"]');
  if (!a) return;
  const sym = (clean(a) || a.getAttribute('title') || '').trim();
  const c = tr.querySelector('td[data-testid-cell="companyshortname"]') ||
            tr.querySelector('td.tw-text-left.tw-max-w-xs.tw-whitespace-normal');
  if (!sym || !c) return;
  out.push([sym, clean(c)]);
});
return {rows: out, total: trs.length};
"""

def run_stock_splits_task(bm):
    tqdm.write("\n" + "=" * 50)
    tqdm.write(">>> 开始执行任务: Stock Splits")
    tqdm.write("=" * 50)

    if RUN_TODAY.weekday() not in (4, 5):
        tqdm.write("今天不是周五或周六，跳过 Stock Splits 任务。")
        return

    file_path = os.path.join(NEWS_DIR, 'Stock_Splits_next.txt')
    if os.path.exists(file_path):
        timestamp = datetime.now().strftime('%y%m%d')
        backup_path = os.path.join(BACKUP_ROOT_DIR, f'Stock_Splits_next_{timestamp}.txt')
        os.makedirs(BACKUP_ROOT_DIR, exist_ok=True)
        shutil.copy2(file_path, backup_path)
        tqdm.write(f"已备份原文件至: {backup_path}")

    old_lines = read_clean_lines(file_path)
    existing_content = set(old_lines)

    try:
        with open(SECTORS_ALL_JSON_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except Exception as e:
        tqdm.write(f"读取 {SECTORS_ALL_JSON_PATH} 失败，跳过 Stock Splits: {e}")
        return
    tracked = set()
    for v in data.values():
        tracked.update(v)

    start_date = week_start(RUN_TODAY) + timedelta(weeks=1)
    end_date = start_date + timedelta(days=6)
    tqdm.write(f"抓取日期范围: {start_date} 至 {end_date}")

    results = []
    try:
        bm.start()
        date_list = [start_date + timedelta(days=i) for i in range(7)]
        pbar = tqdm(date_list, desc="Stock Splits", unit="day")
        try:
            for change_date in pbar:
                ds = change_date.strftime('%Y-%m-%d')
                pbar.set_description(f"正在处理: {ds}")
                offset, last_sig = 0, None
                while offset <= 2000:
                    pbar.set_postfix(offset=offset, found=len(results))
                    url = (f"https://finance.yahoo.com/calendar/splits?from={start_date.strftime('%Y-%m-%d')}"
                           f"&to={end_date.strftime('%Y-%m-%d')}&day={ds}&offset={offset}&size=100")
                    if bm.load(url, timeout=10) != "rows":
                        break
                    payload = bm.driver.execute_script(SPLITS_ROWS_JS) or {}
                    rows, total = payload.get("rows") or [], payload.get("total") or 0
                    if not total:
                        break
                    sig = tuple(tuple(r) for r in rows)
                    if sig == last_sig:
                        break
                    last_sig = sig
                    for symbol, company in rows:
                        if symbol in tracked:
                            entry = f"{symbol}: {ds} - {company}"
                            if entry not in existing_content:
                                results.append(entry)
                                existing_content.add(entry)
                                tqdm.write(f"   [+] 发现新数据: {entry}")
                    if total < 100:
                        break
                    offset += 100
        finally:
            pbar.close()
    except SiteUnavailable as e:
        tqdm.write(f"Stock Splits 跳过/中断：{e}")
    except Exception as e:
        tqdm.write(f"Stock Splits 任务执行出错: {e}")
    finally:
        if results:
            atomic_write_lines(file_path, old_lines + results)
            tqdm.write(f"成功写入 {len(results)} 条新数据。")
        else:
            tqdm.write("没有新内容添加，文件保持不变。")

# --- B.3: Earnings Release Task ---

def compute_group_date_range(group_name: str):
    """
    根据 RUN_TODAY 计算各分组的抓取范围（周一至周六），与 Part A 的周归属规则一致：
      new=本周, next=+1周, third=+2周, fourth=+3周, fifth=+4周
    """
    idx = EARNINGS_GROUPS.index(group_name) if group_name in EARNINGS_GROUPS else 1
    ws = week_start(RUN_TODAY) + timedelta(weeks=idx)
    return ws + timedelta(days=1), ws + timedelta(days=6)

NA = "N/A"
_EMPTY_CALL_VALUES = {"", "-", "--", "—", "–"}

def normalize_call_time(raw):
    """把空白/占位符统一成 N/A；BMO/AMC/TNS/TAS 或具体时间原样保留。"""
    s = (raw or "").strip()
    return NA if s in _EMPTY_CALL_VALUES else s

# 一次性在浏览器内提取整张表（textContent 不受可见性影响；按 data-testid-cell 取列，取不到回退下标）
EXTRACT_ROWS_JS = r"""
const trs = document.querySelectorAll('table tbody > tr');
const out = [];
const clean = el => el ? (el.textContent || '').replace(/\s+/g, ' ').trim() : '';
trs.forEach(tr => {
  const a = tr.querySelector('a[title][href*="/quote/"]');
  if (!a) return;
  const tds = tr.querySelectorAll('td');
  const byName = name => tr.querySelector('td[data-testid-cell="' + name + '"]');
  const evCell = byName('eventname') || tds[2] || null;
  const callCell = byName('startdatetimetype') || tds[3] || null;
  out.push({
    symbol: (a.getAttribute('title') || clean(a)).trim(),
    event: clean(evCell),
    call: clean(callCell),
    html: callCell ? callCell.outerHTML.slice(0, 200) : '(no call cell)'
  });
});
return {rows: out, total: trs.length};
"""

def _blank_count(rows):
    return sum(1 for r in rows if normalize_call_time(r['call']) == NA)

def _merge_rows(old_rows, new_rows):
    """按 (symbol, event) 合并两次读取的结果：同一行优先保留非空的盘前盘后字段。"""
    merged = {}
    for r in list(old_rows) + list(new_rows):
        k = (r['symbol'], r['event'])
        cur = merged.get(k)
        if cur is None or (normalize_call_time(cur['call']) == NA
                           and normalize_call_time(r['call']) != NA):
            merged[k] = r
    return list(merged.values())

def fetch_earnings_page(bm, url, blank_retries=2, retry_wait=1.5):
    """
    加载并解析一页。若有行的 Earnings Call Time 为空，短暂等待后重读，最多 blank_retries 次。
    返回 (state, rows, total_tr_count)。网络/验证问题由 bm.load 处理。
    """
    state = bm.load(url, timeout=10)
    if state is None:
        raise TimeoutException(f"页面未就绪: {url}")
    if state == 'empty':
        return 'end', [], 0

    payload = bm.driver.execute_script(EXTRACT_ROWS_JS) or {"rows": [], "total": 0}
    rows, total = payload['rows'], payload['total']

    for _ in range(blank_retries):
        before = _blank_count(rows)
        if before == 0:
            break
        time.sleep(retry_wait)
        payload2 = bm.driver.execute_script(EXTRACT_ROWS_JS) or {"rows": [], "total": 0}
        rows = _merge_rows(rows, payload2['rows'])
        total = max(total, payload2['total'])
        if _blank_count(rows) >= before:  # 无改善：多半是 Yahoo 本身就没有数据
            break
    return 'rows', rows, total

def file_has_unknown_call_time(path):
    """文件中是否存在盘前盘后为 N/A 的行（格式: SYM : CALL : DATE）"""
    for ln in read_clean_lines(path):
        parts = ln.split(':')
        if len(parts) >= 3 and parts[1].strip() == NA:
            return True
    return False

def run_single_scraper_task(bm, sectors_data, task_config):
    group_name = task_config["group_name"]
    file_path = task_config["file_path"]
    diff_path = task_config["diff_path"]
    backup_dir = task_config["backup_dir"]
    earnings_release_path = task_config["earnings_release_path"]

    tqdm.write(f">> 正在初始化任务: {group_name.upper()}")

    last_sd, last_ed = compute_group_date_range(group_name)
    start_date = datetime(last_sd.year, last_sd.month, last_sd.day)
    end_date = datetime(last_ed.year, last_ed.month, last_ed.day)
    tqdm.write(f"   日期范围: {start_date.date()} -> {end_date.date()}")

    sector_symbols = set()
    for lst in sectors_data.values():
        sector_symbols.update(lst)

    existing_release_entries = set()
    for line in read_clean_lines(earnings_release_path):
        parts = line.split(':')
        if len(parts) >= 2:
            existing_release_entries.add((parts[0].strip(), parts[-1].strip()))

    recent_backup_symbols = set()
    for s, d in existing_release_entries:
        try:
            dt = datetime.strptime(d, '%Y-%m-%d').date()
            if 0 <= (RUN_TODAY - dt).days <= 30:
                recent_backup_symbols.add(s)
        except ValueError:
            continue

    if os.path.exists(file_path):
        ts = datetime.now().strftime('%y%m%d')
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(file_path, os.path.join(backup_dir, f'Earnings_Release_{group_name}_{ts}.txt'))

    existing_lines = read_clean_lines(file_path)
    existing_map = {}
    for ln in existing_lines:
        parts = ln.split(':')
        if len(parts) >= 3:
            existing_map[parts[0].strip()] = (parts[1].strip(), parts[-1].strip())

    new_entries_map = {}
    blank_samples = []
    date_list = [start_date + i * timedelta(days=1) for i in range((end_date - start_date).days + 1)]
    date_pbar = tqdm(date_list, desc=f"   [{group_name}] 日期进度", position=1, leave=False)
    aborted = None

    try:
        for single_date in date_pbar:
            ds = single_date.strftime('%Y-%m-%d')
            offset = 0
            last_sig = None
            date_pbar.set_description(f"   [{group_name}] {ds}")

            while True:
                date_pbar.set_postfix(offset=offset, new=len(new_entries_map))
                url = f"https://finance.yahoo.com/calendar/earnings?day={ds}&offset={offset}&size=100"
                rows, total = [], 0
                found_end = False
                page_load_success = False
                last_err = None

                for attempt in range(3):
                    try:
                        state, rows, total = fetch_earnings_page(bm, url)
                        if state == 'end':
                            found_end = True
                            page_load_success = True
                            break
                        if rows:
                            page_load_success = True
                            break
                    except SiteUnavailable:
                        raise
                    except Exception as e:
                        last_err = e
                    time.sleep(random.uniform(2, 4))

                if found_end:
                    break
                if not page_load_success:
                    tqdm.write(f"    [{ds}] Offset {offset} 加载失败，跳过。"
                               + (f"（{str(last_err).splitlines()[0][:120]}）" if last_err else ""))
                    break
                if not rows:
                    break

                sig = tuple((r['symbol'], r['event']) for r in rows)
                if sig == last_sig:
                    break
                last_sig = sig

                for r in rows:
                    symbol = r['symbol'].strip()
                    if not symbol:
                        continue
                    if group_name == "fifth" and symbol in EXCLUDE_FROM_FIFTH:
                        continue
                    event_name = r['event']
                    call_time = normalize_call_time(r['call'])
                    if not any(k in event_name for k in ["Earnings Release", "Shareholders Meeting", "Earnings Announcement"]):
                        continue
                    if (symbol, ds) in existing_release_entries:
                        continue
                    if symbol not in sector_symbols:
                        continue
                    if call_time == NA and len(blank_samples) < 3:
                        blank_samples.append(f"{symbol} @ {ds}: {r.get('html', '')}")
                    if symbol in existing_map:
                        old_ct, old_dt = existing_map[symbol]
                        if old_dt == ds and old_ct == call_time:
                            continue
                        if old_dt == ds and call_time == NA and old_ct != NA:
                            continue
                    existing_map[symbol] = (call_time, ds)
                    new_entries_map[(symbol, ds)] = f"{symbol:<7}: {call_time:<4}: {ds}"

                offset += total or len(rows)
    except SiteUnavailable as e:
        aborted = e
        tqdm.write(f"   [中断] {group_name.upper()}: {e}（已抓到的数据照常保存）")
    finally:
        date_pbar.close()

    new_entries = list(new_entries_map.values())

    if blank_samples:
        tqdm.write("   [诊断] 重试后仍无盘前盘后时间的样例（若页面实际有值，请把此处 HTML 发我）:")
        for s in blank_samples:
            tqdm.write(f"        {s}")

    symbols_to_avoid = set()
    for f_path in task_config["duplicate_check_files"]:
        for line in read_clean_lines(f_path):
            parts = line.split(':')
            if parts and parts[0].strip():
                symbols_to_avoid.add(parts[0].strip())

    existing_diff_lines = set(read_clean_lines(diff_path))
    entries_for_target, entries_for_diff = [], []

    for ln in new_entries:
        sym = ln.split(':')[0].strip()
        if sym in symbols_to_avoid:
            if ln not in existing_diff_lines:
                entries_for_diff.append(ln)
                existing_diff_lines.add(ln)
        elif sym in recent_backup_symbols:
            marked = f"{ln} #BACKUP_DUP"
            if marked not in existing_diff_lines:
                entries_for_diff.append(marked)
                existing_diff_lines.add(marked)
        else:
            entries_for_target.append(ln)

    replaced_syms = {ln.split(':')[0].strip() for ln in entries_for_target}
    kept_lines = [ln for ln in existing_lines if ln.split(':')[0].strip() not in replaced_syms]
    atomic_write_lines(file_path, kept_lines + entries_for_target)

    if entries_for_diff:
        os.makedirs(os.path.dirname(diff_path), exist_ok=True)
        need_nl = _file_needs_newline(diff_path)
        with open(diff_path, 'a', encoding='utf-8', errors='surrogateescape') as f:
            if need_nl:
                f.write('\n')
            for ln in entries_for_diff:
                f.write(ln + '\n')

    if not entries_for_target and not entries_for_diff:
        tqdm.write(f"   [结果] {group_name.upper()} 任务执行完毕，未发现任何新记录。")
    else:
        tqdm.write(f"   [结果] {group_name.upper()} 任务有更新：")
        if entries_for_target:
            tqdm.write(f"     ✅ 主文件新增/更新 {len(entries_for_target)} 条:")
            for item in entries_for_target:
                tqdm.write(f"        -> {item}")
        if entries_for_diff:
            tqdm.write(f"     ⚠️ Diff 文件新增 {len(entries_for_diff)} 条:")
            for item in entries_for_diff:
                tqdm.write(f"        -> {item}")
    tqdm.write("")

    if aborted:
        raise aborted

def run_earnings_task(bm):
    tqdm.write("\n" + "=" * 50)
    tqdm.write(">>> 开始执行任务: Earnings Release")
    tqdm.write("=" * 50)

    TASK_CONFIGS = []
    new_path = earnings_file('new')
    if not file_has_dated_entries(new_path):
        tqdm.write("检测到 Earnings_Release_new 为空，将补抓本周数据。")
        TASK_CONFIGS.append({"group_name": "new", "duplicate_check_files": []})
    elif file_has_unknown_call_time(new_path):
        tqdm.write("检测到 Earnings_Release_new 中存在 N/A，将刷新本周数据。")
        TASK_CONFIGS.append({"group_name": "new", "duplicate_check_files": []})

    for i, g in enumerate(EARNINGS_GROUPS[1:], start=1):
        TASK_CONFIGS.append({
            "group_name": g,
            "duplicate_check_files": [earnings_file(x) for x in EARNINGS_GROUPS[:i]],
        })

    for cfg in TASK_CONFIGS:
        cfg["file_path"] = earnings_file(cfg["group_name"])
        cfg["diff_path"] = earnings_diff_file(cfg["group_name"])
        cfg["backup_dir"] = BACKUP_ROOT_DIR
        cfg["earnings_release_path"] = EARNINGS_ARCHIVE_PATH

    try:
        with open(SECTORS_ALL_JSON_PATH, 'r', encoding='utf-8') as f:
            sectors_data = json.load(f)
    except Exception as e:
        msg = f"读取 {SECTORS_ALL_JSON_PATH} 失败，跳过 Earnings: {e}"
        tqdm.write(msg)
        show_alert(msg)
        return

    try:
        bm.start()
    except SiteUnavailable as e:
        msg = f"Earnings 任务未执行：{e}"
        tqdm.write(msg)
        show_alert(msg)
        return

    aborted = None
    task_pbar = tqdm(TASK_CONFIGS, desc="总任务进度", position=0)
    try:
        for config in task_pbar:
            task_pbar.set_description(f"执行任务: {config['group_name'].upper()}")
            try:
                run_single_scraper_task(bm, sectors_data, config)
            except SiteUnavailable as e:
                aborted = e
                tqdm.write(f"网络/站点持续不可用，停止剩余分组: {e}")
                break
            except Exception as e:
                tqdm.write(f"[{config['group_name']}] 执行出错（继续下一组）: {e}")
    finally:
        task_pbar.close()

    if aborted:
        show_alert(f"Earnings 抓取中断：{aborted}\n（已抓到的数据已保存）")
    else:
        tqdm.write("\n所有 Earnings 任务执行完毕。")
        show_alert("Earnings 抓取任务已完成！")

def run_part_b(bm):
    tqdm.write("\n" + "=" * 50)
    tqdm.write(">>> 正在启动 Part B (Selenium 爬虫任务)")
    tqdm.write("=" * 50)
    for task in (run_economic_events_task, run_stock_splits_task, run_earnings_task):
        try:
            task(bm)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            tqdm.write(f"\n{task.__name__} 发生未知错误: {e}")
        time.sleep(1)


# ================= Part C: Polymarket =================

def load_existing_polymarket_data(filename):
    data = {}
    for line in read_clean_lines(filename):
        if ':' in line:
            ticker, percent = line.split(':', 1)
            data[ticker.strip()] = percent.strip()
    return data

def save_polymarket_data(filename, data):
    atomic_write_lines(filename, [f"{t}: {p}" for t, p in data.items()])
    print(f"数据已成功保存至 {filename}，共 {len(data)} 条记录。")

def run_part_c():
    print("\n" + "=" * 50)
    print(">>> 正在启动 Part C (Polymarket 爬虫任务)")
    print("=" * 50)

    earnings_data = load_existing_polymarket_data(POLYMARKET_FILE_PATH)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/120.0.0.0 Safari/537.36"
                )
                print("正在访问 Polymarket 页面...")
                page.goto(POLYMARKET_URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(8000)

                results = page.evaluate("""
                    () => {
                        const out = [];
                        const all = Array.from(document.querySelectorAll('*'));
                        for (const el of all) {
                            const txt = (el.textContent || '').trim();
                            if (el.children.length === 0 && /^\\d{1,3}%$/.test(txt)) {
                                let node = el;
                                let ticker = null;
                                for (let i = 0; i < 6 && node; i++) {
                                    node = node.parentElement;
                                    if (!node) break;
                                    const cand = Array.from(node.querySelectorAll('*'))
                                        .map(x => (x.childElementCount === 0 ? x.textContent.trim() : ''))
                                        .find(t => /^[A-Z]{1,6}$/.test(t));
                                    if (cand) { ticker = cand; break; }
                                }
                                if (ticker) out.push([ticker, txt]);
                            }
                        }
                        return out;
                    }
                """)
            finally:
                browser.close()

        print(f"提取到 {len(results)} 条原始记录，正在合并...")
        skip_values = ["0%", "100%", "0", "100", "0.0%", "100.0%"]

        for ticker, percent in results:
            ticker = ticker.strip()
            clean_percent = percent.strip()
            if not ticker or not clean_percent:
                continue
            if ticker in earnings_data:
                if clean_percent in skip_values:
                    print(f"跳过更新: {ticker} (本地已存在, 新值 {percent})")
                else:
                    earnings_data[ticker] = percent
                    print(f"更新覆盖: {ticker} -> {percent}")
            else:
                earnings_data[ticker] = percent
                print(f"抓取新增: {ticker} -> {percent}")

        save_polymarket_data(POLYMARKET_FILE_PATH, earnings_data)
    except Exception as e:
        print(f"Part C (Polymarket) 执行出错: {e}")


# ================= 诊断 / 命令行 =================

def run_diagnostics():
    print("=" * 60)
    print("网络 / 环境诊断")
    print("=" * 60)
    print(f"系统: {platform.system()} {platform.release()}   Python {sys.version.split()[0]}")
    for label, path in (("Chrome", CHROME_BINARY_PATH), ("chromedriver", CHROME_DRIVER_PATH)):
        ver = ""
        if os.path.exists(path):
            try:
                ver = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
            except Exception as e:
                ver = f"(读取版本失败: {e})"
        print(f"{label:<12}: {path}  {'存在' if os.path.exists(path) else '不存在'}  {ver}")
    print("  ↑ 两者主版本号必须一致（附着模式用的是同一个 Chrome Beta）")
    print(f"系统代理    : {getproxies() or '无'}")
    print(f"YF_PROXY    : {YF_PROXY or '未设置（Chrome 跟随系统代理）'}")
    print(f"调试端口    : {CDP_PORT} {'已有 Chrome 在监听' if cdp_alive() else '空闲'}")
    print(f"专用 profile: {YF_PROFILE_DIR}")

    tests = [("系统代理/直连", build_opener())]
    if YF_PROXY and not YF_PROXY.lower().startswith("socks"):
        tests.append(("YF_PROXY", build_opener(ProxyHandler({"http": YF_PROXY, "https": YF_PROXY}))))
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    print("\n连通性测试：")
    for label, op in tests:
        for url in ("https://finance.yahoo.com/", YAHOO_PROBE_URL):
            t0 = time.time()
            try:
                req = Request(url, headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"})
                with op.open(req, timeout=15) as r:
                    body = r.read()
                    print(f"  [{label}] HTTP {r.status}  {len(body)} 字节  {time.time() - t0:.1f}s  -> {r.geturl()}")
            except Exception as e:
                print(f"  [{label}] {url}\n      失败({time.time() - t0:.1f}s): {getattr(e, 'code', '')} {e}")
    print("\n解读：")
    print("  · 直连失败、YF_PROXY 成功 → 日常 Chrome 走的是扩展/独立代理，请设置 YF_PROXY 或在 open 窗口装好代理扩展")
    print("  · 全部失败 → 网络或代理本身有问题，先用浏览器确认代理可用")
    print("  · 全部成功但脚本仍失败 → 用默认有界面模式运行，按提示在窗口内手动处理")

def parse_cli():
    global BROWSER_MODE, ATTACH_ONLY, KEEP_BROWSER_OPEN
    args = {a.lower().lstrip("-") for a in sys.argv[1:]}
    if "headless" in args:
        BROWSER_MODE = "headless"
        print(">>> [模式] 无头 Chrome（遇到验证无法人工处理）")
    if "cdp" in args:
        BROWSER_MODE = "cdp"
        ATTACH_ONLY = True
        print(f">>> [模式] 只附着到已运行的调试 Chrome（端口 {CDP_PORT}）")
    if "keep" in args:
        KEEP_BROWSER_OPEN = True
        print(">>> [模式] 运行结束后保留 Chrome 窗口")
    return args

def open_browser_for_manual():
    if cdp_alive():
        print(f">>> 端口 {CDP_PORT} 上已有调试 Chrome，直接在那个窗口里操作即可。")
        return
    ok, _ = launch_cdp_chrome(YAHOO_PROBE_URL)
    if ok:
        print(">>> 专用 Chrome 已打开并保持运行。你可以在里面：接受 Cookie / 登录 Yahoo / 安装代理扩展。")
        print(f">>> 之后直接运行 python {SCRIPT_NAME}，会自动附着这个窗口，结束时也不会关闭它。")
    else:
        print("!!! 启动失败，请检查 Chrome 路径或执行 diag 诊断。")


if __name__ == "__main__":
    cli = parse_cli()
    if "diag" in cli:
        run_diagnostics()
        sys.exit(0)
    if "open" in cli:
        open_browser_for_manual()
        sys.exit(0)

    # 1. Part A：按日期对账归档（任何一天运行都安全，幂等）
    PartA_Reconciler().run()
    time.sleep(1)

    bm = BrowserManager()
    try:
        # 2. Part B：Yahoo Finance（经济事件 / 拆股 / 财报）
        run_part_b(bm)
        time.sleep(1)
        # 3. Part C：Polymarket
        run_part_c()
    except KeyboardInterrupt:
        tqdm.write("\n程序被用户手动终止。")
    finally:
        bm.close()