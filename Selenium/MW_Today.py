# -*- coding: utf-8 -*-
"""
MW_Today.py
从 MarketWatch 抓取 Sectors_empty.json 中各分组的最新一日数据，写入 Finance.db（组名即表名），
成功后从 JSON 中移除该 symbol。

支持分组：
  - ETFs + 11 个股票分组      -> download-data 历史表格 (OHLCV)
  - Bonds / Currencies / Crypto / Indices / Commodities -> 行情概览页的实时价格

运行方式（附着模式）：连接 mw_debug_chrome.sh 启动的调试 Chrome（127.0.0.1:9222），
若调试 Chrome 未运行会自动调用 mw_debug_chrome.sh start。附着模式下始终为有界面模式。

用法:
    python MW_Today.py --headful --no-fast  # 流水线使用的方式
    python MW_Today.py --groups ETFs Energy # 只跑指定分组
    python MW_Today.py --dry-run            # 只抓取并打印，不写库、不改 JSON（验证映射用）
    python MW_Today.py --no-sanity          # 关闭价格偏差校验
    python MW_Today.py --no-check           # 结束后不调用 Check_yesterday.py
    python MW_Today.py --no-auto-slider     # 关闭滑块自动验证（遇到验证码只能手动）
    python MW_Today.py --no-escalate        # 无头模式遇到验证码时不自动切换为有界面模式
    python MW_Today.py --no-fast            # 关闭快速通道，每个 symbol 都完整打开页面（最保守）
    python MW_Today.py --ignore-cooldown    # 忽略"距上次被封未满冷却期"的启动等待

防封机制：
    1. 拟人节奏：页面间隔 3~6.5 秒随机，每连续 40~70 页休息 1~2.5 分钟；
    2. 自适应限速：触发验证后间隔放大，成功后缓慢恢复；
    3. 区分"滑块验证"与"硬封禁页"（DataDome iframe t=bv / access restricted 文本）：
       硬封禁时不再尝试滑块、不再重试，立刻停止访问并逐级冷却（12/25/45 分钟），冷却后继续；
    4. 被封时间写入 mw_block_state.json，下次启动若距上次被封不足 STARTUP_GRACE_MINUTES 会先等待；
    5. 无人值守模式（环境变量 FS_UNATTENDED=1）下滑块自动失败直接转冷却，不空等人工。

提速机制：
    1. 快速通道：首个 symbol 正常导航拿到 marketwatch.com 同源上下文与反爬 Cookie 后，
       后续 symbol 在页面内 fetch() 目标 HTML 并用 DOMParser 解析；
       任何非 "ready" 结果都自动回退为页面导航；
    2. 页面导航使用 pageLoadStrategy=none + 轮询，目标元素"后面已有兄弟元素"即视为解析完整，立即提取。

滑块自动验证（macOS）：
    检测到验证码 -> 按 9222 端口精确定位调试 Chrome 并切到最前台 -> 屏幕模板匹配 marketwatch_verify.png
    -> 拟人化拖拽 -> 滑块消失即判定通过 -> 把终端切回最前台 -> 等待页面自动跳转后继续抓取。
    需要给终端授予「屏幕录制」「辅助功能」「自动化」权限。

防串页机制：
    1. 每次导航前在旧文档上打 window.__mwStalePage 标记；
    2. 历史表格页校验 URL 中的 symbol 段与目标一致；
    3. 同一轮内数据指纹去重。
"""
import argparse
import atexit
import contextlib
import datetime
import json
import os
import platform
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import pandas_market_calendars as mcal
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from tqdm import tqdm

try:
    import fcntl
except ImportError:      # Windows
    fcntl = None

# ================= 配置区域 =================
USER_HOME = os.path.expanduser("~")
IS_MAC = platform.system() == 'Darwin'

BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_DIR = os.path.join(BASE_CODING_DIR, "News")

SLIDER_GUARD_STATE = os.path.join(NEWS_DIR, "slider_guard_mw.json")

DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
SECTORS_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_empty.json")
SYMBOL_MAPPING_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping.json")
MW_SYMBOL_OVERRIDE_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping_mw.json")
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

JSON_LOCK_PATH = os.path.join(tempfile.gettempdir(), "Financial_System_Sectors_empty.lock")

WRONG_TXT_PATH = os.path.join(NEWS_DIR, "wrong.txt")
PRICE_DEVIATION_ALERT_THRESHOLD = 0.10

# ---- 附着模式（连接 mw_debug_chrome.sh 启动的调试 Chrome） ----
ATTACH_MODE = True
DEBUG_PORT = 9222
DEBUG_CHROME_SCRIPT = os.path.join(FINANCIAL_SYSTEM_DIR, "Selenium", "mw_debug_chrome.sh")
UNATTENDED = os.environ.get("FS_UNATTENDED") == "1"

# 非附着模式才使用的独立 Profile（附着模式下 Profile 由 mw_debug_chrome.sh 管理）
USE_PERSISTENT_PROFILE = True
MW_PROFILE_DIR = os.environ.get("MW_PROFILE_DIR") or os.path.join(DOWNLOADS_DIR, "backup", "mw_chrome_profile")
LEGACY_MW_PROFILE_DIRS = [
    os.path.join(FINANCIAL_SYSTEM_DIR, "Selenium", "mw_chrome_profile"),
]
CLEAN_PROFILE_CACHE_ON_EXIT = True
PROFILE_CACHE_SUBPATHS = [
    "Default/Cache", "Default/Code Cache", "Default/GPUCache",
    "Default/DawnCache", "Default/DawnGraphiteCache", "Default/DawnWebGPUCache",
    "Default/Service Worker/CacheStorage", "Default/Service Worker/ScriptCache",
    "GrShaderCache", "GraphiteDawnCache", "ShaderCache",
    "component_crx_cache", "extensions_crx_cache", "Crashpad",
]

if IS_MAC:
    CHROME_BINARY_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver")
elif platform.system() == 'Windows':
    CHROME_BINARY_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(CHROME_BINARY_PATH):
        CHROME_BINARY_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver.exe")
else:
    CHROME_BINARY_PATH = "/usr/bin/google-chrome"
    CHROME_DRIVER_PATH = "/usr/bin/chromedriver"

# ---- 抓取参数 ----
MW_BASE_URL = "https://www.marketwatch.com/investing"
PAGE_LOAD_TIMEOUT = 30
TABLE_WAIT_TIMEOUT = 15
QUOTE_WAIT_TIMEOUT = 15
POLL_INTERVAL = 0.2             # 页面状态轮询间隔（秒）
CAPTCHA_MANUAL_WAIT = 180       # 有人值守时，等待手动完成验证码的最长时间
MAX_RETRIES = 3
MAX_ROWS_TO_EXTRACT = 5

# ---- 快速通道（页面内 fetch） ----
FAST_FETCH_ENABLED = True
FAST_FETCH_TIMEOUT = 12
FAST_FETCH_MAX_MISSES = 3
FAST_FETCH_RENAV_EVERY = 60

# ---- 限速（拟人节奏 + 自适应） ----
FETCH_DELAY_RANGE = (1.0, 2.5)    # 快速通道之间的随机间隔（秒）
NAV_DELAY_RANGE = (3.0, 6.5)      # 页面导航之间的随机间隔（秒）——原 0.6~1.4 过快，是被封主因
THROTTLE_MAX_SCALE = 4.0          # 触发验证后间隔最多放大倍数
THROTTLE_DECAY = 0.97             # 每成功一次，放大倍数向 1 缓慢衰减
LONG_BREAK_EVERY = (40, 70)       # 每连续导航这么多页（随机）……
LONG_BREAK_SECONDS = (60, 150)    # ……休息这么久（随机）
EST_SECONDS_PER_SYMBOL = 9        # 仅用于启动时估算耗时

# ---- 硬封禁冷却 ----
HARD_BLOCK_COOLDOWN_MINUTES = [12, 25, 45]   # 连续第 1/2/3 次封禁的冷却时长
HARD_BLOCK_JITTER = 0.2                      # 冷却时长 ±20% 随机
HARD_BLOCK_MAX_PER_RUN = 5                   # 单轮累计封禁上限
BLOCK_STATE_PATH = os.path.join(NEWS_DIR, "mw_block_state.json")
STARTUP_GRACE_MINUTES = 15                   # 启动时距上次被封不足此时长则先等待
RECENT_BLOCK_HOURS = 6                       # 此时间内被封过，本轮从 ×2 间隔起步

# ---- 资源屏蔽（仅非附着模式下可用；当前附着模式未启用） ----
BLOCK_AD_RESOURCES = True
BLOCKED_URL_PATTERNS = [
    "*doubleclick.net*", "*googlesyndication.com*", "*googletagservices.com*",
    "*googletagmanager.com*", "*google-analytics.com*", "*adservice.google.*",
    "*amazon-adsystem.com*", "*adsrvr.org*", "*taboola.com*", "*outbrain.com*",
    "*chartbeat.com*", "*chartbeat.net*", "*scorecardresearch.com*", "*moatads.com*",
    "*permutive.com*", "*permutive.app*", "*pubmatic.com*", "*rubiconproject.com*",
    "*criteo.com*", "*criteo.net*", "*casalemedia.com*", "*openx.net*", "*adnxs.com*",
    "*krxd.net*", "*bluekai.com*", "*connect.facebook.net*", "*ads-twitter.com*",
    "*quantserve.com*", "*hotjar.com*", "*nr-data.net*", "*indexww.com*",
    "*3lift.com*", "*sharethrough.com*", "*teads.tv*",
    "*.mp4*", "*.m3u8*",
]

# ---- 滑块自动验证（macOS） ----
AUTO_SLIDER_ENABLED = True
AUTO_ESCALATE_HEADFUL = True
SLIDER_MODULE_DIR = os.path.join(USER_HOME, "Coding", "python_code", "Modules")
SLIDER_TEMPLATE = "marketwatch_verify.png"
SLIDER_THRESHOLD = 0.85
SLIDER_DISTANCE = 223
SLIDER_OVERSHOOT = 30
SLIDER_OVERSHOOT_JITTER = 10
SLIDER_GRAB_OFFSET = (0, 0)
SLIDER_ATTEMPTS_PER_ROUND = 2
AUTO_SLIDER_MAX_ROUNDS = 2
SLIDER_APPEAR_TIMEOUT = 15
WINDOW_ACTIVATE_SETTLE = 1.0
CAPTCHA_POST_SOLVE_REFRESH_AFTER = 8
CAPTCHA_POST_SOLVE_WAIT = 15
RETURN_TO_TERMINAL = True
SLIDER_DEBUG_DIR = "/tmp"

STALE_DATA_POLICY = "skip"

PRICE_SANITY_CHECK = True
PRICE_SANITY_THRESHOLD = 0.25
PRICE_SANITY_ACTION = "skip"

STALE_PAGE_MARKER = "__mwStalePage"

ASSET_PATH_TO_BODY_TYPE = {
    "stock": "stock",
    "fund": "fund",
    "bond": "bond",
    "currency": "currency",
    "cryptocurrency": "cryptocurrency",
    "index": "index",
    "future": "future",
}

STOCK_SECTORS = [
    'Basic_Materials', 'Communication_Services', 'Consumer_Cyclical',
    'Consumer_Defensive', 'Energy', 'Financial_Services', 'Healthcare',
    'Industrials', 'Real_Estate', 'Technology', 'Utilities',
]

SECTOR_HANDLERS = {
    "ETFs": {"asset_path": "fund", "query": {"mod": "mw_quote_tab"}, "parser": "ohlcv_table",
             "suffix": "/download-data", "resolver": "stock"},
}
for _s in STOCK_SECTORS:
    SECTOR_HANDLERS[_s] = {"asset_path": "stock", "query": {}, "parser": "ohlcv_table",
                           "suffix": "/download-data", "resolver": "stock"}

SECTOR_HANDLERS.update({
    "Bonds": {"asset_path": "bond", "query": {}, "parser": "quote", "suffix": "",
              "resolver": "override_only", "expect_type": "bond", "row_style": "price_only",
              "allow_non_positive": True, "sanity": True},
    "Currencies": {"asset_path": "currency", "query": {}, "parser": "quote", "suffix": "",
                   "resolver": "name_lower", "expect_type": "currency", "row_style": "price_only",
                   "sanity": True},
    "Crypto": {"asset_path": "cryptocurrency", "query": {}, "parser": "quote", "suffix": "",
               "resolver": "crypto", "expect_type": "cryptocurrency", "row_style": "flat_ohlc",
               "sanity": True},
    "Indices": {"asset_path": "index", "query": {}, "parser": "quote", "suffix": "",
                "resolver": "index", "expect_type": "index", "row_style": "price_only",
                "sanity": True},
    "Commodities": {"asset_path": "future", "query": {}, "parser": "quote", "suffix": "",
                    "resolver": "future", "expect_type": "future", "row_style": "price_only",
                    "sanity": True},
})

MW_BUILTIN_OVERRIDES = {
    "Bonds": {
        "US10Y": "tmubmusd10y?countrycode=bx",
        "US2Y": "tmubmusd02y?countrycode=bx",
        "US30Y": "tmubmusd30y?countrycode=bx",
    },
    "Currencies": {
        "DXY": "index/dxy",
    },
    "Indices": {
        "NASDAQ": "comp",
        "VIX": "vix",
        "Brazil": "bvsp?countrycode=br",
        "Nikkei": "nik?countrycode=jp",
        "Russell": "rut",
        "S&P500": "spx",
        "Korea": "180721?countrycode=kr",
        "DowJones": "djia",
        "HANGSENG": "hsi?countrycode=hk",
        "Shanghai": "shcomp?countrycode=cn",
        "EURO50": "sx5e?countrycode=xx",
        "Singapore": "sti?countrycode=sg",
        "India": "1?countrycode=in",
    },
    "Commodities": {
        "Huangjin": "gc00",
        "Silver": "si00",
        "Copper": "hg00",
        "Platinum": "pl00",
        "Naturalgas": "ng00",
        "CrudeOil": "cl00",
        "Brent": "brn00?countrycode=uk",
        "YuMi": "c00",
        "Soybean": "s00",
        "Oat": "o00",
        "Rice": "rr00",
        "LeanHogs": "lh00",
        "LiveCattle": "lc00",
    },
}

# ================= 防止系统休眠控制 =================
_caffeinate_proc = None


def start_caffeinate():
    global _caffeinate_proc
    if IS_MAC:
        try:
            _caffeinate_proc = subprocess.Popen(["caffeinate", "-idmu"])
            print(">>> [系统] 已开启防休眠模式 (caffeinate)")
        except Exception as e:
            print(f">>> [系统] 无法启动 caffeinate: {e}")


def stop_caffeinate():
    global _caffeinate_proc
    if _caffeinate_proc:
        try:
            _caffeinate_proc.terminate()
            _caffeinate_proc = None
            print(">>> [系统] 已关闭防休眠模式")
        except Exception as e:
            print(f">>> [系统] 关闭 caffeinate 时出错: {e}")


atexit.register(stop_caffeinate)


# ================= 自定义异常 =================
class ScrapeError(Exception):
    pass


class SymbolNotFoundError(ScrapeError):
    def __init__(self, msg, actual_type=None, final_url=None):
        super().__init__(msg)
        self.actual_type = actual_type
        self.final_url = final_url


class CaptchaBlockedError(ScrapeError):
    pass


class HardBlockedError(CaptchaBlockedError):
    """硬封禁页（access restricted / DataDome t=bv），没有可拖拽的滑块，只能冷却等待"""
    pass


class StalePageError(ScrapeError):
    """页面未完成跳转（仍停留在旧页面）或抓到的数据与其它 symbol 完全一致（串页）"""
    pass


class _NeverRaised(Exception):
    pass


# ================= 通用小工具 =================

def notify_mac(msg, title="MW_Today"):
    if not IS_MAC:
        return
    try:
        subprocess.run(["osascript", "-e", "on run argv",
                        "-e", f'display notification (item 1 of argv) with title "{title}"',
                        "-e", "end run", msg], capture_output=True, timeout=10)
    except Exception:
        pass


def sleep_with_countdown(seconds, label):
    end = time.time() + max(0.0, seconds)
    last_print = None
    while True:
        left = end - time.time()
        if left <= 0:
            break
        if last_print is None or time.time() - last_print >= 60:
            tqdm.write(f"   ⏳ {label}：剩余约 {int(left // 60)} 分 {int(left % 60)} 秒")
            last_print = time.time()
        time.sleep(min(5.0, left))


def load_block_state():
    try:
        with open(BLOCK_STATE_PATH, 'r', encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_block_state(**kw):
    st = load_block_state()
    st.update(kw)
    try:
        os.makedirs(NEWS_DIR, exist_ok=True)
        with open(BLOCK_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except Exception as e:
        tqdm.write(f"⚠️ 写入封禁状态文件失败: {e}")


def wait_startup_grace(ignore=False):
    """距上次被封不足 STARTUP_GRACE_MINUTES 则先等待；返回是否近期被封过（用于提高初始间隔）"""
    ts = load_block_state().get("last_block_ts")
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return False
    since = time.time() - ts
    recent = since < RECENT_BLOCK_HOURS * 3600
    left = STARTUP_GRACE_MINUTES * 60 - since
    if left > 0 and not ignore:
        tqdm.write(f"🧊 距上次被 MarketWatch 拦截仅 {since / 60:.1f} 分钟，先冷却 {left / 60:.1f} 分钟再开始"
                   f"（--ignore-cooldown 可跳过）")
        sleep_with_countdown(left, "启动前冷却")
    return recent


# ================= 自适应限速 =================
class AdaptiveThrottle:
    def __init__(self):
        self.scale = 1.0

    def on_block(self):
        old = self.scale
        self.scale = min(THROTTLE_MAX_SCALE, max(2.0, self.scale * 1.5))
        if self.scale != old:
            tqdm.write(f"   🐢 触发反爬，后续请求间隔放大到 ×{self.scale:.1f}")

    def set_floor(self, v):
        self.scale = max(self.scale, min(THROTTLE_MAX_SCALE, v))

    def on_success(self):
        if self.scale > 1.0:
            self.scale = max(1.0, self.scale * THROTTLE_DECAY)

    def sleep(self, via):
        lo, hi = FETCH_DELAY_RANGE if via == "fetch" else NAV_DELAY_RANGE
        time.sleep(random.uniform(lo, hi) * self.scale)


# ================= 1. 数据库与 JSON 操作 =================

def get_table_type(sector):
    expanded_sectors = [
        'ETFs', 'Basic_Materials', 'Communication_Services', 'Consumer_Cyclical',
        'Consumer_Defensive', 'Energy', 'Financial_Services', 'Healthcare',
        'Industrials', 'Real_Estate', 'Technology', 'Utilities', 'Crypto'
    ]
    no_volume_sectors = ['Bonds', 'Currencies', 'Commodities', 'Economics']
    if sector in expanded_sectors:
        return "expanded"
    elif sector in no_volume_sectors:
        return "no_volume"
    return "standard"


def create_table_if_not_exists(cursor, table_name, table_type):
    safe_table_name = f'"{table_name}"'
    if table_type == "expanded":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT, name TEXT, price REAL, volume INTEGER,
            open REAL, high REAL, low REAL,
            UNIQUE(date, name)
        )''')
    elif table_type == "no_volume":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT, name TEXT, price REAL,
            UNIQUE(date, name)
        )''')
    else:
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT, name TEXT, price REAL, volume INTEGER,
            UNIQUE(date, name)
        )''')


def insert_data_to_db(db_path, table_name, data_rows, table_type):
    """data_rows: [(date, name, price, volume, open, high, low), ...]"""
    if not data_rows:
        return False
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    safe_table = f'"{table_name}"'
    try:
        create_table_if_not_exists(cursor, table_name, table_type)
        if table_type == "expanded":
            filtered_data = data_rows
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price, volume, open, high, low)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price = excluded.price, volume = excluded.volume,
                open = excluded.open, high = excluded.high, low = excluded.low;
            """
        elif table_type == "no_volume":
            filtered_data = [(r[0], r[1], r[2]) for r in data_rows]
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price) VALUES (?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET price = excluded.price;
            """
        else:
            filtered_data = [(r[0], r[1], r[2], r[3]) for r in data_rows]
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price, volume) VALUES (?, ?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price = excluded.price, volume = excluded.volume;
            """
        cursor.executemany(upsert_sql, filtered_data)
        conn.commit()
        return True
    except sqlite3.Error as e:
        tqdm.write(f"❌ 数据库写入失败 ({table_name}): {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_last_db_price(db_path, table_name, name, before_date):
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            cur = conn.execute(
                f'SELECT price FROM "{table_name}" WHERE name = ? AND date < ? AND price IS NOT NULL '
                f'ORDER BY date DESC LIMIT 1', (name, before_date))
            r = cur.fetchone()
            if r and r[0] is not None:
                try:
                    return float(r[0])
                except (ValueError, TypeError):
                    return None
            return None
        finally:
            conn.close()
    except sqlite3.Error:
        return None


_RECORDED_WRONG_SYMBOLS = set()


def record_wrong_symbol_if_exceeded(group, symbol, target_date, new_price, dry_run=False):
    prev_price = get_last_db_price(DB_PATH, group, symbol, target_date)
    if prev_price is None or abs(prev_price) < 1e-8:
        return None

    diff = (new_price - prev_price) / abs(prev_price)
    if abs(diff) > PRICE_DEVIATION_ALERT_THRESHOLD:
        dedup_key = (group, symbol, target_date)
        if dedup_key in _RECORDED_WRONG_SYMBOLS:
            return diff

        tqdm.write(f"🚨 [{symbol}] ({group}) 价格与前一日偏差超 10%: "
                   f"前值 {prev_price} -> 新值 {new_price} ({diff:+.2%})")

        if dry_run:
            tqdm.write(f"   🔍 [DRY-RUN] 模拟追加 [{symbol}] 到: {WRONG_TXT_PATH}")
            _RECORDED_WRONG_SYMBOLS.add(dedup_key)
            return diff

        try:
            os.makedirs(NEWS_DIR, exist_ok=True)
            entry = {
                "group": group, "symbol": symbol, "date": target_date,
                "mw_price": new_price, "prev_price": prev_price,
                "pct": round(diff, 6),
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            }
            with open(WRONG_TXT_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            _RECORDED_WRONG_SYMBOLS.add(dedup_key)
            tqdm.write(f"   📝 已追加 [{symbol}] 到 {WRONG_TXT_PATH}")
        except Exception as e:
            tqdm.write(f"❌ 写入 {WRONG_TXT_PATH} 失败: {e}")
        return diff
    return None


def load_json_file(json_path, desc="JSON"):
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        tqdm.write(f"⚠️ 读取{desc}出错 ({json_path}): {e}")
        return None


def load_tasks_from_json(json_path):
    data = load_json_file(json_path, "任务 JSON")
    if data is None:
        tqdm.write(f"⚠️ 未找到或无法读取 JSON 文件: {json_path}")
        return {}
    return data


def load_alias_mapping(json_path):
    mapping = load_json_file(json_path, "映射文件")
    if not mapping:
        return {}
    return {v: k for k, v in mapping.items()}


def load_mw_overrides(json_path):
    data = load_json_file(json_path, "MW 覆盖映射")
    return data if isinstance(data, dict) else {}


@contextlib.contextmanager
def json_file_lock():
    if fcntl is None:
        yield
        return
    with open(JSON_LOCK_PATH, "a") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def atomic_write_json(json_path, data):
    dir_name = os.path.dirname(json_path) or "."
    try:
        mode = os.stat(json_path).st_mode & 0o777
    except OSError:
        mode = 0o644
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, json_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def remove_symbol_from_json(json_path, group_name, symbol):
    try:
        with json_file_lock():
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if group_name in data and symbol in data[group_name]:
                data[group_name] = [s for s in data[group_name] if s != symbol]
                atomic_write_json(json_path, data)
                return True
    except Exception as e:
        tqdm.write(f"⚠️ 更新 JSON 失败 [{symbol}]: {e}")
    return False


# ================= 2. 交易日 =================

def get_prev_trading_date(ref_date):
    try:
        nyse = mcal.get_calendar('NYSE')
        schedule = nyse.schedule(start_date=ref_date - datetime.timedelta(days=15), end_date=ref_date)
        past_days = [d for d in schedule.index.date if d < ref_date]
        if past_days:
            return past_days[-1].strftime('%Y-%m-%d')
    except Exception as e:
        tqdm.write(f"⚠️ 计算交易日失败（退化为前一个工作日）: {e}")
    d = ref_date - datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d.strftime('%Y-%m-%d')


def get_last_valid_trading_date():
    try:
        return get_prev_trading_date(datetime.datetime.now().date())
    except Exception as e:
        tqdm.write(f"⚠️ 计算交易日失败: {e}")
        return None


_MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}


def parse_quote_date(text):
    if not text:
        return None
    for m in re.finditer(r'\b([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2}),?\s+(\d{4})', text):
        mon = _MONTHS.get(m.group(1).lower())
        if mon:
            try:
                return datetime.date(int(m.group(3)), mon, int(m.group(2))).strftime('%Y-%m-%d')
            except ValueError:
                continue
    m = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', text)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


# ================= 3. Symbol -> URL =================

def _parse_override_value(value):
    values = value if isinstance(value, (list, tuple)) else [value]
    out = []
    for v in values:
        if not v:
            continue
        path_part, _, qs = str(v).strip().partition('?')
        path_part = path_part.strip().strip('/').lower()
        if path_part.startswith('investing/'):
            path_part = path_part[len('investing/'):]
        asset = None
        if '/' in path_part:
            asset, _, path_part = path_part.partition('/')
            asset = asset.strip() or None
            path_part = path_part.strip('/')
            if asset and asset not in ASSET_PATH_TO_BODY_TYPE:
                tqdm.write(f"⚠️ 映射值 '{v}' 中的品种类型 '{asset}' 不在已知列表 "
                           f"{list(ASSET_PATH_TO_BODY_TYPE)} 中，仍按原样尝试。")
        if path_part:
            out.append((asset, path_part, dict(urllib.parse.parse_qsl(qs))))
    return out


def _derive_by_rule(symbol, handler, alias_to_symbol):
    rule = handler.get("resolver")
    alias = alias_to_symbol.get(symbol)

    if rule == "stock":
        s = (alias or symbol).strip().replace('-', '.').replace('/', '.')
        return [(None, s.lower(), {})]
    if rule == "name_lower":
        s = re.sub(r'[^a-z0-9]', '', symbol.lower())
        return [(None, s, {})] if s else []
    if rule == "crypto":
        s = re.sub(r'[^a-z0-9]', '', (alias or symbol).lower())
        return [(None, s, {})] if s else []
    if rule == "index":
        if alias and alias.startswith('^'):
            s = re.sub(r'[^a-z0-9]', '', alias[1:].lower())
            return [(None, s, {})] if s else []
        return []
    if rule == "future":
        if alias and alias.upper().endswith('=F'):
            root = re.sub(r'[^a-z0-9]', '', alias[:-2].lower())
            return [(None, root + "00", {})] if root else []
        return []
    return []


def resolve_mw_candidates(symbol, group, handler, alias_to_symbol, mw_overrides):
    candidates = []
    grp_over = mw_overrides.get(group)
    if isinstance(grp_over, dict) and symbol in grp_over:
        candidates += _parse_override_value(grp_over[symbol])
    flat = mw_overrides.get(symbol)
    if isinstance(flat, (str, list)):
        candidates += _parse_override_value(flat)
    builtin = MW_BUILTIN_OVERRIDES.get(group, {}).get(symbol)
    if builtin:
        candidates += _parse_override_value(builtin)
    candidates += _derive_by_rule(symbol, handler, alias_to_symbol)

    seen, uniq = set(), []
    for asset, path, q in candidates:
        eff_asset = asset or handler['asset_path']
        key = (eff_asset, path, tuple(sorted(q.items())))
        if key not in seen:
            seen.add(key)
            uniq.append((asset, path, q))
    return uniq


def candidate_label(handler, asset, mw_path):
    return f"{asset}/{mw_path}" if asset and asset != handler['asset_path'] else mw_path


def expected_type_for(handler, asset):
    if asset and asset != handler['asset_path']:
        return ASSET_PATH_TO_BODY_TYPE.get(asset, asset)
    return handler.get("expect_type")


def build_target_url(handler, asset, mw_path, extra_query):
    query = dict(handler.get("query", {}))
    query.update(extra_query or {})
    asset_path = asset or handler['asset_path']
    url = f"{MW_BASE_URL}/{asset_path}/{urllib.parse.quote(mw_path, safe='.')}{handler.get('suffix', '')}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    return url


def suggest_override_from_url(final_url):
    if not final_url:
        return None
    try:
        p = urllib.parse.urlparse(final_url)
        m = re.match(r'^/investing/([^/]+)/([^/]+)', p.path, re.I)
        if not m:
            return None
        s = f"{m.group(1).lower()}/{urllib.parse.unquote(m.group(2)).lower()}"
        q = {k: v for k, v in urllib.parse.parse_qsl(p.query) if k.lower() == 'countrycode'}
        if q:
            s += "?" + urllib.parse.urlencode(q)
        return s
    except Exception:
        return None


# ================= 4. 浏览器 =================
def _find_git_root(path):
    cur = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _remove_dir_if_empty(path):
    try:
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)
    except OSError:
        pass


def prepare_profile_dir():
    if ATTACH_MODE or not USE_PERSISTENT_PROFILE:
        return
    target = os.path.abspath(MW_PROFILE_DIR)

    for legacy in LEGACY_MW_PROFILE_DIRS:
        legacy = os.path.abspath(legacy)
        if legacy == target or not os.path.isdir(legacy):
            continue
        if not os.path.exists(target):
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.move(legacy, target)
                tqdm.write(f">>> [Profile] 已将旧浏览器 Profile 迁移到仓库外: {legacy} -> {target}")
                _remove_dir_if_empty(os.path.dirname(legacy))
            except Exception as e:
                tqdm.write(f"⚠️ [Profile] 迁移旧 Profile 失败: {e}")
        else:
            tqdm.write(f"⚠️ [Profile] 发现遗留的旧 Profile 目录，可手动删除: {legacy}")

    os.makedirs(target, exist_ok=True)

    git_root = _find_git_root(target)
    if git_root:
        tqdm.write(f"⚠️ [Profile] 浏览器 Profile 目录位于 Git 仓库 {git_root} 内，"
                   f"建议修改 MW_PROFILE_DIR 或将其加入 .gitignore。")


def clean_profile_cache():
    # 附着模式下 Profile 由调试 Chrome 使用中，不能也不需要清理
    if ATTACH_MODE or not (USE_PERSISTENT_PROFILE and CLEAN_PROFILE_CACHE_ON_EXIT):
        return
    root = os.path.abspath(MW_PROFILE_DIR)
    if not os.path.isdir(root):
        return
    time.sleep(1)
    for sub in PROFILE_CACHE_SUBPATHS:
        p = os.path.join(root, *sub.split("/"))
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)


def debug_chrome_ready():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_debug_chrome():
    if debug_chrome_ready():
        return True
    if not os.path.exists(DEBUG_CHROME_SCRIPT):
        return False
    tqdm.write("🌐 调试 Chrome 未运行，正在通过 mw_debug_chrome.sh 启动...")
    try:
        subprocess.run(["/bin/bash", DEBUG_CHROME_SCRIPT, "start"], timeout=75)
    except Exception as e:
        tqdm.write(f"⚠️ 启动调试 Chrome 失败: {e}")
    return debug_chrome_ready()


def _debug_chrome_pid():
    """附着模式：监听调试端口的进程即调试 Chrome 主进程"""
    try:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{DEBUG_PORT}", "-sTCP:LISTEN", "-t"],
                             capture_output=True, text=True, timeout=5)
        for x in out.stdout.split():
            if x.strip().isdigit():
                return int(x)
    except Exception:
        pass
    return None


def create_driver(headless=True):
    """附着模式：连接到调试 Chrome（127.0.0.1:9222）。headless 参数在附着模式下不生效。"""
    if ATTACH_MODE and not ensure_debug_chrome():
        raise RuntimeError(f"无法连接调试 Chrome（127.0.0.1:{DEBUG_PORT}），"
                           f"请先运行: bash {DEBUG_CHROME_SCRIPT} start")
    options = webdriver.ChromeOptions()
    options.debugger_address = f"127.0.0.1:{DEBUG_PORT}"
    options.page_load_strategy = 'none'
    driver = webdriver.Chrome(service=Service(executable_path=CHROME_DRIVER_PATH), options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.set_script_timeout(FAST_FETCH_TIMEOUT + 5)
    return driver


def is_driver_alive(driver):
    if driver is None:
        return False
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def safe_quit(driver):
    try:
        if driver:
            driver.quit()
    except Exception:
        pass


def _mark_current_document_stale(driver):
    try:
        driver.execute_script(f"try {{ window.{STALE_PAGE_MARKER} = true; }} catch (e) {{}}")
    except WebDriverException:
        pass


def load_page(driver, url):
    _mark_current_document_stale(driver)
    try:
        driver.get(url)
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except WebDriverException:
            pass


def _body_type_from_class(bc):
    m = re.search(r'(?:^|\s)symbol--([a-z0-9_-]+)', bc or '', re.I)
    return m.group(1).lower() if m else None


def detect_body_symbol_type(driver):
    try:
        bc = driver.execute_script("return document.body ? (document.body.className || '') : '';") or ''
    except WebDriverException:
        return None
    return _body_type_from_class(bc)


# ================= 4.5 滑块自动验证（macOS） =================

_TERM_PROGRAM_APPS = {
    "Apple_Terminal": "Terminal",
    "iTerm.app": "iTerm",
    "vscode": "Visual Studio Code",
    "WarpTerminal": "Warp",
    "ghostty": "Ghostty",
    "WezTerm": "WezTerm",
    "Hyper": "Hyper",
}


def _osascript(script, timeout=10.0):
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stderr or r.stdout or "").strip()
    except Exception as e:
        return False, str(e)


def _mac_app_name_from_binary(binary_path):
    m = re.search(r'/([^/]+)\.app/', binary_path or '')
    return m.group(1) if m else "Google Chrome"


class CaptchaAutoSolver:
    def __init__(self, enabled=True):
        self.enabled = bool(enabled) and IS_MAC
        if enabled and not IS_MAC:
            tqdm.write("⚠️ 滑块自动验证仅支持 macOS，已关闭。")
        self._sv = None
        self._solver = None
        self._init_failed = False
        self._failsafe_exc = _NeverRaised
        self._browser_activated = False
        self._pid_cache = {}
        self.chrome_app_name = _mac_app_name_from_binary(CHROME_BINARY_PATH)
        self.stats = {"solved": 0, "failed": 0, "manual": 0}

    @staticmethod
    def _resolve_failsafe_exc(sv):
        exc = None
        pag = getattr(sv, "pyautogui", None)
        if pag is not None:
            exc = getattr(pag, "FailSafeException", None)
        if exc is None:
            try:
                import pyautogui
                exc = pyautogui.FailSafeException
            except Exception:
                exc = None
        return exc if isinstance(exc, type) else _NeverRaised

    def _get_solver(self):
        if self._solver is not None:
            return self._solver
        if self._init_failed or not self.enabled:
            return None
        try:
            if SLIDER_MODULE_DIR not in sys.path:
                sys.path.insert(0, SLIDER_MODULE_DIR)
            with tqdm.external_write_mode():
                import Slider_Verify as sv
                GuardPolicy = getattr(sv, "GuardPolicy", None)
                guard = GuardPolicy(
                    max_consecutive_failures=2, cooldown_minutes=30,
                    max_per_hour=30, max_per_day=100,
                    min_interval_seconds=0,
                    state_path=SLIDER_GUARD_STATE,
                ) if GuardPolicy else None

                cfg = sv.SliderConfig(
                    template=SLIDER_TEMPLATE, threshold=SLIDER_THRESHOLD,
                    distance=SLIDER_DISTANCE, overshoot=SLIDER_OVERSHOOT,
                    overshoot_jitter=SLIDER_OVERSHOOT_JITTER, grab_offset=SLIDER_GRAB_OFFSET,
                    max_attempts=SLIDER_ATTEMPTS_PER_ROUND, debug_dir=SLIDER_DEBUG_DIR,
                    **({"guard": guard} if GuardPolicy else {}),
                )
                solver = sv.SliderSolver(cfg)
            if not solver.available:
                raise RuntimeError(f"模板不可用: {solver.template_path}")
            self._sv, self._solver = sv, solver
            self._failsafe_exc = self._resolve_failsafe_exc(sv)
            tqdm.write(f"🧩 滑块模块已加载（模板 {solver.template_path}，屏幕缩放 {solver.scale:.2f}）")
            return solver
        except Exception as e:
            self._init_failed = True
            self.enabled = False
            tqdm.write(f"⚠️ 滑块自动验证不可用，将退回手动处理: {e}")
            return None

    def ensure_ready(self):
        return self.enabled and self._get_solver() is not None

    def _browser_pid(self, driver):
        key = id(driver)
        pid = self._pid_cache.get(key)
        if pid:
            try:
                os.kill(pid, 0)
                return pid
            except OSError:
                self._pid_cache.pop(key, None)

        # 附着模式：Chrome 不是 chromedriver 的子进程，必须按调试端口定位（否则会激活到自用 Chrome）
        if ATTACH_MODE:
            pid = _debug_chrome_pid()
            if pid:
                self._pid_cache[key] = pid
                return pid
        try:
            svc_pid = driver.service.process.pid
            out = subprocess.run(["pgrep", "-P", str(svc_pid)], capture_output=True, text=True, timeout=5)
            pids = [int(x) for x in out.stdout.split() if x.strip().isdigit()]
            chosen = None
            for p in pids:
                comm = subprocess.run(["ps", "-o", "comm=", "-p", str(p)],
                                      capture_output=True, text=True, timeout=5).stdout
                if "chrome" in comm.lower():
                    chosen = p
                    break
            chosen = chosen or (min(pids) if pids else None)
            if chosen:
                self._pid_cache[key] = chosen
            return chosen
        except Exception:
            return None

    def activate_browser(self, driver):
        if not IS_MAC:
            return False
        ok = False
        pid = self._browser_pid(driver)
        if pid:
            ok, msg = _osascript(
                'tell application "System Events"\n'
                f'  set p to first process whose unix id is {pid}\n'
                '  set frontmost of p to true\n'
                '  try\n'
                '    perform action "AXRaise" of window 1 of p\n'
                '  end try\n'
                'end tell')
            if not ok:
                tqdm.write(f"   ⚠️ 按进程号切换浏览器失败（{msg[:120]}），改用应用名激活")
        else:
            tqdm.write("   ⚠️ 未能定位调试 Chrome 进程，改用应用名激活（可能激活到自用 Chrome）")
        if not ok:
            ok, msg = _osascript(f'tell application "{self.chrome_app_name}" to activate')
            if not ok:
                tqdm.write(f"   ⚠️ 激活 {self.chrome_app_name} 失败: {msg[:120]}")
        try:
            driver.execute_cdp_cmd("Page.bringToFront", {})
        except Exception:
            pass
        if ok:
            self._browser_activated = True
        return ok

    def activate_terminal(self):
        if not (IS_MAC and RETURN_TO_TERMINAL):
            return False
        bid = os.environ.get("MW_TERMINAL_BUNDLE_ID") or os.environ.get("__CFBundleIdentifier")
        if bid and "chrome" not in bid.lower():
            ok, _ = _osascript(f'tell application id "{bid}" to activate')
            if ok:
                return True
        name = os.environ.get("MW_TERMINAL_APP") or _TERM_PROGRAM_APPS.get(
            os.environ.get("TERM_PROGRAM", ""), "Terminal")
        ok, msg = _osascript(f'tell application "{name}" to activate')
        if not ok:
            tqdm.write(f"   ⚠️ 切回终端 {name} 失败: {msg[:120]}")
        return ok

    def restore_terminal(self):
        if not self._browser_activated:
            return
        self._browser_activated = False
        time.sleep(0.3)
        if self.activate_terminal():
            tqdm.write("   🖥️ 已将终端切回前台")

    def alert_manual(self, driver):
        self.stats["manual"] += 1
        if not IS_MAC:
            return
        self.activate_browser(driver)
        _osascript('display notification "MarketWatch 需要人工完成验证，请切到 Chrome 窗口处理" '
                   'with title "MW_Today" sound name "Glass"')

    def try_solve(self, driver, is_captcha_fn):
        solver = self._get_solver()
        guard = getattr(solver, "guard", None)
        if guard is not None:
            allowed, reason = guard.allow()
            if not allowed:
                tqdm.write(f"   ⏸️ 自动拖拽被保护器暂停：{reason}，转手动处理")
                self.enabled = False
                return "blocked"
        if solver is None:
            return "unavailable"

        self.activate_browser(driver)
        time.sleep(WINDOW_ACTIVATE_SETTLE)

        hit = None
        deadline = time.time() + SLIDER_APPEAR_TIMEOUT
        with tqdm.external_write_mode():
            while True:
                try:
                    hit = solver.locate()
                except Exception as e:
                    print(f"[Slider] 截图/识别异常: {e}", flush=True)
                    hit = None
                    break
                if hit:
                    break
                if not is_captcha_fn():
                    break
                if time.time() >= deadline:
                    break
                time.sleep(0.5)

        if hit is None:
            if not is_captcha_fn():
                tqdm.write("   ✅ 验证页已自行消失")
                self.restore_terminal()
                return "passed"
            tqdm.write(f"   ❓ {SLIDER_APPEAR_TIMEOUT}s 内屏幕上未找到滑块"
                       f"（检查：屏幕录制权限 / 窗口是否在主屏且未被遮挡 / 模板是否匹配）")
            try:
                with tqdm.external_write_mode():
                    solver._save_debug("notfound")
            except Exception:
                pass
            return "not_found"

        try:
            with tqdm.external_write_mode():
                res = solver.solve(hit)
        except self._failsafe_exc:
            tqdm.write("   ✋ 检测到鼠标甩到屏幕角落（FailSafe），本轮运行停用自动拖拽，请手动完成。")
            self.enabled = False
            return "aborted"
        except Exception as e:
            tqdm.write(f"   ❌ 拖拽过程异常: {e}")
            self.stats["failed"] += 1
            return "failed"

        not_found_status = getattr(self._sv, "STATUS_NOT_FOUND", "not_found")
        if res.status == not_found_status:
            tqdm.write(f"   ℹ️ {res.message}")
            if not is_captcha_fn():
                self.restore_terminal()
                return "passed"
            return "solved"
        if res.solved:
            self.stats["solved"] += 1
            tqdm.write(f"   ✅ 滑块验证已通过（拖拽 {res.attempts} 次）")
            self.restore_terminal()
            return "solved"
        self.stats["failed"] += 1
        tqdm.write(f"   ❌ 滑块验证未通过: {res.message}")
        return "failed"

    def summary(self):
        s = self.stats
        if any(s.values()):
            return f"🧩 滑块验证：自动通过 {s['solved']} | 自动失败 {s['failed']} | 转手动 {s['manual']}"
        return None


# ================= 5. 页面解析 JS =================

JS_COMMON = r"""
function mwIsStale() {
    try { if (window.__mwStalePage) return true; } catch (e) {}
    const p = location.protocol;
    return p === 'about:' || p === 'data:' || p === 'chrome-error:';
}
function mwText(el) { return el ? (el.textContent || '').replace(/\s+/g, ' ').trim() : ''; }
function mwCellText(el) {
    if (!el) return '';
    const d = el.querySelector('div');
    return mwText(d || el);
}
function mwHasFollowing(el, maxDepth) {
    let n = el, d = 0;
    const lim = maxDepth || 3;
    while (n && n.parentNode && d <= lim) {
        if (n.nextElementSibling) return true;
        n = n.parentNode; d++;
    }
    return false;
}
function mwBodyText(doc, live) {
    const b = doc.body;
    if (!b) return '';
    if (live) return (b.innerText || '').slice(0, 3000);
    const c = b.cloneNode(true);
    c.querySelectorAll('script, style, noscript, template').forEach(e => e.remove());
    return (c.textContent || '').replace(/\s+/g, ' ').slice(0, 3000);
}
// 返回 'blocked'（硬封禁页，无滑块）/ 'captcha'（滑块验证）/ null（正常页面）
// DataDome：iframe src 中 t=bv 为封禁页，t=fe 为可交互的验证
function mwChallengeKind(doc, live) {
    const ifr = doc.querySelector('iframe[src*="captcha-delivery.com"], iframe[src*="geo.captcha"]');
    if (ifr) {
        const src = ifr.getAttribute('src') || '';
        return /[?&]t=bv(&|$)/i.test(src) ? 'blocked' : 'captcha';
    }
    if (doc.querySelector('.element--intraday, mw-downloaddata, .download-data, '
                        + 'table[aria-label="Historical Quotes data table"], h1[class*="company"]')) return null;
    const txt = mwBodyText(doc, live);
    if (/access is temporarily restricted|temporarily restricted|access denied|you have been blocked|unusual activity/i.test(txt)) return 'blocked';
    if (/verify you are (a )?human|are you a robot/i.test(txt)) return 'captcha';
    return null;
}
function mwIsCaptcha(doc, live) { return mwChallengeKind(doc, live) !== null; }
function mwPathSymbolSeg(pathname) {
    const segs = (pathname || '').toLowerCase().split('/').filter(Boolean);
    let seg = segs.length > 2 ? segs[2] : '';
    try { seg = decodeURIComponent(seg); } catch (e) {}
    return seg;
}
const MW_NOTFOUND_RE = /symbol lookup|no results found|there were no matches/i;

/* ---------- 历史表格 ---------- */
function mwFindTable(doc) {
    let t = doc.querySelector('table[aria-label="Historical Quotes data table"]');
    if (t) return t;
    for (const cand of doc.querySelectorAll('table')) {
        const hs = Array.from(cand.querySelectorAll('thead th')).map(th => mwCellText(th).toLowerCase());
        if (hs.includes('date') && hs.includes('close')) return cand;
    }
    return null;
}
function mwTableState(doc, pathname, expectSeg, maxRows, complete, live) {
    const ck = mwChallengeKind(doc, live);
    if (ck) return ck;
    if (!(pathname || '').toLowerCase().includes('download-data')) return 'notfound';
    if (expectSeg && mwPathSymbolSeg(pathname) !== expectSeg) return 'wrong_symbol';
    const tbl = mwFindTable(doc);
    if (tbl) {
        const rows = tbl.querySelectorAll('tbody tr');
        const k = Math.min(rows.length, maxRows);
        if (k > 0 && (complete || mwHasFollowing(rows[k - 1], 3))) return 'ready';
    }
    if (complete && MW_NOTFOUND_RE.test(mwBodyText(doc, live))) return 'notfound';
    return 'loading';
}
function mwNum(s) {
    if (!s) return null;
    s = s.replace(/[$,\s]/g, '');
    if (!s || s === '-' || /^n\/?a$/i.test(s)) return null;
    const v = parseFloat(s);
    return isNaN(v) ? null : v;
}
function mwVol(s) {
    if (!s) return null;
    s = s.replace(/[,\s]/g, '').toUpperCase();
    const m = s.match(/^([\d.]+)([KMB])?$/);
    if (!m) return null;
    let v = parseFloat(m[1]);
    if (m[2]) v *= { K: 1e3, M: 1e6, B: 1e9 }[m[2]];
    return Math.round(v);
}
function mwParseTable(doc, maxRows) {
    const tbl = mwFindTable(doc);
    if (!tbl) return { error: '未找到数据表格' };
    const headers = Array.from(tbl.querySelectorAll('thead th')).map(th => mwCellText(th).toLowerCase());
    const idx = n => headers.indexOf(n);
    const cols = { date: idx('date'), open: idx('open'), high: idx('high'),
                   low: idx('low'), close: idx('close'), volume: idx('volume') };
    if (cols.date < 0 || cols.close < 0) return { error: '表头解析失败: ' + headers.join('|') };
    const out = [];
    for (const tr of tbl.querySelectorAll('tbody tr')) {
        const cells = tr.querySelectorAll('td');
        if (cells.length <= Math.max(cols.date, cols.close)) continue;
        const m = mwCellText(cells[cols.date]).match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
        if (!m) continue;
        const dateStr = `${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
        const g = k => (cols[k] >= 0 && cells[cols[k]]) ? mwCellText(cells[cols[k]]) : '';
        const close = mwNum(g('close'));
        if (close === null) continue;
        out.push([dateStr, close, mwVol(g('volume')), mwNum(g('open')), mwNum(g('high')), mwNum(g('low'))]);
        if (out.length >= maxRows) break;
    }
    return { data: out };
}

/* ---------- 行情概览 ---------- */
function qNum(s) {
    if (s === null || s === undefined) return null;
    s = String(s).replace(/[\u2212\u2013]/g, '-').replace(/[^0-9.\-]/g, '');
    if (!s || s === '-' || s === '.') return null;
    const v = parseFloat(s);
    return isFinite(v) ? v : null;
}
function qScope(doc) { return doc.querySelector('.element--intraday') || doc; }
function qPrice(doc) {
    const scope = qScope(doc);
    const h2 = scope.querySelector('h2[class*="intraday"][class*="price"]')
            || doc.querySelector('h2[class*="intraday"][class*="price"]');
    if (h2) {
        const bq = h2.querySelector('bg-quote[field="Last" i]') || h2.querySelector('bg-quote:not([class*="change"])');
        if (bq) {
            const raw = bq.getAttribute('data-last-raw');
            let v = qNum(raw);
            if (v !== null) return { raw: raw, value: v, src: 'data-last-raw', el: h2 };
            const t = mwText(bq);
            v = qNum(t);
            if (v !== null) return { raw: t, value: v, src: 'bg-quote', el: h2 };
        }
        const clone = h2.cloneNode(true);
        clone.querySelectorAll('sup').forEach(s => s.remove());
        const t = mwText(clone);
        const v = qNum(t);
        if (v !== null) return { raw: t, value: v, src: 'h2', el: h2 };
    }
    const meta = doc.querySelector('meta[name="price"]');
    if (meta) {
        const c = meta.getAttribute('content');
        const v = qNum(c);
        if (v !== null) return { raw: c, value: v, src: 'meta', el: meta };
    }
    return { raw: null, value: null, src: null, el: null };
}
function qTimestamp(doc) {
    const scope = qScope(doc);
    let el = scope.querySelector('bg-quote[field="date" i]');
    let t = mwText(el);
    if (!t) { el = scope.querySelector('[class*="timestamp"][class*="time"]'); t = mwText(el); }
    if (!t) {
        el = doc.querySelector('meta[name="quoteTime"]');
        t = el ? (el.getAttribute('content') || '') : '';
    }
    return { text: t, el: t ? el : null };
}
function mwQuoteState(doc, pathname, expectType, complete, live) {
    const ck = mwChallengeKind(doc, live);
    if (ck) return ck;
    const path = (pathname || '').toLowerCase();
    if (path.includes('/search') || path === '/' || path === '/investing' || path === '/investing/') return 'notfound';
    const bc = doc.body ? (doc.body.className || '') : '';
    if (expectType && /(^|\s)symbol--/.test(bc)
        && !new RegExp('(^|\\s)symbol--' + expectType + '(\\s|$)').test(bc)) return 'mismatch';
    const p = qPrice(doc);
    if (p.value !== null) {
        if (complete) return 'ready';
        if (p.src !== 'meta' && mwHasFollowing(p.el, 3)) {
            const ts = qTimestamp(doc);
            if (ts.el && mwHasFollowing(ts.el, 3)) return 'ready';
        }
    }
    if (complete && MW_NOTFOUND_RE.test(mwBodyText(doc, live))) return 'notfound';
    return 'loading';
}
function qExtract(doc) {
    const p = qPrice(doc);
    const st = qScope(doc).querySelector('small[class*="status"]');
    return {
        price: p.value, price_raw: p.raw, price_src: p.src,
        ts: qTimestamp(doc).text,
        status: mwText(st),
        company: mwText(doc.querySelector('h1[class*="company"]')),
        body_class: doc.body ? (doc.body.className || '') : ''
    };
}
"""

CAPTCHA_CHECK_JS = JS_COMMON + r"""
return mwIsCaptcha(document, true);
"""

PAGE_STATE_JS = JS_COMMON + r"""
if (mwIsStale()) return 'stale';
return mwTableState(document, location.pathname, (arguments[0] || '').toLowerCase(),
                    arguments[1] || 5, document.readyState !== 'loading', true);
"""

EXTRACT_JS = JS_COMMON + r"""
if (mwIsStale()) return { stale: true };
const r = mwParseTable(document, arguments[0] || 5);
r.path_seg = mwPathSymbolSeg(location.pathname);
r.url = location.href;
return r;
"""

QUOTE_STATE_JS = JS_COMMON + r"""
if (mwIsStale()) return 'stale';
return mwQuoteState(document, location.pathname, arguments[0] || '', document.readyState !== 'loading', true);
"""

QUOTE_EXTRACT_JS = JS_COMMON + r"""
if (mwIsStale()) return { stale: true };
const r = qExtract(document);
r.url = location.href;
return r;
"""

FETCH_JS = JS_COMMON + r"""
const done = arguments[arguments.length - 1];
const url = arguments[0], mode = arguments[1];
const expectSeg = (arguments[2] || '').toLowerCase(), expectType = arguments[3] || '';
const maxRows = arguments[4] || 5, timeoutMs = arguments[5] || 10000;
if (!/(^|\.)marketwatch\.com$/i.test(location.hostname) || mwIsStale()) { done({ state: 'need_nav' }); return; }
let ctrl = null, timer = null;
try { ctrl = new AbortController(); timer = setTimeout(() => ctrl.abort(), timeoutMs); } catch (e) {}
fetch(url, {
    credentials: 'include', redirect: 'follow', cache: 'no-store',
    signal: ctrl ? ctrl.signal : undefined,
    headers: { 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' }
}).then(resp => resp.text().then(text => ({ resp: resp, text: text })))
  .then(({ resp, text }) => {
    if (timer) clearTimeout(timer);
    try {
        const finalUrl = resp.url || url;
        let pathname = '';
        try { pathname = new URL(finalUrl).pathname; } catch (e) {}
        const out = { http: resp.status, final_url: finalUrl, url: finalUrl };
        if (resp.status === 401 || resp.status === 403 || resp.status === 429) {
            out.state = 'captcha'; done(out); return;
        }
        const doc = new DOMParser().parseFromString(text, 'text/html');
        out.body_class = doc.body ? (doc.body.className || '') : '';
        let st = mode === 'table'
            ? mwTableState(doc, pathname, expectSeg, maxRows, true, false)
            : mwQuoteState(doc, pathname, expectType, true, false);
        if (st === 'ready') {
            if (mode === 'table') {
                Object.assign(out, mwParseTable(doc, maxRows));
                out.path_seg = mwPathSymbolSeg(pathname);
            } else {
                Object.assign(out, qExtract(doc));
            }
        } else if (st === 'loading') {
            st = resp.status >= 400 ? 'http_error' : 'unparsed';
        }
        out.state = st;
        done(out);
    } catch (e) {
        done({ state: 'error', error: String((e && e.message) || e) });
    }
}).catch(e => {
    if (timer) clearTimeout(timer);
    done({ state: 'error', error: String((e && e.message) || e) });
});
"""


def _is_captcha_now(driver):
    try:
        return bool(driver.execute_script(CAPTCHA_CHECK_JS))
    except WebDriverException:
        return True


def _wait_loop(driver, timeout, headless, state_fn, timeout_msg, expect_type=None, expect_seg=None,
               captcha_solver=None, on_captcha=None):
    deadline = time.time() + timeout
    manual_mode = False
    auto_rounds = 0
    solved_at = None
    refreshed = False
    seen_captcha = False
    captcha_reported = False

    while True:
        try:
            state = state_fn()
        except WebDriverException:
            if not is_driver_alive(driver):
                raise
            state = 'transient'

        # 硬封禁页：没有滑块，任何重试都只会加重封禁 -> 立即上抛，由上层冷却
        if state == 'blocked':
            if not captcha_reported and on_captcha:
                on_captcha()
            if captcha_solver:
                captcha_solver.restore_terminal()
            raise HardBlockedError("页面显示访问受限（硬封禁页，没有可拖拽的滑块）")

        if seen_captcha and state not in ('captcha', 'transient', 'stale'):
            seen_captcha = False
            if captcha_solver:
                captcha_solver.restore_terminal()
            if manual_mode:
                tqdm.write("   ✅ 验证已完成，继续抓取")

        if state == 'ready':
            return
        if state == 'notfound':
            raise SymbolNotFoundError(f"页面不存在或被重定向: {driver.current_url}",
                                      final_url=driver.current_url)
        if state == 'mismatch':
            actual = detect_body_symbol_type(driver)
            final_url = driver.current_url
            raise SymbolNotFoundError(
                f"页面品种类型为 '{actual or '?'}'，与预期 '{expect_type or '?'}' 不符: {final_url}",
                actual_type=actual, final_url=final_url)
        if state == 'wrong_symbol':
            final_url = driver.current_url
            actual = detect_body_symbol_type(driver) or "redirected"
            raise SymbolNotFoundError(
                f"页面 URL 中的代码与预期 '{expect_seg or '?'}' 不符（可能被重定向到其它代码）: {final_url}",
                actual_type=actual, final_url=final_url)

        if state == 'captcha':
            if not captcha_reported:
                captcha_reported = True
                if on_captcha:
                    on_captcha()
            if headless:
                raise CaptchaBlockedError("触发反爬验证（无头模式无法处理）")
            seen_captcha = True
            now = time.time()
            auto_ok = captcha_solver is not None and captcha_solver.enabled and not manual_mode

            if auto_ok and solved_at is not None:
                elapsed = now - solved_at
                if elapsed >= CAPTCHA_POST_SOLVE_REFRESH_AFTER and not refreshed:
                    refreshed = True
                    tqdm.write("   🔄 滑块已通过但页面未跳转，主动刷新一次...")
                    try:
                        driver.refresh()
                    except WebDriverException:
                        pass
                elif elapsed >= CAPTCHA_POST_SOLVE_WAIT:
                    tqdm.write("   ⚠️ 刷新后仍为验证页，可能出现了新一轮验证")
                    solved_at = None
            elif auto_ok and auto_rounds < AUTO_SLIDER_MAX_ROUNDS:
                auto_rounds += 1
                tqdm.write(f"🧩 检测到滑块验证，开始自动处理（第 {auto_rounds}/{AUTO_SLIDER_MAX_ROUNDS} 轮）...")
                result = captcha_solver.try_solve(driver, lambda: _is_captcha_now(driver))
                deadline = time.time() + CAPTCHA_POST_SOLVE_WAIT + 5
                if result == "solved":
                    solved_at = time.time()
                    refreshed = False
                elif result in ("not_found", "failed"):
                    time.sleep(1.5)
                continue
            elif not manual_mode:
                if UNATTENDED:
                    # 无人值守：没人能手动处理，空等只会让会话风险分继续升高，直接转冷却
                    if captcha_solver:
                        captcha_solver.restore_terminal()
                    raise HardBlockedError("无人值守模式下滑块未能自动通过")
                manual_mode = True
                if captcha_solver:
                    captcha_solver.alert_manual(driver)
                tqdm.write(f"🧩 检测到验证码，请在浏览器窗口中手动完成（最多等待 {CAPTCHA_MANUAL_WAIT} 秒）...")
                deadline = time.time() + CAPTCHA_MANUAL_WAIT

        if time.time() > deadline:
            if state == 'captcha':
                raise CaptchaBlockedError("验证码等待超时")
            if state in ('stale', 'transient'):
                raise StalePageError("页面未完成跳转，仍停留在旧页面（导航超时被中止）")
            raise ScrapeError(timeout_msg)
        time.sleep(0.5 if state == 'captcha' else POLL_INTERVAL)


def wait_for_table(driver, timeout, headless, expect_seg=None, captcha_solver=None, on_captcha=None):
    _wait_loop(driver, timeout, headless,
               lambda: driver.execute_script(PAGE_STATE_JS, (expect_seg or "").lower(), MAX_ROWS_TO_EXTRACT),
               "等待数据表格超时", expect_seg=expect_seg, captcha_solver=captcha_solver,
               on_captcha=on_captcha)


def wait_for_quote(driver, timeout, headless, expect_type, captcha_solver=None, on_captcha=None):
    _wait_loop(driver, timeout, headless,
               lambda: driver.execute_script(QUOTE_STATE_JS, expect_type or ""), "等待行情价格超时",
               expect_type=expect_type, captcha_solver=captcha_solver, on_captcha=on_captcha)


def fetch_via_page(driver, url, mode, expect_seg, expect_type):
    try:
        r = driver.execute_async_script(FETCH_JS, url, mode, (expect_seg or "").lower(), expect_type or "",
                                        MAX_ROWS_TO_EXTRACT, int(FAST_FETCH_TIMEOUT * 1000))
    except TimeoutException:
        return {"state": "error", "error": "fetch 脚本超时"}
    except WebDriverException as e:
        if not is_driver_alive(driver):
            raise
        return {"state": "error", "error": str(e).splitlines()[0][:120] if str(e) else type(e).__name__}
    return r if isinstance(r, dict) else {"state": "error", "error": "fetch 返回结果异常"}


def rows_from_table_result(result, symbol, expect_seg=None):
    if not isinstance(result, dict):
        raise ScrapeError("JS 返回结果异常")
    if result.get("stale"):
        raise StalePageError("提取时检测到仍为旧页面")
    if result.get("error"):
        raise ScrapeError(result["error"])
    if expect_seg and (result.get("path_seg") or "") != expect_seg.lower():
        raise StalePageError(f"提取时页面代码为 '{result.get('path_seg')}'，与预期 '{expect_seg}' 不符: "
                             f"{result.get('url')}")
    rows = []
    for r in result.get("data") or []:
        date_str, price, volume, open_, high, low = r
        if price is None or price <= 0:
            continue
        volume = int(volume) if volume is not None else 0
        rows.append((date_str, symbol, float(price), volume, open_, high, low))
    rows.sort(key=lambda x: x[0], reverse=True)
    return rows


def quote_from_result(r):
    if not isinstance(r, dict):
        raise ScrapeError("JS 返回结果异常")
    if r.get("stale"):
        raise StalePageError("提取时检测到仍为旧页面")
    if r.get("price") is None:
        raise ScrapeError("未解析到价格")
    return r


def select_row(rows, last_valid_date):
    if not rows:
        return None, "无有效数据"
    if not last_valid_date:
        return rows[0], None
    for r in rows:
        if r[0] == last_valid_date:
            return r, None

    older = [r for r in rows if r[0] < last_valid_date]
    base = older[0] if older else rows[0]
    relation = "晚于" if base[0] > last_valid_date else "早于"
    if STALE_DATA_POLICY == "skip":
        return None, f"网页最近可用日期 {base[0]} {relation}预期日期 {last_valid_date}，且无匹配行，跳过（保留在 JSON）。"
    fixed = (last_valid_date,) + tuple(base[1:])
    extra = "（表中仅有更晚日期的数据，可能为盘中数据，请留意）" if not older else ""
    return fixed, (f"网页最近可用日期 {base[0]} {relation}预期日期 {last_valid_date}，且无匹配行，"
                   f"使用该行数据并修改日期为 {last_valid_date} 写入。{extra}")


def build_quote_row(symbol, handler, quote, last_valid_date):
    price = float(quote["price"])
    if not handler.get("allow_non_positive") and price <= 0:
        raise ScrapeError(f"价格异常: {quote.get('price_raw')}")

    page_date = parse_quote_date(quote.get("ts"))
    notes = []

    if last_valid_date:
        target_date = last_valid_date
        if page_date is None:
            msg = f"无法解析页面更新时间（'{quote.get('ts')}'），无法确认数据是否为最新"
            if STALE_DATA_POLICY == "skip":
                return None, msg + "，跳过（保留在 JSON）。"
            notes.append(msg + f"，按 {last_valid_date} 写入。")
        elif page_date < last_valid_date:
            msg = f"页面行情时间 {page_date} 早于预期日期 {last_valid_date}（可能当地休市或数据未更新）"
            if STALE_DATA_POLICY == "skip":
                return None, msg + "，跳过（保留在 JSON）。"
            notes.append(msg + f"，使用当前价格并按 {last_valid_date} 写入。")
    elif page_date:
        target_date = get_prev_trading_date(datetime.date.fromisoformat(page_date))
        notes.append(f"无法计算最近开盘日，按页面时间 {page_date} 的前一交易日 {target_date} 写入。")
    else:
        raise ScrapeError("无法确定写入日期（交易日计算失败且页面时间无法解析）")

    if handler.get("row_style") == "flat_ohlc":
        row = (target_date, symbol, price, 0, price, price, price)
    else:
        row = (target_date, symbol, price, 0, None, None, None)
    return row, (" ".join(notes) if notes else None)


def check_price_sanity(table_name, name, date_str, price):
    prev = get_last_db_price(DB_PATH, table_name, name, date_str)
    if prev is None or prev == 0:
        return True, None
    dev = abs(price - prev) / abs(prev)
    if dev > PRICE_SANITY_THRESHOLD:
        return False, (f"价格 {price} 与库中上一条 {prev} 偏差 {dev:.1%}，超过阈值 {PRICE_SANITY_THRESHOLD:.0%}")
    return True, None


# ================= 6.5 防串页：数据指纹 =================

def table_fingerprint(rows):
    return ("table",) + tuple((r[0], r[2], r[3], r[4], r[5], r[6]) for r in rows)


def quote_fingerprint(quote):
    return ("quote", quote.get("company") or "", str(quote.get("price_raw")), quote.get("ts") or "")


def check_and_register_fingerprint(ctx, fp, symbol, group):
    owner = ctx["fingerprints"].get(fp)
    if owner and owner != (group, symbol):
        raise StalePageError(f"抓到的数据与 [{owner[1]}]({owner[0]}) 完全相同，疑似串页（页面未切换）")
    ctx["fingerprints"][fp] = (group, symbol)


# ================= 6.8 硬封禁冷却 =================

def handle_hard_block(driver, ctx, symbol, reason, solver=None):
    """返回 True 表示已冷却完毕可继续；False 表示达到上限应终止本轮"""
    ctx["hard_blocks"] += 1
    streak = ctx["hard_streak"]
    ctx["hard_streak"] += 1
    save_block_state(last_block_ts=time.time(), last_symbol=symbol, reason=reason,
                     last_block_at=datetime.datetime.now().isoformat(timespec="seconds"))
    if solver:
        solver.restore_terminal()

    # 立即离开封禁页，停止对 MarketWatch 的一切请求
    try:
        driver.get("about:blank")
    except Exception:
        pass

    if streak >= len(HARD_BLOCK_COOLDOWN_MINUTES) or ctx["hard_blocks"] > HARD_BLOCK_MAX_PER_RUN:
        tqdm.write(f"🛑 [{symbol}] {reason}；已连续冷却 {streak} 次 / 本轮累计被封 {ctx['hard_blocks']} 次，"
                   f"终止本轮（剩余 symbol 保留在 JSON，稍后重跑即可续抓）。")
        notify_mac("MarketWatch 多次冷却后仍被拦截，本轮已终止，剩余项保留在 JSON")
        return False

    minutes = HARD_BLOCK_COOLDOWN_MINUTES[streak] * random.uniform(1 - HARD_BLOCK_JITTER, 1 + HARD_BLOCK_JITTER)
    tqdm.write(f"🧊 [{symbol}] {reason}\n"
               f"   第 {streak + 1}/{len(HARD_BLOCK_COOLDOWN_MINUTES)} 次冷却 {minutes:.0f} 分钟，"
               f"期间不访问 MarketWatch，结束后自动续抓（Ctrl+C 可中止）")
    notify_mac(f"MarketWatch 访问受限，冷却 {minutes:.0f} 分钟后自动继续")
    ctx["throttle"].set_floor(2.0 + streak)
    sleep_with_countdown(minutes * 60, "冷却中")
    ctx["nav_since_break"] = 0
    tqdm.write("   ▶️ 冷却结束，继续抓取")
    return True


# ================= 7. 主流程 =================

def build_task_list(tasks_dict, only_groups=None):
    task_list, unknown_pending = [], {}
    for group, symbols in tasks_dict.items():
        if not symbols:
            continue
        if only_groups and group not in only_groups:
            continue
        handler = SECTOR_HANDLERS.get(group)
        if handler is None:
            unknown_pending[group] = len(symbols)
            continue
        for sym in dict.fromkeys(symbols):
            task_list.append((sym, group, handler))
    return task_list, unknown_pending


def _note_fast_miss(ctx, symbol, res):
    fast = ctx["fast"]
    st = res.get("state")
    if st in ("captcha", "blocked"):
        fast["captchas"] += 1
        ctx["throttle"].on_block()
        tqdm.write(f"🛡️ [{symbol}] 快速通道被反爬拦截（HTTP {res.get('http')}），改走页面导航以处理验证...")
    elif st in ("unparsed", "error", "http_error"):
        fast["misses"] += 1
        detail = res.get("error") or f"HTTP {res.get('http')}"
        tqdm.write(f"   ↪ [{symbol}] 快速通道未取到数据（{st}: {str(detail)[:100]}），改走页面导航")
        if fast["misses"] >= FAST_FETCH_MAX_MISSES:
            fast["enabled"] = False
            tqdm.write(f"⚠️ 快速通道连续 {fast['misses']} 次未取到数据，本轮停用，全部改走页面导航。")


def run_single_url(driver, ctx, url, symbol, group, handler, last_valid_date, opts,
                   expect_type=None, mw_path=None):
    table_type = get_table_type(group)
    solver = opts.get("captcha_solver")
    fast = ctx["fast"]
    throttle = ctx["throttle"]
    mode = "table" if handler["parser"] == "ohlcv_table" else "quote"
    force_nav = False

    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        if driver is None:
            ctx["aborted"] = True
            return "failed", None
        headless = opts["headless"]
        via = "nav"

        try:
            payload = None
            if fast["enabled"] and not force_nav and fast["since_nav"] < FAST_FETCH_RENAV_EVERY:
                res = fetch_via_page(driver, url, mode, mw_path, expect_type)
                if res.get("state") == "ready":
                    payload, via = res, "fetch"
                    fast["misses"] = 0
                    fast["since_nav"] += 1
                else:
                    force_nav = True
                    _note_fast_miss(ctx, symbol, res)

            if payload is None:
                load_page(driver, url)
                fast["since_nav"] = 0
                ctx["nav_since_break"] += 1
                if mode == "table":
                    wait_for_table(driver, TABLE_WAIT_TIMEOUT, headless, expect_seg=mw_path,
                                   captcha_solver=solver, on_captcha=throttle.on_block)
                    payload = driver.execute_script(EXTRACT_JS, MAX_ROWS_TO_EXTRACT)
                else:
                    wait_for_quote(driver, QUOTE_WAIT_TIMEOUT, headless, expect_type,
                                   captcha_solver=solver, on_captcha=throttle.on_block)
                    payload = driver.execute_script(QUOTE_EXTRACT_JS)

            ctx["hard_streak"] = 0
            ctx["last_via"] = via
            page_info = ""

            if mode == "table":
                rows = rows_from_table_result(payload, symbol, expect_seg=mw_path)
                if not rows:
                    raise ScrapeError("提取到的数据为空")
                check_and_register_fingerprint(ctx, table_fingerprint(rows), symbol, group)
                selected_row, note = select_row(rows, last_valid_date)
            else:
                quote = quote_from_result(payload)
                check_and_register_fingerprint(ctx, quote_fingerprint(quote), symbol, group)
                selected_row, note = build_quote_row(symbol, handler, quote, last_valid_date)
                page_info = (f"（页面: {quote.get('company') or '-'} | 原始值: {quote.get('price_raw')} "
                             f"| 更新: {quote.get('ts') or '-'}）")

            if note:
                tqdm.write(f"⚠️ [{symbol}] {note}")
            if selected_row is None:
                return "skipped", driver

            if opts["sanity"] and handler.get("sanity"):
                ok, msg = check_price_sanity(group, symbol, selected_row[0], selected_row[2])
                if not ok:
                    if PRICE_SANITY_ACTION == "skip":
                        tqdm.write(f"🚫 [{symbol}] {msg}，疑似映射错误或单位不一致，跳过（保留在 JSON）。{page_info}\n"
                                   f"   URL: {url}  （确认无误可用 --no-sanity 重跑）")
                        return "skipped", driver
                    tqdm.write(f"⚠️ [{symbol}] {msg}（仅提示，继续写入）")

            detail = (f"{selected_row[0]} | price={selected_row[2]} vol={selected_row[3]} "
                      f"O={selected_row[4]} H={selected_row[5]} L={selected_row[6]}")
            via_tag = "⚡" if via == "fetch" else "🌐"

            if opts["dry_run"]:
                record_wrong_symbol_if_exceeded(group, symbol, selected_row[0], selected_row[2], dry_run=True)
                tqdm.write(f"🔍 [DRY-RUN]{via_tag} [{symbol}] -> {group}: {detail} {page_info}\n   URL: {url}")
                ctx["via_count"][via] += 1
                throttle.on_success()
                return "success", driver

            if not insert_data_to_db(DB_PATH, group, [selected_row], table_type):
                raise ScrapeError("数据库写入失败")
            remove_symbol_from_json(SECTORS_JSON_PATH, group, symbol)
            record_wrong_symbol_if_exceeded(group, symbol, selected_row[0], selected_row[2], dry_run=False)
            tqdm.write(f"{via_tag}[{symbol}] 成功写入 1 条数据 ({detail}) 到 {group} 表。{page_info}")
            ctx["via_count"][via] += 1
            throttle.on_success()
            return "success", driver

        except SymbolNotFoundError as e:
            tqdm.write(f"❓ [{symbol}] MarketWatch 未找到: {str(e)[:200]}")
            if e.actual_type:
                hint = suggest_override_from_url(e.final_url)
                if hint:
                    ctx["mismatch_hints"].append(hint)
            return "not_found", driver

        except CaptchaBlockedError as e:   # 含 HardBlockedError
            force_nav = True
            if (not isinstance(e, HardBlockedError) and headless and opts.get("escalate")
                    and solver is not None and solver.ensure_ready()):
                tqdm.write(f"🔁 [{symbol}] 无头模式触发验证，切换为有界面模式以自动拖拽滑块...")
                safe_quit(driver)
                time.sleep(1.5)
                try:
                    driver = create_driver(headless=False)
                except Exception as ce:
                    tqdm.write(f"❌ 有界面浏览器启动失败: {ce}")
                    ctx["aborted"] = True
                    return "failed", None
                opts["headless"] = False
                solver.activate_terminal()
                attempt -= 1
                continue

            # 不再"10 秒后重试"——被封期间每次访问都会延长封禁；改为逐级冷却后续抓
            if not handle_hard_block(driver, ctx, symbol, str(e), solver):
                ctx["aborted"] = True
                return "failed", driver
            attempt -= 1     # 冷却不消耗重试次数（冷却次数本身有上限，不会死循环）
            continue

        except StalePageError as e:
            force_nav = True
            if attempt < MAX_RETRIES:
                tqdm.write(f"⏳ [{symbol}] {e}，重新加载 ({attempt}/{MAX_RETRIES})...")
                time.sleep(1 + attempt + random.uniform(0, 1))
            else:
                tqdm.write(f"❌ [{symbol}] 防串页校验未通过 (已重试 {MAX_RETRIES} 次)，不写入，保留在 JSON: {e}")

        except Exception as e:
            force_nav = True
            if isinstance(e, WebDriverException) and not is_driver_alive(driver):
                tqdm.write("♻️ 浏览器会话已失效，正在重建...")
                safe_quit(driver)
                try:
                    driver = create_driver(opts["headless"])
                except Exception as ce:
                    tqdm.write(f"❌ 浏览器重建失败: {ce}")
                    ctx["aborted"] = True
                    return "failed", None
            if attempt < MAX_RETRIES:
                tqdm.write(f"⏳ [{symbol}] 第 {attempt} 次抓取出错，准备重试: {str(e)[:120]}")
                time.sleep(1.5 * attempt + random.uniform(0, 1))
            else:
                tqdm.write(f"❌ [{symbol}] 抓取失败 (已重试 {MAX_RETRIES} 次): {str(e)[:150]}")
    return "failed", driver


def scrape_marketwatch(headless=True, only_groups=None, dry_run=False, sanity=True,
                       auto_slider=True, escalate=True, fast=True, ignore_cooldown=False):
    if ATTACH_MODE and headless:
        headless = False   # 附着的调试 Chrome 始终有窗口，按有界面模式处理验证
    tasks_dict = load_tasks_from_json(SECTORS_JSON_PATH)
    alias_to_symbol = load_alias_mapping(SYMBOL_MAPPING_PATH)
    mw_overrides = load_mw_overrides(MW_SYMBOL_OVERRIDE_PATH)

    last_valid_date = get_last_valid_trading_date()
    if last_valid_date:
        tqdm.write(f"📅 计算得出的最近有效开盘日为: {last_valid_date}")
    else:
        tqdm.write("⚠️ 无法计算最近有效开盘日，将使用网页原始日期。")

    task_list, unknown_pending = build_task_list(tasks_dict, only_groups)
    for g, n in unknown_pending.items():
        tqdm.write(f"⏭️  分组 [{g}] 有 {n} 个待抓取项，不在本爬虫支持范围内，跳过。")

    empty_stats = {"success": [], "failed": [], "not_found": [], "skipped": [], "aborted": False}
    if not task_list:
        tqdm.write("✅ 支持的分组中没有待抓取的 Symbol，任务结束。")
        return empty_stats

    recently_blocked = wait_startup_grace(ignore=ignore_cooldown)

    captcha_solver = CaptchaAutoSolver(enabled=auto_slider and AUTO_SLIDER_ENABLED)
    fast_enabled = bool(fast and FAST_FETCH_ENABLED)

    tqdm.write(f"共加载 {len(task_list)} 个待抓取任务。（模式: {'无头' if headless else '有界面'}"
               f"{' | 快速通道' if fast_enabled else ' | 逐页导航'}"
               f"{' | DRY-RUN 不写库' if dry_run else ''}{' | 已关闭价格校验' if not sanity else ''}"
               f"{' | 滑块自动验证' if captcha_solver.enabled else ' | 滑块需手动'}"
               f"{' | 无人值守' if UNATTENDED else ''}）")
    tqdm.write(f"⏱️ 预计耗时约 {len(task_list) * EST_SECONDS_PER_SYMBOL / 60:.0f} 分钟"
               f"（拟人节奏，不含可能的冷却时间）")

    prepare_profile_dir()
    try:
        driver = create_driver(headless)
    except Exception as e:
        tqdm.write(f"❌ Selenium 启动失败: {e}")
        empty_stats["failed"] = [f"{t[1]}:{t[0]}" for t in task_list]
        empty_stats["aborted"] = True
        return empty_stats

    if not headless:
        captcha_solver.activate_terminal()

    stats = {"success": [], "failed": [], "not_found": [], "skipped": [], "aborted": False}
    ctx = {"aborted": False, "mismatch_hints": [], "fingerprints": {},
           "hard_blocks": 0, "hard_streak": 0,
           "nav_since_break": 0, "next_break": random.randint(*LONG_BREAK_EVERY),
           "fast": {"enabled": fast_enabled, "misses": 0, "captchas": 0, "since_nav": 0},
           "throttle": AdaptiveThrottle(), "last_via": "nav", "via_count": {"fetch": 0, "nav": 0}}
    if recently_blocked:
        ctx["throttle"].set_floor(2.0)
        tqdm.write(f"   🐢 {RECENT_BLOCK_HOURS} 小时内曾被拦截，本轮请求间隔从 ×2.0 起步")
    opts = {"headless": headless, "dry_run": dry_run, "sanity": sanity,
            "captcha_solver": captcha_solver, "escalate": escalate and AUTO_ESCALATE_HEADFUL}

    pbar = None
    processed = 0
    loop_start = time.time()
    try:
        pbar = tqdm(task_list, desc="总体进度", position=0)
        for idx, (symbol, group, handler) in enumerate(pbar):
            if driver is None or ctx["aborted"]:
                break

            candidates = resolve_mw_candidates(symbol, group, handler, alias_to_symbol, mw_overrides)
            if not candidates:
                tqdm.write(f"❓ [{symbol}] 分组 {group} 无法推导 MarketWatch 地址，"
                           f"请在 Symbol_mapping_mw.json 中添加。")
                stats["not_found"].append(f"{group}:{symbol}")
                continue

            labels = [candidate_label(handler, a, p) for a, p, _ in candidates]
            first = labels[0]
            pbar.set_description(f"处理中: {symbol}" + (f" (→ {first})" if first != symbol.lower() else "") + f" [{group}]")

            ctx["mismatch_hints"] = []
            outcome = "failed"
            for c_idx, (asset, mw_path, extra_q) in enumerate(candidates):
                target_url = build_target_url(handler, asset, mw_path, extra_q)
                expect_type = expected_type_for(handler, asset)
                outcome, driver = run_single_url(driver, ctx, target_url, symbol, group, handler,
                                                 last_valid_date, opts, expect_type=expect_type,
                                                 mw_path=mw_path)
                if outcome != "not_found" or ctx["aborted"]:
                    break
                if c_idx < len(candidates) - 1:
                    tqdm.write(f"   ↪ [{symbol}] 尝试下一个候选地址: {labels[c_idx + 1]}")
                    ctx["throttle"].sleep(ctx["last_via"])

            if outcome == "not_found":
                tqdm.write(f"   [{symbol}] 所有候选地址均未找到（{', '.join(labels)}），可在 Symbol_mapping_mw.json 中添加映射。")
                for hint in dict.fromkeys(ctx["mismatch_hints"]):
                    tqdm.write(f"   💡 建议映射: {{\"{group}\": {{\"{symbol}\": \"{hint}\"}}}}")
            stats[outcome].append(f"{group}:{symbol}")
            processed += 1

            if ctx["aborted"]:
                stats["aborted"] = True
                tqdm.write("🛑 多次冷却后仍被拦截或浏览器无法恢复，终止本轮任务。")
                break

            if idx < len(task_list) - 1:
                ctx["throttle"].sleep(ctx["last_via"])
                # 拟人节奏：连续访问一定数量页面后长休息
                if ctx["nav_since_break"] >= ctx["next_break"]:
                    secs = random.uniform(*LONG_BREAK_SECONDS)
                    tqdm.write(f"☕ 已连续访问 {ctx['nav_since_break']} 个页面，休息 {secs:.0f} 秒（降低被风控概率）")
                    time.sleep(secs)
                    ctx["nav_since_break"] = 0
                    ctx["next_break"] = random.randint(*LONG_BREAK_EVERY)
    finally:
        if pbar is not None:
            pbar.close()
        safe_quit(driver)
        clean_profile_cache()
        tqdm.write("🎉 所有任务执行完毕。")

    elapsed = time.time() - loop_start
    tqdm.write(f"📊 统计：成功 {len(stats['success'])} | 失败 {len(stats['failed'])} | "
               f"未找到 {len(stats['not_found'])} | 跳过 {len(stats['skipped'])}")
    if processed:
        vc = ctx["via_count"]
        tqdm.write(f"⏱️ 总耗时 {elapsed:.1f}s，平均 {elapsed / processed:.2f} 秒/个（含间隔、休息与冷却）"
                   f" | ⚡快速通道 {vc['fetch']} 个 | 🌐页面导航 {vc['nav']} 个"
                   f"{' | 快速通道遇反爬 ' + str(ctx['fast']['captchas']) + ' 次' if ctx['fast']['captchas'] else ''}")
    if ctx["hard_blocks"]:
        tqdm.write(f"🧊 本轮共触发访问受限 {ctx['hard_blocks']} 次（若频繁出现，请调大 NAV_DELAY_RANGE）")
    for key, label in (("failed", "失败"), ("not_found", "未找到"), ("skipped", "跳过")):
        if stats[key]:
            tqdm.write(f"   {label}列表: {', '.join(stats[key])}")
    s = captcha_solver.summary()
    if s:
        tqdm.write(s)
    return stats


def run_check_yesterday_if_empty():
    if not os.path.exists(SECTORS_JSON_PATH):
        print(f"⚠️ 未找到任务文件 {SECTORS_JSON_PATH}，跳过执行 Check_yesterday.py。", flush=True)
        return
    final_tasks = load_tasks_from_json(SECTORS_JSON_PATH)
    if not isinstance(final_tasks, dict):
        print("⚠️ 无法正确读取任务 JSON，跳过执行 Check_yesterday.py。", flush=True)
        return

    if not all(not v for v in final_tasks.values()):
        print("⚠️ Sectors_empty.json 中仍有未完成的任务，跳过执行 Check_yesterday.py。", flush=True)
        return

    print("✅ Sectors_empty.json 已全部清空，开始执行 Check_yesterday.py...", flush=True)
    try:
        r = subprocess.run([sys.executable, CHECK_YESTERDAY_SCRIPT_PATH, "--ignore_sectors", "--nopop"],
                           timeout=900)
        if r.returncode == 0:
            print("✅ Check_yesterday.py 执行完毕。", flush=True)
        else:
            print(f"❌ Check_yesterday 返回错误码 {r.returncode}", flush=True)
    except subprocess.TimeoutExpired:
        print("❌ Check_yesterday 执行超时（900 秒），已终止。", flush=True)
    except Exception as e:
        print(f"❌ 调用 Check_yesterday 出错: {e}", flush=True)


def count_remaining_tasks(only_groups=None):
    tasks = load_tasks_from_json(SECTORS_JSON_PATH)
    if not isinstance(tasks, dict):
        return None
    return sum(len(v) for g, v in tasks.items()
               if v and (not only_groups or g in only_groups))


def parse_args():
    parser = argparse.ArgumentParser(description="MarketWatch 每日数据抓取")
    parser.add_argument("--headful", action="store_true", help="显示浏览器窗口（附着模式下始终有界面）")
    parser.add_argument("--groups", nargs="+", default=None, help="只抓取指定分组，例如 --groups Currencies Indices")
    parser.add_argument("--dry-run", action="store_true", help="只抓取并打印，不写数据库、不修改 JSON")
    parser.add_argument("--no-sanity", action="store_true", help="关闭价格偏差合理性校验")
    parser.add_argument("--no-check", action="store_true", help="结束后不调用 Check_yesterday.py")
    parser.add_argument("--no-auto-slider", action="store_true", help="关闭滑块自动验证（只能手动）")
    parser.add_argument("--no-escalate", action="store_true",
                        help="无头模式遇到验证码时不自动切换为有界面模式")
    parser.add_argument("--no-fast", action="store_true",
                        help="关闭快速通道（页面内 fetch），每个 symbol 都完整打开页面")
    parser.add_argument("--ignore-cooldown", action="store_true",
                        help="忽略启动时的“距上次被封未满冷却期”等待")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    start_caffeinate()
    exit_code = 0
    try:
        stats = scrape_marketwatch(headless=not args.headful, only_groups=args.groups,
                                   dry_run=args.dry_run, sanity=not args.no_sanity,
                                   auto_slider=not args.no_auto_slider, escalate=not args.no_escalate,
                                   fast=not args.no_fast, ignore_cooldown=args.ignore_cooldown)
        if args.dry_run:
            exit_code = 0
        else:
            remaining = count_remaining_tasks(args.groups)
            if remaining is None:
                exit_code = 1
            elif remaining == 0:
                exit_code = 0
            else:
                exit_code = 2
            if not args.no_check and remaining == 0:
                run_check_yesterday_if_empty()
    except KeyboardInterrupt:
        print("\n⛔ 用户中断 MW_Today", flush=True)
        exit_code = 130
    finally:
        stop_caffeinate()
    sys.exit(exit_code)