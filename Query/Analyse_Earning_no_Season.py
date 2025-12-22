import json
import sqlite3
import os
import datetime

SYMBOL_TO_TRACE = "VLO"
LOG_FILE_PATH = "/Users/yanzhang/Downloads/No_Season_trace_log.txt"

# --- 1. 配置文件和路径 ---
# 使用 os.path.expanduser('~') 获取用户主目录，增强可移植性
BASE_PATH = os.path.expanduser('~')

PATHS = {
    "config_dir": os.path.join(BASE_PATH, 'Coding/Financial_System/Modules'),
    "db_dir": os.path.join(BASE_PATH, 'Coding/Database'),
    "news_dir": os.path.join(BASE_PATH, 'Coding/News'),
    "sectors_json": lambda config_dir: os.path.join(config_dir, 'Sectors_All.json'),
    "panel_json": lambda config_dir: os.path.join(config_dir, 'Sectors_panel.json'),
    "blacklist_json": lambda config_dir: os.path.join(config_dir, 'Blacklist.json'),
    "description_json": lambda config_dir: os.path.join(config_dir, 'description.json'),
    "tags_setting_json": lambda config_dir: os.path.join(config_dir, 'tags_filter.json'),
    "earnings_history_json": lambda config_dir: os.path.join(config_dir, 'Earning_History.json'),
    "db_file": lambda db_dir: os.path.join(db_dir, 'Finance.db'),
    "output_news": lambda news_dir: os.path.join(news_dir, 'Filter_Earning.txt'),
    "output_backup": lambda news_dir: os.path.join(news_dir, 'backup/Filter_Earning.txt'),
}

# 动态生成完整路径
CONFIG_DIR = PATHS["config_dir"]
DB_DIR = PATHS["db_dir"]
NEWS_DIR = PATHS["news_dir"]
DB_FILE = PATHS["db_file"](DB_DIR)
SECTORS_JSON_FILE = PATHS["sectors_json"](CONFIG_DIR)
BLACKLIST_JSON_FILE = PATHS["blacklist_json"](CONFIG_DIR)
PANEL_JSON_FILE = PATHS["panel_json"](CONFIG_DIR)
NEWS_FILE = PATHS["output_news"](NEWS_DIR)
BACKUP_FILE = PATHS["output_backup"](NEWS_DIR)
DESCRIPTION_JSON_FILE = PATHS["description_json"](CONFIG_DIR)
TAGS_SETTING_JSON_FILE = PATHS["tags_setting_json"](CONFIG_DIR)
EARNING_HISTORY_JSON_FILE = PATHS["earnings_history_json"](CONFIG_DIR)

# --- 2. 可配置参数 ---
CONFIG = {
    "TARGET_SECTORS": {
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    },
    # ========== 代码修改开始 1/3：新增中国概念股成交额阈值 ==========
    # "TURNOVER_THRESHOLD": 100_000_000,
    "TURNOVER_THRESHOLD": 200_000_000,
    "TURNOVER_THRESHOLD_CHINA": 400_000_000,  # 新增：中国概念股的成交额阈值

    "RECENT_EARNINGS_COUNT": 2,
    "MARKETCAP_THRESHOLD": 200_000_000_000,  # 2000亿
    "MARKETCAP_THRESHOLD_MEGA": 500_000_000_000,  # 5000亿

    "COND5_WINDOW_DAYS": 6,

    # 严格筛选标准 (第一轮)
    # "PRICE_DROP_PERCENTAGE_LARGE": 0.079,  # <2000亿=7.9%
    # "PRICE_DROP_PERCENTAGE_SMALL": 0.06,   # 2000亿 ≤ 市值 < 5000亿 = 6%
    # "PRICE_DROP_PERCENTAGE_MEGA": 0.05,    # ≥5000亿=5%
    "PRICE_DROP_PERCENTAGE_LARGE": 0.1,  # <2000亿=10%
    "PRICE_DROP_PERCENTAGE_SMALL": 0.09,   # 2000亿 ≤ 市值 < 5000亿 = 9%
    "PRICE_DROP_PERCENTAGE_MEGA": 0.07,    # ≥5000亿=7%

    # 普通宽松筛选标准
    # "RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.07,  # <2000亿=7%
    # "RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.05,  # ≥2000亿=5%
    "RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.1,  # <2000亿=10%
    "RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.08,  # ≥2000亿=8%

    # 新增：次宽松筛选标准
    # "SUB_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.06,  # <2000亿=6%
    # "SUB_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.04,  # ≥2000亿=4%
    "SUB_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.09,  # <2000亿=9%
    "SUB_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.07,  # ≥2000亿=7%

    # 最宽松筛选标准
    # "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.05,  # <2000亿=5%
    # "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.03,  # ≥2000亿=3%
    "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.07,  # <2000亿=7%
    "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.05,  # ≥2000亿=5%

    # 触发“最宽松”标准的财报收盘价价差百分比 (条件C)
    # "ER_PRICE_DIFF_THRESHOLD": 0.04,
    "ER_PRICE_DIFF_THRESHOLD": 0.06,

    # 触发宽松筛选的最小分组数量 (仅对 PE_valid 组生效)
    "MIN_PE_VALID_SIZE_FOR_RELAXED_FILTER": 5,

    # 回撤阀值 5%：最新收盘价比最新交易日前10天收盘价的最低值高不超过5%（如果10天内有财报，则将财报日收盘价作为最低值）
    "MAX_INCREASE_PERCENTAGE_SINCE_LOW": 0.05,

    # 条件1c 的专属参数：最新价比最新财报收盘价低至少 X%
    # "PRICE_DROP_FOR_COND1C": 0.14,
    "PRICE_DROP_FOR_COND1C": 0.17,

    # 条件3参数
    # "COND3_DROP_THRESHOLDS": [0.07, 0.15],  # 7% 与 15%
    "COND3_DROP_THRESHOLDS": [0.09, 0.15],  # 9% 与 15%
    "COND3_LOOKBACK_DAYS": 60,

    # 条件4参数: 财报日至今最高价相比最新价的涨幅阈值
    # "COND4_RISE_THRESHOLD": 0.07,  # 7%
    "COND4_RISE_THRESHOLD": 0.09,  # 9%

    # ========== 新增：条件5的参数 ==========
    "COND5_ER_TO_HIGH_THRESHOLD": 0.3,  # 财报日到最高价的涨幅阈值 30%
    # "COND5_HIGH_TO_LATEST_THRESHOLD": 0.079,  # 最高价到最新价的跌幅阈值 7.9%
    "COND5_HIGH_TO_LATEST_THRESHOLD": 0.09,  # 最高价到最新价的跌幅阈值 9%

    # ========== 代码修改开始 1/4：新增条件6（抄底W底）参数 ==========
    "COND6_ER_DROP_A_THRESHOLD": 0.25,  # 财报跌幅分界线 25%
    "COND6_LOW_DROP_B_LARGE": 0.09,     # 如果A > 25%，则B需 > 9%
    "COND6_LOW_DROP_B_SMALL": 0.12,     # 如果A <= 25%，则B需 > 12%

    # W底形态参数
    # "COND6_W_BOTTOM_PRICE_TOLERANCE": 0.038,  # 两个谷底的价格差容忍度 (3.8%)
    # "COND6_W_BOTTOM_MIN_DAYS_GAP": 3,        # 两个谷底之间的最小间隔天数
    "COND6_W_BOTTOM_PRICE_TOLERANCE": 0.045,  # 两个谷底的价格差容忍度 (4.8%)
    "COND6_W_BOTTOM_MIN_DAYS_GAP": 5,        # 两个谷底之间的最小间隔天数
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
def build_stock_data_cache(symbols, symbol_to_sector_map, db_path, symbol_to_trace, log_detail, symbol_to_tags_map):
    cache = {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    marketcap_exists = True

    for i, symbol in enumerate(symbols):
        is_tracing = (symbol == symbol_to_trace)
        data = {'is_valid': False}
        sector_name = symbol_to_sector_map.get(symbol)
        
        if not sector_name:
            if is_tracing: log_detail(f"[{symbol}] 失败: 在板块映射中未找到该symbol。")
            continue

        cursor.execute("SELECT date, price FROM Earning WHERE name = ? ORDER BY date ASC", (symbol,))
        er_rows = cursor.fetchall()
        if not er_rows:
            if is_tracing: log_detail(f"[{symbol}] 失败: 在Earning表中未找到任何财报记录。")
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

        cursor.execute(f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? ORDER BY date DESC LIMIT 1', (symbol,))
        latest_row = cursor.fetchone()
        
        if not latest_row or latest_row[1] is None or latest_row[2] is None:
            if is_tracing: log_detail(f"[{symbol}] 失败: 未能获取有效的最新交易日数据。查询结果: {latest_row}")
            continue

        data['latest_date_str'], data['latest_price'], data['latest_volume'] = latest_row
        if is_tracing: log_detail(f"[{symbol}] 步骤3: 获取最新交易日数据。日期: {data['latest_date_str']}, 价格: {data['latest_price']}, 成交量: {data['latest_volume']}")

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

        cursor.execute(f'SELECT MAX(price) FROM "{sector_name}" WHERE name = ? AND date >= ?', (symbol, data['latest_er_date_str']))
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
        # ========== 代码修改结束 2/3 ==========

        # ========== 代码修改开始 2/4：获取条件6所需的完整价格序列 ==========
        # 原有的逻辑获取了 prev_10_prices 和 er_6_day_window_low，但为了算W底，我们需要
        # 从最新财报日(含)到最新交易日(含)的所有收盘价
        cursor.execute(f'SELECT date, price FROM "{sector_name}" WHERE name = ? AND date >= ? ORDER BY date ASC', (symbol, data['latest_er_date_str']))
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
                cond3_type = None
                thresholds = sorted(CONFIG["COND3_DROP_THRESHOLDS"])
                if drop_pct_vs_N_high >= max(thresholds): cond3_type = '15'
                elif drop_pct_vs_N_high >= min(thresholds): cond3_type = '7'
                data['cond3_drop_type'] = cond3_type

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
    drop_pct = (last_N_high - latest_price) / last_N_high if last_N_high > 0 else 0.0
    thresholds = sorted(config["COND3_DROP_THRESHOLDS"])
    hit_15 = drop_pct >= max(thresholds)
    hit_7 = drop_pct >= min(thresholds)
    if is_tracing:
        log_detail(f" - 最近{lookback_days}天最高价: {last_N_high:.2f}, 最新价: {latest_price:.2f}, 跌幅: {drop_pct:.2%}")
        log_detail(f"  - 命中15%: {hit_15}, 命中7%: {hit_7}, cond3_drop_type缓存: {cond3_type}")
    if cond3_type in ('7', '15'):
        if is_tracing: log_detail(f"  - 结果: True (命中条件3, 类型: {cond3_type})")
        return True
    if hit_15:
        data['cond3_drop_type'] = '15'
        if is_tracing: log_detail("  - 结果: True (兜底命中15%)")
        return True
    if hit_7:
        data['cond3_drop_type'] = '7'
        if is_tracing: log_detail("  - 结果: True (兜底命中7%)")
        return True
    if is_tracing: log_detail("  - 结果: False (不满足条件3)")
    return False

def check_new_condition_4(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件4评估 ---")
    high_since_er = data.get('high_since_er')
    latest_price = data.get('latest_price')
    rise_threshold = config.get('COND4_RISE_THRESHOLD', 0.07)
    if high_since_er is None or latest_price is None or latest_price <= 0:
        if is_tracing: log_detail(f"  - 结果: False (数据不足: high_since_er={high_since_er}, latest_price={latest_price})")
        return False
    threshold_price = latest_price * (1 + rise_threshold)
    passed = high_since_er >= threshold_price
    if is_tracing:
        rise_pct = (high_since_er - latest_price) / latest_price
        log_detail(f"  - 财报日至今最高价: {high_since_er:.2f}")
        log_detail(f"  - 最新收盘价: {latest_price:.2f}")
        log_detail(f"  - 实际涨幅: {rise_pct:.2%}")
        log_detail(f"  - 要求涨幅: {rise_threshold:.2%}")
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
    if is_tracing: log_detail(f"   - [W底检测启动] 模式: {mode_str}")

    # 1. 数据准备
    all_er_prices = data.get('all_er_prices', [])
    prices_series = data.get('prices_since_er_series', [])
    dates_series = data.get('dates_since_er_series', [])

    if len(all_er_prices) < 2: 
        if is_tracing: log_detail(f"   - [失败] 财报数据不足 2 条。")
        return False
    if not prices_series or len(prices_series) < 10: 
        if is_tracing: log_detail(f"   - [失败] 财报后交易日数据不足 10 天。")
        return False

    latest_er_price = all_er_prices[-1]
    
    # --- 步骤 1: 仅在严格模式下检查 Drop A 和设定 Drop B 阈值 ---
    threshold_b = 0.12 # 默认值
    
    if check_strict_er_drop:
        prev_er_price = all_er_prices[-2]
        if prev_er_price <= 0: return False
        
        er_drop_a_val = (prev_er_price - latest_er_price) / prev_er_price
        threshold_a = config["COND6_ER_DROP_A_THRESHOLD"] # 0.25

        # 动态设定 条件B 的阈值
        if er_drop_a_val > threshold_a:
            threshold_b = config["COND6_LOW_DROP_B_LARGE"] # > 9%
        elif er_drop_a_val > 0.10: # 至少跌 10%
            threshold_b = config["COND6_LOW_DROP_B_SMALL"] # > 12%
        else:
            if is_tracing: 
                log_detail(f"   - [失败-Drop A] 财报间跌幅 {er_drop_a_val:.2%} <= 10%，不满足抄底前提。")
            return False
        
        if is_tracing:
            log_detail(f"   - [通过-Drop A] 财报间跌幅 {er_drop_a_val:.2%}，设置深度阈值 B > {threshold_b:.1%}")

    # --- 步骤 2: 寻找 W 底几何形态 ---
    
    # 锁定 V2 (右底): 必须是昨天 (index -2)
    # 今天 (index -1), 昨天 (index -2), 前天 (index -3)
    curr_price = prices_series[-1] 
    prev_price = prices_series[-2] 
    prev2_price = prices_series[-3]

    # [几何检查] 右底必须是局部低点 (比前天低，且比今天低，意味着今天开始反弹或企稳)
    if not (prev_price < prev2_price and prev_price < curr_price):
        if is_tracing:
            log_detail(f"   - [失败-V2定位] 昨天({prev_price})不是局部低点(需小于{prev2_price}且小于{curr_price})，无法构成右底。")
        return False

    v2 = prev_price
    idx2 = len(prices_series) - 2
    v2_date = dates_series[idx2]

    price_tolerance = config["COND6_W_BOTTOM_PRICE_TOLERANCE"] # 0.048
    min_days_gap = config["COND6_W_BOTTOM_MIN_DAYS_GAP"]      # 5

    # 向前回溯寻找左底 (V1)
    start_search_index = idx2 - min_days_gap
    
    if start_search_index < 1:
        if is_tracing: log_detail(f"   - [失败-间隔] 距离财报日过近，无法满足最小间隔 {min_days_gap} 天。")
        return False

    if is_tracing: log_detail(f"   - [V2已锁定] 日期: {v2_date}, 价格: {v2}, 开始寻找V1...")

    found_valid_pattern = False

    for i in range(start_search_index, 0, -1):
        v1 = prices_series[i]
        v1_date = dates_series[i]

        # [几何形态检查 1] 局部低点
        # 必须比它前一天低，且比它后一天低
        if not (v1 < prices_series[i-1] and v1 < prices_series[i+1]):
            # 不是局部低点，静默跳过，不需要日志
            continue

        # 找到一个潜在的 V1
        if is_tracing: log_detail(f"     > 发现潜在V1: {v1_date} (价格:{v1})")

        # [几何形态检查 2] 高度差检查 (Symmetry)
        diff_pct = abs(v1 - v2) / min(v1, v2)
        if diff_pct > price_tolerance: 
            if is_tracing: log_detail(f"       x [失败] 左右底高低差 {diff_pct:.2%} > 容忍度 {price_tolerance:.1%}")
            continue

        # [几何形态检查 3] 颈线反弹力度
        # 检查 V1 和 V2 之间的最高价 (Peak)
        peak_prices = prices_series[i+1 : idx2]
        if not peak_prices: 
            continue
            
        max_peak = max(peak_prices)
        avg_valley = (v1 + v2) / 2
        peak_rise = (max_peak - avg_valley) / avg_valley

        # 这里的 0.025 是硬编码的颈线反弹力度，可以考虑放入配置，但目前暂且保留
        min_peak_rise = 0.025
        if peak_rise < min_peak_rise: 
            if is_tracing: log_detail(f"       x [失败] 中间反弹力度 {peak_rise:.2%} < {min_peak_rise:.1%}, 形态不显著")
            continue

        # --- 步骤 3: 最终裁决 (分模式) ---
        
        # 1. 严格模式 (Condition 6): 必须检查深度
        if check_strict_er_drop:
            valley_min_price = min(v1, v2)
            drop_b_val = (latest_er_price - valley_min_price) / latest_er_price
            
            if drop_b_val > threshold_b:
                actual_gap = idx2 - i
                if is_tracing:
                    log_detail(f"   - [成功!] V1:{v1:.2f}, V2:{v2:.2f}, 间隔:{actual_gap}天")
                    log_detail(f"   - [深度检查] 深度 {drop_b_val:.2%} > 阈值 {threshold_b:.1%} -> 通过")
                return True
            else:
                if is_tracing:
                    log_detail(f"       x [失败-Drop B] 虽然形态满足，但深度 {drop_b_val:.2%} 不足 (需 > {threshold_b:.1%})")
                # 这里不 continue，因为可能前面还有更深的 V1? 
                # 通常W底找最近的匹配即可，但如果为了严谨可以继续找。
                # 但根据HCA的例子，如果不满足深度，找更远的也没用，先continue看有没有别的组合
                continue

        # 2. 宽松模式 (Condition 1-5): 只要几何形态满足，无视与财报价的关系
        else:
            actual_gap = idx2 - i
            if is_tracing:
                log_detail(f"   - [成功!] V1:{v1:.2f}, V2:{v2:.2f}, 间隔:{actual_gap}天")
                log_detail(f"   - [宽松模式] 跳过深度检查 (Drop B)。")
            return True

    if is_tracing: log_detail(f"   - [结果] 遍历结束，未找到满足所有条件的 V1。")
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
        return (False, False, False) # 修改返回值格式

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

    # 汇总
    passed_any = passed_original_cond1 or passed_new_cond2 or passed_new_cond3 or passed_new_cond4 or passed_new_cond5 or passed_new_cond6
    
    if is_tracing:
        if passed_any:
            reasons = []
            if passed_original_cond1: reasons.append("条件1")
            if passed_new_cond2: reasons.append("条件2")
            if passed_new_cond3: reasons.append("条件3")
            if passed_new_cond4: reasons.append("条件4")
            if passed_new_cond5: reasons.append("条件5")
            if passed_new_cond6: reasons.append("条件6(W底)")
            log_detail(f"\n--- [{symbol}] 入口条件通过 (原因: {'、'.join(reasons)})。")
        else:
            log_detail(f"\n--- [{symbol}] 入口条件失败。六个入口条件均未满足。")

    return (passed_any, passed_new_cond5, passed_new_cond6)

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

    # 1. 提取变量
    max_increase_pct = CONFIG["MAX_INCREASE_PERCENTAGE_SINCE_LOW"]
    threshold_price_10day = baseline_price * (1 + max_increase_pct)
    cond_10day_ok = data['latest_price'] <= threshold_price_10day

    if is_tracing:
        log_detail(f" - [通用过滤2] 相对10日基准价:")
        if using_er_price_logic:
            log_detail(f"   - 策略: 财报日({latest_er_date})在10天内，使用财报日收盘价作为基准。")
        else:
            log_detail(f"   - 策略: 财报日不在10天内，使用10日最低价作为基准。")
        log_detail(f"   - 基准价: {baseline_price:.2f}")
        log_detail(f"   - 判断: 最新价 {data['latest_price']:.2f} <= 基准价*{1+max_increase_pct:.2f} ({threshold_price_10day:.2f}) -> {cond_10day_ok}")
    # ========== 修改结束 ==========

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
    stock_data_cache = build_stock_data_cache(all_symbols, symbol_to_sector_map, DB_FILE, SYMBOL_TO_TRACE, log_detail, symbol_to_tags_map)
    
    # ========== 筛选核心逻辑函数：在筛选通过时标记是否为 Condition 6 ==========
    def perform_filter_pass(symbols_to_check, drop_large, drop_small, pass_name):
        preliminary_results = [] # 非W底的普通股
        oversell_candidates = [] # 条件6触发的股 -> OverSell
        double_candidates = []   # 条件1-5触发W底的股 -> PE_Double

        for symbol in symbols_to_check:
            data = stock_data_cache.get(symbol)
            if not (data and data['is_valid']):
                continue
            data['symbol'] = symbol

            # 步骤A: 检查入口条件
            # 获取三个返回值
            passed_any, passed_cond5, passed_cond6 = check_entry_conditions(data, SYMBOL_TO_TRACE, log_detail)

            # 如果任何入口条件都没通过，则跳过
            if not passed_any:
                continue

            # 步骤B: 应用通用过滤器
            # 如果通过了条件5 OR 条件6，则跳过价格回撤检查 (skip_drawdown=True)
            # 条件5是因为它有自己的高点逻辑
            # 条件6是因为它是抄底逻辑，不需要检查"距离最高点跌幅"
            should_skip_drawdown = passed_cond5 or passed_cond6
            
            if apply_common_filters(data, SYMBOL_TO_TRACE, log_detail, drop_large, drop_small, skip_drawdown=should_skip_drawdown):
                # ========== [修改] 开始：此处新增日期重合检查，修复条件6漏检问题 ==========
                # 检查最新交易日是否等于财报日
                # 这一步现在对 条件6 和 条件1-5 同时生效
                if data['latest_date_str'] == data['latest_er_date_str']:
                    if symbol == SYMBOL_TO_TRACE:
                        log_detail(f" - [通用过滤] 失败 (日期重合): 最新交易日({data['latest_date_str']}) 与 最新财报日相同。")
                    continue # 直接跳过，不放入任何列表
                # --- 分流逻辑 ---
                # 如果通过了条件6（W底），将其放入 oversell_candidates，优先于其他逻辑
                if passed_cond6:
                    # 优先级最高：如果满足条件6（OverSell策略），直接进入 OverSell 组
                    oversell_candidates.append(symbol)
                else:
                    # 如果不满足条件6，说明是 条件1-5 进来的
                    # 此时检查是否具备 W底形态 (使用宽松模式，忽略财报跌幅前提)
                    is_w_bottom = check_w_bottom_pattern(data, CONFIG, log_detail, SYMBOL_TO_TRACE, check_strict_er_drop=False)
                    
                    if is_w_bottom:
                        double_candidates.append(symbol) # 进入 PE_Double 组
                    else:
                        preliminary_results.append(symbol) # 进入普通 PE_valid/invalid 组

        # 对普通组进行 PE 分组
        pe_valid, pe_invalid = apply_post_filters(preliminary_results, stock_data_cache, SYMBOL_TO_TRACE, log_detail)

        # 步骤 D: 基于Tag的过滤 (对三个组都执行)
        tag_blacklist = CONFIG["BLACKLIST_TAGS"]
        final_pe_valid = [s for s in pe_valid if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]
        final_pe_invalid = [s for s in pe_invalid if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]
        final_oversell = [s for s in oversell_candidates if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]
        final_double = [s for s in double_candidates if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]

        # 返回4个列表
        return final_pe_valid, final_pe_invalid, final_oversell, final_double

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

    # 接收4个返回值
    super_relaxed_valid, super_relaxed_invalid, super_relaxed_oversell, super_relaxed_double = perform_filter_pass(super_relaxed_symbols, CONFIG["SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "第一轮(最宽松)")
    sub_relaxed_valid, sub_relaxed_invalid, sub_relaxed_oversell, sub_relaxed_double = perform_filter_pass(sub_relaxed_symbols, CONFIG["SUB_RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["SUB_RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "第一轮(次宽松)")
    relaxed_valid, relaxed_invalid, relaxed_oversell, relaxed_double = perform_filter_pass(relaxed_symbols, CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "第一轮(普通宽松)")
    strict_valid, strict_invalid, strict_oversell, strict_double = perform_filter_pass(strict_symbols, CONFIG["PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["PRICE_DROP_PERCENTAGE_SMALL"], "第一轮(严格)")

    # 汇总各组结果
    pass1_valid = super_relaxed_valid + sub_relaxed_valid + relaxed_valid + strict_valid
    pass1_invalid = super_relaxed_invalid + sub_relaxed_invalid + relaxed_invalid + strict_invalid
    
    # 汇总所有 Oversell 结果
    total_oversell_symbols = super_relaxed_oversell + sub_relaxed_oversell + relaxed_oversell + strict_oversell
    total_double_symbols = super_relaxed_double + sub_relaxed_double + relaxed_double + strict_double

    final_pe_valid_symbols = pass1_valid
    final_pe_invalid_symbols = pass1_invalid

    # 第二轮筛选 (仅针对 PE_valid 补缺)
    min_size_pe_valid = CONFIG["MIN_PE_VALID_SIZE_FOR_RELAXED_FILTER"]
    
    # 第二轮筛选 (仅针对PE_valid数量不足的情况，且只影响 PE_valid)
    if len(pass1_valid) < min_size_pe_valid:
        rerun_valid, _, rerun_oversell, rerun_double = perform_filter_pass(strict_symbols, CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "第二轮(常规宽松补缺)")
        final_pe_valid_symbols = sorted(list(set(final_pe_valid_symbols) | set(rerun_valid)))
        total_oversell_symbols = sorted(list(set(total_oversell_symbols) | set(rerun_oversell)))
        total_double_symbols = sorted(list(set(total_double_symbols) | set(rerun_double)))

    # 将所有符合资格的 symbol 用于写历史记录
    all_qualified_symbols = final_pe_valid_symbols + final_pe_invalid_symbols + total_oversell_symbols + total_double_symbols
    
    pe_valid_set = set(final_pe_valid_symbols)
    pe_invalid_set = set(final_pe_invalid_symbols)
    oversell_set = set(total_oversell_symbols)
    double_set = set(total_double_symbols)

    blacklist = load_blacklist(BLACKLIST_JSON_FILE)
    try:
        with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f: panel_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): panel_data = {}

    exist_Strategy34 = set(panel_data.get('Strategy34', {}).keys())
    exist_Strategy12 = set(panel_data.get('Strategy12', {}).keys())
    exist_today = set(panel_data.get('Today', {}).keys())
    exist_must = set(panel_data.get('Must', {}).keys())
    
    already_in_panels = exist_Strategy34 | exist_Strategy12 | exist_today | exist_must

    # 过滤黑名单和已存在面板的股票，准备写入列表
    final_pe_valid_to_write = sorted(list(pe_valid_set - blacklist - already_in_panels))
    final_pe_invalid_to_write = sorted(list(pe_invalid_set - blacklist - already_in_panels))
    final_oversell_to_write = sorted(list(oversell_set - blacklist - already_in_panels))
    final_double_to_write = sorted(list(double_set - blacklist - already_in_panels))

    if SYMBOL_TO_TRACE:
        # 追踪日志逻辑更新，包含 Oversell
        combined_sets = [
            (pe_valid_set, "PE_valid"), (pe_invalid_set, "PE_invalid"),
            (oversell_set, "OverSell"), (double_set, "PE_Double")
        ]
        for s_set, name in combined_sets:
            skipped = s_set & (blacklist | already_in_panels)
            if SYMBOL_TO_TRACE in skipped:
                reason = "在 'newlow' 黑名单中" if SYMBOL_TO_TRACE in blacklist else "已存在于 'Strategy34', 'Strategy12', 'Today' 或 'Must' 分组中"
                log_detail(f"\n追踪信息: 目标 symbol '{SYMBOL_TO_TRACE}' ({name}) 虽然通过了筛选，但最终因 ({reason}) 而被跳过，不会写入 panel 文件。")

    hot_tags = set(CONFIG.get("HOT_TAGS", set()))
    def build_symbol_note_map(symbols):
        note_map = {}
        for sym in symbols:
            d = stock_data_cache.get(sym, {})
            cond3_type = d.get('cond3_drop_type')
            tags = set(symbol_to_tags_map.get(sym, []))
            is_hot = bool(tags & hot_tags)
            base = ""
            if cond3_type == '15': base = f"{sym}15"
            elif cond3_type == '7': base = f"{sym}7"
            if base: note_map[sym] = base + ("热" if is_hot else "")
            else: note_map[sym] = f"{sym}热" if is_hot else ""
        return note_map

    pe_valid_notes = build_symbol_note_map(final_pe_valid_to_write)
    pe_invalid_notes = build_symbol_note_map(final_pe_invalid_to_write)
    oversell_notes = build_symbol_note_map(final_oversell_to_write)
    double_notes = build_symbol_note_map(final_double_to_write)

    # 写入 PE_valid
    update_json_panel(final_pe_valid_to_write, PANEL_JSON_FILE, 'PE_valid', symbol_to_note=pe_valid_notes)
    # 同步写入 PE_valid_backup
    update_json_panel(final_pe_valid_to_write, PANEL_JSON_FILE, 'PE_valid_backup', symbol_to_note=pe_valid_notes)
    
    # 写入 PE_invalid
    update_json_panel(final_pe_invalid_to_write, PANEL_JSON_FILE, 'PE_invalid', symbol_to_note=pe_invalid_notes)
    # 同步写入 PE_invalid_backup
    update_json_panel(final_pe_invalid_to_write, PANEL_JSON_FILE, 'PE_invalid_backup', symbol_to_note=pe_invalid_notes)
    
    # 写入 OverSell (条件6)
    update_json_panel(final_oversell_to_write, PANEL_JSON_FILE, 'OverSell', symbol_to_note=oversell_notes)
    # 同步写入 OverSell_backup (新增)
    update_json_panel(final_oversell_to_write, PANEL_JSON_FILE, 'OverSell_backup', symbol_to_note=oversell_notes)

    # 写入 PE_Double (条件1-5且形态良好)
    update_json_panel(final_double_to_write, PANEL_JSON_FILE, 'PE_Double', symbol_to_note=double_notes)
    update_json_panel(final_double_to_write, PANEL_JSON_FILE, 'PE_Double_backup', symbol_to_note=double_notes)

    os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
    try:
        with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
            for sym in sorted(all_qualified_symbols): f.write(sym + '\n')
    except IOError as e:
        log_detail(f"错误: 无法更新备份文件: {e}")

    if all_qualified_symbols:
        update_earning_history_json(EARNING_HISTORY_JSON_FILE, "no_season", sorted(list(set(all_qualified_symbols))), log_detail)
    else:
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
