# -*- coding: utf-8 -*-
"""
MW_Today.py
从 MarketWatch 抓取 Sectors_empty.json 中 ETFs 及 11 个股票分组的最新一日 OHLCV 数据，
写入 Finance.db（组名即表名），成功后从 JSON 中移除该 symbol。

用法:
    python MW_Today.py                      # 默认无头模式
    python MW_Today.py --headful            # 有界面（首次运行 / 遇到验证码时推荐）
    python MW_Today.py --groups ETFs Energy # 只跑指定分组
    python MW_Today.py --no-check           # 结束后不调用 Check_yesterday.py
"""
import argparse
import atexit
import datetime
import json
import os
import platform
import random
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

# ================= 配置区域 =================
USER_HOME = os.path.expanduser("~")

BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")

DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
SECTORS_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_empty.json")
SYMBOL_MAPPING_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping.json")
# 可选：MarketWatch 专用覆盖映射（不存在则忽略），格式 {"BRK-B": "brk.b", "XXX": "xxx?countrycode=uk"}
MW_SYMBOL_OVERRIDE_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping_mw.json")
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

# 独立的浏览器 Profile（保存 Cookie，降低被反爬拦截概率；不要与正在运行的 Chrome 共用）
USE_PERSISTENT_PROFILE = True
MW_PROFILE_DIR = os.path.join(FINANCIAL_SYSTEM_DIR, "Selenium", "mw_chrome_profile")

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
PAGE_LOAD_TIMEOUT = 30          # driver.get 超时
TABLE_WAIT_TIMEOUT = 15         # 等待表格出现的超时
CAPTCHA_MANUAL_WAIT = 180       # 有界面模式下，等待手动完成验证码的最长时间
MAX_RETRIES = 3
MAX_CONSECUTIVE_BLOCKS = 3      # 连续被反爬拦截次数达到此值，终止整轮任务
BLOCK_BACKOFF_SECONDS = 10      # 被拦截后的退避基数（秒）
REQUEST_DELAY_RANGE = (2.0, 4.5)  # 每个 symbol 之间的随机间隔（秒）
MAX_ROWS_TO_EXTRACT = 5         # 从表格顶部提取的行数（用于日期匹配）

# 日期对不上时的策略：
#   "overwrite_date" -> 与 YF_Today 保持一致：取最新一行并把日期改为最近有效开盘日写入
#   "skip"           -> 不写入，保留在 JSON 中等待下次
STALE_DATA_POLICY = "overwrite_date"

# ---- 分组 -> 抓取处理器 ----
STOCK_SECTORS = [
    'Basic_Materials', 'Communication_Services', 'Consumer_Cyclical',
    'Consumer_Defensive', 'Energy', 'Financial_Services', 'Healthcare',
    'Industrials', 'Real_Estate', 'Technology', 'Utilities',
]

SECTOR_HANDLERS = {
    "ETFs": {"asset_path": "fund", "query": {"mod": "mw_quote_tab"}, "parser": "ohlcv_table"},
}
for _s in STOCK_SECTORS:
    SECTOR_HANDLERS[_s] = {"asset_path": "stock", "query": {}, "parser": "ohlcv_table"}

# 预留分组：后续实现时，把对应配置加入 SECTOR_HANDLERS 即可（asset_path 为 MarketWatch 的路径参考）
# 注意：这些分组在数据库中的表结构（get_table_type）与股票不同，写入时会自动按表类型过滤字段
RESERVED_SECTORS = {
    "Bonds":       "bond        例: /investing/bond/tmubmusd10y?countrycode=bx",
    "Currencies":  "currency    例: /investing/currency/eurusd",
    "Crypto":      "cryptocurrency 例: /investing/cryptocurrency/btcusd",
    "Indices":     "index       例: /investing/index/spx",
    "Commodities": "future      例: /investing/future/gc00",
}

# ================= 防止系统休眠控制 =================
_caffeinate_proc = None


def start_caffeinate():
    global _caffeinate_proc
    if platform.system() == 'Darwin':
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
    pass


class CaptchaBlockedError(ScrapeError):
    pass


# ================= 1. 数据库与 JSON 操作 =================

def get_table_type(sector):
    """根据分组判断表结构类型（与 YF_Today 保持一致）"""
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
    """反转 Symbol 映射表：{"BTC-USD": "Bitcoin"} -> {"Bitcoin": "BTC-USD"}"""
    mapping = load_json_file(json_path, "映射文件")
    if not mapping:
        return {}
    return {v: k for k, v in mapping.items()}


def load_mw_overrides(json_path):
    """MarketWatch 专用覆盖映射（可选文件）"""
    data = load_json_file(json_path, "MW 覆盖映射")
    return data if isinstance(data, dict) else {}


def atomic_write_json(json_path, data):
    """原子写入：先写临时文件再替换，防止中途崩溃导致 JSON 损坏"""
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
        tqdm.write(f"⚠️ 更新 JSON 失败 [{symbol}]: {e}")
    return False


# ================= 2. 交易日与 Symbol/URL =================

def get_last_valid_trading_date():
    """获取美股最近的一个有效开盘日（严格小于今天）"""
    try:
        nyse = mcal.get_calendar('NYSE')
        today = datetime.datetime.now().date()
        start_date = today - datetime.timedelta(days=15)
        schedule = nyse.schedule(start_date=start_date, end_date=today)
        past_days = [d for d in schedule.index.date if d < today]
        if past_days:
            return past_days[-1].strftime('%Y-%m-%d')
    except Exception as e:
        tqdm.write(f"⚠️ 计算交易日失败: {e}")
    return None


def resolve_mw_symbol(symbol, alias_to_symbol, mw_overrides):
    """
    返回 (MarketWatch 路径中的 symbol, 额外 query 参数 dict)
    优先级：MW 覆盖映射 > 通用别名映射 > 原 symbol；并将 '-' 转为 '.'（BRK-B -> brk.b）
    """
    raw = mw_overrides.get(symbol)
    if raw:
        path_part, _, qs = str(raw).partition('?')
        return path_part.strip().lower(), dict(urllib.parse.parse_qsl(qs))
    s = alias_to_symbol.get(symbol, symbol)
    s = s.strip().replace('-', '.').replace('/', '.')
    return s.lower(), {}


def build_target_url(handler, mw_symbol, extra_query):
    query = dict(handler.get("query", {}))
    query.update(extra_query or {})
    url = f"{MW_BASE_URL}/{handler['asset_path']}/{urllib.parse.quote(mw_symbol, safe='.')}/download-data"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    return url


# ================= 3. 浏览器 =================

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
    if USE_PERSISTENT_PROFILE:
        os.makedirs(MW_PROFILE_DIR, exist_ok=True)
        options.add_argument(f'--user-data-dir={MW_PROFILE_DIR}')
    options.page_load_strategy = 'eager'

    driver = webdriver.Chrome(service=Service(executable_path=CHROME_DRIVER_PATH), options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

    # 去除 navigator.webdriver 标记
    try:
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception:
        pass

    # 使用真实浏览器版本的 UA，仅去掉 "HeadlessChrome" 字样（避免版本号与内核不一致）
    try:
        ua = driver.execute_script("return navigator.userAgent")
        if 'HeadlessChrome' in ua:
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                'userAgent': ua.replace('HeadlessChrome', 'Chrome'),
                'acceptLanguage': 'en-US,en;q=0.9',
            })
    except Exception:
        pass
    return driver


def is_driver_alive(driver):
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
        # eager 模式下超时通常 DOM 已可用，停止加载后继续轮询
        try:
            driver.execute_script("window.stop();")
        except WebDriverException:
            pass


# ================= 4. 页面解析 =================

JS_COMMON = r"""
function mwCellText(el) {
    if (!el) return '';
    // Date 列有两个重复 div（固定列 + 普通列），只取第一个
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
"""

PAGE_STATE_JS = JS_COMMON + r"""
const txt = (document.body ? document.body.innerText : '').slice(0, 3000);
if (document.querySelector('iframe[src*="captcha-delivery.com"], iframe[src*="geo.captcha"]')) return 'captcha';
if (/access denied|you have been blocked|verify you are (a )?human|are you a robot/i.test(txt)) return 'captcha';
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


def wait_for_table(driver, timeout, headless):
    deadline = time.time() + timeout
    captcha_notified = False
    while True:
        state = driver.execute_script(PAGE_STATE_JS)
        if state == 'ready':
            return
        if state == 'notfound':
            raise SymbolNotFoundError(f"页面不存在或被重定向: {driver.current_url}")
        if state == 'captcha':
            if headless:
                raise CaptchaBlockedError("触发反爬验证（无头模式无法处理）")
            if not captcha_notified:
                tqdm.write(f"🧩 检测到验证码，请在浏览器窗口中手动完成（最多等待 {CAPTCHA_MANUAL_WAIT} 秒）...")
                deadline = time.time() + CAPTCHA_MANUAL_WAIT
                captcha_notified = True
        if time.time() > deadline:
            if state == 'captcha':
                raise CaptchaBlockedError("验证码等待超时")
            raise ScrapeError("等待数据表格超时")
        time.sleep(0.5)


def extract_rows(driver, symbol):
    """返回 [(date, name, price, volume, open, high, low), ...]，按日期降序"""
    result = driver.execute_script(EXTRACT_JS, MAX_ROWS_TO_EXTRACT)
    if not isinstance(result, dict):
        raise ScrapeError("JS 返回结果异常")
    if "error" in result:
        raise ScrapeError(result["error"])
    rows = []
    for r in result.get("data", []):
        date_str, price, volume, open_, high, low = r
        if price is None or price <= 0:
            continue
        volume = int(volume) if volume is not None else 0  # 与 YF_Today 一致，缺失记为 0
        rows.append((date_str, symbol, float(price), volume, open_, high, low))
    rows.sort(key=lambda x: x[0], reverse=True)
    return rows


def select_row(rows, last_valid_date):
    """
    返回 (selected_row 或 None, 提示信息 或 None)
    1. 存在日期 == last_valid_date 的行 -> 直接使用
    2. 否则按 STALE_DATA_POLICY 处理（默认与 YF_Today 一致：用最新一行并改日期）
    """
    if not rows:
        return None, "无有效数据"
    if not last_valid_date:
        return rows[0], None
    for r in rows:
        if r[0] == last_valid_date:
            return r, None

    row0 = rows[0]
    relation = "晚于" if row0[0] > last_valid_date else "早于"
    if STALE_DATA_POLICY == "skip":
        return None, f"网页最新日期 {row0[0]} {relation}预期日期 {last_valid_date}，且无匹配行，跳过（保留在 JSON）。"
    fixed = (last_valid_date,) + tuple(row0[1:])
    return fixed, f"网页最新日期 {row0[0]} {relation}预期日期 {last_valid_date}，且无匹配行，使用最新数据并修改日期为 {last_valid_date} 写入。"


# ================= 5. 主流程 =================

def build_task_list(tasks_dict, only_groups=None):
    task_list, reserved_pending, unknown_pending = [], {}, {}
    for group, symbols in tasks_dict.items():
        if not symbols:
            continue
        if only_groups and group not in only_groups:
            continue
        handler = SECTOR_HANDLERS.get(group)
        if handler is None:
            if group in RESERVED_SECTORS:
                reserved_pending[group] = len(symbols)
            else:
                unknown_pending[group] = len(symbols)
            continue
        for sym in dict.fromkeys(symbols):  # 去重且保持顺序
            task_list.append((sym, group, handler))
    return task_list, reserved_pending, unknown_pending


def scrape_marketwatch(headless=True, only_groups=None):
    tasks_dict = load_tasks_from_json(SECTORS_JSON_PATH)
    alias_to_symbol = load_alias_mapping(SYMBOL_MAPPING_PATH)
    mw_overrides = load_mw_overrides(MW_SYMBOL_OVERRIDE_PATH)

    last_valid_date = get_last_valid_trading_date()
    if last_valid_date:
        tqdm.write(f"📅 计算得出的最近有效开盘日为: {last_valid_date}")
    else:
        tqdm.write("⚠️ 无法计算最近有效开盘日，将使用网页原始日期。")

    task_list, reserved_pending, unknown_pending = build_task_list(tasks_dict, only_groups)

    for g, n in reserved_pending.items():
        tqdm.write(f"⏭️  分组 [{g}] 有 {n} 个待抓取项，MarketWatch 爬虫暂未实现（已预留: {RESERVED_SECTORS[g]}），跳过。")
    for g, n in unknown_pending.items():
        tqdm.write(f"⏭️  分组 [{g}] 有 {n} 个待抓取项，不在本爬虫支持范围内，跳过。")

    if not task_list:
        tqdm.write("✅ 支持的分组中没有待抓取的 Symbol，任务结束。")
        return {"success": [], "failed": [], "not_found": [], "skipped": [], "aborted": False}

    tqdm.write(f"共加载 {len(task_list)} 个待抓取任务。（模式: {'无头' if headless else '有界面'}）")

    try:
        driver = create_driver(headless)
    except Exception as e:
        tqdm.write(f"❌ Selenium 启动失败: {e}")
        if USE_PERSISTENT_PROFILE:
            tqdm.write(f"   提示：若提示 Profile 被占用，请关闭使用 {MW_PROFILE_DIR} 的浏览器进程。")
        return {"success": [], "failed": [t[0] for t in task_list], "not_found": [], "skipped": [], "aborted": True}

    stats = {"success": [], "failed": [], "not_found": [], "skipped": [], "aborted": False}
    consecutive_blocks = 0

    try:
        pbar = tqdm(task_list, desc="总体进度", position=0)
        for idx, (symbol, group, handler) in enumerate(pbar):
            table_type = get_table_type(group)
            mw_symbol, extra_q = resolve_mw_symbol(symbol, alias_to_symbol, mw_overrides)
            target_url = build_target_url(handler, mw_symbol, extra_q)

            if mw_symbol != symbol.lower():
                pbar.set_description(f"处理中: {symbol} (转译为 {mw_symbol}) [{group}]")
            else:
                pbar.set_description(f"处理中: {symbol} [{group}]")

            outcome = None
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    load_page(driver, target_url)
                    wait_for_table(driver, TABLE_WAIT_TIMEOUT, headless)

                    rows = extract_rows(driver, symbol)
                    if not rows:
                        raise ScrapeError("提取到的数据为空")

                    selected_row, note = select_row(rows, last_valid_date)
                    if note:
                        tqdm.write(f"⚠️ [{symbol}] {note}")
                    if selected_row is None:
                        outcome = "skipped"
                        break

                    if not insert_data_to_db(DB_PATH, group, [selected_row], table_type):
                        raise ScrapeError("数据库写入失败")

                    remove_symbol_from_json(SECTORS_JSON_PATH, group, symbol)
                    tqdm.write(f"[{symbol}] 成功写入 1 条数据 ({selected_row[0]} | price={selected_row[2]} "
                               f"vol={selected_row[3]} O={selected_row[4]} H={selected_row[5]} L={selected_row[6]}) 到 {group} 表。")
                    outcome = "success"
                    consecutive_blocks = 0
                    break

                except SymbolNotFoundError as e:
                    tqdm.write(f"❓ [{symbol}] MarketWatch 未找到该代码（{mw_symbol}）: {str(e)[:120]}。"
                               f"可在 Symbol_mapping_mw.json 中添加映射。")
                    outcome = "not_found"
                    break

                except CaptchaBlockedError as e:
                    consecutive_blocks += 1
                    tqdm.write(f"🛑 [{symbol}] 被反爬拦截 ({consecutive_blocks}/{MAX_CONSECUTIVE_BLOCKS}): {e}")
                    if consecutive_blocks >= MAX_CONSECUTIVE_BLOCKS:
                        stats["aborted"] = True
                        break
                    time.sleep(BLOCK_BACKOFF_SECONDS * attempt + random.uniform(0, 5))

                except Exception as e:
                    if isinstance(e, WebDriverException) and not is_driver_alive(driver):
                        tqdm.write(f"♻️ 浏览器会话已失效，正在重建...")
                        safe_quit(driver)
                        try:
                            driver = create_driver(headless)
                        except Exception as ce:
                            tqdm.write(f"❌ 浏览器重建失败: {ce}")
                            stats["aborted"] = True
                            break
                    if attempt < MAX_RETRIES:
                        time.sleep(2 * attempt)
                    else:
                        tqdm.write(f"❌ [{symbol}] 抓取失败 (已重试 {MAX_RETRIES} 次): {str(e)[:120]}")

            if outcome is None:
                outcome = "failed"
            stats[outcome].append(f"{group}:{symbol}")

            if stats["aborted"]:
                tqdm.write("🛑 连续被反爬拦截或浏览器无法恢复，终止本轮任务。"
                           "建议稍后使用 --headful 运行一次并手动完成验证。")
                break

            if idx < len(task_list) - 1:
                time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
    finally:
        safe_quit(driver)
        tqdm.write("🎉 所有任务执行完毕。")

    tqdm.write(f"📊 统计：成功 {len(stats['success'])} | 失败 {len(stats['failed'])} | "
               f"未找到 {len(stats['not_found'])} | 跳过 {len(stats['skipped'])}")
    if stats["failed"]:
        tqdm.write(f"   失败列表: {', '.join(stats['failed'])}")
    if stats["not_found"]:
        tqdm.write(f"   未找到列表: {', '.join(stats['not_found'])}")
    return stats


def run_check_yesterday_if_empty():
    """JSON 全部清空才执行 Check_yesterday.py（与 YF_Today 行为一致）"""
    final_tasks = load_tasks_from_json(SECTORS_JSON_PATH)
    is_empty = all(len(v) == 0 for v in final_tasks.values()) if final_tasks else True

    if is_empty:
        print("✅ Sectors_empty.json 已全部清空，开始执行 Check_yesterday.py...")
        try:
            subprocess.run([sys.executable, CHECK_YESTERDAY_SCRIPT_PATH, "--ignore_sectors"],
                           check=True, capture_output=True, text=True, encoding='utf-8')
            print("✅ Check_yesterday.py 执行完毕。")
        except subprocess.CalledProcessError as e:
            print(f"❌ Check_yesterday 返回错误码 {e.returncode}:\n{(e.stderr or '')[-1000:]}")
        except Exception as e:
            print(f"❌ 调用 Check_yesterday 出错: {e}")
    else:
        print("⚠️ Sectors_empty.json 中仍有未完成的任务，跳过执行 Check_yesterday.py。")


def parse_args():
    parser = argparse.ArgumentParser(description="MarketWatch 每日数据抓取")
    parser.add_argument("--headful", action="store_true", help="显示浏览器窗口（可手动处理验证码）")
    parser.add_argument("--groups", nargs="+", default=None, help="只抓取指定分组，例如 --groups ETFs Technology")
    parser.add_argument("--no-check", action="store_true", help="结束后不调用 Check_yesterday.py")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    start_caffeinate()
    try:
        scrape_marketwatch(headless=not args.headful, only_groups=args.groups)
        if not args.no_check:
            run_check_yesterday_if_empty()
    finally:
        stop_caffeinate()