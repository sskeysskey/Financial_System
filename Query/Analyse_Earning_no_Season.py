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


# --- 2. 可配置参数 ---
CONFIG = {
    "TARGET_SECTORS": {
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    },
    "TURNOVER_THRESHOLD": 100_000_000,
    "RECENT_EARNINGS_COUNT": 2,
    "MARKETCAP_THRESHOLD": 100_000_000_000,
    "PRICE_DROP_PERCENTAGE_LARGE": 0.10,
    "PRICE_DROP_PERCENTAGE_SMALL": 0.06,
    # 新增：最新收盘价比最近交易日前10天最低收盘价高不超过2%
    "MAX_INCREASE_PERCENTAGE_SINCE_LOW": 0.02,
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

def update_json_panel(symbols_list, json_path, group_name):
    """更新JSON面板文件。"""
    print(f"\n--- 更新 JSON 文件: {os.path.basename(json_path)} -> '{group_name}' ---")
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"信息: 目标JSON文件不存在或格式错误，将创建一个新的。")
        data = {}

    data[group_name] = {symbol: "" for symbol in sorted(symbols_list)}

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"成功将 {len(symbols_list)} 个 symbol 写入组 '{group_name}'.")
    except Exception as e:
        print(f"错误: 写入JSON文件失败: {e}")

# --- 4. 核心数据获取模块 (已集成追踪系统) ---

def build_stock_data_cache(symbols, symbol_to_sector_map, db_path, symbol_to_trace, log_detail):
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
            if is_tracing: log_detail(f"[{symbol}] 步骤4 (已知列不存在): 查询PE。结果: PE={data['pe_ratio']}")

        data['is_valid'] = True
        cache[symbol] = data
        if is_tracing: log_detail(f"[{symbol}] 成功: 数据缓存构建完成，标记为有效。")

    conn.close()
    print(f"--- 数据缓存构建完成，有效数据: {len(cache)} 个 ---")
    return cache

# --- 5. 策略与过滤模块 (已集成追踪系统) ---

def run_strategy(data, symbol_to_trace, log_detail):
    """
    对单个股票的数据执行核心筛选策略：
    条件1 (二选一)：
      a) 最近一次财报的涨跌幅 latest_er_pct 为正
      b) 最新财报收盘价 > 过去 N 次财报收盘价平均值
    条件2：最新价 <= 最近一期财报收盘价 * (1 - X%)
    条件3：最新成交额 >= TURNOVER_THRESHOLD
    """
    symbol = data.get('symbol')
    is_tracing = (symbol == symbol_to_trace)
    if is_tracing: log_detail(f"\n--- [{symbol}] 策略评估 ---")

    # 条件1（同原）
    # latest_er_pct = data.get('latest_er_pct') or 0
    # 新增：取最近 N 次财报涨跌幅
    er_pcts_to_check = data.get('all_er_pcts', [])[-CONFIG["RECENT_EARNINGS_COUNT"]:]
    prices_to_check = data['all_er_prices'][-CONFIG["RECENT_EARNINGS_COUNT"]:]
    if len(prices_to_check) < CONFIG["RECENT_EARNINGS_COUNT"]:
        if is_tracing: log_detail(f"  - 结果: False (最近财报收盘价数量不足 {CONFIG['RECENT_EARNINGS_COUNT']} 次)")
        return False
    avg_recent_price = sum(prices_to_check) / len(prices_to_check)
    latest_er_price = prices_to_check[-1]

    # ---- 条件1：二选一 ----
    # 条件1a：最近 N 次涨跌幅都 > 0
    cond1_a = all(pct > 0 for pct in er_pcts_to_check)
    cond1_b = latest_er_price > avg_recent_price
    cond1_ok = cond1_a or cond1_b
    if is_tracing:
        log_detail("  - 条件1 (二选一):")
        log_detail("    - a) 最近 " f"{CONFIG['RECENT_EARNINGS_COUNT']} 次财报涨跌幅都 > 0: " f"{er_pcts_to_check} -> {cond1_a}")
        log_detail(f"    - b) 最新财报收盘价 > 最近{CONFIG['RECENT_EARNINGS_COUNT']}次平均价: {latest_er_price:.2f} > {avg_recent_price:.2f} -> {cond1_b}")
        log_detail(f"    - 条件1结果: {cond1_ok}")
    if not cond1_ok:
        if is_tracing: log_detail("  - 结果: False (条件1未满足)")
        return False

    # 原条件2: 最新价 < 最新财报收盘价 * (1 - X%)
    market_cap = data.get('market_cap')
    drop_pct = (
        CONFIG["PRICE_DROP_PERCENTAGE_SMALL"]
        if (market_cap and market_cap >= CONFIG["MARKETCAP_THRESHOLD"])
        else CONFIG["PRICE_DROP_PERCENTAGE_LARGE"]
    )
    threshold_price2 = latest_er_price * (1 - drop_pct)
    cond2_ok = data['latest_price'] <= threshold_price2
    if is_tracing:
        log_detail("  - 条件2 (价格回撤):")
        log_detail(f"    - 市值: {market_cap} -> 使用下跌百分比: {drop_pct}")
        log_detail(f"    - 判断: 最新价({data['latest_price']:.2f}) <= 最新财报收盘价({latest_er_price:.2f}) * (1 - {drop_pct}) ({threshold_price2:.2f})")
        log_detail(f"    - 条件2结果: {cond2_ok}")
    if not cond2_ok:
        if is_tracing: log_detail("  - 结果: False (条件2未满足)")
        return False

    # 条件3：最新价不高于最近10日最低收盘价的 1+2%
    prev_prices = data.get('prev_10_prices', [])
    if len(prev_prices) < 10:
        if is_tracing: log_detail(f"  - 结果: False (可用历史交易日不足10日，只有{len(prev_prices)}日数据)")
        return False
    min_prev = min(prev_prices)
    threshold_price3 = min_prev * (1 + CONFIG["MAX_INCREASE_PERCENTAGE_SINCE_LOW"])
    cond3_ok = data['latest_price'] <= threshold_price3
    if is_tracing:
        log_detail(f"  - 条件3 (相对10日最低+2%): 最新价 {data['latest_price']:.2f} <= 最低价 {min_prev:.2f}*1.02={threshold_price3:.2f} -> {cond3_ok}")
    if not cond3_ok:
        if is_tracing: log_detail("  - 结果: False (条件3未满足)")
        return False
    
    # 条件4: 最新成交额 >= 阈值
    turnover = data['latest_price'] * data['latest_volume']
    cond4_ok = turnover >= CONFIG["TURNOVER_THRESHOLD"]
    if is_tracing:
        log_detail("  - 条件4 (成交额):")
        log_detail(f"    - 判断: 最新成交额({turnover:,.0f}) >= 阈值({CONFIG['TURNOVER_THRESHOLD']:,})")
        log_detail(f"    - 条件4结果: {cond4_ok}")
    if not cond4_ok:
        if is_tracing: log_detail("  - 结果: False (条件4未满足)")
        return False
        
    if is_tracing: log_detail("  - 结果: True (所有策略条件均满足)")
    return True

def apply_post_filters(symbols, stock_data_cache, symbol_to_trace, log_detail):
    """对初步筛选结果应用额外的过滤规则。"""
    log_detail("\n--- 开始应用后置过滤器 ---")
    final_list = []
    for symbol in symbols:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing: log_detail(f"\n--- [{symbol}] 后置过滤器评估 ---")
        
        data = stock_data_cache[symbol]

        # 过滤1: PE Ratio
        pe = data['pe_ratio']
        if pe is None or str(pe).strip().lower() in ("--", "null", ""):
            if is_tracing: log_detail(f"  - 过滤 (PE无效): PE值为 '{pe}'。")
            continue
        elif is_tracing: log_detail(f"  - 通过 (PE有效): PE值为 '{pe}'。")

        # 过滤2: 最新交易日 == 最新财报日
        if data['latest_date_str'] == data['latest_er_date_str']:
            if is_tracing: log_detail(f"  - 过滤 (日期相同): 最新交易日({data['latest_date_str']}) 与 最新财报日({data['latest_er_date_str']}) 相同。")
            continue
        elif is_tracing: log_detail(f"  - 通过 (日期不同)。")
            
        final_list.append(symbol)
        if is_tracing: log_detail(f"  - 成功: 通过所有后置过滤器。")
    
    log_detail(f"\n后置过滤完成，剩余 {len(final_list)} 个 symbol。")
    return final_list

def run_processing_logic(log_detail):
    """
    核心处理逻辑。
    包含了所有的数据加载、策略执行、过滤和文件输出。
    它接收一个 log_detail 函数作为参数，用于记录过程信息。
    """
    log_detail("程序开始运行...")
    if SYMBOL_TO_TRACE:
        log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")
    
    # 1. 加载初始数据和配置
    all_symbols, symbol_to_sector_map = load_all_symbols(SECTORS_JSON_FILE, CONFIG["TARGET_SECTORS"])
    if all_symbols is None:
        log_detail("错误: 无法加载symbols，程序终止。")
        return
    
    if SYMBOL_TO_TRACE:
        if SYMBOL_TO_TRACE in all_symbols:
            log_detail(f"\n追踪信息: {SYMBOL_TO_TRACE} 在目标板块的初始加载列表中。")
        else:
            log_detail(f"\n追踪信息: {SYMBOL_TO_TRACE} 不在目标板块的初始加载列表中，后续将不会处理。")

    # 2. 构建数据缓存
    stock_data_cache = build_stock_data_cache(all_symbols, symbol_to_sector_map, DB_FILE, SYMBOL_TO_TRACE, log_detail)

    # 3. 运行策略，得到初步结果
    preliminary_results = []
    for symbol, data in stock_data_cache.items():
        if data['is_valid']:
            data['symbol'] = symbol
            if run_strategy(data, SYMBOL_TO_TRACE, log_detail):
                preliminary_results.append(symbol)
    log_detail(f"\n策略筛选完成，初步找到 {len(preliminary_results)} 个符合条件的股票。")
    if SYMBOL_TO_TRACE:
        if SYMBOL_TO_TRACE in preliminary_results:
            log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 通过了策略筛选。")
        elif SYMBOL_TO_TRACE in stock_data_cache and stock_data_cache[SYMBOL_TO_TRACE]['is_valid']:
            log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 未通过策略筛选。")

    # 4. 应用后置过滤器
    final_qualified_symbols = apply_post_filters(preliminary_results, stock_data_cache, SYMBOL_TO_TRACE, log_detail)
    log_detail(f"\n最终符合所有条件的股票共 {len(final_qualified_symbols)} 个: {sorted(final_qualified_symbols)}")
    if SYMBOL_TO_TRACE:
        if SYMBOL_TO_TRACE in final_qualified_symbols:
            log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 通过了后置过滤器。")
        elif SYMBOL_TO_TRACE in preliminary_results:
            log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 在后置过滤器中被移除。")

    # 5. 处理文件输出
    final_qualified_symbols_set = set(final_qualified_symbols)

    # 5.1 加载黑名单并过滤
    blacklist = load_blacklist(BLACKLIST_JSON_FILE)
    filtered_new_symbols = final_qualified_symbols_set - blacklist
    removed_by_blacklist = len(final_qualified_symbols_set) - len(filtered_new_symbols)
    if removed_by_blacklist > 0:
        log_detail(f"\n根据黑名单，从列表中过滤掉 {removed_by_blacklist} 个 symbol。")
    if SYMBOL_TO_TRACE:
        is_in_blacklist = SYMBOL_TO_TRACE in blacklist
        if SYMBOL_TO_TRACE in final_qualified_symbols_set and is_in_blacklist:
            log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 因在黑名单中被过滤。")
        elif SYMBOL_TO_TRACE in final_qualified_symbols_set:
             log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 不在黑名单中，通过此项检查。")

    # 5.2 加载 panel.json，排除已存在分组
    try:
        with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f: panel_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): panel_data = {}
    exist_notify = set(panel_data.get('Notification', {}).keys())
    exist_next_week = set(panel_data.get('Next_Week', {}).keys())
    already_in_panels = exist_notify | exist_next_week
    
    new_for_earning = filtered_new_symbols - already_in_panels
    skipped = filtered_new_symbols & already_in_panels

    if skipped:
        log_detail(f"\n以下 {len(skipped)} 个 symbol 已存在 Notification/Next_Week 分组，将跳过不写入 Earning_Filter：\n  {sorted(list(skipped))}")
    if SYMBOL_TO_TRACE:
        is_in_panels = SYMBOL_TO_TRACE in already_in_panels
        if SYMBOL_TO_TRACE in filtered_new_symbols and is_in_panels:
            log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 因已存在于 Notification/Next_Week 分组中而被跳过。")
        elif SYMBOL_TO_TRACE in filtered_new_symbols:
            log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 不在现有分组中，通过此项检查。")

    # 5.3 根据是否有真正“新”内容，决定写文件
    if new_for_earning:
        log_detail(f"\n发现 {len(new_for_earning)} 个新的、不在黑名单、且不在其他分组的 symbol。")
        if SYMBOL_TO_TRACE and SYMBOL_TO_TRACE in new_for_earning:
            log_detail(f"追踪信息: {SYMBOL_TO_TRACE} 最终被确定为新增symbol，将写入文件。")
        try:
            with open(NEWS_FILE, 'w', encoding='utf-8') as f:
                for sym in sorted(new_for_earning): f.write(sym + '\n')
            log_detail(f"新增结果已写入到: {NEWS_FILE}")
        except IOError as e:
            log_detail(f"错误: 写入 news 文件失败: {e}")
        update_json_panel(list(new_for_earning), PANEL_JSON_FILE, 'Earning_Filter')
    else:
        log_detail("\n没有新的符合条件的 symbol（或都被黑名单/其他分组拦截）。")
        if os.path.exists(NEWS_FILE):
            os.remove(NEWS_FILE)
            log_detail(f"已删除旧的 news 文件: {NEWS_FILE}")
        update_json_panel([], PANEL_JSON_FILE, 'Earning_Filter')

    # 无论如何，都用本次完整结果覆盖备份文件
    os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
    log_detail(f"\n正在用本次扫描到的 {len(final_qualified_symbols_set)} 个完整结果更新备份文件...")
    try:
        with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
            for sym in sorted(final_qualified_symbols_set): f.write(sym + '\n')
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