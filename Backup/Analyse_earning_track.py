import sqlite3
import json
import os
import datetime
from collections import defaultdict

# --- 0. 调试追踪配置 ---
# ##############################################################################
#  请在这里修改为你想要追踪的股票代码
SYMBOL_TO_TRACE = "HPE" 
# ##############################################################################
LOG_FILE_PATH = "/Users/yanzhang/Downloads/a.txt"


# --- 1. 配置文件和路径 ---
# 使用一个配置字典来管理所有路径，更清晰
PATHS = {
    "base": "/Users/yanzhang/Coding/",
    "news": lambda base: os.path.join(base, "News"),
    "db": lambda base: os.path.join(base, "Database"),
    "config": lambda base: os.path.join(base, "Financial_System", "Modules"),
    "earnings_release_next": lambda news: os.path.join(news, "Earnings_Release_next.txt"),
    "earnings_release_new": lambda news: os.path.join(news, "Earnings_Release_new.txt"),
    "sectors_json": lambda config: os.path.join(config, "Sectors_All.json"),
    "db_file": lambda db: os.path.join(db, "Finance.db"),
    "blacklist_json": lambda config: os.path.join(config, "Blacklist.json"),
    "panel_json": lambda config: os.path.join(config, "Sectors_panel.json"),
    "output_next_week": lambda news: os.path.join(news, "NextWeek_Earning.txt"),
    "backup_next_week": lambda news: os.path.join(news, "backup", "NextWeek_Earning.txt"),
    "output_notification": lambda news: os.path.join(news, "notification_earning.txt"),
    "backup_notification": lambda news: os.path.join(news, "backup", "notification_earning.txt"),
}

# 动态生成完整路径
base_path = PATHS["base"]
news_path = PATHS["news"](base_path)
db_path = PATHS["db"](base_path)
config_path = PATHS["config"](base_path)

DB_FILE = PATHS["db_file"](db_path)
SECTORS_JSON_FILE = PATHS["sectors_json"](config_path)
BLACKLIST_JSON_FILE = PATHS["blacklist_json"](config_path)
PANEL_JSON_FILE = PATHS["panel_json"](config_path)

# --- 2. 可配置参数 ---
# 使用一个配置字典来管理所有参数
CONFIG = {
    "NUM_EARNINGS_TO_CHECK": 2,
    "MIN_DROP_PERCENTAGE": 0.04,
    "RISE_DROP_PERCENTAGE": 0.07,
    "MAX_DROP_PERCENTAGE": 0.13,
    "MIN_TURNOVER": 100_000_000,
    "MARKETCAP_THRESHOLD": 100_000_000_000,
}

# --- 3. 辅助与文件操作模块 ---

def create_symbol_to_sector_map(json_file_path):
    """从Sectors_All.json创建 symbol -> sector 的映射。"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            sectors_data = json.load(f)
        symbol_map = {symbol: sector for sector, symbols in sectors_data.items() for symbol in symbols}
        print(f"成功创建板块映射，共 {len(symbol_map)} 个 symbol。")
        return symbol_map
    except Exception as e:
        print(f"错误: 创建板块映射失败: {e}")
        return None

def get_symbols_from_file(file_path):
    """从文本文件中提取股票代码。"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return [line.strip().split(':')[0].strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"信息: 文件未找到 {file_path}，返回空列表。")
        return []

def load_blacklist(json_file_path):
    """从Blacklist.json加载'newlow'黑名单。"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        blacklist = set(data.get('newlow', []))
        print(f"成功加载 'newlow' 黑名单: {len(blacklist)} 个 symbol。")
        return blacklist
    except Exception as e:
        print(f"警告: 加载黑名单失败: {e}，将不进行过滤。")
        return set()

def update_json_panel(symbols_list, target_json_path, group_name):
    """更新JSON面板文件。"""
    print(f"\n--- 更新 JSON 文件: {os.path.basename(target_json_path)} -> '{group_name}' ---")
    try:
        with open(target_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"信息: 目标JSON文件不存在或格式错误，将创建一个新的。")
        data = {}

    data[group_name] = {symbol: "" for symbol in sorted(symbols_list)}

    try:
        with open(target_json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"成功将 {len(symbols_list)} 个 symbol 写入组 '{group_name}'.")
    except Exception as e:
        print(f"错误: 写入JSON文件失败: {e}")
        
def get_next_er_date(last_er_date):
    """计算理论上的下一次财报日期 (+93天)"""
    return last_er_date + datetime.timedelta(days=93)


# --- 4. 核心数据获取模块 (性能优化的关键) ---

def build_stock_data_cache(symbols, db_path, symbol_sector_map, symbol_to_trace, log_detail):
    """
    为所有给定的symbols一次性从数据库加载所有需要的数据。
    这是性能优化的核心，避免了重复查询。
    """
    print(f"\n--- 开始为 {len(symbols)} 个 symbol 构建数据缓存 ---")
    cache = {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    market_cap_exists = True

    for i, symbol in enumerate(symbols):
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n{'='*20} 开始为目标 {symbol} 构建数据缓存 {'='*20}")

        data = {'is_valid': False}
        table_name = symbol_sector_map.get(symbol)
        if not table_name:
            if is_tracing: log_detail(f"[{symbol}] 失败: 在板块映射中未找到该symbol，无法确定数据表。")
            continue
        if is_tracing: log_detail(f"[{symbol}] 信息: 找到板块为 '{table_name}'。")

        cursor.execute(
            "SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT ?",
            (symbol, CONFIG["NUM_EARNINGS_TO_CHECK"] + 1)
        )
        earnings_dates = [r[0] for r in cursor.fetchall()]
        if is_tracing: log_detail(f"[{symbol}] 步骤1: 获取财报日期。找到 {len(earnings_dates)} 个: {earnings_dates}")
        
        if len(earnings_dates) < CONFIG["NUM_EARNINGS_TO_CHECK"]:
            if is_tracing: log_detail(f"[{symbol}] 失败: 财报次数 ({len(earnings_dates)}) 少于要求的 {CONFIG['NUM_EARNINGS_TO_CHECK']} 次。")
            continue

        data['all_er_dates'] = earnings_dates
        data['latest_er_date_str'] = earnings_dates[0]
        data['latest_er_date'] = datetime.datetime.strptime(earnings_dates[0], "%Y-%m-%d").date()

        er_prices = []
        for date_str in earnings_dates:
            cursor.execute(f'SELECT price FROM "{table_name}" WHERE name = ? AND date = ?', (symbol, date_str))
            price_result = cursor.fetchone()
            er_prices.append(price_result[0] if price_result and price_result[0] is not None else None)
        
        if is_tracing: log_detail(f"[{symbol}] 步骤2: 获取财报日收盘价。价格: {er_prices}")

        if any(p is None for p in er_prices[:CONFIG["NUM_EARNINGS_TO_CHECK"]]):
            if is_tracing: log_detail(f"[{symbol}] 失败: 前 {CONFIG['NUM_EARNINGS_TO_CHECK']} 次财报中存在缺失的价格。")
            continue

        data['all_er_prices'] = er_prices
        
        cursor.execute(f'SELECT date, price, volume FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1', (symbol,))
        latest_row = cursor.fetchone()
        if not latest_row or latest_row[1] is None or latest_row[2] is None:
            if is_tracing: log_detail(f"[{symbol}] 失败: 未能获取到有效的最新交易日数据。查询结果: {latest_row}")
            continue
            
        data['latest_date_str'], data['latest_price'], data['latest_volume'] = latest_row
        data['latest_date'] = datetime.datetime.strptime(data['latest_date_str'], "%Y-%m-%d").date()
        if is_tracing: log_detail(f"[{symbol}] 步骤3: 获取最新交易日数据。日期: {data['latest_date_str']}, 价格: {data['latest_price']}, 成交量: {data['latest_volume']}")

        data['pe_ratio'] = None
        data['market_cap'] = None

        if market_cap_exists:
            try:
                cursor.execute("SELECT pe_ratio, market_cap FROM MNSPP WHERE symbol = ?", (symbol,))
                row = cursor.fetchone()
                if row:
                    data['pe_ratio'], data['market_cap'] = row[0], row[1]
                if is_tracing: log_detail(f"[{symbol}] 步骤4: 尝试从MNSPP获取PE和市值。查询结果: PE={data['pe_ratio']}, 市值={data['market_cap']}")
            except sqlite3.OperationalError as e:
                if "no such column: market_cap" in str(e):
                    if i == 0: print(f"警告: MNSPP表中未找到 'market_cap' 列。将回退到仅查询 'pe_ratio'。")
                    market_cap_exists = False
                    cursor.execute("SELECT pe_ratio FROM MNSPP WHERE symbol = ?", (symbol,))
                    row = cursor.fetchone()
                    if row: data['pe_ratio'] = row[0]
                    if is_tracing: log_detail(f"[{symbol}] 步骤4 (回退): 'market_cap'列不存在。查询PE。结果: PE={data['pe_ratio']}")
                else:
                    print(f"警告: 查询MNSPP表时发生意外错误 for {symbol}: {e}")
        else:
            cursor.execute("SELECT pe_ratio FROM MNSPP WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            if row: data['pe_ratio'] = row[0]
            if is_tracing: log_detail(f"[{symbol}] 步骤4 (已知列不存在): 查询PE。结果: PE={data['pe_ratio']}")

        cursor.execute("SELECT price FROM Earning WHERE name = ? AND date = ?", (symbol, data['latest_er_date_str']))
        row = cursor.fetchone()
        data['earning_record_price'] = row[0] if row else None
        if is_tracing: log_detail(f"[{symbol}] 步骤5: 从Earning表获取最新财报记录的价格。结果: {data['earning_record_price']}")
        
        data['is_valid'] = True
        cache[symbol] = data
        if is_tracing: log_detail(f"[{symbol}] 成功: 数据缓存构建完成，标记为有效。")

    conn.close()
    print(f"--- 数据缓存构建完成，有效数据: {len(cache)} 个 ---")
    return cache

# --- 5. 策略模块 (每个策略都是独立的函数) ---

def run_strategy_1(data, symbol_to_trace, log_detail):
    """策略 1：最新收盘价比过去N次财报的最低值还低至少4%"""
    if data.get('symbol') == symbol_to_trace:
        log_detail(f"\n--- [{symbol_to_trace}] 策略 1 评估 ---")
        prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
        min_price = min(prices)
        threshold_price = min_price * (1 - CONFIG["MIN_DROP_PERCENTAGE"])
        result = data['latest_price'] < threshold_price
        log_detail(f"  - 条件: latest_price ({data['latest_price']}) < min(过去{CONFIG['NUM_EARNINGS_TO_CHECK']}次财报价: {prices}) ({min_price}) * {1 - CONFIG['MIN_DROP_PERCENTAGE']} ({threshold_price:.4f})")
        log_detail(f"  - 结果: {result}")
        return result
    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    threshold = 1 - CONFIG["MIN_DROP_PERCENTAGE"]
    return data['latest_price'] < min(prices) * threshold

def run_strategy_2(data, symbol_to_trace, log_detail):
    """策略 2：过去N次财报收盘都是上升，且最新收盘价比（N次财报收盘价的最高值）低4%，且最近一次的财报日期要和最新收盘价日期间隔不少于7天"""
    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices = list(reversed(prices))
    is_increasing = all(asc_prices[i] < asc_prices[i+1] for i in range(len(asc_prices)-1))
    days_since_er = (data['latest_date'] - data['latest_er_date']).days
    is_date_ok = days_since_er >= 7
    max_price = max(prices)
    threshold_price = max_price * (1 - CONFIG["MIN_DROP_PERCENTAGE"])
    is_price_ok = data['latest_price'] < threshold_price
    
    if data.get('symbol') == symbol_to_trace:
        log_detail(f"\n--- [{symbol_to_trace}] 策略 2 评估 ---")
        log_detail(f"  - 财报价格 (从远到近): {asc_prices}")
        log_detail(f"  - 条件1 (递增): {is_increasing}")
        log_detail(f"  - 条件2 (时间间隔): latest_date ({data['latest_date']}) - latest_er_date ({data['latest_er_date']}) = {days_since_er}天 >= 7天 -> {is_date_ok}")
        log_detail(f"  - 条件3 (价格低于最高): latest_price ({data['latest_price']}) < max({prices}) ({max_price}) * {1-CONFIG['MIN_DROP_PERCENTAGE']} ({threshold_price:.4f}) -> {is_price_ok}")
        log_detail(f"  - 最终结果: {is_increasing and is_date_ok and is_price_ok}")

    return is_increasing and is_date_ok and is_price_ok

def run_strategy_2_5(data, symbol_to_trace, log_detail):
    """策略 2.5 过去N次财报保持上升，且最近的3次财报里至少有一次财报的收盘价要比该symbol的最新收盘价高7%以上，且最近一次的财报日期要和最新收盘价日期间隔不少于7天"""
    if len(data['all_er_prices']) < 3 or any(p is None for p in data['all_er_prices'][:3]):
        return False
    
    prices_n = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices_n = list(reversed(prices_n))
    is_increasing = all(asc_prices_n[i] < asc_prices_n[i+1] for i in range(len(asc_prices_n)-1))
    prices_3 = data['all_er_prices'][:3]
    price_threshold = data['latest_price'] * (1 + CONFIG["RISE_DROP_PERCENTAGE"])
    any_high = any(p > price_threshold for p in prices_3)
    days_since_er = (data['latest_date'] - data['latest_er_date']).days
    is_date_ok = days_since_er >= 7

    if data.get('symbol') == symbol_to_trace:
        log_detail(f"\n--- [{symbol_to_trace}] 策略 2.5 评估 ---")
        log_detail(f"  - {CONFIG['NUM_EARNINGS_TO_CHECK']}次财报价格 (从远到近): {asc_prices_n}")
        log_detail(f"  - 条件1 (递增): {is_increasing}")
        log_detail(f"  - 3次财报价格: {prices_3}")
        log_detail(f"  - 条件2 (任一价比最新价高7%): any(p > {data['latest_price']} * {1+CONFIG['RISE_DROP_PERCENTAGE']} = {price_threshold:.4f}) -> {any_high}")
        log_detail(f"  - 条件3 (时间间隔): {days_since_er}天 >= 7天 -> {is_date_ok}")
        log_detail(f"  - 最终结果: {is_increasing and any_high and is_date_ok}")

    return is_increasing and any_high and is_date_ok

def run_strategy_3(data, symbol_to_trace, log_detail):
    """ 策略 3 """
    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices = list(reversed(prices))
    
    next_er = get_next_er_date(data['latest_er_date'])
    window_start = next_er - datetime.timedelta(days=20)
    window_end = next_er - datetime.timedelta(days=7)
    is_in_window = (window_start <= data['latest_date'] <= window_end)
    
    is_increasing = asc_prices[-2] < asc_prices[-1]
    price_ok = False
    
    if is_increasing:
        price_ok = data['latest_price'] < max(asc_prices) * (1 - CONFIG["RISE_DROP_PERCENTAGE"])
    else:
        diff = abs(asc_prices[-1] - asc_prices[-2])
        diff_pct_ok = diff >= asc_prices[-2] * CONFIG["MIN_DROP_PERCENTAGE"]
        price_low_ok = data['latest_price'] < min(prices)
        price_ok = diff_pct_ok and price_low_ok

    if data.get('symbol') == symbol_to_trace:
        log_detail(f"\n--- [{symbol_to_trace}] 策略 3 评估 ---")
        log_detail(f"  - 最新财报日: {data['latest_er_date']}, 理论下次财报日: {next_er}")
        log_detail(f"  - 时间窗口: {window_start} <= 最新交易日({data['latest_date']}) <= {window_end}")
        log_detail(f"  - 条件1 (在时间窗口内): {is_in_window}")
        if not is_in_window:
            log_detail(f"  - 结果: False (未在时间窗口内)")
            return False
        
        log_detail(f"  - 最近两次财报价 (从远到近): {[asc_prices[-2], asc_prices[-1]]}")
        log_detail(f"  - 条件2 (最近两次财报上升): {is_increasing}")
        if is_increasing:
            max_p = max(asc_prices)
            threshold = max_p * (1 - CONFIG["RISE_DROP_PERCENTAGE"])
            log_detail(f"    - 分支(上升): latest_price({data['latest_price']}) < max({asc_prices})({max_p}) * {1-CONFIG['RISE_DROP_PERCENTAGE']} ({threshold:.4f}) -> {price_ok}")
        else:
            diff = abs(asc_prices[-1] - asc_prices[-2])
            min_diff = asc_prices[-2] * CONFIG["MIN_DROP_PERCENTAGE"]
            diff_pct_ok = diff >= min_diff
            price_low_ok = data['latest_price'] < min(prices)
            log_detail(f"    - 分支(非上升):")
            log_detail(f"      - 差额检查: abs({asc_prices[-1]} - {asc_prices[-2]}) ({diff:.4f}) >= {asc_prices[-2]} * {CONFIG['MIN_DROP_PERCENTAGE']} ({min_diff:.4f}) -> {diff_pct_ok}")
            log_detail(f"      - 低价检查: latest_price({data['latest_price']}) < min({prices}) ({min(prices)}) -> {price_low_ok}")
            log_detail(f"      - 分支结果: {price_ok}")
        log_detail(f"  - 最终结果: {is_in_window and price_ok}")

    return is_in_window and price_ok

def run_strategy_3_5(data, symbol_to_trace, log_detail):
    """策略 3.5"""
    if len(data['all_er_prices']) < 3 or any(p is None for p in data['all_er_prices'][:3]):
        return False

    next_er = get_next_er_date(data['latest_er_date'])
    window_start = next_er - datetime.timedelta(days=20)
    window_end = next_er - datetime.timedelta(days=7)
    is_in_window = (window_start <= data['latest_date'] <= window_end)
    
    prices_n = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices_n = list(reversed(prices_n))
    is_increasing = asc_prices_n[-2] < asc_prices_n[-1]
    prices_3 = data['all_er_prices'][:3]
    price_threshold = data['latest_price'] * (1 + CONFIG["MAX_DROP_PERCENTAGE"])
    any_high = any(p > price_threshold for p in prices_3)

    if data.get('symbol') == symbol_to_trace:
        log_detail(f"\n--- [{symbol_to_trace}] 策略 3.5 评估 ---")
        log_detail(f"  - 最新财报日: {data['latest_er_date']}, 理论下次财报日: {next_er}")
        log_detail(f"  - 时间窗口: {window_start} <= 最新交易日({data['latest_date']}) <= {window_end}")
        log_detail(f"  - 条件1 (在时间窗口内): {is_in_window}")
        log_detail(f"  - 最近两次财报价 (从远到近): {[asc_prices_n[-2], asc_prices_n[-1]]}")
        log_detail(f"  - 条件2 (最近两次财报上升): {is_increasing}")
        log_detail(f"  - 最近三次财报价: {prices_3}")
        log_detail(f"  - 条件3 (任一价比最新价高7%): any(p > {data['latest_price']} * {1+CONFIG['MAX_DROP_PERCENTAGE']} = {price_threshold:.4f}) -> {any_high}")
        log_detail(f"  - 最终结果: {is_in_window and is_increasing and any_high}")

    return is_in_window and is_increasing and any_high

def run_strategy_4(data, cursor, symbol_sector_map, symbol_to_trace, log_detail):
    """ 策略 4 """
    is_tracing = (data.get('symbol') == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol_to_trace}] 策略 4 评估 ---")

    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices = list(reversed(prices))
    is_increasing = all(asc_prices[i] < asc_prices[i+1] for i in range(len(asc_prices)-1))
    is_recent_er = data['latest_er_date'] >= (datetime.date.today() - datetime.timedelta(days=30))
    is_positive_earning = data['earning_record_price'] is not None and data['earning_record_price'] > 0
    
    if is_tracing:
        log_detail(f"  - 财报价格 (从远到近): {asc_prices}")
        log_detail(f"  - 条件1.1 (递增): {is_increasing}")
        log_detail(f"  - 条件1.2 (最近30天财报): {data['latest_er_date']} >= {datetime.date.today() - datetime.timedelta(days=30)} -> {is_recent_er}")
        log_detail(f"  - 条件1.3 (Earning表price>0): {data['earning_record_price']} > 0 -> {is_positive_earning}")

    if not (is_increasing and is_recent_er and is_positive_earning):
        if is_tracing: log_detail(f"  - 结果: False (基础条件未满足)")
        return False

    window_start = data['latest_er_date'] + datetime.timedelta(days=5)
    window_end = data['latest_er_date'] + datetime.timedelta(days=12)
    is_in_window = (window_start <= data['latest_date'] <= window_end)
    if is_tracing:
        log_detail(f"  - 时间窗口: {window_start} <= 最新交易日({data['latest_date']}) <= {window_end}")
        log_detail(f"  - 条件2 (在时间窗口内): {is_in_window}")
    
    if not is_in_window:
        if is_tracing: log_detail(f"  - 结果: False (未在时间窗口内)")
        return False
        
    second_er_price = data['all_er_prices'][1]
    if second_er_price is None: 
        if is_tracing: log_detail(f"  - 结果: False (倒数第二次财报价格缺失)")
        return False
    
    cond_B = data['latest_price'] < second_er_price
    if is_tracing: log_detail(f"  - 条件B: latest_price({data['latest_price']}) < 倒数第二次财报价({second_er_price}) -> {cond_B}")
    if cond_B: 
        if is_tracing: log_detail(f"  - 结果: True (满足条件B)")
        return True

    table_name = symbol_sector_map.get(data['symbol'])
    start_range = data['latest_er_date'] - datetime.timedelta(days=2)
    end_range   = data['latest_er_date'] + datetime.timedelta(days=2)
    cursor.execute(
        f'SELECT MAX(price) FROM "{table_name}" WHERE name = ? AND date BETWEEN ? AND ?',
        (data['symbol'], start_range.isoformat(), end_range.isoformat())
    )
    max_price_row = cursor.fetchone()
    max_price_around_er = max_price_row[0] if max_price_row else None
    
    if max_price_around_er is None: 
        if is_tracing: log_detail(f"  - 结果: False (无法获取财报日前后最高价)")
        return False

    mcap = data['market_cap']
    drop_pct = CONFIG["MIN_DROP_PERCENTAGE"] if mcap and mcap >= CONFIG["MARKETCAP_THRESHOLD"] else CONFIG["RISE_DROP_PERCENTAGE"]
    threshold_price = max_price_around_er * (1 - drop_pct)
    cond_A = data['latest_price'] < threshold_price
    
    if is_tracing:
        log_detail(f"  - 条件A:")
        log_detail(f"    - 市值: {mcap}, 阈值: {CONFIG['MARKETCAP_THRESHOLD']} -> 使用下跌百分比: {drop_pct}")
        log_detail(f"    - 财报日前后最高价: {max_price_around_er}")
        log_detail(f"    - 判断: latest_price({data['latest_price']}) < {max_price_around_er} * (1-{drop_pct}) ({threshold_price:.4f}) -> {cond_A}")
        log_detail(f"  - 最终结果: {cond_A}")

    return cond_A

# --- 6. 过滤模块 ---

def filter_recent_negative_earnings(db_path):
    """高效获取最近30天内有负财报的symbols集合"""
    one_month_ago = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT name FROM Earning WHERE date >= ? AND price < 0",
        (one_month_ago,)
    )
    symbols = {row[0] for row in cursor.fetchall()}
    conn.close()
    print(f"\n过滤条件: 找到 {len(symbols)} 个最近有负财报的 symbol。")
    return symbols

def apply_filters(symbols_set, stock_data_cache, blacklist, negative_earnings_set, is_main_list, symbol_to_trace, log_detail):
    """对给定的symbol集合应用一系列过滤规则"""
    final_list = []
    for symbol in sorted(list(symbols_set)):
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n{'='*20} 开始对目标 {symbol} 进行过滤 {'='*20}")

        if symbol not in stock_data_cache or not stock_data_cache[symbol]['is_valid']:
            if is_tracing: log_detail(f"[{symbol}] 过滤: 因为在数据缓存中无效或不存在。")
            continue
        
        data = stock_data_cache[symbol]

        if symbol in blacklist:
            if is_tracing: log_detail(f"[{symbol}] 过滤(黑名单): symbol在黑名单中。")
            continue
        elif is_tracing: log_detail(f"[{symbol}] 通过(黑名单): symbol不在黑名单中。")

        if is_main_list and symbol in negative_earnings_set:
            if is_tracing: log_detail(f"[{symbol}] 过滤(主列表-负财报): symbol在最近负财报集合中。")
            continue
        elif is_tracing and is_main_list: log_detail(f"[{symbol}] 通过(主列表-负财报): symbol不在最近负财报集合中。")

        turnover = data['latest_price'] * data['latest_volume']
        if turnover < CONFIG["MIN_TURNOVER"]:
            if is_tracing: log_detail(f"[{symbol}] 过滤(成交额): {turnover:,.0f} < {CONFIG['MIN_TURNOVER']:,}")
            continue
        elif is_tracing: log_detail(f"[{symbol}] 通过(成交额): {turnover:,.0f} >= {CONFIG['MIN_TURNOVER']:,}")

        pe = data['pe_ratio']
        if pe is None or str(pe).strip().lower() in ("--", "null", ""):
            if is_tracing: log_detail(f"[{symbol}] 过滤(PE无效): PE值为 '{pe}'。")
            continue
        elif is_tracing: log_detail(f"[{symbol}] 通过(PE有效): PE值为 '{pe}'。")

        if data['latest_date_str'] == data['latest_er_date_str']:
            if is_tracing: log_detail(f"[{symbol}] 过滤(日期相同): 最新交易日({data['latest_date_str']}) 与 最新财报日({data['latest_er_date_str']}) 相同。")
            continue
        elif is_tracing: log_detail(f"[{symbol}] 通过(日期不同)。")
            
        final_list.append(symbol)
        if is_tracing: log_detail(f"[{symbol}] 成功: 通过所有过滤器，已添加到最终列表。")
        
    return final_list


# --- 7. 主执行流程 ---

def main():
    """主程序入口"""
    # 使用 with 语句确保日志文件被正确关闭
    with open(LOG_FILE_PATH, 'w', encoding='utf-8') as log_file:
        
        def log_detail(message):
            """一个辅助函数，用于将调试信息写入文件并打印到控制台"""
            log_file.write(message + '\n')
            print(message) # 也在控制台打印，方便实时查看

        log_detail(f"程序开始运行... 日志将写入: {LOG_FILE_PATH}")
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")
        
        # 1. 加载初始数据
        symbol_sector_map = create_symbol_to_sector_map(SECTORS_JSON_FILE)
        if not symbol_sector_map:
            print("错误: 无法加载板块映射，程序终止。")
            return

        symbols_next = get_symbols_from_file(PATHS["earnings_release_next"](news_path))
        symbols_new = get_symbols_from_file(PATHS["earnings_release_new"](news_path))
        initial_symbols = list(dict.fromkeys(symbols_next + symbols_new))

        if SYMBOL_TO_TRACE in initial_symbols:
            log_detail(f"\n追踪信息: {SYMBOL_TO_TRACE} 在初始文件列表中。")
        else:
            log_detail(f"\n追踪信息: {SYMBOL_TO_TRACE} 不在初始文件列表中 (next/new)。")

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT name FROM Earning")
            all_db_symbols = [row[0] for row in cursor.fetchall()]

        symbols_to_process = sorted(list(set(initial_symbols + all_db_symbols)))
        
        # 2. 构建数据缓存 (核心性能提升)
        stock_data_cache = build_stock_data_cache(symbols_to_process, DB_FILE, symbol_sector_map, SYMBOL_TO_TRACE, log_detail)

        # 3. 运行策略
        results = defaultdict(list)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            for symbol, data in stock_data_cache.items():
                if not data['is_valid']:
                    continue
                
                data['symbol'] = symbol

                if symbol in initial_symbols:
                    if run_strategy_1(data, SYMBOL_TO_TRACE, log_detail): results['s1'].append(symbol)
                    if run_strategy_2(data, SYMBOL_TO_TRACE, log_detail): results['s2'].append(symbol)
                    if run_strategy_2_5(data, SYMBOL_TO_TRACE, log_detail): results['s2_5'].append(symbol)

                if run_strategy_3(data, SYMBOL_TO_TRACE, log_detail): results['s3'].append(symbol)
                if run_strategy_3_5(data, SYMBOL_TO_TRACE, log_detail): results['s3_5'].append(symbol)
                if run_strategy_4(data, cursor, symbol_sector_map, SYMBOL_TO_TRACE, log_detail): results['s4'].append(symbol)

        # 4. 汇总初步结果
        prelim_final_symbols = set(results['s1'] + results['s2'] + results['s2_5'])
        prelim_notification_list = set(results['s3'] + results['s3_5'] + results['s4'])

        print("\n--- 策略运行初步结果 ---")
        print(f"主列表初步候选: {len(prelim_final_symbols)} 个")
        print(f"通知列表初步候选: {len(prelim_notification_list)} 个")
        if SYMBOL_TO_TRACE in prelim_final_symbols:
            log_detail(f"\n追踪信息: {SYMBOL_TO_TRACE} 在策略筛选后的 '主列表' 初步候选名单中。")
        if SYMBOL_TO_TRACE in prelim_notification_list:
            log_detail(f"\n追踪信息: {SYMBOL_TO_TRACE} 在策略筛选后的 '通知列表' 初步候选名单中。")


        # 5. 应用通用过滤器
        blacklist = load_blacklist(BLACKLIST_JSON_FILE)
        negative_earnings_set = filter_recent_negative_earnings(DB_FILE)

        print("\n--- 开始对主列表进行过滤 ---")
        final_symbols = apply_filters(prelim_final_symbols, stock_data_cache, blacklist, negative_earnings_set, True, SYMBOL_TO_TRACE, log_detail)
        
        print("\n--- 开始对通知列表进行过滤 ---")
        final_notification_list = apply_filters(prelim_notification_list, stock_data_cache, blacklist, set(), False, SYMBOL_TO_TRACE, log_detail)

        print("\n--- 所有过滤完成后的最终结果 ---")
        print(f"主列表最终数量: {len(final_symbols)} - {final_symbols}")
        print(f"通知列表最终数量: {len(final_notification_list)} - {final_notification_list}")
        if SYMBOL_TO_TRACE in final_symbols:
            log_detail(f"\n最终追踪结果: {SYMBOL_TO_TRACE} 成功进入了最终的 '主列表'。")
        if SYMBOL_TO_TRACE in final_notification_list:
            log_detail(f"\n最终追踪结果: {SYMBOL_TO_TRACE} 成功进入了最终的 '通知列表'。")


        # 6. 文件和JSON输出
        update_json_panel(final_symbols, PANEL_JSON_FILE, "Next_Week")
        # try:
        #     output_path = PATHS["output_next_week"](news_path)
        #     backup_path = PATHS["backup_next_week"](news_path)
        #     os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            
        #     with open(output_path, 'w', encoding='utf-8') as f:
        #         for sym in sorted(final_symbols):
        #             f.write(sym + '\n')
        #     print(f"主列表结果已写入: {output_path}")

        #     with open(backup_path, 'w', encoding='utf-8') as f:
        #         for sym in sorted(final_symbols):
        #             f.write(sym + '\n')
        #     print(f"主列表备份已更新: {backup_path}")

        # except IOError as e:
        #     print(f"写入主列表文件时出错: {e}")

        update_json_panel(final_notification_list, PANEL_JSON_FILE, "Notification")
        # try:
        #     output_path = PATHS["output_notification"](news_path)
        #     backup_path = PATHS["backup_notification"](news_path)
        #     os.makedirs(os.path.dirname(backup_path), exist_ok=True)

        #     with open(output_path, 'w', encoding='utf-8') as f:
        #         for sym in sorted(final_notification_list):
        #             f.write(sym + '\n')
        #     print(f"通知列表结果已写入: {output_path}")

        #     with open(backup_path, 'w', encoding='utf-8') as f:
        #         for sym in sorted(final_notification_list):
        #             f.write(sym + '\n')
        #     print(f"通知列表备份已更新: {backup_path}")

        # except IOError as e:
        #     print(f"写入通知列表文件时出错: {e}")

    print("\n程序运行结束。")


if __name__ == "__main__":
    main()