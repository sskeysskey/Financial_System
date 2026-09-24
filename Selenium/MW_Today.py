# -*- coding: utf-8 -*-
"""
MW_Today.py
从 MarketWatch 抓取 Sectors_empty.json 中各分组的最新一日数据，写入 Finance.db（组名即表名），
成功后从 JSON 中移除该 symbol。

支持分组：
  - ETFs + 11 个股票分组      -> download-data 历史表格 (OHLCV)
  - Bonds / Currencies / Crypto / Indices / Commodities -> 行情概览页的实时价格

用法:
    python MW_Today.py                      # 默认无头模式
    python MW_Today.py --headful            # 有界面（首次运行 / 遇到验证码时推荐）
    python MW_Today.py --groups ETFs Energy # 只跑指定分组
    python MW_Today.py --dry-run            # 只抓取并打印，不写库、不改 JSON（验证映射用）
    python MW_Today.py --no-sanity          # 关闭价格偏差校验
    python MW_Today.py --no-check           # 结束后不调用 Check_yesterday.py
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
# 可选：MarketWatch 专用覆盖映射（不存在则忽略）。支持两种格式（可混用）：
#   平铺: {"BRK-B": "brk.b"}
#   分组: {"Indices": {"UK100": "ukx?countrycode=uk"}, "Commodities": {"Rice": ["rr00", "zr00"]}}
# 值中可带"品种类型/"前缀以覆盖分组默认的 URL 类型（同时页面类型校验也随之改变），例如：
#   {"Currencies": {"DXY": "index/dxy"}}  -> https://www.marketwatch.com/investing/index/dxy
MW_SYMBOL_OVERRIDE_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping_mw.json")
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

# 独立的浏览器 Profile（保存 Cookie，降低被反爬拦截概率；不要与正在运行的 Chrome 共用）
# 注意：Profile 会产生大量文件，必须放在 Git 仓库之外。可用环境变量 MW_PROFILE_DIR 覆盖。
USE_PERSISTENT_PROFILE = True
MW_PROFILE_DIR = os.environ.get("MW_PROFILE_DIR") or os.path.join(DOWNLOADS_DIR, "backup", "mw_chrome_profile")
# 旧版本放在仓库内的位置：若存在，首次运行时会自动迁移到 MW_PROFILE_DIR（保留 Cookie）
LEGACY_MW_PROFILE_DIRS = [
    os.path.join(FINANCIAL_SYSTEM_DIR, "Selenium", "mw_chrome_profile"),
]
# 每次运行结束后清理 Profile 中的纯缓存目录（不影响 Cookie / 登录状态），防止目录无限膨胀
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
PAGE_LOAD_TIMEOUT = 30          # driver.get 超时
TABLE_WAIT_TIMEOUT = 15         # 等待历史表格出现的超时
QUOTE_WAIT_TIMEOUT = 15         # 等待行情价格出现的超时
CAPTCHA_MANUAL_WAIT = 180       # 有界面模式下，等待手动完成验证码的最长时间
MAX_RETRIES = 3
MAX_CONSECUTIVE_BLOCKS = 3      # 连续被反爬拦截次数达到此值，终止整轮任务
BLOCK_BACKOFF_SECONDS = 10      # 被拦截后的退避基数（秒）
REQUEST_DELAY_RANGE = (2.0, 4.5)  # 每个 symbol 之间的随机间隔（秒）
MAX_ROWS_TO_EXTRACT = 5         # 从表格顶部提取的行数（用于日期匹配）

# 日期对不上时的策略：
#   "overwrite_date" -> 与 YF_Today 保持一致：取最新数据并把日期改为最近有效开盘日写入
#   "skip"           -> 不写入，保留在 JSON 中等待下次
STALE_DATA_POLICY = "overwrite_date"

# 价格合理性校验（仅对行情页分组生效）：与库中该 name 上一条价格比较，偏差超过阈值视为异常
PRICE_SANITY_CHECK = True
PRICE_SANITY_THRESHOLD = 0.25   # 25%
PRICE_SANITY_ACTION = "skip"    # "skip" -> 不写入并保留在 JSON；"warn" -> 仅提示仍写入

# ---- MarketWatch URL 中的品种类型 -> 页面 body 上 symbol--xxx 类名 ----
# 用于映射中带"类型/"前缀时（如 "index/dxy"），自动切换页面类型校验
ASSET_PATH_TO_BODY_TYPE = {
    "stock": "stock",
    "fund": "fund",
    "bond": "bond",
    "currency": "currency",
    "cryptocurrency": "cryptocurrency",
    "index": "index",
    "future": "future",
}

# ---- 分组 -> 抓取处理器 ----
STOCK_SECTORS = [
    'Basic_Materials', 'Communication_Services', 'Consumer_Cyclical',
    'Consumer_Defensive', 'Energy', 'Financial_Services', 'Healthcare',
    'Industrials', 'Real_Estate', 'Technology', 'Utilities',
]

# parser:
#   ohlcv_table -> /download-data 历史表格
#   quote       -> 行情概览页 (h2.intraday__price)
# resolver: symbol -> MarketWatch 路径的推导规则（内置/用户覆盖映射优先）
# expect_type: 页面 body 上的 symbol--xxx 类名，用于识别是否跳转到了错误品种页
#              （若映射值带"类型/"前缀，则以该类型为准）
# row_style:
#   price_only -> (date, name, price, volume=0)，由 insert_data_to_db 按表结构过滤
#   flat_ohlc  -> open/high/low 均等于 price，volume=0（Crypto 表是 expanded 结构）
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

# 内置映射（优先级低于 Symbol_mapping_mw.json，高于推导规则）。值可以是字符串或候选列表（依次尝试）
# 值格式: "[品种类型/]代码[?查询参数]"，品种类型省略时使用分组默认 asset_path
MW_BUILTIN_OVERRIDES = {
    "Bonds": {
        "US10Y": "tmubmusd10y?countrycode=bx",
        "US2Y": "tmubmusd02y?countrycode=bx",
        "US30Y": "tmubmusd30y?countrycode=bx",
    },
    "Currencies": {
        # 美元指数在 MarketWatch 属于"指数"：/currency/dxy 会被重定向到 /index/dxy（body 为 symbol--index）
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
        # ---- 以下未经你确认，首次请用 --dry-run 核对页面名称；UK100(^BUK100P)/panEURO100(^N100)
        #      与 MarketWatch 常见指数口径不同，故不内置，需要时写到 Symbol_mapping_mw.json ----
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
        "Brent": "brn00?countrycode=uk",   # ICE 布伦特，推导规则 bz00 在 MW 不存在
        "YuMi": "c00",                     # CBOT 玉米在 MW 为 c00（非 zc00）
        "Soybean": "s00",                  # 大豆 s00（非 zs00）
        "Oat": "o00",                      # 找不到时自动回退到推导规则 zo00
        "Rice": "rr00",                    # 找不到时自动回退到推导规则 zr00
        "LeanHogs": "lh00",                # 瘦肉猪 lh00（非 he00）
        "LiveCattle": "lc00",              # 活牛 lc00（非 le00）
    },
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
    def __init__(self, msg, actual_type=None, final_url=None):
        super().__init__(msg)
        self.actual_type = actual_type    # 类型不符时，页面实际的 symbol--xxx 类型
        self.final_url = final_url        # 重定向后的最终 URL


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


def get_last_db_price(db_path, table_name, name, before_date):
    """读取库中该 name 在 before_date 之前的最后一条价格（用于合理性校验），表不存在返回 None"""
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            cur = conn.execute(
                f'SELECT price FROM "{table_name}" WHERE name = ? AND date < ? AND price IS NOT NULL '
                f'ORDER BY date DESC LIMIT 1', (name, before_date))
            r = cur.fetchone()
            return float(r[0]) if r and r[0] is not None else None
        finally:
            conn.close()
    except sqlite3.Error:
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


# ================= 2. 交易日 =================

def get_prev_trading_date(ref_date):
    """严格小于 ref_date 的最近一个 NYSE 交易日 ('YYYY-MM-DD')；日历异常时退化为"前一个工作日" """
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
    """获取美股最近的一个有效开盘日（严格小于今天）"""
    try:
        return get_prev_trading_date(datetime.datetime.now().date())
    except Exception as e:
        tqdm.write(f"⚠️ 计算交易日失败: {e}")
        return None


_MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}


def parse_quote_date(text):
    """解析 'Sep 23, 2026 3:34 a.m.' / 'Sept. 23, 2026 at 3:46 a.m.' / '09/23/2026' -> '2026-09-23'"""
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
# 候选统一为三元组: (asset_override 或 None, mw_path, extra_query_dict)

def _parse_override_value(value):
    """
    'tmubmusd10y?countrycode=bx' / 'index/dxy' / ['rr00', 'zr00']
      -> [(asset_override 或 None, path, query_dict), ...]
    """
    values = value if isinstance(value, (list, tuple)) else [value]
    out = []
    for v in values:
        if not v:
            continue
        path_part, _, qs = str(v).strip().partition('?')
        path_part = path_part.strip().strip('/').lower()
        # 兼容用户直接粘贴 "investing/index/dxy"
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
    """按分组规则推导 MarketWatch 路径（兜底方案）"""
    rule = handler.get("resolver")
    alias = alias_to_symbol.get(symbol)

    if rule == "stock":
        s = (alias or symbol).strip().replace('-', '.').replace('/', '.')
        return [(None, s.lower(), {})]
    if rule == "name_lower":            # Currencies: CNYINR -> cnyinr
        s = re.sub(r'[^a-z0-9]', '', symbol.lower())
        return [(None, s, {})] if s else []
    if rule == "crypto":                # Bitcoin -> BTC-USD -> btcusd
        s = re.sub(r'[^a-z0-9]', '', (alias or symbol).lower())
        return [(None, s, {})] if s else []
    if rule == "index":                 # ^RUT -> rut
        if alias and alias.startswith('^'):
            s = re.sub(r'[^a-z0-9]', '', alias[1:].lower())
            return [(None, s, {})] if s else []
        return []
    if rule == "future":                # GC=F -> gc00
        if alias and alias.upper().endswith('=F'):
            root = re.sub(r'[^a-z0-9]', '', alias[:-2].lower())
            return [(None, root + "00", {})] if root else []
        return []
    return []                           # override_only (Bonds) 等


def resolve_mw_candidates(symbol, group, handler, alias_to_symbol, mw_overrides):
    """
    返回候选列表 [(asset_override, mw_path, extra_query), ...]，依次尝试直到找到页面
    优先级：Symbol_mapping_mw.json(分组) > Symbol_mapping_mw.json(平铺) > 内置映射 > 推导规则
    """
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
    """用于日志显示：分组默认类型只显示代码，覆盖类型显示 '类型/代码'"""
    return f"{asset}/{mw_path}" if asset and asset != handler['asset_path'] else mw_path


def expected_type_for(handler, asset):
    """映射指定了品种类型时，以该类型作为页面校验依据；否则用分组默认 expect_type"""
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
    """从重定向后的 URL 推出可用的映射写法：.../investing/index/dxy?countrycode=xx -> 'index/dxy?countrycode=xx'"""
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
    """向上查找包含 .git 的目录，找不到返回 None"""
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
    """
    1. 旧 Profile（位于仓库内）自动迁移到 MW_PROFILE_DIR，保留 Cookie
    2. 确保目录存在
    3. 若目标目录位于 Git 仓库内，给出警告
    """
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
                tqdm.write(f"⚠️ [Profile] 迁移旧 Profile 失败（请手动移动或删除）: {e}")
        else:
            tqdm.write(f"⚠️ [Profile] 发现遗留的旧 Profile 目录（新目录已存在，已不再使用），"
                       f"可手动删除: {legacy}")

    os.makedirs(target, exist_ok=True)

    git_root = _find_git_root(target)
    if git_root:
        tqdm.write(f"⚠️ [Profile] 浏览器 Profile 目录位于 Git 仓库 {git_root} 内，会产生大量文件！"
                   f"请修改 MW_PROFILE_DIR 或将其加入 .gitignore。")


def clean_profile_cache():
    """浏览器退出后清理纯缓存目录（保留 Cookies / Local Storage 等身份数据）"""
    if not (USE_PERSISTENT_PROFILE and CLEAN_PROFILE_CACHE_ON_EXIT):
        return
    root = os.path.abspath(MW_PROFILE_DIR)
    if not os.path.isdir(root):
        return
    time.sleep(1)  # 等 Chrome 子进程释放文件句柄
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
    options.add_argument('--disk-cache-size=52428800')   # 磁盘缓存上限 50MB
    if USE_PERSISTENT_PROFILE:
        os.makedirs(MW_PROFILE_DIR, exist_ok=True)
        options.add_argument(f'--user-data-dir={os.path.abspath(MW_PROFILE_DIR)}')
    options.page_load_strategy = 'eager'

    driver = webdriver.Chrome(service=Service(executable_path=CHROME_DRIVER_PATH), options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

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
        try:
            driver.execute_script("window.stop();")
        except WebDriverException:
            pass


def detect_body_symbol_type(driver):
    """读取页面 body 上的 symbol--xxx 类型（如 index / currency），失败返回 None"""
    try:
        bc = driver.execute_script("return document.body ? (document.body.className || '') : '';") or ''
    except WebDriverException:
        return None
    m = re.search(r'(?:^|\s)symbol--([a-z0-9_-]+)', bc, re.I)
    return m.group(1).lower() if m else None


# ================= 5. 页面解析：历史表格 (ETFs / 股票) =================

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


def _wait_loop(driver, timeout, headless, state_fn, timeout_msg, expect_type=None):
    """通用等待循环：state_fn() 返回 ready/notfound/mismatch/captcha/loading"""
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
                f"页面品种类型为 '{actual or '?'}'，与预期 '{expect_type or '?'}' 不符"
                f"（被重定向到其他类型页面）: {final_url}",
                actual_type=actual, final_url=final_url)
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
            raise ScrapeError(timeout_msg)
        time.sleep(0.5)


def wait_for_table(driver, timeout, headless):
    _wait_loop(driver, timeout, headless, lambda: driver.execute_script(PAGE_STATE_JS), "等待数据表格超时")


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
        volume = int(volume) if volume is not None else 0
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


# ================= 6. 页面解析：行情概览页 (Bonds/Currencies/Crypto/Indices/Commodities) =================

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
    // 兼容 intraday__price（BEM 双下划线）与 intraday_price 两种写法
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
    ts: qTimestamp(),
    status: qText(st),
    company: qText(document.querySelector('h1[class*="company"]')),
    body_class: document.body ? (document.body.className || '') : '',
    url: location.href
};
"""


def wait_for_quote(driver, timeout, headless, expect_type):
    _wait_loop(driver, timeout, headless,
               lambda: driver.execute_script(QUOTE_STATE_JS, expect_type or ""), "等待行情价格超时",
               expect_type=expect_type)


def extract_quote(driver):
    r = driver.execute_script(QUOTE_EXTRACT_JS)
    if not isinstance(r, dict):
        raise ScrapeError("JS 返回结果异常")
    if r.get("price") is None:
        raise ScrapeError("未解析到价格")
    return r


def build_quote_row(symbol, handler, quote, last_valid_date):
    """
    返回 (row 或 None, 提示信息 或 None)
    写入日期规则：统一为最近有效开盘日（与表格型分组一致）；页面时间仅用于"过期"校验。
    """
    price = float(quote["price"])
    if not handler.get("allow_non_positive") and price <= 0:
        raise ScrapeError(f"价格异常: {quote.get('price_raw')}")

    page_date = parse_quote_date(quote.get("ts"))
    notes = []

    if last_valid_date:
        target_date = last_valid_date
        if page_date is None:
            notes.append(f"未能解析页面更新时间（'{quote.get('ts')}'），按 {last_valid_date} 写入。")
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
    """返回 (是否通过, 说明)"""
    prev = get_last_db_price(DB_PATH, table_name, name, date_str)
    if prev is None or prev == 0:
        return True, None
    dev = abs(price - prev) / abs(prev)
    if dev > PRICE_SANITY_THRESHOLD:
        return False, (f"价格 {price} 与库中上一条 {prev} 偏差 {dev:.1%}，超过阈值 {PRICE_SANITY_THRESHOLD:.0%}")
    return True, None


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
        for sym in dict.fromkeys(symbols):  # 去重且保持顺序
            task_list.append((sym, group, handler))
    return task_list, unknown_pending


def run_single_url(driver, ctx, url, symbol, group, handler, last_valid_date, opts, expect_type=None):
    """
    对单个 URL 执行抓取（含重试）。返回 (outcome, driver)
    outcome: success / skipped / not_found / failed
    """
    headless = opts["headless"]
    table_type = get_table_type(group)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            load_page(driver, url)
            page_info = ""

            if handler["parser"] == "ohlcv_table":
                wait_for_table(driver, TABLE_WAIT_TIMEOUT, headless)
                ctx["consecutive_blocks"] = 0
                rows = extract_rows(driver, symbol)
                if not rows:
                    raise ScrapeError("提取到的数据为空")
                selected_row, note = select_row(rows, last_valid_date)
            else:
                wait_for_quote(driver, QUOTE_WAIT_TIMEOUT, headless, expect_type)
                ctx["consecutive_blocks"] = 0
                quote = extract_quote(driver)
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

            if opts["dry_run"]:
                tqdm.write(f"🔍 [DRY-RUN] [{symbol}] -> {group}: {detail} {page_info}\n   URL: {url}")
                return "success", driver

            if not insert_data_to_db(DB_PATH, group, [selected_row], table_type):
                raise ScrapeError("数据库写入失败")
            remove_symbol_from_json(SECTORS_JSON_PATH, group, symbol)
            tqdm.write(f"[{symbol}] 成功写入 1 条数据 ({detail}) 到 {group} 表。{page_info}")
            return "success", driver

        except SymbolNotFoundError as e:
            tqdm.write(f"❓ [{symbol}] MarketWatch 未找到: {str(e)[:200]}")
            if e.actual_type:
                hint = suggest_override_from_url(e.final_url)
                if hint:
                    ctx["mismatch_hints"].append(hint)
            return "not_found", driver

        except CaptchaBlockedError as e:
            ctx["consecutive_blocks"] += 1
            tqdm.write(f"🛑 [{symbol}] 被反爬拦截 ({ctx['consecutive_blocks']}/{MAX_CONSECUTIVE_BLOCKS}): {e}")
            if ctx["consecutive_blocks"] >= MAX_CONSECUTIVE_BLOCKS:
                ctx["aborted"] = True
                return "failed", driver
            time.sleep(BLOCK_BACKOFF_SECONDS * attempt + random.uniform(0, 5))

        except Exception as e:
            if isinstance(e, WebDriverException) and not is_driver_alive(driver):
                tqdm.write("♻️ 浏览器会话已失效，正在重建...")
                safe_quit(driver)
                try:
                    driver = create_driver(headless)
                except Exception as ce:
                    tqdm.write(f"❌ 浏览器重建失败: {ce}")
                    ctx["aborted"] = True
                    return "failed", None
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
            else:
                tqdm.write(f"❌ [{symbol}] 抓取失败 (已重试 {MAX_RETRIES} 次): {str(e)[:150]}")
    return "failed", driver


def scrape_marketwatch(headless=True, only_groups=None, dry_run=False, sanity=True):
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

    tqdm.write(f"共加载 {len(task_list)} 个待抓取任务。（模式: {'无头' if headless else '有界面'}"
               f"{' | DRY-RUN 不写库' if dry_run else ''}{' | 已关闭价格校验' if not sanity else ''}）")

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

    stats = {"success": [], "failed": [], "not_found": [], "skipped": [], "aborted": False}
    ctx = {"consecutive_blocks": 0, "aborted": False, "mismatch_hints": []}
    opts = {"headless": headless, "dry_run": dry_run, "sanity": sanity}

    try:
        pbar = tqdm(task_list, desc="总体进度", position=0)
        for idx, (symbol, group, handler) in enumerate(pbar):
            candidates = resolve_mw_candidates(symbol, group, handler, alias_to_symbol, mw_overrides)
            if not candidates:
                tqdm.write(f"❓ [{symbol}] 分组 {group} 无法推导 MarketWatch 地址，"
                           f"请在 Symbol_mapping_mw.json 中添加，例如 {{\"{group}\": {{\"{symbol}\": \"xxx\"}}}}")
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
                                                 last_valid_date, opts, expect_type=expect_type)
                if outcome != "not_found" or ctx["aborted"]:
                    break
                if c_idx < len(candidates) - 1:
                    tqdm.write(f"   ↪ [{symbol}] 尝试下一个候选地址: {labels[c_idx + 1]}")
                    time.sleep(random.uniform(*REQUEST_DELAY_RANGE))

            if outcome == "not_found":
                tqdm.write(f"   [{symbol}] 所有候选地址均未找到（{', '.join(labels)}），"
                           f"可在 Symbol_mapping_mw.json 中添加映射。")
                for hint in dict.fromkeys(ctx["mismatch_hints"]):
                    tqdm.write(f"   💡 页面被重定向到其他品种类型。若确认该页面就是目标品种（请用 --dry-run 核对页面名称），"
                               f"可添加映射: {{\"{group}\": {{\"{symbol}\": \"{hint}\"}}}}")
            stats[outcome].append(f"{group}:{symbol}")

            if ctx["aborted"]:
                stats["aborted"] = True
                tqdm.write("🛑 连续被反爬拦截或浏览器无法恢复，终止本轮任务。"
                           "建议稍后使用 --headful 运行一次并手动完成验证。")
                break

            if idx < len(task_list) - 1:
                time.sleep(random.uniform(*REQUEST_DELAY_RANGE))
    finally:
        safe_quit(driver)
        clean_profile_cache()
        tqdm.write("🎉 所有任务执行完毕。")

    tqdm.write(f"📊 统计：成功 {len(stats['success'])} | 失败 {len(stats['failed'])} | "
               f"未找到 {len(stats['not_found'])} | 跳过 {len(stats['skipped'])}")
    for key, label in (("failed", "失败"), ("not_found", "未找到"), ("skipped", "跳过")):
        if stats[key]:
            tqdm.write(f"   {label}列表: {', '.join(stats[key])}")
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
    parser.add_argument("--groups", nargs="+", default=None, help="只抓取指定分组，例如 --groups Currencies Indices")
    parser.add_argument("--dry-run", action="store_true", help="只抓取并打印，不写数据库、不修改 JSON")
    parser.add_argument("--no-sanity", action="store_true", help="关闭价格偏差合理性校验")
    parser.add_argument("--no-check", action="store_true", help="结束后不调用 Check_yesterday.py")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    start_caffeinate()
    try:
        scrape_marketwatch(headless=not args.headful, only_groups=args.groups,
                           dry_run=args.dry_run, sanity=not args.no_sanity)
        if not args.no_check and not args.dry_run:
            run_check_yesterday_if_empty()
    finally:
        stop_caffeinate()