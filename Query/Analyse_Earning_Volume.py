import json
import sqlite3
import os
import datetime

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 1. 配置文件和路径 ---
BASE_PATH = USER_HOME

# ================= 配置区域 =================
# 如果为空，则运行“今天”模式；如果填入日期（如 "2024-11-03"），则运行回测模式
SYMBOL_TO_TRACE = "" 
TARGET_DATE = ""

# SYMBOL_TO_TRACE = "IESC"
# TARGET_DATE = "2026-01-09"

# 3. 日志路径
LOG_FILE_PATH = os.path.join(BASE_PATH, "Downloads", "PE_Volume_trace_log.txt")

PATHS = {
    "config_dir": os.path.join(BASE_CODING_DIR, 'Financial_System', 'Modules'),
    "db_dir": os.path.join(BASE_CODING_DIR, 'Database'),
    "sectors_json": lambda config_dir: os.path.join(config_dir, 'Sectors_All.json'),
    "panel_json": lambda config_dir: os.path.join(config_dir, 'Sectors_panel.json'),
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
PANEL_JSON_FILE = PATHS["panel_json"](CONFIG_DIR)
DESCRIPTION_JSON_FILE = PATHS["description_json"](CONFIG_DIR)
TAGS_SETTING_JSON_FILE = PATHS["tags_setting_json"](CONFIG_DIR)
EARNING_HISTORY_JSON_FILE = PATHS["earnings_history_json"](CONFIG_DIR)

CONFIG = {
    "TARGET_SECTORS": {
        "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
        "Industrials", "Real_Estate", "Technology", "Utilities"
    },
    # ========== 目标分组 (两个策略共用) ==========
    "TARGET_GROUPS": [
        "OverSell_W", "PE_Deeper", "PE_Deep", 
        "PE_W", "PE_valid", "PE_invalid", "season", "no_season"
    ],
    # ========== 策略1 (PE_Volume放量下跌) 参数 ==========
    "COND8_VOLUME_LOOKBACK_MONTHS": 2,   # 过去 N 个月
    "COND8_VOLUME_RANK_THRESHOLD": 4,    # 成交量排名前 N 名 (默认3，代码逻辑是 <4)
    
    # ========== 策略2 (PE_Volume_up活跃上涨) 参数 ==========
    "COND_UP_HISTORY_LOOKBACK_DAYS": 5,  # 历史记录回溯天数
    "COND_UP_VOL_RANK_MONTHS": 2,        # 放量检查回溯月份
    "COND_UP_VOL_RANK_THRESHOLD": 4,     # 放量检查前 N 名
}

# --- 2. 辅助与文件操作模块 ---

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
        symbol_to_sector_map = {}
        for sector, symbols in all_sectors_data.items():
            if sector in target_sectors:
                for symbol in symbols:
                    symbol_to_sector_map[symbol] = sector
        return symbol_to_sector_map
    except Exception as e:
        print(f"错误: 加载symbols失败: {e}")
        return None

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

def update_panel_with_conflict_check(json_path, pe_vol_list, pe_vol_notes, pe_vol_up_list, pe_vol_up_notes, log_detail):
    """
    专门用于 PE_Volume 和 PE_Volume_up 的写入。
    功能：
    1. 写入 PE_Volume, PE_Volume_backup, PE_Volume_up, PE_Volume_up_backup。
    2. 检查这些 symbol 是否存在于指定的 backup 分组中，如果存在则删除。
    """
    # 定义需要检查并删除 symbol 的冲突分组
    CONFLICT_GROUPS = [
        "PE_Deep_backup", 
        "PE_Deeper_backup", 
        "PE_W_backup", 
        "OverSell_W_backup", 
        "PE_valid_backup", 
        "PE_invalid_backup", 
        "Strategy12_backup", 
        "Strategy34_backup"
    ]

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    # 1. 汇总所有即将写入 Volume 系列的新 symbol
    all_new_volume_symbols = set(pe_vol_list) | set(pe_vol_up_list)
    
    if not all_new_volume_symbols:
        log_detail("没有新的 Volume symbol 需要写入，跳过冲突检查。")
    else:
        log_detail(f"正在检查 {len(all_new_volume_symbols)} 个新 symbol 是否存在于旧 backup 分组中...")

        # 2. 遍历冲突分组进行清理
        for group_name in CONFLICT_GROUPS:
            if group_name in data and isinstance(data[group_name], dict):
                original_keys = list(data[group_name].keys())
                # 找出交集 (既在旧分组，又是新 Volume symbol)
                intersection = set(original_keys) & all_new_volume_symbols
                
                if intersection:
                    # 重建该分组，排除掉交集中的 symbol
                    new_group_data = {
                        k: v for k, v in data[group_name].items() 
                        if k not in all_new_volume_symbols
                    }
                    data[group_name] = new_group_data
                    log_detail(f"  -> 从 '{group_name}' 中移除了: {sorted(list(intersection))}")

    # 3. 写入新的 Volume 分组数据
    # 辅助函数：构建带备注的字典
    def build_group_dict(symbols, notes):
        return {sym: notes.get(sym, "") for sym in sorted(symbols)}

    data['PE_Volume'] = build_group_dict(pe_vol_list, pe_vol_notes)
    data['PE_Volume_backup'] = build_group_dict(pe_vol_list, pe_vol_notes)
    
    data['PE_Volume_up'] = build_group_dict(pe_vol_up_list, pe_vol_up_notes)
    data['PE_Volume_up_backup'] = build_group_dict(pe_vol_up_list, pe_vol_up_notes)

    # 4. 保存文件
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_detail("Panel 文件更新完成 (包含冲突清理)。")
    except Exception as e:
        log_detail(f"错误: 写入 Panel JSON 文件失败: {e}")

def update_earning_history_json(file_path, group_name, symbols_to_add, log_detail, base_date_str):
    log_detail(f"\n--- 更新历史记录文件: {os.path.basename(file_path)} -> '{group_name}' ---")
    
    # 使用传入的基准日期作为记录日期
    record_date_str = base_date_str

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    if group_name not in data:
        data[group_name] = {}

    existing_symbols = data[group_name].get(record_date_str, [])
    combined_symbols = set(existing_symbols) | set(symbols_to_add)
    updated_symbols = sorted(list(combined_symbols))
    
    data[group_name][record_date_str] = updated_symbols
    num_added = len(updated_symbols) - len(existing_symbols)

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_detail(f"成功更新历史记录。日期: {record_date_str}, 分组: '{group_name}'.")
        log_detail(f" - 本次新增 {num_added} 个不重复的 symbol。")
    except Exception as e:
        log_detail(f"错误: 写入历史记录文件失败: {e}")

# --- 3. 核心逻辑模块 ---

def get_trading_dates_list(cursor, sector_name, symbol, end_date_str, limit=10):
    """
    获取包含 end_date_str 在内的最近 limit 个交易日日期列表。
    返回: ['2025-01-28', '2025-01-27', '2025-01-24', ...] (倒序)
    """
    query = f'SELECT date FROM "{sector_name}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT ?'
    cursor.execute(query, (symbol, end_date_str, limit))
    rows = cursor.fetchall()
    return [r[0] for r in rows]

def check_volume_rank(cursor, sector_name, symbol, latest_date_str, latest_volume, lookback_months, rank_threshold, log_detail, is_tracing):
    """
    通用检查：latest_volume 是否是过去 lookback_months 个月内的前 rank_threshold 名
    """
    # 计算 N 个月前的日期
    try:
        dt = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d")
        start_date = dt - datetime.timedelta(days=lookback_months * 30)
        start_date_str = start_date.strftime("%Y-%m-%d")
    except Exception:
        return False

    # 查询过去 N 个月的所有日期和成交量
    query = f'SELECT date, volume FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?'
    cursor.execute(query, (symbol, start_date_str, latest_date_str))
    rows = cursor.fetchall() # 结果是 [(date1, vol1), (date2, vol2), ...]
    
    # 过滤掉 None 值
    valid_data = [(r[0], r[1]) for r in rows if r[1] is not None]
    
    if not valid_data:
        return False
        
    # 排序：按 volume (x[1]) 从大到小排
    sorted_data = sorted(valid_data, key=lambda x: x[1], reverse=True)
    
    # 截取前 N 名
    top_n_data = sorted_data[:rank_threshold]
    
    # 提取前 N 名的成交量数值
    top_n_volumes = [item[1] for item in top_n_data]
    
    # 判定逻辑：当前成交量是否在前 N 名中，或者大于等于第 N 名的值
    is_top_n = False
    if latest_volume in top_n_volumes:
        is_top_n = True
    elif len(top_n_volumes) >= rank_threshold and latest_volume >= top_n_volumes[rank_threshold - 1]:
        is_top_n = True
        
    if is_tracing:
        log_detail(f"     [Rank检查] 日期:{latest_date_str}, 量:{latest_volume}, 回溯:{lookback_months}月")
        top_n_str = ", ".join([f"[{d}]: {v}" for d, v in top_n_data])
        log_detail(f"     前{rank_threshold}名: {top_n_str} -> 结果: {is_top_n}")
        
    return is_top_n

def check_is_earnings_day(cursor, symbol, target_date_str):
    """
    检查 target_date_str 是否为该 symbol 在 Earning 表中的最新财报日。
    """
    try:
        # 查询该 symbol 的最新一条财报记录（或者直接查是否存在该日期的记录）
        # 这里逻辑是：如果该日是财报日，Earning表里应该有这一天的记录
        query = "SELECT date FROM Earning WHERE name = ? AND date = ?"
        cursor.execute(query, (symbol, target_date_str))
        row = cursor.fetchone()
        if row:
            return True
        return False
    except Exception as e:
        # 如果表不存在或查询出错，默认不过滤
        return False

# --- 策略1: PE_Volume (T, T-1, T-2, T-3 放量下跌) ---
def process_condition_8(db_path, history_json_path, sector_map, target_date_override, symbol_to_trace, log_detail):
    """
    执行条件8策略：PE_Volume (修改版：T-1, T-2, T-3 检查是否放量且下跌)
    """
    log_detail("\n========== 开始执行 条件8 (PE_Volume - 放量下跌) 策略 ==========")
    
    # 读取配置
    rank_threshold = CONFIG.get("COND8_VOLUME_RANK_THRESHOLD", 3)
    lookback_months = CONFIG.get("COND8_VOLUME_LOOKBACK_MONTHS", 3)
    log_detail(f"配置参数: 排名阈值 = Top {rank_threshold}, 且必须收盘价下跌")

    # 1. 确定基准日期 (Today)
    # 如果没有指定日期，则获取昨天的日期
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    log_detail(f"基准日期 (Today): {base_date}")
    candidates_volume = set()
    
    # 加载历史记录
    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
    except Exception as e:
        log_detail(f"错误: 无法读取历史记录文件: {e}")
        return []

    # 连接数据库
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    target_groups = CONFIG["TARGET_GROUPS"]
    
    # 获取大盘基准日期 T-1, T-2, T-3
    sample_symbol = list(sector_map.keys())[0] if sector_map else "AAPL"
    sample_sector = sector_map.get(sample_symbol, "Technology")
    
    # 获取最近 5 天日期，算出 T-1, T-2, T-3
    # global_dates[0] = Today, global_dates[1] = T-1 (上一个有效交易日)
    global_dates = get_trading_dates_list(cursor, sample_sector, sample_symbol, base_date, limit=5)
    
    if len(global_dates) < 4:
        log_detail("错误: 无法获取足够的交易日历数据。")
        conn.close()
        return []
        
    # 定义关键日期
    date_t0 = global_dates[0] # Today
    date_t1 = global_dates[1]
    date_t2 = global_dates[2]
    date_t3 = global_dates[3]
    
    log_detail(f"系统计算出的关键日期: T={date_t0}, T-1={date_t1}, T-2={date_t2}, T-3={date_t3}")
    
    # 定义任务列表
    # 格式: (Target_Date_In_History, Date_Index_In_List, Task_Name)
    # Date_Index_In_List: 1代表T-1, 2代表T-2, 3代表T-3
    tasks = [
        (date_t0, 0, "T策略"),
        (date_t1, 1, "T-1策略"),
        (date_t2, 2, "T-2策略"),
        (date_t3, 3, "T-3策略")
    ]
    
    for hist_date, date_idx, task_name in tasks:
        # 1. 从历史文件中提取该日期的所有 symbol
        symbols_on_date = set()
        for group in target_groups:
            grp_data = history_data.get(group, {})
            if isinstance(grp_data, dict):
                syms = grp_data.get(hist_date, [])
                symbols_on_date.update(syms)
        
        symbols_on_date = sorted(list(symbols_on_date))
        log_detail(f" -> 正在扫描 {task_name} (日期: {hist_date})，包含 {len(symbols_on_date)} 个候选。")
        if symbol_to_trace:
            if symbol_to_trace in symbols_on_date:
                log_detail(f"    !!! 目标 {symbol_to_trace} 在 {hist_date} 的历史记录中，开始检查...")
        
        for symbol in symbols_on_date:
            is_tracing = (symbol == symbol_to_trace)
            sector = sector_map.get(symbol)
            if not sector: continue
            
            # 获取该股的具体交易日历
            # 获取 5 天: Today(0), T-1(1), T-2(2), T-3(3)
            dates = get_trading_dates_list(cursor, sector, symbol, base_date, limit=5)
            
            if len(dates) < 4: continue
            if dates[date_idx] != hist_date: continue
            
            # ========== 修改点：获取今日(dates[0]) 和 昨日(dates[1]) 的价格和成交量 ==========
            # 查询最近两天的数据 (倒序: Row 0=Today, Row 1=Yesterday)
            query = f'SELECT price, volume FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol, dates[0]))
            rows = cursor.fetchall()
            
            if len(rows) < 2:
                if is_tracing: log_detail(f"    x [失败] 缺少足够的价格数据进行涨跌幅对比。")
                continue
            
            price_curr, vol_curr = rows[0]
            price_prev, vol_prev = rows[1]
            
            if price_curr is None or price_prev is None or vol_curr is None: continue

            # ========== 规则修改：必须下跌 (今日价 < 昨日价) ==========
            if price_curr >= price_prev:
                if is_tracing: log_detail(f"    x [失败] 价格未下跌 ({price_curr} >= {price_prev})。")
                continue

            # 核心判断逻辑：检查放量
            vol_cond = check_volume_rank(
                cursor, sector, symbol, dates[0], vol_curr, 
                CONFIG["COND8_VOLUME_LOOKBACK_MONTHS"], 
                rank_threshold, 
                log_detail, is_tracing
            )
            
            if vol_cond:
                # ================== 财报日过滤逻辑 ==================
                # 检查今日(dates[0])是否为财报日
                if check_is_earnings_day(cursor, symbol, dates[0]):
                    if is_tracing: log_detail(f"    🛑 [过滤] 今日({dates[0]}) 为财报日，剔除。")
                    continue

                candidates_volume.add(symbol)
                if is_tracing: log_detail(f"    ✅ [通过] {task_name} 放量下跌条件满足！(Price: {price_prev}->{price_curr})")

    conn.close()
    
    result_list = sorted(list(candidates_volume))
    log_detail(f"条件8 (PE_Volume) 筛选完成，共命中 {len(result_list)} 个: {result_list}")
    return result_list

# --- 策略2: PE_Volume_up (T, T-1, T-2 活跃且今日上涨) ---
def process_pe_volume_up(db_path, history_json_path, sector_map, target_date_override, symbol_to_trace, log_detail):
    log_detail("\n========== 开始执行 策略2 (PE_Volume_up) ==========")
    
    # 配置参数
    lookback_days = CONFIG.get("COND_UP_HISTORY_LOOKBACK_DAYS", 3) 
    # 修改点：放量检查回溯月份改为3个月
    vol_rank_months = CONFIG.get("COND_UP_VOL_RANK_MONTHS", 3)
    vol_rank_threshold = CONFIG.get("COND_UP_VOL_RANK_THRESHOLD", 3)
    
    log_detail(f"配置: 历史池扫描范围=近3天(T, T-1, T-2), 放量标准=近{vol_rank_months}个月前{vol_rank_threshold}名")

    # 【回测逻辑】这里处理回测日期
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    # 1. 连接数据库获取全局日期
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    
    sample_symbol = list(sector_map.keys())[0] if sector_map else "AAPL"
    sample_sector = sector_map.get(sample_symbol, "Technology")
    # 获取最近3个交易日 (T, T-1, T-2)
    global_dates = get_trading_dates_list(cursor, sample_sector, sample_symbol, base_date, limit=lookback_days)
    
    if len(global_dates) < 2: # 至少需要 T 和 T-1
        log_detail("错误: 交易日数据不足，无法执行策略2。")
        conn.close()
        return []
    
    log_detail(f"扫描历史日期范围 (T, T-1, T-2): {global_dates}")

    # 2. 从History中收集候选股 (仅限 T, T-1, T-2)
    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
    except Exception:
        conn.close()
        return []

    target_groups = CONFIG["TARGET_GROUPS"]
    candidate_symbols = set()
    
    for hist_date in global_dates:
        for group in target_groups:
            grp_data = history_data.get(group, {})
            if isinstance(grp_data, dict):
                syms = grp_data.get(hist_date, [])
                candidate_symbols.update(syms)
    
    candidate_symbols = sorted(list(candidate_symbols))
    log_detail(f"在 T, T-1, T-2 的历史记录中共扫描到 {len(candidate_symbols)} 个候选 Symbol。")

    results = []
    
    # 3. 逐个检查逻辑
    for symbol in candidate_symbols:
        is_tracing = (symbol == symbol_to_trace)
        sector = sector_map.get(symbol)
        if not sector: continue
        
        if is_tracing: log_detail(f"--- 正在检查 {symbol} (策略2) ---")

        # 【修改点 1】将 LIMIT 从 3 改为 8，以便获取今日 + 过去 7 天的数据
        query = f'SELECT date, price, volume FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 8'
        cursor.execute(query, (symbol, base_date))
        rows = cursor.fetchall()
        
        # 至少需要 T 和 T-1 进行涨跌判断
        if len(rows) < 2:
            if is_tracing: log_detail(f"    x 数据不足2天，跳过。")
            continue
            
        # rows[0]=T, rows[1]=T-1, rows[2]=T-2 (可能不存在)
        # 提取数据
        date_curr, price_curr, vol_curr = rows[0]
        date_prev, price_prev, vol_prev = rows[1]
        
        if price_curr is None or price_prev is None or vol_curr is None or vol_prev is None:
            continue

        # 规则1 (硬性): 必须上涨 (最新价 > 次新价)
        if price_curr <= price_prev:
            if is_tracing: log_detail(f"    x 价格未上涨 ({price_curr} <= {price_prev})，跳过。")
            continue

        # 【修改点 2】新增过滤：比前 7 天最低点高出 3% 则过滤
        # 提取 rows[1:] 中的所有价格（即排除今日后的前 7 天）
        past_prices = [r[1] for r in rows[1:] if r[1] is not None]
        if past_prices:
            min_past_price = min(past_prices)
            threshold_price = min_past_price * 1.03
            if price_curr > threshold_price:
                if is_tracing: 
                    log_detail(f"    🛑 [过滤] 涨幅过大: 当前价 {price_curr} 超过前{len(past_prices)}日最低点 {min_past_price} 的 3% (阈值: {threshold_price:.2f})")
                continue
            else:
                if is_tracing:
                    log_detail(f"    i [通过] 价格位置合理: 当前价 {price_curr} 未超过前{len(past_prices)}日最低点 {min_past_price} 的 3%")

        # 规则2: 财报日过滤 (T-1日)
        if check_is_earnings_day(cursor, symbol, date_prev):
            if is_tracing: log_detail(f"    🛑 昨日({date_prev})是财报日，跳过。")
            continue

        is_match = False
        reason = ""

        # 规则3: 成交量分支逻辑
        if vol_curr > vol_prev:
            # === 分支 A: 放量上涨 ===
            # 修改点: 检查今日(T)是否为 3个月内前3名
            is_top_vol = check_volume_rank(
                cursor, sector, symbol, date_curr, vol_curr, 
                vol_rank_months, vol_rank_threshold, log_detail, is_tracing
            )
            if is_top_vol:
                is_match = True
                reason = "放量上涨 (3个月Top3)"
            else:
                if is_tracing: log_detail(f"    x 放量但未满足3个月Top{vol_rank_threshold}。")
        else:
            # === 分支 B: 缩量上涨 ===
            # 修改点: 检查 T, T-1, T-2 中是否有任意一天是“3个月内前3名”
            # 已经满足: 量缩 (vol_curr < vol_prev) 且 价涨 (price_curr > price_prev)
            
            # 检查列表中的每一天 (T, T-1, T-2)
            has_high_volume_history = False
            # 检查 T, T-1, T-2
            for i in range(min(3, len(rows))):
                d_date, _, d_vol = rows[i]
                if d_vol is None: continue
                
                # 检查这一天是否是当时的3个月内前3名
                # 注意：check_volume_rank 会自动回溯该日期之前的3个月
                is_high = check_volume_rank(
                    cursor, sector, symbol, d_date, d_vol,
                    vol_rank_months, vol_rank_threshold, log_detail, False # 这里如果不追踪细节可以设为False，避免日志爆炸
                )
                if is_high:
                    has_high_volume_history = True
                    if is_tracing: log_detail(f"    -> 发现高量日: {d_date} (Vol:{d_vol})")
                    break # 只要有一天满足即可
            
            if has_high_volume_history:
                is_match = True
                reason = "缩量上涨 (近3日存在高量)"
            else:
                if is_tracing: log_detail(f"    x 缩量上涨，但近3日(T,T-1,T-2)均无高量记录。")

        if is_match:
            results.append(symbol)
            if is_tracing: log_detail(f"    ✅ [选中] {reason}")

    conn.close()
    log_detail(f"策略2 (PE_Volume_up) 筛选完成，共命中 {len(results)} 个。")
    return sorted(results)

# --- 4. 主执行流程 ---

def run_pe_volume_logic(log_detail):
    log_detail("PE_Volume 双策略程序开始运行...")
    if SYMBOL_TO_TRACE: log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")
    
    base_date_str = TARGET_DATE if TARGET_DATE else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    if TARGET_DATE:
        log_detail(f"\n⚠️⚠️⚠️ 注意：当前处于【回测模式】，目标日期：{TARGET_DATE} ⚠️⚠️⚠️")
        log_detail("本次运行将【不会】更新 Panel 和 History JSON 文件。")
    
    # 1. 加载配置和映射
    tag_blacklist, hot_tags = load_tag_settings(TAGS_SETTING_JSON_FILE)
    symbol_to_sector_map = load_all_symbols(SECTORS_JSON_FILE, CONFIG["TARGET_SECTORS"])
    symbol_to_tags_map = load_symbol_tags(DESCRIPTION_JSON_FILE)

    if not symbol_to_sector_map:
        log_detail("错误: 无法加载板块映射，程序终止。")
        return

    # ================= 策略 1 执行 (已恢复) =================
    # 执行策略1：放量下跌
    raw_pe_volume = process_condition_8(
        DB_FILE, 
        EARNING_HISTORY_JSON_FILE, 
        symbol_to_sector_map, 
        TARGET_DATE, 
        SYMBOL_TO_TRACE, 
        log_detail
    )
    final_pe_volume = sorted(list(set(raw_pe_volume)))

    # ================= 策略 2 执行 =================
    # 传入 TARGET_DATE，内部会处理
    raw_pe_volume_up = process_pe_volume_up(
        DB_FILE,
        EARNING_HISTORY_JSON_FILE,
        symbol_to_sector_map,
        TARGET_DATE, 
        SYMBOL_TO_TRACE,
        log_detail
    )
    final_pe_volume_up = sorted(list(set(raw_pe_volume_up)))

    # ================= Tag 黑名单过滤逻辑 =================
    def filter_blacklisted_tags(symbols):
        allowed = []
        for sym in symbols:
            # 获取该股的 tags
            s_tags = set(symbol_to_tags_map.get(sym, []))
            # 检查是否有交集 (即是否命中黑名单)
            intersect = s_tags.intersection(tag_blacklist)
            if not intersect:
                allowed.append(sym)
            else:
                # 如果是追踪目标，打印日志
                if sym == SYMBOL_TO_TRACE:
                    log_detail(f"🛑 [Tag过滤] {sym} 命中黑名单标签: {intersect} -> 剔除。")
        return sorted(allowed)

    # 对策略结果进行过滤 (用于写入 Panel)
    # 策略 1 (虽然现在为空，但逻辑加上)
    filtered_pe_volume = filter_blacklisted_tags(final_pe_volume)
    
    # 策略 2
    filtered_pe_volume_up = filter_blacklisted_tags(final_pe_volume_up)
    
    if SYMBOL_TO_TRACE:
        if SYMBOL_TO_TRACE in final_pe_volume and SYMBOL_TO_TRACE not in filtered_pe_volume:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略1) 通过，但因黑名单标签被过滤。")
        if SYMBOL_TO_TRACE in final_pe_volume_up and SYMBOL_TO_TRACE not in filtered_pe_volume_up:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略2) 通过，但因黑名单标签被过滤。")

    # ================= [新增逻辑] 检查 PE_Deep / PE_Deeper 交叉 =================
    # 在生成 Note 之前，先读取现有的 Panel 文件，找出哪些 symbol 在 Deep/Deeper 组里
    all_existing_notes = {}
    current_deep_symbols = set()
    try:
        with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f:
            p_data = json.load(f)
            # 收集所有组的备注，防止覆盖
            for group_name, group_content in p_data.items():
                if isinstance(group_content, dict):
                    for s, n in group_content.items():
                        # 如果备注里有东西，就存下来
                        if len(n) > len(all_existing_notes.get(s, "")):
                            all_existing_notes[s] = n
            
            # 专门提取 Deep/Deeper 用于“听”字逻辑
            if "PE_Deep" in p_data: current_deep_symbols.update(p_data["PE_Deep"].keys())
            if "PE_Deeper" in p_data: current_deep_symbols.update(p_data["PE_Deeper"].keys())
            
            # === 修改点：新增 PE_valid 和 PE_invalid 用于“听”字逻辑 ===
            if "PE_valid" in p_data: current_deep_symbols.update(p_data["PE_valid"].keys())
            if "PE_invalid" in p_data: current_deep_symbols.update(p_data["PE_invalid"].keys())
            if "OverSell_W" in p_data: current_deep_symbols.update(p_data["OverSell_W"].keys())
            
    except Exception as e:
        log_detail(f"提示: 读取现有备注时出错(可能是文件不存在): {e}")

    # 4. 构建备注 (Note) - 使用过滤后的列表
    # 修改：增加 highlight_set 参数，用于给特定集合中的 symbol 加 "听" 后缀
    def build_symbol_note_map(symbols, existing_notes=None, highlight_set=None):
        """
        symbols: 本次筛选出的 symbol 列表
        existing_notes: 字典，存储了从 panel.json 读取的 {symbol: "原有备注"}
        highlight_set: Deep/Deeper/Valid/Invalid 的 symbol 集合
        """
        note_map = {}
        for sym in symbols:
            # 1. 获取原有备注（如 "OKLO15热"）
            # 注意：这里我们通常只需要后缀部分，所以把 symbol 删掉
            orig_note = ""
            if existing_notes and sym in existing_notes:
                orig_note = existing_notes[sym].replace(sym, "") # 提取出 "15热"
            
            # 3. 构造新备注
            new_suffix = orig_note
            
            # 检查“听”：如果属于 Deep 组且当前备注里没“听”
            if highlight_set and sym in highlight_set:
                if "听" not in new_suffix:
                    new_suffix += "听"
            
            # 最终组合：Symbol + 累加后的后缀
            note_map[sym] = f"{sym}{new_suffix}"
        return note_map
        
    # 为 PE_Volume 组生成备注
    pe_volume_notes = build_symbol_note_map(
        filtered_pe_volume, 
        existing_notes=all_existing_notes, 
        highlight_set=current_deep_symbols
    )
    
    # PE_Volume_up 暂时不需要此逻辑
    pe_volume_up_notes = build_symbol_note_map(filtered_pe_volume_up)

    # 5. 回测安全拦截
    # 【回测逻辑】如果设置了 TARGET_DATE，在这里直接 return，不执行下面的写入操作
    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 [安全拦截] 回测模式 (Date: {TARGET_DATE}) 已启用。")
        log_detail(f"📊 [策略1] PE_Volume (放量下跌) 命中: {len(filtered_pe_volume)} 个 (Raw: {len(final_pe_volume)})") 
        log_detail(f"📊 [策略2] PE_Volume_up (活跃上涨) 命中: {len(filtered_pe_volume_up)} 个 (Raw: {len(final_pe_volume_up)})")
        log_detail("="*60 + "\n")
        return

    # 6. 写入 Panel (使用过滤后的 clean data)
    log_detail(f"\n正在写入 Panel 文件...")
    
    # 使用新的函数：同时写入 Volume 分组并清理 Backup 冲突
    update_panel_with_conflict_check(
        PANEL_JSON_FILE,
        filtered_pe_volume, pe_volume_notes,
        filtered_pe_volume_up, pe_volume_up_notes,
        log_detail
    )

    # 7. 写入 History (通常保留 Raw Data)
    log_detail(f"正在更新 History 文件...")
    # 策略1 写入 (恢复)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume", final_pe_volume, log_detail, base_date_str)
    
    # 策略2 写入 (使用原始 Raw Data，保持算法池完整性)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume_up", final_pe_volume_up, log_detail, base_date_str)

    # ================= [新增] 写入 Tag 黑名单标记分组 =================
    # 汇总两个策略的所有原始 Symbol (注意：这里用的是 final_pe_volume 等原始列表，未经过 tag 剔除的)
    all_volume_symbols = set(final_pe_volume) | set(final_pe_volume_up)
    
    blocked_symbols_to_log = []
    # tag_blacklist 在函数开头已经加载
    
    for sym in all_volume_symbols:
        s_tags = set(symbol_to_tags_map.get(sym, []))
        if s_tags.intersection(tag_blacklist):
            blocked_symbols_to_log.append(sym)
            
    if blocked_symbols_to_log:
        blocked_symbols_to_log = sorted(list(set(blocked_symbols_to_log)))
        update_earning_history_json(EARNING_HISTORY_JSON_FILE, "_Tag_Blacklist", blocked_symbols_to_log, log_detail, base_date_str)
        log_detail(f"已将 {len(blocked_symbols_to_log)} 个命中黑名单Tag的symbol额外记入 '_Tag_Blacklist' 分组。")
    # ================================================================

    log_detail("程序运行结束。")

def main():
    if SYMBOL_TO_TRACE:
        print(f"追踪模式已启用，目标: {SYMBOL_TO_TRACE}。日志将写入: {LOG_FILE_PATH}")
        try:
            with open(LOG_FILE_PATH, 'w', encoding='utf-8') as log_file:
                def log_detail_file(message):
                    log_file.write(message + '\n')
                    print(message)
                run_pe_volume_logic(log_detail_file)
        except IOError as e:
            print(f"错误：无法打开或写入日志文件 {LOG_FILE_PATH}: {e}")
    else:
        print("追踪模式未启用。日志仅输出到控制台。")
        def log_detail_console(message):
            print(message)
        run_pe_volume_logic(log_detail_console)

if __name__ == '__main__':
    main()