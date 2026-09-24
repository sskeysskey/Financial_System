import json
import sqlite3
import os
import datetime

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 1. 配置文件和路径 ---
BASE_PATH = USER_HOME

SYMBOL_TO_TRACE = ""
TARGET_DATE = ""

# SYMBOL_TO_TRACE = "VVV"
# TARGET_DATE = "2026-09-21"

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
CONFIG = {
    "TARGET_SECTORS": {
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    },
    "TURNOVER_THRESHOLD": 80_000_000,
    "TURNOVER_THRESHOLD_CHINA": 100_000_000,

    # ============================================================
    # ========== 【新增】成交额三级判定 (满足任一级即通过) ==========
    # 级别① 单日：今日成交额 > 阈值 (原逻辑)
    # 级别② ADV ：最近 N 个交易日(含今日)平均成交额 >= 阈值，且今日成交额 >= 阈值 × MIN_TODAY_RATIO
    # 级别③ 链条：前一交易日已在 CHAIN_GROUPS 中 + 今日收盘更低 + 今日成交额 >= 阈值 × CHAIN_RATIO
    # ============================================================
    "TURNOVER_ENABLE_ADV": True,
    "TURNOVER_ADV_DAYS": 5,
    "TURNOVER_ADV_MIN_TODAY_RATIO": 0.5,
    "TURNOVER_ENABLE_CHAIN": True,
    "TURNOVER_CHAIN_RATIO": 0.6,
    "TURNOVER_CHAIN_GROUPS": ["PE_Deeper", "PE_Deep", "PE_low", "PE_lower", "PE_lowest"],
    "TURNOVER_CHAIN_GAP_MAX_DAYS": 7,   # 前一交易日与今日的最大自然日跨度(防停牌后误继承)

    "RECENT_EARNINGS_COUNT": 2,
    "MARKETCAP_THRESHOLD": 200_000_000_000,
    "MARKETCAP_THRESHOLD_MEGA": 500_000_000_000,
    "MARKETCAP_THRESHOLD_GIANT": 1_000_000_000_000,
    "COND5_WINDOW_DAYS": 6,

    "PRICE_DROP_PERCENTAGE_LARGE": 0.107,
    "PRICE_DROP_PERCENTAGE_SMALL": 0.09,
    "PRICE_DROP_PERCENTAGE_MEGA": 0.07,
    "PRICE_DROP_PERCENTAGE_GIANT": 0.05,

    "RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.1,
    "RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.08,
    "RELAXED_PRICE_DROP_PERCENTAGE_MINI": 0.05,

    "HOT_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.075,
    "HOT_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.067,

    "SUB_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.09,
    "SUB_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.07,
    "SUB_RELAXED_PRICE_DROP_PERCENTAGE_MINI": 0.05,

    "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.07,
    "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.05,

    "ER_PRICE_DIFF_THRESHOLD": 0.06,
    "MIN_PE_VALID_SIZE_FOR_RELAXED_FILTER": 5,
    "MAX_INCREASE_PERCENTAGE_SINCE_LOW": 0.06,
    "LOOKBACK_WINDOW_DAYS": 5,
    "MAX_INCREASE_PERCENTAGE_SINCE_LOW_HOT": 0.12,
    "PRICE_DROP_FOR_COND1C": 0.17,

    "COND3_DROP_THRESHOLDS": [0.09, 0.15],
    "COND3_LOOKBACK_DAYS": 60,

    "MARKETCAP_VAL_1": 220_000_000_000,
    "MARKETCAP_VAL_2": 500_000_000_000,
    "MARKETCAP_VAL_3": 800_000_000_000,
    "MARKETCAP_VAL_4": 1_400_000_000_000,

    "COND4_THRESH_1": 0.062,
    "COND4_THRESH_2": 0.056,
    "COND4_THRESH_3": 0.051,
    "COND4_THRESH_4": 0.047,
    "COND4_THRESH_5": 0.045,

    "COND5_ER_TO_HIGH_THRESHOLD": 0.3,
    "COND5_HIGH_TO_LATEST_THRESHOLD": 0.09,

    "PE_DEEP_DROP_THRESHOLD": 0.151,
    "PE_DEEP_MAX_DROP_THRESHOLD": 0.16,
    "PE_DEEP_HIGH_SINCE_ER_THRESHOLD": 0.18,
    "PE_DEEPER_DROP_THRESHOLD": 0.225,

    "COND6_ER_DROP_A_THRESHOLD": 0.25,
    "COND6_LOW_DROP_B_LARGE": 0.09,
    "COND6_LOW_DROP_B_SMALL": 0.12,
    "COND6_W_BOTTOM_MIN_PEAK_RISE": 0.015,
    "COND6_W_BOTTOM_HIGHER_LOW_DAYS": 18,
    "COND6_W_BOTTOM_PRICE_TOLERANCE": 0.0492,
    "COND6_W_BOTTOM_MIN_DAYS_GAP": 3,

    "PE_W_LOOKBACK_DAYS": 21,
    "PE_W_MAX_RISE_FROM_LOW": 0.07,

    "COND8_EARNINGS_LOOKBACK_COUNT": 4,
    "COND8_MIN_DECLINE_COUNT": 3,
    "COND8_REQUIRE_LATEST_IN_SEQUENCE": False,
    "COND8_MARKETCAP_THRESHOLD": 500_000_000_000,
    "COND8_LOW_DROP_BIG": 0.06,
    "COND8_LOW_DROP_SMALL": 0.108,
    "COND8_LOWER_DROP_BIG": 0.11,
    "COND8_LOWER_DROP_SMALL": 0.15,
    "COND8_LOWEST_DROP_BIG": 0.15,
    "COND8_LOWEST_DROP_SMALL": 0.21,
    "COND8_APPLY_TURNOVER_FILTER": True,
    "COND8_EXCLUDE_EXISTING_RESULTS": False,
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
        for item in data.get('stocks', []):
            symbol = item.get('symbol')
            tags = item.get('tag', [])
            if symbol:
                symbol_tag_map[symbol] = tags
        return symbol_tag_map
    except Exception:
        return {}

# ========== 【新增】只读加载 Earning_History，用于成交额链条顺延判定 ==========
def load_earning_history_readonly(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
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

    if not symbols_to_add:
        log_detail(f" - 列表为空，跳过写入历史记录。")
        return

    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    yesterday_str = yesterday.isoformat()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log_detail("信息: 历史记录文件不存在或格式错误，将创建新的。")
        data = {}

    if group_name not in data:
        data[group_name] = {}

    existing_symbols = data[group_name].get(yesterday_str, [])
    combined_symbols = set(existing_symbols) | set(symbols_to_add)
    updated_symbols = sorted(list(combined_symbols))

    if not updated_symbols:
        return

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
    lookback_days = max(
        CONFIG.get("LOOKBACK_WINDOW_DAYS", 10),
        CONFIG.get("PE_W_LOOKBACK_DAYS", 21)
    )
    adv_days = max(1, int(CONFIG.get("TURNOVER_ADV_DAYS", 5)))

    for i, symbol in enumerate(symbols):
        is_tracing = (symbol == symbol_to_trace)
        data = {'is_valid': False}
        sector_name = symbol_to_sector_map.get(symbol)

        if not sector_name:
            if is_tracing: log_detail(f"[{symbol}] 失败: 在板块映射中未找到该symbol。")
            continue

        if target_date:
            cursor.execute("SELECT date, price FROM Earning WHERE name = ? AND date <= ? ORDER BY date ASC", (symbol, target_date))
        else:
            cursor.execute("SELECT date, price FROM Earning WHERE name = ? ORDER BY date ASC", (symbol,))

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

        if target_date:
            query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 1'
            params = (symbol, target_date)
            if is_tracing: log_detail(f"[{symbol}] !!! 回测模式启动 !!! 正在查找 {target_date} 或之前的最新数据...")
        else:
            query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? ORDER BY date DESC LIMIT 1'
            params = (symbol,)

        cursor.execute(query, params)
        latest_row = cursor.fetchone()

        if not latest_row or latest_row[1] is None or latest_row[2] is None:
            if is_tracing: log_detail(f"[{symbol}] 失败: 未能获取有效的交易日数据(可能该日期停牌或无数据)。")
            continue

        data['latest_date_str'], data['latest_price'], data['latest_volume'] = latest_row

        if is_tracing: log_detail(f"[{symbol}] 步骤3: 获取基准交易日数据。日期: {data['latest_date_str']}, 价格: {data['latest_price']}, 成交量: {data['latest_volume']}")

        cursor.execute(f'SELECT date, price FROM "{sector_name}" WHERE name = ? AND date < ? ORDER BY date DESC LIMIT {lookback_days}', (symbol, data['latest_date_str']))
        prev_rows = cursor.fetchall()
        data['prev_window_dates'] = [r[0] for r in prev_rows]
        data['prev_window_prices'] = [r[1] for r in prev_rows]

        if is_tracing:
            log_detail(f"[{symbol}] 步骤3.1: 获取最近 {lookback_days} 个交易日数据。日期: {data['prev_window_dates']}, 价格: {data['prev_window_prices']}")

        # ========== 【新增】步骤3.1b: 最近 N 个交易日(含今日)成交额，用于 ADV 判定 ==========
        cursor.execute(
            f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT ?',
            (symbol, data['latest_date_str'], adv_days)
        )
        t_rows = [r for r in cursor.fetchall() if r[1] is not None and r[2] is not None]
        data['recent_turnover_dates'] = [r[0] for r in t_rows]
        data['recent_turnovers'] = [r[1] * r[2] for r in t_rows]
        if is_tracing:
            pairs = ", ".join(f"{d}:{t/1e8:.3f}亿" for d, t in zip(data['recent_turnover_dates'], data['recent_turnovers']))
            log_detail(f"[{symbol}] 步骤3.1b: 最近 {adv_days} 日成交额: {pairs}")

        latest_er_date = data['latest_er_date_str']
        latest_er_price = data['all_er_prices'][-1]

        if target_date:
            cursor.execute(f'SELECT price FROM "{sector_name}" WHERE name = ? AND date > ? AND date <= ? ORDER BY date ASC LIMIT 3', (symbol, latest_er_date, target_date))
        else:
            cursor.execute(f'SELECT price FROM "{sector_name}" WHERE name = ? AND date > ? ORDER BY date ASC LIMIT 3', (symbol, latest_er_date))

        next_days_prices = [row[0] for row in cursor.fetchall()]
        data['latest_er_next_day_price'] = next_days_prices[0] if next_days_prices else None

        er_window_prices = [latest_er_price]
        er_window_prices.extend(next_days_prices)
        data['er_window_high_price'] = max(er_window_prices) if er_window_prices else None

        if is_tracing: log_detail(f"[{symbol}] 步骤3.2: 查找财报窗口期最高价。窗口期价格: {er_window_prices}, 最高价: {data['er_window_high_price']}")

        if target_date:
            cursor.execute(f'SELECT MAX(price) FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?', (symbol, data['latest_er_date_str'], target_date))
        else:
            cursor.execute(f'SELECT MAX(price) FROM "{sector_name}" WHERE name = ? AND date >= ?', (symbol, data['latest_er_date_str']))
        high_since_er_row = cursor.fetchone()
        data['high_since_er'] = high_since_er_row[0] if high_since_er_row else None

        if is_tracing: log_detail(f"[{symbol}] 步骤3.3: 获取自最新财报日({data['latest_er_date_str']})以来的最高价: {data['high_since_er']}")

        cursor.execute(f'SELECT MAX(price) FROM "{sector_name}" WHERE name = ? AND date > ? AND date <= ?', (symbol, latest_er_date, data['latest_date_str']))
        row_hb = cursor.fetchone()
        data['high_between_er_and_latest'] = row_hb[0] if row_hb else None

        if is_tracing: log_detail(f"[{symbol}] 步骤3.4: 获取从财报日({latest_er_date})到最新日({data['latest_date_str']})之间的最高价: {data['high_between_er_and_latest']}")

        limit_days = CONFIG.get("COND5_WINDOW_DAYS", 6)
        cursor.execute(f'SELECT price FROM "{sector_name}" WHERE name = ? AND date >= ? ORDER BY date ASC LIMIT {limit_days}', (symbol, data['latest_er_date_str']))
        er_6_day_prices = [row[0] for row in cursor.fetchall() if row[0] is not None]
        data['er_6_day_window_low'] = min(er_6_day_prices) if er_6_day_prices else None
        if is_tracing:
            log_detail(f"[{symbol}] 步骤3.5: 为条件5获取财报窗口期(6天)最低价。价格: {er_6_day_prices}, 最低价: {data['er_6_day_window_low']}")

        if target_date:
            cursor.execute(f'SELECT date, price FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ? ORDER BY date ASC', (symbol, data['latest_er_date_str'], target_date))
        else:
            cursor.execute(f'SELECT date, price FROM "{sector_name}" WHERE name = ? AND date >= ? ORDER BY date ASC', (symbol, data['latest_er_date_str']))
        since_er_rows = [r for r in cursor.fetchall() if r[0] is not None and r[1] is not None]
        data['prices_since_er_series'] = [r[1] for r in since_er_rows]
        data['dates_since_er_series'] = [r[0] for r in since_er_rows]

        if is_tracing:
            log_detail(f"[{symbol}] 步骤3.6: 获取财报日至今的价格序列，共 {len(data['prices_since_er_series'])} 天。")

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
            lookback_days_cond3 = CONFIG.get("COND3_LOOKBACK_DAYS", 60)
            last_N_high = get_high_price_last_n_days(cursor, sector_name, symbol, data['latest_date_str'], lookback_days_cond3)
            data['last_N_high'] = last_N_high

            if last_N_high and last_N_high > 0:
                drop_pct_vs_N_high = (last_N_high - data['latest_price']) / last_N_high
                thresholds = sorted(CONFIG["COND3_DROP_THRESHOLDS"])
                low_t, high_t = thresholds[0], thresholds[1]
                low_l, high_l = str(int(low_t * 100)), str(int(high_t * 100))
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
            prices = [r[0] for r in cursor.fetchall() if r[0] is not None]
            return max(prices) if prices else None
    else:
        def to_str(d): return d.strftime("%Y-%m-%d")

    start_str = to_str(dt - timedelta(days=lookback_days))
    end_str = to_str(dt)
    cursor.execute(f'SELECT MAX(price) FROM "{sector_name}" WHERE name = ? AND date BETWEEN ? AND ?', (symbol, start_str, end_str))
    row = cursor.fetchone()
    return row[0] if row and row[0] is not None else None

# ==============================================================================
# ========== 【新增】成交额三级判定 (单日 / ADV / 链条顺延) ==========
# ==============================================================================
def _find_turnover_chain_source(data, config, symbol):
    """
    判断前一交易日该 symbol 是否已在 TURNOVER_CHAIN_GROUPS 中。
    由于 Earning_History 的日期 key 是"运行日的昨天"，不一定等于真实交易日，
    这里采用区间匹配：prev_trade_date <= key < latest_date。
    返回 (group, date_key) 或 (None, None)
    """
    history = config.get("_EARNING_HISTORY") or {}
    groups = config.get("TURNOVER_CHAIN_GROUPS", [])
    prev_dates = data.get('prev_window_dates', [])
    latest_date = data.get('latest_date_str')
    if not history or not groups or not prev_dates or not latest_date:
        return None, None

    prev_date = prev_dates[0]
    try:
        gap = (datetime.datetime.strptime(latest_date, "%Y-%m-%d") -
               datetime.datetime.strptime(prev_date, "%Y-%m-%d")).days
        if gap > config.get("TURNOVER_CHAIN_GAP_MAX_DAYS", 7):
            return None, None
    except Exception:
        return None, None

    best = (None, None)
    for g in groups:
        g_hist = history.get(g) or {}
        for d_key, syms in g_hist.items():
            if not isinstance(d_key, str) or not isinstance(syms, list):
                continue
            if prev_date <= d_key < latest_date and symbol in syms:
                if best[1] is None or d_key > best[1]:
                    best = (g, d_key)
    return best


def evaluate_turnover(data, config, log_detail, symbol_to_trace, prefix="通用过滤3"):
    """
    成交额三级判定，满足任一级即通过。返回 (是否通过, 通过级别描述)
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)

    latest_price = data.get('latest_price')
    latest_volume = data.get('latest_volume')
    if latest_price is None or latest_volume is None:
        if is_tracing: log_detail(f"  - [{prefix}·成交额] 失败: 缺少价格或成交量数据。")
        return False, None

    tags = data.get('tags', set())
    is_china_stock = any("中国" in tag for tag in tags)
    threshold = config["TURNOVER_THRESHOLD_CHINA"] if is_china_stock else config["TURNOVER_THRESHOLD"]
    today_turnover = latest_price * latest_volume

    if is_tracing:
        log_detail(f"  - [{prefix}·成交额] {'中国概念股阈值' if is_china_stock else '通用阈值'}: {threshold:,}")

    # ① 单日
    ok1 = today_turnover > threshold
    if is_tracing:
        log_detail(f"    ① 单日: {today_turnover:,.0f} > {threshold:,} -> {ok1}")
    if ok1:
        return True, "单日"

    # ② N 日 ADV
    if config.get("TURNOVER_ENABLE_ADV", True):
        n = int(config.get("TURNOVER_ADV_DAYS", 5))
        turns = data.get('recent_turnovers', [])
        min_today_ratio = config.get("TURNOVER_ADV_MIN_TODAY_RATIO", 0.5)
        if len(turns) >= n:
            adv = sum(turns[:n]) / n
            ok_adv = adv >= threshold
            ok_floor = today_turnover >= threshold * min_today_ratio
            ok2 = ok_adv and ok_floor
            if is_tracing:
                log_detail(f"    ② {n}日ADV: {adv:,.0f} >= {threshold:,} -> {ok_adv}；"
                           f"今日下限 {today_turnover:,.0f} >= {threshold*min_today_ratio:,.0f} -> {ok_floor} => {ok2}")
            if ok2:
                return True, f"{n}日ADV"
        elif is_tracing:
            log_detail(f"    ② {n}日ADV: 可用交易日仅 {len(turns)} 天，跳过")

    # ③ 链条顺延
    if config.get("TURNOVER_ENABLE_CHAIN", True):
        prev_prices = data.get('prev_window_prices', [])
        chain_ratio = config.get("TURNOVER_CHAIN_RATIO", 0.6)
        if prev_prices and prev_prices[0] is not None:
            price_down = latest_price < prev_prices[0]
            src_group, src_date = _find_turnover_chain_source(data, config, symbol)
            ok_floor = today_turnover >= threshold * chain_ratio
            ok3 = bool(src_group) and price_down and ok_floor
            if is_tracing:
                log_detail(f"    ③ 链条顺延: 前一交易日所在分组={src_group or '无'}({src_date or '-'})；"
                           f"收盘走低 {latest_price:.2f} < {prev_prices[0]:.2f} -> {price_down}；"
                           f"今日 {today_turnover:,.0f} >= {threshold*chain_ratio:,.0f} -> {ok_floor} => {ok3}")
            if ok3:
                return True, f"链条顺延({src_group}@{src_date})"
        elif is_tracing:
            log_detail(f"    ③ 链条顺延: 缺少前一交易日价格，跳过")

    return False, None

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
    if (cond_a and cond_b) or (cond_c and cond_d):
        if is_tracing: log_detail(f"    - 最终决策: 命中 ((A & B) or (C & D)) -> 返回 1 (普通宽松)")
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
    er_threshold = config.get("ER_PRICE_DIFF_THRESHOLD", 0.06)
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

    drop_pct = (last_N_high - latest_price) / last_N_high
    thresholds = sorted(config["COND3_DROP_THRESHOLDS"])
    low_thresh, high_thresh = thresholds[0], thresholds[1]
    low_label, high_label = str(int(low_thresh * 100)), str(int(high_thresh * 100))

    hit_high = drop_pct >= high_thresh
    hit_low = drop_pct >= low_thresh

    if is_tracing:
        log_detail(f" - 最近{lookback_days}天最高价: {last_N_high:.2f}, 最新价: {latest_price:.2f}, 跌幅: {drop_pct:.2%}")
        log_detail(f"  - 命中{high_label}%: {hit_high}, 命中{low_label}%: {hit_low}, cond3_drop_type缓存: {cond3_type}")

    if cond3_type in (low_label, high_label):
        if is_tracing: log_detail(f"  - 结果: True (命中条件3, 类型: {cond3_type})")
        return True
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
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件4评估 (多级动态市值阈值) ---")

    high_since_er = data.get('high_since_er')
    latest_price = data.get('latest_price')
    marketcap = data.get('marketcap')

    if high_since_er is None or latest_price is None or latest_price <= 0:
        if is_tracing: log_detail(f"  - 结果: False (数据不足: high_since_er={high_since_er}, latest_price={latest_price})")
        return False

    v1, v2, v3, v4 = config["MARKETCAP_VAL_1"], config["MARKETCAP_VAL_2"], config["MARKETCAP_VAL_3"], config["MARKETCAP_VAL_4"]

    if marketcap is None:
        rise_threshold = config["COND4_THRESH_1"]
        cap_type = f"未知市值 (默认使用 <= {v1/1e8:.0f}亿 档位)"
    elif marketcap <= v1:
        rise_threshold = config["COND4_THRESH_1"]
        cap_type = f"普通市值 (<= {v1/1e8:.0f}亿)"
    elif marketcap <= v2:
        rise_threshold = config["COND4_THRESH_2"]
        cap_type = f"大市值 ({v1/1e8:.0f}亿 - {v2/1e8:.0f}亿)"
    elif marketcap <= v3:
        rise_threshold = config["COND4_THRESH_3"]
        cap_type = f"超大市值 ({v2/1e8:.0f}亿 - {v3/1e8:.0f}亿)"
    elif marketcap <= v4:
        rise_threshold = config["COND4_THRESH_4"]
        cap_type = f"巨型市值 ({v3/1e8:.0f}亿 - {v4/1e8:.0f}亿)"
    else:
        rise_threshold = config["COND4_THRESH_5"]
        cap_type = f"顶级市值 (> {v4/1e8:.0f}亿)"

    threshold_price = latest_price * (1 + rise_threshold)
    passed = high_since_er >= threshold_price

    if is_tracing:
        rise_pct = (high_since_er - latest_price) / latest_price
        log_detail(f"  - 当前市值: {marketcap:,.0f}" if marketcap else "  - 当前市值: 未知")
        log_detail(f"  - 判定区间: {cap_type}")
        log_detail(f"  - 财报日至今最高价: {high_since_er:.2f}, 最新价: {latest_price:.2f}")
        log_detail(f"  - 要求的反弹空间(Upside): {rise_threshold:.2%}")
        log_detail(f"  - 实际的反弹空间(Upside): {rise_pct:.2%}")
        log_detail(f"  - 结果: {passed} (最高价 {high_since_er:.2f} >= 阈值价 {threshold_price:.2f})")

    return passed

def check_new_condition_5(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件5评估 (新规则) ---")

    high_between = data.get('high_between_er_and_latest')
    er_window_low_price = data.get('er_6_day_window_low')
    latest_price = data.get('latest_price')

    er_to_high_threshold = config.get('COND5_ER_TO_HIGH_THRESHOLD', 0.3)
    high_to_latest_threshold = config.get('COND5_HIGH_TO_LATEST_THRESHOLD', 0.079)

    if high_between is None or er_window_low_price is None or latest_price is None:
        if is_tracing: log_detail(f"  - 结果: False (数据不足: high_between={high_between}, er_window_low_price={er_window_low_price}, latest_price={latest_price})")
        return False

    if er_window_low_price <= 0 or latest_price <= 0:
        if is_tracing: log_detail(f"  - 结果: False (价格数据无效: er_window_low_price={er_window_low_price}, latest_price={latest_price})")
        return False

    cond_a = high_between >= er_window_low_price * (1 + er_to_high_threshold)
    cond_b = high_between >= latest_price * (1 + high_to_latest_threshold)
    passed = cond_a and cond_b

    if is_tracing:
        er_rise_pct = (high_between - er_window_low_price) / er_window_low_price
        latest_rise_pct = (high_between - latest_price) / latest_price
        log_detail(f"  - 财报窗口期(6天)最低价: {er_window_low_price:.2f}")
        log_detail(f"  - 财报日到最新日之间最高价: {high_between:.2f}")
        log_detail(f"  - 最新收盘价: {latest_price:.2f}")
        log_detail(f"  - 条件A (新): 最高价相对财报窗口期最低价涨幅 {er_rise_pct:.2%} >= {er_to_high_threshold:.2%} -> {cond_a}")
        log_detail(f"  - 条件B: 最高价相对最新价涨幅 {latest_rise_pct:.2%} >= {high_to_latest_threshold:.2%} -> {cond_b}")
        log_detail(f"  - 结果: {passed}")

    return passed

def check_w_bottom_pattern(data, config, log_detail, symbol_to_trace, check_strict_er_drop=True):
    """
    check_strict_er_drop:
    - True (用于条件6): 必须满足财报间大幅下跌(Drop A) 且 现价深跌(Drop B) 的前提。
    - False (用于条件1-5): 纯形态检测。
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    mode_str = "严格抄底模式(Cond6)" if check_strict_er_drop else "形态确认模式(Cond1-5)"

    if is_tracing: log_detail(f" - [W底检测启动] 模式: {mode_str}")

    all_er_prices = data.get('all_er_prices', [])
    prices_series = data.get('prices_since_er_series', [])
    dates_series = data.get('dates_since_er_series', [])

    if len(all_er_prices) < 2:
        if is_tracing: log_detail(f" - [失败] 财报数据不足 2 条。")
        return False

    if not prices_series or len(prices_series) < 10:
        if is_tracing: log_detail(f" - [失败] 财报后交易日数据不足 10 天。")
        return False

    period_lowest_price = min(prices_series)
    try:
        lowest_price_idx = prices_series.index(period_lowest_price)
    except ValueError:
        lowest_price_idx = 0

    if is_tracing: log_detail(f" - [区间统计] 财报后最低价: {period_lowest_price:.2f} (索引: {lowest_price_idx})")

    latest_er_price = all_er_prices[-1]

    threshold_b = 0.12
    if check_strict_er_drop:
        prev_er_price = all_er_prices[-2]
        if prev_er_price <= 0: return False

        er_drop_a_val = (prev_er_price - latest_er_price) / prev_er_price
        threshold_a = config.get("COND6_ER_DROP_A_THRESHOLD", 0.25)

        if er_drop_a_val > threshold_a:
            threshold_b = config.get("COND6_LOW_DROP_B_LARGE", 0.09)
        elif er_drop_a_val > 0.10:
            threshold_b = config.get("COND6_LOW_DROP_B_SMALL", 0.12)
        else:
            if is_tracing:
                log_detail(f" - [失败-Drop A] 财报间跌幅 {er_drop_a_val:.2%} <= 10%，不满足抄底前提。")
            return False

        if is_tracing:
            log_detail(f" - [通过-Drop A] 财报间跌幅 {er_drop_a_val:.2%}，设置深度阈值 B > {threshold_b:.1%}")

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

    for i in range(start_search_index, 0, -1):
        v1 = prices_series[i]
        v1_date = dates_series[i]

        if not (v1 < prices_series[i-1] and v1 < prices_series[i+1]):
            continue

        if is_tracing: log_detail(f" > 发现潜在V1: {v1_date} (价格:{v1:.2f})")

        diff_pct = abs(v1 - v2) / min(v1, v2)
        if diff_pct > price_tolerance:
            if is_tracing: log_detail(f"   x [几何-对称性失败] 左右底高低差 {diff_pct:.2%} > 容忍度 {price_tolerance:.1%}")
            continue

        neckline_prices = prices_series[i+1 : idx2]
        if not neckline_prices: continue

        min_trough_between = min(neckline_prices)
        avg_valley = (v1 + v2) / 2
        min_valley_absolute = min(v1, v2)
        noise_tolerance = config.get("COND6_W_BOTTOM_NOISE_TOLERANCE", 0.01)
        limit_price = min_valley_absolute * (1 - noise_tolerance)

        if min_trough_between < limit_price:
            if is_tracing:
                log_detail(f"   x [几何-形态失败] V1-V2之间存在破位低点({min_trough_between:.2f})，跌破最低谷底容忍线({limit_price:.2f})")
            continue

        max_peak = max(neckline_prices)
        peak_rise = (max_peak - avg_valley) / avg_valley
        min_peak_rise = config.get("COND6_W_BOTTOM_MIN_PEAK_RISE", 0.015)

        if peak_rise < min_peak_rise:
            if is_tracing:
                log_detail(f"   x [几何-力度失败] 中间反弹力度 {peak_rise:.2%} < {min_peak_rise:.1%}, 形态不显著")
            continue

        valley_min = min(v1, v2)
        is_absolute_low = valley_min <= period_lowest_price * 1.001
        higher_low_tolerance_days = config.get("COND6_W_BOTTOM_HIGHER_LOW_DAYS", 18)
        days_since_lowest = i - lowest_price_idx
        is_valid_higher_low = (valley_min > period_lowest_price) and (days_since_lowest >= higher_low_tolerance_days)

        if not (is_absolute_low or is_valid_higher_low):
            if is_tracing:
                log_detail(f"   x [位置失败] W底({valley_min:.2f}) > 绝对低点({period_lowest_price:.2f})。")
                log_detail(f"     且绝对低点仅在 {days_since_lowest} 天前 (需 >= {higher_low_tolerance_days} 天才允许抬高底)。")
            continue

        if is_tracing and is_valid_higher_low:
            log_detail(f"   ! [提示] 检测到底部抬高 (Higher Low): W底({valley_min:.2f}) > 前低({period_lowest_price:.2f})，但在 {days_since_lowest} 天前，形态有效。")

        if check_strict_er_drop:
            drop_b_val = (latest_er_price - valley_min) / latest_er_price
            if drop_b_val > threshold_b:
                if is_tracing:
                    log_detail(f"   - ✅ [成功! (严格模式)] V1:{v1:.2f}, V2:{v2:.2f}, 间隔:{idx2 - i}天")
                    log_detail(f"   - [深度检查] 深度 {drop_b_val:.2%} > 阈值 {threshold_b:.1%} -> 通过")
                return True
            else:
                if is_tracing:
                    log_detail(f"   x [失败-Drop B] 形态满足，但深度 {drop_b_val:.2%} 不足 (需 > {threshold_b:.1%})")
                continue
        else:
            if is_tracing:
                log_detail(f"   - ✅ [成功! (宽松模式)] V1:{v1:.2f}, V2:{v2:.2f}, 间隔:{idx2 - i}天")
            return True

    if is_tracing: log_detail(f" - [结果] 遍历结束，未找到满足所有条件的 W 底形态。")
    return False

def check_new_condition_6(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件6评估 (W底 - 抄底模式) ---")
    passed = check_w_bottom_pattern(data, config, log_detail, symbol_to_trace, check_strict_er_drop=True)
    if is_tracing: log_detail(f" - 结果: {passed}")
    return passed

def check_new_condition_7(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件7评估 (强财报深跌) ---")

    all_er_pcts = data.get('all_er_pcts', [])
    all_er_prices = data.get('all_er_prices', [])
    latest_price = data.get('latest_price')

    if len(all_er_pcts) < 4 or len(all_er_prices) < 4:
        if is_tracing: log_detail(f" - 结果: False (财报数据不足4次)")
        return False

    cond_a = (all_er_pcts[-1] > 0) and (all_er_pcts[-2] > 0)
    cond_b = all_er_prices[-1] > all_er_prices[-2]

    if is_tracing:
        log_detail(f" - 条件A (最近两次财报为正): {all_er_pcts[-1]:.2f} > 0 AND {all_er_pcts[-2]:.2f} > 0 -> {cond_a}")
        log_detail(f" - 条件B (财报价格上移): {all_er_prices[-1]:.2f} > {all_er_prices[-2]:.2f} -> {cond_b}")

    if not (cond_a and cond_b):
        if is_tracing: log_detail(" - 结果: False (前提条件未满足)")
        return False

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

# ==============================================================================
# ========== 条件8：财报持续下跌 + 财报后深跌 (PE_low 系列) ==========
# ==============================================================================
def _find_longest_declining_chain(prices, anchor_last=True):
    n = len(prices)
    if n == 0:
        return 0, []
    dp = [1] * n
    parent = [-1] * n
    for i in range(n):
        for j in range(i):
            if prices[j] is None or prices[i] is None:
                continue
            if prices[j] > prices[i] and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
                parent[i] = j
    end = n - 1 if anchor_last else max(range(n), key=lambda k: dp[k])
    chain = []
    cur = end
    while cur != -1:
        chain.append(cur)
        cur = parent[cur]
    chain.reverse()
    return dp[end], chain


def check_cond8_declining_earnings(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)

    lookback = config.get("COND8_EARNINGS_LOOKBACK_COUNT", 4)
    min_count = config.get("COND8_MIN_DECLINE_COUNT", 3)
    require_latest = config.get("COND8_REQUIRE_LATEST_IN_SEQUENCE", True)

    all_er_prices = data.get('all_er_prices', [])
    all_er_dates = data.get('all_er_dates', [])

    if is_tracing:
        log_detail(f"\n--- [{symbol}] 新增条件8评估 · 第一部分 (财报持续下跌) ---")

    if len(all_er_prices) < min_count:
        if is_tracing:
            log_detail(f"  - 结果: False (财报收盘价数量 {len(all_er_prices)} < 最低要求 {min_count})")
        return False, "财报数量不足"

    window_prices = all_er_prices[-lookback:]
    window_dates = all_er_dates[-lookback:] if len(all_er_dates) >= len(window_prices) else ["?"] * len(window_prices)

    length, chain_idx = _find_longest_declining_chain(window_prices, anchor_last=require_latest)
    passed = length >= min_count

    chain_desc = " → ".join([f"{window_dates[k]}({window_prices[k]:.2f})" for k in chain_idx]) if chain_idx else "无"

    if is_tracing:
        pair_desc = ", ".join([f"{d}:{p:.2f}" for d, p in zip(window_dates, window_prices)])
        log_detail(f"  - 观察窗口 (最近{lookback}次财报): {pair_desc}")
        log_detail(f"  - 模式: {'必须以最新财报结尾' if require_latest else '全局最长递减链'}")
        log_detail(f"  - 找到的递减链 (长度 {length}): {chain_desc}")
        log_detail(f"  - 要求长度 >= {min_count} -> {passed}")

    return passed, chain_desc


def check_cond8_drop_tier(data, config, log_detail, symbol_to_trace):
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)

    if is_tracing:
        log_detail(f"--- [{symbol}] 新增条件8评估 · 第二部分 (财报后深跌分档) ---")

    all_er_prices = data.get('all_er_prices', [])
    latest_price = data.get('latest_price')
    marketcap = data.get('marketcap')

    if not all_er_prices or latest_price is None:
        if is_tracing: log_detail("  - 结果: None (缺少价格数据)")
        return None, 0.0

    er_price = all_er_prices[-1]
    if er_price is None or er_price <= 0:
        if is_tracing: log_detail(f"  - 结果: None (最新财报收盘价无效: {er_price})")
        return None, 0.0

    cap_line = config.get("COND8_MARKETCAP_THRESHOLD", 500_000_000_000)
    is_big_cap = (marketcap is not None) and (marketcap > cap_line)

    if is_big_cap:
        t_low = config.get("COND8_LOW_DROP_BIG", 0.06)
        t_lower = config.get("COND8_LOWER_DROP_BIG", 0.11)
        t_lowest = config.get("COND8_LOWEST_DROP_BIG", 0.15)
        cap_desc = f"大市值 (> {cap_line/1e8:.0f}亿)"
    else:
        t_low = config.get("COND8_LOW_DROP_SMALL", 0.11)
        t_lower = config.get("COND8_LOWER_DROP_SMALL", 0.15)
        t_lowest = config.get("COND8_LOWEST_DROP_SMALL", 0.21)
        cap_desc = f"中小市值 (<= {cap_line/1e8:.0f}亿 或 市值未知)"

    def get_tier(pct):
        if pct >= t_lowest: return 'PE_lowest'
        elif pct >= t_lower: return 'PE_lower'
        elif pct >= t_low: return 'PE_low'
        return None

    ref_price = er_price
    ref_name = "最新财报日收盘价"
    drop_pct = (ref_price - latest_price) / ref_price
    tier = get_tier(drop_pct)

    if tier is None:
        next_day_price = data.get('latest_er_next_day_price')
        if next_day_price and next_day_price > 0:
            drop_pct_next = (next_day_price - latest_price) / next_day_price
            tier_next = get_tier(drop_pct_next)
            if tier_next is not None:
                if is_tracing:
                    log_detail(f"  - 提示: 相比财报日收盘价({er_price:.2f})跌幅 {drop_pct:.2%} 未达最低门槛({t_low:.2%})；"
                               f"改用财报日次日收盘价({next_day_price:.2f})重新比较，跌幅达到 {drop_pct_next:.2%}")
                ref_price = next_day_price
                ref_name = "财报日次日收盘价"
                drop_pct = drop_pct_next
                tier = tier_next

    if is_tracing:
        log_detail(f"  - 当前市值: {marketcap:,.0f}" if marketcap else "  - 当前市值: 未知")
        log_detail(f"  - 市值档位: {cap_desc}")
        log_detail(f"  - 最终基准参考价({ref_name}): {ref_price:.2f}, 最新收盘价: {latest_price:.2f}")
        log_detail(f"  - 最终计算跌幅: {drop_pct:.2%}")
        log_detail(f"  - 分档阈值: PE_low>={t_low:.2%}, PE_lower>={t_lower:.2%}, PE_lowest>={t_lowest:.2%}")
        log_detail(f"  - 判定结果: {tier if tier else '未达到任何档位'}")

    return tier, drop_pct


def check_turnover_filter(data, config, log_detail, symbol_to_trace, prefix="条件8"):
    """
    【修改】统一改用三级成交额判定 (单日 / ADV / 链条顺延)
    """
    ok, mode = evaluate_turnover(data, config, log_detail, symbol_to_trace, prefix=prefix)
    if ok and data.get('symbol') == symbol_to_trace:
        log_detail(f"  - [{prefix}·成交额] 通过 (级别: {mode})")
    return ok


def run_condition_8_scan(stock_data_cache, config, log_detail, symbol_to_trace, exclude_symbols=None):
    results = {'PE_low': [], 'PE_lower': [], 'PE_lowest': []}
    exclude_symbols = exclude_symbols or set()

    log_detail("\n========== 开始执行【条件8】独立扫描 (PE_low / PE_lower / PE_lowest) ==========")

    for symbol, data in stock_data_cache.items():
        if not (data and data.get('is_valid')):
            continue
        data['symbol'] = symbol
        is_tracing = (symbol == symbol_to_trace)

        if data.get('latest_date_str') == data.get('latest_er_date_str'):
            if is_tracing:
                log_detail(f"\n--- [{symbol}] 条件8: 跳过 (最新交易日 {data['latest_date_str']} 与最新财报日重合)")
            continue

        if symbol in exclude_symbols:
            if is_tracing:
                log_detail(f"\n--- [{symbol}] 条件8: 跳过 (已被其它分组收录，且开启了 COND8_EXCLUDE_EXISTING_RESULTS)")
            continue

        latest_price = data.get('latest_price')
        prev_prices = data.get('prev_window_prices', [])

        if not prev_prices or latest_price is None:
            if is_tracing:
                log_detail(f"\n--- [{symbol}] 条件8: 跳过 (缺少前一交易日价格数据无法判断是否下跌)")
            continue

        prev_price = prev_prices[0]
        if latest_price >= prev_price:
            if is_tracing:
                log_detail(f"\n--- [{symbol}] 条件8: 跳过 (最新收盘价 {latest_price:.2f} >= 前一日收盘价 {prev_price:.2f}，未处于下跌状态)")
            continue

        part1_ok, _chain_desc = check_cond8_declining_earnings(data, config, log_detail, symbol_to_trace)
        if not part1_ok:
            continue

        tier, drop_pct = check_cond8_drop_tier(data, config, log_detail, symbol_to_trace)
        if not tier:
            continue

        if config.get("COND8_APPLY_TURNOVER_FILTER", True):
            if not check_turnover_filter(data, config, log_detail, symbol_to_trace, prefix="条件8"):
                if is_tracing:
                    log_detail(f"  - [{symbol}] 条件8最终裁定: 失败 (成交额不足)。")
                continue

        results[tier].append(symbol)
        if is_tracing:
            log_detail(f"  - ✅ [{symbol}] 条件8最终裁定: 命中 {tier} (财报后跌幅 {drop_pct:.2%})。")

    log_detail(f"【条件8】扫描完成 -> PE_low: {len(results['PE_low'])} 个, "
               f"PE_lower: {len(results['PE_lower'])} 个, PE_lowest: {len(results['PE_lowest'])} 个")
    log_detail("=" * 76)

    return results

# ==============================================================================
# 入口条件
# ==============================================================================
def check_entry_conditions(data, symbol_to_trace, log_detail):
    """
    返回: (passed_any, passed_cond4, passed_cond5, passed_cond6, passed_cond7)
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)

    if is_tracing:
        log_detail(f"\n--- [{symbol}] 入口条件评估 ---")

    er_pcts = data.get('all_er_pcts', [])
    if not er_pcts or len(data.get('all_er_prices', [])) < CONFIG["RECENT_EARNINGS_COUNT"]:
        if is_tracing: log_detail(" - 预检失败: 缺少财报数据，无法评估入口条件。")
        return (False, False, False, False, False)

    prices_to_check = data['all_er_prices'][-CONFIG["RECENT_EARNINGS_COUNT"]:]
    latest_er_pct = er_pcts[-1]
    latest_er_price = prices_to_check[-1]
    avg_recent_price = sum(prices_to_check) / len(prices_to_check)
    previous_er_price = prices_to_check[-2]
    price_diff_pct_cond1b = ((latest_er_price - previous_er_price) / previous_er_price) if previous_er_price > 0 else 0

    drop_pct_for_cond1c = CONFIG["PRICE_DROP_FOR_COND1C"]
    threshold_price1c = latest_er_price * (1 - drop_pct_for_cond1c)

    cond1_a = latest_er_pct > 0
    er_diff_threshold = CONFIG["ER_PRICE_DIFF_THRESHOLD"]
    cond1_b = (latest_er_price > avg_recent_price) and (price_diff_pct_cond1b >= er_diff_threshold)
    cond1_c = data['latest_price'] <= threshold_price1c

    passed_original_cond1 = cond1_a and cond1_b and cond1_c

    if is_tracing:
        log_detail(" - [入口条件A] 条件1评估 (需同时满足 a, b, c):")
        log_detail(f"   - a) 最新财报涨跌幅 > 0 ({latest_er_pct:.4f}) -> {cond1_a}")
        log_detail(f"   - b) 最新财报价 > 平均价 且 较上次财报涨幅 >= {er_diff_threshold:.0%} -> {cond1_b}")
        log_detail(f"   - c) 最新价({data['latest_price']:.2f}) <= 财报价({latest_er_price:.2f}) * (1 - {drop_pct_for_cond1c}) = {threshold_price1c:.2f} -> {cond1_c}")
        log_detail(f"   - 条件1最终结果: {passed_original_cond1}")

    passed_new_cond2 = check_condition_2(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond3 = check_new_condition_3(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond4 = check_new_condition_4(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond5 = check_new_condition_5(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond6 = check_new_condition_6(data, CONFIG, log_detail, symbol_to_trace)
    passed_new_cond7 = check_new_condition_7(data, CONFIG, log_detail, symbol_to_trace)

    passed_any = (passed_original_cond1 or passed_new_cond2 or passed_new_cond3 or passed_new_cond4
                  or passed_new_cond5 or passed_new_cond6 or passed_new_cond7)

    if is_tracing:
        if passed_any:
            reasons = []
            if passed_original_cond1: reasons.append("条件1")
            if passed_new_cond2: reasons.append("条件2")
            if passed_new_cond3: reasons.append("条件3")
            if passed_new_cond4: reasons.append("条件4")
            if passed_new_cond5: reasons.append("条件5")
            if passed_new_cond6: reasons.append("条件6(W底)")
            if passed_new_cond7: reasons.append("条件7(强财报深跌)")
            log_detail(f"\n--- [{symbol}] 入口条件通过 (原因: {'、'.join(reasons)})。")
        else:
            log_detail(f"\n--- [{symbol}] 入口条件失败。七个入口条件均未满足。")

    return (passed_any, passed_new_cond4, passed_new_cond5, passed_new_cond6, passed_new_cond7)

def apply_common_filters(data, symbol_to_trace, log_detail, drop_pct_large, drop_pct_small, drop_pct_mini=None, skip_drawdown=False, skip_baseline_filter=False):
    """
    应用通用的过滤条件：价格回撤、N日基准价、成交额(三级判定)。
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)

    if is_tracing:
        log_detail(f"\n--- [{symbol}] 开始执行通用过滤 (使用 large={drop_pct_large*100}%, small={drop_pct_small*100}%" + (f", mini={drop_pct_mini*100}%" if drop_pct_mini else "") + ") ---")

    # 1. 价格回撤
    if not skip_drawdown:
        marketcap = data.get('marketcap')
        high_price_reference = data.get('high_since_er')
        if high_price_reference is None:
            high_price_reference = data.get('er_window_high_price')

        if high_price_reference is None or high_price_reference <= 0:
            if is_tracing: log_detail(f" - 最终裁定: 失败 (通用过滤1: 无法获取有效的最高价数据: {high_price_reference})。")
            return False

        is_strict_mode = (
            drop_pct_large == CONFIG["PRICE_DROP_PERCENTAGE_LARGE"] and
            drop_pct_small == CONFIG["PRICE_DROP_PERCENTAGE_SMALL"]
        )

        if is_strict_mode:
            if marketcap and marketcap >= CONFIG["MARKETCAP_THRESHOLD_GIANT"]: drop_pct = CONFIG["PRICE_DROP_PERCENTAGE_GIANT"]
            elif marketcap and marketcap >= CONFIG["MARKETCAP_THRESHOLD_MEGA"]: drop_pct = CONFIG["PRICE_DROP_PERCENTAGE_MEGA"]
            elif marketcap and marketcap >= CONFIG["MARKETCAP_THRESHOLD"]: drop_pct = CONFIG["PRICE_DROP_PERCENTAGE_SMALL"]
            else: drop_pct = CONFIG["PRICE_DROP_PERCENTAGE_LARGE"]
        else:
            if drop_pct_mini and marketcap and marketcap >= CONFIG["MARKETCAP_THRESHOLD_GIANT"]: drop_pct = drop_pct_mini
            elif marketcap and marketcap >= CONFIG["MARKETCAP_THRESHOLD"]: drop_pct = drop_pct_small
            else: drop_pct = drop_pct_large

        threshold_price_drawdown = high_price_reference * (1 - drop_pct)
        cond_drawdown_ok = data['latest_price'] <= threshold_price_drawdown

        if is_tracing:
            log_detail(" - [通用过滤1] 价格回撤:")
            log_detail(f"   - 市值: {marketcap} -> 使用下跌百分比: {drop_pct*100:.1f}%")
            log_detail(f"   - 判断: 最新价({data['latest_price']:.2f}) <= 财报日至今最高价({high_price_reference:.2f}) * (1 - {drop_pct:.2f}) = 阈值价({threshold_price_drawdown:.2f}) -> {cond_drawdown_ok}")

        if not cond_drawdown_ok:
            if is_tracing: log_detail(" - 最终裁定: 失败 (通用过滤1: 价格回撤不满足)。")
            return False
    else:
        if is_tracing: log_detail(" - [通用过滤1] 价格回撤: 已跳过 (条件5/6/7模式)。")

    # 2. 相对 N 日基准价
    if not skip_baseline_filter:
        lookback_days = CONFIG.get("LOOKBACK_WINDOW_DAYS", 10)
        prev_prices = data.get('prev_window_prices', [])
        prev_dates = data.get('prev_window_dates', [])
        latest_er_date = data.get('latest_er_date_str')

        if len(prev_prices) < lookback_days:
            if is_tracing: log_detail(f" - 最终裁定: 失败 (通用过滤2: 可用历史交易日不足 {lookback_days} 日，只有{len(prev_prices)}日数据)。")
            return False

        using_er_price_logic = False
        if latest_er_date and latest_er_date in prev_dates:
            er_index = prev_dates.index(latest_er_date)
            baseline_price = prev_prices[er_index]
            using_er_price_logic = True
        else:
            baseline_price = min(prev_prices)

        symbol_tags = data.get('tags', set())
        hot_tags = CONFIG.get("HOT_TAGS", set())
        is_hot_stock = bool(symbol_tags & hot_tags)

        if is_hot_stock:
            max_increase_pct = CONFIG.get("MAX_INCREASE_PERCENTAGE_SINCE_LOW_HOT", 0.12)
        else:
            max_increase_pct = CONFIG["MAX_INCREASE_PERCENTAGE_SINCE_LOW"]

        threshold_price_window = baseline_price * (1 + max_increase_pct)
        cond_window_ok = data['latest_price'] <= threshold_price_window

        if is_tracing:
            log_detail(f" - [通用过滤2] 相对{lookback_days} 日基准价:")
            if using_er_price_logic:
                log_detail(f"   - 策略: 财报日({latest_er_date})在{lookback_days}天内，使用财报日收盘价作为基准。")
            else:
                log_detail(f"   - 策略: 财报日不在{lookback_days}天内，使用{lookback_days}日最低价作为基准。")
            hot_status_str = f"是 (放宽至 {max_increase_pct:.0%})" if is_hot_stock else f"否 (保持 {max_increase_pct:.0%})"
            log_detail(f"   - 热门判定: {hot_status_str} (Tags: {symbol_tags})")
            log_detail(f"   - 基准价: {baseline_price:.2f}")
            log_detail(f"   - 判断: 最新价 {data['latest_price']:.2f} <= 基准价*{1+max_increase_pct:.2f} ({threshold_price_window:.2f}) -> {cond_window_ok}")

        if not cond_window_ok:
            if is_tracing: log_detail(f" - 最终裁定: 失败 (通用过滤2: 相对{lookback_days}日基准价条件不满足)。")
            return False
    else:
        if is_tracing: log_detail(" - [通用过滤2] 相对N日基准价: 已跳过 (条件4/5模式)。")

    # 3. 【修改】成交额三级判定
    if is_tracing: log_detail(" - [通用过滤3] 成交额 (三级判定: 单日 / ADV / 链条顺延):")
    cond_turnover_ok, turnover_mode = evaluate_turnover(data, CONFIG, log_detail, symbol_to_trace, prefix="通用过滤3")
    data['turnover_pass_mode'] = turnover_mode

    if not cond_turnover_ok:
        if is_tracing: log_detail(" - 最终裁定: 失败 (通用过滤3: 成交额三级判定均不满足)。")
        return False

    if is_tracing: log_detail(f" - 最终裁定: 成功! 所有通用过滤条件均满足 (成交额通过级别: {turnover_mode})。")
    return True

def apply_post_filters(symbols, stock_data_cache, symbol_to_trace, log_detail):
    pe_valid_symbols = []
    pe_invalid_symbols = []

    for symbol in symbols:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n--- [{symbol}] 后置过滤器评估 ---")

        data = stock_data_cache[symbol]
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

    if TARGET_DATE:
        log_detail(f"\n⚠️⚠️⚠️ 注意：当前处于【回测模式】，目标日期：{TARGET_DATE} ⚠️⚠️⚠️")
        log_detail("为了保护现有数据，本次运行将【不会】更新 Panel 和 History JSON 文件。")
        log_detail("仅用于生成 trace log 进行逻辑验证。\n")

    tag_blacklist_from_file, hot_tags_from_file = load_tag_settings(TAGS_SETTING_JSON_FILE)
    CONFIG["BLACKLIST_TAGS"] = tag_blacklist_from_file
    CONFIG["HOT_TAGS"] = hot_tags_from_file
    CONFIG["SYMBOL_BLACKLIST"] = load_earning_symbol_blacklist(BLACKLIST_JSON_FILE)

    # ========== 【新增】只读加载历史，供成交额链条顺延使用 ==========
    CONFIG["_EARNING_HISTORY"] = load_earning_history_readonly(EARNING_HISTORY_JSON_FILE)

    all_symbols, symbol_to_sector_map = load_all_symbols(SECTORS_JSON_FILE, CONFIG["TARGET_SECTORS"])
    if all_symbols is None:
        log_detail("错误: 无法加载symbols，程序终止。")
        return

    symbol_blacklist = CONFIG.get("SYMBOL_BLACKLIST", set())
    if symbol_blacklist:
        all_symbols = [s for s in all_symbols if s not in symbol_blacklist]

    symbol_to_tags_map = load_symbol_tags(DESCRIPTION_JSON_FILE)

    stock_data_cache = build_stock_data_cache(
        all_symbols, symbol_to_sector_map, DB_FILE, SYMBOL_TO_TRACE,
        log_detail, symbol_to_tags_map, target_date=TARGET_DATE
    )

    def perform_filter_pass(symbols_to_check, drop_large, drop_small, pass_name, drop_mini=None):
        preliminary_results = []
        oversell_w_candidates = []
        pe_deep_candidates = []
        pe_deeper_candidates = []
        pe_w_candidates = []

        for symbol in symbols_to_check:
            data = stock_data_cache.get(symbol)
            if not (data and data['is_valid']):
                continue
            data['symbol'] = symbol

            passed_any, passed_cond4, passed_cond5, passed_cond6, passed_cond7 = check_entry_conditions(data, SYMBOL_TO_TRACE, log_detail)
            if not passed_any:
                continue

            should_skip_drawdown = passed_cond5 or passed_cond6 or passed_cond7
            should_skip_baseline = passed_cond4 or passed_cond5

            current_drop_large = drop_large
            current_drop_small = drop_small

            if pass_name == "普通宽松":
                symbol_tags = data.get('tags', set())
                hot_tags = CONFIG.get("HOT_TAGS", set())
                if symbol_tags & hot_tags:
                    current_drop_large = CONFIG.get("HOT_RELAXED_PRICE_DROP_PERCENTAGE_LARGE", drop_large)
                    current_drop_small = CONFIG.get("HOT_RELAXED_PRICE_DROP_PERCENTAGE_SMALL", drop_small)
                    if symbol == SYMBOL_TO_TRACE:
                        log_detail(f" - [动态阈值] 命中热门标签，普通宽松阈值调整为 large={current_drop_large*100}%, small={current_drop_small*100}%")

            if apply_common_filters(data, SYMBOL_TO_TRACE, log_detail, current_drop_large, current_drop_small, drop_pct_mini=drop_mini, skip_drawdown=should_skip_drawdown, skip_baseline_filter=should_skip_baseline):
                if data['latest_date_str'] == data['latest_er_date_str']:
                    if symbol == SYMBOL_TO_TRACE:
                        log_detail(f" - [通用过滤] 失败 (日期重合): 最新交易日({data['latest_date_str']}) 与 最新财报日相同。")
                    continue

                if passed_cond6 or passed_cond7:
                    oversell_w_candidates.append(symbol)
                else:
                    is_w_bottom = check_w_bottom_pattern(data, CONFIG, log_detail, SYMBOL_TO_TRACE, check_strict_er_drop=False)

                    if is_w_bottom:
                        pe_w_lookback = CONFIG.get("PE_W_LOOKBACK_DAYS", 21)
                        pe_w_max_rise = CONFIG.get("PE_W_MAX_RISE_FROM_LOW", 0.06)
                        recent_prices = data.get('prev_window_prices', [])[:pe_w_lookback] + [data['latest_price']]
                        recent_min_price = min(recent_prices) if recent_prices else data['latest_price']
                        rise_from_recent_min = (data['latest_price'] - recent_min_price) / recent_min_price

                        if rise_from_recent_min <= pe_w_max_rise:
                            if symbol == SYMBOL_TO_TRACE:
                                log_detail(f" - [PE_W 附加检查] 成功: 最新价较近{pe_w_lookback}天最低价({recent_min_price:.2f})涨幅 {rise_from_recent_min:.2%} <= {pe_w_max_rise:.0%}")
                            pe_w_candidates.append(symbol)
                        else:
                            if symbol == SYMBOL_TO_TRACE:
                                log_detail(f" - [PE_W 附加检查] 失败: 最新价较近{pe_w_lookback}天最低价({recent_min_price:.2f})涨幅 {rise_from_recent_min:.2%} > {pe_w_max_rise:.0%} -> 转入深跌判定")
                            is_w_bottom = False

                    if not is_w_bottom:
                        if symbol == SYMBOL_TO_TRACE:
                            log_detail(f" - [W形态最终裁定]： W底形态未构成 -> 转入深跌判定流程。")

                        latest_price = data['latest_price']
                        er_close_price = data['all_er_prices'][-1]

                        er_window_high = data.get('er_window_high_price')
                        if er_window_high is None:
                            er_window_high = er_close_price

                        high_since_er = data.get('high_since_er')
                        if high_since_er is None:
                            high_since_er = er_window_high

                        limit_deeper = CONFIG["PE_DEEPER_DROP_THRESHOLD"]
                        pass_deeper = latest_price <= er_close_price * (1 - limit_deeper)

                        if pass_deeper:
                            if symbol == SYMBOL_TO_TRACE:
                                log_detail(f" - [超深跌Deeper判定] 命中: 较财报日跌幅 {((er_close_price-latest_price)/er_close_price):.2%} >= {limit_deeper:.0%}")
                            pe_deeper_candidates.append(symbol)
                        else:
                            limit_er_base = CONFIG["PE_DEEP_DROP_THRESHOLD"]
                            limit_window_base = CONFIG["PE_DEEP_MAX_DROP_THRESHOLD"]
                            limit_high_since_er_base = CONFIG.get("PE_DEEP_HIGH_SINCE_ER_THRESHOLD", 0.18)

                            pass_er_base = latest_price <= er_close_price * (1 - limit_er_base)
                            pass_window_base = latest_price <= er_window_high * (1 - limit_window_base)
                            pass_high_since_base = latest_price <= high_since_er * (1 - limit_high_since_er_base)

                            if pass_er_base or pass_window_base or pass_high_since_base:
                                if symbol == SYMBOL_TO_TRACE:
                                    log_detail(f" - [深跌Deep判定] 命中: 财报日跌幅({pass_er_base}) OR 窗口高点跌幅({pass_window_base}) OR 至今高点跌幅({pass_high_since_base})")
                                    log_detail(f"   * 最新价: {latest_price:.2f}")
                                    log_detail(f"   * 财报日价: {er_close_price:.2f} (需跌破 {er_close_price*(1-limit_er_base):.2f})")
                                    log_detail(f"   * 窗口高点: {er_window_high:.2f} (需跌破 {er_window_high*(1-limit_window_base):.2f})")
                                    log_detail(f"   * 至今高点: {high_since_er:.2f} (需跌破 {high_since_er*(1-limit_high_since_er_base):.2f})")
                                pe_deep_candidates.append(symbol)
                            else:
                                preliminary_results.append(symbol)

        pe_valid, pe_invalid = apply_post_filters(preliminary_results, stock_data_cache, SYMBOL_TO_TRACE, log_detail)

        return (pe_valid, pe_invalid, oversell_w_candidates, pe_deep_candidates, pe_w_candidates, pe_deeper_candidates)

    # --- 执行筛选 ---
    strict_symbols, relaxed_symbols, sub_relaxed_symbols, super_relaxed_symbols = [], [], [], []
    for symbol in list(stock_data_cache.keys()):
        data = stock_data_cache.get(symbol)
        if not (data and data['is_valid']): continue
        data['symbol'] = symbol

        filter_mode = check_special_condition(data, CONFIG, log_detail, SYMBOL_TO_TRACE)
        if filter_mode == 3: super_relaxed_symbols.append(symbol)
        elif filter_mode == 2: sub_relaxed_symbols.append(symbol)
        elif filter_mode == 1: relaxed_symbols.append(symbol)
        else: strict_symbols.append(symbol)

    res_super = perform_filter_pass(super_relaxed_symbols, CONFIG["SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "最宽松")
    res_sub = perform_filter_pass(
        sub_relaxed_symbols,
        CONFIG["SUB_RELAXED_PRICE_DROP_PERCENTAGE_LARGE"],
        CONFIG["SUB_RELAXED_PRICE_DROP_PERCENTAGE_SMALL"],
        "次宽松",
        drop_mini=CONFIG.get("SUB_RELAXED_PRICE_DROP_PERCENTAGE_MINI")
    )
    res_relaxed = perform_filter_pass(relaxed_symbols, CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_SMALL"], "普通宽松", drop_mini=CONFIG.get("RELAXED_PRICE_DROP_PERCENTAGE_MINI"))
    res_strict = perform_filter_pass(strict_symbols, CONFIG["PRICE_DROP_PERCENTAGE_LARGE"], CONFIG["PRICE_DROP_PERCENTAGE_SMALL"], "严格")

    raw_pe_valid = res_super[0] + res_sub[0] + res_relaxed[0] + res_strict[0]
    raw_pe_invalid = res_super[1] + res_sub[1] + res_relaxed[1] + res_strict[1]
    raw_oversell_w = res_super[2] + res_sub[2] + res_relaxed[2] + res_strict[2]
    raw_pe_deep = res_super[3] + res_sub[3] + res_relaxed[3] + res_strict[3]
    raw_pe_w = res_super[4] + res_sub[4] + res_relaxed[4] + res_strict[4]
    raw_pe_deeper = res_super[5] + res_sub[5] + res_relaxed[5] + res_strict[5]

    cond8_exclude = set()
    if CONFIG.get("COND8_EXCLUDE_EXISTING_RESULTS", False):
        cond8_exclude = set(raw_pe_valid) | set(raw_pe_invalid) | set(raw_oversell_w) \
                        | set(raw_pe_deep) | set(raw_pe_w) | set(raw_pe_deeper)

    cond8_results = run_condition_8_scan(stock_data_cache, CONFIG, log_detail, SYMBOL_TO_TRACE, exclude_symbols=cond8_exclude)
    raw_pe_low = cond8_results['PE_low']
    raw_pe_lower = cond8_results['PE_lower']
    raw_pe_lowest = cond8_results['PE_lowest']

    tag_blacklist = CONFIG["BLACKLIST_TAGS"]
    def filter_tags(syms):
        return [s for s in syms if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]

    blacklist = load_blacklist(BLACKLIST_JSON_FILE)

    try:
        with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f: panel_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): panel_data = {}

    exist_Strategy34 = set(panel_data.get('Strategy34', {}).keys())
    exist_Strategy12 = set(panel_data.get('Strategy12', {}).keys())
    exist_must = set(panel_data.get('Must', {}).keys())
    already_in_panels = exist_Strategy34 | exist_Strategy12 | exist_must

    final_pe_valid_to_write = sorted(list(set(filter_tags(raw_pe_valid)) - blacklist - already_in_panels))
    final_pe_invalid_to_write = sorted(list(set(filter_tags(raw_pe_invalid)) - blacklist - already_in_panels))
    final_oversell_w_to_write = sorted(list(set(filter_tags(raw_oversell_w))))
    final_pe_deeper_to_write = sorted(list(set(filter_tags(raw_pe_deeper))))
    final_pe_w_to_write = sorted(list(set(filter_tags(raw_pe_w))))
    final_pe_deep_to_write = sorted(list(set(filter_tags(raw_pe_deep)) - already_in_panels))

    final_pe_low_to_write = sorted(list(set(filter_tags(raw_pe_low)) - already_in_panels))
    final_pe_lower_to_write = sorted(list(set(filter_tags(raw_pe_lower)) - already_in_panels))
    final_pe_lowest_to_write = sorted(list(set(filter_tags(raw_pe_lowest)) - already_in_panels))

    if SYMBOL_TO_TRACE:
        raw_sets = [
            (set(raw_pe_valid), "PE_valid"), (set(raw_pe_invalid), "PE_invalid"),
            (set(raw_pe_deep), "PE_Deep"), (set(raw_pe_w), "PE_W"), (set(raw_oversell_w), "OverSell_W"),
            (set(raw_pe_deeper), "PE_Deeper"),
            (set(raw_pe_low), "PE_low"), (set(raw_pe_lower), "PE_lower"), (set(raw_pe_lowest), "PE_lowest")
        ]
        for s_set, name in raw_sets:
            if SYMBOL_TO_TRACE in s_set:
                is_tag_blocked = bool(set(symbol_to_tags_map.get(SYMBOL_TO_TRACE, [])).intersection(tag_blacklist))
                if name in ["PE_valid", "PE_invalid"]:
                    if SYMBOL_TO_TRACE in blacklist:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' ({name}) 算法通过，但在 'newlow' 黑名单中 -> 不写Panel。")
                    elif SYMBOL_TO_TRACE in already_in_panels:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' ({name}) 算法通过，但已在其他 Panel 中 -> 不写Panel。")
                    elif is_tag_blocked:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' ({name}) 算法通过，但命中 Tag 黑名单 -> 不写Panel。")
                    else:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' 将写入 ({name})。")
                elif name in ["PE_low", "PE_lower", "PE_lowest", "PE_Deep"]:
                    if is_tag_blocked:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' ({name}) 算法通过，但命中 Tag 黑名单 -> 不写Panel。")
                    elif SYMBOL_TO_TRACE in already_in_panels:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' ({name}) 算法通过，但已在其他 Panel(Strategy/Must) 中 -> 不写Panel。")
                    else:
                        log_detail(f"\n追踪信息: '{SYMBOL_TO_TRACE}' 将写入 ({name})。")
                else:
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
            base = f"{sym}{cond3_type}" if cond3_type else ""
            if base: note_map[sym] = base + ("热" if is_hot else "")
            else: note_map[sym] = f"{sym}热" if is_hot else ""
        return note_map

    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 [安全拦截] 回测模式 (Date: {TARGET_DATE}) 已启用。")
        log_detail(f"🛑 为防止覆盖当前数据，以下文件写入操作已被取消：")
        log_detail(f"   1. 面板文件: {os.path.basename(PANEL_JSON_FILE)}")
        log_detail(f"   2. 历史记录: {os.path.basename(EARNING_HISTORY_JSON_FILE)}")
        log_detail("-" * 40)
        log_detail(f"📊 [模拟结果] 如果不是回测，将写入以下数量的 Symbol:")
        log_detail(f"   - PE_valid:   {len(final_pe_valid_to_write)} 个")
        log_detail(f"   - PE_invalid: {len(final_pe_invalid_to_write)} 个")
        log_detail(f"   - PE_Deep:    {len(final_pe_deep_to_write)} 个")
        log_detail(f"   - PE_Deeper:  {len(final_pe_deeper_to_write)} 个")
        log_detail(f"   - PE_W:       {len(final_pe_w_to_write)} 个")
        log_detail(f"   - OverSell_W: {len(final_oversell_w_to_write)} 个")
        log_detail(f"   - PE_low:     {len(final_pe_low_to_write)} 个")
        log_detail(f"   - PE_lower:   {len(final_pe_lower_to_write)} 个")
        log_detail(f"   - PE_lowest:  {len(final_pe_lowest_to_write)} 个")

        if SYMBOL_TO_TRACE:
            log_detail(f"🔎 [验证] Symbol '{SYMBOL_TO_TRACE}' 最终筛选状态:")
            log_detail(f"   - 是否进入 PE_valid:   {SYMBOL_TO_TRACE in final_pe_valid_to_write}")
            log_detail(f"   - 是否进入 PE_Deep:    {SYMBOL_TO_TRACE in final_pe_deep_to_write}")
            log_detail(f"   - 是否进入 PE_Deeper:  {SYMBOL_TO_TRACE in final_pe_deeper_to_write}")
            log_detail(f"   - 是否进入 PE_W:       {SYMBOL_TO_TRACE in final_pe_w_to_write}")
            log_detail(f"   - 是否进入 OverSell_W: {SYMBOL_TO_TRACE in final_oversell_w_to_write}")
            log_detail(f"   - 是否进入 PE_low:     {SYMBOL_TO_TRACE in final_pe_low_to_write}")
            log_detail(f"   - 是否进入 PE_lower:   {SYMBOL_TO_TRACE in final_pe_lower_to_write}")
            log_detail(f"   - 是否进入 PE_lowest:  {SYMBOL_TO_TRACE in final_pe_lowest_to_write}")
            tr = stock_data_cache.get(SYMBOL_TO_TRACE, {})
            if tr.get('turnover_pass_mode'):
                log_detail(f"   - 成交额通过级别:      {tr.get('turnover_pass_mode')}")

        log_detail("="*60 + "\n")
        return

    # ======== 生产模式写入 ========
    pe_valid_notes = build_symbol_note_map(final_pe_valid_to_write)
    pe_invalid_notes = build_symbol_note_map(final_pe_invalid_to_write)
    oversell_w_notes = build_symbol_note_map(final_oversell_w_to_write)
    pe_deep_notes = build_symbol_note_map(final_pe_deep_to_write)
    pe_w_notes = build_symbol_note_map(final_pe_w_to_write)
    pe_deeper_notes = build_symbol_note_map(final_pe_deeper_to_write)
    pe_low_notes = build_symbol_note_map(final_pe_low_to_write)
    pe_lower_notes = build_symbol_note_map(final_pe_lower_to_write)
    pe_lowest_notes = build_symbol_note_map(final_pe_lowest_to_write)

    update_json_panel(final_pe_valid_to_write, PANEL_JSON_FILE, 'PE_valid', symbol_to_note=pe_valid_notes)
    update_json_panel(final_pe_valid_to_write, PANEL_JSON_FILE, 'PE_valid_backup', symbol_to_note=pe_valid_notes)
    update_json_panel(final_pe_invalid_to_write, PANEL_JSON_FILE, 'PE_invalid', symbol_to_note=pe_invalid_notes)
    update_json_panel(final_pe_invalid_to_write, PANEL_JSON_FILE, 'PE_invalid_backup', symbol_to_note=pe_invalid_notes)
    update_json_panel(final_oversell_w_to_write, PANEL_JSON_FILE, 'OverSell_W', symbol_to_note=oversell_w_notes)
    update_json_panel(final_oversell_w_to_write, PANEL_JSON_FILE, 'OverSell_W_backup', symbol_to_note=oversell_w_notes)
    update_json_panel(final_pe_deep_to_write, PANEL_JSON_FILE, 'PE_Deep', symbol_to_note=pe_deep_notes)
    update_json_panel(final_pe_deep_to_write, PANEL_JSON_FILE, 'PE_Deep_backup', symbol_to_note=pe_deep_notes)
    update_json_panel(final_pe_deeper_to_write, PANEL_JSON_FILE, 'PE_Deeper', symbol_to_note=pe_deeper_notes)
    update_json_panel(final_pe_deeper_to_write, PANEL_JSON_FILE, 'PE_Deeper_backup', symbol_to_note=pe_deeper_notes)
    update_json_panel(final_pe_w_to_write, PANEL_JSON_FILE, 'PE_W', symbol_to_note=pe_w_notes)
    update_json_panel(final_pe_w_to_write, PANEL_JSON_FILE, 'PE_W_backup', symbol_to_note=pe_w_notes)
    update_json_panel(final_pe_low_to_write, PANEL_JSON_FILE, 'PE_low', symbol_to_note=pe_low_notes)
    update_json_panel(final_pe_low_to_write, PANEL_JSON_FILE, 'PE_low_backup', symbol_to_note=pe_low_notes)
    update_json_panel(final_pe_lower_to_write, PANEL_JSON_FILE, 'PE_lower', symbol_to_note=pe_lower_notes)
    update_json_panel(final_pe_lower_to_write, PANEL_JSON_FILE, 'PE_lower_backup', symbol_to_note=pe_lower_notes)
    update_json_panel(final_pe_lowest_to_write, PANEL_JSON_FILE, 'PE_lowest', symbol_to_note=pe_lowest_notes)
    update_json_panel(final_pe_lowest_to_write, PANEL_JSON_FILE, 'PE_lowest_backup', symbol_to_note=pe_lowest_notes)

    groups_to_log = {
        "PE_valid": raw_pe_valid,
        "PE_invalid": raw_pe_invalid,
        "PE_Deep": raw_pe_deep,
        "PE_Deeper": raw_pe_deeper,
        "PE_W": raw_pe_w,
        "OverSell_W": raw_oversell_w,
        "PE_low": raw_pe_low,
        "PE_lower": raw_pe_lower,
        "PE_lowest": raw_pe_lowest,
    }

    has_written_any = False
    for group_name, symbols in groups_to_log.items():
        if symbols:
            update_earning_history_json(EARNING_HISTORY_JSON_FILE, group_name, sorted(set(symbols)), log_detail)
            has_written_any = True

    if not has_written_any:
        log_detail("\n--- 无符合条件的 symbol 可写入 Earning_History.json ---")

def main():
    if SYMBOL_TO_TRACE:
        print(f"追踪模式已启用，目标: {SYMBOL_TO_TRACE}。日志将仅在控制台输出。")
    else:
        print("追踪模式未启用 (SYMBOL_TO_TRACE 为空)。")

    def log_detail_console(message):
        print(message)

    run_processing_logic(log_detail_console)
    print("\n程序运行结束。")

if __name__ == '__main__':
    main()