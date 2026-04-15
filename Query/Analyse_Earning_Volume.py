import json
import sqlite3
import os
import re
import datetime

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 1. 配置文件和路径 ---
BASE_PATH = USER_HOME

# ================= 配置区域 =================
# 如果为空，则运行"今天"模式；如果填入日期（如 "2024-11-03"），则运行回测模式
SYMBOL_TO_TRACE = "" 
TARGET_DATE = "" 

# SYMBOL_TO_TRACE = "CM"
# TARGET_DATE = "2026-03-30"

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
        "OverSell_W", "PE_Deeper", "PE_Deep", "PE_W"
    ],
    # ========== 策略1 (PE_Volume放量下跌) 参数 ==========
    "COND8_VOLUME_LOOKBACK_MONTHS": 1.5,   # 过去 N 个月
    "COND8_VOLUME_RANK_THRESHOLD": 3,    # 成交量排名前 N 名
    "COND8_EARNINGS_CHECK_DAYS": 2,      # [新增配置] 检查财报日的回溯天数 (填2则检查前2天: T-1, T-2)
    
    # ========== 策略2 (PE_Volume_up活跃上涨) 参数 ==========
    "COND_UP_HISTORY_LOOKBACK_DAYS": 5,  # 历史记录回溯天数
    "COND_UP_VOL_RANK_MONTHS": 2,        # 放量检查回溯月份
    "COND_UP_VOL_RANK_THRESHOLD": 3,     # 放量检查前 N 名

    # ========== 策略3 (PE_Volume_high 财报突破放量) 参数 ==========
    "COND_HIGH_TURNOVER_LOOKBACK_MONTHS": 12,  # 成交额回溯12个月 (用于甲类)
    "COND_HIGH_TURNOVER_RANK_THRESHOLD": 3,    # 成交额排名前3名
    # [新增] 丙类专用配置
    "COND_HIGH_TURNOVER_BING_DAYS": 45,        # 丙类：成交额回溯45天
    "COND_HIGH_TURNOVER_BING_RANK_THRESHOLD": 3,  # 丙类：排名前3名

    # ========== 策略4 (ETF_Volume_high 放量突破) 参数 ==========
    "ETF_COND_HIGH_TURNOVER_LOOKBACK_MONTHS": 12,  # 成交额回溯12个月
    "ETF_COND_HIGH_TURNOVER_RANK_THRESHOLD": 3,    # 成交额排名前3名

    # ========== 策略5 (ETF_Volume_low 触底放量) 参数 ==========
    "ETF_COND_LOW_PRICE_LOOKBACK_MONTHS": 5,       # 最高点回溯6个月（半年）
    "ETF_COND_LOW_DROP_THRESHOLD": 0.06,           # 距最高点跌幅
    "ETF_COND_LOW_TURNOVER_MONTHS": 3,             # 成交额回溯3个月
    "ETF_COND_LOW_TURNOVER_RANK_THRESHOLD": 2,     # [新增] 成交额排名前 N 名 (前2名)

    # ========== 策略6 (PE_Hot 白名单/超大市值) 参数 ==========
    "PE_HOT_MIN_MARKET_CAP": 150000000000,         # 超大市值门槛 (默认 1500亿)
}

# --- 2. 辅助与文件操作模块 ---
def clean_symbol(symbol_with_suffix):
    """
    更强大的清洗函数：
    1. 移除所有非字母字符 (保留字母)
    2. 如果有数字，通常股票代码不含数字，可以根据需要选择移除或保留
    """
    if not symbol_with_suffix:
        return ""
    
    # 策略：只保留字母。如果你的股票代码包含数字（如某些ETF或特定代码），请调整正则表达式
    # 这里的逻辑是：从字符串中提取出第一个连续的字母序列
    # 例如 "C9热" -> "C", "META15" -> "META"
    match = re.match(r'([A-Za-z]+)', symbol_with_suffix)
    if match:
        return match.group(1).upper()
    
    # 如果没有匹配到字母（极其罕见），则返回原字符串
    return symbol_with_suffix

def load_tag_settings(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        tag_blacklist = set(settings.get('BLACKLIST_TAGS', []))
        hot_tags = set(settings.get('HOT_TAGS', []))
        # [新增] 读取 HOT_TAGS_T
        hot_tags_t = set(settings.get('HOT_TAGS_T', []))
        return tag_blacklist, hot_tags, hot_tags_t
    except Exception:
        return set(), set(), set()

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

def update_panel_with_conflict_check(json_path, pe_vol_list, pe_vol_notes, pe_vol_up_list, pe_vol_up_notes, pe_vol_high_list, pe_vol_high_notes, etf_vol_high_list, etf_vol_high_notes, etf_vol_low_list, etf_vol_low_notes, pe_hot_list, pe_hot_notes, log_detail):
    """
    专门用于 PE_Volume, PE_Volume_up, PE_Volume_high, 以及 ETF_Volume_high 、pe_hot_list、pe_hot_notes 的写入。
    功能：
    1. 写入所有三个策略的主分组和 backup 分组。
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

    # === 修改 ===：将 ETF symbol 也加入新写入汇总池
    all_new_volume_symbols = set(pe_vol_list) | set(pe_vol_up_list) | set(pe_vol_high_list) | set(etf_vol_high_list)
    
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
    # 辅助函数：构建带备注的字典 (修复 "IWF": "IWF" 问题)
    def build_group_dict(symbols, notes):
        result = {}
        for sym in sorted(symbols):
            val = notes.get(sym, "")
            # 如果生成的值等于纯净的 symbol，说明没有后缀，必须往 Panel 里写入 ""
            if val == sym:
                result[sym] = ""
            else:
                result[sym] = val
        return result

    # 写入策略1
    data['PE_Volume'] = build_group_dict(pe_vol_list, pe_vol_notes)
    data['PE_Volume_backup'] = build_group_dict(pe_vol_list, pe_vol_notes)
    
    # 写入策略2
    data['PE_Volume_up'] = build_group_dict(pe_vol_up_list, pe_vol_up_notes)
    data['PE_Volume_up_backup'] = build_group_dict(pe_vol_up_list, pe_vol_up_notes)
    
    # 写入策略3
    data['PE_Volume_high'] = build_group_dict(pe_vol_high_list, pe_vol_high_notes)
    data['PE_Volume_high_backup'] = build_group_dict(pe_vol_high_list, pe_vol_high_notes)
    
    # 写入策略4 (ETF_Volume_high)
    data['ETF_Volume_high'] = build_group_dict(etf_vol_high_list, etf_vol_high_notes)
    data['ETF_Volume_high_backup'] = build_group_dict(etf_vol_high_list, etf_vol_high_notes)

    # === 新增 ===：写入策略5 (ETF_Volume_low)
    data['ETF_Volume_low'] = build_group_dict(etf_vol_low_list, etf_vol_low_notes)
    data['ETF_Volume_low_backup'] = build_group_dict(etf_vol_low_list, etf_vol_low_notes)

    # === 新增：写入 PE_Hot 分组 ===
    data['PE_Hot'] = build_group_dict(pe_hot_list, pe_hot_notes)
    data['PE_Hot_backup'] = build_group_dict(pe_hot_list, pe_hot_notes)

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_detail("Panel 文件更新完成 (包含冲突清理、ETF 及 PE_Hot 写入)。")
    except Exception as e:
        log_detail(f"错误: 写入 Panel JSON 文件失败: {e}")

def update_earning_history_json(file_path, group_name, symbols_to_add, log_detail, base_date_str):
    log_detail(f"\n--- 更新历史记录文件: {os.path.basename(file_path)} -> '{group_name}' ---")
    
    # === 新增判断：如果列表为空，则直接跳过不写入 ===
    if not symbols_to_add:
        log_detail(f" - 列表为空，跳过写入历史记录。")
        return
    
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
    
    # 二次保险：如果合并后依然为空，也跳过
    if not updated_symbols:
        return
    
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

# ========== 新增：动态生成白名单 (过去一年涨幅 > 100%) ==========
def generate_whitelist_symbols(db_path, sectors_json_path, target_date_override, log_detail):
    log_detail("\n========== 开始动态生成白名单 (过去一年涨幅 > 100%) ==========")
    
    if not os.path.exists(sectors_json_path):
        log_detail(f"错误: {sectors_json_path} 不存在，无法生成白名单。")
        return []

    with open(sectors_json_path, 'r', encoding='utf-8') as f:
        sectors_data = json.load(f)

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    # 确定基准日期和一年前的日期
    base_date_str = target_date_override if target_date_override else datetime.date.today().isoformat()
    base_date = datetime.datetime.strptime(base_date_str, '%Y-%m-%d')
    one_year_ago = base_date - datetime.timedelta(days=365)
    one_year_ago_str = one_year_ago.strftime('%Y-%m-%d')

    final_symbols = []
    target_sectors = CONFIG["TARGET_SECTORS"]

    for sector, symbols in sectors_data.items():
        if sector not in target_sectors:
            continue
        
        for symbol in symbols:
            query = f"""
                SELECT 
                    (SELECT price FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 1) as latest_price,
                    (SELECT MIN(price) FROM "{sector}" WHERE name = ? AND date >= ? AND date <= ?) as min_price
            """
            try:
                cursor.execute(query, (symbol, base_date_str, symbol, one_year_ago_str, base_date_str))
                row = cursor.fetchone()
                
                if row and row[0] is not None and row[1] is not None:
                    latest_p, min_p = row
                    if min_p > 0:
                        growth = (latest_p - min_p) / min_p
                        if growth > 1.0:  # 原来是 1.5，现在改为 1.0 (即 100%)
                            final_symbols.append(symbol)
            except sqlite3.OperationalError:
                continue

    conn.close()
    log_detail(f"动态白名单生成完成，共命中 {len(final_symbols)} 个 Symbol。")
    return final_symbols

# --- 策略1: PE_Volume (T, T-1, T-2, T-3 放量下跌) ---
def pe_volume(db_path, history_json_path, sector_map, target_date_override, symbol_to_trace, log_detail):
    """
    执行条件8策略：PE_Volume (修改版：T-1, T-2, T-3 检查是否放量且下跌，使用成交额 Price * Volume 进行排名)
    """
    log_detail("\n========== 开始执行 条件8 (PE_Volume - 放量下跌) 策略 ==========")
    
    # 读取配置
    rank_threshold = CONFIG.get("COND8_VOLUME_RANK_THRESHOLD", 3)
    lookback_months = CONFIG.get("COND8_VOLUME_LOOKBACK_MONTHS", 3)
    # [修改点] 获取财报检查天数的配置
    earnings_check_days = CONFIG.get("COND8_EARNINGS_CHECK_DAYS", 2)
    
    log_detail(f"配置参数: 成交额排名阈值 = Top {rank_threshold}, 且必须收盘价下跌")
    log_detail(f"配置参数: 财报日过滤范围 = 前 {earnings_check_days} 天")

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

    # ===== 新增：追踪 symbol 在策略1中的详细状态 =====
    trace_found_in_any_task = False
    
    for hist_date, date_idx, task_name in tasks:
        # 1. 从历史文件中提取该日期的所有 symbol
        symbols_on_date = set()
        for group in target_groups:
            grp_data = history_data.get(group, {})
            if isinstance(grp_data, dict):
                syms = grp_data.get(hist_date, [])
                # *** 关键修改：清洗 symbol ***
                cleaned_syms = [clean_symbol(s) for s in syms]
                symbols_on_date.update(cleaned_syms)
        
        symbols_on_date = sorted(list(symbols_on_date))
        log_detail(f" -> 正在扫描 {task_name} (日期: {hist_date})，包含 {len(symbols_on_date)} 个候选。")

        if symbol_to_trace:
            if symbol_to_trace in symbols_on_date:
                trace_found_in_any_task = True
                log_detail(f"    !!! 目标 {symbol_to_trace} 在 {hist_date} 的历史记录中，开始检查...")
            else:
                log_detail(f"    --- 目标 {symbol_to_trace} 不在 {hist_date} 的历史记录中，跳过该任务。")
        
        for symbol in symbols_on_date:
            is_tracing = (symbol == symbol_to_trace)
            sector = sector_map.get(symbol)
            if not sector:
                if is_tracing: log_detail(f"    x [失败] 未找到 {symbol} 的板块映射。")
                continue
            
            # 获取该股的具体交易日历
            # 获取 5 天: Today(0), T-1(1), T-2(2), T-3(3)
            dates = get_trading_dates_list(cursor, sector, symbol, base_date, limit=5)
            
            if len(dates) < 4:
                if is_tracing: log_detail(f"    x [失败] 交易日数据不足4天。")
                continue
            if dates[date_idx] != hist_date:
                if is_tracing: log_detail(f"    x [失败] 日期对齐不匹配: dates[{date_idx}]={dates[date_idx]} != {hist_date}。")
                continue
            
            query = f'SELECT price, volume, open FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol, dates[0]))
            rows = cursor.fetchall()

            if len(rows) < 2:
                if is_tracing: log_detail(f"    x [失败] 缺少足够的价格数据进行涨跌幅对比。")
                continue

            price_curr, vol_curr, open_curr = rows[0]
            price_prev, vol_prev, _ = rows[1]

            if price_curr is None or price_prev is None or vol_curr is None or open_curr is None:
                if is_tracing: log_detail(f"    x [失败] 价格/成交量数据存在 None。")
                continue

            # ========== 规则修改：必须下跌 (今日收盘 < 昨日收盘 且 今日收盘 < 今日开盘) ==========
            if price_curr >= price_prev or price_curr >= open_curr:
                if is_tracing: log_detail(f"    x [失败] 价格未满足下跌条件 (收盘{price_curr}, 昨收{price_prev}, 今开{open_curr})。")
                continue

            # --- 修改点：计算成交额并调用成交额排名函数 ---
            turnover_curr = price_curr * vol_curr
            
            # 先判断从最近财报日到今天是否是成交额前三
            cursor.execute("SELECT date FROM Earning WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 1", (symbol, dates[0]))
            er_row = cursor.fetchone()
            
            vol_cond = False
            if er_row:
                er_date_str = er_row[0]
                if is_tracing: log_detail(f"    - 检查财报日起成交额排名 (财报日: {er_date_str})")
                vol_cond = check_turnover_since_earning(
                    cursor, sector, symbol, er_date_str, dates[0], turnover_curr,
                    rank_threshold, log_detail, is_tracing
                )
            
            # 如果不是，再判断1.5个月这个步骤
            if not vol_cond:
                if is_tracing: log_detail(f"    - 财报日起未满足前{rank_threshold}，检查过去 {CONFIG['COND8_VOLUME_LOOKBACK_MONTHS']} 个月排名")
                vol_cond = check_turnover_rank(
                    cursor, sector, symbol, dates[0], turnover_curr, 
                    CONFIG["COND8_VOLUME_LOOKBACK_MONTHS"], 
                    rank_threshold, 
                    log_detail, is_tracing
                )
            
            if not vol_cond:
                if is_tracing: log_detail(f"    x [失败] 成交额排名未进入前{rank_threshold}。")
                continue

            if vol_cond:
                # ================== 财报日过滤逻辑 ==================
                # 1. 检查今日(dates[0])是否为财报日
                if check_is_earnings_day(cursor, symbol, dates[0]):
                    if is_tracing: log_detail(f"    🛑 [过滤] 今日({dates[0]}) 为财报日，剔除。")
                    continue
                
                # 2. [新增] 检查前面三天 (T-1, T-2, T-3) 是否为财报日
                has_recent_earnings = False
                # [修改点] 使用配置项 earnings_check_days 来控制循环范围
                for i in range(1, min(earnings_check_days + 1, len(dates))):
                    if check_is_earnings_day(cursor, symbol, dates[i]):
                        if is_tracing: log_detail(f"    🛑 [过滤] 前面第{i}天({dates[i]}) 为财报日，剔除。")
                        has_recent_earnings = True
                        break # 只要有一天是财报日，就跳出循环
                
                # 如果前三天内有财报日，则跳过该 symbol
                if has_recent_earnings:
                    continue

                candidates_volume.add(symbol)
                if is_tracing: log_detail(f"    ✅ [通过] {task_name} 放量下跌条件满足！(Price: {price_prev}->{price_curr})")

    conn.close()
    result_list = sorted(list(candidates_volume))
    log_detail(f"条件8 (PE_Volume) 筛选完成，共命中 {len(result_list)} 个: {result_list}")

    # ===== 新增：策略1 追踪总结 =====
    if symbol_to_trace:
        log_detail(f"\n📌 [策略1总结] {symbol_to_trace}:")
        if not trace_found_in_any_task:
            log_detail(f"    ❌ 未命中 — 原因: 在 T/T-1/T-2/T-3 四天的历史记录池中均未出现。")
        elif symbol_to_trace in result_list:
            log_detail(f"    ✅ 命中 PE_Volume")
        else:
            log_detail(f"    ❌ 未命中 — 原因: 虽然出现在历史池中，但未通过后续筛选条件（见上方详细日志）。")

    return result_list

def check_pe_volume_retention(db_path, history_json_path, panel_json_path, current_pe_volume, sector_map, target_date_override, symbol_to_trace, log_detail):
    """
    回溯逻辑：检查前一天的 PE_Volume 成员。
    如果满足：
    1. 不在今天的 current_pe_volume 中
    2. 收盘价下降 且 收盘价低于开盘价 (无论量级涨跌)
    3. 存在于今天的 [扩展后的深跌池] 中
    则将其捞回。
    """
    log_detail("\n========== 执行 PE_Volume 回溯保留机制 (Retention Check) ==========")
    
    # 1. 确定日期
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    # 2. 加载历史记录，找到"前一天"的 PE_Volume 列表
    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
        
        hist_pe_vol = history_data.get("PE_Volume", {})
        if not hist_pe_vol:
            log_detail("    x 历史记录中无 PE_Volume 数据，跳过回溯。")
            if symbol_to_trace:
                log_detail(f"📌 [回溯总结] {symbol_to_trace}: ❌ 无历史数据可回溯。")
            return []
            
        sorted_dates = sorted(hist_pe_vol.keys())
        
        prev_date = None
        for d in reversed(sorted_dates):
            if d < base_date:
                prev_date = d
                break
        
        if not prev_date:
            log_detail(f"    x 无法找到 {base_date} 之前的历史记录，跳过回溯。")
            if symbol_to_trace:
                log_detail(f"📌 [回溯总结] {symbol_to_trace}: ❌ 无前期历史记录。")
            return []
            
        prev_symbols_raw = hist_pe_vol[prev_date]
        prev_symbols = set([clean_symbol(s) for s in prev_symbols_raw])
        sorted_prev_symbols = sorted(list(prev_symbols))
        log_detail(f"    -> 找到上一期 ({prev_date}) PE_Volume 记录: {len(prev_symbols)} 个: {sorted_prev_symbols}")
        
    except Exception as e:
        log_detail(f"    x 读取历史文件失败: {e}")
        return []

    # 3. 加载 Panel 文件，获取当前存在的 Deep/Valid 等池子
    valid_pool = set()
    target_pool_names = [
        "PE_Deep", "PE_Deeper", "OverSell_W", "PE_W", 
        "PE_valid", "PE_invalid", "season"
    ]
    
    try:
        with open(panel_json_path, 'r', encoding='utf-8') as f:
            panel_data = json.load(f)
        
        for name in target_pool_names:
            group_data = panel_data.get(name, {})
            if isinstance(group_data, dict):
                valid_pool.update(group_data.keys())
        log_detail(f"    -> 已加载扩展后的验证池 ({'/'.join(target_pool_names)}): 共 {len(valid_pool)} 个 unique symbol")
    except Exception as e:
        log_detail(f"    x 读取 Panel 文件失败: {e}")
        return []

    # ===== 新增：追踪 symbol 是否在上期列表中 =====
    if symbol_to_trace:
        if symbol_to_trace in prev_symbols:
            log_detail(f"    !!! 目标 {symbol_to_trace} 在上期 PE_Volume 列表中，开始逐条件检查...")
        else:
            log_detail(f"    --- 目标 {symbol_to_trace} 不在上期 PE_Volume 列表中，无需回溯。")

    # 4. 遍历筛选
    retention_list = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    current_set = set(current_pe_volume)

    for symbol in prev_symbols:
        is_tracing = (symbol == symbol_to_trace)
        
        # 条件1: 不在今天写入的最新的 pe_volume 里
        if symbol in current_set:
            if is_tracing: log_detail(f"    --- [回溯] {symbol}: 已在今日 PE_Volume 中，无需捞回，跳过。")
            continue
            
        # 条件3: 必须在扩展后的深跌池/验证池里
        if symbol not in valid_pool:
            if is_tracing: log_detail(f"    x [回溯] {symbol}: 不在验证池 ({'/'.join(target_pool_names)}) 中，无法捞回。")
            continue

        sector = sector_map.get(symbol)
        if not sector:
            if is_tracing: log_detail(f"    x [回溯] {symbol}: 未找到板块映射，跳过。")
            continue

        query = f'SELECT date, price, volume, open FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2'
        cursor.execute(query, (symbol, base_date))
        rows = cursor.fetchall()

        if len(rows) < 2:
            if is_tracing: log_detail(f"    x [回溯] {symbol}: 交易数据不足2天，跳过。")
            continue
        
        date_curr, price_curr, vol_curr, open_curr = rows[0]
        date_prev, price_prev, vol_prev, _ = rows[1]

        if None in [price_curr, vol_curr, price_prev, vol_prev, open_curr]:
            if is_tracing: log_detail(f"    x [回溯] {symbol}: 价格/成交量数据存在 None，跳过。")
            continue

        # 条件2: 收盘价降低 且 收盘价低于开盘价 (已移除 Turnover 下降的限制)
        cond_price_down = price_curr < price_prev
        cond_close_below_open = price_curr < open_curr
        
        if is_tracing:
            log_detail(f"    - [回溯] {symbol} 条件检查:")
            log_detail(f"      收盘价下跌: {price_prev:.2f} -> {price_curr:.2f} = {cond_price_down}")
            log_detail(f"      收盘<开盘: {price_curr:.2f} < {open_curr:.2f} = {cond_close_below_open}")
        
        if cond_price_down and cond_close_below_open:
            retention_list.append(symbol)
            log_detail(f"    + [捞回] {symbol}: 上期存在且继续下跌 (Price: {price_prev}->{price_curr}, Open: {open_curr})")
        else:
            if is_tracing:
                log_detail(f"    x [回溯] {symbol}: 未满足下跌条件，未捞回。")

    conn.close()

    # ===== 新增：回溯追踪总结 =====
    if symbol_to_trace:
        if symbol_to_trace not in prev_symbols:
            log_detail(f"📌 [回溯总结] {symbol_to_trace}: ❌ 不在上期列表中，无需回溯。")
        elif symbol_to_trace in retention_list:
            log_detail(f"📌 [回溯总结] {symbol_to_trace}: ✅ 被捞回")
        else:
            log_detail(f"📌 [回溯总结] {symbol_to_trace}: ❌ 在上期列表中但未满足捞回条件（见上方详细日志）。")

    return retention_list

# --- 策略2: PE_Volume_up (T, T-1, T-2 活跃且今日上涨) ---
def process_pe_volume_up(db_path, history_json_path, sector_map, target_date_override, symbol_to_trace, log_detail):
    log_detail("\n========== 开始执行 策略2 (PE_Volume_up) ==========")
    
    # 配置参数
    lookback_days = CONFIG.get("COND_UP_HISTORY_LOOKBACK_DAYS", 5) 
    # 修改点：放量检查回溯月份改为3个月
    vol_rank_months = CONFIG.get("COND_UP_VOL_RANK_MONTHS", 2)
    vol_rank_threshold = CONFIG.get("COND_UP_VOL_RANK_THRESHOLD", 4)
    
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
                # *** 关键修改：清洗 symbol ***
                cleaned_syms = [clean_symbol(s) for s in syms]
                candidate_symbols.update(cleaned_syms)
    
    candidate_symbols = sorted(list(candidate_symbols))
    log_detail(f"在 T, T-1, T-2 的历史记录中共扫描到 {len(candidate_symbols)} 个候选 Symbol。")

    # ===== 新增：追踪 symbol 候选池检查 =====
    if symbol_to_trace:
        if symbol_to_trace in candidate_symbols:
            log_detail(f"    !!! 目标 {symbol_to_trace} 在策略2候选池中，将进行条件检查...")
        else:
            log_detail(f"    --- 目标 {symbol_to_trace} 不在策略2候选池中 (未在扫描日期的历史记录中找到)。")

    results = []
    
    # 3. 逐个检查逻辑
    for symbol in candidate_symbols:
        is_tracing = (symbol == symbol_to_trace)
        sector = sector_map.get(symbol)
        if not sector: continue
        
        if is_tracing: log_detail(f"--- 正在检查 {symbol} (策略2) ---")

        # 【修改点 1】将 LIMIT 从 3 改为 8，以便获取今日 + 过去 7 天的数据
        query = f'SELECT date, price, volume, open FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 8'
        cursor.execute(query, (symbol, base_date))
        rows = cursor.fetchall()
        
        # 至少需要 T 和 T-1 进行涨跌判断
        if len(rows) < 2:
            if is_tracing: log_detail(f"    x 数据不足2天，跳过。")
            continue
            
        # rows[0]=T, rows[1]=T-1, rows[2]=T-2 (可能不存在)
        # 提取数据
        date_curr, price_curr, vol_curr, open_curr = rows[0]
        date_prev, price_prev, vol_prev, _ = rows[1]
        
        if None in [price_curr, price_prev, vol_curr, vol_prev, open_curr]: continue

        # 计算成交额 (Turnover)
        turnover_curr = price_curr * vol_curr
        turnover_prev = price_prev * vol_prev

        # 规则1 (硬性): 必须上涨 (最新价 > 次新价 且 收盘价 > 开盘价)
        if price_curr <= price_prev or price_curr <= open_curr:
            if is_tracing: log_detail(f"    x 价格未上涨 (收盘{price_curr} <= 昨收{price_prev} 或 <= 今开{open_curr})，跳过。")
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
        if turnover_curr > turnover_prev:
            # === 分支 A: 放量上涨 ===
            # 修改点: 检查今日(T)是否为 3个月内前3名
            is_top_vol = check_turnover_rank(
                cursor, sector, symbol, date_curr, turnover_curr, 
                vol_rank_months, vol_rank_threshold, log_detail, is_tracing
            )
            if is_top_vol:
                is_match = True
                reason = "放量上涨 (3个月Top3)"
            else:
                if is_tracing: log_detail(f"    x 放量但未满足3个月Top{vol_rank_threshold}。")
        else:
            # === 分支 B: 缩量上涨 ===
            # 修改点: 检查 T, T-1, T-2 中是否有任意一天是"3个月内前3名"
            # 已经满足: 量缩 (vol_curr < vol_prev) 且 价涨 (price_curr > price_prev)
            
            # 检查列表中的每一天 (T, T-1, T-2)
            has_high_volume_history = False
            
            # 检查 T, T-1, T-2
            for i in range(min(3, len(rows))):
                d_date, d_price, d_vol, _ = rows[i]
                if d_vol is None or d_price is None: continue
                
                # 2. 必须计算那一天的成交额
                d_turnover = d_price * d_vol 
                
                # 3. 传入 d_turnover 而不是 d_vol
                is_high = check_turnover_rank(
                    cursor, sector, symbol, d_date, d_turnover,
                    vol_rank_months, vol_rank_threshold, log_detail, False 
                )
                if is_high:
                    has_high_volume_history = True
                    if is_tracing: log_detail(f"    -> 发现高成交额日: {d_date} (TO:{d_turnover:,.0f})")
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

    # ===== 新增：策略2 追踪总结 =====
    if symbol_to_trace:
        if symbol_to_trace not in candidate_symbols:
            log_detail(f"📌 [策略2总结] {symbol_to_trace}: ❌ 未命中 — 不在候选池中。")
        elif symbol_to_trace in results:
            log_detail(f"📌 [策略2总结] {symbol_to_trace}: ✅ 命中 PE_Volume_up")
        else:
            log_detail(f"📌 [策略2总结] {symbol_to_trace}: ❌ 未命中 — 在候选池中但未通过筛选条件（见上方详细日志）。")

    return sorted(results)

# --- 策略3: PE_Volume_high (财报持续上升 + 价格突破 + 成交额放量) ---
def process_pe_volume_high(db_path, history_json_path, panel_json_path, sector_map, target_date_override, symbol_to_trace, log_detail, symbol_to_tags_map, hot_tags_t):
    """
    执行策略3：PE_Volume_high
    返回四个分类：
    - 甲类: 两次财报递增 + 最新财报涨跌幅>0 + 价格突破 + 成交额12个月前3名
    - 乙类: 最新财报涨跌幅>0 + 未突破 + 成交额6个月前3名
    - 丙类: (无需财报递增/涨跌幅要求) + 价格突破 + 成交额45天前3名
    - 抄底类: 最新日期到最近财报之间曾入选 PE_Volume_high 且今日在指定回调池中
    """
    log_detail("\n========== 开始执行 策略3 (PE_Volume_high - 财报突破放量 & 抄底扫描) ==========")
    
    # 读取配置
    turnover_lookback_months = CONFIG.get("COND_HIGH_TURNOVER_LOOKBACK_MONTHS", 12)
    turnover_rank_threshold = CONFIG.get("COND_HIGH_TURNOVER_RANK_THRESHOLD", 3)
    
    # [新增] 读取丙类专用配置
    bing_lookback_days = CONFIG.get("COND_HIGH_TURNOVER_BING_DAYS", 45)
    bing_rank_threshold = CONFIG.get("COND_HIGH_TURNOVER_BING_RANK_THRESHOLD", 3)
    
    log_detail(f"配置参数: 成交额回溯 = {turnover_lookback_months} 个月(甲类) / 6 个月(乙类) / {bing_lookback_days} 天(丙类), 排名阈值 = Top {turnover_rank_threshold}")
    
    # 确定基准日期 (提前确定以供加载 pool 使用)
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    log_detail(f"基准日期: {base_date}")

    # 加载历史记录
    hist_pe_vol_high = {}
    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            hist_data = json.load(f)
            hist_pe_vol_high = hist_data.get("PE_Volume_high", {})
    except Exception as e:
        log_detail(f"读取历史文件失败: {e}")
        hist_data = {}

    # ================= 修复点：加载当前回调池 (拆分基础池和扩展池) =================
    base_valid_pool = set()
    extended_valid_pool = set()
    
    base_pool_names = ["PE_W", "PE_Deep", "PE_Deeper", "OverSell_W"]
    extended_pool_names = ["PE_valid", "PE_invalid", "season"]
    
    try:
        # 优先从 History 中读取 base_date 当天的跌幅池数据，以支持回测
        if hist_data:
            for name in base_pool_names:
                group_history = hist_data.get(name, {})
                if base_date in group_history:
                    # 清洗 symbol 后加入
                    clean_syms = [clean_symbol(s) for s in group_history[base_date]]
                    base_valid_pool.update(clean_syms)
            
            for name in extended_pool_names:
                group_history = hist_data.get(name, {})
                if base_date in group_history:
                    clean_syms = [clean_symbol(s) for s in group_history[base_date]]
                    extended_valid_pool.update(clean_syms)
        
        # 如果在 history 中没有找到当天的任何数据（可能是实盘当天还没写入 history），则降级从 Panel 读取
        if not base_valid_pool and not target_date_override:
            with open(panel_json_path, 'r', encoding='utf-8') as f:
                panel_data = json.load(f)
                for name in base_pool_names:
                    group_data = panel_data.get(name, {})
                    if isinstance(group_data, dict):
                        base_valid_pool.update(group_data.keys())
                for name in extended_pool_names:
                    group_data = panel_data.get(name, {})
                    if isinstance(group_data, dict):
                        extended_valid_pool.update(group_data.keys())
                        
        log_detail(f"已加载基础跌幅池 (日期: {base_date})，共 {len(base_valid_pool)} 个候选抄底 Symbol。")
        log_detail(f"已加载扩展跌幅池 (PE_valid/invalid)，共 {len(extended_valid_pool)} 个候选抄底 Symbol。")
    except Exception as e:
        log_detail(f"读取跌幅池数据失败: {e}")
    # =======================================================
    
    # 四个分类的结果集
    results_jia = []     # 甲类
    results_yi = []      # 乙类 (新)
    results_bing = []    # 丙类 (原乙类)
    results_chaodi = []  # 抄底类
    
    # 连接数据库
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    
    # 遍历所有 symbol
    all_symbols = list(sector_map.keys())
    log_detail(f"开始扫描 {len(all_symbols)} 个 Symbol...")
    
    for symbol in all_symbols:
        is_tracing = (symbol == symbol_to_trace)
        sector = sector_map.get(symbol)
        if not sector:
            continue
        
        # [新增] 获取当前 symbol 的所有 tags，并检查是否命中 HOT_TAGS_T
        s_tags = set(symbol_to_tags_map.get(symbol, []))
        has_hot_tag_t = bool(s_tags.intersection(hot_tags_t))
        
        if is_tracing:
            log_detail(f"\n--- 正在检查 {symbol} (策略3) ---")
        
        # 1. 财报数据检查
        if target_date_override:
            cursor.execute("SELECT date, price FROM Earning WHERE name = ? AND date <= ? ORDER BY date ASC", (symbol, target_date_override))
        else:
            cursor.execute("SELECT date, price FROM Earning WHERE name = ? ORDER BY date ASC", (symbol,))
        
        er_rows = cursor.fetchall()
        
        # 至少需要1次财报记录
        if len(er_rows) < 1:
            if is_tracing:
                log_detail(f"    x [失败] 无财报记录")
            continue
        
        all_er_dates = [r[0] for r in er_rows]
        latest_er_date = all_er_dates[-1]
        latest_er_pct = er_rows[-1][1]  # Earning表里的price列其实是pct
        
        if is_tracing:
            log_detail(f"    - 财报记录: {len(er_rows)} 次, 最新财报日: {latest_er_date}, 涨跌幅: {latest_er_pct}")
        
        # 2. 财报日价格
        placeholders = ', '.join(['?'] * len(all_er_dates))
        query = f'SELECT date, price FROM "{sector}" WHERE name = ? AND date IN ({placeholders}) ORDER BY date ASC'
        cursor.execute(query, (symbol, *all_er_dates))
        price_data = cursor.fetchall()
        
        if len(price_data) != len(all_er_dates):
            if is_tracing:
                log_detail(f"    x [失败] 财报日收盘价数据不完整")
            continue
        
        all_er_prices = [p[1] for p in price_data]
        latest_er_price = all_er_prices[-1]
        
        # 3. 计算财报条件
        cond_er_increasing = (len(er_rows) >= 2 and latest_er_price > all_er_prices[-2])
        cond_er_pct_positive = (latest_er_pct is not None and latest_er_pct > 0)
        
        # ========== 步骤3: 计算各项条件 ==========
        
        # 条件A: 两次财报递增 (需要至少2次财报)
        cond_er_increasing = False
        if len(er_rows) >= 2:
            prev_er_price = all_er_prices[-2]
            cond_er_increasing = (latest_er_price > prev_er_price)
            if is_tracing:
                log_detail(f"    - 条件A (财报价格递增): {prev_er_price:.2f} -> {latest_er_price:.2f} = {cond_er_increasing}")
        else:
            if is_tracing:
                log_detail(f"    - 条件A (财报价格递增): 仅1次财报，无法判断 = False")
        
        # 条件B: 最新财报涨跌幅 > 0
        cond_er_pct_positive = (latest_er_pct is not None and latest_er_pct > 0)
        if is_tracing:
            log_detail(f"    - 条件B (财报涨跌幅>0): {latest_er_pct} > 0 = {cond_er_pct_positive}")
        
        # 4. 获取最新交易数据
        if target_date_override:
            query = f'SELECT date, price, volume, open FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol, target_date_override))
        else:
            query = f'SELECT date, price, volume, open FROM "{sector}" WHERE name = ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol,))
        
        rows = cursor.fetchall()
        
        # 修正：确保这里能正确解包 prev_volume
        if len(rows) < 2 or rows[0][1] is None or rows[0][2] is None or rows[0][3] is None or rows[1][1] is None or rows[1][2] is None:
            if is_tracing:
                log_detail(f"    x [失败] 无法获取最新两天交易数据")
            continue
        
        latest_date, latest_price, latest_volume, latest_open = rows[0]
        prev_date, prev_price, prev_volume, _ = rows[1]
        
        latest_turnover = latest_price * latest_volume
        prev_turnover = prev_price * prev_volume
        
        # 门槛 1: 成交额大于 2 亿
        if latest_turnover < 200000000:
            if is_tracing:
                log_detail(f"    x [过滤] 最新成交额 {latest_turnover:,.0f} 不足 20000 万 (2亿)，跳过。")
            continue
        
        # ================= 抄底逻辑 (不受今日上涨/放量门槛限制) =================
        cond_chaodi = False
        
        # 1. 检查历史：从最新财报日到今天，该股是否以"甲"类进入过 PE_Volume_high
        was_in_high_history = False
        latest_jia_history_date = None  # 追踪最近一次有效历史出现的日期，用于路径C
        
        for h_date, h_symbols_raw in hist_pe_vol_high.items():
            if latest_er_date <= h_date <= latest_date:
                # 遍历该日期的所有记录（保留后缀）
                for s_with_suffix in h_symbols_raw:
                    # 清洗后获取纯净 symbol
                    clean_sym = clean_symbol(s_with_suffix)
                    
                    # 如果 symbol 匹配
                    if clean_sym == symbol:
                        # [修改] 检查是否满足条件：甲，或者 (乙/丙 且 包含 HOT_TAGS_T)
                        is_valid_history = False
                        if "甲" in s_with_suffix:
                            is_valid_history = True
                        elif ("乙" in s_with_suffix or "丙" in s_with_suffix) and has_hot_tag_t:
                            is_valid_history = True
                            
                        if is_valid_history:
                            was_in_high_history = True
                            if is_tracing:
                                log_detail(f"    - 发现历史记录: {h_date} -> {s_with_suffix} (满足抄底历史条件)")
                        
                            # 记录最近一次有效历史出现的日期
                            if latest_jia_history_date is None or h_date > latest_jia_history_date:
                                latest_jia_history_date = h_date
        
        # [说明] 移除了原有的 break，确保遍历所有历史日期找到最近的甲类日期
        
        if is_tracing and latest_jia_history_date:
            log_detail(f"    - 最近有效历史(甲/带Tag的乙丙)出现日期: {latest_jia_history_date}")
        
        if was_in_high_history:
            # 路径 A: 跌幅池抄底 (今日在 PE_W/Deep 等池子里)
            # [修改点] 检查基础池，或者 (带有 HOT_TAGS_T 并且在扩展池中)
            in_base_pool = symbol in base_valid_pool
            in_extended_pool = has_hot_tag_t and (symbol in extended_valid_pool)
            
            if in_base_pool or in_extended_pool:
                cond_chaodi = True
                if is_tracing: 
                    pool_match_reason = "基础回调池" if in_base_pool else "扩展回调池(带HOT_TAGS_T)"
                    log_detail(f"    - 抄底判定: 命中 [回调池路径A] ({pool_match_reason})")
            
            # 路径 B: 放量下跌抄底 (今日价格下跌 且 成交额是近1.5个月前2名)
            else:
                cond_price_down_today = (latest_price < prev_price) and (latest_price < latest_open)
                if cond_price_down_today:
                    # [修改点] 使用 check_turnover_rank_by_days 替代之前的 since_earning 逻辑
                    # 45天即约等于1.5个月
                    lookback_days = CONFIG.get("COND_HIGH_TURNOVER_BING_DAYS", 45) 
                    rank_threshold = 2 # 保持您要求的排名前2名
                    
                    is_top2_recent = check_turnover_rank_by_days(
                        cursor, sector, symbol, latest_date, latest_turnover,
                        lookback_days, rank_threshold, log_detail, is_tracing
                    )
                    
                    if is_top2_recent:
                        cond_chaodi = True
                        if is_tracing: log_detail(f"    - 抄底判定: 命中 [放量下跌路径B] (近{lookback_days}天成交额Top{rank_threshold})")
            
            # [新增] 路径 C: 缩量回调后缩量上涨
            # 条件：甲日之后到昨天，每天都是缩量下跌；今天是缩量上涨
            if not cond_chaodi and latest_jia_history_date is not None:
                cond_c_price_up = (latest_price > prev_price) and (latest_price > latest_open)
                cond_c_turnover_down = (latest_turnover < prev_turnover)
                
                if is_tracing:
                    log_detail(f"    - 路径C检查: 今日缩量上涨? 价格上涨={cond_c_price_up}, 成交额缩量={cond_c_turnover_down}")
                
                if cond_c_price_up and cond_c_turnover_down:
                    # 获取从甲日到今天的所有交易数据（按日期升序）
                    query_c = f'SELECT date, price, volume, open FROM "{sector}" WHERE name = ? AND date >= ? AND date <= ? ORDER BY date ASC'
                    cursor.execute(query_c, (symbol, latest_jia_history_date, latest_date))
                    all_rows_c = cursor.fetchall()

                    # 至少需要: 甲日 + 1个中间日 + 今天 = 3条记录
                    if len(all_rows_c) >= 3:
                        # [新增逻辑] 提取这段时间的所有收盘价，判断今日收盘价是否为最高价
                        all_prices_c = [row[1] for row in all_rows_c if row[1] is not None]
                        max_price_c = max(all_prices_c) if all_prices_c else 0
                        
                        if latest_price >= max_price_c:
                            if is_tracing:
                                log_detail(f"    - 路径C中断: 今日收盘价 {latest_price:.2f} 是自甲日({latest_jia_history_date})以来的最高价，不符合抄底逻辑。")
                        else:
                            all_shrink_down = True
                            for i in range(1, len(all_rows_c) - 1):
                                curr_d, curr_p, curr_v, curr_open = all_rows_c[i]
                                prev_d_c, prev_p_c, prev_v_c, _ = all_rows_c[i - 1]
                                
                                if any(x is None for x in [curr_p, curr_v, prev_p_c, prev_v_c, curr_open]):
                                    all_shrink_down = False
                                    break
                                
                                curr_to = curr_p * curr_v
                                prev_to = prev_p_c * prev_v_c
                                
                                # 缩量下跌：价格下跌 AND 收盘低于开盘 AND 成交额下降
                                if not (curr_p < prev_p_c and curr_p < curr_open and curr_to < prev_to):
                                    all_shrink_down = False
                                    if is_tracing:
                                        log_detail(f"      路径C中断于 {curr_d}: 价格 {prev_p_c:.2f}->{curr_p:.2f}, 开盘 {curr_open:.2f}, 成交额 {prev_to:,.0f}->{curr_to:,.0f}")
                                    break
                            
                            if all_shrink_down:
                                cond_chaodi = True
                                middle_days = len(all_rows_c) - 2
                                if is_tracing:
                                    log_detail(f"    - 抄底判定: 命中 [缩量回调路径C] (甲日: {latest_jia_history_date}, 连续缩量下跌天数: {middle_days})")
                    else:
                        if is_tracing:
                            log_detail(f"    - 路径C: 数据不足，甲日到今天仅 {len(all_rows_c)} 条记录 (需要>=3)")

        if cond_chaodi:
            results_chaodi.append(symbol)
            if is_tracing:
                log_detail(f"    ✅ [选中-抄底类] 满足历史入选+今日回调/放量/缩量回调条件")

        # ================= 甲乙丙类逻辑的基础门槛 =================
        # 门槛 2: 今日上涨 (如果未上涨，则跳过甲乙丙的判断)
        cond_price_up_today = (latest_price > prev_price) and (latest_price > latest_open)

        # 门槛 3: 今日成交额 > 昨日成交额
        cond_turnover_up_today = (latest_turnover > prev_turnover)
        
        if is_tracing:
            log_detail(f"--- 检查 {symbol} ---")
            log_detail(f"    - 今日价: {latest_price}, 昨日价: {prev_price}, 上涨: {cond_price_up_today}")
            log_detail(f"    - 今日额: {latest_turnover:,.0f}, 昨日额: {prev_turnover:,.0f}, 放量: {cond_turnover_up_today}")

        # 如果未上涨 或 未放量，则跳过甲乙丙的判断
        if not (cond_price_up_today and cond_turnover_up_today):
            if is_tracing: log_detail(f"    x [失败] 今日未上涨 且 今日未放量")
            continue 
        
        # 条件D: 价格突破财报日收盘价
        cond_price_breakout = (latest_price >= latest_er_price)
        if is_tracing:
            log_detail(f"    - 条件D (价格突破财报): {latest_price:.2f} > {latest_er_price:.2f} = {cond_price_breakout}")
                
        # ========== 步骤6: 检查成交额条件 ==========
        
        # 条件E: 成交额为12个月前3名 (用于甲类)
        cond_turnover_12m_top3 = check_turnover_rank(
            cursor, sector, symbol, latest_date, latest_turnover,
            turnover_lookback_months, turnover_rank_threshold,
            log_detail, is_tracing
        )

        # [新增修改] 条件E2: 成交额为6个月前3名 (用于乙类)
        cond_turnover_6m_top3 = check_turnover_rank(
            cursor, sector, symbol, latest_date, latest_turnover,
            6, turnover_rank_threshold, # 强制使用6个月
            log_detail, is_tracing
        )

        # [新增] 丙类：检查成交额是否为过去45天的前3名
        cond_turnover_45d_top3 = check_turnover_rank_by_days(
            cursor, sector, symbol, latest_date, latest_turnover,
            bing_lookback_days, bing_rank_threshold,
            log_detail, is_tracing
        )
        
        # ========== 步骤7: 分类判定 ==========
        
        # 甲类: 财报递增 + 财报涨幅>0 + 价格突破 + 今日上涨 + 12月Top3
        if cond_er_increasing and cond_er_pct_positive and cond_price_breakout and cond_turnover_12m_top3:
            results_jia.append(symbol)
            if is_tracing:
                log_detail(f"    ✅ [选中-甲类] 严格条件 + 价格突破 + 12个月Top{turnover_rank_threshold}")
        
        # 乙类: 财报涨幅>0 + 今日上涨 + 6月Top3
        elif cond_er_pct_positive and cond_turnover_6m_top3:
            results_yi.append(symbol)
            if is_tracing:
                log_detail(f"    ✅ [选中-乙类] 财报涨幅>0 + 未突破 + 6个月Top{turnover_rank_threshold}")
        
        # [修改] 丙类: (无需财报要求) + 今日上涨 + 45天前3名
        elif cond_turnover_12m_top3:
            results_bing.append(symbol)
            if is_tracing:
                log_detail(f"    ✅ [选中-丙类] 价格突破 + {bing_lookback_days}天Top{bing_rank_threshold}")
    
    conn.close()
    
    # 去重并排序
    results_jia = sorted(list(set(results_jia)))
    results_yi = sorted(list(set(results_yi)))
    results_bing = sorted(list(set(results_bing)))
    results_chaodi = sorted(list(set(results_chaodi))) # 排序抄底结果
    
    log_detail(f"\n————策略3 Volume_high 最终筛选结果:")
    log_detail(f"  - 甲类 (严格+突破+12月Top{turnover_rank_threshold}): {len(results_jia)} 个: {results_jia}")
    log_detail(f"  - 乙类 (财报涨幅>0+未突破+6月Top{turnover_rank_threshold}): {len(results_yi)} 个: {results_yi}")
    log_detail(f"  - 丙类 (宽松+突破+财报起前3+间隔>3天): {len(results_bing)} 个: {results_bing}")
    log_detail(f"  - 抄底类 (财报后曾入选且今日回调): {len(results_chaodi)} 个: {results_chaodi}")
    
    # ===== 新增：策略3 追踪总结 =====
    if symbol_to_trace:
        in_jia = symbol_to_trace in results_jia
        in_yi = symbol_to_trace in results_yi
        in_bing = symbol_to_trace in results_bing
        in_chaodi = symbol_to_trace in results_chaodi
        if in_jia or in_yi or in_bing or in_chaodi:
            parts = []
            if in_jia: parts.append("甲类")
            if in_yi: parts.append("乙类")
            if in_bing: parts.append("丙类")
            if in_chaodi: parts.append("抄底类")
            log_detail(f"📌 [策略3总结] {symbol_to_trace}: ✅ 命中 PE_Volume_high ({', '.join(parts)})")
        else:
            log_detail(f"📌 [策略3总结] {symbol_to_trace}: ❌ 未命中 PE_Volume_high（见上方详细日志）。")
    
    return results_jia, results_yi, results_bing, results_chaodi

# --- 策略4: ETF_Volume_high (ETF放量突破) ---
def process_etf_volume_high(db_path, target_date_override, symbol_to_trace, log_detail):
    """
    执行策略4：ETF_Volume_high
    规则: (无需财报要求) + 价格上涨(突破) + 成交额12个月前3名
    直接从 "ETFs" 数据表读取所有不重复的 symbol
    """
    log_detail("\n========== 开始执行 策略4 (ETF_Volume_high - ETF放量突破) ==========")
    
    # 共用策略3的成交额参数 (12个月前3名)
    turnover_lookback_months = CONFIG.get("ETF_COND_HIGH_TURNOVER_LOOKBACK_MONTHS", 12)
    turnover_rank_threshold = CONFIG.get("ETF_COND_HIGH_TURNOVER_RANK_THRESHOLD", 3)
    
    # 确定基准日期
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    results = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    
    # 1. 直接从 ETFs 表中获取所有独一无二的 symbol
    try:
        cursor.execute('SELECT DISTINCT name FROM "ETFs"')
        all_etfs = [r[0] for r in cursor.fetchall()]
        log_detail(f"从 ETFs 表中成功获取 {len(all_etfs)} 个 Symbol 进行扫描...")
    except Exception as e:
        log_detail(f"错误: 无法读取 ETFs 数据表: {e}")
        conn.close()
        return []
        
    for symbol in all_etfs:
        is_tracing = (symbol == symbol_to_trace)
        
        if is_tracing:
            log_detail(f"\n--- 正在检查 ETF {symbol} (策略4) ---")
            
        # 获取最新两天交易数据 (Today, Yesterday)
        if target_date_override:
            query = f'SELECT date, price, volume, open FROM "ETFs" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol, target_date_override))
        else:
            query = f'SELECT date, price, volume, open FROM "ETFs" WHERE name = ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol,))
        
        rows = cursor.fetchall()
        
        # 数据完整性检查
        if len(rows) < 2 or rows[0][1] is None or rows[0][2] is None or rows[0][3] is None or rows[1][1] is None:
            if is_tracing: log_detail(f"    x [失败] 无法获取最新两天的交易数据")
            continue
            
        latest_date, latest_price, latest_volume, latest_open = rows[0]
        prev_date, prev_price, prev_volume, _ = rows[1]
        latest_turnover = latest_price * latest_volume
        
        # 条件1: 价格突破 (ETF无财报，这里定义为今日上涨。若需改写为突破 N 日新高，可在此处扩展逻辑)
        cond_price_up = (latest_price > prev_price) and (latest_price > latest_open)
        if is_tracing:
            log_detail(f"    - 条件A (今日上涨/突破): {prev_price:.2f} -> {latest_price:.2f} = {cond_price_up}")
            
        if not cond_price_up:
            continue
            
        # 条件2: 成交额为 12 个月前 2 名
        cond_turnover_12m_top2 = check_turnover_rank(
            cursor, "ETFs", symbol, latest_date, latest_turnover,
            turnover_lookback_months, turnover_rank_threshold,
            log_detail, is_tracing
        )
        
        # 满足所有条件
        if cond_price_up and cond_turnover_12m_top2:
            results.append(symbol)
            if is_tracing: log_detail(f"    ✅ [选中-ETF类] 价格上涨 + 12个月成交额Top2")
            
    conn.close()
    
    results = sorted(list(set(results)))
    log_detail(f"\n策略4 筛选完成，共命中 {len(results)} 个 ETF: {results}")
    
    return results

# --- 策略5: ETF_Volume_low (ETF触底放量) ---
def process_etf_volume_low(db_path, target_date_override, symbol_to_trace, log_detail):
    """
    执行策略5：ETF_Volume_low
    规则: 比最近半年的最高点低超过11% + 最新日期或前一日的成交额为最近3个月的前 N 名 + 放量日必须下跌且T日必须下跌
    """
    log_detail("\n========== 开始执行 策略5 (ETF_Volume_low - ETF触底放量) ==========")
    
    # 读取配置
    price_lookback_months = CONFIG.get("ETF_COND_LOW_PRICE_LOOKBACK_MONTHS", 6)
    drop_threshold = CONFIG.get("ETF_COND_LOW_DROP_THRESHOLD", 0.11)
    turnover_lookback_months = CONFIG.get("ETF_COND_LOW_TURNOVER_MONTHS", 3)
    # [新增] 读取排名阈值配置，默认值为 2
    turnover_rank_threshold = CONFIG.get("ETF_COND_LOW_TURNOVER_RANK_THRESHOLD", 2) 
    
    # 确定基准日期
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    results = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT DISTINCT name FROM "ETFs"')
        all_etfs = [r[0] for r in cursor.fetchall()]
        log_detail(f"从 ETFs 表中成功获取 {len(all_etfs)} 个 Symbol 进行扫描 (策略5)...")
    except Exception as e:
        log_detail(f"错误: 无法读取 ETFs 数据表: {e}")
        conn.close()
        return []
        
    for symbol in all_etfs:
        is_tracing = (symbol == symbol_to_trace)
        if is_tracing:
            log_detail(f"\n--- 正在检查 ETF {symbol} (策略5) ---")
            
        # 1. 计算寻找最高点的起始日期 (回溯半年)
        try:
            dt = datetime.datetime.strptime(base_date, "%Y-%m-%d")
            start_date_price = dt - datetime.timedelta(days=price_lookback_months * 30)
            start_date_price_str = start_date_price.strftime("%Y-%m-%d")
        except Exception:
            continue
            
        # 修改点：至少需要获取 3 天的数据，以便计算 T-1 日是否下跌
        query = f'SELECT date, price, volume FROM "ETFs" WHERE name = ? AND date >= ? AND date <= ? ORDER BY date DESC'
        cursor.execute(query, (symbol, start_date_price_str, base_date))
        rows = cursor.fetchall()
        
        if len(rows) < 3:
            if is_tracing: log_detail("    x [失败] 数据不足 3 天")
            continue
            
        latest_date, latest_price, latest_volume = rows[0]
        prev_date, prev_price, prev_volume = rows[1]
        prev_prev_date, prev_prev_price, prev_prev_volume = rows[2]
        
        if latest_price is None or prev_price is None or prev_prev_price is None or latest_volume is None or prev_volume is None:
            continue
            
        latest_turnover = latest_price * latest_volume
        prev_turnover = prev_price * prev_volume
        
        # 新增：T日必须是下跌状态（收盘价 < 昨收价）
        cond_latest_down = latest_price < prev_price
        if not cond_latest_down:
            if is_tracing: log_detail(f"    x [过滤] T日未下跌 (当前价 {latest_price:.2f} >= 昨收价 {prev_price:.2f})")
            continue

        valid_prices = [r[1] for r in rows if r[1] is not None]
        max_price = max(valid_prices)
        
        cond_price_drop = latest_price <= max_price * (1 - drop_threshold)
        
        if is_tracing:
            drop_pct = (1 - latest_price / max_price) if max_price > 0 else 0
            log_detail(f"    - 条件A (跌幅>{drop_threshold*100}%): {price_lookback_months}个月最高价 {max_price:.2f}, 当前价 {latest_price:.2f}, 跌幅 {drop_pct:.2%} = {cond_price_drop}")
            
        if not cond_price_drop:
            continue
            
        # 3. 条件B: T日或T-1日的成交额为最近 3 个月前 N 名
        # 检查 T 日放量
        cond_latest_turnover_topN = check_turnover_rank(
            cursor, "ETFs", symbol, latest_date, latest_turnover,
            turnover_lookback_months, turnover_rank_threshold, log_detail, is_tracing
        )
        
        cond_prev_turnover_topN = False
        cond_prev_down = prev_price < prev_prev_price
        
        # 如果 T 日不是最高，则检查 T-1 日
        if not cond_latest_turnover_topN:
            cond_prev_turnover_topN = check_turnover_rank(
                cursor, "ETFs", symbol, prev_date, prev_turnover,
                turnover_lookback_months, turnover_rank_threshold, log_detail, is_tracing
            )
            
        # 修改点：放量日必须下跌。因为前面已经确保 T 日下跌，所以如果 T 日放量则直接满足。如果 T-1 日放量，则要求 T-1 日也必须下跌。
        cond_turnover_high_and_down = cond_latest_turnover_topN or (cond_prev_turnover_topN and cond_prev_down)
        
        if is_tracing:
            log_detail(f"    - 条件B (放量且下跌): T日放量={cond_latest_turnover_topN}, T-1日放量={cond_prev_turnover_topN}, T-1日下跌={cond_prev_down} -> 综合满足={cond_turnover_high_and_down}")
            
        if cond_price_drop and cond_turnover_high_and_down:
            results.append(symbol)
            if is_tracing: log_detail(f"    ✅ [选中-ETF类] 跌幅达标 + 阶段巨量且下跌")
            
    conn.close()
    
    results = sorted(list(set(results)))
    log_detail(f"\n策略5 筛选完成，共命中 {len(results)} 个 ETF: {results}")
    
    return results

def check_turnover_since_earning(cursor, sector_name, symbol, er_date_str, latest_date_str, latest_turnover, rank_threshold, log_detail, is_tracing):
    """
    检查 latest_turnover 是否是从 er_date_str (财报日) 到 latest_date_str 期间的前 rank_threshold 名成交额
    """
    # 查询从财报日到最新日期的所有交易数据
    query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?'
    cursor.execute(query, (symbol, er_date_str, latest_date_str))
    rows = cursor.fetchall()
    
    # 计算成交额并过滤掉 None 值
    valid_data = []
    for r in rows:
        if r[1] is not None and r[2] is not None:
            turnover = r[1] * r[2]
            valid_data.append((r[0], turnover))
    
    if not valid_data:
        return False
    
    # 按成交额从大到小排序
    sorted_data = sorted(valid_data, key=lambda x: x[1], reverse=True)
    
    # 获取前 rank_threshold 名
    top_n_data = sorted_data[:rank_threshold]
    top_n_turnovers = [item[1] for item in top_n_data]
    
    # 判断最新成交额是否在前 N 名中（或者大于等于第 N 名）
    is_top_n = False
    if len(top_n_turnovers) > 0:
        # 如果数据量少于阈值，且当前值在其中，那肯定是前N名
        # 如果数据量足够，检查是否大于等于第N大的值
        cutoff_value = top_n_turnovers[-1]
        if latest_turnover >= cutoff_value:
            is_top_n = True
    
    if is_tracing:
        log_detail(f"    - 条件F (财报日起前{rank_threshold}): 范围 {er_date_str} ~ {latest_date_str}, 共 {len(valid_data)} 个交易日")
        top_n_str = ", ".join([f"[{d}]: {v:,.0f}" for d, v in top_n_data])
        log_detail(f"      前{rank_threshold}名: {top_n_str}")
        log_detail(f"      当前成交额: {latest_turnover:,.0f} -> 是否前{rank_threshold}: {is_top_n}")
    
    return is_top_n

def check_turnover_rank_by_days(cursor, sector_name, symbol, latest_date_str, latest_turnover, lookback_days, rank_threshold, log_detail, is_tracing):
    """
    检查 latest_turnover (成交额=price*volume) 是否是过去 lookback_days 天内的前 rank_threshold 名
    
    参数:
        lookback_days: 回溯天数（如45天）
    """
    # 计算 N 天前的日期
    try:
        dt = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d")
        start_date = dt - datetime.timedelta(days=lookback_days)
        start_date_str = start_date.strftime("%Y-%m-%d")
    except Exception:
        return False

    # 查询过去 N 天的所有日期、价格和成交量
    query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?'
    cursor.execute(query, (symbol, start_date_str, latest_date_str))
    rows = cursor.fetchall()
    
    # 计算成交额并过滤掉 None 值
    valid_data = []
    for r in rows:
        if r[1] is not None and r[2] is not None:
            turnover = r[1] * r[2]
            valid_data.append((r[0], turnover))
    
    if not valid_data:
        return False
    
    # 按成交额从大到小排序
    sorted_data = sorted(valid_data, key=lambda x: x[1], reverse=True)
    
    # 截取前 N 名
    top_n_data = sorted_data[:rank_threshold]
    top_n_turnovers = [item[1] for item in top_n_data]
    
    # 判定逻辑
    is_top_n = False
    if latest_turnover in top_n_turnovers:
        is_top_n = True
    elif len(top_n_turnovers) >= rank_threshold and latest_turnover >= top_n_turnovers[rank_threshold - 1]:
        is_top_n = True
    
    if is_tracing:
        log_detail(f"    - 条件F (成交额排名-丙类): 回溯{lookback_days}天，共{len(valid_data)}个交易日")
        top_n_str = ", ".join([f"[{d}]: {v:,.0f}" for d, v in top_n_data])
        log_detail(f"      前{rank_threshold}名: {top_n_str}")
        log_detail(f"      当前成交额: {latest_turnover:,.0f} -> 在前{rank_threshold}名: {is_top_n}")
    
    return is_top_n

def check_turnover_rank(cursor, sector_name, symbol, latest_date_str, latest_turnover, lookback_months, rank_threshold, log_detail, is_tracing):
    """
    检查 latest_turnover (成交额=price*volume) 是否是过去 lookback_months 个月内的前 rank_threshold 名
    """
    # 计算 N 个月前的日期
    try:
        dt = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d")
        start_date = dt - datetime.timedelta(days=lookback_months * 30)
        start_date_str = start_date.strftime("%Y-%m-%d")
    except Exception:
        return False

    # 查询过去 N 个月的所有日期、价格和成交量
    query = f'SELECT date, price, volume FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?'
    cursor.execute(query, (symbol, start_date_str, latest_date_str))
    rows = cursor.fetchall()
    
    # 计算成交额并过滤掉 None 值
    valid_data = []
    for r in rows:
        if r[1] is not None and r[2] is not None:
            turnover = r[1] * r[2]
            valid_data.append((r[0], turnover))
    
    if not valid_data:
        return False
    
    # 按成交额从大到小排序
    sorted_data = sorted(valid_data, key=lambda x: x[1], reverse=True)
    
    # 截取前 N 名
    top_n_data = sorted_data[:rank_threshold]
    top_n_turnovers = [item[1] for item in top_n_data]
    
    # 判定逻辑
    is_top_n = False
    if latest_turnover in top_n_turnovers:
        is_top_n = True
    elif len(top_n_turnovers) >= rank_threshold and latest_turnover >= top_n_turnovers[rank_threshold - 1]:
        is_top_n = True
    
    if is_tracing:
        log_detail(f"    - 条件E (成交额排名): 回溯{lookback_months}个月，共{len(valid_data)}个交易日")
        top_n_str = ", ".join([f"[{d}]: {v:,.0f}" for d, v in top_n_data])
        log_detail(f"      前{rank_threshold}名: {top_n_str}")
        log_detail(f"      当前成交额: {latest_turnover:,.0f} -> 在前{rank_threshold}名: {is_top_n}")
    
    return is_top_n

# ========== 修改：处理 PE_Hot 策略的独立函数 (接收动态白名单 + 增加市值维度 + 10天防暴涨过滤) ==========
def process_pe_hot(db_path, sector_map, target_date_override, panel_json_path, exclude_symbols, whitelist_symbols, log_detail):
    """
    检索 sectors_panel 里的特定分组，如果发现白名单中的 symbol 在这些分组里，
    或者该 symbol 的市值 >= 配置门槛，
    且不在 exclude_symbols (PE_Volume等) 中，并且最新成交额 >= 2亿，
    【新增】且过去10天内的最低收盘价没有比最新收盘价低超过3%，则将其提取出来。
    返回: pe_hot_list (list), pe_hot_notes (dict)
    """
    # [修改点] 读取配置中的市值门槛，默认值为 1500亿
    min_mcap = CONFIG.get("PE_HOT_MIN_MARKET_CAP", 150000000000)
    min_mcap_yi = min_mcap / 100000000  # 转换为“亿”用于日志显示
    
    log_detail(f"\n========== 开始执行 策略: PE_Hot (白名单/超大市值检索 + 2亿成交额过滤 + 10天防暴涨过滤) ==========")
    log_detail(f"配置参数: 超大市值门槛 = {min_mcap_yi:.0f}亿")
    
    # === 修改区域：在这里添加你想要包含的所有深跌/回调池分组 ===
    target_groups = [
        "PE_Deep", 
        "PE_Deeper", 
        "PE_W", 
        "OverSell_W",
        "PE_valid",
        "PE_invalid",
        "season"
    ]
    
    pe_hot_list = []
    pe_hot_notes = {}

    # 确定基准日期
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    # 连接数据库以获取成交额和市值
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    
    # ========== 查询市值 >= min_mcap 的 symbol ==========
    high_mcap_symbols = set()
    try:
        # [修改点] 使用参数化查询替代硬编码
        cursor.execute("SELECT symbol FROM MNSPP WHERE marketcap >= ?", (min_mcap,))
        rows = cursor.fetchall()
        high_mcap_symbols = {r[0] for r in rows}
        log_detail(f"从 MNSPP 表成功获取 {len(high_mcap_symbols)} 个市值 >= {min_mcap_yi:.0f}亿 的 Symbol。")
    except Exception as e:
        log_detail(f"警告: 无法读取 MNSPP 表的市值数据: {e}")
    # =======================================================

    try:
        with open(panel_json_path, 'r', encoding='utf-8') as f:
            panel_data = json.load(f)
            
        for group in target_groups:
            # 检查分组是否存在，避免 key error
            if group in panel_data and isinstance(panel_data[group], dict):
                for sym, note in panel_data[group].items():
                    # 1. 检查是否在动态生成的白名单中，或者市值 >= min_mcap
                    is_whitelist = sym in whitelist_symbols
                    is_high_mcap = sym in high_mcap_symbols
                    
                    if is_whitelist or is_high_mcap:
                        # 2. 检查是否在排除列表(PE_Volume系列)中
                        if sym not in exclude_symbols:
                            
                            # 3. 获取板块信息以查询数据库
                            sector = sector_map.get(sym)
                            if not sector:
                                continue
                                
                            # 4. 【修改】查询最新 10 天的价格和成交量
                            query = f'SELECT price, volume FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 10'
                            cursor.execute(query, (sym, base_date))
                            rows = cursor.fetchall()
                            
                            if rows and rows[0][0] is not None and rows[0][1] is not None:
                                latest_price, latest_volume = rows[0]
                                turnover = latest_price * latest_volume
                                
                                # 5. 判断成交额是否大于等于 2 亿 (200,000,000)
                                if turnover >= 200000000:
                                    
                                    # 6. 【新增】10天防暴涨过滤：10天内最低价不能比最新价低超过3%
                                    valid_prices = [r[0] for r in rows if r[0] is not None]
                                    min_price_10d = min(valid_prices) if valid_prices else latest_price
                                    
                                    # 如果最低价 < 最新价的 97%，说明跌下去又涨上来超过了阈值（或者单边暴涨）
                                    if min_price_10d < latest_price * 0.97:
                                        log_detail(f"    x [过滤-PE_Hot] {sym} 10天内最低价({min_price_10d:.2f})比最新价({latest_price:.2f})低超过3%")
                                    else:
                                        if sym not in pe_hot_list:
                                            pe_hot_list.append(sym)
                                            # 保留它在原分组的备注
                                            pe_hot_notes[sym] = note if note else sym
                                            
                                            # 记录命中原因
                                            reasons = []
                                            if is_whitelist: reasons.append("白名单")
                                            if is_high_mcap: reasons.append("超大市值")
                                            reason_str = "+".join(reasons)
                                            
                                            log_detail(f"    ✅ [选中-PE_Hot] {sym} (来自分组: {group}, 理由: {reason_str}, 成交额: {turnover/100000000:.2f}亿, 10天最低: {min_price_10d:.2f})")
                                else:
                                    log_detail(f"    x [过滤-PE_Hot] {sym} 成交额不足2亿 (仅 {turnover/100000000:.2f}亿)")
                            else:
                                log_detail(f"    x [过滤-PE_Hot] {sym} 无法获取最新交易数据")
    except Exception as e:
        log_detail(f"错误: 读取 Panel 文件或查询数据库执行 PE_Hot 策略失败: {e}")
    finally:
        conn.close()
        
    pe_hot_list = sorted(pe_hot_list)
    log_detail(f"PE_Hot 筛选完成，共命中 {len(pe_hot_list)} 个: {pe_hot_list}")
    return pe_hot_list, pe_hot_notes

# --- 4. 主执行流程 ---
def run_pe_volume_logic(log_detail):
    log_detail("PE_Volume 双策略程序开始运行...")
    if SYMBOL_TO_TRACE: log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")
    
    base_date_str = TARGET_DATE if TARGET_DATE else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    if TARGET_DATE:
        log_detail(f"\n⚠️⚠️⚠️ 注意：当前处于【回测模式】，目标日期：{TARGET_DATE} ⚠️⚠️⚠️")
        log_detail("本次运行将【不会】更新 Panel 和 History JSON 文件。")
    
    # 1. 加载配置和映射
    # [修改] 接收 hot_tags_t
    tag_blacklist, hot_tags, hot_tags_t = load_tag_settings(TAGS_SETTING_JSON_FILE)
    symbol_to_sector_map = load_all_symbols(SECTORS_JSON_FILE, CONFIG["TARGET_SECTORS"])
    symbol_to_tags_map = load_symbol_tags(DESCRIPTION_JSON_FILE)

    if not symbol_to_sector_map:
        log_detail("错误: 无法加载板块映射，程序终止。")
        return

    # ================= 新增：动态生成白名单 =================
    whitelist_symbols = generate_whitelist_symbols(
        DB_FILE, 
        SECTORS_JSON_FILE, 
        TARGET_DATE, 
        log_detail
    )

    # ================= 策略 1 执行 =================
    raw_pe_volume = pe_volume(
        DB_FILE, 
        EARNING_HISTORY_JSON_FILE, 
        symbol_to_sector_map, 
        TARGET_DATE, 
        SYMBOL_TO_TRACE, 
        log_detail
    )
    # 此时 final_pe_volume 仅包含策略1原始结果
    final_pe_volume = sorted(list(set(raw_pe_volume)))

    # 执行回溯保留逻辑 (Retention Check)
    retention_symbols = check_pe_volume_retention(
        DB_FILE,
        EARNING_HISTORY_JSON_FILE,
        PANEL_JSON_FILE,
        final_pe_volume,       # 传入当前的列表，避免重复添加
        symbol_to_sector_map,
        TARGET_DATE,
        SYMBOL_TO_TRACE,
        log_detail
    )
    
    # 将捞回的 symbol 合并进 final_pe_volume
    if retention_symbols:
        final_pe_volume = sorted(list(set(final_pe_volume) | set(retention_symbols)))
        log_detail(f"合并回溯结果后，PE_Volume 总数: {len(final_pe_volume)} (新增 {len(retention_symbols)} 个)")

    # ================= 策略 2 执行 =================
    raw_pe_volume_up = process_pe_volume_up(
        DB_FILE,
        EARNING_HISTORY_JSON_FILE,
        symbol_to_sector_map,
        TARGET_DATE, 
        SYMBOL_TO_TRACE,
        log_detail
    )
    final_pe_volume_up = sorted(list(set(raw_pe_volume_up)))

    # ================= 策略 3 执行 =================
    raw_pe_volume_high_jia, raw_pe_volume_high_yi, raw_pe_volume_high_bing, raw_pe_volume_high_chaodi = process_pe_volume_high(
        DB_FILE, 
        EARNING_HISTORY_JSON_FILE, 
        PANEL_JSON_FILE,           
        symbol_to_sector_map, 
        TARGET_DATE, 
        SYMBOL_TO_TRACE, 
        log_detail,
        symbol_to_tags_map,  # [新增] 传入标签映射
        hot_tags_t           # [新增] 传入 HOT_TAGS_T 集合
    )
    
    # 合并所有策略3的结果用于统一处理
    final_pe_volume_high = sorted(list(set(raw_pe_volume_high_jia) | set(raw_pe_volume_high_yi) | set(raw_pe_volume_high_bing) | set(raw_pe_volume_high_chaodi)))

    # ================= 策略 4 执行 (ETF 放量突破) =================
    raw_etf_volume_high = process_etf_volume_high(
        DB_FILE, 
        TARGET_DATE, 
        SYMBOL_TO_TRACE, 
        log_detail
    )
    final_etf_volume_high = sorted(list(set(raw_etf_volume_high)))

    # ================= 策略 5 执行 (ETF 触底巨量) =================
    raw_etf_volume_low = process_etf_volume_low(
        DB_FILE, 
        TARGET_DATE, 
        SYMBOL_TO_TRACE, 
        log_detail
    )
    final_etf_volume_low = sorted(list(set(raw_etf_volume_low)))

    # ================= Tag 黑名单过滤逻辑 =================
    def filter_blacklisted_tags(symbols):
        # 现已不再剔除，全部保留，以便写入 Panel
        for sym in symbols:
            s_tags = set(symbol_to_tags_map.get(sym, []))
            intersect = s_tags.intersection(tag_blacklist)
            if intersect:
                if sym == SYMBOL_TO_TRACE:
                    log_detail(f"🛑 [Tag过滤] {sym} 命中黑名单标签: {intersect} -> 已保留并标记为'黑'。")
        return sorted(symbols) # 直接返回完整的 sorted(symbols)

    # 对策略结果进行过滤 (用于写入 Panel)
    filtered_pe_volume = filter_blacklisted_tags(final_pe_volume)
    filtered_pe_volume_up = filter_blacklisted_tags(final_pe_volume_up)
    
    # 策略3的子类分别过滤
    filtered_pe_volume_high_jia = filter_blacklisted_tags(raw_pe_volume_high_jia)
    filtered_pe_volume_high_yi = filter_blacklisted_tags(raw_pe_volume_high_yi)
    filtered_pe_volume_high_bing = filter_blacklisted_tags(raw_pe_volume_high_bing)
    filtered_pe_volume_high_chaodi = filter_blacklisted_tags(raw_pe_volume_high_chaodi)
    filtered_pe_volume_high = filter_blacklisted_tags(final_pe_volume_high)

    # === 新增 ===：ETF 过滤
    filtered_etf_volume_high = filter_blacklisted_tags(final_etf_volume_high)
    filtered_etf_volume_low = filter_blacklisted_tags(final_etf_volume_low)

    if SYMBOL_TO_TRACE:
        # (保留原有的 trace 提示)
        if SYMBOL_TO_TRACE in final_pe_volume and SYMBOL_TO_TRACE not in filtered_pe_volume:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略1) 通过，但因黑名单标签将会被打上‘黑’字。")
        if SYMBOL_TO_TRACE in final_pe_volume_up and SYMBOL_TO_TRACE not in filtered_pe_volume_up:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略2) 通过，但因黑名单标签将会被打上‘黑’字。")
        if SYMBOL_TO_TRACE in final_pe_volume_high and SYMBOL_TO_TRACE not in filtered_pe_volume_high:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略3) 通过，但因黑名单标签将会被打上‘黑’字。")
        if SYMBOL_TO_TRACE in final_etf_volume_high and SYMBOL_TO_TRACE not in filtered_etf_volume_high:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略4) 通过，但因黑名单标签将会被打上‘黑’字。")
        if SYMBOL_TO_TRACE in final_etf_volume_low and SYMBOL_TO_TRACE not in filtered_etf_volume_low:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略5) 通过，但因黑名单标签将会被打上‘黑’字。")

    # ================= 检查 PE_Deep / PE_Deeper 交叉 =================
    all_existing_notes = {}
    current_deep_symbols = set()
    try:
        with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f:
            p_data = json.load(f)
            for group_name, group_content in p_data.items():
                if isinstance(group_content, dict):
                    for s, n in group_content.items():
                        if len(n) > len(all_existing_notes.get(s, "")):
                            all_existing_notes[s] = n
            
            if "PE_Deep" in p_data: current_deep_symbols.update(p_data["PE_Deep"].keys())
            if "PE_Deeper" in p_data: current_deep_symbols.update(p_data["PE_Deeper"].keys())
            if "PE_valid" in p_data: current_deep_symbols.update(p_data["PE_valid"].keys())
            if "PE_invalid" in p_data: current_deep_symbols.update(p_data["PE_invalid"].keys())
            if "PE_W" in p_data: current_deep_symbols.update(p_data["PE_W"].keys())
            if "OverSell_W" in p_data: current_deep_symbols.update(p_data["OverSell_W"].keys())
            if "season" in p_data: current_deep_symbols.update(p_data["season"].keys())
            
    except Exception as e:
        log_detail(f"提示: 读取现有备注时出错(可能是文件不存在): {e}")

    # 4. 构建备注 (Note)
    def build_symbol_note_map(symbols, existing_notes=None, highlight_set=None, suffix_tag=""):
        note_map = {}
        for sym in symbols:
            orig_note = ""
            if existing_notes and sym in existing_notes:
                orig_note = existing_notes[sym].replace(sym, "")
            
            new_suffix = orig_note
            
            # 这里会自动加上 "听"
            if highlight_set and sym in highlight_set:
                if "听" not in new_suffix:
                    new_suffix += "听"
            
            if suffix_tag and suffix_tag not in new_suffix:
                new_suffix += suffix_tag
                
            # === 新增：如果该股在黑名单里，追加“黑”字 ===
            s_tags = set(symbol_to_tags_map.get(sym, []))
            if s_tags.intersection(tag_blacklist):
                if "黑" not in new_suffix:
                    new_suffix += "黑"
            
            note_map[sym] = f"{sym}{new_suffix}"
        return note_map
    
    # >>>>>>>>>> [修改] 生成 PE_Volume 备注，追加“追”字 >>>>>>>>>>
    # 第一步：生成基础备注（包含“听”）
    pe_volume_notes = build_symbol_note_map(
        filtered_pe_volume, 
        existing_notes=all_existing_notes, 
        highlight_set=current_deep_symbols
    )

    # 第二步：为回溯捞回的 symbol 追加“追”字
    # 修改说明：移除 if "追" not in ... 的判断，改为直接追加，实现“追追”、“追追追”的效果
    for sym in retention_symbols:
        if sym in pe_volume_notes:
            # 直接追加“追”字，不再检查是否已经存在
            pe_volume_notes[sym] += "追"
                
    # 第三步：如果该 symbol 同时存在于 PE_Volume_high 中，追加“嗨”字
    for sym in filtered_pe_volume:
        if sym in filtered_pe_volume_high:
            if sym in pe_volume_notes and "嗨" not in pe_volume_notes[sym]:
                pe_volume_notes[sym] += "嗨"
                
    # 此时 pe_volume_notes 里的格式应该是： "LSCC听追嗨" 或者 "LSCC听" (如果不是捞回的)
    
    pe_volume_up_notes = build_symbol_note_map(filtered_pe_volume_up)
    
    # 为策略3生成带分类后缀的备注 
    pe_vol_high_notes = {}
    for sym in filtered_pe_volume_high:
        categories = []
        
        # 1. 先判断是否属于 甲、乙、丙
        if sym in filtered_pe_volume_high_jia:
            categories.append("甲")
        elif sym in filtered_pe_volume_high_yi:
            categories.append("乙")
        elif sym in filtered_pe_volume_high_bing:
            categories.append("丙")
            
        # 2. 只有在没有被分类为 甲、乙、丙 的情况下，才判断是否加入“抄底”
        # 如果 categories 为空，说明它既不是甲也不是乙也不是丙，此时才允许显示“抄底”
        if not categories and sym in filtered_pe_volume_high_chaodi:
            categories.append("抄底")
            
        suffix = "".join(categories)  # 例如 "甲乙" 或 "乙"
        
        # === 新增：如果该股在黑名单里，追加“黑”字 ===
        s_tags = set(symbol_to_tags_map.get(sym, []))
        if s_tags.intersection(tag_blacklist):
            suffix += "黑"
            
        pe_vol_high_notes[sym] = f"{sym}{suffix}"
    
    # === 新增 ===：生成 ETF 的备注 (正常情况下直接写入symbol本体即可)
    etf_vol_high_notes = build_symbol_note_map(filtered_etf_volume_high)
    etf_vol_low_notes = build_symbol_note_map(filtered_etf_volume_low) 

    # ================= 新增：执行 PE_Hot 策略 =================
    # 排除的 symbol 列表：如果在这些 Volume 策略中，就不进入 PE_Hot
    exclude_symbols_for_hot = set(filtered_pe_volume) | set(filtered_pe_volume_up) | set(filtered_pe_volume_high)
    
    # 传入动态生成的 whitelist_symbols 以及数据库参数用于成交额过滤
    pe_hot_list, pe_hot_notes = process_pe_hot(
        DB_FILE,               # 新增：数据库路径
        symbol_to_sector_map,  # 新增：板块映射
        TARGET_DATE,           # 新增：目标日期(支持回测)
        PANEL_JSON_FILE, 
        exclude_symbols_for_hot, 
        whitelist_symbols,
        log_detail
    )

    # ================= 新增：追踪 Symbol 全策略命中汇总 =================
    if SYMBOL_TO_TRACE:
        log_detail(f"\n{'='*60}")
        log_detail(f"📌📌📌 [{SYMBOL_TO_TRACE}] 全策略命中汇总 📌📌📌")
        log_detail(f"  策略1 PE_Volume (放量下跌):     {'✅ 命中' if SYMBOL_TO_TRACE in filtered_pe_volume else '❌ 未命中'}")
        log_detail(f"  策略1 回溯保留 (Retention):     {'✅ 被捞回' if SYMBOL_TO_TRACE in retention_symbols else '❌ 未捞回'}")
        log_detail(f"  策略2 PE_Volume_up (活跃上涨):  {'✅ 命中' if SYMBOL_TO_TRACE in filtered_pe_volume_up else '❌ 未命中'}")
        
        high_parts = []
        if SYMBOL_TO_TRACE in filtered_pe_volume_high_jia: high_parts.append("甲")
        if SYMBOL_TO_TRACE in filtered_pe_volume_high_yi: high_parts.append("乙")
        if SYMBOL_TO_TRACE in filtered_pe_volume_high_bing: high_parts.append("丙")
        if SYMBOL_TO_TRACE in filtered_pe_volume_high_chaodi: high_parts.append("抄底")
        if high_parts:
            log_detail(f"  策略3 PE_Volume_high (财报突破):✅ 命中 ({','.join(high_parts)})")
        else:
            log_detail(f"  策略3 PE_Volume_high (财报突破):❌ 未命中")
        
        log_detail(f"  策略4 ETF_Volume_high (ETF突破): {'✅ 命中' if SYMBOL_TO_TRACE in filtered_etf_volume_high else '❌ 未命中 (非ETF则正常)'}")
        log_detail(f"  策略5 ETF_Volume_low (ETF触底):  {'✅ 命中' if SYMBOL_TO_TRACE in filtered_etf_volume_low else '❌ 未命中 (非ETF则正常)'}")
        log_detail(f"  策略6 PE_Hot (白名单/超大市值):   {'✅ 命中' if SYMBOL_TO_TRACE in pe_hot_list else '❌ 未命中'}")
        log_detail(f"{'='*60}")

    # 5. 回测安全拦截 (新增 ETF 统计)
    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 [安全拦截] 回测模式 (Date: {TARGET_DATE}) 已启用。")
        log_detail(f"📊 [策略1] PE_Volume 命中: {len(filtered_pe_volume)} 个") 
        log_detail(f"📊 [策略2] PE_Volume_up 命中: {len(filtered_pe_volume_up)} 个")
        log_detail(f"📊 [策略3] PE_Volume_high 总计命中: {len(filtered_pe_volume_high)} 个")
        log_detail(f"    - 甲类: {len(filtered_pe_volume_high_jia)} 个")
        log_detail(f"    - 乙类: {len(filtered_pe_volume_high_yi)} 个")
        log_detail(f"    - 丙类: {len(filtered_pe_volume_high_bing)} 个")
        log_detail(f"    - 抄底类: {len(filtered_pe_volume_high_chaodi)} 个")
        log_detail(f"📊 [策略4] ETF_Volume_high 命中: {len(filtered_etf_volume_high)} 个")
        log_detail(f"📊 [策略5] ETF_Volume_low 命中: {len(filtered_etf_volume_low)} 个") 
        log_detail(f"📊 [策略-Hot] PE_Hot 命中: {len(pe_hot_list)} 个") 
        log_detail("="*60 + "\n")
        return

    # 6. 写入 Panel (已有的函数逻辑会顺带将其自动写入到对应的 _backup 里)
    log_detail(f"\n正在写入 Panel 文件...")
    update_panel_with_conflict_check(
        PANEL_JSON_FILE,
        filtered_pe_volume, pe_volume_notes,
        filtered_pe_volume_up, pe_volume_up_notes,
        filtered_pe_volume_high, pe_vol_high_notes,
        filtered_etf_volume_high, etf_vol_high_notes,
        filtered_etf_volume_low, etf_vol_low_notes, 
        pe_hot_list, pe_hot_notes, # 传入 PE_Hot 数据
        log_detail
    )

    # # 7. 写入 History (新增 ETF)
    # log_detail(f"正在更新 History 文件...")
    # update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume", final_pe_volume, log_detail, base_date_str)
    # update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume_up", final_pe_volume_up, log_detail, base_date_str)
    # update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume_high", final_pe_volume_high, log_detail, base_date_str)
    # update_earning_history_json(EARNING_HISTORY_JSON_FILE, "ETF_Volume_high", final_etf_volume_high, log_detail, base_date_str) # === 新增 ===

    # 7. 写入 History (新增 ETF)
    log_detail(f"\n正在更新 History 文件...")
    
    # === 将带有中文后缀的变量 values() 提取成列表，用于写入 History ===
    history_pe_volume = sorted(list(pe_volume_notes.values()))
    history_pe_volume_up = sorted(list(pe_volume_up_notes.values()))
    history_pe_volume_high = sorted(list(pe_vol_high_notes.values()))
    history_etf_volume_high = sorted(list(etf_vol_high_notes.values()))
    history_etf_volume_low = sorted(list(etf_vol_low_notes.values())) 
    
    # === 新增 PE_Hot 写入 History ===
    history_pe_hot = sorted(list(pe_hot_notes.values()))

    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume", history_pe_volume, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume_up", history_pe_volume_up, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume_high", history_pe_volume_high, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "ETF_Volume_high", history_etf_volume_high, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "ETF_Volume_low", history_etf_volume_low, log_detail, base_date_str) 
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Hot", history_pe_hot, log_detail, base_date_str)

    # 写入 Tag 黑名单标记分组 (包含所有策略)
    # all_volume_symbols = set(final_pe_volume) | set(final_pe_volume_up) | set(final_pe_volume_high) | set(final_etf_volume_high) | set(final_etf_volume_low) 
    
    # blocked_symbols_to_log = []
    # for sym in all_volume_symbols:
    #     s_tags = set(symbol_to_tags_map.get(sym, []))
    #     if s_tags.intersection(tag_blacklist):
    #         blocked_symbols_to_log.append(sym)
            
    # if blocked_symbols_to_log:
    #     blocked_symbols_to_log = sorted(list(set(blocked_symbols_to_log)))
    #     update_earning_history_json(EARNING_HISTORY_JSON_FILE, "_Tag_Blacklist", blocked_symbols_to_log, log_detail, base_date_str)
    #     log_detail(f"已将 {len(blocked_symbols_to_log)} 个命中黑名单Tag的symbol额外记入 '_Tag_Blacklist' 分组。")

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