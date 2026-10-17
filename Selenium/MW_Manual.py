# -*- coding: utf-8 -*-
"""
MW_Today.py  (已合并 MW_Manual.py)
从 MarketWatch 抓取数据写入 Finance.db（组名即表名）。两种模式共用同一套抓取引擎：

【Today 模式】（默认；不带任何手动参数）
    读取 Sectors_empty.json，抓取各分组最新一个有效开盘日的数据，写库，成功后从 JSON 移除该 symbol，
    全部清空后调用 Check_yesterday.py。
    python MW_Today.py                       # 默认无头（遇滑块自动切有界面并自动拖拽）
    python MW_Today.py --headful
    python MW_Today.py --groups ETFs Energy  # 只跑指定分组
    python MW_Today.py --dry-run             # 只抓取并打印，不写库、不改 JSON

【Manual 模式】（出现 --task / --symbol / --manual 任一即进入）
    手动指定 symbol + 日期，【强制覆盖】写入；不修改 JSON，不调用 Check_yesterday。
    - ETFs + 11 个股票分组：download-data 历史表格，可指定任意历史日期（可多个）
    - Bonds / Currencies / Crypto / Indices / Commodities：只能抓当前页面价格，只允许 1 个日期
    python MW_Today.py --task "AAPL:2026-09-18,2026-09-19" --task "SPY@ETFs:2026-09-10"
    python MW_Today.py --symbol AAPL --dates 2026-09-18 2026-09-19
    python MW_Today.py --task "S&P500:2026-09-19"      # 含 & 的名字务必加引号
    python MW_Today.py --manual                         # 使用文件顶部 MANUAL_TASKS
    python MW_Today.py --task "AAPL:2026-09-18" --dry-run --headful   # 首次建议先这样验证

通用参数: --headful/--headless --dry-run --no-sanity --strict-date --record-wrong/--no-record-wrong
          --no-auto-slider --no-escalate
Today 专用: --groups --no-check          Manual 专用: --group --yes --manual

防串页机制：
    1. 每次导航前先跳 about:blank，并在旧文档打 window.__mwStalePage 标记；检测到标记仍在只会继续等待；
    2. 历史表格页校验 URL 中的 symbol 段与目标一致；
    3. 同一轮内数据指纹去重：与其它 symbol 数据完全相同即判定为串页，重试，仍相同则不写库。

滑块自动验证（macOS）需要给终端授予「屏幕录制」「辅助功能」「自动化」权限。
"""
import argparse
import atexit
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
from collections import Counter

try:
    import pandas_market_calendars as mcal
except ImportError:  # 没装也能跑，退化为"前一个工作日"
    mcal = None
try:
    import fcntl  # 单实例锁（仅 macOS/Linux）
except ImportError:
    fcntl = None

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from tqdm import tqdm

# ================= 配置区域 =================
# Manual 模式不用命令行时，在这里填写，然后用 `--manual` 运行。group 可省略（自动判断）。
MANUAL_TASKS = [
    # {"symbol": "AAPL", "dates": ["2026-09-18", "2026-09-19"]},
    # {"symbol": "SPY", "group": "ETFs", "dates": ["2026-09-10"]},
    # {"symbol": "S&P500", "dates": ["2026-09-19"]},
]

USER_HOME = os.path.expanduser("~")
IS_MAC = platform.system() == 'Darwin'

BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_DIR = os.path.join(BASE_CODING_DIR, "News")

# 配置区
SLIDER_GUARD_STATE = os.path.join(NEWS_DIR, "slider_guard_mw.json")

DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
SECTORS_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_empty.json")
SYMBOL_MAPPING_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping.json")
MW_SYMBOL_OVERRIDE_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping_mw.json")
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

WRONG_TXT_PATH = os.path.join(NEWS_DIR, "wrong.txt")
PRICE_DEVIATION_ALERT_THRESHOLD = 0.10  # 偏差超过 10% 警告（并按设置记录到 wrong.txt）

TODAY_LOG_PATH = os.path.join(NEWS_DIR, "MW_Today.log")
MANUAL_LOG_PATH = os.path.join(NEWS_DIR, "MW_Manual.log")
LOG_MAX_BYTES = 5 * 1024 * 1024  # 超过则轮转为 .1，防止日志无限增长

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

# ---- 抓取参数 ----
MW_BASE_URL = "https://www.marketwatch.com/investing"
PAGE_LOAD_TIMEOUT = 30
TABLE_WAIT_TIMEOUT = 15
QUOTE_WAIT_TIMEOUT = 15
CAPTCHA_MANUAL_WAIT = 180
MAX_RETRIES = 3
MAX_CONSECUTIVE_BLOCKS = 3
BLOCK_BACKOFF_SECONDS = 10
REQUEST_DELAY_RANGE = (2.0, 4.5)
MAX_ROWS_TO_EXTRACT = 5       # Today：从表格顶部提取的行数（用于日期匹配）
MAX_TABLE_ROWS = 500          # Manual：单页最多提取行数
FINGERPRINT_ROWS = 5          # 防串页指纹取表格前 N 行

# ---- Manual 历史窗口参数 ----
WINDOW_MAX_SPAN_DAYS = 90     # 多个日期合并成一个请求窗口的最大跨度
WINDOW_PADDING_DAYS = 1       # 窗口两端各多取 1 天，防止边界 off-by-one

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

# Today 模式日期对不上时的策略： "overwrite_date" 取最新数据改成目标日期写入 / "skip" 不写入
STALE_DATA_POLICY = "overwrite_date"

# 行情页分组价格合理性校验：与库中上一条价格偏差超阈值
PRICE_SANITY_THRESHOLD = 0.25
PRICE_SANITY_ACTION = "skip"    # "skip" 不写入 / "warn" 仅提示仍写入

STALE_PAGE_MARKER = "__mwStalePage"

ASSET_PATH_TO_BODY_TYPE = {
    "stock": "stock", "fund": "fund", "bond": "bond", "currency": "currency",
    "cryptocurrency": "cryptocurrency", "index": "index", "future": "future",
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
    "Currencies": {"DXY": "index/dxy"},
    "Indices": {
        "NASDAQ": "comp", "VIX": "vix", "Brazil": "bvsp?countrycode=br",
        "Nikkei": "nik?countrycode=jp", "Russell": "rut", "S&P500": "spx",
        "Korea": "180721?countrycode=kr", "DowJones": "djia",
        "HANGSENG": "hsi?countrycode=hk", "Shanghai": "shcomp?countrycode=cn",
        "EURO50": "sx5e?countrycode=xx", "Singapore": "sti?countrycode=sg",
        "India": "1?countrycode=in",
    },
    "Commodities": {
        "Huangjin": "gc00", "Silver": "si00", "Copper": "hg00", "Platinum": "pl00",
        "Naturalgas": "ng00", "CrudeOil": "cl00", "Brent": "brn00?countrycode=uk",
        "YuMi": "c00", "Soybean": "s00", "Oat": "o00", "Rice": "rr00",
        "LeanHogs": "lh00", "LiveCattle": "lc00",
    },
}

TABLE_COLS = ["date", "name", "price", "volume", "open", "high", "low"]
OK_STATUSES = {"inserted", "updated", "dry-run"}


# ================= 异常 =================
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


# ================= 日志 =================
_LOG_FILE = None


def init_logging(path):
    global _LOG_FILE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > LOG_MAX_BYTES:
            os.replace(path, path + ".1")
        _LOG_FILE = path
    except OSError:
        _LOG_FILE = None


def log(msg):
    tqdm.write(msg)
    if _LOG_FILE:
        try:
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
        except OSError:
            pass


# ================= 防休眠 / 单实例锁 =================
_caffeinate_proc = None
_lock_fh = None


def start_caffeinate():
    global _caffeinate_proc
    if IS_MAC and _caffeinate_proc is None:
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


def acquire_run_lock():
    """同一 Profile 同时只允许一个实例（避免 Today 与 Manual 抢 Profile / 同时写库）"""
    global _lock_fh
    if fcntl is None:
        return True
    path = os.path.abspath(MW_PROFILE_DIR) + ".lock"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _lock_fh = open(path, "w")
    except OSError:
        return True  # 无法创建锁文件时不阻塞运行
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


# ================= 1. 数据库 =================
def get_table_type(sector):
    if sector == 'ETFs' or sector in STOCK_SECTORS or sector == 'Crypto':
        return "expanded"
    if sector in ('Bonds', 'Currencies', 'Commodities', 'Economics'):
        return "no_volume"
    return "standard"


def create_table_if_not_exists(cursor, table_name, table_type):
    t = f'"{table_name}"'
    if table_type == "expanded":
        cursor.execute(f'''CREATE TABLE IF NOT EXISTS {t} (
            date TEXT, name TEXT, price REAL, volume INTEGER,
            open REAL, high REAL, low REAL, UNIQUE(date, name))''')
    elif table_type == "no_volume":
        cursor.execute(f'''CREATE TABLE IF NOT EXISTS {t} (
            date TEXT, name TEXT, price REAL, UNIQUE(date, name))''')
    else:
        cursor.execute(f'''CREATE TABLE IF NOT EXISTS {t} (
            date TEXT, name TEXT, price REAL, volume INTEGER, UNIQUE(date, name))''')


def _assert_known_table(table):
    """表名只允许来自白名单，杜绝 SQL 拼接风险"""
    if table not in SECTOR_HANDLERS:
        raise ValueError(f"非法表名: {table}")


def read_existing(table, name, date_str):
    _assert_known_table(table)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        try:
            cur = conn.execute(f'SELECT * FROM "{table}" WHERE name = ? AND date = ?', (name, date_str))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def write_row(table, row):
    """
    统一写入（两种模式共用）：同一个 IMMEDIATE 事务内 DELETE 同 (date,name) 的全部行 + INSERT。
    不依赖表上是否存在 UNIQUE 约束；按表的真实列写入。返回 (ok, old_rows, err)
    """
    _assert_known_table(table)
    values = dict(zip(TABLE_COLS, row))
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    try:
        create_table_if_not_exists(conn.cursor(), table, get_table_type(table))
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        for need in ("date", "name", "price"):
            if need not in cols:
                raise sqlite3.Error(f"表 {table} 缺少必要列 {need}")
        use = [c for c in TABLE_COLS if c in cols]
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(f'SELECT * FROM "{table}" WHERE name = ? AND date = ?',
                           (values["name"], values["date"]))
        names = [d[0] for d in cur.description]
        old_rows = [dict(zip(names, r)) for r in cur.fetchall()]
        conn.execute(f'DELETE FROM "{table}" WHERE name = ? AND date = ?',
                     (values["name"], values["date"]))
        conn.execute(
            f'INSERT INTO "{table}" ({",".join(use)}) VALUES ({",".join("?" * len(use))})',
            [values[c] for c in use])
        conn.commit()
        return True, old_rows, None
    except sqlite3.Error as e:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return False, [], str(e)
    finally:
        conn.close()


def get_last_db_price(table, name, before_date):
    _assert_known_table(table)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        try:
            r = conn.execute(
                f'SELECT price FROM "{table}" WHERE name = ? AND date < ? AND price IS NOT NULL '
                f'ORDER BY date DESC LIMIT 1', (name, before_date)).fetchone()
            return float(r[0]) if r and r[0] is not None else None
        finally:
            conn.close()
    except (sqlite3.Error, ValueError, TypeError):
        return None


_RECORDED_WRONG = set()


def check_price_jump(group, symbol, date_str, price, record_wrong, dry_run):
    """与库中前一条价格比较，偏差 >10% 警告；record_wrong 时追加 symbol 到 wrong.txt"""
    prev = get_last_db_price(group, symbol, date_str)
    if prev is None or abs(prev) < 1e-8:
        return
    diff = (price - prev) / abs(prev)
    if abs(diff) <= PRICE_DEVIATION_ALERT_THRESHOLD:
        return
    log(f"🚨 [{symbol}] ({group}) {date_str} 价格与前一条偏差超 10%: {prev} -> {price} ({diff:+.2%})")
    key = (group, symbol, date_str)
    if not record_wrong or key in _RECORDED_WRONG:
        return
    _RECORDED_WRONG.add(key)
    if dry_run:
        log(f"   🔍 [DRY-RUN] 模拟追加 [{symbol}] 到: {WRONG_TXT_PATH}")
        return
    try:
        os.makedirs(NEWS_DIR, exist_ok=True)
        with open(WRONG_TXT_PATH, "a", encoding="utf-8") as f:
            f.write(f"{symbol}\n")
        log(f"   📝 已追加 [{symbol}] 到 {WRONG_TXT_PATH}")
    except OSError as e:
        log(f"❌ 写入 wrong.txt 失败: {e}")


def check_price_sanity(table, name, date_str, price):
    prev = get_last_db_price(table, name, date_str)
    if prev is None or prev == 0:
        return True, None
    dev = abs(price - prev) / abs(prev)
    if dev > PRICE_SANITY_THRESHOLD:
        return False, f"价格 {price} 与库中上一条 {prev} 偏差 {dev:.1%}，超过阈值 {PRICE_SANITY_THRESHOLD:.0%}"
    return True, None


# ================= 2. JSON / 映射 =================
def load_json_file(path, desc="JSON"):
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f"⚠️ 读取{desc}出错 ({path}): {e}")
        return None


def load_alias_mapping(path):
    m = load_json_file(path, "映射文件")
    return {v: k for k, v in m.items()} if isinstance(m, dict) else {}


def load_mw_overrides(path):
    d = load_json_file(path, "MW 覆盖映射")
    return d if isinstance(d, dict) else {}


def atomic_write_json(json_path, data):
    dir_name = os.path.dirname(json_path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, json_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def remove_symbol_from_json(json_path, group_name, symbol):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if group_name in data and symbol in data[group_name]:
            data[group_name] = [s for s in data[group_name] if s != symbol]
            atomic_write_json(json_path, data)
            return True
    except Exception as e:
        log(f"⚠️ 更新 JSON 失败 [{symbol}]: {e}")
    return False


# ================= 3. 日期 / 交易日 =================
def get_prev_trading_date(ref_date):
    """严格小于 ref_date 的最近一个 NYSE 交易日 ('YYYY-MM-DD')"""
    try:
        if mcal is not None:
            sched = mcal.get_calendar('NYSE').schedule(
                start_date=ref_date - datetime.timedelta(days=15), end_date=ref_date)
            past = [d for d in sched.index.date if d < ref_date]
            if past:
                return past[-1].strftime('%Y-%m-%d')
    except Exception as e:
        log(f"⚠️ 计算交易日失败（退化为前一个工作日）: {e}")
    d = ref_date - datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d.strftime('%Y-%m-%d')


def get_last_valid_trading_date():
    try:
        return get_prev_trading_date(datetime.date.today())
    except Exception as e:
        log(f"⚠️ 计算交易日失败: {e}")
        return None


def nyse_trading_days(start, end):
    """返回 {'YYYY-MM-DD'}；失败返回 None"""
    if mcal is None:
        return None
    try:
        sched = mcal.get_calendar('NYSE').schedule(start_date=start, end_date=end)
        return {d.strftime('%Y-%m-%d') for d in sched.index.date}
    except Exception:
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


def fmt_mw_date(d):
    return f"{d.month:02d}/{d.day:02d}/{d.year}"


def normalize_dates(raw_dates, today):
    good, errors = [], []
    for s in raw_dates:
        try:
            d = datetime.datetime.strptime(str(s).strip(), "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"日期格式无效: '{s}'（应为 YYYY-MM-DD）")
            continue
        if d > today:
            errors.append(f"日期 {d} 晚于今天 {today}，不可能有数据")
            continue
        good.append(d.isoformat())
    return sorted(set(good)), errors


def build_windows(iso_dates):
    """把排序后的日期按最大跨度切成窗口: list[list[date]]"""
    windows = []
    for s in iso_dates:
        d = datetime.date.fromisoformat(s)
        if windows and (d - windows[-1][0]).days <= WINDOW_MAX_SPAN_DAYS:
            windows[-1].append(d)
        else:
            windows.append([d])
    return windows


# ================= 4. Symbol -> URL =================
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
                log(f"⚠️ 映射值 '{v}' 中的品种类型 '{asset}' 不在已知列表 "
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
        key = (asset or handler['asset_path'], path, tuple(sorted(q.items())))
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
    url = (f"{MW_BASE_URL}/{asset or handler['asset_path']}/"
           f"{urllib.parse.quote(mw_path, safe='.')}{handler.get('suffix', '')}")
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


# ================= 5. 浏览器 =================
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
                log(f">>> [Profile] 已将旧浏览器 Profile 迁移到仓库外: {legacy} -> {target}")
                _remove_dir_if_empty(os.path.dirname(legacy))
            except Exception as e:
                log(f"⚠️ [Profile] 迁移旧 Profile 失败: {e}")
        else:
            log(f"⚠️ [Profile] 发现遗留的旧 Profile 目录，可手动删除: {legacy}")
    os.makedirs(target, exist_ok=True)
    git_root = _find_git_root(target)
    if git_root:
        log(f"⚠️ [Profile] 浏览器 Profile 目录位于 Git 仓库 {git_root} 内，"
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
    # 有界面模式下 Chrome 常被终端窗口遮挡：禁止对被遮挡/后台窗口降频，避免页面"加载不完"
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
    options.page_load_strategy = 'eager'

    driver = webdriver.Chrome(service=Service(executable_path=CHROME_DRIVER_PATH), options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

    if not headless:
        # 固定到主屏左上角：截屏只截主屏，窗口跑到副屏会导致滑块永远识别不到
        try:
            driver.set_window_position(0, 0)
        except Exception:
            pass
    try:
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"})
    except Exception:
        pass
    try:
        ua = driver.execute_script("return navigator.userAgent")
        if 'HeadlessChrome' in ua:
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                'userAgent': ua.replace('HeadlessChrome', 'Chrome'),
                'acceptLanguage': 'en-US,en;q=0.9'})
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
    """防串页导航：旧文档打标记 -> about:blank -> 再打标记 -> 目标 URL。
    若导航被 window.stop() 取消，页面停留在带标记的旧文档上，状态检测会识别为 stale。"""
    _mark_current_document_stale(driver)
    try:
        driver.get("about:blank")
    except WebDriverException:
        pass
    _mark_current_document_stale(driver)
    try:
        driver.get(url)
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except WebDriverException:
            pass


def detect_body_symbol_type(driver):
    try:
        bc = driver.execute_script("return document.body ? (document.body.className || '') : '';") or ''
    except WebDriverException:
        return None
    m = re.search(r'(?:^|\s)symbol--([a-z0-9_-]+)', bc, re.I)
    return m.group(1).lower() if m else None


# ================= 5.5 滑块自动验证（macOS） =================
_TERM_PROGRAM_APPS = {
    "Apple_Terminal": "Terminal", "iTerm.app": "iTerm", "vscode": "Visual Studio Code",
    "WarpTerminal": "Warp", "ghostty": "Ghostty", "WezTerm": "WezTerm", "Hyper": "Hyper",
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
    """切换窗口（浏览器 <-> 终端）、调用 Slider_Verify 识别并拖拽滑块、手动兜底提醒。
    Slider_Verify 延迟到第一次需要时才加载。"""

    def __init__(self, enabled=True):
        self.enabled = bool(enabled) and IS_MAC
        if enabled and not IS_MAC:
            log("⚠️ 滑块自动验证仅支持 macOS，已关闭。")
        self._sv = None
        self._solver = None
        self._init_failed = False
        self._browser_activated = False
        self._pid_cache = {}
        self.chrome_app_name = _mac_app_name_from_binary(CHROME_BINARY_PATH)
        self.stats = {"solved": 0, "failed": 0, "manual": 0}

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
                GuardPolicy = getattr(sv, "GuardPolicy", None)   # 兼容旧版
                guard = GuardPolicy(
                    max_consecutive_failures=2, cooldown_minutes=30,
                    max_per_hour=30, max_per_day=100,
                    min_interval_seconds=0,                      # MW 场景下关闭"过密"判断
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
            log(f"🧩 滑块模块已加载（模板 {solver.template_path}，屏幕缩放 {solver.scale:.2f}）")
            return solver
        except Exception as e:
            self._init_failed = True
            self.enabled = False
            log(f"⚠️ 滑块自动验证不可用，将退回手动处理: {e}")
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
        """把爬虫启动的 Chrome Beta 切到最前台（优先按进程号，避免误切到你自己开的 Chrome Beta）"""
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
                log(f"   ⚠️ 按进程号切换浏览器失败（{msg[:120]}），改用应用名激活")
        if not ok:
            ok, msg = _osascript(f'tell application "{self.chrome_app_name}" to activate')
            if not ok:
                log(f"   ⚠️ 激活 {self.chrome_app_name} 失败: {msg[:120]}")
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
            log(f"   ⚠️ 切回终端 {name} 失败: {msg[:120]}")
        return ok

    def restore_terminal(self):
        if not self._browser_activated:
            return
        self._browser_activated = False
        time.sleep(0.3)
        if self.activate_terminal():
            log("   🖥️ 已将终端切回前台")

    def alert_manual(self, driver):
        self.stats["manual"] += 1
        if not IS_MAC:
            return
        self.activate_browser(driver)
        _osascript('display notification "MarketWatch 需要人工完成验证，请切到 Chrome 窗口处理" '
                   'with title "MW_Today" sound name "Glass"')

    def try_solve(self, driver, is_captcha_fn):
        """返回: solved / passed / not_found / failed / aborted / unavailable"""
        solver = self._get_solver()
        guard = getattr(solver, "guard", None)
        if guard is not None:
            allowed, reason = guard.allow()
            if not allowed:
                tqdm.write(f"   ⏸️ 自动拖拽被保护器暂停：{reason}，转手动处理")
                self.enabled = False          # 本轮后续验证码直接走手动
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
                log("   ✅ 验证页已自行消失")
                self.restore_terminal()
                return "passed"
            log(f"   ❓ {SLIDER_APPEAR_TIMEOUT}s 内屏幕上未找到滑块"
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
        except self._sv.pyautogui.FailSafeException:
            log("   ✋ 检测到鼠标甩到屏幕角落（FailSafe），本轮运行停用自动拖拽，请手动完成。")
            self.enabled = False
            return "aborted"
        except Exception as e:
            log(f"   ❌ 拖拽过程异常: {e}")
            self.stats["failed"] += 1
            return "failed"

        if res.solved:
            self.stats["solved"] += 1
            log(f"   ✅ 滑块验证已通过（拖拽 {res.attempts} 次）")
            self.restore_terminal()
            return "solved"
        self.stats["failed"] += 1
        log(f"   ❌ 滑块验证未通过: {res.message}")
        return "failed"

    def summary(self):
        s = self.stats
        if any(s.values()):
            return f"🧩 滑块验证：自动通过 {s['solved']} | 自动失败 {s['failed']} | 转手动 {s['manual']}"
        return None


# ================= 6. 页面解析 JS =================
JS_COMMON = r"""
function mwIsStale() {
    try { if (window.__mwStalePage) return true; } catch (e) {}
    return location.protocol === 'about:' || location.href === 'about:blank';
}
function mwCellText(el) {
    if (!el) return '';
    const d = el.querySelector('div');
    return ((d ? d.textContent : el.textContent) || '').replace(/\s+/g, ' ').trim();
}
function mwFindTable() {
    let t = document.querySelector('table[aria-label="Historical Quotes data table"]');
    if (t) return t;
    for (const cand of document.querySelectorAll('.download-data table, mw-downloaddata table, table')) {
        const hs = Array.from(cand.querySelectorAll('thead th')).map(th => mwCellText(th).toLowerCase());
        if (hs.includes('date') && hs.includes('close')) return cand;
    }
    return null;
}
function mwIsCaptcha() {
    const txt = (document.body ? document.body.innerText : '').slice(0, 3000);
    if (document.querySelector('iframe[src*="captcha-delivery.com"], iframe[src*="geo.captcha"]')) return true;
    return /access denied|you have been blocked|verify you are (a )?human|are you a robot/i.test(txt);
}
function mwPathSymbolSeg() {
    const segs = location.pathname.toLowerCase().split('/').filter(Boolean);
    let seg = segs.length > 2 ? segs[2] : '';
    try { seg = decodeURIComponent(seg); } catch (e) {}
    return seg;
}
"""

CAPTCHA_CHECK_JS = JS_COMMON + r"""
return mwIsCaptcha();
"""

PAGE_STATE_JS = JS_COMMON + r"""
const expectSeg = (arguments[0] || '').toLowerCase();
if (mwIsStale()) return 'stale';
const txt = (document.body ? document.body.innerText : '').slice(0, 3000);
if (mwIsCaptcha()) return 'captcha';
if (!location.pathname.toLowerCase().includes('download-data')) return 'notfound';
if (expectSeg && mwPathSymbolSeg() !== expectSeg) return 'wrong_symbol';
const tbl = mwFindTable();
if (tbl && tbl.querySelectorAll('tbody tr').length > 0) return 'ready';
if (/symbol lookup|no results found|there were no matches/i.test(txt)) return 'notfound';
return 'loading';
"""

EXTRACT_JS = JS_COMMON + r"""
const maxRows = arguments[0] || 5;
if (mwIsStale()) return { stale: true };
const tbl = mwFindTable();
if (!tbl) return { error: '未找到数据表格' };

const headers = Array.from(tbl.querySelectorAll('thead th')).map(th => mwCellText(th).toLowerCase());
const idx = n => headers.indexOf(n);
const cols = { date: idx('date'), open: idx('open'), high: idx('high'),
               low: idx('low'), close: idx('close'), volume: idx('volume') };
if (cols.date < 0 || cols.close < 0) return { error: '表头解析失败: ' + headers.join('|') };

function num(s) {
    if (!s) return null;
    s = s.replace(/[$,\s]/g, '');
    if (!s || s === '-' || /^n\/?a$/i.test(s)) return null;
    const v = parseFloat(s);
    return isNaN(v) ? null : v;
}
function vol(s) {
    if (!s) return null;
    s = s.replace(/[,\s]/g, '').toUpperCase();
    const m = s.match(/^([\d.]+)([KMB])?$/);
    if (!m) return null;
    let v = parseFloat(m[1]);
    if (m[2]) v *= { K: 1e3, M: 1e6, B: 1e9 }[m[2]];
    return Math.round(v);
}

const out = [];
for (const tr of tbl.querySelectorAll('tbody tr')) {
    const cells = tr.querySelectorAll('td');
    if (cells.length <= Math.max(cols.date, cols.close)) continue;
    const m = mwCellText(cells[cols.date]).match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (!m) continue;
    const dateStr = `${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
    const g = k => (cols[k] >= 0 && cells[cols[k]]) ? mwCellText(cells[cols[k]]) : '';
    const close = num(g('close'));
    if (close === null) continue;
    out.push([dateStr, close, vol(g('volume')), num(g('open')), num(g('high')), num(g('low'))]);
    if (out.length >= maxRows) break;
}
return { data: out, path_seg: mwPathSymbolSeg(), url: location.href };
"""

QUOTE_COMMON_JS = JS_COMMON + r"""
function qText(el) { return el ? (el.textContent || '').replace(/\s+/g, ' ').trim() : ''; }
function qNum(s) {
    if (s === null || s === undefined) return null;
    s = String(s).replace(/[\u2212\u2013]/g, '-').replace(/[^0-9.\-]/g, '');
    if (!s || s === '-' || s === '.') return null;
    const v = parseFloat(s);
    return isFinite(v) ? v : null;
}
function qScope() { return document.querySelector('.element--intraday') || document; }
function qPrice() {
    const scope = qScope();
    const h2 = scope.querySelector('h2[class*="intraday"][class*="price"]')
            || document.querySelector('h2[class*="intraday"][class*="price"]');
    if (h2) {
        const bq = h2.querySelector('bg-quote[field="Last" i]') || h2.querySelector('bg-quote:not([class*="change"])');
        if (bq) {
            const raw = bq.getAttribute('data-last-raw');
            let v = qNum(raw);
            if (v !== null) return { raw: raw, value: v, src: 'data-last-raw' };
            const t = qText(bq);
            v = qNum(t);
            if (v !== null) return { raw: t, value: v, src: 'bg-quote' };
        }
        const clone = h2.cloneNode(true);
        clone.querySelectorAll('sup').forEach(s => s.remove());
        const t = qText(clone);
        const v = qNum(t);
        if (v !== null) return { raw: t, value: v, src: 'h2' };
    }
    const meta = document.querySelector('meta[name="price"]');
    if (meta) {
        const c = meta.getAttribute('content');
        const v = qNum(c);
        if (v !== null) return { raw: c, value: v, src: 'meta' };
    }
    return { raw: null, value: null, src: null };
}
function qTimestamp() {
    const scope = qScope();
    let t = qText(scope.querySelector('bg-quote[field="date" i]'));
    if (!t) t = qText(scope.querySelector('[class*="timestamp"][class*="time"]'));
    if (!t) {
        const m = document.querySelector('meta[name="quoteTime"]');
        if (m) t = m.getAttribute('content') || '';
    }
    return t;
}
"""

QUOTE_STATE_JS = QUOTE_COMMON_JS + r"""
const expectType = arguments[0];
if (mwIsStale()) return 'stale';
const txt = (document.body ? document.body.innerText : '').slice(0, 3000);
if (mwIsCaptcha()) return 'captcha';
const path = location.pathname.toLowerCase();
if (path.includes('/search') || path === '/' || path === '/investing' || path === '/investing/') return 'notfound';
const bc = document.body ? (document.body.className || '') : '';
if (expectType && /(^|\s)symbol--/.test(bc)
    && !new RegExp('(^|\\s)symbol--' + expectType + '(\\s|$)').test(bc)) return 'mismatch';
if (qPrice().value !== null) return 'ready';
if (/symbol lookup|no results found|there were no matches/i.test(txt)) return 'notfound';
return 'loading';
"""

QUOTE_EXTRACT_JS = QUOTE_COMMON_JS + r"""
if (mwIsStale()) return { stale: true };
const p = qPrice();
const st = qScope().querySelector('small[class*="status"]');
return {
    price: p.value, price_raw: p.raw, price_src: p.src,
    ts: qTimestamp(),
    status: qText(st),
    company: qText(document.querySelector('h1[class*="company"]')),
    body_class: document.body ? (document.body.className || '') : '',
    url: location.href
};
"""


def _is_captcha_now(driver):
    """页面跳转中脚本执行失败时按"仍在验证"处理，宁可多等也不误判"""
    try:
        return bool(driver.execute_script(CAPTCHA_CHECK_JS))
    except WebDriverException:
        return True


def _wait_loop(driver, timeout, headless, state_fn, timeout_msg, expect_type=None, expect_seg=None,
               captcha_solver=None):
    deadline = time.time() + timeout
    manual_mode = False
    auto_rounds = 0
    solved_at = None
    refreshed = False
    seen_captcha = False

    while True:
        state = state_fn()

        if seen_captcha and state != 'captcha':
            seen_captcha = False
            if captcha_solver:
                captcha_solver.restore_terminal()
            if manual_mode:
                log("   ✅ 验证已完成，继续抓取")

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
            if headless:
                raise CaptchaBlockedError("触发反爬验证（无头模式无法处理）")
            seen_captcha = True
            now = time.time()
            auto_ok = captcha_solver is not None and captcha_solver.enabled and not manual_mode

            if auto_ok and solved_at is not None:
                elapsed = now - solved_at
                if elapsed >= CAPTCHA_POST_SOLVE_REFRESH_AFTER and not refreshed:
                    refreshed = True
                    log("   🔄 滑块已通过但页面未跳转，主动刷新一次...")
                    try:
                        driver.refresh()
                    except WebDriverException:
                        pass
                elif elapsed >= CAPTCHA_POST_SOLVE_WAIT:
                    log("   ⚠️ 刷新后仍为验证页，可能出现了新一轮验证")
                    solved_at = None
            elif auto_ok and auto_rounds < AUTO_SLIDER_MAX_ROUNDS:
                auto_rounds += 1
                log(f"🧩 检测到滑块验证，开始自动处理（第 {auto_rounds}/{AUTO_SLIDER_MAX_ROUNDS} 轮）...")
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
                log(f"🧩 检测到验证码，请在浏览器窗口中手动完成（最多等待 {CAPTCHA_MANUAL_WAIT} 秒）...")
                deadline = time.time() + CAPTCHA_MANUAL_WAIT

        if time.time() > deadline:
            if state == 'captcha':
                raise CaptchaBlockedError("验证码等待超时")
            if state == 'stale':
                raise StalePageError("页面未完成跳转，仍停留在旧页面（导航超时被中止）")
            raise ScrapeError(timeout_msg)
        time.sleep(0.5)


def wait_for_table(driver, timeout, headless, expect_seg=None, captcha_solver=None):
    _wait_loop(driver, timeout, headless,
               lambda: driver.execute_script(PAGE_STATE_JS, (expect_seg or "").lower()),
               "等待数据表格超时（该日期窗口可能没有任何交易数据）",
               expect_seg=expect_seg, captcha_solver=captcha_solver)


def extract_rows(driver, max_rows, expect_seg=None):
    """返回 [(date, price, volume, open, high, low)]，按日期降序"""
    result = driver.execute_script(EXTRACT_JS, max_rows)
    if not isinstance(result, dict):
        raise ScrapeError("JS 返回结果异常")
    if result.get("stale"):
        raise StalePageError("提取时检测到仍为旧页面")
    if "error" in result:
        raise ScrapeError(result["error"])
    if expect_seg and (result.get("path_seg") or "") != expect_seg.lower():
        raise StalePageError(f"提取时页面代码为 '{result.get('path_seg')}'，与预期 '{expect_seg}' 不符: "
                             f"{result.get('url')}")
    rows = []
    for date_str, price, volume, o, h, l in result.get("data", []):
        if price is None or price <= 0:
            continue
        rows.append((date_str, float(price), int(volume) if volume is not None else 0, o, h, l))
    rows.sort(key=lambda x: x[0], reverse=True)
    return rows


def wait_for_quote(driver, timeout, headless, expect_type, captcha_solver=None):
    _wait_loop(driver, timeout, headless,
               lambda: driver.execute_script(QUOTE_STATE_JS, expect_type or ""), "等待行情价格超时",
               expect_type=expect_type, captcha_solver=captcha_solver)


def extract_quote(driver):
    r = driver.execute_script(QUOTE_EXTRACT_JS)
    if not isinstance(r, dict):
        raise ScrapeError("JS 返回结果异常")
    if r.get("stale"):
        raise StalePageError("提取时检测到仍为旧页面")
    if r.get("price") is None:
        raise ScrapeError("未解析到价格")
    return r


# ================= 7. 防串页：数据指纹 =================
def table_fingerprint(rows):
    return ("table",) + tuple(rows[:FINGERPRINT_ROWS])


def quote_fingerprint(quote):
    return ("quote", quote.get("company") or "", str(quote.get("price_raw")), quote.get("ts") or "")


def check_and_register_fingerprint(ctx, fp, symbol, group):
    owner = ctx["fingerprints"].get(fp)
    if owner and owner != (group, symbol):
        raise StalePageError(f"抓到的数据与 [{owner[1]}]({owner[0]}) 完全相同，疑似串页（页面未切换）")
    ctx["fingerprints"][fp] = (group, symbol)


# ================= 8. 抓取核心（两种模式共用） =================
def fetch_page(ctx, job, url, expect_type=None, expect_seg=None, max_rows=MAX_ROWS_TO_EXTRACT):
    """返回 (status, payload)；status: ok / not_found / failed。浏览器句柄保存在 ctx['driver']"""
    handler, symbol, group = job["handler"], job["symbol"], job["group"]
    solver = ctx["solver"]
    last_err = ""
    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        driver = ctx["driver"]
        if driver is None:
            ctx["aborted"] = True
            return "failed", "浏览器不可用"
        headless = ctx["headless"]  # 每次重试都读取最新模式（可能已从无头切换为有界面）
        try:
            load_page(driver, url)
            if handler["parser"] == "ohlcv_table":
                wait_for_table(driver, TABLE_WAIT_TIMEOUT, headless, expect_seg=expect_seg,
                               captcha_solver=solver)
                ctx["consecutive_blocks"] = 0
                rows = extract_rows(driver, max_rows, expect_seg=expect_seg)
                if not rows:
                    raise ScrapeError("提取到的数据为空")
                check_and_register_fingerprint(ctx, table_fingerprint(rows), symbol, group)
                return "ok", rows

            wait_for_quote(driver, QUOTE_WAIT_TIMEOUT, headless, expect_type, captcha_solver=solver)
            ctx["consecutive_blocks"] = 0
            quote = extract_quote(driver)
            check_and_register_fingerprint(ctx, quote_fingerprint(quote), symbol, group)
            return "ok", quote

        except SymbolNotFoundError as e:
            log(f"❓ [{symbol}] MarketWatch 未找到: {str(e)[:200]}")
            if e.actual_type:
                hint = suggest_override_from_url(e.final_url)
                if hint:
                    ctx["mismatch_hints"].append(hint)
            return "not_found", str(e)[:200]

        except CaptchaBlockedError as e:
            last_err = str(e)
            # 无头模式无法拖滑块：用同一 Profile 重启为有界面模式，本次不计入重试次数
            if headless and ctx["escalate"] and solver.ensure_ready():
                log(f"🔁 [{symbol}] 无头模式触发验证，切换为有界面模式以自动拖拽滑块...")
                safe_quit(driver)
                time.sleep(1.5)  # 等待 Profile 锁释放
                try:
                    ctx["driver"] = create_driver(headless=False)
                except Exception as ce:
                    log(f"❌ 有界面浏览器启动失败: {ce}")
                    ctx["driver"] = None
                    ctx["aborted"] = True
                    return "failed", f"有界面浏览器启动失败: {ce}"
                ctx["headless"] = False
                solver.activate_terminal()
                attempt -= 1
                continue
            ctx["consecutive_blocks"] += 1
            log(f"🛑 [{symbol}] 被反爬拦截 ({ctx['consecutive_blocks']}/{MAX_CONSECUTIVE_BLOCKS}): {e}")
            if ctx["consecutive_blocks"] >= MAX_CONSECUTIVE_BLOCKS:
                ctx["aborted"] = True
                return "failed", last_err
            time.sleep(BLOCK_BACKOFF_SECONDS * attempt + random.uniform(0, 5))

        except StalePageError as e:
            last_err = str(e)[:150]
            if attempt < MAX_RETRIES:
                log(f"⏳ [{symbol}] {e}，重新加载 ({attempt}/{MAX_RETRIES})...")
                time.sleep(2 * attempt + random.uniform(0, 2))
            else:
                log(f"❌ [{symbol}] 防串页校验未通过 (已重试 {MAX_RETRIES} 次)，不写入: {e}")

        except Exception as e:
            last_err = str(e)[:150]
            if isinstance(e, WebDriverException) and not is_driver_alive(driver):
                log("♻️ 浏览器会话已失效，正在重建...")
                safe_quit(driver)
                try:
                    ctx["driver"] = create_driver(ctx["headless"])
                except Exception as ce:
                    log(f"❌ 浏览器重建失败: {ce}")
                    ctx["driver"] = None
                    ctx["aborted"] = True
                    return "failed", f"浏览器重建失败: {ce}"
            if attempt < MAX_RETRIES:
                log(f"⏳ [{symbol}] 第 {attempt} 次抓取出错，准备重试: {last_err[:120]}")
                time.sleep(2 * attempt)
            else:
                log(f"❌ [{symbol}] 抓取失败 (已重试 {MAX_RETRIES} 次): {last_err}")
    return "failed", last_err


def fetch_via_candidates(ctx, job, extra=None, max_rows=MAX_ROWS_TO_EXTRACT):
    """依次尝试候选地址。返回 (status, payload, url)"""
    handler, symbol = job["handler"], job["symbol"]
    cands = job["candidates"]
    labels = [candidate_label(handler, a, p) for a, p, _ in cands]
    is_table = handler["parser"] == "ohlcv_table"
    ctx["mismatch_hints"] = []
    status, payload, url = "not_found", "无候选地址", ""
    for i, (asset, path, q) in enumerate(cands):
        query = dict(q)
        query.update(extra or {})
        url = build_target_url(handler, asset, path, query)
        status, payload = fetch_page(ctx, job, url, expect_type=expected_type_for(handler, asset),
                                     expect_seg=path if is_table else None, max_rows=max_rows)
        if status != "not_found" or ctx["aborted"]:
            return status, payload, url
        if i < len(cands) - 1:
            log(f"   ↪ [{symbol}] 尝试下一个候选地址: {labels[i + 1]}")
            time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
    log(f"   [{symbol}] 所有候选地址均未找到（{', '.join(labels)}），可在 Symbol_mapping_mw.json 添加映射。")
    for hint in dict.fromkeys(ctx["mismatch_hints"]):
        log(f"   💡 建议映射: {{\"{job['group']}\": {{\"{symbol}\": \"{hint}\"}}}}")
    return status, payload, url


# ================= 9. 结果与写入（两种模式共用） =================
def add_result(ctx, job, date_str, status, msg=""):
    ctx["results"].append({"symbol": job["symbol"], "group": job["group"],
                           "date": date_str or "-", "status": status, "msg": msg})


def fail_job(ctx, job, msg, status="failed"):
    for d in (job["dates"] or [None]):
        add_result(ctx, job, d, status, msg)


def fmt_vals(d):
    if not d:
        return "-"
    return (f"price={d.get('price')} vol={d.get('volume')} "
            f"O={d.get('open')} H={d.get('high')} L={d.get('low')}")


def commit_row(ctx, job, row, extra_info=""):
    """校验 -> 写库 -> (Today 模式) 从 JSON 移除。返回是否写入成功"""
    opts = ctx["opts"]
    group, symbol, handler = job["group"], job["symbol"], job["handler"]
    date_str, price = row[0], row[2]
    new = dict(zip(TABLE_COLS, row))

    check_price_jump(group, symbol, date_str, price, opts["record_wrong"], opts["dry_run"])

    if opts["sanity"] and handler.get("sanity"):
        ok, msg = check_price_sanity(group, symbol, date_str, price)
        if not ok:
            if PRICE_SANITY_ACTION == "skip":
                log(f"🚫 [{symbol}] {msg}，疑似映射错误或单位不一致，跳过。{extra_info}\n"
                    f"   （确认无误可用 --no-sanity 重跑）")
                add_result(ctx, job, date_str, "skipped", msg)
                return False
            log(f"⚠️ [{symbol}] {msg}（仅提示，继续写入）")

    if opts["dry_run"]:
        old_rows = read_existing(group, symbol, date_str)
        action = f"将覆盖 {len(old_rows)} 条旧记录" if old_rows else "将新增"
        log(f"🔍 [DRY-RUN] [{symbol}] {group} {date_str}: {action}\n"
            f"     旧: {fmt_vals(old_rows[0]) if old_rows else '-'}\n     新: {fmt_vals(new)} {extra_info}")
        add_result(ctx, job, date_str, "dry-run", action)
        return True

    ok, old_rows, err = write_row(group, row)
    if not ok:
        log(f"❌ [{symbol}] {group} {date_str} 数据库写入失败: {err}")
        add_result(ctx, job, date_str, "failed", f"数据库写入失败: {err}")
        return False

    if old_rows:
        log(f"♻️ [{symbol}] {group} {date_str} 已覆盖 {len(old_rows)} 条旧记录\n"
            f"     旧: {fmt_vals(old_rows[0])}\n     新: {fmt_vals(new)} {extra_info}")
        add_result(ctx, job, date_str, "updated", "已覆盖")
    else:
        log(f"🆕 [{symbol}] {group} {date_str} 新增 1 条\n     新: {fmt_vals(new)} {extra_info}")
        add_result(ctx, job, date_str, "inserted", "新增")

    if not opts["manual"]:
        remove_symbol_from_json(SECTORS_JSON_PATH, group, symbol)
    return True


# ================= 10. 任务执行 =================
def select_row(rows, last_valid_date):
    """Today：rows 为 (date, price, vol, o, h, l)。返回 (row, note)"""
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


def process_table_today(ctx, job):
    symbol = job["symbol"]
    target = job["dates"][0]
    status, payload, url = fetch_via_candidates(ctx, job, max_rows=MAX_ROWS_TO_EXTRACT)
    if status != "ok":
        add_result(ctx, job, target, "not_found" if status == "not_found" else "failed", str(payload)[:150])
        return
    sel, note = select_row(payload, target)
    if note:
        log(f"⚠️ [{symbol}] {note}")
    if sel is None:
        add_result(ctx, job, target, "skipped", note or "")
        return
    commit_row(ctx, job, (sel[0], symbol) + tuple(sel[1:]))


def process_table_manual(ctx, job):
    today = datetime.date.today()
    symbol = job["symbol"]
    windows = build_windows(job["dates"])

    for wi, win in enumerate(windows):
        if ctx["aborted"]:
            for d in win:
                add_result(ctx, job, d.isoformat(), "failed", "任务已中止（被反爬拦截/浏览器不可用）")
            continue

        lo = win[0] - datetime.timedelta(days=WINDOW_PADDING_DAYS)
        hi = min(win[-1] + datetime.timedelta(days=WINDOW_PADDING_DAYS), today)
        extra = {"startDate": fmt_mw_date(lo), "endDate": fmt_mw_date(hi)}
        log(f"🌐 [{symbol}] 抓取窗口 {lo} ~ {hi}（目标日期: {', '.join(d.isoformat() for d in win)}）")
        status, payload, url = fetch_via_candidates(ctx, job, extra, max_rows=MAX_TABLE_ROWS)

        if status != "ok":
            for d in win:
                add_result(ctx, job, d.isoformat(), "not_found" if status == "not_found" else "failed",
                           str(payload)[:150])
            log(f"❌ [{symbol}] 窗口抓取失败({status}): {str(payload)[:150]}\n   URL: {url}")
        else:
            rows = payload
            by_date = {r[0]: r for r in rows}
            lo_s, hi_s = lo.isoformat(), hi.isoformat()
            in_window = any(lo_s <= r[0] <= hi_s for r in rows)
            trading = nyse_trading_days(win[0], win[-1])

            for d in win:
                ds = d.isoformat()
                r = by_date.get(ds)
                if r is None:
                    reasons = []
                    if trading is not None and ds not in trading:
                        reasons.append("该日不是 NYSE 交易日")
                    if not in_window:
                        reasons.append(f"页面返回日期范围 {rows[-1][0]}~{rows[0][0]} 与请求窗口不符，"
                                       f"startDate/endDate 参数可能未生效")
                    reason = "；".join(reasons) or f"页面表格中没有 {ds} 这一行"
                    log(f"❓ [{symbol}] {ds} 未写入: {reason}\n   URL: {url}")
                    add_result(ctx, job, ds, "missing", reason)
                    continue
                if ds == today.isoformat():
                    log(f"⚠️ [{symbol}] {ds} 是今天，若尚未收盘则数据可能不完整。")
                commit_row(ctx, job, (ds, symbol) + tuple(r[1:]))

        if wi < len(windows) - 1 and not ctx["aborted"]:
            time.sleep(random.uniform(*REQUEST_DELAY_RANGE))


def process_quote_job(ctx, job):
    opts = ctx["opts"]
    manual = opts["manual"]
    symbol, group, handler = job["symbol"], job["group"], job["handler"]

    if manual and len(job["dates"]) != 1:
        msg = f"{group} 分组只能抓取当前页面价格，仅支持 1 个日期（收到 {len(job['dates'])} 个）"
        log(f"🚫 [{symbol}] {msg}")
        fail_job(ctx, job, msg, status="skipped")
        return
    target = job["dates"][0]  # Today 模式下可能为 None（无法计算开盘日）

    status, payload, url = fetch_via_candidates(ctx, job)
    if status != "ok":
        log(f"❌ [{symbol}] 抓取失败({status}): {str(payload)[:150]}\n   URL: {url}")
        add_result(ctx, job, target, "not_found" if status == "not_found" else "failed", str(payload)[:150])
        return

    quote = payload
    price = float(quote["price"])
    if not handler.get("allow_non_positive") and price <= 0:
        log(f"❌ [{symbol}] 价格异常: {quote.get('price_raw')}")
        add_result(ctx, job, target, "failed", f"价格异常: {quote.get('price_raw')}")
        return

    page_date = parse_quote_date(quote.get("ts"))
    page_info = (f"（页面: {quote.get('company') or '-'} | 原始值: {quote.get('price_raw')} "
                 f"| 更新: {quote.get('ts') or '-'} | 状态: {quote.get('status') or '-'}）")
    if manual:
        log(f"ℹ️ [{symbol}] {group} 只能抓取当前页面价格，将按指定日期 {target} 写入。{page_info}")

    notes = []
    if target is None:
        if not page_date:
            log(f"❌ [{symbol}] 无法确定写入日期（交易日计算失败且页面时间无法解析）")
            add_result(ctx, job, None, "failed", "无法确定写入日期")
            return
        target = get_prev_trading_date(datetime.date.fromisoformat(page_date))
        notes.append(f"无法计算最近开盘日，按页面时间 {page_date} 的前一交易日 {target} 写入。")
    elif page_date is None:
        notes.append(f"未能解析页面更新时间（'{quote.get('ts')}'），无法核对日期，按 {target} 写入。")
    elif page_date != target:
        msg = f"页面行情日期 {page_date} 与目标日期 {target} 不一致"
        skip = opts["strict_date"] or (not manual and page_date < target and STALE_DATA_POLICY == "skip")
        if skip:
            log(f"🚫 [{symbol}] {msg}，跳过。")
            add_result(ctx, job, target, "skipped", msg)
            return
        if manual or page_date < target:
            notes.append(f"{msg}（亚洲/欧洲市场常见；仍按目标日期写入，可用 --strict-date 禁止）")
    for n in notes:
        log(f"⚠️ [{symbol}] {n}")

    st = quote.get("status") or ""
    if re.search(r'\bopen\b', st, re.I) and not re.search(r'closed', st, re.I):
        log(f"⚠️ [{symbol}] 页面状态为 '{st}'，价格可能是盘中价而非收盘价。")

    if handler.get("row_style") == "flat_ohlc":
        row = (target, symbol, price, 0, price, price, price)
    else:
        row = (target, symbol, price, 0, None, None, None)
    commit_row(ctx, job, row, extra_info=page_info)


# ================= 11. 任务构建 =================
def canonical_group(name):
    key = re.sub(r'[\s\-]+', '_', str(name).strip()).lower()
    for g in SECTOR_HANDLERS:
        if g.lower() == key:
            return g
    return None


def make_job(symbol, group, dates, alias_to_symbol, mw_overrides):
    handler = SECTOR_HANDLERS[group]
    return {"symbol": symbol, "group": group, "handler": handler, "dates": dates,
            "candidates": resolve_mw_candidates(symbol, group, handler, alias_to_symbol, mw_overrides)}


def build_today_jobs(tasks_dict, only_groups, target_date, alias_to_symbol, mw_overrides):
    jobs, unknown_pending = [], {}
    if not isinstance(tasks_dict, dict):
        return jobs, unknown_pending
    for group, symbols in tasks_dict.items():
        if not isinstance(symbols, list) or not symbols:
            continue
        if only_groups and group not in only_groups:
            continue
        if group not in SECTOR_HANDLERS:
            unknown_pending[group] = len(symbols)
            continue
        for sym in dict.fromkeys(symbols):
            jobs.append(make_job(sym, group, [target_date], alias_to_symbol, mw_overrides))
    return jobs, unknown_pending


def detect_group(symbol, only_group=None):
    """返回 {group: 规范化 symbol 名}。来源：Finance.db 各分组表 + Sectors_empty.json"""
    hits = {}
    groups = [only_group] if only_group else list(SECTOR_HANDLERS)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for g in groups:
                if g in tables:
                    row = conn.execute(
                        f'SELECT name FROM "{g}" WHERE name = ? COLLATE NOCASE LIMIT 1', (symbol,)).fetchone()
                    if row:
                        hits[g] = row[0]
        finally:
            conn.close()
    except sqlite3.Error as e:
        log(f"⚠️ 查询数据库识别分组失败: {e}")

    pending = load_json_file(SECTORS_JSON_PATH, "任务 JSON")
    if isinstance(pending, dict):
        for g in groups:
            lst = pending.get(g)
            if isinstance(lst, list):
                for s in lst:
                    if str(s).lower() == symbol.lower():
                        hits.setdefault(g, str(s))
    return hits


def build_manual_jobs(raw_tasks, cli_group, today, alias_to_symbol, mw_overrides):
    jobs, errors = {}, []
    for t in raw_tasks:
        symbol = str(t.get("symbol", "")).strip()
        if not symbol:
            errors.append(f"任务缺少 symbol: {t}")
            continue
        dates, derrs = normalize_dates(t.get("dates") or [], today)
        errors += [f"[{symbol}] {e}" for e in derrs]
        if not dates:
            errors.append(f"[{symbol}] 没有有效日期，已忽略")
            continue

        g_in = t.get("group") or cli_group
        if g_in:
            group = canonical_group(g_in)
            if not group:
                errors.append(f"[{symbol}] 未知分组 '{g_in}'，可选: {', '.join(SECTOR_HANDLERS)}")
                continue
            name = detect_group(symbol, only_group=group).get(group)
            if name is None:
                log(f"⚠️ [{symbol}] 在 {group} 表/待办 JSON 中未找到该 symbol，将按输入原样处理（可能是新增）。")
                name = symbol
        else:
            hits = detect_group(symbol)
            if not hits:
                errors.append(f"[{symbol}] 无法判断所属分组（库中各表及 Sectors_empty.json 均无），"
                              f"请用 '{symbol}@分组:日期' 或 --group 指定")
                continue
            if len(hits) > 1:
                errors.append(f"[{symbol}] 同时存在于多个分组 {list(hits)}，请用 '@分组' 明确指定")
                continue
            group, name = next(iter(hits.items()))

        key = (group, name)
        if key in jobs:
            jobs[key]["dates"] = sorted(set(jobs[key]["dates"]) | set(dates))
        else:
            jobs[key] = make_job(name, group, dates, alias_to_symbol, mw_overrides)
    return list(jobs.values()), errors


def parse_task_spec(spec):
    """'AAPL:2026-09-18,2026-09-19' 或 'SPY@ETFs:2026-09-10'"""
    head, sep, tail = spec.partition(':')
    if not sep or not tail.strip():
        raise ValueError(f"任务格式应为 SYMBOL[@GROUP]:DATE[,DATE...]，收到: {spec}")
    symbol, _, group = head.partition('@')
    return {"symbol": symbol.strip(), "group": group.strip() or None,
            "dates": [x for x in re.split(r'[,\s;]+', tail.strip()) if x]}


# ================= 12. 主流程 =================
def print_plan(jobs):
    log("=" * 60)
    log("📋 执行计划（强制覆盖写入）:")
    for j in jobs:
        kind = "历史表格" if j["handler"]["parser"] == "ohlcv_table" else "当前页面价格"
        log(f"  - {j['symbol']:<14} → 表 {j['group']:<22} [{kind}]  日期: {', '.join(j['dates'])}")
    log("=" * 60)


def print_summary(ctx, manual):
    results = ctx["results"]
    log("📊 汇总:")
    shown = results if manual else [r for r in results if r["status"] not in OK_STATUSES]
    for r in shown:
        mark = "✅" if r["status"] in OK_STATUSES else "❌"
        log(f"  {mark} {r['symbol']:<14} {r['group']:<22} {r['date']}  {r['status']:<9} {r['msg']}")
    c = Counter(r["status"] for r in results)
    log("   合计: " + (" | ".join(f"{k}={v}" for k, v in c.items()) or "无"))
    s = ctx["solver"].summary()
    if s:
        log(s)


def run_jobs(jobs, opts):
    """返回 ctx（含 results）。两种模式共用的执行循环"""
    manual = opts["manual"]
    solver = CaptchaAutoSolver(enabled=opts["auto_slider"] and AUTO_SLIDER_ENABLED)
    ctx = {"driver": None, "headless": opts["headless"], "escalate": opts["escalate"] and AUTO_ESCALATE_HEADFUL,
           "solver": solver, "opts": opts, "consecutive_blocks": 0, "aborted": False,
           "mismatch_hints": [], "fingerprints": {}, "results": []}

    log(f"共 {len(jobs)} 个任务。（模式: {'Manual' if manual else 'Today'} | "
        f"{'无头' if ctx['headless'] else '有界面'}"
        f"{' | DRY-RUN 不写库' if opts['dry_run'] else ''}"
        f"{' | 已关闭价格校验' if not opts['sanity'] else ''}"
        f"{' | 滑块自动验证' if solver.enabled else ' | 滑块需手动'}）")

    prepare_profile_dir()
    try:
        ctx["driver"] = create_driver(ctx["headless"])
    except Exception as e:
        log(f"❌ Selenium 启动失败: {e}\n   提示：若提示 Profile 被占用，请关闭使用 {MW_PROFILE_DIR} 的浏览器进程。")
        for j in jobs:
            fail_job(ctx, j, "浏览器启动失败")
        return ctx

    if not ctx["headless"]:
        solver.activate_terminal()  # 有界面浏览器启动会抢焦点，把终端切回来

    pbar = tqdm(jobs, desc="总体进度", position=0)
    try:
        for idx, job in enumerate(pbar):
            if ctx["aborted"]:
                fail_job(ctx, job, "任务已中止（被反爬拦截/浏览器不可用）")
                continue
            if not job["candidates"]:
                msg = "无法推导 MarketWatch 地址，请在 Symbol_mapping_mw.json 中添加"
                log(f"❓ [{job['symbol']}] {job['group']} {msg}")
                fail_job(ctx, job, msg, status="not_found")
                continue

            first = candidate_label(job["handler"], *job["candidates"][0][:2])
            pbar.set_description(f"处理中: {job['symbol']}"
                                 + (f" (→ {first})" if first != job["symbol"].lower() else "")
                                 + f" [{job['group']}]")
            try:
                if job["handler"]["parser"] == "ohlcv_table":
                    (process_table_manual if manual else process_table_today)(ctx, job)
                else:
                    process_quote_job(ctx, job)
            except Exception as e:  # 单个任务的意外异常不拖垮整轮
                log(f"❌ [{job['symbol']}] 处理异常: {type(e).__name__}: {str(e)[:150]}")
                fail_job(ctx, job, f"处理异常: {str(e)[:100]}")

            if ctx["aborted"]:
                log("🛑 连续被反爬拦截或浏览器无法恢复，终止本轮任务。")
            elif idx < len(jobs) - 1:
                time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
    finally:
        pbar.close()
        safe_quit(ctx["driver"])
        clean_profile_cache()
    return ctx


def run_check_yesterday_if_empty():
    """只有在 Sectors_empty.json 存在且全部清空时才执行 Check_yesterday.py"""
    if not os.path.exists(SECTORS_JSON_PATH):
        log(f"⚠️ 未找到任务文件 {SECTORS_JSON_PATH}，跳过执行 Check_yesterday.py。")
        return
    final_tasks = load_json_file(SECTORS_JSON_PATH, "任务 JSON")
    if not isinstance(final_tasks, dict):
        log("⚠️ 无法正确读取任务 JSON，跳过执行 Check_yesterday.py。")
        return
    if all(not v for v in final_tasks.values()):
        log("✅ Sectors_empty.json 已全部清空，开始执行 Check_yesterday.py...")
        try:
            subprocess.run([sys.executable, CHECK_YESTERDAY_SCRIPT_PATH, "--ignore_sectors"],
                           check=True, capture_output=True, text=True, encoding='utf-8')
            log("✅ Check_yesterday.py 执行完毕。")
        except subprocess.CalledProcessError as e:
            log(f"❌ Check_yesterday 返回错误码 {e.returncode}:\n{(e.stderr or '')[-1000:]}")
        except Exception as e:
            log(f"❌ 调用 Check_yesterday 出错: {e}")
    else:
        log("⚠️ Sectors_empty.json 中仍有未完成的任务，跳过执行 Check_yesterday.py。")


def parse_args():
    p = argparse.ArgumentParser(description="MarketWatch 数据抓取（Today / Manual 双模式）",
                                allow_abbrev=False)
    g = p.add_argument_group("通用")
    g.add_argument("--headful", action="store_true", help="显示浏览器窗口")
    g.add_argument("--headless", action="store_true", help="强制无头（覆盖 MW_Manual.py 垫片的有界面默认值）")
    g.add_argument("--dry-run", action="store_true", help="只抓取并对比，不写库、不改 JSON")
    g.add_argument("--no-sanity", action="store_true", help="关闭行情页分组的价格偏差合理性校验")
    g.add_argument("--strict-date", action="store_true", help="行情页日期与目标日期不一致时跳过")
    g.add_argument("--record-wrong", action=argparse.BooleanOptionalAction, default=None,
                   help="偏差>10%% 时把 symbol 追加到 wrong.txt（Today 默认开，Manual 默认关）")
    g.add_argument("--no-auto-slider", action="store_true", help="关闭滑块自动验证（只能手动）")
    g.add_argument("--no-escalate", action="store_true", help="无头模式遇到验证码时不自动切换为有界面模式")
    t = p.add_argument_group("Today 模式")
    t.add_argument("--groups", nargs="+", default=None, help="只抓取指定分组，例如 --groups Currencies Indices")
    t.add_argument("--no-check", action="store_true", help="结束后不调用 Check_yesterday.py")
    m = p.add_argument_group("Manual 模式（出现 --task/--symbol/--manual 任一即进入）")
    m.add_argument("--manual", action="store_true", help="进入 Manual 模式并使用文件顶部 MANUAL_TASKS")
    m.add_argument("--task", action="append", default=[],
                   help="SYMBOL[@GROUP]:DATE[,DATE...]，可重复。例 --task AAPL:2026-09-18,2026-09-19")
    m.add_argument("--symbol", help="与 --dates 配合使用的单个 symbol")
    m.add_argument("--dates", nargs="+", help="日期列表 YYYY-MM-DD")
    m.add_argument("--group", help="显式指定分组（对所有任务生效，自动判断有歧义时使用）")
    m.add_argument("--yes", "-y", action="store_true", help="跳过执行前确认")
    return p.parse_args()


def main(force_manual=False, default_headful=False):
    args = parse_args()
    manual = bool(force_manual or args.manual or args.task or args.symbol)

    if not manual and (args.dates or args.group):
        print("❌ --dates / --group 仅用于 Manual 模式，请同时使用 --symbol 或 --task。")
        return 2
    if manual and args.groups:
        print("⚠️ --groups 仅用于 Today 模式，Manual 模式下已忽略（请用 --group）。")
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}（为避免误建空库，已中止）")
        return 2

    if args.headful or args.headless:
        headless = not args.headful
    else:
        headless = not default_headful
    record_wrong = args.record_wrong if args.record_wrong is not None else (not manual)

    init_logging(MANUAL_LOG_PATH if manual else TODAY_LOG_PATH)
    if not acquire_run_lock():
        print("❌ 已有另一个 MW_Today/MW_Manual 实例在运行（共用同一浏览器 Profile），已退出。")
        return 3

    opts = {"manual": manual, "headless": headless, "dry_run": args.dry_run,
            "sanity": not args.no_sanity, "strict_date": args.strict_date,
            "record_wrong": record_wrong, "auto_slider": not args.no_auto_slider,
            "escalate": not args.no_escalate}

    alias_to_symbol = load_alias_mapping(SYMBOL_MAPPING_PATH)
    mw_overrides = load_mw_overrides(MW_SYMBOL_OVERRIDE_PATH)
    errors = []

    if manual:
        raw_tasks = []
        try:
            raw_tasks += [parse_task_spec(s) for s in args.task]
        except ValueError as e:
            print(f"❌ {e}")
            return 2
        if args.symbol:
            if not args.dates:
                print("❌ 使用 --symbol 时必须同时提供 --dates")
                return 2
            raw_tasks.append({"symbol": args.symbol, "dates": args.dates})
        if not raw_tasks:
            raw_tasks = list(MANUAL_TASKS)
        if not raw_tasks:
            print("❌ 没有任务：请使用 --task / --symbol+--dates，或编辑文件顶部 MANUAL_TASKS 后用 --manual。")
            return 2
        jobs, errors = build_manual_jobs(raw_tasks, args.group, datetime.date.today(),
                                         alias_to_symbol, mw_overrides)
        for e in errors:
            log(f"❌ 配置错误: {e}")
        if not jobs:
            log("没有可执行的任务，退出。")
            return 2
        print_plan(jobs)
        if not args.dry_run and not args.yes and sys.stdin.isatty():
            if input("以上操作将【强制覆盖】数据库中对应记录，确认执行？[y/N]: ").strip().lower() != "y":
                log("已取消。")
                return 0
    else:
        only_groups = None
        if args.groups:
            only_groups = set()
            for g in args.groups:
                cg = canonical_group(g)
                if cg:
                    only_groups.add(cg)
                else:
                    log(f"⚠️ 未知分组 '{g}'，已忽略。可选: {', '.join(SECTOR_HANDLERS)}")
            if not only_groups:
                log("没有有效的分组，退出。")
                return 2
        tasks_dict = load_json_file(SECTORS_JSON_PATH, "任务 JSON")
        if tasks_dict is None:
            log(f"⚠️ 未找到或无法读取 JSON 文件: {SECTORS_JSON_PATH}")
        last_valid_date = get_last_valid_trading_date()
        if last_valid_date:
            log(f"📅 计算得出的最近有效开盘日为: {last_valid_date}")
        else:
            log("⚠️ 无法计算最近有效开盘日，将使用网页原始日期。")
        jobs, unknown_pending = build_today_jobs(tasks_dict, only_groups, last_valid_date,
                                                 alias_to_symbol, mw_overrides)
        for g, n in unknown_pending.items():
            log(f"⏭️  分组 [{g}] 有 {n} 个待抓取项，不在本爬虫支持范围内，跳过。")
        if not jobs:
            log("✅ 支持的分组中没有待抓取的 Symbol，任务结束。")
            if not args.no_check and not args.dry_run:
                run_check_yesterday_if_empty()
            return 0

    start_caffeinate()
    try:
        ctx = run_jobs(jobs, opts)
        print_summary(ctx, manual)
        if not manual and not args.no_check and not args.dry_run:
            run_check_yesterday_if_empty()
    finally:
        stop_caffeinate()
    all_ok = all(r["status"] in OK_STATUSES for r in ctx["results"]) and not errors
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())