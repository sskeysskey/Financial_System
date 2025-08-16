import sqlite3
import json
import os
import datetime
from collections import defaultdict

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
    "backup_next_week": lambda news: os.path.join(news, "backup", "NextWeek_Earning.txt"),
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

def build_stock_data_cache(symbols, db_path, symbol_sector_map):
    """
    为所有给定的symbols一次性从数据库加载所有需要的数据。
    这是性能优化的核心，避免了重复查询。
    """
    print(f"\n--- 开始为 {len(symbols)} 个 symbol 构建数据缓存 ---")
    cache = {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查market_cap列是否存在的标志
    market_cap_exists = True

    for i, symbol in enumerate(symbols):
        data = {'is_valid': False} # 默认数据无效
        table_name = symbol_sector_map.get(symbol)
        if not table_name:
            continue

        # 1. 获取最近 N+1 次财报 (多取一次用于策略2.5/3.5)
        cursor.execute(
            "SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT ?",
            (symbol, CONFIG["NUM_EARNINGS_TO_CHECK"] + 1)
        )
        earnings_dates = [r[0] for r in cursor.fetchall()]
        if len(earnings_dates) < CONFIG["NUM_EARNINGS_TO_CHECK"]:
            continue

        data['all_er_dates'] = earnings_dates
        data['latest_er_date_str'] = earnings_dates[0]
        data['latest_er_date'] = datetime.datetime.strptime(earnings_dates[0], "%Y-%m-%d").date()

        # 2. 获取这些财报日的收盘价
        er_prices = []
        prices_valid = True
        for date_str in earnings_dates:
            cursor.execute(f'SELECT price FROM "{table_name}" WHERE name = ? AND date = ?', (symbol, date_str))
            price_result = cursor.fetchone()
            if price_result and price_result[0] is not None:
                er_prices.append(price_result[0])
            else:
                # 关键财报日价格缺失，但为了保持长度一致，先用None填充
                er_prices.append(None)
        
        # 检查关键的前N次财报价格是否存在
        if any(p is None for p in er_prices[:CONFIG["NUM_EARNINGS_TO_CHECK"]]):
            continue

        data['all_er_prices'] = er_prices
        
        # 3. 获取最新交易日数据
        cursor.execute(f'SELECT date, price, volume FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1', (symbol,))
        latest_row = cursor.fetchone()
        if not latest_row or latest_row[1] is None or latest_row[2] is None:
            continue
            
        data['latest_date_str'], data['latest_price'], data['latest_volume'] = latest_row
        data['latest_date'] = datetime.datetime.strptime(data['latest_date_str'], "%Y-%m-%d").date()

        # 4. 获取其他所需数据 (PE, MarketCap, Earning表price)
        # ########################## MODIFICATION START ##########################
        # 此处为核心修改，处理 market_cap 列不存在的错误
        
        data['pe_ratio'] = None
        data['market_cap'] = None

        if market_cap_exists: # 如果列存在，尝试最优查询
            try:
                cursor.execute("SELECT pe_ratio, market_cap FROM MNSPP WHERE symbol = ?", (symbol,))
                row = cursor.fetchone()
                if row:
                    data['pe_ratio'] = row[0]
                    data['market_cap'] = row[1]
            except sqlite3.OperationalError as e:
                if "no such column: market_cap" in str(e):
                    if i == 0: # 只在第一次遇到错误时打印警告
                        print(f"警告: MNSPP表中未找到 'market_cap' 列。将回退到仅查询 'pe_ratio'。")
                    market_cap_exists = False # 标记列不存在，后续循环不再尝试
                    # 执行回退查询
                    cursor.execute("SELECT pe_ratio FROM MNSPP WHERE symbol = ?", (symbol,))
                    row = cursor.fetchone()
                    if row:
                        data['pe_ratio'] = row[0]
                else:
                    # 其他数据库错误
                    print(f"警告: 查询MNSPP表时发生意外错误 for {symbol}: {e}")
        else: # 如果已经知道列不存在，直接使用回退查询
            cursor.execute("SELECT pe_ratio FROM MNSPP WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            if row:
                data['pe_ratio'] = row[0]

        # ########################### MODIFICATION END ###########################

        cursor.execute("SELECT price FROM Earning WHERE name = ? AND date = ?", (symbol, data['latest_er_date_str']))
        row = cursor.fetchone()
        data['earning_record_price'] = row[0] if row else None
        
        # 5. 如果所有关键数据都获取成功，则标记为有效
        data['is_valid'] = True
        cache[symbol] = data

    conn.close()
    print(f"--- 数据缓存构建完成，有效数据: {len(cache)} 个 ---")
    return cache

# --- 5. 策略模块 (每个策略都是独立的函数) ---

def run_strategy_1(data):
    """策略 1：最新收盘价比过去N次财报的最低值还低至少4%"""
    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    threshold = 1 - CONFIG["RISE_DROP_PERCENTAGE"]
    return data['latest_price'] < min(prices) * threshold

def run_strategy_2(data):
    """策略 2：过去N次财报收盘都是上升，且最新收盘价比（N次财报收盘价的最高值）低4%，且最近一次的财报日期要和最新收盘价日期间隔不少于7天"""
    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices = list(reversed(prices))
    is_increasing = all(asc_prices[i] < asc_prices[i+1] for i in range(len(asc_prices)-1))
    
    days_since_er = (data['latest_date'] - data['latest_er_date']).days
    is_date_ok = days_since_er >= 7
    
    threshold = 1 - CONFIG["MIN_DROP_PERCENTAGE"]
    is_price_ok = data['latest_price'] < max(prices) * threshold
    
    return is_increasing and is_date_ok and is_price_ok

def run_strategy_2_5(data):
    """策略 2.5 过去N次财报保持上升，且最近的3次财报里至少有一次财报的收盘价要比该symbol的最新收盘价高7%以上，且最近一次的财报日期要和最新收盘价日期间隔不少于7天"""
    # 确保有足够的数据点
    if len(data['all_er_prices']) < 3 or any(p is None for p in data['all_er_prices'][:3]):
        return False
    
    # 检查N次递增
    prices_n = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices_n = list(reversed(prices_n))
    is_increasing = all(asc_prices_n[i] < asc_prices_n[i+1] for i in range(len(asc_prices_n)-1))

    # 检查3次财报价格
    prices_3 = data['all_er_prices'][:3]
    any_high = any(p > data['latest_price'] * (1 + CONFIG["RISE_DROP_PERCENTAGE"]) for p in prices_3)
    
    days_since_er = (data['latest_date'] - data['latest_er_date']).days
    is_date_ok = days_since_er >= 7

    return is_increasing and any_high and is_date_ok

def run_strategy_3(data):
    """ 策略 3（1）：如果最近2次财报是上升的，且最新收盘价比过去N次财报最高收盘价低7% """
    """ 策略 3（2）：如果不是上升的，要求最近2次财报收盘价差额要大于等于4%，最新收盘价 < 过去N次财报最低收盘价 """
    """ 策略 3（3）：以上两个结果还同时必须满足最新交易日落在下次理论(最近一次财报日期+93天)财报之前的7~20天窗口期内 """
    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices = list(reversed(prices))
    
    # 时间窗口检查
    next_er = get_next_er_date(data['latest_er_date'])
    window_start = next_er - datetime.timedelta(days=20)
    window_end = next_er - datetime.timedelta(days=7)
    if not (window_start <= data['latest_date'] <= window_end):
        return False
        
    price_ok = False
    # 最新两次财报比较
    if asc_prices[-2] < asc_prices[-1]: # 上升
        price_ok = data['latest_price'] < max(asc_prices) * (1 - CONFIG["RISE_DROP_PERCENTAGE"])
    else: # 非升序
        diff = abs(asc_prices[-1] - asc_prices[-2])
        price_ok = (diff >= asc_prices[-2] * CONFIG["MIN_DROP_PERCENTAGE"] and 
                    data['latest_price'] < min(prices))
    
    return price_ok

def run_strategy_3_5(data):
    """策略 3.5: 过去2次财报保持上升，且最近的3次财报里至少有一次财报的收盘价要比该symbol的最新收盘价高7%以上，且最新交易日落在下次理论(最近一次财报日期+93天)财报之前的7~20天窗口期内"""
    if len(data['all_er_prices']) < 3 or any(p is None for p in data['all_er_prices'][:3]):
        return False

    # 时间窗口检查
    next_er = get_next_er_date(data['latest_er_date'])
    window_start = next_er - datetime.timedelta(days=20)
    window_end = next_er - datetime.timedelta(days=7)
    if not (window_start <= data['latest_date'] <= window_end):
        return False
        
    # 价格条件检查
    prices_n = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices_n = list(reversed(prices_n))
    is_increasing = asc_prices_n[-2] < asc_prices_n[-1] # 只比较最近两次

    prices_3 = data['all_er_prices'][:3]
    any_high = any(p > data['latest_price'] * (1 + CONFIG["RISE_DROP_PERCENTAGE"]) for p in prices_3)

    return is_increasing and any_high

def run_strategy_4(data, cursor, symbol_sector_map):
    """ 策略 4（1）：最近N次财报的收盘价要递增，最近一次财报必须是从系统日期往前数一个月内，且该symbol从earning表中读到的price值必须为正 """
    """ 策略 4（2）：最新收盘价位于最近财报日后9-25天之间，且A：最新收盘价比最新财报日前后(±2天内)的最高收盘价低超过X%（如果股票symbol的marketcap是1000亿以上时X就是4%，如果股票symbol的marketcap是1000亿以下时X就是7%），B：或者不管marketcap是多少，只要最新收盘价低于倒数第二次财报的收盘价时也算符合要求，A、B是或的关系 """
    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices = list(reversed(prices))
    
    # 基本条件
    is_increasing = all(asc_prices[i] < asc_prices[i+1] for i in range(len(asc_prices)-1))
    is_recent_er = data['latest_er_date'] >= (datetime.date.today() - datetime.timedelta(days=30))
    is_positive_earning = data['earning_record_price'] is not None and data['earning_record_price'] > 0
    
    if not (is_increasing and is_recent_er and is_positive_earning):
        return False

    # 日期窗口
    window_start = data['latest_er_date'] + datetime.timedelta(days=9)
    window_end = data['latest_er_date'] + datetime.timedelta(days=25)
    if not (window_start <= data['latest_date'] <= window_end):
        return False
        
    # A/B 条件判断
    # B条件
    second_er_price = data['all_er_prices'][1]
    if second_er_price is None: return False # 需要倒数第二次财报价格
    
    cond_B = data['latest_price'] < second_er_price
    if cond_B: return True # B满足则直接通过

    # A条件
    table_name = symbol_sector_map.get(data['symbol'])
    start_range = data['latest_er_date'] - datetime.timedelta(days=2)
    end_range   = data['latest_er_date'] + datetime.timedelta(days=2)
    cursor.execute(
        f'SELECT MAX(price) FROM "{table_name}" WHERE name = ? AND date BETWEEN ? AND ?',
        (data['symbol'], start_range.isoformat(), end_range.isoformat())
    )
    max_price_row = cursor.fetchone()
    max_price_around_er = max_price_row[0] if max_price_row else None
    
    if max_price_around_er is None: return False

    mcap = data['market_cap']
    drop_pct = CONFIG["MIN_DROP_PERCENTAGE"] if mcap and mcap >= CONFIG["MARKETCAP_THRESHOLD"] else CONFIG["RISE_DROP_PERCENTAGE"]
    cond_A = data['latest_price'] < max_price_around_er * (1 - drop_pct)
    
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

def apply_filters(symbols_set, stock_data_cache, blacklist, negative_earnings_set, is_main_list=False):
    """对给定的symbol集合应用一系列过滤规则"""
    final_list = []
    for symbol in sorted(list(symbols_set)):
        if symbol not in stock_data_cache or not stock_data_cache[symbol]['is_valid']:
            continue
        
        data = stock_data_cache[symbol]

        # 过滤1: 黑名单
        if symbol in blacklist:
            continue
            
        # 过滤2: 最近负财报 (仅用于主列表)
        if is_main_list and symbol in negative_earnings_set:
            print(f"  - 过滤 (主列表-负财报): {symbol}")
            continue

        # 过滤3: 成交额
        turnover = data['latest_price'] * data['latest_volume']
        if turnover < CONFIG["MIN_TURNOVER"]:
            # print(f"  - 过滤 (成交额不足): {symbol} (成交额: {turnover:,.0f})")
            continue
            
        # 过滤4: PE Ratio
        pe = data['pe_ratio']
        if pe is None or str(pe).strip().lower() in ("--", "null", ""):
            # print(f"  - 过滤 (PE无效): {symbol} (PE: {pe})")
            continue

        # 过滤5: 最新交易日 == 最新财报日
        if data['latest_date_str'] == data['latest_er_date_str']:
            # print(f"  - 过滤 (日期相同): {symbol}")
            continue
            
        final_list.append(symbol)
        
    return final_list


# --- 7. 主执行流程 ---

def main():
    """主程序入口"""
    print("程序开始运行...")
    
    # 1. 加载初始数据
    symbol_sector_map = create_symbol_to_sector_map(SECTORS_JSON_FILE)
    if not symbol_sector_map:
        print("错误: 无法加载板块映射，程序终止。")
        return

    symbols_next = get_symbols_from_file(PATHS["earnings_release_next"](news_path))
    symbols_new = get_symbols_from_file(PATHS["earnings_release_new"](news_path))
    initial_symbols = list(dict.fromkeys(symbols_next + symbols_new))

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT name FROM Earning")
        all_db_symbols = [row[0] for row in cursor.fetchall()]

    symbols_to_process = sorted(list(set(initial_symbols + all_db_symbols)))
    
    # 2. 构建数据缓存 (核心性能提升)
    stock_data_cache = build_stock_data_cache(symbols_to_process, DB_FILE, symbol_sector_map)

    # 3. 运行策略
    results = defaultdict(list)
    with sqlite3.connect(DB_FILE) as conn: # 策略4需要一个cursor
        cursor = conn.cursor()

        for symbol, data in stock_data_cache.items():
            if not data['is_valid']:
                continue
            
            data['symbol'] = symbol # 将symbol本身加入data，方便策略4使用

            # 跑主列表策略 (仅针对初始文件里的symbols)
            if symbol in initial_symbols:
                if run_strategy_1(data): results['s1'].append(symbol)
                if run_strategy_2(data): results['s2'].append(symbol)
                if run_strategy_2_5(data): results['s2_5'].append(symbol)

            # 跑通知列表策略 (针对所有有数据的symbols)
            if run_strategy_3(data): results['s3'].append(symbol)
            if run_strategy_3_5(data): results['s3_5'].append(symbol)
            if run_strategy_4(data, cursor, symbol_sector_map): results['s4'].append(symbol)

    # 4. 汇总初步结果
    prelim_final_symbols = set(results['s1'] + results['s2'] + results['s2_5'])
    prelim_notification_list = set(results['s3'] + results['s3_5'] + results['s4'])

    print("\n--- 策略运行初步结果 ---")
    print(f"主列表初步候选: {len(prelim_final_symbols)} 个")
    print(f"通知列表初步候选: {len(prelim_notification_list)} 个")

    # 5. 应用通用过滤器
    blacklist = load_blacklist(BLACKLIST_JSON_FILE)
    negative_earnings_set = filter_recent_negative_earnings(DB_FILE)

    print("\n--- 开始对主列表进行过滤 ---")
    final_symbols = apply_filters(prelim_final_symbols, stock_data_cache, blacklist, negative_earnings_set, is_main_list=True)
    
    print("\n--- 开始对通知列表进行过滤 ---")
    final_notification_list = apply_filters(prelim_notification_list, stock_data_cache, blacklist, set())

    # 在这里加一行：把出现在主列表里的剔除掉
    final_notification_list = [s for s in final_notification_list if s not in final_symbols]

    print("\n--- 所有过滤完成后的最终结果 ---")
    print(f"主列表最终数量: {len(final_symbols)} - {final_symbols}")
    print(f"通知列表最终数量: {len(final_notification_list)} - {final_notification_list}")

    # 6. 文件和JSON输出
    # 主列表 (NextWeek_Earning)
    update_json_panel(final_symbols, PANEL_JSON_FILE, "Next_Week")
    try:
        backup_path = PATHS["backup_next_week"](news_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)

        with open(backup_path, 'w', encoding='utf-8') as f:
            for sym in sorted(final_symbols):
                f.write(sym + '\n')
        print(f"主列表备份已更新: {backup_path}")

    except IOError as e:
        print(f"写入主列表文件时出错: {e}")

    # 通知列表 (Notification)
    update_json_panel(final_notification_list, PANEL_JSON_FILE, "Notification")
    try:
        backup_path = PATHS["backup_notification"](news_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)

        with open(backup_path, 'w', encoding='utf-8') as f:
            for sym in sorted(final_notification_list):
                f.write(sym + '\n')
        print(f"通知列表备份已更新: {backup_path}")

    except IOError as e:
        print(f"写入通知列表文件时出错: {e}")

    print("\n程序运行结束。")


if __name__ == "__main__":
    main()