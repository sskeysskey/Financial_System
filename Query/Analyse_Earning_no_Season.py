import json
import sqlite3
import os

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


# --- 2. 可配置参数 ---
CONFIG = {
    "TARGET_SECTORS": {
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    },
    # 新增：Symbol 黑名单。所有在此列表中的 symbol 将在处理开始前被直接过滤。
    "SYMBOL_BLACKLIST": {
        "TW"
    },
    # ========================================
    "TURNOVER_THRESHOLD": 100_000_000,
    "RECENT_EARNINGS_COUNT": 2,
    "MARKETCAP_THRESHOLD": 100_000_000_000,
    # 严格筛选标准 (第一轮)
    "PRICE_DROP_PERCENTAGE_LARGE": 0.10, # 1000亿以下
    "PRICE_DROP_PERCENTAGE_SMALL": 0.06, # 1000亿以上
    # 宽松筛选标准 (当第一轮结果数量不足时启用)
    "RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.07,
    "RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.05,
    # 新增：更宽松的筛选标准 (仅在满足特定条件时启用)
    "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE": 0.05,
    "SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL": 0.03,
    # 新增：触发“更宽松”标准的财报收盘价价差百分比
    "ER_PRICE_DIFF_THRESHOLD": 0.40,
    
    # 新增：触发“最宽松”标准的市值门槛 (前提条件D)
    "MARKETCAP_THRESHOLD_FOR_SUPER_RELAXED": 500_000_000_000,
    
    # 触发宽松筛选的最小分组数量 (仅对 PE_valid 组生效)
    "MIN_PE_VALID_SIZE_FOR_RELAXED_FILTER": 5,
    
    "MAX_INCREASE_PERCENTAGE_SINCE_LOW": 0.03,
    # ========== 在这里添加新参数 ==========
    # 条件1c 的专属参数：最新价比最新财报收盘价低至少 X%
    "PRICE_DROP_FOR_COND1C": 0.14,
    # 条件3参数
    "COND4_MARKETCAP_THRESHOLD": 200_000_000_000,  # 2000亿
    "COND4_DROP_THRESHOLDS": [0.07, 0.15],         # 7% 与 15%
    "COND4_LOOKBACK_DAYS": 60,
    
    # 新增：Tag 黑名单。所有包含以下任一 tag 的 symbol 将被过滤掉。
    "TAG_BLACKLIST": {
        
    },
    # 新增：热门 Tag 集合——命中后在 JSON 中将 value 写成 “{symbol}热”
    "HOT_TAGS": {
        "AI软件",
        "数据中心",
        "赋能数据中心",
        "光纤",
        "激光设备",
        "核能",
        "核电",
        "核电站",
        "赋能人工智能"
    },
}

# --- 3. 辅助与文件操作模块 ---

def load_all_symbols(json_path, target_sectors):
    """从Sectors_All.json加载所有目标板块的symbols和symbol->sector映射。"""
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
                    
        print(f"成功加载 {len(all_symbols)} 个 symbols 从 {len(target_sectors)} 个目标板块。")
        return all_symbols, symbol_to_sector_map
    except Exception as e:
        print(f"错误: 加载symbols失败: {e}")
        return None, None

def load_blacklist(json_path):
    """从Blacklist.json加载'newlow'黑名单。"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        blacklist = set(data.get('newlow', []))
        print(f"成功加载 'newlow' 黑名单: {len(blacklist)} 个 symbol。")
        return blacklist
    except Exception as e:
        print(f"警告: 加载黑名单失败: {e}，将不进行过滤。")
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

def update_json_panel(symbols_list, json_path, group_name, symbol_to_note=None):
    """更新JSON面板文件。
    symbols_list: list[str]
    group_name: str
    symbol_to_note: Optional[dict[str, str]] 若提供则按映射写入 value，否则写空字符串
    """
    print(f"\n--- 更新 JSON 文件: {os.path.basename(json_path)} -> '{group_name}' ---")
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"信息: 目标JSON文件不存在或格式错误，将创建一个新的。")
        data = {}

    if symbol_to_note is None:
        data[group_name] = {symbol: "" for symbol in sorted(symbols_list)}
    else:
        data[group_name] = {symbol: symbol_to_note.get(symbol, "") for symbol in sorted(symbols_list)}

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"成功将 {len(symbols_list)} 个 symbol 写入组 '{group_name}'.")
    except Exception as e:
        print(f"错误: 写入JSON文件失败: {e}")

# --- 4. 核心数据获取模块 (已集成追踪系统) ---

def build_stock_data_cache(symbols, symbol_to_sector_map, db_path, symbol_to_trace, log_detail, symbol_to_tags_map):
    """
    为所有给定的symbols一次性从数据库加载所有需要的数据。
    同时从 Earning 表里取出每次财报的涨跌幅（price 字段），
    并记录最新一期的涨跌幅到 data['latest_er_pct']。
    """
    print(f"\n--- 开始为 {len(symbols)} 个 symbol 构建数据缓存 ---")
    cache = {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    market_cap_exists = True  # 假设列存在，遇到错误时再修改

    for i, symbol in enumerate(symbols):
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n{'='*20} 开始为目标 {symbol} 构建数据缓存 {'='*20}")
        
        data = {'is_valid': False}
        sector_name = symbol_to_sector_map.get(symbol)
        if not sector_name:
            if is_tracing: log_detail(f"[{symbol}] 失败: 在板块映射中未找到该symbol。")
            continue
        if is_tracing: log_detail(f"[{symbol}] 信息: 找到板块为 '{sector_name}'。")

        # 1. 获取所有财报日及涨跌幅
        cursor.execute(
            "SELECT date, price FROM Earning WHERE name = ? ORDER BY date ASC",
            (symbol,)
        )
        er_rows = cursor.fetchall()
        if len(er_rows) < 1:
            if is_tracing: log_detail(f"[{symbol}] 失败: 在Earning表中未找到任何财报记录。")
            continue
        if is_tracing: log_detail(f"[{symbol}] 步骤1: 从Earning表获取了 {len(er_rows)} 条财报记录。")

        # 拆分日期和涨跌幅
        all_er_dates = [r[0] for r in er_rows]
        all_er_pcts  = [r[1] for r in er_rows]
        data['all_er_pcts'] = all_er_pcts
        data['all_er_dates'] = all_er_dates
        data['latest_er_date_str'] = all_er_dates[-1]
        data['latest_er_pct'] = all_er_pcts[-1]
        if is_tracing: log_detail(f"[{symbol}]   - 最新财报日: {data['latest_er_date_str']}, 最新财报涨跌幅: {data['latest_er_pct']}")

        # 2. 获取所有财报日的收盘价（从板块表里取）
        placeholders = ', '.join(['?'] * len(all_er_dates))
        query = (
            f'SELECT date, price FROM "{sector_name}" '
            f'WHERE name = ? AND date IN ({placeholders}) ORDER BY date ASC'
        )
        cursor.execute(query, (symbol, *all_er_dates))
        price_data = cursor.fetchall()
        if is_tracing: log_detail(f"[{symbol}] 步骤2: 查询财报日收盘价。要求 {len(all_er_dates)} 条，实际查到 {len(price_data)} 条。")
        if len(price_data) != len(all_er_dates):
            if is_tracing: log_detail(f"[{symbol}] 失败: 财报日收盘价数据不完整。")
            continue
        data['all_er_prices'] = [p[1] for p in price_data]
        if is_tracing: log_detail(f"[{symbol}]   - 财报日收盘价列表: {data['all_er_prices']}")

        # 3. 最新交易日的价格和成交量
        cursor.execute(
            f'SELECT date, price, volume FROM "{sector_name}" '
            f'WHERE name = ? ORDER BY date DESC LIMIT 1',
            (symbol,)
        )
        latest_row = cursor.fetchone()
        if not latest_row or latest_row[1] is None or latest_row[2] is None:
            if is_tracing: log_detail(f"[{symbol}] 失败: 未能获取有效的最新交易日数据。查询结果: {latest_row}")
            continue
        data['latest_date_str'], data['latest_price'], data['latest_volume'] = latest_row
        if is_tracing: log_detail(f"[{symbol}] 步骤3: 获取最新交易日数据。日期: {data['latest_date_str']}, 价格: {data['latest_price']}, 成交量: {data['latest_volume']}")

        # 3.1 获取最新交易日前 10 个交易日的收盘价
        cursor.execute(
            f'SELECT price FROM "{sector_name}" '
            f'WHERE name = ? AND date < ? '
            f'ORDER BY date DESC LIMIT 10',
            (symbol, data['latest_date_str'])
        )
        prev_rows = cursor.fetchall()
        prices_last_10 = [r[0] for r in prev_rows]
        data['prev_10_prices'] = prices_last_10
        if is_tracing:
            log_detail(f"[{symbol}] 步骤3.1: 获取最近10个交易日的收盘价，共 {len(prices_last_10)} 条: {prices_last_10}")

        # 获取财报窗口期最高价 (财报日当天及后三个交易日)
        latest_er_date = data['latest_er_date_str']
        latest_er_price = data['all_er_prices'][-1]
        
        # 查询财报日后三个交易日的价格
        cursor.execute(
            f'SELECT price FROM "{sector_name}" '
            f'WHERE name = ? AND date > ? '
            f'ORDER BY date ASC LIMIT 3',
            (symbol, latest_er_date)
        )
        next_days_rows = cursor.fetchall()
        next_days_prices = [row[0] for row in next_days_rows]
        
        # 收集窗口期内的所有有效价格 (财报日 + 后三天)
        er_window_prices = [latest_er_price]
        er_window_prices.extend(next_days_prices)
            
        data['er_window_high_price'] = max(er_window_prices) if er_window_prices else None
        
        if is_tracing:
            log_detail(f"[{symbol}] 步骤3.2: 查找财报窗口期最高价 (财报日当天及后三个交易日)。")
            log_detail(f"[{symbol}]   - 财报日当天价格: {latest_er_price}")
            log_detail(f"[{symbol}]   - 财报日后三个交易日价格: {next_days_prices}")
            log_detail(f"[{symbol}]   - 窗口期内价格列表: {er_window_prices}")
            log_detail(f"[{symbol}]   - 窗口期内最高价: {data['er_window_high_price']}")

        # 4. 获取PE和市值
        data['pe_ratio'], data['market_cap'] = None, None
        if market_cap_exists:
            try:
                cursor.execute(
                    "SELECT pe_ratio, market_cap FROM MNSPP WHERE symbol = ?",
                    (symbol,)
                )
                row = cursor.fetchone()
                if row:
                    data['pe_ratio'], data['market_cap'] = row
                if is_tracing: log_detail(f"[{symbol}] 步骤4: 尝试从MNSPP获取PE和市值。查询结果: PE={data['pe_ratio']}, 市值={data['market_cap']}")
            except sqlite3.OperationalError as e:
                if "no such column: market_cap" in str(e):
                    if i == 0:
                        print("警告: MNSPP表中无 'market_cap' 列，将回退查询。")
                    market_cap_exists = False
                    cursor.execute(
                        "SELECT pe_ratio FROM MNSPP WHERE symbol = ?",
                        (symbol,)
                    )
                    row = cursor.fetchone()
                    if row:
                        data['pe_ratio'] = row[0]
                    if is_tracing: log_detail(f"[{symbol}] 步骤4 (回退): 'market_cap'列不存在。查询PE。结果: PE={data['pe_ratio']}")
                else:
                    raise
        else:
            cursor.execute(
                "SELECT pe_ratio FROM MNSPP WHERE symbol = ?",
                (symbol,)
            )
            row = cursor.fetchone()
            if row:
                data['pe_ratio'] = row[0]
            if is_tracing: log_detail(f"[{symbol}] 步骤4: 查询PE。结果: PE={data['pe_ratio']}")

        # 5. 条件3相关的缓存字段
        # 标注是否热门Tag或市值≥2000亿
        tags = set(symbol_to_tags_map.get(symbol, []))
        is_hot = len(tags & set(CONFIG.get("HOT_TAGS", set()))) > 0
        is_big = (data['market_cap'] is not None) and (data['market_cap'] >= CONFIG["COND4_MARKETCAP_THRESHOLD"])

        # 只有满足热门或大市值才去查最近lookback_days天最高价
        data['is_hot_or_big_for_cond4'] = bool(is_hot or is_big)
        data['last_N_high'] = None
        data['cond4_drop_type'] = None  # 可能值: None, '7', '15'

        if data['is_hot_or_big_for_cond4']:
            lookback_days = CONFIG.get("COND4_LOOKBACK_DAYS", 60)  # 默认60天≈2个月
            last_N_high = get_high_price_last_n_days(cursor, sector_name, symbol, data['latest_date_str'], lookback_days)
            data['last_N_high'] = last_N_high
            if last_N_high and last_N_high > 0:
                drop_pct_vs_N_high = (last_N_high - data['latest_price']) / last_N_high
                # 命中7%或15%的最低匹配优先记录更高档位（15优先于7）
                cond4_type = None
                thresholds = sorted(CONFIG["COND4_DROP_THRESHOLDS"])  # [0.07, 0.15]
                # 先检查大的阈值（15%），再检查小的阈值（7%）
                if drop_pct_vs_N_high >= max(thresholds):
                    cond4_type = '15'
                elif drop_pct_vs_N_high >= min(thresholds):
                    cond4_type = '7'
                data['cond4_drop_type'] = cond4_type

        if is_tracing:
            log_detail(f"[{symbol}] 步骤5: 条件3缓存 -> is_hot={is_hot}, is_big={is_big}, last_N_high={data['last_N_high']}, cond4_drop_type={data['cond4_drop_type']}")

        data['is_valid'] = True
        cache[symbol] = data
        if is_tracing: log_detail(f"[{symbol}] 成功: 数据缓存构建完成，标记为有效。")

    conn.close()
    print(f"--- 数据缓存构建完成，有效数据: {len(cache)} 个 ---")
    return cache

def get_high_price_last_n_days(cursor, sector_name, symbol, latest_date_str, lookback_days):
    """
    获取 latest_date_str（含当日）往前lookback_days个自然日内的最高价。
    注：若数据库日期非每日连续交易日，此查询会按日期范围选取可用记录。
    """
    # 计算lookback_days天前的日期字符串（简单按日期字符串比较，假设YYYY-MM-DD）
    # 若你的日期是YYYYMMDD或其他格式，请改相应的日期函数或SQL。
    from datetime import datetime, timedelta
    try:
        dt = datetime.strptime(latest_date_str, "%Y-%m-%d")
    except ValueError:
        # 若不是该格式，尝试常见变体；若都不行，可直接用 LIMIT 方式近似
        try:
            dt = datetime.strptime(latest_date_str, "%Y%m%d")
            def to_str(d): return d.strftime("%Y%m%d")
        except ValueError:
            # 回退方案：直接取最近lookback_days条记录的最高价
            cursor.execute(
                f'SELECT price FROM "{sector_name}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT ?',
                (symbol, latest_date_str, lookback_days)
            )
            rows = cursor.fetchall()
            prices = [r[0] for r in rows if r[0] is not None]
            return max(prices) if prices else None
    else:
        def to_str(d): return d.strftime("%Y-%m-%d")

    start_dt = dt - timedelta(days=lookback_days)
    start_str = to_str(start_dt)
    end_str = to_str(dt)

    cursor.execute(
        f'SELECT MAX(price) FROM "{sector_name}" WHERE name = ? AND date BETWEEN ? AND ?',
        (symbol, start_str, end_str)
    )
    row = cursor.fetchone()
    return row[0] if row and row[0] is not None else None

# --- 5. 策略与过滤模块 (已集成追踪系统) ---

# ========== 代码修改部分: check_special_condition 函数重构 ==========
def check_special_condition(data, config, log_detail, symbol_to_trace):
    """
    检查股票应采用何种筛选标准 (前提条件)。
    新规则：
    - 最宽松: (A & B & C) or (A & B & D)
    - 宽松: (A & B) or (B & C)  (但不满足最宽松)
    - 严格: 其他情况
    返回:
      - 0: 严格标准 (Strict)
      - 1: 宽松标准 (Relaxed)
      - 2: 更宽松标准 (Super-Relaxed)
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"  - [特殊条件检查(前提条件)] for {symbol}:")

    # --- 数据准备 ---
    er_pcts = data.get('all_er_pcts', [])
    all_er_prices = data.get('all_er_prices', [])
    market_cap = data.get('market_cap')
    recent_earnings_count = config["RECENT_EARNINGS_COUNT"]

    # --- 数据有效性检查 ---
    if not er_pcts or len(all_er_prices) < recent_earnings_count:
        if is_tracing: log_detail(f"    - 失败: 财报数据不足。-> 返回 0 (严格)")
        return 0

    # --- 评估四个子条件 A, B, C, D ---
    
    # 条件A: 最新一次财报涨跌幅 > 0
    latest_er_pct = er_pcts[-1]
    cond_a = latest_er_pct > 0

    # 条件B: 最新财报收盘价 > 过去 N 次财报收盘价平均值
    prices_to_check = all_er_prices[-recent_earnings_count:]
    avg_recent_price = sum(prices_to_check) / len(prices_to_check)
    latest_er_price = prices_to_check[-1]
    cond_b = latest_er_price > avg_recent_price
    
    # 条件C: 最新两次财报收盘价价差 > 40%
    previous_er_price = all_er_prices[-2]
    price_diff_pct = ((latest_er_price - previous_er_price) / previous_er_price) if previous_er_price > 0 else 0
    cond_c = price_diff_pct > config["ER_PRICE_DIFF_THRESHOLD"]

    # 条件D: 市值 > 5000亿
    market_cap_threshold = config["MARKETCAP_THRESHOLD_FOR_SUPER_RELAXED"]
    cond_d = market_cap is not None and market_cap > market_cap_threshold

    if is_tracing:
        log_detail(f"    - a) 最新财报涨跌幅 > 0: {latest_er_pct:.4f} > 0 -> {cond_a}")
        log_detail(f"    - b) 最新财报收盘价 > 平均价: {latest_er_price:.2f} > {avg_recent_price:.2f} -> {cond_b}")
        log_detail(f"    - c) 最新两次财报价差 > {config['ER_PRICE_DIFF_THRESHOLD']*100}%: {price_diff_pct:.2%} > {config['ER_PRICE_DIFF_THRESHOLD']:.2%} -> {cond_c}")
        log_detail(f"    - d) 市值 > {market_cap_threshold:,}: {market_cap} > {market_cap_threshold:,} -> {cond_d}")

    # --- 最终决策树 ---
    
    # 核心条件B是所有宽松标准的基础，如果不满足，直接返回严格
    if not cond_b:
        if is_tracing: log_detail(f"    - 最终决策 (B为假): -> 返回 0 (严格)")
        return 0
    
    # 到这里，B为真。
    # 检查最宽松标准: (A and B and C) or (A and B and D) => A and B and (C or D)
    if cond_a and (cond_c or cond_d):
        if is_tracing: log_detail(f"    - 最终决策 (A=T, B=T, C or D=T): -> 返回 2 (最宽松)")
        return 2
    
    # 检查宽松标准: (A and B) or (B and C) => B and (A or C)
    # 因为已经排除了最宽松的情况，所以这里直接检查 (A or C) 即可
    if cond_a or cond_c:
        if is_tracing: log_detail(f"    - 最终决策 (B=T, A or C=T, 但不满足最宽松): -> 返回 1 (宽松)")
        return 1
        
    # 如果B为真，但A和C都为假，则应用严格标准
    if is_tracing: log_detail(f"    - 最终决策 (B=T, 但A和C均为假): -> 返回 0 (严格)")
    return 0

def check_new_condition_2(data, config, log_detail, symbol_to_trace):
    """
    检查新增的“前提条件”是否满足。
    a) 最新财报收盘价 > 过去 N 次财报收盘价平均值
    b) 最近2次财报收盘价价差 >= 4%
    c) 最新财报涨跌幅 > 0
    d) 最新收盘价 < 过去N次财报最低收盘价
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 新增前提条件评估 ---")

    # --- 数据准备和有效性检查 ---
    recent_earnings_count = config["RECENT_EARNINGS_COUNT"]
    all_er_prices = data.get('all_er_prices', [])
    all_er_pcts = data.get('all_er_pcts', [])

    if len(all_er_prices) < recent_earnings_count:
        if is_tracing: log_detail(f"  - 结果: False (财报收盘价数量不足 {recent_earnings_count} 次)")
        return False
    if not all_er_pcts:
        if is_tracing: log_detail("  - 结果: False (缺少财报涨跌幅数据)")
        return False
    
    # --- 开始逐一检查条件 ---
    recent_er_prices = all_er_prices[-recent_earnings_count:]
    latest_er_price = recent_er_prices[-1]
    latest_er_pct = all_er_pcts[-1]
    
    # 条件a: 最新财报收盘价 > 过去 N 次财报收盘价平均值
    avg_recent_price = sum(recent_er_prices) / len(recent_er_prices)
    cond_a = latest_er_price > avg_recent_price
    if is_tracing: log_detail(f"  - a) 最新财报价 > 平均价: {latest_er_price:.2f} > {avg_recent_price:.2f} -> {cond_a}")
    if not cond_a:
        if is_tracing: log_detail("  - 结果: False (条件a未满足)")
        return False

    # 条件b: 最近2次财报收盘价价差 >= 4%
    # 此条件要求至少有2次财报价格，我们已经在上面用 recent_earnings_count 保证了
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

    # 条件c: 最新财报涨跌幅 > 0
    cond_c = latest_er_pct > 0
    if is_tracing: log_detail(f"  - c) 最新财报涨跌幅 > 0: {latest_er_pct:.4f} > 0 -> {cond_c}")
    if not cond_c:
        if is_tracing: log_detail("  - 结果: False (条件c未满足)")
        return False

    # 条件d: 最新收盘价 < 过去N次财报最低收盘价
    min_recent_er_price = min(recent_er_prices)
    latest_price = data['latest_price']
    cond_d = latest_price < min_recent_er_price
    if is_tracing: log_detail(f"  - d) 最新价 < 最近N次财报最低价: {latest_price:.2f} < {min_recent_er_price:.2f} -> {cond_d}")
    if not cond_d:
        if is_tracing: log_detail("  - 结果: False (条件d未满足)")
        return False

    if is_tracing: log_detail("  - 结果: True (新增前提条件所有子条件均满足)")
    return True

def check_new_condition_4(data, config, log_detail, symbol_to_trace):
    """
    条件3：热门Tag或市值≥2000亿的symbol，若最新价较最近lookback_days天最高价回撤≥7%或≥15%，则满足条件。
    命中的类型写入 data['cond4_drop_type'] 为 '7' 或 '15'（在构建缓存时已计算）。
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)

    if is_tracing: log_detail(f"\n--- [{symbol}] 新增条件3评估 ---")
    if not data.get('is_hot_or_big_for_cond4'):
        if is_tracing: log_detail("  - 结果: False (既非热门也非大市值)")
        return False

    last_N_high = data.get('last_N_high')
    latest_price = data.get('latest_price')
    cond4_type = data.get('cond4_drop_type')
    lookback_days = config.get("COND4_LOOKBACK_DAYS", 60)

    if not last_N_high or last_N_high <= 0:
        if is_tracing: log_detail(f"  - 结果: False (无法获取最近{lookback_days}天最高价)")
        return False

    drop_pct = (last_N_high - latest_price) / last_N_high if last_N_high > 0 else 0.0
    thresholds = sorted(config["COND4_DROP_THRESHOLDS"])  # [0.07, 0.15]
    hit_15 = drop_pct >= max(thresholds)
    hit_7 = drop_pct >= min(thresholds)

    if is_tracing:
        log_detail(f" - 最近{lookback_days}天最高价: {last_N_high:.2f}, 最新价: {latest_price:.2f}, 跌幅: {drop_pct:.2%}")
        log_detail(f"  - 命中15%: {hit_15}, 命中7%: {hit_7}, cond4_drop_type缓存: {cond4_type}")

    # 以缓存计算为准（避免二次判定不一致），但加一层兜底
    if cond4_type in ('7', '15'):
        if is_tracing: log_detail(f"  - 结果: True (命中条件3, 类型: {cond4_type})")
        return True

    # 兜底：若未写入缓存但满足阈值，按最高档位赋值
    if hit_15:
        data['cond4_drop_type'] = '15'
        if is_tracing: log_detail("  - 结果: True (兜底命中15%)")
        return True
    if hit_7:
        data['cond4_drop_type'] = '7'
        if is_tracing: log_detail("  - 结果: True (兜底命中7%)")
        return True

    if is_tracing: log_detail("  - 结果: False (不满足条件3)")
    return False

def evaluate_stock_conditions(data, symbol_to_trace, log_detail, drop_pct_large, drop_pct_small):
    """
    此函数为原始筛选流程 (条件1 + 前提条件的阈值应用)
    条件1 (三选一)：
      a) 最近一次财报的涨跌幅 latest_er_pct 为正
      b) 最新财报收盘价 > 过去 N 次财报收盘价平均值，且最近2次财报收盘价差额 > 4%
      c) 最新收盘价比最新一期财报收盘价低至少 X% (X 来自 CONFIG)
    (AND)
    价格回撤条件：最新价 <= 财报窗口期最高价 * (1 - Y%)
    (AND)
    条件5：最新价不高于最近10日最低收盘价的 1+3%
    (AND)
    成交额条件：最新成交额 >= TURNOVER_THRESHOLD
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 统一策略评估 (使用 large={drop_pct_large*100}%, small={drop_pct_small*100}%) ---")

    # --- 步骤1: 检查两个并列的入口条件 ---
    
    # 入口条件A: 条件1 (三选一)
    er_pcts = data.get('all_er_pcts', [])
    prices_to_check = data['all_er_prices'][-CONFIG["RECENT_EARNINGS_COUNT"]:]
    if not er_pcts or len(prices_to_check) < CONFIG["RECENT_EARNINGS_COUNT"]:
        if is_tracing: log_detail("  - 预检失败: 缺少财报数据，无法评估入口条件。")
        return False
        
    latest_er_pct = er_pcts[-1]
    latest_er_price = prices_to_check[-1]
    avg_recent_price = sum(prices_to_check) / len(prices_to_check)
    drop_pct_for_cond1c = CONFIG["PRICE_DROP_FOR_COND1C"]
    threshold_price1c = latest_er_price * (1 - drop_pct_for_cond1c)
    
    cond1_a = latest_er_pct > 0
    
    # <--- 修改开始: 更新条件1b的逻辑 ---
    # 新条件b: 最新财报收盘价 > 平均价 AND 最近两次财报价差 > 4%
    previous_er_price = prices_to_check[-2] # 获取倒数第二次的财报价格
    price_diff_pct_cond1b = ((latest_er_price - previous_er_price) / previous_er_price) if previous_er_price > 0 else 0
    
    cond1_b_part1 = latest_er_price > avg_recent_price
    cond1_b_part2 = price_diff_pct_cond1b > 0.04
    cond1_b = cond1_b_part1 and cond1_b_part2
    # <--- 修改结束 ---

    cond1_c = data['latest_price'] <= threshold_price1c
    passed_original_cond1 = cond1_a or cond1_b or cond1_c

    if is_tracing:
        log_detail("  - [入口条件A] 原始条件1评估:")
        log_detail(f"    - a) 最新财报涨跌幅 > 0: {latest_er_pct:.4f} > 0 -> {cond1_a}")
        
        # <--- 修改开始: 更新日志输出以匹配新逻辑 ---
        log_detail(f"    - b) 最新财报收盘价 > 平均价 且 最近两次财报价差 > 4%:")
        log_detail(f"      - Part 1 (价 > 平均价): {latest_er_price:.2f} > {avg_recent_price:.2f} -> {cond1_b_part1}")
        log_detail(f"      - Part 2 (价差 > 4%): {price_diff_pct_cond1b:.2%} > 4.00% -> {cond1_b_part2}")
        log_detail(f"      - 综合结果: {cond1_b}")
        # <--- 修改结束 ---
        
        log_detail(f"    - c) 最新价比最新财报收盘价低至少 {drop_pct_for_cond1c*100}%: {data['latest_price']:.2f} <= {threshold_price1c:.2f} -> {cond1_c}")
        log_detail(f"    - 结果: {passed_original_cond1}")

    # 入口条件B: 新增前提条件
    passed_new_cond2 = check_new_condition_2(data, CONFIG, log_detail, symbol_to_trace)

    # 新增：入口条件C: 条件3
    passed_new_cond3 = check_new_condition_4(data, CONFIG, log_detail, symbol_to_trace)

    # 裁定入口条件是否满足
    if not (passed_original_cond1 or passed_new_cond2 or passed_new_cond3):
        if is_tracing: log_detail(f"  - 最终裁定: 失败。三个入口条件均未满足。")
        return False
    
    if is_tracing:
        reasons = []
        if passed_original_cond1: reasons.append("原始条件1")
        if passed_new_cond2: reasons.append("新增前提条件")
        if passed_new_cond3: reasons.append("新增条件3")
        log_detail(f"  - 入口条件通过 (原因: {' 和 '.join(reasons)})。开始执行通用过滤...")

    # --- 步骤2: 执行所有通用过滤条件 ---

    # 通用过滤1: 价格回撤条件
    market_cap = data.get('market_cap')
    er_window_high_price = data.get('er_window_high_price') # 获取新计算的窗口期最高价

    # 确保窗口期最高价有效
    if er_window_high_price is None or er_window_high_price <= 0:
        if is_tracing: log_detail(f"  - 最终裁定: 失败 (无法获取有效的财报窗口期最高价: {er_window_high_price})。")
        return False

    drop_pct = (
        drop_pct_small
        if (market_cap and market_cap >= CONFIG["MARKETCAP_THRESHOLD"])
        else drop_pct_large
    )
    # 使用 er_window_high_price 作为回撤基准
    threshold_price_drawdown = er_window_high_price * (1 - drop_pct)
    cond_drawdown_ok = data['latest_price'] <= threshold_price_drawdown
    
    if is_tracing:
        log_detail("  - [通用过滤1] 价格回撤:")
        log_detail(f"    - 市值: {market_cap} -> 使用下跌百分比: {drop_pct*100:.1f}%")
        # 更新日志以反映新逻辑
        log_detail(f"    - 判断: 最新价({data['latest_price']:.2f}) <= 财报窗口期最高价({er_window_high_price:.2f}) * (1 - {drop_pct:.2f}) = 阈值价({threshold_price_drawdown:.2f}) -> {cond_drawdown_ok}")
    
    if not cond_drawdown_ok:
        if is_tracing: log_detail("  - 最终裁定: 失败 (价格回撤不满足)。")
        return False

    # 通用过滤2: 相对10日最低价条件 (条件3)
    prev_prices = data.get('prev_10_prices', [])
    if len(prev_prices) < 10:
        if is_tracing: log_detail(f"  - 最终裁定: 失败 (可用历史交易日不足10日，只有{len(prev_prices)}日数据)。")
        return False
    min_prev = min(prev_prices)
    threshold_price_10day = min_prev * (1 + CONFIG["MAX_INCREASE_PERCENTAGE_SINCE_LOW"])
    cond_10day_ok = data['latest_price'] <= threshold_price_10day
    if is_tracing:
        log_detail(f"  - [通用过滤2] 相对10日最低价:")
        log_detail(f"    - 判断: 最新价 {data['latest_price']:.2f} <= 最低价*1.03 ({threshold_price_10day:.2f}) -> {cond_10day_ok}")
    if not cond_10day_ok:
        if is_tracing: log_detail("  - 最终裁定: 失败 (相对10日最低价条件不满足)。")
        return False
    
    # 通用过滤3: 成交额条件
    turnover = data['latest_price'] * data['latest_volume']
    cond_turnover_ok = turnover >= CONFIG["TURNOVER_THRESHOLD"]
    if is_tracing:
        log_detail("  - [通用过滤3] 成交额:")
        log_detail(f"    - 判断: 最新成交额({turnover:,.0f}) >= 阈值({CONFIG['TURNOVER_THRESHOLD']:,}) -> {cond_turnover_ok}")
    if not cond_turnover_ok:
        if is_tracing: log_detail("  - 最终裁定: 失败 (成交额不满足)。")
        return False
        
    if is_tracing: log_detail("  - 最终裁定: 成功! 所有入口和通用条件均满足。")
    return True

# 修改 apply_post_filters 函数，使其根据PE有效性返回两个独立的列表
def apply_post_filters(symbols, stock_data_cache, symbol_to_trace, log_detail):
    """
    对初步筛选结果应用额外的过滤规则。
    此函数现在返回两个列表：
    1. pe_valid_symbols: 通过所有后置过滤器，且PE值有效的股票 (条件5)。
    2. pe_invalid_symbols: 通过所有后置过滤器，但PE值无效的股票 (条件5)。
    """
    log_detail("\n--- 开始应用后置过滤器 (含条件5: PE分组) ---")
    pe_valid_symbols = []
    pe_invalid_symbols = []
    
    for symbol in symbols:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n--- [{symbol}] 后置过滤器评估 ---")
        
        data = stock_data_cache[symbol]

        # 过滤1: 最新交易日 == 最新财报日 (此过滤对两组都生效)
        if data['latest_date_str'] == data['latest_er_date_str']:
            if is_tracing: log_detail(f"  - 过滤 (日期相同): 最新交易日({data['latest_date_str']}) 与 最新财报日({data['latest_er_date_str']}) 相同。")
            continue
        elif is_tracing: log_detail(f"  - 通过 (日期不同)。")

        # 过滤2: PE Ratio (根据此条件将symbol分到不同列表)
        pe = data['pe_ratio']
        is_pe_valid = pe is not None and str(pe).strip().lower() not in ("--", "null", "")

        if is_pe_valid:
            if is_tracing: log_detail(f"  - 分组 (PE有效): PE值为 '{pe}'。加入 PE_valid 组。")
            pe_valid_symbols.append(symbol)
        else:
            if is_tracing: log_detail(f"  - 分组 (PE无效): PE值为 '{pe}'。加入 PE_invalid 组。")
            pe_invalid_symbols.append(symbol)
            
    log_detail(f"后置过滤完成: PE有效 {len(pe_valid_symbols)} 个, PE无效 {len(pe_invalid_symbols)} 个。")
    return pe_valid_symbols, pe_invalid_symbols

# ========== 代码修改部分 3/6: 重构核心处理逻辑 ==========
def run_processing_logic(log_detail):
    """
    核心处理逻辑。
    此函数被重构以支持多阶段筛选：
    1. 根据财报和价格条件区分股票为三组：严格、宽松、更宽松。
    2. 对每个组应用对应的回撤标准进行第一轮筛选。
    3. 如果筛选后 PE_valid 组数量依然过少，则对该组中原先使用严格标准的股票再次进行常规宽松筛选。
    """
    log_detail("程序开始运行...")
    if SYMBOL_TO_TRACE:
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")
    
    # 1. 加载初始数据和配置
    all_symbols, symbol_to_sector_map = load_all_symbols(SECTORS_JSON_FILE, CONFIG["TARGET_SECTORS"])
    if all_symbols is None:
        log_detail("错误: 无法加载symbols，程序终止。")
        return
    
    # 1.1 应用 SYMBOL_BLACKLIST 进行初步过滤
    symbol_blacklist = CONFIG.get("SYMBOL_BLACKLIST", set())
    if symbol_blacklist:
        original_count = len(all_symbols)
        # 找出被移除的symbols，用于日志记录
        removed_symbols = set(all_symbols) & symbol_blacklist
        
        if removed_symbols:
            log_detail(f"\n--- (条件7) 应用 Symbol 黑名单 ---")
            log_detail(f"从处理列表中移除了 {len(removed_symbols)} 个在黑名单中的 symbol: {sorted(list(removed_symbols))}")
            # 如果追踪的 symbol 被移除，特别提示
            if SYMBOL_TO_TRACE and SYMBOL_TO_TRACE in removed_symbols:
                log_detail(f"追踪信息: 目标 symbol '{SYMBOL_TO_TRACE}' 在 Symbol 黑名单中，已被移除，将不会被处理。")

        # 创建新的、不包含黑名单成员的 symbol 列表
        all_symbols = [s for s in all_symbols if s not in symbol_blacklist]
        log_detail(f"Symbol 列表从 {original_count} 个缩减到 {len(all_symbols)} 个。")

    symbol_to_tags_map = load_symbol_tags(DESCRIPTION_JSON_FILE)
    
    # 2. 构建数据缓存 (一次性完成)
    stock_data_cache = build_stock_data_cache(all_symbols, symbol_to_sector_map, DB_FILE, SYMBOL_TO_TRACE, log_detail, symbol_to_tags_map)
    
    # 定义一个可重复使用的筛选流程函数
    def perform_filter_pass(symbols_to_check, drop_large, drop_small, pass_name):
        log_detail(f"\n--- {pass_name}: 开始筛选 (下跌标准: >$100B {drop_small*100}%, <$100B {drop_large*100}%) ---")
        
        # 步骤 A: 对每个股票运行统一的筛选函数
        preliminary_results = []
        for symbol in symbols_to_check:
            data = stock_data_cache.get(symbol)
            if not (data and data['is_valid']):
                continue
            
            data['symbol'] = symbol
            
            # 只需调用一个函数，所有逻辑都在其中处理
            if evaluate_stock_conditions(data, SYMBOL_TO_TRACE, log_detail, drop_large, drop_small):
                preliminary_results.append(symbol)

        log_detail(f"{pass_name}: 策略筛选完成，初步找到 {len(preliminary_results)} 个符合条件的股票。")

        # 步骤 B: 应用后置过滤器 (条件5: PE 分组)
        pe_valid, pe_invalid = apply_post_filters(preliminary_results, stock_data_cache, SYMBOL_TO_TRACE, log_detail)

        # 步骤 C: (属于条件7) 基于Tag的过滤
        log_detail(f"\n--- {pass_name}: (条件7) 开始基于Tag的过滤 ---")
        tag_blacklist = CONFIG["TAG_BLACKLIST"]
        
        final_pe_valid = [s for s in pe_valid if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]
        final_pe_invalid = [s for s in pe_invalid if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]

        log_detail(f"{pass_name}: Tag过滤后 -> PE_valid: {len(final_pe_valid)} 个, PE_invalid: {len(final_pe_invalid)} 个。")
        return final_pe_valid, final_pe_invalid

    # ========== 代码修改部分 4/6: 区分股票为三组 ==========
    log_detail("\n--- 步骤 3: 根据特殊条件(前提条件)区分股票组 (严格/宽松/更宽松) ---")
    strict_symbols = []
    relaxed_symbols = []
    super_relaxed_symbols = []
    initial_candidates = list(stock_data_cache.keys())

    for symbol in initial_candidates:
        data = stock_data_cache.get(symbol)
        if not (data and data['is_valid']):
            continue
        data['symbol'] = symbol
        
        filter_mode = check_special_condition(data, CONFIG, log_detail, SYMBOL_TO_TRACE)
        if filter_mode == 2:
            super_relaxed_symbols.append(symbol)
        elif filter_mode == 1:
            relaxed_symbols.append(symbol)
        else:
            strict_symbols.append(symbol)
            
    log_detail(f"完成区分: {len(strict_symbols)} 个(严格), {len(relaxed_symbols)} 个(宽松), {len(super_relaxed_symbols)} 个(更宽松)。")

    # ========== 代码修改部分 5/6: 执行三组独立的第一轮筛选 ==========
    log_detail("\n--- 步骤 4: 执行第一轮筛选 ---")
    
    # 4a. 对“更宽松”组使用更宽松标准
    super_relaxed_valid, super_relaxed_invalid = perform_filter_pass(
        super_relaxed_symbols,
        CONFIG["SUPER_RELAXED_PRICE_DROP_PERCENTAGE_LARGE"],
        CONFIG["SUPER_RELAXED_PRICE_DROP_PERCENTAGE_SMALL"],
        "第一轮筛选 (更宽松组)"
    )

    # 4b. 对“宽松”组使用常规宽松标准
    relaxed_valid, relaxed_invalid = perform_filter_pass(
        relaxed_symbols,
        CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_LARGE"],
        CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_SMALL"],
        "第一轮筛选 (宽松组)"
    )
    
    # 4c. 对“严格”组使用严格标准
    strict_valid, strict_invalid = perform_filter_pass(
        strict_symbols,
        CONFIG["PRICE_DROP_PERCENTAGE_LARGE"],
        CONFIG["PRICE_DROP_PERCENTAGE_SMALL"],
        "第一轮筛选 (严格组)"
    )

    # 4d. 合并第一轮的筛选结果
    pass1_valid = super_relaxed_valid + relaxed_valid + strict_valid
    pass1_invalid = super_relaxed_invalid + relaxed_invalid + strict_invalid
    log_detail("\n--- 第一轮筛选结果汇总 ---")
    log_detail(f"PE_valid 组: {len(pass1_valid)} 个 ({len(super_relaxed_valid)} 更宽松 + {len(relaxed_valid)} 宽松 + {len(strict_valid)} 严格)")
    log_detail(f"PE_invalid 组: {len(pass1_invalid)} 个 ({len(super_relaxed_invalid)} 更宽松 + {len(relaxed_invalid)} 宽松 + {len(strict_invalid)} 严格)")

    # ========== 代码修改部分 (逻辑变更) ==========
    # 条件6：如果 PE_valid 组结果少于5个，将针对严格组使用普通宽松阈值再扫一遍
    log_detail("\n--- (条件6) 检查是否需要为 PE_valid 组进行第二轮宽松筛选 ---")
    min_size_pe_valid = CONFIG["MIN_PE_VALID_SIZE_FOR_RELAXED_FILTER"]
    
    # 默认最终结果为第一轮的结果
    final_pe_valid_symbols = pass1_valid
    final_pe_invalid_symbols = pass1_invalid # PE_invalid 组的结果在第一轮后就已确定

    # 仅检查 PE_valid 组
    if len(pass1_valid) < min_size_pe_valid:
        log_detail(f"\n'PE_valid' 组在第一轮筛选后数量 ({len(pass1_valid)}) 小于阈值 ({min_size_pe_valid})。")
        log_detail(f"将对原先使用严格标准的 {len(strict_symbols)} 个股票，应用常规宽松标准重新筛选。")
        
        # 仅为 PE_valid 组重跑
        rerun_valid, _ = perform_filter_pass(
            strict_symbols,
            CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_LARGE"],
            CONFIG["RELAXED_PRICE_DROP_PERCENTAGE_SMALL"],
            "第二轮筛选 (常规宽松, for PE_valid)"
        )
        # 最终结果是：第一轮中所有宽松/更宽松选出的 + 第二轮对严格部分重筛后选出的
        final_pe_valid_symbols = sorted(list(set(super_relaxed_valid) | set(relaxed_valid) | set(rerun_valid)))
        log_detail(f"第二轮筛选后，'PE_valid' 组更新为 {len(final_pe_valid_symbols)} 个。")
    else:
        log_detail(f"\n'PE_valid' 组在第一轮筛选后数量 ({len(pass1_valid)}) 已达标，无需进行第二轮宽松筛选。")

    log_detail(f"\n'PE_invalid' 组数量为 {len(final_pe_invalid_symbols)}，根据新规则，不进行重扫。")
    # =================================================

    # 6. 汇总最终结果并输出
    all_qualified_symbols = final_pe_valid_symbols + final_pe_invalid_symbols
    log_detail(f"\n--- 最终结果汇总 ---")
    log_detail(f"最终 PE_valid 组: {len(final_pe_valid_symbols)} 个: {sorted(final_pe_valid_symbols)}")
    log_detail(f"最终 PE_invalid 组: {len(final_pe_invalid_symbols)} 个: {sorted(final_pe_invalid_symbols)}")
    log_detail(f"总计符合条件的股票共 {len(all_qualified_symbols)} 个。")

    # (条件7) 处理文件输出和最终过滤
    pe_valid_set = set(final_pe_valid_symbols)
    pe_invalid_set = set(final_pe_invalid_symbols)

    log_detail("\n--- (条件7) 应用最终文件过滤 ---")
    blacklist = load_blacklist(BLACKLIST_JSON_FILE)
    
    # 7.2 加载 panel.json，获取已存在分组的内容
    try:
        with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f: panel_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): panel_data = {}
    exist_Strategy34 = set(panel_data.get('Strategy34', {}).keys())
    exist_Strategy12 = set(panel_data.get('Strategy12', {}).keys())
    already_in_panels = exist_Strategy34 | exist_Strategy12

    # 7.2 从两个组中分别过滤掉黑名单和已存在分组的symbol
    final_pe_valid_to_write = sorted(list(pe_valid_set - blacklist - already_in_panels))
    final_pe_invalid_to_write = sorted(list(pe_invalid_set - blacklist - already_in_panels))

    # 7.3 打印被跳过的信息
    skipped_valid = pe_valid_set & (blacklist | already_in_panels)
    if skipped_valid:
        log_detail(f"\nPE_valid 组中，有 {len(skipped_valid)} 个 symbol 因在黑名单或已有分组中被跳过: {sorted(list(skipped_valid))}")

    skipped_invalid = pe_invalid_set & (blacklist | already_in_panels)
    if skipped_invalid:
        log_detail(f"\nPE_invalid 组中，有 {len(skipped_invalid)} 个 symbol 因在黑名单或已有分组中被跳过: {sorted(list(skipped_invalid))}")

    # 7.4 新增：热门Tag命中 -> JSON中标注 “{symbol}热”
    hot_tags = set(CONFIG.get("HOT_TAGS", set()))
    def build_symbol_note_map(symbols):
        """
        生成 symbol -> note 的映射。
        优先级：cond4 15% > cond4 7%，两者与“热”并列；如果同时满足则拼接“热”。
        例：命中15%且热门 -> 'SYMBOL15热'；命中7%且非热门 -> 'SYMBOL7'；仅热门 -> 'SYMBOL热'；否则 -> ''。
        """
        note_map = {}
        for sym in symbols:
            d = stock_data_cache.get(sym, {})
            cond4_type = d.get('cond4_drop_type')  # '15' or '7' or None
            tags = set(symbol_to_tags_map.get(sym, []))
            is_hot = bool(tags & hot_tags)

            base = ""
            if cond4_type == '15':
                base = f"{sym}15"
            elif cond4_type == '7':
                base = f"{sym}7"

            if base:
                note_map[sym] = base + ("热" if is_hot else "")
            else:
                note_map[sym] = f"{sym}热" if is_hot else ""
        return note_map

    pe_valid_notes = build_symbol_note_map(final_pe_valid_to_write)
    pe_invalid_notes = build_symbol_note_map(final_pe_invalid_to_write)

    # 7.5 更新 JSON 面板文件（带热门标注）
    log_detail(f"\n准备写入 {len(final_pe_valid_to_write)} 个 symbol 到 'PE_valid' 组。")
    update_json_panel(final_pe_valid_to_write, PANEL_JSON_FILE, 'PE_valid', symbol_to_note=pe_valid_notes)
    
    log_detail(f"\n准备写入 {len(final_pe_invalid_to_write)} 个 symbol 到 'PE_invalid' 组。")
    update_json_panel(final_pe_invalid_to_write, PANEL_JSON_FILE, 'PE_invalid', symbol_to_note=pe_invalid_notes)

    # 备份文件仅写 symbol，不带“热”标注
    os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
    log_detail(f"\n正在用本次扫描到的 {len(all_qualified_symbols)} 个完整结果更新备份文件...")
    try:
        with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
            for sym in sorted(all_qualified_symbols): f.write(sym + '\n')
        log_detail(f"备份文件已成功更新: {BACKUP_FILE}")
    except IOError as e:
        log_detail(f"错误: 无法更新备份文件: {e}")

# --- 6. 主执行流程 (已集成追踪系统) ---

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

if __name__ == '__main__':
    main()