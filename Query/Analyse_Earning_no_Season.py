import json
import sqlite3
import os
import datetime

SYMBOL_TO_TRACE = ""
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
    "TURNOVER_THRESHOLD": 200_000_000,
    "TURNOVER_THRESHOLD_CHINA": 40_000_000, # 新增：中国概念股的成交额阈值
    
    "RECENT_EARNINGS_COUNT": 2,
    "MARKETCAP_THRESHOLD": 200_000_000_000,      # 2000亿
    "MARKETCAP_THRESHOLD_MEGA": 500_000_000_000, # 5000亿
    
    # 严格筛选标准 (第一轮)
    "PRICE_DROP_PERCENTAGE_LARGE": 0.09, # <2000亿=9%
    "PRICE_DROP_PERCENTAGE_SMALL": 0.06, # 2000亿 ≤ 市值 < 5000亿 = 6%
    "PRICE_DROP_PERCENTAGE_MEGA": 0.05,  # ≥5000亿=5%
    
    # 普通宽松筛选标准
    "RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.07, # <2000亿=7%
    "RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.05, # ≥2000亿=5%
    
    # 新增：次宽松筛选标准
    "SUB_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.06, # <2000亿=6%
    "SUB_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.04, # ≥2000亿=4%
    
    # 最宽松筛选标准
    "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.05, # <2000亿=5%
    "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.03, # ≥2000亿=3%

    # 触发“最宽松”标准的财报收盘价价差百分比 (条件C)
    "ER_PRICE_DIFF_THRESHOLD": 0.40,
    
    # 触发宽松筛选的最小分组数量 (仅对 PE_valid 组生效)
    "MIN_PE_VALID_SIZE_FOR_RELAXED_FILTER": 5,
    
    "MAX_INCREASE_PERCENTAGE_SINCE_LOW": 0.03,
    
    # 条件1c 的专属参数：最新价比最新财报收盘价低至少 X%
    "PRICE_DROP_FOR_COND1C": 0.14,
    # 条件3参数
    "COND3_DROP_THRESHOLDS": [0.07, 0.15],         # 7% 与 15%
    "COND3_LOOKBACK_DAYS": 60,
    
    # 条件4参数: 财报日至今最高价相比最新价的涨幅阈值
    "COND4_RISE_THRESHOLD": 0.07, # 7%
    # ========== 新增：条件5的参数 ==========
    "COND5_ER_TO_HIGH_THRESHOLD": 0.3,  # 财报日到最高价的涨幅阈值 30%
    "COND5_HIGH_TO_LATEST_THRESHOLD": 0.079,  # 最高价到最新价的跌幅阈值 7.9%
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
    today_str = datetime.date.today().isoformat()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log_detail("信息: 历史记录文件不存在或格式错误，将创建新的。")
        data = {}
    if group_name not in data:
        data[group_name] = {}
    existing_symbols = data[group_name].get(today_str, [])
    combined_symbols = set(existing_symbols) | set(symbols_to_add)
    updated_symbols = sorted(list(combined_symbols))
    data[group_name][today_str] = updated_symbols
    num_added = len(updated_symbols) - len(existing_symbols)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_detail(f"成功更新历史记录。日期: {today_str}, 分组: '{group_name}'.")
        log_detail(f"  - 本次新增 {num_added} 个不重复的 symbol。")
        log_detail(f"  - 当天总计 {len(updated_symbols)} 个 symbol。")
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
        all_er_pcts  = [r[1] for r in er_rows]
        data['all_er_pcts'] = all_er_pcts
        data['all_er_dates'] = all_er_dates
        data['latest_er_date_str'] = all_er_dates[-1]
        data['latest_er_pct'] = all_er_pcts[-1]
        if is_tracing: log_detail(f"[{symbol}]   - 最新财报日: {data['latest_er_date_str']}, 最新财报涨跌幅: {data['latest_er_pct']}")
        placeholders = ', '.join(['?'] * len(all_er_dates))
        query = (f'SELECT date, price FROM "{sector_name}" WHERE name = ? AND date IN ({placeholders}) ORDER BY date ASC')
        cursor.execute(query, (symbol, *all_er_dates))
        price_data = cursor.fetchall()
        if is_tracing: log_detail(f"[{symbol}] 步骤2: 查询财报日收盘价。要求 {len(all_er_dates)} 条，实际查到 {len(price_data)} 条。")
        if len(price_data) != len(all_er_dates):
            if is_tracing: log_detail(f"[{symbol}] 失败: 财报日收盘价数据不完整。")
            continue
        data['all_er_prices'] = [p[1] for p in price_data]
        if is_tracing: log_detail(f"[{symbol}]   - 财报日收盘价列表: {data['all_er_prices']}")
        cursor.execute(f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? ORDER BY date DESC LIMIT 1', (symbol,))
        latest_row = cursor.fetchone()
        if not latest_row or latest_row[1] is None or latest_row[2] is None:
            if is_tracing: log_detail(f"[{symbol}] 失败: 未能获取有效的最新交易日数据。查询结果: {latest_row}")
            continue
        data['latest_date_str'], data['latest_price'], data['latest_volume'] = latest_row
        if is_tracing: log_detail(f"[{symbol}] 步骤3: 获取最新交易日数据。日期: {data['latest_date_str']}, 价格: {data['latest_price']}, 成交量: {data['latest_volume']}")
        cursor.execute(f'SELECT price FROM "{sector_name}" WHERE name = ? AND date < ? ORDER BY date DESC LIMIT 10', (symbol, data['latest_date_str']))
        prev_rows = cursor.fetchall()
        prices_last_10 = [r[0] for r in prev_rows]
        data['prev_10_prices'] = prices_last_10
        if is_tracing: log_detail(f"[{symbol}] 步骤3.1: 获取最近10个交易日的收盘价，共 {len(prices_last_10)} 条: {prices_last_10}")
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
        cursor.execute(f'SELECT price FROM "{sector_name}" WHERE name = ? AND date >= ? ORDER BY date ASC LIMIT 6', (symbol, data['latest_er_date_str']))
        er_6_day_prices_rows = cursor.fetchall()
        er_6_day_prices = [row[0] for row in er_6_day_prices_rows if row[0] is not None]
        data['er_6_day_window_low'] = min(er_6_day_prices) if er_6_day_prices else None
        if is_tracing: 
            log_detail(f"[{symbol}] 步骤3.5: 为条件5获取财报窗口期(6天)最低价。价格: {er_6_day_prices}, 最低价: {data['er_6_day_window_low']}")
        # ========== 代码修改结束 2/3 ==========

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
    if is_tracing: log_detail(f"  - [特殊条件检查(前提条件)] for {symbol}:")
    er_pcts = data.get('all_er_pcts', [])
    all_er_prices = data.get('all_er_prices', [])
    recent_earnings_count = config["RECENT_EARNINGS_COUNT"]
    if not er_pcts or not all_er_prices:
        if is_tracing: log_detail(f"    - 失败: 财报数据不足。-> 返回 0 (严格)")
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
    cond_b = price_diff_pct >= 0.04
    if is_tracing: log_detail(f"  - b) 最近两次财报价差 >= 4%: {price_diff_pct:.2%} >= 4.00% -> {cond_b}")
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

# ========== 代码修改点 1/3: 重构 evaluate_stock_conditions 函数 ==========
# 1. 重命名为 check_entry_conditions，使其只负责检查入口条件
# 2. 修改返回值为元组 (passed_any, passed_cond5)，以便后续逻辑判断
# 3. 移除所有通用过滤逻辑（价格回撤、10日最低价、成交额）
def check_entry_conditions(data, symbol_to_trace, log_detail):
    """
    此函数现在只检查入口条件 (条件1 OR 条件2 OR 条件3 OR 条件4 OR 条件5)。
    返回:
        (bool, bool): 一个元组 (passed_any_condition, passed_condition_5)
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: 
        log_detail(f"\n--- [{symbol}] 入口条件评估 ---")

    # --- 数据预检 ---
    er_pcts = data.get('all_er_pcts', [])
    if not er_pcts or len(data.get('all_er_prices', [])) < CONFIG["RECENT_EARNINGS_COUNT"]:
        if is_tracing: log_detail("  - 预检失败: 缺少财报数据，无法评估入口条件。")
        return (False, False)
        
    # --- 评估各个入口条件 ---

    # 入口条件A: 条件1 (三选一)
    prices_to_check = data['all_er_prices'][-CONFIG["RECENT_EARNINGS_COUNT"]:]
    latest_er_pct = er_pcts[-1]
    latest_er_price = prices_to_check[-1]
    avg_recent_price = sum(prices_to_check) / len(prices_to_check)
    drop_pct_for_cond1c = CONFIG["PRICE_DROP_FOR_COND1C"]
    threshold_price1c = latest_er_price * (1 - drop_pct_for_cond1c)
    
    cond1_a = latest_er_pct > 0
    previous_er_price = prices_to_check[-2]
    price_diff_pct_cond1b = ((latest_er_price - previous_er_price) / previous_er_price) if previous_er_price > 0 else 0
    cond1_b = (latest_er_price > avg_recent_price) and (price_diff_pct_cond1b >= 0.04)
    cond1_c = data['latest_price'] <= threshold_price1c
    passed_original_cond1 = cond1_a or cond1_b or cond1_c

    if is_tracing:
        log_detail("  - [入口条件A] 条件1评估:")
        log_detail(f"    - a) 最新财报涨跌幅 > 0 -> {cond1_a}")
        log_detail(f"    - b) 最新财报收盘价 > 平均价 且 最近两次财报价差 > 4% -> {cond1_b}")
        log_detail(f"    - c) 最新价比最新财报收盘价低至少 {drop_pct_for_cond1c*100}% -> {cond1_c}")
        log_detail(f"    - 结果: {passed_original_cond1}")

    # 入口条件：条件2, 3, 4, 5
    passed_new_cond2 = check_condition_2(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond3 = check_new_condition_3(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond4 = check_new_condition_4(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond5 = check_new_condition_5(data, CONFIG, log_detail, symbol_to_trace)

    # --- 汇总结果 ---
    passed_any = passed_original_cond1 or passed_new_cond2 or passed_new_cond3 or passed_new_cond4 or passed_new_cond5
    
    if is_tracing:
        if passed_any:
            reasons = []
            if passed_original_cond1: reasons.append("条件1")
            if passed_new_cond2: reasons.append("条件2")
            if passed_new_cond3: reasons.append("条件3")
            if passed_new_cond4: reasons.append("条件4")
            if passed_new_cond5: reasons.append("条件5")
            log_detail(f"\n--- [{symbol}] 入口条件通过 (原因: {'、'.join(reasons)})。")
        else:
            log_detail(f"\n--- [{symbol}] 入口条件失败。五个入口条件均未满足。")

    return (passed_any, passed_new_cond5)

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
        er_window_high_price = data.get('er_window_high_price')

        if er_window_high_price is None or er_window_high_price <= 0:
            if is_tracing: log_detail(f"  - 最终裁定: 失败 (通用过滤1: 无法获取有效的财报窗口期最高价: {er_window_high_price})。")
            return False

        is_strict_mode = (
            drop_pct_large == CONFIG["PRICE_DROP_PERCENTAGE_LARGE"] and
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

        threshold_price_drawdown = er_window_high_price * (1 - drop_pct)
        cond_drawdown_ok = data['latest_price'] <= threshold_price_drawdown
        
        if is_tracing:
            log_detail("  - [通用过滤1] 价格回撤:")
            log_detail(f"    - 市值: {marketcap} -> 使用下跌百分比: {drop_pct*100:.1f}%")
            log_detail(f"    - 判断: 最新价({data['latest_price']:.2f}) <= 财报窗口期最高价({er_window_high_price:.2f}) * (1 - {drop_pct:.2f}) = 阈值价({threshold_price_drawdown:.2f}) -> {cond_drawdown_ok}")
        
        if not cond_drawdown_ok:
            if is_tracing: log_detail("  - 最终裁定: 失败 (通用过滤1: 价格回撤不满足)。")
            return False
    else:
        if is_tracing: log_detail("  - [通用过滤1] 价格回撤: 已跳过 (条件5模式)。")

    # 2. 相对10日最低价条件
    prev_prices = data.get('prev_10_prices', [])
    if len(prev_prices) < 10:
        if is_tracing: log_detail(f"  - 最终裁定: 失败 (通用过滤2: 可用历史交易日不足10日，只有{len(prev_prices)}日数据)。")
        return False
    min_prev = min(prev_prices)
    threshold_price_10day = min_prev * (1 + CONFIG["MAX_INCREASE_PERCENTAGE_SINCE_LOW"])
    cond_10day_ok = data['latest_price'] <= threshold_price_10day
    if is_tracing:
        log_detail(f"  - [通用过滤2] 相对10日最低价:")
        log_detail(f"    - 判断: 最新价 {data['latest_price']:.2f} <= 最低价*1.03 ({threshold_price_10day:.2f}) -> {cond_10day_ok}")
    if not cond_10day_ok:
        if is_tracing: log_detail("  - 最终裁定: 失败 (通用过滤2: 相对10日最低价条件不满足)。")
        return False
    
    # 3. 成交额条件
    turnover = data['latest_price'] * data['latest_volume']
    tags = data.get('tags', set())
    is_china_stock = any("中国" in tag for tag in tags)
    current_threshold = CONFIG["TURNOVER_THRESHOLD_CHINA"] if is_china_stock else CONFIG["TURNOVER_THRESHOLD"]
    cond_turnover_ok = turnover > current_threshold

    if is_tracing:
        log_detail("  - [通用过滤3] 成交额:")
        log_detail(f"    - {'使用中国概念股阈值' if is_china_stock else '使用通用阈值'}: {current_threshold:,}")
        log_detail(f"    - 判断: 最新成交额({turnover:,.0f}) >= 阈值({current_threshold:,}) -> {cond_turnover_ok}")

    if not cond_turnover_ok:
        if is_tracing: log_detail("  - 最终裁定: 失败 (通用过滤3: 成交额不满足)。")
        return False
        
    if is_tracing: log_detail("  - 最终裁定: 成功! 所有通用过滤条件均满足。")
    return True

def apply_post_filters(symbols, stock_data_cache, symbol_to_trace, log_detail):
    pe_valid_symbols = []
    pe_invalid_symbols = []
    for symbol in symbols:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n--- [{symbol}] 后置过滤器评估 ---")
        data = stock_data_cache[symbol]
        if data['latest_date_str'] == data['latest_er_date_str']:
            if is_tracing: log_detail(f"  - 过滤 (日期相同): 最新交易日({data['latest_date_str']}) 与 最新财报日({data['latest_er_date_str']}) 相同。")
            continue
        elif is_tracing: log_detail(f"  - 通过 (日期不同)。")
        pe = data['pe_ratio']
        is_pe_valid = pe is not None and str(pe).strip().lower() not in ("--", "null", "")
        if is_pe_valid:
            if is_tracing: log_detail(f"  - 分组 (PE有效): PE值为 '{pe}'。加入 PE_valid 组。")
            pe_valid_symbols.append(symbol)
        else:
            if is_tracing: log_detail(f"  - 分组 (PE无效): PE值为 '{pe}'。加入 PE_invalid 组。")
            pe_invalid_symbols.append(symbol)
    return pe_valid_symbols, pe_invalid_symbols

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
    
    # ========== 代码修改点 3/3: 修改 perform_filter_pass 函数的内部逻辑 ==========
    def perform_filter_pass(symbols_to_check, drop_large, drop_small, pass_name):
        preliminary_results = []
        for symbol in symbols_to_check:
            data = stock_data_cache.get(symbol)
            if not (data and data['is_valid']):
                continue
            
            data['symbol'] = symbol
            
            # 步骤A: 检查入口条件
            passed_any, passed_cond5 = check_entry_conditions(data, SYMBOL_TO_TRACE, log_detail)
            
            # 如果任何入口条件都没通过，则跳过
            if not passed_any:
                continue
                
            # 步骤B: 应用通用过滤器。
            # 关键逻辑：如果通过了条件5，则将 skip_drawdown 设为 True
            if apply_common_filters(data, SYMBOL_TO_TRACE, log_detail, drop_large, drop_small, skip_drawdown=passed_cond5):
                preliminary_results.append(symbol)

        # 步骤 C: 应用后置过滤器 (PE 分组)
        pe_valid, pe_invalid = apply_post_filters(preliminary_results, stock_data_cache, SYMBOL_TO_TRACE, log_detail)

        # 步骤 D: 基于Tag的过滤
        tag_blacklist = CONFIG["BLACKLIST_TAGS"]
        final_pe_valid = [s for s in pe_valid if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]
        final_pe_invalid = [s for s in pe_invalid if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]

        return final_pe_valid, final_pe_invalid

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

    super_relaxed_valid, super_relaxed_invalid = perform_filter_pass(super_relaxed_symbols, CONFIG["SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "第一轮筛选 (最宽松组)")
    sub_relaxed_valid, sub_relaxed_invalid = perform_filter_pass(sub_relaxed_symbols, CONFIG["SUB_RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["SUB_RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "第一轮筛选 (次宽松组)")
    relaxed_valid, relaxed_invalid = perform_filter_pass(relaxed_symbols, CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "第一轮筛选 (普通宽松组)")
    strict_valid, strict_invalid = perform_filter_pass(strict_symbols, CONFIG["PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["PRICE_DROP_PERCENTAGE_SMALL"], "第一轮筛选 (严格组)")

    pass1_valid = super_relaxed_valid + sub_relaxed_valid + relaxed_valid + strict_valid
    pass1_invalid = super_relaxed_invalid + sub_relaxed_invalid + relaxed_invalid + strict_invalid
    
    final_pe_valid_symbols = pass1_valid
    final_pe_invalid_symbols = pass1_invalid
    min_size_pe_valid = CONFIG["MIN_PE_VALID_SIZE_FOR_RELAXED_FILTER"]
    if len(pass1_valid) < min_size_pe_valid:
        rerun_valid, _ = perform_filter_pass(strict_symbols, CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "第二轮筛选 (常规宽松, for PE_valid)")
        final_pe_valid_symbols = sorted(list(set(super_relaxed_valid) | set(sub_relaxed_valid) | set(relaxed_valid) | set(rerun_valid)))

    all_qualified_symbols = final_pe_valid_symbols + final_pe_invalid_symbols
    pe_valid_set = set(final_pe_valid_symbols)
    pe_invalid_set = set(final_pe_invalid_symbols)
    blacklist = load_blacklist(BLACKLIST_JSON_FILE)
    try:
        with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f: panel_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): panel_data = {}
    exist_Strategy34 = set(panel_data.get('Strategy34', {}).keys())
    exist_Strategy12 = set(panel_data.get('Strategy12', {}).keys())
    exist_today = set(panel_data.get('Today', {}).keys())
    exist_must = set(panel_data.get('Must', {}).keys())
    already_in_panels = exist_Strategy34 | exist_Strategy12 | exist_today | exist_must
    final_pe_valid_to_write = sorted(list(pe_valid_set - blacklist - already_in_panels))
    final_pe_invalid_to_write = sorted(list(pe_invalid_set - blacklist - already_in_panels))

    if SYMBOL_TO_TRACE:
        skipped_valid = pe_valid_set & (blacklist | already_in_panels)
        if SYMBOL_TO_TRACE in skipped_valid:
            reason = "在 'newlow' 黑名单中" if SYMBOL_TO_TRACE in blacklist else "已存在于 'Strategy34', 'Strategy12', 'Today' 或 'Must' 分组中"
            log_detail(f"\n追踪信息: 目标 symbol '{SYMBOL_TO_TRACE}' 虽然通过了筛选，但最终因 ({reason}) 而被跳过，不会写入 panel 文件。")
        skipped_invalid = pe_invalid_set & (blacklist | already_in_panels)
        if SYMBOL_TO_TRACE in skipped_invalid:
            reason = "在 'newlow' 黑名单中" if SYMBOL_TO_TRACE in blacklist else "已存在于 'Strategy34', 'Strategy12', 'Today' 或 'Must' 分组中"
            log_detail(f"\n追踪信息: 目标 symbol '{SYMBOL_TO_TRACE}' 虽然通过了筛选，但最终因 ({reason}) 而被跳过，不会写入 panel 文件。")

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
    update_json_panel(final_pe_valid_to_write, PANEL_JSON_FILE, 'PE_valid', symbol_to_note=pe_valid_notes)
    update_json_panel(final_pe_invalid_to_write, PANEL_JSON_FILE, 'PE_invalid', symbol_to_note=pe_invalid_notes)
    os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
    try:
        with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
            for sym in sorted(all_qualified_symbols): f.write(sym + '\n')
    except IOError as e:
        log_detail(f"错误: 无法更新备份文件: {e}")
    if all_qualified_symbols:
        update_earning_history_json(EARNING_HISTORY_JSON_FILE, "no_season", all_qualified_symbols, log_detail)
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