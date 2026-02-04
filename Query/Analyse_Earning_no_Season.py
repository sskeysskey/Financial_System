import json
import sqlite3
import os
import datetime

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 1. 配置文件和路径 ---
# 使用 os.path.expanduser('~') 获取用户主目录，增强可移植性
BASE_PATH = USER_HOME

SYMBOL_TO_TRACE = ""
TARGET_DATE = ""

# SYMBOL_TO_TRACE = "KO"
# TARGET_DATE = "2026-01-07"

# 动态生成日志路径，不再写死用户名
LOG_FILE_PATH = os.path.join(BASE_PATH, "Downloads", "No_Season_trace_log.txt")

PATHS = {
    "config_dir": os.path.join(BASE_CODING_DIR, 'Financial_System', 'Modules'),
    "db_dir": os.path.join(BASE_CODING_DIR, 'Database'),
    "sectors_json": lambda config_dir: os.path.join(config_dir, 'Sectors_All.json'),
    "panel_json": lambda config_dir: os.path.join(config_dir, 'Sectors_panel.json'),
    "blacklist_json": lambda config_dir: os.path.join(config_dir, 'Blacklist.json'),
    "description_json": lambda config_dir: os.path.join(config_dir, 'description.json'),
    "tags_setting_json": lambda config_dir: os.path.join(config_dir, 'tags_filter.json'),
    "earnings_history_json": lambda config_dir: os.path.join(config_dir, 'Earning_History.json'),
    "db_file": lambda db_dir: os.path.join(db_dir, 'Finance.db'),
}

# 动态生成完整路径
CONFIG_DIR = PATHS["config_dir"]
DB_DIR = PATHS["db_dir"]
DB_FILE = PATHS["db_file"](DB_DIR)
SECTORS_JSON_FILE = PATHS["sectors_json"](CONFIG_DIR)
BLACKLIST_JSON_FILE = PATHS["blacklist_json"](CONFIG_DIR)
PANEL_JSON_FILE = PATHS["panel_json"](CONFIG_DIR)
DESCRIPTION_JSON_FILE = PATHS["description_json"](CONFIG_DIR)
TAGS_SETTING_JSON_FILE = PATHS["tags_setting_json"](CONFIG_DIR)
EARNING_HISTORY_JSON_FILE = PATHS["earnings_history_json"](CONFIG_DIR)

# --- 2. 可配置参数 ---

# CONFIG = {
#     "TARGET_SECTORS": {
#         "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
#         "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
#         "Industrials", "Real_Estate", "Technology", "Utilities"
#     },
#     # ========== 代码修改开始 1/3：新增中国概念股成交额阈值 ==========
#     "TURNOVER_THRESHOLD": 50_000_000,
#     "TURNOVER_THRESHOLD_CHINA": 400_000_000,  # 新增：中国概念股的成交额阈值

#     "RECENT_EARNINGS_COUNT": 2,
#     "MARKETCAP_THRESHOLD": 200_000_000_000,  # 2000亿
#     "MARKETCAP_THRESHOLD_MEGA": 500_000_000_000,  # 5000亿

#     "COND5_WINDOW_DAYS": 6,

#     # 严格筛选标准
#     "PRICE_DROP_PERCENTAGE_LARGE": 0.079,  # <2000亿=7.9%
#     "PRICE_DROP_PERCENTAGE_SMALL": 0.06,   # 2000亿 ≤ 市值 < 5000亿 = 6%
#     "PRICE_DROP_PERCENTAGE_MEGA": 0.05,    # ≥5000亿=5%
    
#     # 普通宽松筛选标准
#     "RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.07,  # <2000亿=7%
#     "RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.05,  # ≥2000亿=5%

#     # 新增：次宽松筛选标准
#     "SUB_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.06,  # <2000亿=6%
#     "SUB_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.04,  # ≥2000亿=4%

#     # 最宽松筛选标准
#     "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.05,  # <2000亿=5%
#     "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.03,  # ≥2000亿=3%

#     # 触发“最宽松”标准的财报收盘价价差百分比 (条件C)
#     "ER_PRICE_DIFF_THRESHOLD": 0.04,

#     # 触发宽松筛选的最小分组数量 (仅对 PE_valid 组生效)
#     "MIN_PE_VALID_SIZE_FOR_RELAXED_FILTER": 4,

#     # 回撤阀值 6%：最新收盘价比最新交易日前10天收盘价的最低值高不超过5%（如果10天内有财报，则将财报日收盘价作为最低值）
#     "MAX_INCREASE_PERCENTAGE_SINCE_LOW": 0.06,

# # 【新增】热门板块回撤容忍度：如果属于 HOT_TAGS，则允许放宽到 12%
#     "MAX_INCREASE_PERCENTAGE_SINCE_LOW_HOT": 0.12, 

#     # 条件1c 的专属参数：最新价比最新财报收盘价低至少 X%
#     "PRICE_DROP_FOR_COND1C": 0.14,

#     # 条件3参数
#     "COND3_DROP_THRESHOLDS": [0.07, 0.15],  # 7% 与 15%
#     "COND3_LOOKBACK_DAYS": 60,

#     # 条件4参数: 财报日至今最高价相比最新价的涨幅阈值
#     "COND4_RISE_THRESHOLD": 0.07,  # 7%

#     # ========== 新增：条件5的参数 ==========
#     "COND5_ER_TO_HIGH_THRESHOLD": 0.3,  # 财报日到最高价的涨幅阈值 30%
#     "COND5_HIGH_TO_LATEST_THRESHOLD": 0.079,  # 最高价到最新价的跌幅阈值 7.9%
#     "PE_DEEP_DROP_THRESHOLD": 0.14, # 条件1-5后的深跌判断1
#     "PE_DEEP_MAX_DROP_THRESHOLD": 0.15, # 条件1-5后的深跌判断2
#     "PE_DEEP_HIGH_SINCE_ER_THRESHOLD": 0.18, # 条件1-5后的深跌判断3

#     # ========== 代码修改开始 1/4：新增条件6（抄底W底）参数 ==========
#     "COND6_ER_DROP_A_THRESHOLD": 0.25,  # 财报跌幅分界线 25%
#     "COND6_LOW_DROP_B_LARGE": 0.09,     # 如果A > 25%，则B需 > 9%
#     "COND6_LOW_DROP_B_SMALL": 0.12,     # 如果A <= 25%，则B需 > 12%
#     "COND6_W_BOTTOM_MIN_PEAK_RISE": 0.015, # 例如改为 1.5%

#     # W底形态参数
#     "COND6_W_BOTTOM_PRICE_TOLERANCE": 0.038,  # 两个谷底的价格差容忍度 (3.8%)
#     "COND6_W_BOTTOM_MIN_DAYS_GAP": 3,        # 两个谷底之间的最小间隔天数
# }

CONFIG = {
    "TARGET_SECTORS": {
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    },
    # ========== 代码修改开始 1/3：新增中国概念股成交额阈值 ==========
    "TURNOVER_THRESHOLD": 100_000_000,
    "TURNOVER_THRESHOLD_CHINA": 400_000_000,  # 新增：中国概念股的成交额阈值

    "RECENT_EARNINGS_COUNT": 2,
    "MARKETCAP_THRESHOLD": 200_000_000_000,  # 2000亿
    "MARKETCAP_THRESHOLD_MEGA": 500_000_000_000,  # 5000亿

    "COND5_WINDOW_DAYS": 6,

    # 严格筛选标准
    "PRICE_DROP_PERCENTAGE_LARGE": 0.1,  # <2000亿=10%
    "PRICE_DROP_PERCENTAGE_SMALL": 0.09,   # 2000亿 ≤ 市值 < 5000亿 = 9%
    "PRICE_DROP_PERCENTAGE_MEGA": 0.07,    # ≥5000亿=7%

    # 普通宽松筛选标准
    "RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.1,  # <2000亿=10%
    "RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.08,  # ≥2000亿=8%

    # 新增：次宽松筛选标准
    "SUB_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.09,  # <2000亿=9%
    "SUB_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.07,  # ≥2000亿=7%

    # 最宽松筛选标准
    "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.07,  # <2000亿=7%
    "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.05,  # ≥2000亿=5%

    # 触发“最宽松”标准的财报收盘价价差百分比 (条件C)
    "ER_PRICE_DIFF_THRESHOLD": 0.06,

    # 触发宽松筛选的最小分组数量 (仅对 PE_valid 组生效)
    "MIN_PE_VALID_SIZE_FOR_RELAXED_FILTER": 5,

    # 回撤阀值 5%：最新收盘价比最新交易日前10天收盘价的最低值高不超过5%（如果10天内有财报，则将财报日收盘价作为最低值）
    "MAX_INCREASE_PERCENTAGE_SINCE_LOW": 0.06,

    # 【新增】热门板块回撤容忍度：如果属于 HOT_TAGS，则允许放宽到 12%
    "MAX_INCREASE_PERCENTAGE_SINCE_LOW_HOT": 0.12, 

    # 条件1c 的专属参数：最新价比最新财报收盘价低至少 X%
    "PRICE_DROP_FOR_COND1C": 0.17,

    # 条件3参数
    "COND3_DROP_THRESHOLDS": [0.09, 0.15],  # 9% 与 15%
    "COND3_LOOKBACK_DAYS": 60,

    # 条件4参数: 财报日至今最高价相比最新价的涨幅阈值
    "MARKETCAP_THRESHOLD_ULTRA": 800_000_000_000,  # 8000亿
    "COND4_RISE_THRESHOLD_LARGE": 0.09,           # > 8000亿亿使用 9%
    "COND4_RISE_THRESHOLD_SMALL": 0.11,           # <= 8000亿亿使用 11%

    # ========== 新增：条件5的参数 ==========
    "COND5_ER_TO_HIGH_THRESHOLD": 0.3,  # 财报日到最高价的涨幅阈值 30%
    "COND5_HIGH_TO_LATEST_THRESHOLD": 0.09,  # 最高价到最新价的跌幅阈值 9%
    "PE_DEEP_DROP_THRESHOLD": 0.151, # 条件1-5后的深跌判断1
    "PE_DEEP_MAX_DROP_THRESHOLD": 0.16, # 条件1-5后的深跌判断2
    "PE_DEEP_HIGH_SINCE_ER_THRESHOLD": 0.18, # 条件1-5后的深跌判断3
    "PE_DEEPER_DROP_THRESHOLD": 0.351, # 新增：条件1-5后的超深跌判断 (35.1%)

    # ========== 代码修改开始 1/4：新增条件6（抄底W底）参数 ==========
    "COND6_ER_DROP_A_THRESHOLD": 0.25,  # 财报跌幅分界线 25%
    "COND6_LOW_DROP_B_LARGE": 0.09,     # 如果A > 25%，则B需 > 9%
    "COND6_LOW_DROP_B_SMALL": 0.12,     # 如果A <= 25%，则B需 > 12%
    "COND6_W_BOTTOM_MIN_PEAK_RISE": 0.015, # 例如改为 1.5%

    # [新增] W底形态 - 底部抬高容忍天数
    # 含义：如果“财报后最低价”发生在 X 天前，则允许当前的 W 底价格高于那个最低价（视为上涨中继或底部抬高）。
    "COND6_W_BOTTOM_HIGHER_LOW_DAYS": 18, 

    # W底形态参数
    "COND6_W_BOTTOM_PRICE_TOLERANCE": 0.045,  # 两个谷底的价格差容忍度 (4.8%)
    "COND6_W_BOTTOM_MIN_DAYS_GAP": 3,        # 两个谷底之间的最小间隔天数
}

# --- 3. 辅助与文件操作模块 ---
def load_tag_settings(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        tag_blacklist = set(settings.get('BLACKLIST_TAGS', []))
        hot_tags = set(settings.get('HOT_TAGS', []))
        return tag_blacklist, hot_tags
    except Exception:
        return set(), set()

def load_all_symbols(json_path, target_sectors):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            all_sectors_data = json.load(f)
        all_symbols = []
        symbol_to_sector_map = {}
        for sector, symbols in all_sectors_data.items():
            if sector in target_sectors:
                all_symbols.extend(symbols)
                for symbol in symbols:
                    symbol_to_sector_map[symbol] = sector
        return all_symbols, symbol_to_sector_map
    except Exception as e:
        print(f"错误: 加载symbols失败: {e}")
        return None, None

def load_blacklist(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return set(data.get('newlow', []))
    except Exception:
        return set()

def load_earning_symbol_blacklist(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return set(data.get('Earning', []))
    except Exception:
        return set()

def load_symbol_tags(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        symbol_tag_map = {}
        stock_list = data.get('stocks', [])
        for item in stock_list:
            symbol = item.get('symbol')
            tags = item.get('tag', [])
            if symbol:
                symbol_tag_map[symbol] = tags
        return symbol_tag_map
    except Exception:
        return {}

def update_json_panel(symbols_list, json_path, group_name, symbol_to_note=None):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    if symbol_to_note is None:
        data[group_name] = {symbol: "" for symbol in sorted(symbols_list)}
    else:
        data[group_name] = {symbol: symbol_to_note.get(symbol, "") for symbol in sorted(symbols_list)}

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"错误: 写入JSON文件失败: {e}")

def update_earning_history_json(file_path, group_name, symbols_to_add, log_detail):
    log_detail(f"\n--- 更新历史记录文件: {os.path.basename(file_path)} -> '{group_name}' ---")
    yesterday = datetime.date.today() - datetime.timedelta(days=1)  # 获取昨天的日期
    yesterday_str = yesterday.isoformat()  # 获取 'YYYY-MM-DD' 格式的昨天日期

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log_detail("信息: 历史记录文件不存在或格式错误，将创建新的。")
        data = {}

    # 确保顶层分组存在 (e.g., 'season')
    if group_name not in data:
        data[group_name] = {}

    # 获取昨天已有的 symbol 列表，如果不存在则为空列表
    existing_symbols = data[group_name].get(yesterday_str, [])

    # 合并新旧列表，通过集合去重，然后排序
    combined_symbols = set(existing_symbols) | set(symbols_to_add)
    updated_symbols = sorted(list(combined_symbols))

    # 更新数据结构
    data[group_name][yesterday_str] = updated_symbols
    num_added = len(updated_symbols) - len(existing_symbols)

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_detail(f"成功更新历史记录。日期: {yesterday_str}, 分组: '{group_name}'.")
        log_detail(f" - 本次新增 {num_added} 个不重复的 symbol。")
        log_detail(f" - 当天总计 {len(updated_symbols)} 个 symbol。")
    except Exception as e:
        log_detail(f"错误: 写入历史记录文件失败: {e}")


# --- 4. 核心数据获取模块 ---
def build_stock_data_cache(symbols, symbol_to_sector_map, db_path, symbol_to_trace, log_detail, symbol_to_tags_map, target_date=None):
    cache = {}
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    marketcap_exists = True

    for i, symbol in enumerate(symbols):
        is_tracing = (symbol == symbol_to_trace)
        data = {'is_valid': False}
        sector_name = symbol_to_sector_map.get(symbol)
        
        if not sector_name:
            if is_tracing: log_detail(f"[{symbol}] 失败: 在板块映射中未找到该symbol。")
            continue

        # ========== 【修改点 1/3】: 财报获取增加回测日期限制 ==========
        if target_date:
            # 回测模式：只获取回测日期(含)之前的财报
            cursor.execute("SELECT date, price FROM Earning WHERE name = ? AND date <= ? ORDER BY date ASC", (symbol, target_date))
        else:
            # 正常模式：获取所有财报
            cursor.execute("SELECT date, price FROM Earning WHERE name = ? ORDER BY date ASC", (symbol,))
        # ========================================================
        
        er_rows = cursor.fetchall()
        if not er_rows:
            if is_tracing: log_detail(f"[{symbol}] 失败: 在Earning表中未找到符合日期的财报记录。")
            continue

        if is_tracing: log_detail(f"[{symbol}] 步骤1: 从Earning表获取了 {len(er_rows)} 条财报记录。")
        
        all_er_dates = [r[0] for r in er_rows]
        all_er_pcts = [r[1] for r in er_rows]
        data['all_er_pcts'] = all_er_pcts
        data['all_er_dates'] = all_er_dates
        data['latest_er_date_str'] = all_er_dates[-1]
        data['latest_er_pct'] = all_er_pcts[-1]

        if is_tracing: log_detail(f"[{symbol}] - 最新财报日: {data['latest_er_date_str']}, 最新财报涨跌幅: {data['latest_er_pct']}")

        placeholders = ', '.join(['?'] * len(all_er_dates))
        query = (f'SELECT date, price FROM "{sector_name}" WHERE name = ? AND date IN ({placeholders}) ORDER BY date ASC')
        cursor.execute(query, (symbol, *all_er_dates))
        price_data = cursor.fetchall()

        if is_tracing: log_detail(f"[{symbol}] 步骤2: 查询财报日收盘价。要求 {len(all_er_dates)} 条，实际查到 {len(price_data)} 条。")
        
        if len(price_data) != len(all_er_dates):
            if is_tracing: log_detail(f"[{symbol}] 失败: 财报日收盘价数据不完整。")
            continue

        data['all_er_prices'] = [p[1] for p in price_data]
        if is_tracing: log_detail(f"[{symbol}] - 财报日收盘价列表: {data['all_er_prices']}")

        # 步骤3: 获取基准交易日数据 (原代码逻辑保持不变，这部分是对的)
        if target_date:
            # 回测模式：强制查询指定日期(含)之前的最新一条数据
            query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 1'
            params = (symbol, target_date)
            if is_tracing: log_detail(f"[{symbol}] !!! 回测模式启动 !!! 正在查找 {target_date} 或之前的最新数据...")
        else:
            # 正常模式：查询数据库里最新的一条数据
            query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? ORDER BY date DESC LIMIT 1'
            params = (symbol,)

        cursor.execute(query, params)
        latest_row = cursor.fetchone()
        
        if not latest_row or latest_row[1] is None or latest_row[2] is None:
            if is_tracing: log_detail(f"[{symbol}] 失败: 未能获取有效的交易日数据(可能该日期停牌或无数据)。")
            continue
        
        # 这一步很关键：一旦这里锁定了 latest_date_str 为 2025-12-17
        # 后续所有代码(prev_10_prices, high_since_er等)都会基于这个日期自动计算
        data['latest_date_str'], data['latest_price'], data['latest_volume'] = latest_row
        
        if is_tracing: log_detail(f"[{symbol}] 步骤3: 获取基准交易日数据。日期: {data['latest_date_str']}, 价格: {data['latest_price']}, 成交量: {data['latest_volume']}")

        # ========== 修改开始：同时获取日期和价格 ==========
        cursor.execute(f'SELECT date, price FROM "{sector_name}" WHERE name = ? AND date < ? ORDER BY date DESC LIMIT 10', (symbol, data['latest_date_str']))
        prev_rows = cursor.fetchall()
        
        # 分离日期和价格
        data['prev_10_dates'] = [r[0] for r in prev_rows]
        data['prev_10_prices'] = [r[1] for r in prev_rows]

        if is_tracing: log_detail(f"[{symbol}] 步骤3.1: 获取最近10个交易日数据。日期: {data['prev_10_dates']}, 价格: {data['prev_10_prices']}")

        latest_er_date = data['latest_er_date_str']
        latest_er_price = data['all_er_prices'][-1]
        
        cursor.execute(f'SELECT price FROM "{sector_name}" WHERE name = ? AND date > ? ORDER BY date ASC LIMIT 3', (symbol, latest_er_date))
        next_days_rows = cursor.fetchall()
        next_days_prices = [row[0] for row in next_days_rows]
        er_window_prices = [latest_er_price]
        er_window_prices.extend(next_days_prices)
        data['er_window_high_price'] = max(er_window_prices) if er_window_prices else None
        
        if is_tracing: log_detail(f"[{symbol}] 步骤3.2: 查找财报窗口期最高价。窗口期价格: {er_window_prices}, 最高价: {data['er_window_high_price']}")

        # ========== 【修改点 2/3】: "财报后至今最高价" 需增加回测日期上限 ==========
        if target_date:
            cursor.execute(f'SELECT MAX(price) FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?', (symbol, data['latest_er_date_str'], target_date))
        else:
            cursor.execute(f'SELECT MAX(price) FROM "{sector_name}" WHERE name = ? AND date >= ?', (symbol, data['latest_er_date_str']))
        # ======================================================================
        high_since_er_row = cursor.fetchone()
        data['high_since_er'] = high_since_er_row[0] if high_since_er_row else None
        if is_tracing: log_detail(f"[{symbol}] 步骤3.3: 获取自最新财报日({data['latest_er_date_str']})以来的最高价: {data['high_since_er']}")

        cursor.execute(f'SELECT MAX(price) FROM "{sector_name}" WHERE name = ? AND date > ? AND date <= ?', (symbol, latest_er_date, data['latest_date_str']))
        high_between_er_and_latest_row = cursor.fetchone()
        data['high_between_er_and_latest'] = high_between_er_and_latest_row[0] if high_between_er_and_latest_row else None
        
        if is_tracing: log_detail(f"[{symbol}] 步骤3.4: 获取从财报日({latest_er_date})到最新日({data['latest_date_str']})之间的最高价: {data['high_between_er_and_latest']}")

        # ========== 代码修改开始 2/3：新增逻辑以获取条件5所需的数据 ==========
        # 为条件5获取财报日及之后5个交易日（共6天）的收盘价，并计算最低价
        limit_days = CONFIG.get("COND5_WINDOW_DAYS", 6)
        cursor.execute(f'SELECT price FROM "{sector_name}" WHERE name = ? AND date >= ? ORDER BY date ASC LIMIT {limit_days}', (symbol, data['latest_er_date_str']))
        er_6_day_prices_rows = cursor.fetchall()
        er_6_day_prices = [row[0] for row in er_6_day_prices_rows if row[0] is not None]
        data['er_6_day_window_low'] = min(er_6_day_prices) if er_6_day_prices else None

        if is_tracing:
             log_detail(f"[{symbol}] 步骤3.5: 为条件5获取财报窗口期(6天)最低价。价格: {er_6_day_prices}, 最低价: {data['er_6_day_window_low']}")

        # ========== 【修改点 3/3】: "条件6完整价格序列" 必须增加回测日期上限 ==========
        if target_date:
            cursor.execute(f'SELECT date, price FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ? ORDER BY date ASC', (symbol, data['latest_er_date_str'], target_date))
        else:
            cursor.execute(f'SELECT date, price FROM "{sector_name}" WHERE name = ? AND date >= ? ORDER BY date ASC', (symbol, data['latest_er_date_str']))
        # ======================================================================
        since_er_rows = cursor.fetchall()
        
        # 存储序列，用于条件6的形态分析
        data['prices_since_er_series'] = [r[1] for r in since_er_rows if r[1] is not None]
        data['dates_since_er_series'] = [r[0] for r in since_er_rows if r[0] is not None]
        
        if is_tracing:
             log_detail(f"[{symbol}] 步骤3.6: 获取财报日至今的价格序列，共 {len(data['prices_since_er_series'])} 天。")
        # ========== 代码修改结束 2/4 ==========

        data['pe_ratio'], data['marketcap'] = None, None
        if marketcap_exists:
            try:
                cursor.execute("SELECT pe_ratio, marketcap FROM MNSPP WHERE symbol = ?", (symbol,))
                row = cursor.fetchone()
                if row: data['pe_ratio'], data['marketcap'] = row
                if is_tracing: log_detail(f"[{symbol}] 步骤4: 尝试从MNSPP获取PE和市值。查询结果: PE={data['pe_ratio']}, 市值={data['marketcap']}")
            except sqlite3.OperationalError as e:
                if "no such column: marketcap" in str(e):
                    if i == 0: print("警告: MNSPP表中无 'marketcap' 列，将回退查询。")
                    marketcap_exists = False
                    cursor.execute("SELECT pe_ratio FROM MNSPP WHERE symbol = ?", (symbol,))
                    row = cursor.fetchone()
                    if row: data['pe_ratio'] = row[0]
                    if is_tracing: log_detail(f"[{symbol}] 步骤4 (回退): 'marketcap'列不存在。查询PE。结果: PE={data['pe_ratio']}")
                else: raise
        else:
            cursor.execute("SELECT pe_ratio FROM MNSPP WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            if row: data['pe_ratio'] = row[0]
            if is_tracing: log_detail(f"[{symbol}] 步骤4: 查询PE。结果: PE={data['pe_ratio']}")

        tags = set(symbol_to_tags_map.get(symbol, []))
        data['tags'] = tags
        is_hot = len(tags & set(CONFIG.get("HOT_TAGS", set()))) > 0
        is_big = (data['marketcap'] is not None) and (data['marketcap'] >= CONFIG["MARKETCAP_THRESHOLD"])
        
        data['is_hot_or_big_for_cond3'] = bool(is_hot or is_big)
        data['last_N_high'] = None
        data['cond3_drop_type'] = None
        
        if data['is_hot_or_big_for_cond3']:
            lookback_days = CONFIG.get("COND3_LOOKBACK_DAYS", 60)
            last_N_high = get_high_price_last_n_days(cursor, sector_name, symbol, data['latest_date_str'], lookback_days)
            data['last_N_high'] = last_N_high
            
            if last_N_high and last_N_high > 0:
                drop_pct_vs_N_high = (last_N_high - data['latest_price']) / last_N_high
                
                # --- 修改为动态标签 ---
                thresholds = sorted(CONFIG["COND3_DROP_THRESHOLDS"])
                low_t = thresholds[0]
                high_t = thresholds[1]
                low_l = str(int(low_t * 100))   # "9"
                high_l = str(int(high_t * 100)) # "15"
                
                c3_type = None
                if drop_pct_vs_N_high >= high_t: c3_type = high_l
                elif drop_pct_vs_N_high >= low_t: c3_type = low_l
                data['cond3_drop_type'] = c3_type

        if is_tracing: log_detail(f"[{symbol}] 步骤5: 条件3缓存 -> is_hot={is_hot}, is_big={is_big}, last_N_high={data['last_N_high']}, cond3_drop_type={data['cond3_drop_type']}")
        
        data['is_valid'] = True
        cache[symbol] = data
        if is_tracing: log_detail(f"[{symbol}] 成功: 数据缓存构建完成，标记为有效。")

    conn.close()
    return cache

def get_high_price_last_n_days(cursor, sector_name, symbol, latest_date_str, lookback_days):
    from datetime import datetime, timedelta
    try:
        dt = datetime.strptime(latest_date_str, "%Y-%m-%d")
    except ValueError:
        try:
            dt = datetime.strptime(latest_date_str, "%Y%m%d")
            def to_str(d): return d.strftime("%Y%m%d")
        except ValueError:
            cursor.execute(f'SELECT price FROM "{sector_name}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT ?', (symbol, latest_date_str, lookback_days))
            rows = cursor.fetchall()
            prices = [r[0] for r in rows if r[0] is not None]
            return max(prices) if prices else None
    else:
        def to_str(d): return d.strftime("%Y-%m-%d")
    start_dt = dt - timedelta(days=lookback_days)
    start_str = to_str(start_dt)
    end_str = to_str(dt)
    cursor.execute(f'SELECT MAX(price) FROM "{sector_name}" WHERE name = ? AND date BETWEEN ? AND ?', (symbol, start_str, end_str))
    row = cursor.fetchone()
    return row[0] if row and row[0] is not None else None

# --- 5. 策略与过滤模块 ---

def check_special_condition(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f" - [特殊条件检查(前提条件)] for {symbol}:")

    er_pcts = data.get('all_er_pcts', [])
    all_er_prices = data.get('all_er_prices', [])
    recent_earnings_count = config["RECENT_EARNINGS_COUNT"]

    if not er_pcts or not all_er_prices:
        if is_tracing: log_detail(f" - 失败: 财报数据不足。-> 返回 0 (严格)")
        return 0

    cond_a, cond_b, cond_c, cond_d = False, False, False, False
    
    latest_er_pct = er_pcts[-1]
    cond_a = latest_er_pct > 0

    if len(all_er_prices) >= recent_earnings_count:
        prices_to_check = all_er_prices[-recent_earnings_count:]
        avg_recent_price = sum(prices_to_check) / len(prices_to_check)
        latest_er_price = prices_to_check[-1]
        cond_b = latest_er_price > avg_recent_price
        
        previous_er_price = all_er_prices[-2]
        price_diff_pct = ((latest_er_price - previous_er_price) / previous_er_price) if previous_er_price > 0 else 0
        cond_c = price_diff_pct > config["ER_PRICE_DIFF_THRESHOLD"]
    
    if len(all_er_prices) >= 3:
        cond_d = all_er_prices[-1] > all_er_prices[-2] > all_er_prices[-3]

    if is_tracing:
        log_detail(f"    - a) 最新财报涨跌幅 > 0: {latest_er_pct:.4f} > 0 -> {cond_a}")
        if len(all_er_prices) >= recent_earnings_count:
            log_detail(f"    - b) 最新财报收盘价 > 平均价: {latest_er_price:.2f} > {avg_recent_price:.2f} -> {cond_b}")
            log_detail(f"    - c) 最新两次财报价差 > {config['ER_PRICE_DIFF_THRESHOLD']*100}%: {price_diff_pct:.2%} > {config['ER_PRICE_DIFF_THRESHOLD']:.2%} -> {cond_c}")
        else:
            log_detail(f"    - b) & c) 跳过 (财报价格数量 < {recent_earnings_count})")
        if len(all_er_prices) >= 3:
            log_detail(f"    - d) 最近三次财报收盘价递增: {all_er_prices[-1]:.2f} > {all_er_prices[-2]:.2f} > {all_er_prices[-3]:.2f} -> {cond_d}")
        else:
            log_detail(f"    - d) 跳过 (财报价格数量 < 3)")
    if cond_a and cond_b and cond_c:
        if is_tracing: log_detail(f"    - 最终决策: 命中 (A & B & C) -> 返回 3 (最宽松)")
        return 3
    if cond_a and cond_d:
        if is_tracing: log_detail(f"    - 最终决策: 命中 (A & D) -> 返回 2 (次宽松)")
        return 2
    if (cond_a and cond_b) or (cond_b and cond_c):
        if is_tracing: log_detail(f"    - 最终决策: 命中 ((A & B) or (B & C)) -> 返回 1 (普通宽松)")
        return 1
    if is_tracing: log_detail(f"    - 最终决策: 未命中任何宽松条件 -> 返回 0 (严格)")
    return 0

def check_condition_2(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件2评估 ---")
    recent_earnings_count = config["RECENT_EARNINGS_COUNT"]
    all_er_prices = data.get('all_er_prices', [])
    all_er_pcts = data.get('all_er_pcts', [])
    if len(all_er_prices) < recent_earnings_count:
        if is_tracing: log_detail(f"  - 结果: False (财报收盘价数量不足 {recent_earnings_count} 次)")
        return False
    if not all_er_pcts:
        if is_tracing: log_detail("  - 结果: False (缺少财报涨跌幅数据)")
        return False
    recent_er_prices = all_er_prices[-recent_earnings_count:]
    latest_er_price = recent_er_prices[-1]
    latest_er_pct = all_er_pcts[-1]
    avg_recent_price = sum(recent_er_prices) / len(recent_er_prices)
    cond_a = latest_er_price > avg_recent_price
    if is_tracing: log_detail(f"  - a) 最新财报价 > 平均价: {latest_er_price:.2f} > {avg_recent_price:.2f} -> {cond_a}")
    if not cond_a:
        if is_tracing: log_detail("  - 结果: False (条件a未满足)")
        return False
    previous_er_price = all_er_prices[-2]
    if previous_er_price <= 0:
        if is_tracing: log_detail(f"  - 结果: False (上次财报价格为 {previous_er_price}，无法计算价差)")
        return False
    price_diff_pct = (latest_er_price - previous_er_price) / previous_er_price
    # 同样建议关联到配置
    # 1. 先获取阈值变量 (默认为 0.04)
    er_threshold = config.get("ER_PRICE_DIFF_THRESHOLD", 0.04)
    # 2. 使用该变量进行判断
    cond_b = price_diff_pct >= er_threshold
    if is_tracing: 
        log_detail(f"  - b) 最近两次财报价差 >= {er_threshold:.0%}: {price_diff_pct:.2%} >= {er_threshold:.2%} -> {cond_b}")
    if not cond_b:
        if is_tracing: log_detail("  - 结果: False (条件b未满足)")
        return False
    cond_c = latest_er_pct > 0
    if is_tracing: log_detail(f"  - c) 最新财报涨跌幅 > 0: {latest_er_pct:.4f} > 0 -> {cond_c}")
    if not cond_c:
        if is_tracing: log_detail("  - 结果: False (条件c未满足)")
        return False
    min_recent_er_price = min(recent_er_prices)
    latest_price = data['latest_price']
    cond_d = latest_price < min_recent_er_price
    if is_tracing: log_detail(f"  - d) 最新价 < 最近N次财报最低价: {latest_price:.2f} < {min_recent_er_price:.2f} -> {cond_d}")
    if not cond_d:
        if is_tracing: log_detail("  - 结果: False (条件d未满足)")
        return False
    if is_tracing: log_detail("  - 结果: True (新增前提条件所有子条件均满足)")
    return True

def check_new_condition_3(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件3评估 ---")
    
    if not data.get('is_hot_or_big_for_cond3'):
        if is_tracing: log_detail("  - 结果: False (既非热门也非大市值)")
        return False

    last_N_high = data.get('last_N_high')
    latest_price = data.get('latest_price')
    cond3_type = data.get('cond3_drop_type')
    lookback_days = config.get("COND3_LOOKBACK_DAYS", 60)

    if not last_N_high or last_N_high <= 0:
        if is_tracing: log_detail(f"  - 结果: False (无法获取最近{lookback_days}天最高价)")
        return False

    # 计算实际跌幅
    drop_pct = (last_N_high - latest_price) / last_N_high if last_N_high > 0 else 0.0
    
    # 动态获取阈值（从配置读取）
    thresholds = sorted(config["COND3_DROP_THRESHOLDS"]) # [0.09, 0.15]
    low_thresh = thresholds[0]   # 0.09
    high_thresh = thresholds[1]  # 0.15
    
    # 将小数转换为整数字符串，用于标签（例如 0.09 -> "9", 0.15 -> "15"）
    low_label = str(int(low_thresh * 100))   # "9"
    high_label = str(int(high_thresh * 100)) # "15"

    hit_high = drop_pct >= high_thresh
    hit_low = drop_pct >= low_thresh

    if is_tracing:
        log_detail(f" - 最近{lookback_days}天最高价: {last_N_high:.2f}, 最新价: {latest_price:.2f}, 跌幅: {drop_pct:.2%}")
        log_detail(f"  - 命中{high_label}%: {hit_high}, 命中{low_label}%: {hit_low}, cond3_drop_type缓存: {cond3_type}")

    # 1. 如果缓存里已经有值了，直接返回 True
    if cond3_type in (low_label, high_label):
        if is_tracing: log_detail(f"  - 结果: True (命中条件3, 类型: {cond3_type})")
        return True

    # 2. 判定逻辑：优先存入高阈值标签
    if hit_high:
        data['cond3_drop_type'] = high_label
        if is_tracing: log_detail(f"  - 结果: True (兜底命中{high_label}%)")
        return True
    if hit_low:
        data['cond3_drop_type'] = low_label
        if is_tracing: log_detail(f"  - 结果: True (兜底命中{low_label}%)")
        return True

    if is_tracing: log_detail("  - 结果: False (不满足条件3)")
    return False

def check_new_condition_4(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件4评估 (动态市值阈值) ---")
    
    high_since_er = data.get('high_since_er')
    latest_price = data.get('latest_price')
    marketcap = data.get('marketcap')
    
    # --- 动态阈值判断逻辑 ---
    ultra_cap_limit = config.get("MARKETCAP_THRESHOLD_ULTRA", 1000_000_000_000)
    if marketcap and marketcap >= ultra_cap_limit:
        rise_threshold = config.get('COND4_RISE_THRESHOLD_LARGE', 0.09)
        cap_type = "超大市值 (>8000亿)"
    else:
        rise_threshold = config.get('COND4_RISE_THRESHOLD_SMALL', 0.11)
        cap_type = "普通市值 (<=8000亿)"
    # -----------------------

    if high_since_er is None or latest_price is None or latest_price <= 0:
        if is_tracing: log_detail(f"  - 结果: False (数据不足: high_since_er={high_since_er}, latest_price={latest_price})")
        return False

    threshold_price = latest_price * (1 + rise_threshold)
    passed = high_since_er >= threshold_price
    
    if is_tracing:
        rise_pct = (high_since_er - latest_price) / latest_price
        log_detail(f"  - 当前市值: {marketcap if marketcap else '未知':,}")
        log_detail(f"  - 判定类型: {cap_type}")
        log_detail(f"  - 财报日至今最高价: {high_since_er:.2f}")
        log_detail(f"  - 最新收盘价: {latest_price:.2f}")
        log_detail(f"  - 实际涨幅: {rise_pct:.2%}")
        log_detail(f"  - 动态要求涨幅: {rise_threshold:.2%}")
        log_detail(f"  - 判断: {high_since_er:.2f} >= {threshold_price:.2f} -> {passed}")
        log_detail(f"  - 结果: {passed}")
    return passed

# ========== 代码修改开始 3/3：更新 check_new_condition_5 函数以实现新规则 ==========
def check_new_condition_5(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件5评估 (新规则) ---")

    # 从缓存中获取所需数据
    high_between = data.get('high_between_er_and_latest')
    # 使用新获取的“财报日及之后6天窗口期”的最低价
    er_window_low_price = data.get('er_6_day_window_low')
    latest_price = data.get('latest_price')
    
    # 从配置中获取阈值
    er_to_high_threshold = config.get('COND5_ER_TO_HIGH_THRESHOLD', 0.3)
    high_to_latest_threshold = config.get('COND5_HIGH_TO_LATEST_THRESHOLD', 0.079)

    # 数据有效性检查
    if high_between is None or er_window_low_price is None or latest_price is None:
        if is_tracing: log_detail(f"  - 结果: False (数据不足: high_between={high_between}, er_window_low_price={er_window_low_price}, latest_price={latest_price})")
        return False
    
    if er_window_low_price <= 0 or latest_price <= 0:
        if is_tracing: log_detail(f"  - 结果: False (价格数据无效: er_window_low_price={er_window_low_price}, latest_price={latest_price})")
        return False

    # 条件A：最高价比“财报窗口期最低价”高至少30%
    er_price_threshold = er_window_low_price * (1 + er_to_high_threshold)
    cond_a = high_between >= er_price_threshold

    # 条件B：最高价比“最新收盘价”高至少7.9%
    latest_price_threshold = latest_price * (1 + high_to_latest_threshold)
    cond_b = high_between >= latest_price_threshold

    passed = cond_a and cond_b

    # 详细日志记录
    if is_tracing:
        er_rise_pct = (high_between - er_window_low_price) / er_window_low_price if er_window_low_price > 0 else 0
        latest_rise_pct = (high_between - latest_price) / latest_price if latest_price > 0 else 0
        log_detail(f"  - 财报窗口期(6天)最低价: {er_window_low_price:.2f}")
        log_detail(f"  - 财报日到最新日之间最高价: {high_between:.2f}")
        log_detail(f"  - 最新收盘价: {latest_price:.2f}")
        log_detail(f"  - 条件A (新): 最高价相对财报窗口期最低价涨幅 {er_rise_pct:.2%} >= {er_to_high_threshold:.2%} -> {cond_a}")
        log_detail(f"  - 条件B: 最高价相对最新价涨幅 {latest_rise_pct:.2%} >= {high_to_latest_threshold:.2%} -> {cond_b}")
        log_detail(f"  - 结果: {passed}")
        
    return passed

# ==============================================================================
# 提取的独立通用函数：W底（双底）形态检测算法 (增强日志版)
# ==============================================================================
def check_w_bottom_pattern(data, config, log_detail, symbol_to_trace, check_strict_er_drop=True):
    """
    check_strict_er_drop:
    - True (用于条件6): 必须满足财报间大幅下跌(Drop A) 且 现价深跌(Drop B) 的前提。
    - False (用于条件1-5): 纯形态检测。忽略与财报价的相对位置，只要几何形态满足W底即可。
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    mode_str = "严格抄底模式(Cond6)" if check_strict_er_drop else "形态确认模式(Cond1-5)"
    
    if is_tracing: log_detail(f" - [W底检测启动] 模式: {mode_str}")

    # 1. 数据准备
    all_er_prices = data.get('all_er_prices', [])
    prices_series = data.get('prices_since_er_series', [])
    dates_series = data.get('dates_since_er_series', [])

    if len(all_er_prices) < 2:
        if is_tracing: log_detail(f" - [失败] 财报数据不足 2 条。")
        return False
    
    if not prices_series or len(prices_series) < 10:
        if is_tracing: log_detail(f" - [失败] 财报后交易日数据不足 10 天。")
        return False

    # ========== 计算区间最低价及其索引 ==========
    # 获取从财报日(含)到最新交易日(含)的绝对最低收盘价
    period_lowest_price = min(prices_series)
    # 获取最低价第一次出现的索引位置（用于计算时间间隔）
    try:
        lowest_price_idx = prices_series.index(period_lowest_price)
    except ValueError:
        lowest_price_idx = 0

    if is_tracing: log_detail(f" - [区间统计] 财报后最低价: {period_lowest_price:.2f} (索引: {lowest_price_idx})")

    latest_er_price = all_er_prices[-1]

    # --- 步骤 1: 仅在严格模式下检查 Drop A 和设定 Drop B 阈值 ---
    threshold_b = 0.12 # 默认值
    if check_strict_er_drop:
        prev_er_price = all_er_prices[-2]
        if prev_er_price <= 0: return False
        
        er_drop_a_val = (prev_er_price - latest_er_price) / prev_er_price
        threshold_a = config.get("COND6_ER_DROP_A_THRESHOLD", 0.25)
        
        if er_drop_a_val > threshold_a:
            threshold_b = config.get("COND6_LOW_DROP_B_LARGE", 0.09) # > 9%
        elif er_drop_a_val > 0.10: # 至少跌 10%
            threshold_b = config.get("COND6_LOW_DROP_B_SMALL", 0.12) # > 12%
        else:
            if is_tracing:
                log_detail(f" - [失败-Drop A] 财报间跌幅 {er_drop_a_val:.2%} <= 10%，不满足抄底前提。")
            return False
            
        if is_tracing:
            log_detail(f" - [通过-Drop A] 财报间跌幅 {er_drop_a_val:.2%}，设置深度阈值 B > {threshold_b:.1%}")

    # --- 步骤 2: 寻找 W 底几何形态 ---
    # 锁定 V2 (右底): 必须是昨天 (index -2)，且构成局部低点
    curr_price = prices_series[-1]
    prev_price = prices_series[-2]
    prev2_price = prices_series[-3]

    if not (prev_price < prev2_price and prev_price < curr_price):
        if is_tracing:
            log_detail(f" - [失败-V2定位] 昨天({prev_price:.2f})不是局部低点(需小于{prev2_price:.2f}且小于{curr_price:.2f})，无法构成右底。")
        return False

    v2 = prev_price
    idx2 = len(prices_series) - 2
    v2_date = dates_series[idx2]
    
    price_tolerance = config.get("COND6_W_BOTTOM_PRICE_TOLERANCE", 0.045)
    min_days_gap = config.get("COND6_W_BOTTOM_MIN_DAYS_GAP", 3)
    
    start_search_index = idx2 - min_days_gap

    if start_search_index < 1:
        if is_tracing: log_detail(f" - [失败-间隔] 距离财报日过近，无法满足最小间隔 {min_days_gap} 天。")
        return False

    if is_tracing: log_detail(f" - [V2已锁定] 日期: {v2_date}, 价格: {v2:.2f}, 开始寻找V1...")

    # 倒序遍历寻找 V1 (左底)
    for i in range(start_search_index, 0, -1):
        v1 = prices_series[i]
        v1_date = dates_series[i]

        # V1 必须是局部低点
        if not (v1 < prices_series[i-1] and v1 < prices_series[i+1]):
            continue

        if is_tracing: log_detail(f" > 发现潜在V1: {v1_date} (价格:{v1:.2f})")

        # [几何形态检查 1] 对称性 (左右底高度差)
        diff_pct = abs(v1 - v2) / min(v1, v2)
        if diff_pct > price_tolerance:
            if is_tracing: log_detail(f"   x [几何-对称性失败] 左右底高低差 {diff_pct:.2%} > 容忍度 {price_tolerance:.1%}")
            continue

        # [几何形态检查 2] 颈线检查 (中间不能有太深的破位)
        neckline_prices = prices_series[i+1 : idx2]
        if not neckline_prices: continue
            
        min_trough_between = min(neckline_prices)
        avg_valley = (v1 + v2) / 2 
        
        min_valley_absolute = min(v1, v2)
        noise_tolerance = config.get("COND6_W_BOTTOM_NOISE_TOLERANCE", 0.01) # 1% 噪音容忍
        
        limit_price = min_valley_absolute * (1 - noise_tolerance)
        if min_trough_between < limit_price:
            if is_tracing:
                log_detail(f"   x [几何-形态失败] V1-V2之间存在破位低点({min_trough_between:.2f})，跌破最低谷底容忍线({limit_price:.2f})")
            continue 

        # [几何形态检查 3] 反弹力度检查
        max_peak = max(neckline_prices)
        peak_rise = (max_peak - avg_valley) / avg_valley
        min_peak_rise = config.get("COND6_W_BOTTOM_MIN_PEAK_RISE", 0.015) 
        
        if peak_rise < min_peak_rise:
            if is_tracing:
                log_detail(f"   x [几何-力度失败] 中间反弹力度 {peak_rise:.2%} < {min_peak_rise:.1%}, 形态不显著")
            continue

        # ========== 修改 2/2：位置校验 (修复 FLEX 漏检问题) ==========
        # 逻辑：允许 W 底不是绝对最低点，只要它是一个经过长时间整理后的"底部抬高" (Higher Low)
        
        valley_min = min(v1, v2)
        
        # 1. 绝对低点判断 (允许 0.1% 误差)
        is_absolute_low = valley_min <= period_lowest_price * 1.001
        
        # 2. 底部抬高判断 (Higher Low)
        # 获取配置：允许底部抬高的最小间隔天数 (默认 18 天)
        higher_low_tolerance_days = config.get("COND6_W_BOTTOM_HIGHER_LOW_DAYS", 18)
        
        # 计算 V1 (左底) 距离 财报后绝对最低点 的时间间隔
        # i 是当前 V1 的索引, lowest_price_idx 是绝对最低点的索引
        days_since_lowest = i - lowest_price_idx
        
        is_valid_higher_low = (valley_min > period_lowest_price) and (days_since_lowest >= higher_low_tolerance_days)

        if not (is_absolute_low or is_valid_higher_low):
            if is_tracing:
                log_detail(f"   x [位置失败] W底({valley_min:.2f}) > 绝对低点({period_lowest_price:.2f})。")
                log_detail(f"     且绝对低点仅在 {days_since_lowest} 天前 (需 >= {higher_low_tolerance_days} 天才允许抬高底)。")
            continue
        
        if is_tracing and is_valid_higher_low:
             log_detail(f"   ! [提示] 检测到底部抬高 (Higher Low): W底({valley_min:.2f}) > 前低({period_lowest_price:.2f})，但在 {days_since_lowest} 天前，形态有效。")

        # ==========================================================

        # --- 步骤 3: 最终裁决 (分模式) ---
        if check_strict_er_drop:
            valley_min_price = min(v1, v2)
            # 计算深度时，使用 W 底的实际最低价
            drop_b_val = (latest_er_price - valley_min_price) / latest_er_price
            
            if drop_b_val > threshold_b:
                actual_gap = idx2 - i
                if is_tracing:
                    log_detail(f"   - ✅ [成功! (严格模式)] V1:{v1:.2f}, V2:{v2:.2f}, 间隔:{actual_gap}天")
                    log_detail(f"   - [深度检查] 深度 {drop_b_val:.2%} > 阈值 {threshold_b:.1%} -> 通过")
                return True
            else:
                if is_tracing:
                    log_detail(f"   x [失败-Drop B] 形态满足，但深度 {drop_b_val:.2%} 不足 (需 > {threshold_b:.1%})")
                continue

        else: # 宽松模式
            actual_gap = idx2 - i
            if is_tracing:
                log_detail(f"   - ✅ [成功! (宽松模式)] V1:{v1:.2f}, V2:{v2:.2f}, 间隔:{actual_gap}天")
            return True

    if is_tracing: log_detail(f" - [结果] 遍历结束，未找到满足所有条件的 W 底形态。")
    return False

def check_new_condition_6(data, config, log_detail, symbol_to_trace):
    # 锁定了昨天（index -2）必须是第二个峰值，且今天（index -1）必须下跌或企稳。
    # 严格遵循用户规则：条件B的最低价必须取自双谷中的最低点。
    # [修正] 严格控制双底之间的价格差异 (Symmetry)
    
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件6评估 (W底 - 抄底模式) ---")
    
    # 抄底模式：必须检查财报跌幅前提 (check_strict_er_drop=True)
    passed = check_w_bottom_pattern(data, config, log_detail, symbol_to_trace, check_strict_er_drop=True)
    
    if is_tracing: log_detail(f" - 结果: {passed}")
    return passed

def check_new_condition_7(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\\n--- [{symbol}] 新增条件7评估 (强财报深跌) ---")

    # 1. 数据获取与预检
    all_er_pcts = data.get('all_er_pcts', [])
    all_er_prices = data.get('all_er_prices', [])
    latest_price = data.get('latest_price')

    # 硬性要求：至少有4次财报记录
    if len(all_er_pcts) < 4 or len(all_er_prices) < 4:
        if is_tracing: log_detail(f" - 结果: False (财报数据不足4次)")
        return False
    
    # 2. 前提条件检查
    # A. 最近两次财报的 price值 (涨跌幅) 都是正的
    # all_er_pcts[-1] 是最新，[-2] 是次新
    cond_a = (all_er_pcts[-1] > 0) and (all_er_pcts[-2] > 0)
    
    # B. 最新一期财报收盘价 > 次新一期财报收盘价
    cond_b = all_er_prices[-1] > all_er_prices[-2]

    if is_tracing:
        log_detail(f" - 条件A (最近两次财报为正): {all_er_pcts[-1]:.2f} > 0 AND {all_er_pcts[-2]:.2f} > 0 -> {cond_a}")
        log_detail(f" - 条件B (财报价格上移): {all_er_prices[-1]:.2f} > {all_er_prices[-2]:.2f} -> {cond_b}")

    if not (cond_a and cond_b):
        if is_tracing: log_detail(" - 结果: False (前提条件未满足)")
        return False

    # 3. 核心触发条件检查
    # 最新价 < 最近四次财报日收盘价的最低值
    recent_4_er_prices = all_er_prices[-4:]
    min_er_price_4 = min(recent_4_er_prices)
    
    cond_c = latest_price < min_er_price_4

    if is_tracing:
        log_detail(f" - 最近4次财报价: {recent_4_er_prices}")
        log_detail(f" - 最低值: {min_er_price_4:.2f}")
        log_detail(f" - 最新价: {latest_price:.2f}")
        log_detail(f" - 条件C (破位深跌): {latest_price:.2f} < {min_er_price_4:.2f} -> {cond_c}")
        log_detail(f" - 结果: {cond_c}")

    return cond_c


# ========== 代码修改点 1/3: 重构 evaluate_stock_conditions 函数 ==========
# 1. 重命名为 check_entry_conditions，使其只负责检查入口条件
# 2. 修改返回值为元组 (passed_any, passed_cond5, passed_cond6)，以便后续逻辑判断
# 3. 移除所有通用过滤逻辑（价格回撤、10日最低价、成交额）

def check_entry_conditions(data, symbol_to_trace, log_detail):
    """
    此函数现在只检查入口条件 (条件1 OR 条件2 OR 条件3 OR 条件4 OR 条件5 OR 条件6)。
    返回: (passed_any, passed_cond5, passed_cond6)
    条件1修改为：a AND b AND c 必须同时满足。
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing:
        log_detail(f"\n--- [{symbol}] 入口条件评估 ---")
        
    # --- 数据预检 ---
    er_pcts = data.get('all_er_pcts', [])
    if not er_pcts or len(data.get('all_er_prices', [])) < CONFIG["RECENT_EARNINGS_COUNT"]:
        if is_tracing: log_detail(" - 预检失败: 缺少财报数据，无法评估入口条件。")
        return (False, False, False, False) # <--- 补齐为4个值

    # --- 评估各个入口条件 ---
    
    # 准备条件1所需数据
    prices_to_check = data['all_er_prices'][-CONFIG["RECENT_EARNINGS_COUNT"]:]
    latest_er_pct = er_pcts[-1]
    latest_er_price = prices_to_check[-1]
    avg_recent_price = sum(prices_to_check) / len(prices_to_check)
    previous_er_price = prices_to_check[-2]
    price_diff_pct_cond1b = ((latest_er_price - previous_er_price) / previous_er_price) if previous_er_price > 0 else 0
    
    # 获取阈值
    drop_pct_for_cond1c = CONFIG["PRICE_DROP_FOR_COND1C"]
    threshold_price1c = latest_er_price * (1 - drop_pct_for_cond1c)
    
    # 子条件计算
    cond1_a = latest_er_pct > 0
    
    # 1. 获取配置
    er_diff_threshold = CONFIG["ER_PRICE_DIFF_THRESHOLD"]

    # 2. 使用变量计算
    cond1_b = (latest_er_price > avg_recent_price) and (price_diff_pct_cond1b >= er_diff_threshold)
    cond1_c = data['latest_price'] <= threshold_price1c
    
    passed_original_cond1 = cond1_a and cond1_b and cond1_c
    
    if is_tracing:
        log_detail(" - [入口条件A] 条件1评估 (需同时满足 a, b, c):")
        log_detail(f"   - a) 最新财报涨跌幅 > 0 ({latest_er_pct:.4f}) -> {cond1_a}")
        log_detail(f"   - b) 最新财报价 > 平均价 且 较上次财报涨幅 >= {er_diff_threshold:.0%} -> {cond1_b}")
        log_detail(f"   - c) 最新价({data['latest_price']:.2f}) <= 财报价({latest_er_price:.2f}) * (1 - {drop_pct_for_cond1c}) = {threshold_price1c:.2f} -> {cond1_c}")
        log_detail(f"   - 条件1最终结果: {passed_original_cond1}")

    # 入口条件：条件2, 3, 4, 5
    passed_new_cond2 = check_condition_2(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond3 = check_new_condition_3(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond4 = check_new_condition_4(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond5 = check_new_condition_5(data, CONFIG, log_detail, symbol_to_trace)
    
    # 新增：条件6
    passed_new_cond6 = check_new_condition_6(data, CONFIG, log_detail, symbol_to_trace)

    # ========== 修改点：新增条件7调用 ==========
    passed_new_cond7 = check_new_condition_7(data, CONFIG, log_detail, symbol_to_trace)

    # 汇总
    passed_any = passed_original_cond1 or passed_new_cond2 or passed_new_cond3 or passed_new_cond4 or passed_new_cond5 or passed_new_cond6 or passed_new_cond7

    if is_tracing:
        if passed_any:
            reasons = []
            if passed_original_cond1: reasons.append("条件1")
            if passed_new_cond2: reasons.append("条件2")
            if passed_new_cond3: reasons.append("条件3")
            if passed_new_cond4: reasons.append("条件4")
            if passed_new_cond5: reasons.append("条件5")
            if passed_new_cond6: reasons.append("条件6(W底)")
            if passed_new_cond7: reasons.append("条件7(强财报深跌)") # 日志添加
            log_detail(f"\\n--- [{symbol}] 入口条件通过 (原因: {'、'.join(reasons)})。")
        else:
            log_detail(f"\\n--- [{symbol}] 入口条件失败。七个入口条件均未满足。")

    # ========== 修改点：返回值增加 passed_new_cond7 ==========
    return (passed_any, passed_new_cond5, passed_new_cond6, passed_new_cond7)

# ========== 代码修改点 2/3: 新增 apply_common_filters 函数 ==========
# 这个函数包含了从原 evaluate_stock_conditions 中移出的通用过滤逻辑

def apply_common_filters(data, symbol_to_trace, log_detail, drop_pct_large, drop_pct_small, skip_drawdown=False):
    """
    应用通用的过滤条件：价格回撤、10日最低价、成交额。
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    
    if is_tracing:
        log_detail(f"\n--- [{symbol}] 开始执行通用过滤 (使用 large={drop_pct_large*100}%, small={drop_pct_small*100}%) ---")

    # 1. 价格回撤条件 (可跳过)
    if not skip_drawdown:
        marketcap = data.get('marketcap')
        # [修改] 原来使用的是 er_window_high_price (仅财报后3天)，现在改为 high_since_er (财报后至今最高价)
        # 如果 high_since_er 不存在(极少数情况)，回退使用 er_window_high_price
        high_price_reference = data.get('high_since_er')
        if high_price_reference is None:
            high_price_reference = data.get('er_window_high_price')

        if high_price_reference is None or high_price_reference <= 0:
            if is_tracing: log_detail(f" - 最终裁定: 失败 (通用过滤1: 无法获取有效的最高价数据: {high_price_reference})。")
            return False

        is_strict_mode = (
            drop_pct_large == CONFIG["PRICE_DROP_PERCENTAGE_LARGE" ] and
            drop_pct_small == CONFIG["PRICE_DROP_PERCENTAGE_SMALL"]
        )
        
        drop_pct = 0
        if is_strict_mode:
            if marketcap and marketcap >= CONFIG["MARKETCAP_THRESHOLD_MEGA"]: drop_pct = CONFIG["PRICE_DROP_PERCENTAGE_MEGA"]
            elif marketcap and marketcap >= CONFIG["MARKETCAP_THRESHOLD"]: drop_pct = CONFIG["PRICE_DROP_PERCENTAGE_SMALL"]
            else: drop_pct = CONFIG["PRICE_DROP_PERCENTAGE_LARGE"]
        else:
            if marketcap and marketcap >= CONFIG["MARKETCAP_THRESHOLD"]: drop_pct = drop_pct_small
            else: drop_pct = drop_pct_large

        # 使用修正后的 high_price_reference 计算阈值
        threshold_price_drawdown = high_price_reference * (1 - drop_pct)
        cond_drawdown_ok = data['latest_price'] <= threshold_price_drawdown
        
        if is_tracing:
            log_detail(" - [通用过滤1] 价格回撤:")
            log_detail(f"   - 市值: {marketcap} -> 使用下跌百分比: {drop_pct*100:.1f}%")
            # [修改] 日志文案更新，明确显示使用的是“财报日至今最高价”
            log_detail(f"   - 判断: 最新价({data['latest_price']:.2f}) <= 财报日至今最高价({high_price_reference:.2f}) * (1 - {drop_pct:.2f}) = 阈值价({threshold_price_drawdown:.2f}) -> {cond_drawdown_ok}")

        if not cond_drawdown_ok:
            if is_tracing: log_detail(" - 最终裁定: 失败 (通用过滤1: 价格回撤不满足)。")
            return False
    else:
        if is_tracing: log_detail(" - [通用过滤1] 价格回撤: 已跳过 (条件5/6模式)。")

    # 2. 相对10日最低价条件 (逻辑更新：如果10天内含财报日，则使用财报日收盘价作为基准)
    prev_prices = data.get('prev_10_prices', [])
    prev_dates = data.get('prev_10_dates', [])
    latest_er_date = data.get('latest_er_date_str')
    
    if len(prev_prices) < 10:
        if is_tracing: log_detail(f" - 最终裁定: 失败 (通用过滤2: 可用历史交易日不足10日，只有{len(prev_prices)}日数据)。")
        return False
        
    # ========== 修改开始：判断基准价格 ==========
    baseline_price = None
    using_er_price_logic = False
    
    if latest_er_date and latest_er_date in prev_dates:
        # 如果财报日在最近10天内
        try:
            er_index = prev_dates.index(latest_er_date)
            baseline_price = prev_prices[er_index]
            using_er_price_logic = True
        except ValueError:
            # 理论上不会发生，因为前面check了 in prev_dates
            baseline_price = min(prev_prices)
    else:
        # 如果财报日不在10天内，使用原来的逻辑（最低价）
        baseline_price = min(prev_prices)

    # ========== 【代码修改点：增加热门板块判断逻辑】 ==========
    # 1. 获取当前 Symbol 的 Tags 和全局 HOT_TAGS
    symbol_tags = data.get('tags', set())
    hot_tags = CONFIG.get("HOT_TAGS", set())
    
    # 2. 判断是否有交集（是否属于热门）
    is_hot_stock = bool(symbol_tags & hot_tags)
    
    # 3. 根据是否热门，选择不同的阈值
    if is_hot_stock:
        max_increase_pct = CONFIG.get("MAX_INCREASE_PERCENTAGE_SINCE_LOW_HOT", 0.12) # 默认12%
    else:
        max_increase_pct = CONFIG["MAX_INCREASE_PERCENTAGE_SINCE_LOW"] # 默认6%

    # 4. 计算阈值价格
    threshold_price_10day = baseline_price * (1 + max_increase_pct)
    cond_10day_ok = data['latest_price'] <= threshold_price_10day

    if is_tracing:
        log_detail(f" - [通用过滤2] 相对10日基准价:")
        if using_er_price_logic:
            log_detail(f"   - 策略: 财报日({latest_er_date})在10天内，使用财报日收盘价作为基准。")
        else:
            log_detail(f"   - 策略: 财报日不在10天内，使用10日最低价作为基准。")
        
        # 打印热门判定详情
        hot_status_str = f"是 (放宽至 {max_increase_pct:.0%})" if is_hot_stock else f"否 (保持 {max_increase_pct:.0%})"
        log_detail(f"   - 热门判定: {hot_status_str} (Tags: {symbol_tags})")
        
        log_detail(f"   - 基准价: {baseline_price:.2f}")
        log_detail(f"   - 判断: 最新价 {data['latest_price']:.2f} <= 基准价*{1+max_increase_pct:.2f} ({threshold_price_10day:.2f}) -> {cond_10day_ok}")

    if not cond_10day_ok:
        if is_tracing: log_detail(" - 最终裁定: 失败 (通用过滤2: 相对10日基准价条件不满足)。")
        return False

    # 3. 成交额条件
    turnover = data['latest_price'] * data['latest_volume']
    tags = data.get('tags', set())
    is_china_stock = any("中国" in tag for tag in tags)
    current_threshold = CONFIG["TURNOVER_THRESHOLD_CHINA"] if is_china_stock else CONFIG["TURNOVER_THRESHOLD"]

    cond_turnover_ok = turnover > current_threshold
    
    if is_tracing:
        log_detail(" - [通用过滤3] 成交额:")
        log_detail(f"   - {'使用中国概念股阈值' if is_china_stock else '使用通用阈值'}: {current_threshold:,}")
        log_detail(f"   - 判断: 最新成交额({turnover:,.0f}) >= 阈值({current_threshold:,}) -> {cond_turnover_ok}")

    if not cond_turnover_ok:
        if is_tracing: log_detail(" - 最终裁定: 失败 (通用过滤3: 成交额不满足)。")
        return False

    if is_tracing: log_detail(" - 最终裁定: 成功! 所有通用过滤条件均满足。")
    return True

def apply_post_filters(symbols, stock_data_cache, symbol_to_trace, log_detail):
    pe_valid_symbols = []
    pe_invalid_symbols = []
    
    for symbol in symbols:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n--- [{symbol}] 后置过滤器评估 ---")
        
        data = stock_data_cache[symbol]
        
        # 注意：日期检查已在主循环执行，这里不再重复拦截
        # if data['latest_date_str'] == data['latest_er_date_str']:
        #     if is_tracing: log_detail(f" - 过滤 (日期相同): 最新交易日({data['latest_date_str']}) 与 最新财报日({data['latest_er_date_str']}) 相同。")
        #     continue
        # elif is_tracing: log_detail(f" - 通过 (日期不同)。")

        pe = data['pe_ratio']
        is_pe_valid = pe is not None and str(pe).strip().lower() not in ("--", "null", "")
        
        if is_pe_valid:
            if is_tracing: log_detail(f" - 分组 (PE有效): PE值为 '{pe}'。加入 PE_valid 组。")
            pe_valid_symbols.append(symbol)
        else:
            if is_tracing: log_detail(f" - 分组 (PE无效): PE值为 '{pe}'。加入 PE_invalid 组。")
            pe_invalid_symbols.append(symbol)
            
    return pe_valid_symbols, pe_invalid_symbols


# --- 6. 主逻辑 ---

def run_processing_logic(log_detail):
    log_detail("程序开始运行...")
    if SYMBOL_TO_TRACE: log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")

    # 【新增】打印回测状态
    if TARGET_DATE:
        log_detail(f"\n⚠️⚠️⚠️ 注意：当前处于【回测模式】，目标日期：{TARGET_DATE} ⚠️⚠️⚠️")
        log_detail("为了保护现有数据，本次运行将【不会】更新 Panel 和 History JSON 文件。")
        log_detail("仅用于生成 trace log 进行逻辑验证。\n")

    tag_blacklist_from_file, hot_tags_from_file = load_tag_settings(TAGS_SETTING_JSON_FILE)
    CONFIG["BLACKLIST_TAGS"] = tag_blacklist_from_file
    CONFIG["HOT_TAGS"] = hot_tags_from_file
    CONFIG["SYMBOL_BLACKLIST"] = load_earning_symbol_blacklist(BLACKLIST_JSON_FILE)
    
    all_symbols, symbol_to_sector_map = load_all_symbols(SECTORS_JSON_FILE, CONFIG["TARGET_SECTORS"])
    if all_symbols is None:
        log_detail("错误: 无法加载symbols，程序终止。")
        return

    symbol_blacklist = CONFIG.get("SYMBOL_BLACKLIST", set())
    if symbol_blacklist:
        all_symbols = [s for s in all_symbols if s not in symbol_blacklist]
    
    symbol_to_tags_map = load_symbol_tags(DESCRIPTION_JSON_FILE)
    # ========== 修改点：调用 build_stock_data_cache 时传入 TARGET_DATE ==========
    stock_data_cache = build_stock_data_cache(
        all_symbols, 
        symbol_to_sector_map, 
        DB_FILE, 
        SYMBOL_TO_TRACE, 
        log_detail, 
        symbol_to_tags_map, 
        target_date=TARGET_DATE  # 传入参数
    )
    
    # ========== 修改点 1：perform_filter_pass 不再进行 Tag 过滤 ==========
    def perform_filter_pass(symbols_to_check, drop_large, drop_small, pass_name):
        preliminary_results = []       # 普通股 (PE 分组)
        oversell_w_candidates = []     # 仅限条件 6 (OverSell_W)
        pe_deep_candidates = []        # 条件 1-5 触发普通深跌
        pe_deeper_candidates = []        # 条件 1-5 触发超级深跌
        pe_w_candidates = []           # 条件 1-5 触发 W 底 (PE_W)

        for symbol in symbols_to_check:
            data = stock_data_cache.get(symbol)
            if not (data and data['is_valid']):
                continue
            data['symbol'] = symbol
            
            # 步骤A: 检查入口条件
            # ========== 修改点：接收4个返回值 ==========
            passed_any, passed_cond5, passed_cond6, passed_cond7 = check_entry_conditions(data, SYMBOL_TO_TRACE, log_detail)
            
            if not passed_any:
                continue

            # 步骤B: 应用通用过滤器
            # 逻辑：如果是条件5、6、7触发，跳过价格回撤过滤 (因为这些策略自带价格位置判断)
            should_skip_drawdown = passed_cond5 or passed_cond6 or passed_cond7
            
            if apply_common_filters(data, SYMBOL_TO_TRACE, log_detail, drop_large, drop_small, skip_drawdown=should_skip_drawdown):
                # ========== [修改] 开始：此处新增日期重合检查，修复条件6漏检问题 ==========
                # 检查最新交易日是否等于财报日
                # 这一步现在对 条件6 和 条件1-5 同时生效
                if data['latest_date_str'] == data['latest_er_date_str']:
                    if symbol == SYMBOL_TO_TRACE:
                        log_detail(f" - [通用过滤] 失败 (日期重合): 最新交易日({data['latest_date_str']}) 与 最新财报日相同。")
                    continue # 直接跳过，不放入任何列表
                # --- 分流逻辑 ---
                
                # ========== 修改点：条件6 OR 条件7 都进入 OverSell_W ==========
                if passed_cond6 or passed_cond7:
                    # 优先级 1：W底 (Cond6) 或 强财报深跌 (Cond7) 进 OverSell_W
                    oversell_w_candidates.append(symbol)
                
                else:
                    # 优先级 2：条件 1-5 进来的，检查是否符合 W 底形态
                    is_w_bottom = check_w_bottom_pattern(data, CONFIG, log_detail, SYMBOL_TO_TRACE, check_strict_er_drop=False)
                    
                    if is_w_bottom:
                        pe_w_candidates.append(symbol)
                    else:
                        # ========== 【新增代码：添加 W底 失败总结日志】 ==========
                        if symbol == SYMBOL_TO_TRACE:
                            log_detail(f" - [W形态最终裁定]： W底形态未构成 -> 转入深跌判定流程。")
                        
                        # --- 进入深跌判定流程 ---
                        latest_price = data['latest_price']
                        
                        # 1. 获取基准价格
                        er_close_price = data['all_er_prices'][-1]       # 财报日当天收盘价
                        
                        # 兜底：防止 None 导致计算报错
                        er_window_high = data.get('er_window_high_price') # 财报窗口期(含财报日及后3天)最高价
                        if er_window_high is None: 
                                er_window_high = er_close_price
                        high_since_er = data.get('high_since_er')         # 财报日至今(含今天)的最高收盘价
                        if high_since_er is None:
                                high_since_er = er_window_high

                        # A. 【新增判断】首先判断是否满足 Deeper (35%)
                        limit_deeper = CONFIG["PE_DEEPER_DROP_THRESHOLD"]
                        pass_deeper = latest_price <= er_close_price * (1 - limit_deeper)

                        if pass_deeper:
                            if symbol == SYMBOL_TO_TRACE:
                                log_detail(f" - [超深跌Deeper判定] 命中: 较财报日跌幅 {((er_close_price-latest_price)/er_close_price):.2%} >= {limit_deeper:.0%}")
                            pe_deeper_candidates.append(symbol) # 进 PE_Deeper
                        
                        else:
                            # B. 如果不满足 35%，再判断是否满足原有的 Deep 三准则
                            # 2. 设定阈值
                            # 标准1：基于财报日当天的跌幅阈值 (15%)
                            limit_er_base = CONFIG["PE_DEEP_DROP_THRESHOLD"]
                            
                            # 标准2：基于窗口期最高价的跌幅阈值 (16%)
                            limit_window_base = CONFIG["PE_DEEP_MAX_DROP_THRESHOLD"]
                            
                            # 标准3 (新增)：基于财报日至今最高价的跌幅阈值 (18%)
                            limit_high_since_er_base = CONFIG.get("PE_DEEP_HIGH_SINCE_ER_THRESHOLD", 0.18)

                            # 3. 计算判断条件
                            # 条件A: (财报日价 - 最新价) / 财报日价 > 15%
                            pass_er_base = latest_price <= er_close_price * (1 - limit_er_base)
                            
                            # 条件B: (窗口最高价 - 最新价) / 窗口最高价 > 16%
                            pass_window_base = latest_price <= er_window_high * (1 - limit_window_base)
                            
                            # 条件C (新增): (财报日至今最高价 - 最新价) / 财报日至今最高价 > 18%
                            pass_high_since_base = latest_price <= high_since_er * (1 - limit_high_since_er_base)

                            # 4. 综合判定 (满足任一即可)
                            if pass_er_base or pass_window_base or pass_high_since_base:
                                if symbol == SYMBOL_TO_TRACE:
                                    log_detail(f" - [深跌Deep判定] 命中: 财报日跌幅({pass_er_base}) OR 窗口高点跌幅({pass_window_base}) OR 至今高点跌幅({pass_high_since_base})")
                                    log_detail(f"   * 最新价: {latest_price:.2f}")
                                    log_detail(f"   * 财报日价: {er_close_price:.2f} (需跌破 {er_close_price*(1-limit_er_base):.2f})")
                                    log_detail(f"   * 窗口高点: {er_window_high:.2f} (需跌破 {er_window_high*(1-limit_window_base):.2f})")
                                    log_detail(f"   * 至今高点: {high_since_er:.2f} (需跌破 {high_since_er*(1-limit_high_since_er_base):.2f})")
                                
                                pe_deep_candidates.append(symbol) # 进 PE_Deep
                            else:
                                # 优先级 4：普通股
                                preliminary_results.append(symbol)

        # 对普通组进行 PE 分组
        pe_valid, pe_invalid = apply_post_filters(preliminary_results, stock_data_cache, SYMBOL_TO_TRACE, log_detail)

        # [修改] 直接返回原始列表，不做 Tag 过滤
        return (
            pe_valid, 
            pe_invalid, 
            oversell_w_candidates, 
            pe_deep_candidates, 
            pe_w_candidates,
            pe_deeper_candidates
        )

    # --- 执行筛选 ---
    strict_symbols, relaxed_symbols, sub_relaxed_symbols, super_relaxed_symbols = [], [], [], []
    initial_candidates = list(stock_data_cache.keys())
    for symbol in initial_candidates:
        data = stock_data_cache.get(symbol)
        if not (data and data['is_valid']): continue
        data['symbol'] = symbol
        filter_mode = check_special_condition(data, CONFIG, log_detail, SYMBOL_TO_TRACE)
        if filter_mode == 3: super_relaxed_symbols.append(symbol)
        elif filter_mode == 2: sub_relaxed_symbols.append(symbol)
        elif filter_mode == 1: relaxed_symbols.append(symbol)
        else: strict_symbols.append(symbol)

    # 接收 5 个返回值 (Raw Data: 包含可能被 Tag 黑名单命中的 Symbol)
    res_super = perform_filter_pass(super_relaxed_symbols, CONFIG["SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "最宽松")
    res_sub = perform_filter_pass(sub_relaxed_symbols, CONFIG["SUB_RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["SUB_RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "次宽松")
    res_relaxed = perform_filter_pass(relaxed_symbols, CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "普通宽松")
    res_strict = perform_filter_pass(strict_symbols, CONFIG["PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["PRICE_DROP_PERCENTAGE_SMALL"], "严格")

    # ========== 修改点 2: 汇总 Raw 数据 (包含 Tag 黑名单，用于 History) ==========
    raw_pe_valid = res_super[0] + res_sub[0] + res_relaxed[0] + res_strict[0]
    raw_pe_invalid = res_super[1] + res_sub[1] + res_relaxed[1] + res_strict[1]
    raw_oversell_w = res_super[2] + res_sub[2] + res_relaxed[2] + res_strict[2]
    raw_pe_deep = res_super[3] + res_sub[3] + res_relaxed[3] + res_strict[3]
    raw_pe_w = res_super[4] + res_sub[4] + res_relaxed[4] + res_strict[4]
    raw_pe_deeper = res_super[5] + res_sub[5] + res_relaxed[5] + res_strict[5]

    # ========== 修改点 3: 准备写入 Panel 的数据 (需进行 Tag 过滤) ==========
    tag_blacklist = CONFIG["BLACKLIST_TAGS"]
    def filter_tags(syms):
        # 仅保留没有命中黑名单 Tag 的 symbol
        return [s for s in syms if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]

    blacklist = load_blacklist(BLACKLIST_JSON_FILE)
    try:
        with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f: panel_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): panel_data = {}

    exist_Strategy34 = set(panel_data.get('Strategy34', {}).keys())
    exist_Strategy12 = set(panel_data.get('Strategy12', {}).keys())
    # exist_today = set(panel_data.get('Today', {}).keys())
    exist_must = set(panel_data.get('Must', {}).keys())
    already_in_panels = exist_Strategy34 | exist_Strategy12 | exist_must

    # [逻辑] PE_valid/invalid: 过滤 Tags + 黑名单 + 已存在
    # [逻辑] Deep/W/OverSell: 过滤 Tags (根据你原代码逻辑，这几组不剔除黑名单和已存在)
    final_pe_valid_to_write = sorted(list(set(filter_tags(raw_pe_valid)) - blacklist - already_in_panels))
    final_pe_invalid_to_write = sorted(list(set(filter_tags(raw_pe_invalid)) - blacklist - already_in_panels))
    
    final_oversell_w_to_write = sorted(list(set(filter_tags(raw_oversell_w))))
    final_pe_deep_to_write = sorted(list(set(filter_tags(raw_pe_deep))))
    final_pe_deeper_to_write = sorted(list(set(filter_tags(raw_pe_deeper))))
    final_pe_w_to_write = sorted(list(set(filter_tags(raw_pe_w))))

    final_pe_deep_to_write = sorted(list(set(filter_tags(raw_pe_deep)) - already_in_panels))
    # final_pe_w_to_write = sorted(list(set(filter_tags(raw_pe_w)) - blacklist - already_in_panels))
    # final_oversell_w_to_write = sorted(list(set(filter_tags(raw_oversell_w)) - blacklist - already_in_panels))

    # 追踪日志 (增强版：显示拦截原因)
    if SYMBOL_TO_TRACE:
        raw_sets = [
            (set(raw_pe_valid), "PE_valid"), (set(raw_pe_invalid), "PE_invalid"),
            (set(raw_pe_deep), "PE_Deep"), (set(raw_pe_w), "PE_W"), (set(raw_oversell_w), "OverSell_W") 
        ]
        for s_set, name in raw_sets:
            if SYMBOL_TO_TRACE in s_set:
                is_tag_blocked = bool(set(symbol_to_tags_map.get(SYMBOL_TO_TRACE, [])).intersection(tag_blacklist))
                # PE_valid/invalid 还会检查 blacklist 和 existing
                if name in ["PE_valid", "PE_invalid"]:
                    if SYMBOL_TO_TRACE in blacklist:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' ({name}) 算法通过，但在 'newlow' 黑名单中 -> 不写Panel。")
                    elif SYMBOL_TO_TRACE in already_in_panels:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' ({name}) 算法通过，但已在其他 Panel 中 -> 不写Panel。")
                    elif is_tag_blocked:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' ({name}) 算法通过，但命中 Tag 黑名单 -> 不写Panel。")
                    else:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' 将写入 ({name})。")
                else:
                    # 其他组只检查 Tag
                    if is_tag_blocked:
                         log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' ({name}) 算法通过，但命中 Tag 黑名单 -> 不写Panel。")
                    else:
                         log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' 将写入 ({name})。")

    hot_tags = set(CONFIG.get("HOT_TAGS", set()))
    def build_symbol_note_map(symbols):
        note_map = {}
        for sym in symbols:
            d = stock_data_cache.get(sym, {})
            cond3_type = d.get('cond3_drop_type')
            tags = set(symbol_to_tags_map.get(sym, []))
            is_hot = bool(tags & hot_tags)
            base = ""
            # 动态匹配标签
            if cond3_type:
                base = f"{sym}{cond3_type}" # 如果 cond3_type 是 "9"，则生成 "INFY9"
            else:
                base = ""
            if base: note_map[sym] = base + ("热" if is_hot else "")
            else: note_map[sym] = f"{sym}热" if is_hot else ""
        return note_map

    # ============================================================
    # 核心修改：回测模式安全拦截网 (Security Net for Backtest)
    # ============================================================
    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 [安全拦截] 回测模式 (Date: {TARGET_DATE}) 已启用。")
        log_detail(f"🛑 为防止覆盖当前数据，以下文件写入操作已被取消：")
        log_detail(f"   1. 面板文件: {os.path.basename(PANEL_JSON_FILE)}")
        log_detail(f"   2. 历史记录: {os.path.basename(EARNING_HISTORY_JSON_FILE)}")
        
        # 模拟打印一下结果，让你知道如果写入会写些什么 (Optional)
        log_detail("-" * 40)
        log_detail(f"📊 [模拟结果] 如果不是回测，将写入以下数量的 Symbol:")
        log_detail(f"   - PE_valid:   {len(final_pe_valid_to_write)} 个")
        log_detail(f"   - PE_invalid: {len(final_pe_invalid_to_write)} 个")
        log_detail(f"   - PE_Deep:    {len(final_pe_deep_to_write)} 个")
        log_detail(f"   - PE_Deeper:  {len(final_pe_deeper_to_write)} 个")
        log_detail(f"   - PE_W:       {len(final_pe_w_to_write)} 个")        # 【新增】补上 PE_W 的统计
        log_detail(f"   - OverSell_W: {len(final_oversell_w_to_write)} 个")  # 【修正】文案改为 OverSell_W
        
        if SYMBOL_TO_TRACE:
             # 检查目标 Symbol 是否在最终列表中 (模拟验证)
             in_valid = SYMBOL_TO_TRACE in final_pe_valid_to_write
             in_deep = SYMBOL_TO_TRACE in final_pe_deep_to_write
             in_deeper = SYMBOL_TO_TRACE in final_pe_deeper_to_write
             in_pe_w = SYMBOL_TO_TRACE in final_pe_w_to_write           # 【新增】
             in_oversell = SYMBOL_TO_TRACE in final_oversell_w_to_write # 【新增】

             log_detail(f"🔎 [验证] Symbol '{SYMBOL_TO_TRACE}' 最终筛选状态:")
             log_detail(f"   - 是否进入 PE_valid:   {in_valid}")
             log_detail(f"   - 是否进入 PE_Deep:    {in_deep}")
             log_detail(f"   - 是否进入 PE_Deeper:  {in_deeper}")
             log_detail(f"   - 是否进入 PE_W:       {in_pe_w}")       # 【新增】
             log_detail(f"   - 是否进入 OverSell_W: {in_oversell}")   # 【新增】
        
        log_detail("="*60 + "\n")
        
        # 直接结束函数，后续所有的 update_json_panel 和 update_earning_history_json 都不会执行
        return 

    # ============================================================
    # 以下是正常的生产模式写入逻辑 (只有 TARGET_DATE 为空时才会执行)
    # ============================================================

    # 1. 写入 Panel (Filtered Data)
    pe_valid_notes = build_symbol_note_map(final_pe_valid_to_write)
    pe_invalid_notes = build_symbol_note_map(final_pe_invalid_to_write)
    oversell_w_notes = build_symbol_note_map(final_oversell_w_to_write)
    pe_deep_notes = build_symbol_note_map(final_pe_deep_to_write)
    pe_w_notes = build_symbol_note_map(final_pe_w_to_write)
    pe_deeper_notes = build_symbol_note_map(final_pe_deeper_to_write)

    # 写入 PE_valid
    update_json_panel(final_pe_valid_to_write, PANEL_JSON_FILE, 'PE_valid', symbol_to_note=pe_valid_notes)
    # 同步写入 PE_valid_backup
    update_json_panel(final_pe_valid_to_write, PANEL_JSON_FILE, 'PE_valid_backup', symbol_to_note=pe_valid_notes)
    
    # 写入 PE_invalid
    update_json_panel(final_pe_invalid_to_write, PANEL_JSON_FILE, 'PE_invalid', symbol_to_note=pe_invalid_notes)
    # 同步写入 PE_invalid_backup
    update_json_panel(final_pe_invalid_to_write, PANEL_JSON_FILE, 'PE_invalid_backup', symbol_to_note=pe_invalid_notes)
    
    # 1. 写入 OverSell_W (仅条件 6)
    update_json_panel(final_oversell_w_to_write, PANEL_JSON_FILE, 'OverSell_W', symbol_to_note=oversell_w_notes)
    update_json_panel(final_oversell_w_to_write, PANEL_JSON_FILE, 'OverSell_W_backup', symbol_to_note=oversell_w_notes)

    # 2. 写入 PE_Deep (条件 1-5 的深跌)
    update_json_panel(final_pe_deep_to_write, PANEL_JSON_FILE, 'PE_Deep', symbol_to_note=pe_deep_notes)
    update_json_panel(final_pe_deep_to_write, PANEL_JSON_FILE, 'PE_Deep_backup', symbol_to_note=pe_deep_notes)

    # 写入 PE_Deeper 及其备份
    update_json_panel(final_pe_deeper_to_write, PANEL_JSON_FILE, 'PE_Deeper', symbol_to_note=pe_deeper_notes)
    update_json_panel(final_pe_deeper_to_write, PANEL_JSON_FILE, 'PE_Deeper_backup', symbol_to_note=pe_deeper_notes)

    # 写入 PE_W (条件1-5且形态良好)
    update_json_panel(final_pe_w_to_write, PANEL_JSON_FILE, 'PE_W', symbol_to_note=pe_w_notes)
    update_json_panel(final_pe_w_to_write, PANEL_JSON_FILE, 'PE_W_backup', symbol_to_note=pe_w_notes)

    # ========== 修改点 4: 写入 History (Raw Data, 包含 Tag 黑名单) ==========
    # 原逻辑：合并所有 Raw 列表写入 "no_season"
    # 新逻辑：分别写入各自的组名

    # 定义组名和对应的原始数据列表 (使用 Raw 数据以保持和原逻辑一致，包含 Tag 黑名单)
    groups_to_log = {
        "PE_valid": raw_pe_valid,
        "PE_invalid": raw_pe_invalid,
        "PE_Deep": raw_pe_deep,
        "PE_Deeper": raw_pe_deeper,
        "PE_W": raw_pe_w,
        "OverSell_W": raw_oversell_w
    }

    has_written_any = False
    for group_name, symbols in groups_to_log.items():
        if symbols:
            # 去重并排序
            unique_symbols = sorted(list(set(symbols)))
            # 分别调用更新函数，传入对应的 group_name
            update_earning_history_json(EARNING_HISTORY_JSON_FILE, group_name, unique_symbols, log_detail)
            has_written_any = True

    if not has_written_any:
        log_detail("\n--- 无符合条件的 symbol 可写入 Earning_History.json ---")

# --- 6. 主执行流程 ---
def main():
    if SYMBOL_TO_TRACE:
        print(f"追踪模式已启用，目标: {SYMBOL_TO_TRACE}。日志将写入: {LOG_FILE_PATH}")
        try:
            with open(LOG_FILE_PATH, 'w', encoding='utf-8') as log_file:
                def log_detail_file(message):
                    log_file.write(message + '\n')
                    print(message)
                run_processing_logic(log_detail_file)
        except IOError as e:
            print(f"错误：无法打开或写入日志文件 {LOG_FILE_PATH}: {e}")
    else:
        print("追踪模式未启用 (SYMBOL_TO_TRACE 为空)。将不会生成日志文件。")
        def log_detail_console(message):
            print(message)
        run_processing_logic(log_detail_console)
    
    print("\n程序运行结束。")

if __name__ == '__main__':
    main()
