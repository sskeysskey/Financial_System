# -*- coding: utf-8 -*-
"""
MW_Manual.py
手动指定 symbol + 日期，从 MarketWatch 抓取并【强制覆盖】写入 Finance.db。

- ETFs + 11 个股票分组：download-data 历史表格，可指定任意历史日期（可多个）
- Bonds / Currencies / Crypto / Indices / Commodities：仅能抓当前页面价格，只允许 1 个日期

用法:
    python MW_Manual.py --task "AAPL:2026-09-18,2026-09-19" --task "SPY@ETFs:2026-09-10"
    python MW_Manual.py --symbol AAPL --dates 2026-09-18 2026-09-19
    python MW_Manual.py --task "S&P500:2026-09-19"
    python MW_Manual.py                      # 使用文件顶部 MANUAL_TASKS
    python MW_Manual.py --dry-run --headful  # 首次建议先这样验证
其它参数: --group --headful --no-sanity --strict-date --record-wrong --yes
"""
import argparse
import datetime
import json
import os
import platform
import random
import re
import shutil
import sqlite3
import sys
import time
import urllib.parse
from collections import Counter

try:
    import pandas_market_calendars as mcal
except ImportError:  # 没装也能跑，只是少了交易日提示
    mcal = None
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from tqdm import tqdm

# ================= 配置区域 =================
# 不用命令行时，在这里填写。group 可省略（自动判断）。
MANUAL_TASKS = [
    # {"symbol": "AAPL", "dates": ["2026-09-18", "2026-09-19"]},
    # {"symbol": "SPY", "group": "ETFs", "dates": ["2026-09-10"]},
    # {"symbol": "S&P500", "dates": ["2026-09-19"]},
]

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_DIR = os.path.join(BASE_CODING_DIR, "News")

DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
SECTORS_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_empty.json")
SYMBOL_MAPPING_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping.json")
MW_SYMBOL_OVERRIDE_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping_mw.json")
WRONG_TXT_PATH = os.path.join(NEWS_DIR, "wrong.txt")
MANUAL_LOG_PATH = os.path.join(NEWS_DIR, "MW_Manual.log")
PRICE_DEVIATION_ALERT_THRESHOLD = 0.10

USE_PERSISTENT_PROFILE = True
MW_PROFILE_DIR = os.environ.get("MW_PROFILE_DIR") or os.path.join(DOWNLOADS_DIR, "backup", "mw_chrome_profile")
CLEAN_PROFILE_CACHE_ON_EXIT = True
PROFILE_CACHE_SUBPATHS = [
    "Default/Cache", "Default/Code Cache", "Default/GPUCache",
    "Default/DawnCache", "Default/DawnGraphiteCache", "Default/DawnWebGPUCache",
    "Default/Service Worker/CacheStorage", "Default/Service Worker/ScriptCache",
    "GrShaderCache", "GraphiteDawnCache", "ShaderCache",
    "component_crx_cache", "extensions_crx_cache", "Crashpad",
]

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

# ---- 历史窗口参数 ----
WINDOW_MAX_SPAN_DAYS = 90   # 多个日期合并成一个请求窗口的最大跨度
WINDOW_PADDING_DAYS = 1     # 窗口两端各多取 1 天，防止边界 off-by-one
MAX_TABLE_ROWS = 500        # 单页最多提取行数

PRICE_SANITY_THRESHOLD = 0.25   # 仅对行情页分组生效

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


# ================= 日志 =================
def log(msg):
    tqdm.write(msg)
    try:
        os.makedirs(os.path.dirname(MANUAL_LOG_PATH), exist_ok=True)
        with open(MANUAL_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


# ================= 数据库 =================
def get_table_type(sector):
    expanded = ['ETFs'] + STOCK_SECTORS + ['Crypto']
    if sector in expanded:
        return "expanded"
    if sector in ['Bonds', 'Currencies', 'Commodities', 'Economics']:
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


def overwrite_row(table, table_type, row):
    """
    强制覆盖：同一事务内 DELETE 同 (date,name) 的全部行 + INSERT。
    不依赖 UNIQUE 约束；按表的真实列写入。
    返回 (ok, old_rows(list[dict]), err)
    """
    _assert_known_table(table)
    values = dict(zip(TABLE_COLS, row))
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    try:
        create_table_if_not_exists(conn.cursor(), table, table_type)
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        for need in ("date", "name", "price"):
            if need not in cols:
                raise sqlite3.Error(f"表 {table} 缺少必要列 {need}")
        use = [c for c in TABLE_COLS if c in cols]
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
        conn.rollback()
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


def check_price_jump(group, symbol, date_str, price, record_wrong):
    """与库中前一条价格比较，偏差>10% 仅警告；--record-wrong 时才写 wrong.txt"""
    prev = get_last_db_price(group, symbol, date_str)
    if prev is None or abs(prev) < 1e-8:
        return
    diff = (price - prev) / abs(prev)
    if abs(diff) <= PRICE_DEVIATION_ALERT_THRESHOLD:
        return
    log(f"🚨 [{symbol}] ({group}) {date_str} 价格与前一条偏差超 10%: {prev} -> {price} ({diff:+.2%})")
    if record_wrong and (group, symbol, date_str) not in _RECORDED_WRONG:
        try:
            os.makedirs(NEWS_DIR, exist_ok=True)
            with open(WRONG_TXT_PATH, "a", encoding="utf-8") as f:
                f.write(f"{symbol}\n")
            _RECORDED_WRONG.add((group, symbol, date_str))
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


# ================= JSON / 映射 =================
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


# ================= 日期 / 交易日 =================
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


def get_prev_trading_date(ref_date):
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


def nyse_trading_days(start, end):
    """返回 {'YYYY-MM-DD'}；失败返回 None"""
    if mcal is None:
        return None
    try:
        sched = mcal.get_calendar('NYSE').schedule(start_date=start, end_date=end)
        return {d.strftime('%Y-%m-%d') for d in sched.index.date}
    except Exception:
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


# ================= Symbol -> URL =================
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


# ================= 浏览器 =================
def prepare_profile_dir():
    if USE_PERSISTENT_PROFILE:
        os.makedirs(os.path.abspath(MW_PROFILE_DIR), exist_ok=True)


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


def load_page(driver, url):
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


# ================= 页面解析 JS =================
JS_COMMON = r"""
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
"""

PAGE_STATE_JS = JS_COMMON + r"""
const txt = (document.body ? document.body.innerText : '').slice(0, 3000);
if (mwIsCaptcha()) return 'captcha';
const tbl = mwFindTable();
if (tbl && tbl.querySelectorAll('tbody tr').length > 0) return 'ready';
if (!location.pathname.toLowerCase().includes('download-data')) return 'notfound';
if (/symbol lookup|no results found|there were no matches/i.test(txt)) return 'notfound';
return 'loading';
"""

EXTRACT_JS = JS_COMMON + r"""
const maxRows = arguments[0] || 5;
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
return { data: out };
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
const p = qPrice();
const st = qScope().querySelector('small[class*="status"]');
return {
    price: p.value, price_raw: p.raw, price_src: p.src,
    ts: qTimestamp(), status: qText(st),
    company: qText(document.querySelector('h1[class*="company"]')),
    body_class: document.body ? (document.body.className || '') : '',
    url: location.href
};
"""


def _wait_loop(driver, timeout, headless, state_fn, timeout_msg, expect_type=None):
    deadline = time.time() + timeout
    captcha_notified = False
    while True:
        state = state_fn()
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
        if state == 'captcha':
            if headless:
                raise CaptchaBlockedError("触发反爬验证（无头模式无法处理，请加 --headful）")
            if not captcha_notified:
                log(f"🧩 检测到验证码，请在浏览器窗口中手动完成（最多等待 {CAPTCHA_MANUAL_WAIT} 秒）...")
                deadline = time.time() + CAPTCHA_MANUAL_WAIT
                captcha_notified = True
        if time.time() > deadline:
            if state == 'captcha':
                raise CaptchaBlockedError("验证码等待超时")
            raise ScrapeError(timeout_msg)
        time.sleep(0.5)


def wait_for_table(driver, timeout, headless):
    _wait_loop(driver, timeout, headless, lambda: driver.execute_script(PAGE_STATE_JS),
               "等待数据表格超时（该日期窗口可能没有任何交易数据）")


def extract_rows(driver, max_rows):
    """返回 [(date, price, volume, open, high, low)]，按日期降序"""
    result = driver.execute_script(EXTRACT_JS, max_rows)
    if not isinstance(result, dict):
        raise ScrapeError("JS 返回结果异常")
    if "error" in result:
        raise ScrapeError(result["error"])
    rows = []
    for date_str, price, volume, o, h, l in result.get("data", []):
        if price is None or price <= 0:
            continue
        rows.append((date_str, float(price), int(volume) if volume is not None else 0, o, h, l))
    rows.sort(key=lambda x: x[0], reverse=True)
    return rows


def wait_for_quote(driver, timeout, headless, expect_type):
    _wait_loop(driver, timeout, headless,
               lambda: driver.execute_script(QUOTE_STATE_JS, expect_type or ""),
               "等待行情价格超时", expect_type=expect_type)


def extract_quote(driver):
    r = driver.execute_script(QUOTE_EXTRACT_JS)
    if not isinstance(r, dict):
        raise ScrapeError("JS 返回结果异常")
    if r.get("price") is None:
        raise ScrapeError("未解析到价格")
    return r


# ================= 抓取核心 =================
def fetch_page(ctx, opts, url, parser, expect_type=None):
    """返回 (status, payload)；status: ok / not_found / failed。浏览器句柄保存在 ctx['driver']"""
    headless = opts["headless"]
    last_err = ""
    for attempt in range(1, MAX_RETRIES + 1):
        driver = ctx["driver"]
        if driver is None:
            ctx["aborted"] = True
            return "failed", "浏览器不可用"
        try:
            load_page(driver, url)
            if parser == "ohlcv_table":
                wait_for_table(driver, TABLE_WAIT_TIMEOUT, headless)
                ctx["consecutive_blocks"] = 0
                rows = extract_rows(driver, MAX_TABLE_ROWS)
                if not rows:
                    raise ScrapeError("提取到的数据为空")
                return "ok", rows
            wait_for_quote(driver, QUOTE_WAIT_TIMEOUT, headless, expect_type)
            ctx["consecutive_blocks"] = 0
            return "ok", extract_quote(driver)

        except SymbolNotFoundError as e:
            if e.actual_type:
                hint = suggest_override_from_url(e.final_url)
                if hint:
                    ctx["mismatch_hints"].append(hint)
            return "not_found", str(e)[:200]

        except CaptchaBlockedError as e:
            ctx["consecutive_blocks"] += 1
            last_err = str(e)
            log(f"🛑 被反爬拦截 ({ctx['consecutive_blocks']}/{MAX_CONSECUTIVE_BLOCKS}): {e}")
            if ctx["consecutive_blocks"] >= MAX_CONSECUTIVE_BLOCKS:
                ctx["aborted"] = True
                return "failed", last_err
            time.sleep(BLOCK_BACKOFF_SECONDS * attempt + random.uniform(0, 5))

        except Exception as e:
            last_err = str(e)[:150]
            if isinstance(e, WebDriverException) and not is_driver_alive(driver):
                log("♻️ 浏览器会话已失效，正在重建...")
                safe_quit(driver)
                try:
                    ctx["driver"] = create_driver(headless)
                except Exception as ce:
                    log(f"❌ 浏览器重建失败: {ce}")
                    ctx["driver"] = None
                    ctx["aborted"] = True
                    return "failed", f"浏览器重建失败: {ce}"
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
    return "failed", last_err


def fetch_via_candidates(ctx, opts, job, extra=None):
    """依次尝试候选地址。返回 (status, payload, url)"""
    handler, symbol = job["handler"], job["symbol"]
    cands = job["candidates"]
    labels = [candidate_label(handler, a, p) for a, p, _ in cands]
    ctx["mismatch_hints"] = []
    status, payload, url = "not_found", "无候选地址", ""
    for i, (asset, path, q) in enumerate(cands):
        query = dict(q)
        query.update(extra or {})
        url = build_target_url(handler, asset, path, query)
        status, payload = fetch_page(ctx, opts, url, handler["parser"], expected_type_for(handler, asset))
        if status != "not_found" or ctx["aborted"]:
            return status, payload, url
        if i < len(cands) - 1:
            log(f"   ↪ [{symbol}] 尝试下一个候选地址: {labels[i + 1]}")
            time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
    log(f"   [{symbol}] 所有候选地址均未找到（{', '.join(labels)}），可在 Symbol_mapping_mw.json 添加映射。")
    for hint in dict.fromkeys(ctx["mismatch_hints"]):
        log(f"   💡 建议映射: {{\"{job['group']}\": {{\"{symbol}\": \"{hint}\"}}}}")
    return status, payload, url


# ================= 结果与写入 =================
def add_result(ctx, job, date_str, status, msg=""):
    ctx["results"].append({"symbol": job["symbol"], "group": job["group"],
                           "date": date_str, "status": status, "msg": msg})


def fmt_vals(d):
    if not d:
        return "-"
    return (f"price={d.get('price')} vol={d.get('volume')} "
            f"O={d.get('open')} H={d.get('high')} L={d.get('low')}")


def apply_row(ctx, opts, job, row, extra_info=""):
    group, symbol, date_str = job["group"], job["symbol"], row[0]
    new = dict(zip(TABLE_COLS, row))
    check_price_jump(group, symbol, date_str, row[2], opts["record_wrong"])
    old_rows = read_existing(group, symbol, date_str)

    if opts["dry_run"]:
        action = f"将覆盖 {len(old_rows)} 条旧记录" if old_rows else "将新增"
        log(f"🔍 [DRY-RUN] [{symbol}] {group} {date_str}: {action}\n"
            f"     旧: {fmt_vals(old_rows[0]) if old_rows else '-'}\n     新: {fmt_vals(new)} {extra_info}")
        add_result(ctx, job, date_str, "dry-run", action)
        return

    ok, old_rows, err = overwrite_row(group, get_table_type(group), row)
    if not ok:
        log(f"❌ [{symbol}] {group} {date_str} 数据库写入失败: {err}")
        add_result(ctx, job, date_str, "failed", f"数据库写入失败: {err}")
        return
    if old_rows:
        log(f"♻️ [{symbol}] {group} {date_str} 已覆盖 {len(old_rows)} 条旧记录\n"
            f"     旧: {fmt_vals(old_rows[0])}\n     新: {fmt_vals(new)} {extra_info}")
        add_result(ctx, job, date_str, "updated", "已覆盖")
    else:
        log(f"🆕 [{symbol}] {group} {date_str} 新增 1 条\n     新: {fmt_vals(new)} {extra_info}")
        add_result(ctx, job, date_str, "inserted", "新增")


# ================= 任务执行：历史表格类 =================
def run_table_job(ctx, opts, job):
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
        status, payload, url = fetch_via_candidates(ctx, opts, job, extra)

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
                row = (ds, symbol, r[1], r[2], r[3], r[4], r[5])
                apply_row(ctx, opts, job, row)

        if wi < len(windows) - 1 and not ctx["aborted"]:
            time.sleep(random.uniform(*REQUEST_DELAY_RANGE))


# ================= 任务执行：行情概览类 =================
def run_quote_job(ctx, opts, job):
    symbol, group, handler = job["symbol"], job["group"], job["handler"]
    if len(job["dates"]) != 1:
        msg = f"{group} 分组只能抓取当前页面价格，仅支持 1 个日期（收到 {len(job['dates'])} 个）"
        log(f"🚫 [{symbol}] {msg}")
        for d in job["dates"]:
            add_result(ctx, job, d, "skipped", msg)
        return
    target = job["dates"][0]

    status, payload, url = fetch_via_candidates(ctx, opts, job)
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
    log(f"ℹ️ [{symbol}] {group} 只能抓取当前页面价格，将按指定日期 {target} 写入。{page_info}")

    if page_date is None:
        log(f"⚠️ [{symbol}] 未能解析页面更新时间，无法核对日期。")
    elif page_date != target:
        msg = f"页面行情日期 {page_date} 与指定日期 {target} 不一致"
        if opts["strict_date"]:
            log(f"🚫 [{symbol}] {msg}，--strict-date 已开启，跳过。")
            add_result(ctx, job, target, "skipped", msg)
            return
        log(f"⚠️ [{symbol}] {msg}（亚洲/欧洲市场常见；仍按指定日期写入，可用 --strict-date 禁止）")

    st = quote.get("status") or ""
    if re.search(r'\bopen\b', st, re.I) and not re.search(r'closed', st, re.I):
        log(f"⚠️ [{symbol}] 页面状态为 '{st}'，价格可能是盘中价而非收盘价。")

    if opts["sanity"] and handler.get("sanity"):
        ok, msg = check_price_sanity(group, symbol, target, price)
        if not ok:
            log(f"🚫 [{symbol}] {msg}，疑似映射错误或单位不一致，跳过。\n"
                f"   URL: {url}（确认无误可用 --no-sanity 重跑）")
            add_result(ctx, job, target, "skipped", msg)
            return

    if handler.get("row_style") == "flat_ohlc":
        row = (target, symbol, price, 0, price, price, price)
    else:
        row = (target, symbol, price, 0, None, None, None)
    apply_row(ctx, opts, job, row, extra_info=page_info)


# ================= 分组识别与任务构建 =================
def canonical_group(name):
    key = re.sub(r'[\s\-]+', '_', str(name).strip()).lower()
    for g in SECTOR_HANDLERS:
        if g.lower() == key:
            return g
    return None


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


def build_jobs(raw_tasks, cli_group, today):
    jobs, errors = {}, []
    alias_to_symbol = load_alias_mapping(SYMBOL_MAPPING_PATH)
    mw_overrides = load_mw_overrides(MW_SYMBOL_OVERRIDE_PATH)

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

        handler = SECTOR_HANDLERS[group]
        key = (group, name)
        if key in jobs:
            jobs[key]["dates"] = sorted(set(jobs[key]["dates"]) | set(dates))
            continue
        cands = resolve_mw_candidates(name, group, handler, alias_to_symbol, mw_overrides)
        jobs[key] = {"symbol": name, "group": group, "handler": handler,
                     "dates": dates, "candidates": cands}
    return list(jobs.values()), errors


def parse_task_spec(spec):
    """'AAPL:2026-09-18,2026-09-19' 或 'SPY@ETFs:2026-09-10'"""
    head, sep, tail = spec.partition(':')
    if not sep or not tail.strip():
        raise ValueError(f"任务格式应为 SYMBOL[@GROUP]:DATE[,DATE...]，收到: {spec}")
    symbol, _, group = head.partition('@')
    return {"symbol": symbol.strip(), "group": group.strip() or None,
            "dates": [x for x in re.split(r'[,\s;]+', tail.strip()) if x]}


# ================= 主流程 =================
def print_plan(jobs):
    log("=" * 60)
    log("📋 执行计划（强制覆盖写入）:")
    for j in jobs:
        kind = "历史表格" if j["handler"]["parser"] == "ohlcv_table" else "当前页面价格"
        log(f"  - {j['symbol']:<14} → 表 {j['group']:<22} [{kind}]  日期: {', '.join(j['dates'])}")
    log("=" * 60)


def print_summary(results):
    log("📊 汇总:")
    for r in results:
        mark = "✅" if r["status"] in OK_STATUSES else "❌"
        log(f"  {mark} {r['symbol']:<14} {r['group']:<22} {r['date']}  {r['status']:<9} {r['msg']}")
    c = Counter(r["status"] for r in results)
    log("   合计: " + " | ".join(f"{k}={v}" for k, v in c.items()))


def run(jobs, opts):
    ctx = {"driver": None, "consecutive_blocks": 0, "aborted": False,
           "mismatch_hints": [], "results": []}
    prepare_profile_dir()
    try:
        ctx["driver"] = create_driver(opts["headless"])
    except Exception as e:
        log(f"❌ Selenium 启动失败: {e}\n   提示：若 Profile 被占用，请先关闭 MW_Today.py 或其它使用 "
            f"{MW_PROFILE_DIR} 的 Chrome 进程。")
        for j in jobs:
            for d in j["dates"]:
                add_result(ctx, j, d, "failed", "浏览器启动失败")
        return ctx["results"]

    try:
        for idx, job in enumerate(jobs):
            if ctx["aborted"]:
                for d in job["dates"]:
                    add_result(ctx, job, d, "failed", "任务已中止（被反爬拦截/浏览器不可用）")
                continue
            if not job["candidates"]:
                msg = "无法推导 MarketWatch 地址，请在 Symbol_mapping_mw.json 中添加"
                log(f"❓ [{job['symbol']}] {job['group']} {msg}")
                for d in job["dates"]:
                    add_result(ctx, job, d, "not_found", msg)
                continue
            if job["handler"]["parser"] == "ohlcv_table":
                run_table_job(ctx, opts, job)
            else:
                run_quote_job(ctx, opts, job)
            if idx < len(jobs) - 1 and not ctx["aborted"]:
                time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
    finally:
        safe_quit(ctx["driver"])
        clean_profile_cache()
    return ctx["results"]


def parse_args():
    p = argparse.ArgumentParser(description="MarketWatch 手动指定 symbol+日期 强制覆盖写库")
    p.add_argument("--task", action="append", default=[],
                   help="SYMBOL[@GROUP]:DATE[,DATE...]，可重复。例 --task AAPL:2026-09-18,2026-09-19")
    p.add_argument("--symbol", help="与 --dates 配合使用的单个 symbol")
    p.add_argument("--dates", nargs="+", help="日期列表 YYYY-MM-DD")
    p.add_argument("--group", help="显式指定分组（对所有任务生效，自动判断有歧义时使用）")
    p.add_argument("--headful", action="store_true", help="显示浏览器窗口（可手动过验证码）")
    p.add_argument("--dry-run", action="store_true", help="只抓取并对比，不写库")
    p.add_argument("--no-sanity", action="store_true", help="关闭行情页分组的价格偏差校验")
    p.add_argument("--strict-date", action="store_true", help="行情页日期与指定日期不一致时跳过")
    p.add_argument("--record-wrong", action="store_true", help="偏差>10% 时把 symbol 追加到 wrong.txt")
    p.add_argument("--yes", "-y", action="store_true", help="跳过执行前确认")
    return p.parse_args()


def main():
    args = parse_args()
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}（为避免误建空库，已中止）")
        return 2

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
        print("❌ 没有任务：请使用 --task / --symbol+--dates，或编辑文件顶部 MANUAL_TASKS。")
        return 2

    today = datetime.date.today()
    jobs, errors = build_jobs(raw_tasks, args.group, today)
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

    opts = {"headless": not args.headful, "dry_run": args.dry_run, "sanity": not args.no_sanity,
            "strict_date": args.strict_date, "record_wrong": args.record_wrong}
    log(f"🚀 开始（模式: {'无头' if opts['headless'] else '有界面'}"
        f"{' | DRY-RUN' if args.dry_run else ''}）")
    results = run(jobs, opts)
    print_summary(results)
    all_ok = all(r["status"] in OK_STATUSES for r in results) and not errors
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())