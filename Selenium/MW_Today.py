# -*- coding: utf-8 -*-
"""
MW_Today.py
从 MarketWatch 抓取 Sectors_empty.json 中各分组的最新一日数据，写入 Finance.db（组名即表名），
成功后从 JSON 中移除该 symbol。

支持分组：
  - ETFs + 11 个股票分组      -> download-data 历史表格 (OHLCV)
  - Bonds / Currencies / Crypto / Indices / Commodities -> 行情概览页的实时价格

用法:
    python MW_Today.py                      # 默认无头模式（遇到滑块验证会自动切换为有界面模式并自动拖拽）
    python MW_Today.py --headful            # 有界面
    python MW_Today.py --groups ETFs Energy # 只跑指定分组
    python MW_Today.py --dry-run            # 只抓取并打印，不写库、不改 JSON（验证映射用）
    python MW_Today.py --no-sanity          # 关闭价格偏差校验
    python MW_Today.py --no-check           # 结束后不调用 Check_yesterday.py
    python MW_Today.py --no-auto-slider     # 关闭滑块自动验证（遇到验证码只能手动）
    python MW_Today.py --no-escalate        # 无头模式遇到验证码时不自动切换为有界面模式
    python MW_Today.py --no-fast            # 关闭快速通道，每个 symbol 都完整打开页面（最保守）

提速机制：
    1. 快速通道：首个 symbol 正常导航拿到 marketwatch.com 同源上下文与反爬 Cookie 后，
       后续 symbol 在页面内 fetch() 目标 HTML 并用 DOMParser 解析，不渲染、不执行广告脚本；
       任何非 "ready" 结果（反爬 / 解析失败 / 重定向 / 未找到）都自动回退为页面导航，由原有流程处理验证码与确认；
    2. 页面导航使用 pageLoadStrategy=none + 0.12s 轮询，目标元素"后面已有兄弟元素"即视为解析完整，立即提取；
    3. CDP 屏蔽广告/统计域名（反爬与验证码域名不屏蔽）；
    4. 自适应限速：正常时间隔很短，触发验证码后自动放大间隔，成功后逐步恢复。

滑块自动验证（macOS）：
    检测到验证码 -> 将爬虫启动的 Chrome 窗口切到最前台 -> 屏幕模板匹配 marketwatch_verify.png
    -> 拟人化拖拽 -> 滑块消失即判定通过 -> 把终端切回最前台 -> 等待页面自动跳转后继续抓取。
    自动失败时退回手动模式（系统通知 + 等待 CAPTCHA_MANUAL_WAIT 秒），手动通过后同样切回终端。
    需要给终端授予「屏幕录制」「辅助功能」「自动化」权限。

防串页机制：
    1. 每次导航前在旧文档上打 window.__mwStalePage 标记；状态检测发现标记仍在（仍停留在旧页面）时只会继续等待；
    2. 历史表格页校验 URL 中的 symbol 段与目标一致（快速通道用 fetch 的最终 URL 校验）；
    3. 同一轮内数据指纹去重：与其它 symbol 数据完全相同即判定为串页，重试，仍相同则不写库。
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

# Sectors_empty.json 的跨进程锁（YF_Today 使用同一路径即可互斥；放在系统临时目录，不污染仓库）
JSON_LOCK_PATH = os.path.join(tempfile.gettempdir(), "Financial_System_Sectors_empty.lock")

# 波动偏差过大异常记录文件
WRONG_TXT_PATH = os.path.join(NEWS_DIR, "wrong.txt")
PRICE_DEVIATION_ALERT_THRESHOLD = 0.10  # 偏差超过 10% 记录到 wrong.txt

# 独立的浏览器 Profile（保存 Cookie，降低被反爬拦截概率；不要与正在运行的 Chrome 共用）
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
PAGE_LOAD_TIMEOUT = 30          # driver.get 超时
TABLE_WAIT_TIMEOUT = 15         # 等待历史表格出现的超时
QUOTE_WAIT_TIMEOUT = 15         # 等待行情价格出现的超时
POLL_INTERVAL = 0.12            # 页面状态轮询间隔（秒）
CAPTCHA_MANUAL_WAIT = 180       # 有界面模式下，等待手动完成验证码的最长时间
MAX_RETRIES = 3
MAX_CONSECUTIVE_BLOCKS = 3      # 连续被反爬拦截次数达到此值，终止整轮任务
BLOCK_BACKOFF_SECONDS = 10      # 被拦截后的退避基数（秒）
MAX_ROWS_TO_EXTRACT = 5         # 从表格顶部提取的行数（用于日期匹配）

# ---- 快速通道（页面内 fetch） ----
FAST_FETCH_ENABLED = True       # 总开关（命令行 --no-fast 可关闭）
FAST_FETCH_TIMEOUT = 12         # 单次 fetch 超时（秒）
FAST_FETCH_MAX_MISSES = 3       # 连续解析失败多少次后本轮停用快速通道（被反爬不计入）
FAST_FETCH_RENAV_EVERY = 60     # 每连续快速抓取多少个，正常导航一次以刷新宿主页面

# ---- 限速（自适应） ----
FETCH_DELAY_RANGE = (0.15, 0.5)   # 快速通道之间的随机间隔（秒）
NAV_DELAY_RANGE = (0.6, 1.4)      # 页面导航之间的随机间隔（秒）
THROTTLE_MAX_SCALE = 6.0          # 触发验证后间隔最多放大倍数
THROTTLE_DECAY = 0.85             # 每成功一次，放大倍数向 1 衰减

# ---- 资源屏蔽（仅广告/统计；反爬与验证码相关域名绝不屏蔽） ----
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

# 日期对不上时的策略："overwrite_date" / "skip"
STALE_DATA_POLICY = "skip"

# 价格合理性校验（仅对行情页分组生效）
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


class StalePageError(ScrapeError):
    """页面未完成跳转（仍停留在旧页面）或抓到的数据与其它 symbol 完全一致（串页）"""
    pass


class _NeverRaised(Exception):
    """占位异常：永远不会被抛出，仅用于 pyautogui 不可用时的兜底"""
    pass


# ================= 自适应限速 =================
class AdaptiveThrottle:
    def __init__(self):
        self.scale = 1.0

    def on_block(self):
        old = self.scale
        self.scale = min(THROTTLE_MAX_SCALE, max(2.0, self.scale * 2))
        if self.scale != old:
            tqdm.write(f"   🐢 触发反爬，后续请求间隔放大到 ×{self.scale:.1f}")

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
    """跨进程互斥锁（MW_Today / YF_Today 同时改 Sectors_empty.json 时防止互相覆盖）"""
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
        os.chmod(tmp_path, mode)   # mkstemp 默认 0600，保持原文件权限
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
    """严格小于 ref_date 的最近一个 NYSE 交易日 ('YYYY-MM-DD')"""
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
    if not USE_PERSISTENT_PROFILE:
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
    if not (USE_PERSISTENT_PROFILE and CLEAN_PROFILE_CACHE_ON_EXIT):
        return
    root = os.path.abspath(MW_PROFILE_DIR)
    if not os.path.isdir(root):
        return
    time.sleep(1)
    for sub in PROFILE_CACHE_SUBPATHS:
        p = os.path.join(root, *sub.split("/"))
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)


def create_driver(headless=True):
    options = webdriver.ChromeOptions()
    if os.path.exists(CHROME_BINARY_PATH):
        options.binary_location = CHROME_BINARY_PATH
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--lang=en-US')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--blink-settings=imagesEnabled=false')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-background-timer-throttling')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disk-cache-size=52428800')
    if USE_PERSISTENT_PROFILE:
        os.makedirs(MW_PROFILE_DIR, exist_ok=True)
        options.add_argument(f'--user-data-dir={os.path.abspath(MW_PROFILE_DIR)}')
    # none：driver.get 立即返回，由轮询判断目标元素是否已解析完整（不再等整页 DOMContentLoaded）
    options.page_load_strategy = 'none'

    driver = webdriver.Chrome(service=Service(executable_path=CHROME_DRIVER_PATH), options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.set_script_timeout(FAST_FETCH_TIMEOUT + 5)

    if not headless:
        try:
            driver.set_window_position(0, 0)
        except Exception:
            pass

    try:
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception:
        pass

    try:
        ua = driver.execute_script("return navigator.userAgent")
        if 'HeadlessChrome' in ua:
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                'userAgent': ua.replace('HeadlessChrome', 'Chrome'),
                'acceptLanguage': 'en-US,en;q=0.9',
            })
    except Exception:
        pass

    if BLOCK_AD_RESOURCES:
        try:
            driver.execute_cdp_cmd('Network.enable', {})
            driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': BLOCKED_URL_PATTERNS})
        except Exception:
            pass
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
    """
    防串页导航：先给旧文档打标记，再导航。新文档的 window 是全新的，标记自然消失；
    在新文档提交之前（pageLoadStrategy=none 下 get 立即返回）轮询到的都是带标记的旧文档 -> 'stale'，只会继续等待。
    """
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


# ================= 5. 页面解析 JS（同时适用于实时页面与 fetch 得到的离线文档） =================

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
// el 之后（在 maxDepth 层祖先范围内）已出现兄弟元素 -> HTML 解析器已越过 el，el 的内容一定完整
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
function mwIsCaptcha(doc, live) {
    if (doc.querySelector('iframe[src*="captcha-delivery.com"], iframe[src*="geo.captcha"]')) return true;
    // 已出现正常内容 -> 不是验证页（避免每次轮询都读 innerText 触发重排）
    if (doc.querySelector('.element--intraday, mw-downloaddata, .download-data, '
                        + 'table[aria-label="Historical Quotes data table"], h1[class*="company"]')) return false;
    return /access denied|you have been blocked|verify you are (a )?human|are you a robot/i
        .test(mwBodyText(doc, live));
}
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
    if (mwIsCaptcha(doc, live)) return 'captcha';
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
    if (mwIsCaptcha(doc, live)) return 'captcha';
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

# 快速通道：在已打开的 marketwatch.com 页面内 fetch 目标 HTML 并离线解析
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
            # 文档切换瞬间脚本上下文失效（document unloaded / Cannot find context）属正常现象，继续轮询
            if not is_driver_alive(driver):
                raise
            state = 'transient'

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
    """快速通道。返回 dict，state ∈ ready/captcha/notfound/mismatch/wrong_symbol/unparsed/http_error/error/need_nav"""
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
    if st == "captcha":
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
    # need_nav / notfound / mismatch / wrong_symbol：静默改走页面导航，由原流程确认


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
                if mode == "table":
                    wait_for_table(driver, TABLE_WAIT_TIMEOUT, headless, expect_seg=mw_path,
                                   captcha_solver=solver, on_captcha=throttle.on_block)
                    payload = driver.execute_script(EXTRACT_JS, MAX_ROWS_TO_EXTRACT)
                else:
                    wait_for_quote(driver, QUOTE_WAIT_TIMEOUT, headless, expect_type,
                                   captcha_solver=solver, on_captcha=throttle.on_block)
                    payload = driver.execute_script(QUOTE_EXTRACT_JS)

            ctx["consecutive_blocks"] = 0
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

        except CaptchaBlockedError as e:
            force_nav = True
            if headless and opts.get("escalate") and solver is not None and solver.ensure_ready():
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

            ctx["consecutive_blocks"] += 1
            tqdm.write(f"🛑 [{symbol}] 被反爬拦截 ({ctx['consecutive_blocks']}/{MAX_CONSECUTIVE_BLOCKS}): {e}")
            if ctx["consecutive_blocks"] >= MAX_CONSECUTIVE_BLOCKS:
                ctx["aborted"] = True
                return "failed", driver
            time.sleep(BLOCK_BACKOFF_SECONDS * attempt + random.uniform(0, 5))

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
                time.sleep(1.5 * attempt)
            else:
                tqdm.write(f"❌ [{symbol}] 抓取失败 (已重试 {MAX_RETRIES} 次): {str(e)[:150]}")
    return "failed", driver


def scrape_marketwatch(headless=True, only_groups=None, dry_run=False, sanity=True,
                       auto_slider=True, escalate=True, fast=True):
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

    captcha_solver = CaptchaAutoSolver(enabled=auto_slider and AUTO_SLIDER_ENABLED)
    fast_enabled = bool(fast and FAST_FETCH_ENABLED)

    tqdm.write(f"共加载 {len(task_list)} 个待抓取任务。（模式: {'无头' if headless else '有界面'}"
               f"{' | 快速通道' if fast_enabled else ' | 逐页导航'}"
               f"{' | DRY-RUN 不写库' if dry_run else ''}{' | 已关闭价格校验' if not sanity else ''}"
               f"{' | 滑块自动验证' if captcha_solver.enabled else ' | 滑块需手动'}）")

    prepare_profile_dir()
    try:
        driver = create_driver(headless)
    except Exception as e:
        tqdm.write(f"❌ Selenium 启动失败: {e}")
        if USE_PERSISTENT_PROFILE:
            tqdm.write(f"   提示：若提示 Profile 被占用，请关闭使用 {MW_PROFILE_DIR} 的浏览器进程。")
        empty_stats["failed"] = [f"{t[1]}:{t[0]}" for t in task_list]
        empty_stats["aborted"] = True
        return empty_stats

    if not headless:
        captcha_solver.activate_terminal()

    stats = {"success": [], "failed": [], "not_found": [], "skipped": [], "aborted": False}
    ctx = {"consecutive_blocks": 0, "aborted": False, "mismatch_hints": [], "fingerprints": {},
           "fast": {"enabled": fast_enabled, "misses": 0, "captchas": 0, "since_nav": 0},
           "throttle": AdaptiveThrottle(), "last_via": "nav", "via_count": {"fetch": 0, "nav": 0}}
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
                tqdm.write("🛑 连续被反爬拦截或浏览器无法恢复，终止本轮任务。")
                break

            if idx < len(task_list) - 1:
                ctx["throttle"].sleep(ctx["last_via"])
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
        tqdm.write(f"⏱️ 总耗时 {elapsed:.1f}s，平均 {elapsed / processed:.2f} 秒/个（含请求间隔）"
                   f" | ⚡快速通道 {vc['fetch']} 个 | 🌐页面导航 {vc['nav']} 个"
                   f"{' | 快速通道遇反爬 ' + str(ctx['fast']['captchas']) + ' 次' if ctx['fast']['captchas'] else ''}")
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
    parser.add_argument("--headful", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--groups", nargs="+", default=None, help="只抓取指定分组，例如 --groups Currencies Indices")
    parser.add_argument("--dry-run", action="store_true", help="只抓取并打印，不写数据库、不修改 JSON")
    parser.add_argument("--no-sanity", action="store_true", help="关闭价格偏差合理性校验")
    parser.add_argument("--no-check", action="store_true", help="结束后不调用 Check_yesterday.py")
    parser.add_argument("--no-auto-slider", action="store_true", help="关闭滑块自动验证（只能手动）")
    parser.add_argument("--no-escalate", action="store_true",
                        help="无头模式遇到验证码时不自动切换为有界面模式")
    parser.add_argument("--no-fast", action="store_true",
                        help="关闭快速通道（页面内 fetch），每个 symbol 都完整打开页面")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    start_caffeinate()
    exit_code = 0
    try:
        stats = scrape_marketwatch(headless=not args.headful, only_groups=args.groups,
                                   dry_run=args.dry_run, sanity=not args.no_sanity,
                                   auto_slider=not args.no_auto_slider, escalate=not args.no_escalate,
                                   fast=not args.no_fast)
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