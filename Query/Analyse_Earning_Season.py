import sqlite3
import json
import os
import datetime
from collections import defaultdict

SYMBOL_TO_TRACE = ""
LOG_FILE_PATH = "/Users/yanzhang/Downloads/Season_trace_log.txt"

# --- 1. 配置文件和路径 --- 使用一个配置字典来管理所有路径，更清晰
PATHS = {
    "base": "/Users/yanzhang/Coding/",
    "news": lambda base: os.path.join(base, "News"),
    "db": lambda base: os.path.join(base, "Database"),
    "config": lambda base: os.path.join(base, "Financial_System", "Modules"),
    "earnings_release_next": lambda news: os.path.join(news, "Earnings_Release_next.txt"),
    "earnings_release_new": lambda news: os.path.join(news, "Earnings_Release_new.txt"),
    "earnings_release_third": lambda news: os.path.join(news, "Earnings_Release_third.txt"),
    "earnings_release_fourth": lambda news: os.path.join(news, "Earnings_Release_fourth.txt"),
    "earnings_release_fifth": lambda news: os.path.join(news, "Earnings_Release_fifth.txt"),
    "sectors_json": lambda config: os.path.join(config, "Sectors_All.json"),
    "db_file": lambda db: os.path.join(db, "Finance.db"),
    "blacklist_json": lambda config: os.path.join(config, "Blacklist.json"),
    "panel_json": lambda config: os.path.join(config, "Sectors_panel.json"),
    "description_json": lambda config: os.path.join(config, 'description.json'),
    "tags_setting_json": lambda config: os.path.join(config, 'tags_filter.json'),
    "earnings_history_json": lambda config: os.path.join(config, 'Earning_History.json'),
    "backup_Strategy12": lambda news: os.path.join(news, "backup", "NextWeek_Earning.txt"),
    "backup_Strategy34": lambda news: os.path.join(news, "backup", "Strategy34_earning.txt"),
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
DESCRIPTION_JSON_FILE = PATHS["description_json"](config_path)
TAGS_SETTING_JSON_FILE = PATHS["tags_setting_json"](config_path)
# ========== 新增路径变量 ==========
EARNING_HISTORY_JSON_FILE = PATHS["earnings_history_json"](config_path)
# ================================


# --- 2. 可配置参数 --- 使用一个配置字典来管理所有参数
CONFIG = {
    # ========================================
    "NUM_EARNINGS_TO_CHECK": 2,
    "MIN_DROP_PERCENTAGE": 0.03,
    "MINOR_DROP_PERCENTAGE": 0.05,
    "MIDDLE_DROP_PERCENTAGE": 0.07,
    "MIDDLE_PLUS_DROP_PERCENTAGE": 0.08,
    "HIGH_DROP_PERCENTAGE": 0.09,
    "MAX_DROP_PERCENTAGE": 0.15,
    "MIN_TURNOVER": 100_000_000,
    "MARKETCAP_THRESHOLD": 100_000_000_000,
    "MAX_RISE_FROM_7D_LOW": 0.03,
}

# --- 3. 辅助与文件操作模块 ---

# 新增: 用于加载外部标签配置的函数
def load_tag_settings(json_path):
    """从 Tags_Setting.json 加载 BLACKLIST_TAGS 和 HOT_TAGS。"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        # 从JSON加载列表，并转换成set，如果不存在则返回空set
        tag_blacklist = set(settings.get('BLACKLIST_TAGS', []))
        hot_tags = set(settings.get('HOT_TAGS', []))
        
        print(f"成功从 {os.path.basename(json_path)} 加载设置。")
        print(f"  - BLACKLIST_TAGS: {len(tag_blacklist)} 个")
        print(f"  - HOT_TAGS: {len(hot_tags)} 个")
        
        return tag_blacklist, hot_tags
    except FileNotFoundError:
        print(f"警告: 标签配置文件未找到: {json_path}。将使用空的黑名单和热门标签列表。")
        return set(), set()
    except json.JSONDecodeError:
        print(f"警告: 标签配置文件格式错误: {json_path}。将使用空的黑名单和热门标签列表。")
        return set(), set()
    except Exception as e:
        print(f"警告: 加载标签配置失败: {e}。将使用空的黑名单和热门标签列表。")
        return set(), set()

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

# 新增: 用于加载 'Earning' Symbol 黑名单的函数
def load_earning_symbol_blacklist(json_path):
    """从Blacklist.json加载'Earning'分组的symbol黑名单。"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        blacklist = set(data.get('Earning', []))
        print(f"成功加载 'Earning' Symbol 黑名单: {len(blacklist)} 个 symbol。")
        return blacklist
    except Exception as e:
        print(f"警告: 加载 'Earning' Symbol 黑名单失败: {e}，将不进行过滤。")
        return set()

# ========== 新增/修改部分 4/5 ==========
def load_symbol_tags(json_path):
    """从 description.json 加载 'stocks' 分组下所有 symbol 的 tags。"""
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
        
        print(f"成功从 description.json 加载 {len(symbol_tag_map)} 个 symbol 的 tags。")
        return symbol_tag_map
    except FileNotFoundError:
        print(f"警告: Tag 定义文件未找到: {json_path}。将不进行Tag过滤。")
        return {}
    except json.JSONDecodeError:
        print(f"警告: Tag 定义文件格式错误: {json_path}。将不进行Tag过滤。")
        return {}
    except Exception as e:
        print(f"警告: 加载 Tags 失败: {e}。将不进行Tag过滤。")
        return {}

def update_json_panel(symbols_list, target_json_path, group_name, symbol_to_note=None):
    """更新JSON面板文件。
    symbols_list: list[str] 要写入的 symbol 列表
    group_name: str JSON中的组名
    symbol_to_note: Optional[dict[str, str]] 如果提供，按映射写入 value；否则写为 ""
    """
    print(f"\n--- 更新 JSON 文件: {os.path.basename(target_json_path)} -> '{group_name}' ---")
    try:
        with open(target_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"信息: 目标JSON文件不存在或格式错误，将创建一个新的。")
        data = {}

    if symbol_to_note is None:
        data[group_name] = {symbol: "" for symbol in sorted(symbols_list)}
    else:
        # 对于列表中没有映射的 symbol，默认空字符串
        data[group_name] = {symbol: symbol_to_note.get(symbol, "") for symbol in sorted(symbols_list)}

    try:
        with open(target_json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"成功将 {len(symbols_list)} 个 symbol 写入组 '{group_name}'.")
    except Exception as e:
        print(f"错误: 写入JSON文件失败: {e}")

def update_earning_history_json(file_path, group_name, symbols_to_add, log_detail):
    """
    更新 Earning_History.json 文件。
    - file_path: Earning_History.json 的完整路径。
    - group_name: 'season' 或 'no_season'。
    - symbols_to_add: 本次要添加的 symbol 列表。
    - log_detail: 日志记录函数。
    """
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
        log_detail(f"  - 本次新增 {num_added} 个不重复的 symbol。")
        log_detail(f"  - 当天总计 {len(updated_symbols)} 个 symbol。")
    except Exception as e:
        log_detail(f"错误: 写入历史记录文件失败: {e}")
        
def get_next_er_date(last_er_date):
    """计算理论上的下一次财报日期 (+94天)"""
    return last_er_date + datetime.timedelta(days=94)


# --- 4. 核心数据获取模块 (已集成追踪系统) ---

def build_stock_data_cache(symbols, db_path, symbol_sector_map, symbol_to_trace, log_detail):
    """
    为所有给定的symbols一次性从数据库加载所有需要的数据。
    这是性能优化的核心，避免了重复查询。
    """
    print(f"\n--- 开始为 {len(symbols)} 个 symbol 构建数据缓存 ---")
    cache = {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查marketcap列是否存在的标志
    marketcap_exists = True

    for i, symbol in enumerate(symbols):
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n{'='*20} 开始为目标 {symbol} 构建数据缓存 {'='*20}")

        data = {'is_valid': False}
        table_name = symbol_sector_map.get(symbol)
        if not table_name:
            if is_tracing: log_detail(f"[{symbol}] 失败: 在板块映射中未找到该symbol，无法确定数据表。")
            continue
        if is_tracing: log_detail(f"[{symbol}] 信息: 找到板块为 '{table_name}'。")

        # 1. 获取最近 N+1 次财报 (多取一次用于策略2.5/3.5)
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
        if is_tracing: log_detail(f"[{symbol}] 步骤2: 获取财报日收盘价。价格: {er_prices}")
        
        # 检查关键的前N次财报价格是否存在
        if any(p is None for p in er_prices[:CONFIG["NUM_EARNINGS_TO_CHECK"]]):
            if is_tracing: log_detail(f"[{symbol}] 失败: 前 {CONFIG['NUM_EARNINGS_TO_CHECK']} 次财报中存在缺失的价格。")
            continue

        data['all_er_prices'] = er_prices
        
        # 3. 获取最新交易日数据
        cursor.execute(f'SELECT date, price, volume FROM "{table_name}" WHERE name = ? ORDER BY date DESC LIMIT 1', (symbol,))
        latest_row = cursor.fetchone()
        if not latest_row or latest_row[1] is None or latest_row[2] is None:
            if is_tracing: log_detail(f"[{symbol}] 失败: 未能获取到有效的最新交易日数据。查询结果: {latest_row}")
            continue
            
        data['latest_date_str'], data['latest_price'], data['latest_volume'] = latest_row
        data['latest_date'] = datetime.datetime.strptime(data['latest_date_str'], "%Y-%m-%d").date()
        if is_tracing: log_detail(f"[{symbol}] 步骤3: 获取最新交易日数据。日期: {data['latest_date_str']}, 价格: {data['latest_price']}, 成交量: {data['latest_volume']}")

        # 4. 获取其他所需数据 (PE, MarketCap, Earning表price)
        data['pe_ratio'] = None
        data['marketcap'] = None

        if marketcap_exists: # 如果列存在，尝试最优查询
            try:
                cursor.execute("SELECT pe_ratio, marketcap FROM MNSPP WHERE symbol = ?", (symbol,))
                row = cursor.fetchone()
                if row:
                    data['pe_ratio'] = row[0]
                    data['marketcap'] = row[1]
                if is_tracing: log_detail(f"[{symbol}] 步骤4: 尝试从MNSPP获取PE和市值。查询结果: PE={data['pe_ratio']}, 市值={data['marketcap']}")
            except sqlite3.OperationalError as e:
                if "no such column: marketcap" in str(e):
                    if i == 0: # 只在第一次遇到错误时打印警告
                        print(f"警告: MNSPP表中未找到 'marketcap' 列。将回退到仅查询 'pe_ratio'。")
                    marketcap_exists = False # 标记列不存在，后续循环不再尝试
                    # 执行回退查询
                    cursor.execute("SELECT pe_ratio FROM MNSPP WHERE symbol = ?", (symbol,))
                    row = cursor.fetchone()
                    if row:
                        data['pe_ratio'] = row[0]
                    if is_tracing: log_detail(f"[{symbol}] 步骤4 (回退): 'marketcap'列不存在。查询PE。结果: PE={data['pe_ratio']}")
                else:
                    # 其他数据库错误
                    print(f"警告: 查询MNSPP表时发生意外错误 for {symbol}: {e}")
        else: # 如果已经知道列不存在，直接使用回退查询
            cursor.execute("SELECT pe_ratio FROM MNSPP WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            if row:
                data['pe_ratio'] = row[0]
            if is_tracing: log_detail(f"[{symbol}] 步骤4 (已知列不存在): 查询PE。结果: PE={data['pe_ratio']}")

        cursor.execute("SELECT price FROM Earning WHERE name = ? AND date = ?", (symbol, data['latest_er_date_str']))
        row = cursor.fetchone()
        data['earning_record_price'] = row[0] if row else None
        if is_tracing: log_detail(f"[{symbol}] 步骤5: 从Earning表获取最新财报记录的价格。结果: {data['earning_record_price']}")
        
        # 5. 如果所有关键数据都获取成功，则标记为有效
        data['is_valid'] = True
        cache[symbol] = data
        if is_tracing: log_detail(f"[{symbol}] 成功: 数据缓存构建完成，标记为有效。")

    conn.close()
    print(f"--- 数据缓存构建完成，有效数据: {len(cache)} 个 ---")
    return cache

# --- 5. 策略模块 (已集成追踪系统) ---

def run_strategy_1(data, symbol_to_trace, log_detail):
    """策略 1：最新收盘价比过去N次财报的最低值还低至少7%"""
    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    threshold = 1 - CONFIG["MIDDLE_DROP_PERCENTAGE"]
    result = data['latest_price'] < min(prices) * threshold

    if data.get('symbol') == symbol_to_trace:
        log_detail(f"\n--- [{symbol_to_trace}] 策略 1 评估 ---")
        min_price = min(prices)
        threshold_price = min_price * threshold
        log_detail(f"  - 规则: 最新收盘价 < 过去{CONFIG['NUM_EARNINGS_TO_CHECK']}次财报最低价 * (1 - {CONFIG['MIDDLE_DROP_PERCENTAGE']})")
        log_detail(f"  - 条件: latest_price ({data['latest_price']}) < min({prices}) ({min_price}) * {threshold:.2f} ({threshold_price:.4f})")
        log_detail(f"  - 结果: {result}")
        
    return result

# <<< 修改开始: 修改策略3的函数签名和内部逻辑 >>>
def run_strategy_3(data, cursor, symbol_sector_map, symbols_for_time_condition, symbol_to_trace, log_detail):
    """ 策略 3 (修改后):
    (1) 如果最近2次财报上升，最新价 < 过去N次财报最高价 * (1-9%)
    (2) 如果不上升，最近2次财报差额 >= 3%，最新财报非负，且最新价 < 过去N次财报最低价
    ---
    (3) 必须满足(1)或(2)其中之一
    (4) 必须满足：最新价比前10天最低价高不超过3%
    (5) 必须满足：(在指定的财报文件列表中) 或 (最新交易日落在下次理论财报前6-26天窗口期)
    """
    is_tracing = (data.get('symbol') == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol_to_trace}] 策略 3 评估 (已修改) ---")

    # 步骤1: 价格条件检查 (上升/非上升分支)
    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices = list(reversed(prices))
    
    price_ok = False
    is_increasing = asc_prices[-2] < asc_prices[-1]
    if is_tracing:
        log_detail(f"  - 最近两次财报价 (从远到近): {[asc_prices[-2], asc_prices[-1]]}")
        log_detail(f"  - 条件 (最近两次财报上升): {is_increasing}")

    if is_increasing:
        # 上升分支
        threshold = 1 - CONFIG["HIGH_DROP_PERCENTAGE"]
        max_p = max(asc_prices)
        price_ok = data['latest_price'] < max_p * threshold
        if is_tracing:
            log_detail(f"    - 分支(上升): latest_price({data['latest_price']}) < max({asc_prices})({max_p}) * {threshold:.2f} ({max_p * threshold:.4f}) -> {price_ok}")
    else:
        # 非上升分支
        if is_tracing: log_detail(f"    - 分支(非上升):")
        
        # 条件1: 差额检查
        diff_abs = abs(asc_prices[-1] - asc_prices[-2])
        min_diff = asc_prices[-2] * CONFIG["MIN_DROP_PERCENTAGE"]
        diff_ok = diff_abs >= min_diff
        
        # 新增条件2: 最新财报不能为负
        latest_er_positive_ok = data['earning_record_price'] is not None and data['earning_record_price'] > 0
        
        # 条件3: 低价检查
        price_low_ok = data['latest_price'] < min(prices)
        
        # 合并所有条件
        price_ok = diff_ok and latest_er_positive_ok and price_low_ok
        
        if is_tracing:
            log_detail(f"      - 差额检查: abs({asc_prices[-1]} - {asc_prices[-2]}) ({diff_abs:.4f}) >= {asc_prices[-2]} * {CONFIG['MIN_DROP_PERCENTAGE']} ({min_diff:.4f}) -> {diff_ok}")
            log_detail(f"      - 最新财报检查: Earning表price({data['earning_record_price']}) > 0 -> {latest_er_positive_ok}")
            log_detail(f"      - 低价检查: latest_price({data['latest_price']}) < min({prices}) ({min(prices)}) -> {price_low_ok}")
            log_detail(f"      - 分支结果: {price_ok}")

    if not price_ok:
        if is_tracing: log_detail(f"  - 结果: False (价格条件未满足)")
        return False

    # 步骤2: 10日最低价检查
    table_name = symbol_sector_map.get(data['symbol'])
    if not table_name:
        if is_tracing: log_detail(f"      - 无法查询10日最低价 (无table_name)，策略失败")
        return False
    
    ten_days_ago = data['latest_date'] - datetime.timedelta(days=10)
    cursor.execute(
        f'SELECT MIN(price) FROM "{table_name}" WHERE name = ? AND date BETWEEN ? AND ?',
        (data['symbol'], ten_days_ago.isoformat(), data['latest_date_str'])
    )
    min_price_row = cursor.fetchone()
    min_price_10d = min_price_row[0] if min_price_row and min_price_row[0] is not None else None
    
    if is_tracing: log_detail(f"  - 查询过去10天最低价 (从{ten_days_ago.isoformat()}到{data['latest_date_str']}) -> {min_price_10d}")

    if min_price_10d is None:
        if is_tracing: log_detail(f"  - 结果: False (未能获取10日最低价)")
        return False

    threshold_10d = min_price_10d * (1 + CONFIG["MAX_RISE_FROM_7D_LOW"])
    rise_ok = data['latest_price'] <= threshold_10d
    
    if is_tracing:
        log_detail(f"  - 条件 (10日低价上涨幅度): latest_price({data['latest_price']}) <= {min_price_10d} * {1 + CONFIG['MAX_RISE_FROM_7D_LOW']} ({threshold_10d:.4f}) -> {rise_ok}")

    if not rise_ok:
        if is_tracing: log_detail(f"  - 结果: False (10日低价上涨幅度条件未满足)")
        return False

    # 步骤3: 新增的条件性时间窗口检查
    symbol = data['symbol']
    # 使用传入的、不包含 'new' 文件 symbol 的列表进行判断
    is_in_time_condition_list = symbol in symbols_for_time_condition
    
    next_er = get_next_er_date(data['latest_er_date'])
    window_start = next_er - datetime.timedelta(days=26)
    window_end = next_er - datetime.timedelta(days=6)
    is_in_window = (window_start <= data['latest_date'] <= window_end)

    time_condition_met = is_in_time_condition_list or is_in_window
    
    if is_tracing:
        log_detail(f"  - 条件 (时间窗口):")
        log_detail(f"    - 检查1: 是否在指定的财报文件列表(不含new.txt)? -> {is_in_time_condition_list}")
        log_detail(f"    - 检查2: 是否在 {window_start} 到 {window_end} 的时间窗口内? -> {is_in_window}")
        log_detail(f"    - 综合时间条件 (满足其一即可): {time_condition_met}")

    # 最终结果：必须满足价格条件、10日低价条件，以及新的综合时间条件
    final_result = price_ok and rise_ok and time_condition_met
    
    if is_tracing:
        log_detail(f"  - 最终结果 (price_ok AND rise_ok AND time_condition_met): {final_result}")
        
    return final_result

# <<< 修改开始: 修改策略3.5的函数签名和内部逻辑 >>>
def run_strategy_3_5(data, symbols_for_time_condition, symbol_to_trace, log_detail):
    """策略 3.5:
    (1) 过去2次财报保持上升
    (2) 最近的3次财报里至少有一次财报的收盘价要比该symbol的最新收盘价高15%以上
    (3) (在指定的财报文件列表中) 或 (最新交易日落在下次理论财报前6-26天窗口期)
    """
    is_tracing = (data.get('symbol') == symbol_to_trace)
    if len(data['all_er_prices']) < 3 or any(p is None for p in data['all_er_prices'][:3]):
        if is_tracing: log_detail(f"\n--- [{symbol_to_trace}] 策略 3.5 评估 ---\n  - 结果: False (财报价格数据不足3次或有缺失)")
        return False
    
    if is_tracing: log_detail(f"\n--- [{symbol_to_trace}] 策略 3.5 评估 ---")

    # 条件1: 过去2次财报上升
    prices_n = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices_n = list(reversed(prices_n))
    is_increasing = asc_prices_n[-2] < asc_prices_n[-1] # 只比较最近两次

    # 条件2: 价格高于阈值
    prices_3 = data['all_er_prices'][:3]
    price_threshold = data['latest_price'] * (1 + CONFIG["MAX_DROP_PERCENTAGE"])
    any_high = any(p > price_threshold for p in prices_3 if p is not None)

    # 条件3: 新增的条件性时间窗口检查
    symbol = data['symbol']
    # 使用传入的、不包含 'new' 文件 symbol 的列表进行判断
    is_in_time_condition_list = symbol in symbols_for_time_condition

    next_er = get_next_er_date(data['latest_er_date'])
    window_start = next_er - datetime.timedelta(days=26)
    window_end = next_er - datetime.timedelta(days=6)
    is_in_window = (window_start <= data['latest_date'] <= window_end)

    time_condition_met = is_in_time_condition_list or is_in_window

    # 最终结果
    result = is_increasing and any_high and time_condition_met

    if is_tracing:
        log_detail(f"  - 最近两次财报价 (从远到近): {[asc_prices_n[-2], asc_prices_n[-1]]}")
        log_detail(f"  - 条件1 (最近两次财报上升): {is_increasing}")
        log_detail(f"  - 最近三次财报价: {prices_3}")
        log_detail(f"  - 条件2 (任一价比最新价高{CONFIG['MAX_DROP_PERCENTAGE']*100}%): any(p > {data['latest_price']} * {1+CONFIG['MAX_DROP_PERCENTAGE']} = {price_threshold:.4f}) -> {any_high}")
        log_detail(f"  - 条件3 (时间窗口):")
        log_detail(f"    - 检查1: 是否在指定的财报文件列表(不含new.txt)? -> {is_in_time_condition_list}")
        log_detail(f"    - 检查2: 是否在 {window_start} 到 {window_end} 的时间窗口内? -> {is_in_window}")
        log_detail(f"    - 综合时间条件 (满足其一即可): {time_condition_met}")
        log_detail(f"  - 最终结果 (is_increasing AND any_high AND time_condition_met): {result}")

    return result

# 策略 4
def run_strategy_4(data, cursor, symbol_sector_map, symbol_to_trace, log_detail):
    """ 策略 4 (修改后):
    (1) 最近N次财报递增，最近30天内财报，Earning表price>0
    (2) 最新收盘价位于财报日后6-26天
    (3) A：价比财报日前后最高价低X%；B：或价比倒数第二次财报低
    (4) 必须满足：最新价比前10天最低价高不超过3%
    """
    is_tracing = (data.get('symbol') == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol_to_trace}] 策略 4 评估 (已修改) ---")

    prices = data['all_er_prices'][:CONFIG["NUM_EARNINGS_TO_CHECK"]]
    asc_prices = list(reversed(prices))
    
    # 步骤1: 基本条件
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

    # 步骤2: 日期窗口
    window_start = data['latest_er_date'] + datetime.timedelta(days=6)
    window_end = data['latest_er_date'] + datetime.timedelta(days=26)
    is_in_window = (window_start <= data['latest_date'] <= window_end)
    if is_tracing:
        log_detail(f"  - 时间窗口: {window_start} <= 最新交易日({data['latest_date']}) <= {window_end}")
        log_detail(f"  - 条件2 (在时间窗口内): {is_in_window}")
    
    if not is_in_window:
        if is_tracing: log_detail(f"  - 结果: False (未在时间窗口内)")
        return False
        
    # 步骤3: A/B 条件判断
    initial_price_ok = False
    
    # B条件
    second_er_price = data['all_er_prices'][1]
    if second_er_price is None: 
        if is_tracing: log_detail(f"  - 结果: False (倒数第二次财报价格缺失)")
        return False
    
    cond_B = data['latest_price'] < second_er_price
    if is_tracing: log_detail(f"  - 条件3.B: latest_price({data['latest_price']}) < 倒数第二次财报价({second_er_price}) -> {cond_B}")
    if cond_B: 
        initial_price_ok = True
    else:
        # A条件 (仅在B不满足时检查)
        table_name = symbol_sector_map.get(data['symbol'])
        if not table_name:
            if is_tracing: log_detail(f"  - 结果: False (无法获取table_name以检查A条件)")
            return False
            
        start_range = data['latest_er_date'] - datetime.timedelta(days=2)
        end_range   = data['latest_er_date'] + datetime.timedelta(days=5)
        cursor.execute(
            f'SELECT MAX(price) FROM "{table_name}" WHERE name = ? AND date BETWEEN ? AND ?',
            (data['symbol'], start_range.isoformat(), end_range.isoformat())
        )
        max_price_row = cursor.fetchone()
        max_price_around_er = max_price_row[0] if max_price_row else None
        
        if max_price_around_er is None: 
            if is_tracing: log_detail(f"  - 结果: False (无法获取财报日前后最高价)")
            return False

        mcap = data['marketcap']
        drop_pct = CONFIG["MINOR_DROP_PERCENTAGE"] if mcap and mcap >= CONFIG["MARKETCAP_THRESHOLD"] else CONFIG["MIDDLE_PLUS_DROP_PERCENTAGE"]
        threshold_price = max_price_around_er * (1 - drop_pct)
        cond_A = data['latest_price'] < threshold_price
        
        if is_tracing:
            log_detail(f"  - 条件3.A:")
            log_detail(f"    - 市值: {mcap}, 阈值: {CONFIG['MARKETCAP_THRESHOLD']} -> 使用下跌百分比: {drop_pct}")
            log_detail(f"    - 财报日前后(-2+5天)最高价: {max_price_around_er}")
            log_detail(f"    - 判断: latest_price({data['latest_price']}) < {max_price_around_er} * (1-{drop_pct}) ({threshold_price:.4f}) -> {cond_A}")
        
        if cond_A:
            initial_price_ok = True

    if not initial_price_ok:
        if is_tracing: log_detail(f"  - 结果: False (A/B价格条件均未满足)")
        return False

    # 步骤4: 10日最低价检查 (新增的最终条件)
    table_name = symbol_sector_map.get(data['symbol']) # 重复获取以防万一，虽然前面已有
    if not table_name:
        if is_tracing: log_detail(f"      - 无法查询10日最低价 (无table_name)，策略失败")
        return False
        
    ten_days_ago = data['latest_date'] - datetime.timedelta(days=10)
    cursor.execute(
        f'SELECT MIN(price) FROM "{table_name}" WHERE name = ? AND date BETWEEN ? AND ?',
        (data['symbol'], ten_days_ago.isoformat(), data['latest_date_str'])
    )
    min_price_row = cursor.fetchone()
    min_price_10d = min_price_row[0] if min_price_row and min_price_row[0] is not None else None

    if is_tracing: log_detail(f"  - 查询过去10天最低价 (从{ten_days_ago.isoformat()}到{data['latest_date_str']}) -> {min_price_10d}")

    if min_price_10d is None:
        if is_tracing: log_detail(f"  - 结果: False (未能获取10日最低价)")
        return False

    threshold_10d = min_price_10d * (1 + CONFIG["MAX_RISE_FROM_7D_LOW"])
    rise_ok = data['latest_price'] <= threshold_10d

    if is_tracing:
        log_detail(f"  - 条件4 (10日低价上涨幅度): latest_price({data['latest_price']}) <= {min_price_10d} * {1 + CONFIG['MAX_RISE_FROM_7D_LOW']} ({threshold_10d:.4f}) -> {rise_ok}")
        log_detail(f"  - 最终结果: {rise_ok}")

    return rise_ok

# --- 6. 过滤模块 (已集成追踪系统) ---

def get_symbols_with_latest_negative_earning(db_path):
    """
    获取最新一期财报为负 (price < 0) 的所有 symbol 集合。
    这取代了原先的“最近30天”逻辑。
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 使用窗口函数 ROW_NUMBER 来为每个 symbol 的财报按日期降序排名。
    # rn = 1 就代表是最新的一期财报。
    # 然后我们只筛选出那些最新财报 price < 0 的 symbol。
    query = """
    SELECT name
    FROM (
        SELECT
            name,
            price,
            ROW_NUMBER() OVER(PARTITION BY name ORDER BY date DESC) as rn
        FROM Earning
    )
    WHERE rn = 1 AND price < 0;
    """
    
    try:
        cursor.execute(query)
        symbols = {row[0] for row in cursor.fetchall()}
        print(f"\n过滤条件: 找到 {len(symbols)} 个最新一期财报为负的 symbol。")
    except sqlite3.OperationalError as e:
        print(f"错误: 查询最新负财报时发生数据库错误: {e}")
        print("这可能是因为您的 SQLite 版本不支持窗口函数。将返回空集合。")
        symbols = set()
        
    conn.close()
    return symbols

def apply_filters(symbols_set, stock_data_cache, blacklist, negative_earnings_set, is_main_list, symbol_to_trace, log_detail):
    """对给定的symbol集合应用一系列过滤规则"""
    final_list = []
    for symbol in sorted(list(symbols_set)):
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n{'='*20} 开始对目标 {symbol} 进行过滤 (列表: {'主列表' if is_main_list else '通知列表'}) {'='*20}")

        if symbol not in stock_data_cache or not stock_data_cache[symbol]['is_valid']:
            if is_tracing: log_detail(f"[{symbol}] 过滤: 因为在数据缓存中无效或不存在。")
            continue
        
        data = stock_data_cache[symbol]

        # 过滤1: 黑名单
        if symbol in blacklist:
            if is_tracing: log_detail(f"[{symbol}] 过滤(黑名单): symbol在黑名单中。")
            continue
        elif is_tracing: log_detail(f"[{symbol}] 通过(黑名单): symbol不在黑名单中。")

        # 核心修改点：此处的 negative_earnings_set 现在是“最新财报为负”的集合
        if is_main_list and symbol in negative_earnings_set:
            if is_tracing: log_detail(f"[{symbol}] 过滤(主列表-最新财报为负): symbol在最新负财报集合中。")
            continue
        elif is_tracing and is_main_list: log_detail(f"[{symbol}] 通过(主列表-最新财报为负): symbol不在最新负财报集合中。")

        # 过滤3: 成交额
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

        # 过滤5: 最新交易日 == 最新财报日
        if data['latest_date_str'] == data['latest_er_date_str']:
            if is_tracing: log_detail(f"[{symbol}] 过滤(日期相同): 最新交易日({data['latest_date_str']}) 与 最新财报日({data['latest_er_date_str']}) 相同。")
            continue
        elif is_tracing: log_detail(f"[{symbol}] 通过(日期不同)。")
            
        final_list.append(symbol)
        if is_tracing: log_detail(f"[{symbol}] 成功: 通过所有过滤器，已添加到最终列表。")
        
    return final_list

# ========== 新增/修改部分 2/2 ==========
def run_processing_logic(log_detail):
    """
    核心处理逻辑。
    这个函数包含了所有的数据加载、策略执行、过滤和文件输出。
    """
    log_detail(f"程序开始运行...")
    if SYMBOL_TO_TRACE:
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")
    
    # 1. 加载初始数据
    # 修改：加载外部标签配置并更新CONFIG
    tag_blacklist_from_file, hot_tags_from_file = load_tag_settings(TAGS_SETTING_JSON_FILE)
    CONFIG["BLACKLIST_TAGS"] = tag_blacklist_from_file
    CONFIG["HOT_TAGS"] = hot_tags_from_file
    
    # 新增: 从 Blacklist.json 加载 Earning Symbol 黑名单
    CONFIG["SYMBOL_BLACKLIST"] = load_earning_symbol_blacklist(BLACKLIST_JSON_FILE)
    
    symbol_sector_map = create_symbol_to_sector_map(SECTORS_JSON_FILE)
    if not symbol_sector_map:
        log_detail("错误: 无法加载板块映射，程序终止。")
        return

    # 新增：加载 symbol->tags 映射
    symbol_to_tags_map = load_symbol_tags(DESCRIPTION_JSON_FILE)

    # <<< 修改开始: 分离处理 'new' 文件和其他财报文件 >>>
    # 加载 'new' 文件中的 symbols
    symbols_from_new_file = set(get_symbols_from_file(PATHS["earnings_release_new"](news_path)))
    log_detail(f"从 earnings_release_new.txt 加载了 {len(symbols_from_new_file)} 个 symbol。")

    # 加载其他文件中的 symbols，这些将用于满足策略中的“时间条件”
    symbols_next = get_symbols_from_file(PATHS["earnings_release_next"](news_path))
    symbols_third = get_symbols_from_file(PATHS["earnings_release_third"](news_path))
    symbols_fourth = get_symbols_from_file(PATHS["earnings_release_fourth"](news_path))
    symbols_fifth = get_symbols_from_file(PATHS["earnings_release_fifth"](news_path))
    # 使用集合去重
    symbols_for_time_condition = set(symbols_next + symbols_third + symbols_fourth + symbols_fifth)
    log_detail(f"从其他财报文件 (next, third, fourth, fifth) 加载了 {len(symbols_for_time_condition)} 个不重复的 symbol。")

    # 初始文件中的所有 symbol (用于决定总共要处理哪些从文件来的 symbol)
    # 使用集合的并集操作 `|`
    initial_symbols_all = list(symbols_from_new_file | symbols_for_time_condition)

    if SYMBOL_TO_TRACE and SYMBOL_TO_TRACE in initial_symbols_all:
        log_detail(f"\n追踪信息: {SYMBOL_TO_TRACE} 在初始文件列表中。")
        if SYMBOL_TO_TRACE in symbols_from_new_file:
             log_detail(f"  - 具体来源: {SYMBOL_TO_TRACE} 在 'new' 文件中，将不满足策略3/3.5的时间条件。")
        if SYMBOL_TO_TRACE in symbols_for_time_condition:
             log_detail(f"  - 具体来源: {SYMBOL_TO_TRACE} 在其他财报文件中，将满足策略3/3.5的时间条件。")
    elif SYMBOL_TO_TRACE:
        log_detail(f"\n追踪信息: {SYMBOL_TO_TRACE} 不在任何初始财报文件中。")

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT name FROM Earning")
        all_db_symbols = [row[0] for row in cursor.fetchall()]

    # symbols_to_process 现在包含所有来自财报文件和数据库的 symbol
    symbols_to_process = sorted(list(set(initial_symbols_all + all_db_symbols)))
    # <<< 修改结束 >>>

    # 1.1 (新增) 应用 SYMBOL_BLACKLIST 进行初步过滤
    symbol_blacklist = CONFIG.get("SYMBOL_BLACKLIST", set())
    if symbol_blacklist:
        original_count = len(symbols_to_process)
        removed_symbols = set(symbols_to_process) & symbol_blacklist
        
        if removed_symbols:
            log_detail(f"\n--- 应用 Symbol 黑名单 ---")
            log_detail(f"从处理列表中移除了 {len(removed_symbols)} 个在黑名单中的 symbol: {sorted(list(removed_symbols))}")
            if SYMBOL_TO_TRACE and SYMBOL_TO_TRACE in removed_symbols:
                log_detail(f"追踪信息: 目标 symbol '{SYMBOL_TO_TRACE}' 在 Symbol 黑名单中，已被移除，将不会被处理。")

        symbols_to_process = [s for s in symbols_to_process if s not in symbol_blacklist]
        log_detail(f"Symbol 列表从 {original_count} 个缩减到 {len(symbols_to_process)} 个。")
    
    # 2. 构建数据缓存 (核心性能提升)
    stock_data_cache = build_stock_data_cache(symbols_to_process, DB_FILE, symbol_sector_map, SYMBOL_TO_TRACE, log_detail)

    # 3. 运行策略
    results = defaultdict(list)
    with sqlite3.connect(DB_FILE) as conn: # 策略3和4需要一个cursor
        cursor = conn.cursor()

        for symbol, data in stock_data_cache.items():
            if not data['is_valid']:
                continue
            
            data['symbol'] = symbol # 将symbol本身加入data，方便策略3、4使用

            # <<< 修改开始: 使用 'symbols_for_time_condition' 来决定是否运行策略1 >>>
            # 跑主列表策略 (仅针对在 'next', 'third' 等文件里的symbols)
            if symbol in symbols_for_time_condition:
                if run_strategy_1(data, SYMBOL_TO_TRACE, log_detail): results['s1'].append(symbol)
            # <<< 修改结束 >>>
                
            # <<< 修改开始: 将 'symbols_for_time_condition' 传递给策略3和3.5 >>>
            # 跑通知列表策略 (针对所有有数据的symbols)
            if run_strategy_3(data, cursor, symbol_sector_map, symbols_for_time_condition, SYMBOL_TO_TRACE, log_detail): results['s3'].append(symbol)
            if run_strategy_3_5(data, symbols_for_time_condition, SYMBOL_TO_TRACE, log_detail): results['s3_5'].append(symbol)
            # <<< 修改结束 >>>
            if run_strategy_4(data, cursor, symbol_sector_map, SYMBOL_TO_TRACE, log_detail): results['s4'].append(symbol)

    # 4. 汇总初步结果
    # 主列表现在只包含 s1
    s1_set  = set(results['s1'])
    prelim_final_symbols = s1_set

    prelim_Strategy34_list = set(results['s3'] + results['s3_5'] + results['s4'])

    log_detail("\n--- 策略运行初步结果 ---")
    log_detail(f"主列表初步候选: {len(prelim_final_symbols)} 个")
    log_detail(f"通知列表初步候选: {len(prelim_Strategy34_list)} 个")
    if SYMBOL_TO_TRACE and SYMBOL_TO_TRACE in prelim_final_symbols:
        log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 在策略筛选后的 '主列表' 初步候选名单中。")
    if SYMBOL_TO_TRACE and SYMBOL_TO_TRACE in prelim_Strategy34_list:
        log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 在策略筛选后的 '通知列表' 初步候选名单中。")

    # 5. 应用通用过滤器
    blacklist = load_blacklist(BLACKLIST_JSON_FILE)
    negative_earnings_set = get_symbols_with_latest_negative_earning(DB_FILE)

    log_detail("\n--- 开始对主列表进行过滤 ---")
    # 对 s1 用负财报过滤
    log_detail("\n--- 开始对 s1 列表进行过滤（包含负财报过滤） ---")
    final_s1 = apply_filters(
        s1_set,
        stock_data_cache,
        blacklist,
        negative_earnings_set,  # 这里传入真实的负财报集合
        True,
        SYMBOL_TO_TRACE,
        log_detail
    )

    # 最终主列表直接等于 final_s1
    final_symbols = final_s1
    
    log_detail("\n--- 开始对通知列表进行过滤 ---")
    final_Strategy34_list = apply_filters(prelim_Strategy34_list, stock_data_cache, blacklist, set(), False, SYMBOL_TO_TRACE, log_detail)

    # 在这里加一行：把出现在主列表里的剔除掉
    final_Strategy34_list = [s for s in final_Strategy34_list if s not in final_symbols]

    # 6. 基于Tag的过滤 (在所有其他过滤之后)
    log_detail("\n--- 开始基于Tag的过滤 ---")
    tag_blacklist = CONFIG["BLACKLIST_TAGS"]
    log_detail(f"Tag黑名单: {tag_blacklist}")

    # 过滤主列表
    filtered_final_symbols = []
    for symbol in final_symbols:
        symbol_tags = set(symbol_to_tags_map.get(symbol, []))
        if not symbol_tags.intersection(tag_blacklist):
            filtered_final_symbols.append(symbol)
        else:
            log_detail(f"  - [主列表] 因Tag被过滤: {symbol} (Tags: {list(symbol_tags)})")
    final_symbols = filtered_final_symbols

    # 过滤通知列表
    filtered_Strategy34_list = []
    for symbol in final_Strategy34_list:
        symbol_tags = set(symbol_to_tags_map.get(symbol, []))
        if not symbol_tags.intersection(tag_blacklist):
            filtered_Strategy34_list.append(symbol)
        else:
            log_detail(f"  - [通知列表] 因Tag被过滤: {symbol} (Tags: {list(symbol_tags)})")
    final_Strategy34_list = filtered_Strategy34_list

    # 7. 新增：根据 panel.json 中已存在的分组进行最终过滤 (移植自 b.py)
    log_detail("\n--- 开始根据 panel.json 已有分组 ('Today', 'Must') 进行最终过滤 ---")
    try:
        with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f:
            panel_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log_detail(f"警告: panel 文件 ({PANEL_JSON_FILE}) 未找到或格式错误，将不进行分组过滤。")
        panel_data = {}

    # 获取 'Today' 和 'Must' 分组中的所有 symbol，并合并成一个集合用于过滤
    # .get(key, {}) 是一种安全的方式，如果分组不存在，会返回一个空字典，避免出错
    symbols_in_today = set(panel_data.get('Today', {}).keys())
    symbols_in_must = set(panel_data.get('Must', {}).keys())
    
    # 使用集合的并集操作 `|` 来合并两个集合
    exclusion_symbols = symbols_in_today | symbols_in_must

    log_detail(f"从 panel.json 加载了 {len(symbols_in_today)} 个 'Today' symbol。")
    log_detail(f"从 panel.json 加载了 {len(symbols_in_must)} 个 'Must' symbol。")
    log_detail(f"合并后的排除列表包含 {len(exclusion_symbols)} 个不重复的 symbol。")

    # 过滤 Strategy12 列表 (final_symbols)
    # 规则: 如果 symbol 在 'Today' 或 'Must' 组中，则移除
    final_symbols_before_panel_filter = final_symbols
    final_symbols = [s for s in final_symbols if s not in exclusion_symbols]
    removed_from_s12 = set(final_symbols_before_panel_filter) - set(final_symbols)
    if removed_from_s12:
        log_detail(f"  - [Strategy12 过滤]: 移除了 {len(removed_from_s12)} 个已存在于 'Today' 或 'Must' 组的 symbol: {sorted(list(removed_from_s12))}")

    # 过滤 Strategy34 列表 (final_Strategy34_list)
    # 规则: 如果 symbol 在 'Today' 或 'Must' 组中，则移除
    final_Strategy34_list_before_panel_filter = final_Strategy34_list
    final_Strategy34_list = [s for s in final_Strategy34_list if s not in exclusion_symbols]
    removed_from_s34 = set(final_Strategy34_list_before_panel_filter) - set(final_Strategy34_list)
    if removed_from_s34:
        log_detail(f"  - [Strategy34 过滤]: 移除了 {len(removed_from_s34)} 个已存在于 'Today' 或 'Must' 组的 symbol: {sorted(list(removed_from_s34))}")
    # ==================== 代码修改结束 ====================

    # 8. 生成标注并输出最终结果
    # 8.1 热门Tag命中 -> JSON中标注 “{symbol}热”
    hot_tags = set(CONFIG.get("HOT_TAGS", set()))
    def build_symbol_note_map(symbols):
        note_map = {}
        for sym in symbols:
            tags = set(symbol_to_tags_map.get(sym, []))
            if tags & hot_tags:
                note_map[sym] = f"{sym}热"
            else:
                note_map[sym] = ""
        return note_map

    strategy12_notes = build_symbol_note_map(final_symbols)
    strategy34_notes = build_symbol_note_map(final_Strategy34_list)

    # 8.2 打印最终结果
    log_detail("\n--- 所有过滤完成后的最终结果 ---")
    log_detail(f"主列表(Strategy12)最终数量: {len(final_symbols)} - {final_symbols}")
    log_detail(f"通知列表(Strategy34)最终数量: {len(final_Strategy34_list)} - {final_Strategy34_list}")
    if SYMBOL_TO_TRACE:
        if SYMBOL_TO_TRACE in removed_from_s12:
            log_detail(f"\n最终追踪结果: {SYMBOL_TO_TRACE} 通过了策略筛选，但因已存在于 'Today' 或 'Must' 组而未被加入 'Strategy12'。")
        elif SYMBOL_TO_TRACE in removed_from_s34:
            log_detail(f"\n最终追踪结果: {SYMBOL_TO_TRACE} 通过了策略筛选，但因已存在于 'Today' 或 'Must' 组而未被加入 'Strategy34'。")
        elif SYMBOL_TO_TRACE in final_symbols:
            log_detail(f"\n最终追踪结果: {SYMBOL_TO_TRACE} 成功进入了最终的 'Strategy12' 列表。")
        elif SYMBOL_TO_TRACE in final_Strategy34_list:
            log_detail(f"\n最终追踪结果: {SYMBOL_TO_TRACE} 成功进入了最终的 'Strategy34' 列表。")
        else:
            log_detail(f"\n最终追踪结果: {SYMBOL_TO_TRACE} 未进入任何最终列表。")

    # 8.3 文件和JSON输出
    # 主列表 (Strategy12)
    update_json_panel(final_symbols, PANEL_JSON_FILE, "Strategy12", symbol_to_note=strategy12_notes)
    # >>> 修改点 1: 同步写入 Strategy12_backup <<<
    update_json_panel(final_symbols, PANEL_JSON_FILE, "Strategy12_backup", symbol_to_note=strategy12_notes)
    
    try:
        backup_path = PATHS["backup_Strategy12"](news_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)

        with open(backup_path, 'w', encoding='utf-8') as f:
            for sym in sorted(final_symbols):
                f.write(sym + '\n')
        print(f"主列表备份已更新: {backup_path}")

    except IOError as e:
        print(f"写入主列表文件时出错: {e}")

    # 通知列表 (Strategy34)
    update_json_panel(final_Strategy34_list, PANEL_JSON_FILE, "Strategy34", symbol_to_note=strategy34_notes)
    # >>> 修改点 2: 同步写入 Strategy34_backup <<<
    update_json_panel(final_Strategy34_list, PANEL_JSON_FILE, "Strategy34_backup", symbol_to_note=strategy34_notes)
    
    try:
        backup_path = PATHS["backup_Strategy34"](news_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)

        with open(backup_path, 'w', encoding='utf-8') as f:
            for sym in sorted(final_Strategy34_list):
                f.write(sym + '\n')
        print(f"通知列表备份已更新: {backup_path}")

    except IOError as e:
        print(f"写入通知列表文件时出错: {e}")

    # ========== 新增步骤 9: 更新 Earning_History.json ==========
    # 合并所有最终符合条件的 symbol (主列表 + 通知列表)
    all_final_symbols = sorted(list(set(final_symbols + final_Strategy34_list)))
    
    if all_final_symbols:
        update_earning_history_json(
            EARNING_HISTORY_JSON_FILE,
            "season",  # a.py 写入 'season' 分组
            all_final_symbols,
            log_detail
        )
    else:
        log_detail("\n--- 无符合条件的 symbol 可写入 Earning_History.json ---")
    # ==========================================================

# --- 7. 主执行流程 (已集成追踪系统) ---

def main():
    """主程序入口"""
    # 检查是否设置了追踪符号
    if SYMBOL_TO_TRACE:
        # 如果设置了，则启用文件日志记录
        print(f"追踪模式已启用，目标: {SYMBOL_TO_TRACE}。日志将写入: {LOG_FILE_PATH}")
        try:
            with open(LOG_FILE_PATH, 'w', encoding='utf-8') as log_file:
                def log_detail_file(message):
                    """一个辅助函数，用于将调试信息写入文件并打印到控制台"""
                    log_file.write(message + '\n')
                    print(message)
                
                # 调用核心逻辑，并传入文件日志记录函数
                run_processing_logic(log_detail_file)

        except IOError as e:
            print(f"错误：无法打开或写入日志文件 {LOG_FILE_PATH}: {e}")
    
    else:
        # 如果没有设置，则只在控制台打印信息
        print("追踪模式未启用 (SYMBOL_TO_TRACE 为空)。将不会生成日志文件。")
        def log_detail_console(message):
            """一个辅助函数，当不追踪时只打印到控制台"""
            print(message)
        
        # 调用核心逻辑，并传入仅控制台打印的函数
        run_processing_logic(log_detail_console)

    print("\n程序运行结束。")

if __name__ == "__main__":
    main()