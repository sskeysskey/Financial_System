import json
import sqlite3
import os

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
    "PRICE_DROP_PERCENTAGE_LARGE": 0.07,
    "PRICE_DROP_PERCENTAGE_SMALL": 0.04,
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

# --- 4. 核心数据获取模块 ---

def build_stock_data_cache(symbols, symbol_to_sector_map, db_path):
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
        data = {'is_valid': False}
        sector_name = symbol_to_sector_map.get(symbol)
        if not sector_name:
            continue

        # 1. 获取所有财报日及涨跌幅
        cursor.execute(
            "SELECT date, price FROM Earning WHERE name = ? ORDER BY date ASC",
            (symbol,)
        )
        er_rows = cursor.fetchall()
        if len(er_rows) < 1:
            continue

        # 拆分日期和涨跌幅
        all_er_dates = [r[0] for r in er_rows]
        all_er_pcts  = [r[1] for r in er_rows]

        data['all_er_dates'] = all_er_dates
        data['latest_er_date_str'] = all_er_dates[-1]
        data['latest_er_pct']      = all_er_pcts[-1]

        # 2. 获取所有财报日的收盘价（从板块表里取）
        placeholders = ', '.join(['?'] * len(all_er_dates))
        query = (
            f'SELECT date, price FROM "{sector_name}" '
            f'WHERE name = ? AND date IN ({placeholders}) ORDER BY date ASC'
        )
        cursor.execute(query, (symbol, *all_er_dates))
        price_data = cursor.fetchall()
        if len(price_data) != len(all_er_dates):
            continue  # 数据不完整
        data['all_er_prices'] = [p[1] for p in price_data]

        # 3. 最新交易日的价格和成交量
        cursor.execute(
            f'SELECT date, price, volume FROM "{sector_name}" '
            f'WHERE name = ? ORDER BY date DESC LIMIT 1',
            (symbol,)
        )
        latest_row = cursor.fetchone()
        if not latest_row or latest_row[1] is None or latest_row[2] is None:
            continue
        data['latest_date_str'], data['latest_price'], data['latest_volume'] = latest_row

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

        data['is_valid'] = True
        cache[symbol] = data

    conn.close()
    print(f"--- 数据缓存构建完成，有效数据: {len(cache)} 个 ---")
    return cache

# --- 5. 策略与过滤模块 ---

def run_strategy(data):
    """
    对单个股票的数据执行核心筛选策略：
    条件1 (二选一)：
      a) 最近一次财报的涨跌幅 latest_er_pct 为正
      b) 最新财报收盘价 > 过去 N 次财报收盘价平均值
    条件2：最新价 <= 最近一期财报收盘价 * (1 - X%)
    条件3：最新成交额 >= TURNOVER_THRESHOLD
    """
    latest_er_pct = data.get('latest_er_pct', 0)

    # 拿到最近 N 次财报收盘价
    prices_to_check = data['all_er_prices'][-CONFIG["RECENT_EARNINGS_COUNT"]:]
    if len(prices_to_check) < CONFIG["RECENT_EARNINGS_COUNT"]:
        return False

    avg_recent_price = sum(prices_to_check) / len(prices_to_check)
    latest_er_price = prices_to_check[-1]

    # ---- 条件1：二选一 ----
    if not (latest_er_pct > 0 or latest_er_price > avg_recent_price):
        return False

    # 原条件2: 最新价 < 最新财报收盘价 * (1 - X%)
    market_cap = data.get('market_cap')
    drop_pct = (
        CONFIG["PRICE_DROP_PERCENTAGE_SMALL"]
        if (market_cap and market_cap >= CONFIG["MARKETCAP_THRESHOLD"])
        else CONFIG["PRICE_DROP_PERCENTAGE_LARGE"]
    )
    if data['latest_price'] > latest_er_price * (1 - drop_pct):
        return False

    # 条件3: 最新成交额 >= 阈值
    turnover = data['latest_price'] * data['latest_volume']
    if turnover < CONFIG["TURNOVER_THRESHOLD"]:
        return False
        
    # 所有条件均满足
    # print(f"  [策略符合] {data['symbol']}: 最新价 {data['latest_price']:.2f}, 回撤要求 < {latest_er_price * (1 - drop_pct):.2f}, 成交额 {turnover:,.0f}")
    return True

def apply_post_filters(symbols, stock_data_cache):
    """对初步筛选结果应用额外的过滤规则。"""
    print("\n--- 开始应用后置过滤器 ---")
    final_list = []
    for symbol in symbols:
        data = stock_data_cache[symbol]

        # 过滤1: PE Ratio
        pe = data['pe_ratio']
        if pe is None or str(pe).strip().lower() in ("--", "null", ""):
            # print(f"  - 过滤 (PE无效): {symbol}")
            continue

        # 过滤2: 最新交易日 == 最新财报日
        if data['latest_date_str'] == data['latest_er_date_str']:
            # print(f"  - 过滤 (日期相同): {symbol}")
            continue
            
        final_list.append(symbol)
    
    print(f"后置过滤完成，剩余 {len(final_list)} 个 symbol。")
    return final_list

# --- 6. 主执行流程 ---

def main():
    """主程序入口"""
    print("程序开始运行...")
    
    # 1. 加载初始数据和配置
    all_symbols, symbol_to_sector_map = load_all_symbols(SECTORS_JSON_FILE, CONFIG["TARGET_SECTORS"])
    if all_symbols is None:
        return

    # 2. 构建数据缓存 (核心性能提升)
    stock_data_cache = build_stock_data_cache(all_symbols, symbol_to_sector_map, DB_FILE)

    # 3. 运行策略，得到初步结果
    preliminary_results = []
    for symbol, data in stock_data_cache.items():
        if data['is_valid']:
            data['symbol'] = symbol  # 方便调试
            if run_strategy(data):
                preliminary_results.append(symbol)
    print(f"\n策略筛选完成，初步找到 {len(preliminary_results)} 个符合条件的股票。")

    # 4. 应用后置过滤器
    final_qualified_symbols = apply_post_filters(preliminary_results, stock_data_cache)
    print(f"\n最终符合所有条件的股票共 {len(final_qualified_symbols)} 个: {sorted(final_qualified_symbols)}")

    # 5. 处理文件输出
    final_qualified_symbols = set(final_qualified_symbols)

    # 5.1 加载黑名单并过滤
    blacklist = load_blacklist(BLACKLIST_JSON_FILE)
    filtered_new_symbols = final_qualified_symbols - blacklist
    removed_by_blacklist = len(final_qualified_symbols) - len(filtered_new_symbols)
    if removed_by_blacklist > 0:
        print(f"根据黑名单，从新增列表中过滤掉 {removed_by_blacklist} 个 symbol。")

    # 5.2 【新增】再加载 panel.json，排除已经在 Notification 或 Next_Week 分组的
    try:
        with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f:
            panel_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        panel_data = {}

    exist_notify     = set(panel_data.get('Notification', {}).keys())
    exist_next_week = set(panel_data.get('Next_Week',   {}).keys())

    already_in_panels = exist_notify | exist_next_week
    # 最终真正要写到 Earning_Filter 的新符号
    new_for_earning = filtered_new_symbols - already_in_panels
    skipped = filtered_new_symbols & already_in_panels

    if skipped:
        print(f"以下 {len(skipped)} 个 symbol 已存在 Notification/Next_Week 分组，将跳过不写入 Earning_Filter：\n  {sorted(skipped)}")
    filtered_new_symbols = new_for_earning

    # 5.3 根据是否有真正“新”内容，决定写 news 文件 & 更新 Earning_Filter
    if filtered_new_symbols:
        print(f"\n发现 {len(filtered_new_symbols)} 个新的、且不在黑名单，且不在 Notification/Next_Week 的 symbol。")
        # 写入 news 文件
        try:
            with open(NEWS_FILE, 'w', encoding='utf-8') as f:
                for sym in sorted(filtered_new_symbols):
                    f.write(sym + '\n')
            print(f"新增结果已写入到: {NEWS_FILE}")
        except IOError as e:
            print(f"错误: 写入 news 文件失败: {e}")
        # 更新 panel.json 的 Earning_Filter 分组
        update_json_panel(filtered_new_symbols, PANEL_JSON_FILE, 'Earning_Filter')
    else:
        print("\n没有新的符合条件的 symbol（或都被黑名单/其他分组拦截）。")
        # 删除旧的 news 文件
        if os.path.exists(NEWS_FILE):
            os.remove(NEWS_FILE)
            print(f"已删除旧的 news 文件: {NEWS_FILE}")
        # 清空 panel.json 中的 Earning_Filter 分组
        update_json_panel([], PANEL_JSON_FILE, 'Earning_Filter')

    # 无论如何，都用本次完整结果覆盖备份文件
    # 确保备份目录存在
    os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
    print(f"\n正在用本次扫描到的 {len(final_qualified_symbols)} 个完整结果更新备份文件...")
    try:
        with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
            for sym in sorted(final_qualified_symbols):
                f.write(sym + '\n')
        print(f"备份文件已成功更新: {BACKUP_FILE}")
    except IOError as e:
        print(f"错误: 无法更新备份文件: {e}")

    print("\n程序运行结束。")


if __name__ == '__main__':
    main()