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
    # ========== 策略1 (PE_Volume) 参数 ==========
    "COND8_VOLUME_LOOKBACK_MONTHS": 3,   # 过去3个月
    "COND8_VOLUME_RANK_THRESHOLD": 4,    # 成交量排名前 N 名 (默认3，代码逻辑是 <4)
    
    # ========== 策略2 (PE_Volume_up) 参数 ==========
    "COND_UP_HISTORY_LOOKBACK_DAYS": 5,  # 历史记录回溯天数
    "COND_UP_VOL_RANK_MONTHS": 1,        # 放量检查回溯月份 (1个月)
    "COND_UP_VOL_RANK_THRESHOLD": 3,     # 放量检查前 N 名
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
        log_detail(f"   - [Rank检查] 回溯{lookback_months}个月, 记录数: {len(valid_data)}")
        top_n_str = ", ".join([f"[{d}]: {v}" for d, v in top_n_data])
        log_detail(f"   - 前{rank_threshold}名: {top_n_str}")
        log_detail(f"   - 当前量: {latest_volume} -> 结果: {is_top_n}")
        
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

# --- 策略1: PE_Volume (T, T-1, T-2, T-3 放量) ---
def process_condition_8(db_path, history_json_path, sector_map, target_date_override, symbol_to_trace, log_detail):
    """
    执行条件8策略：PE_Volume (修改版：T-1, T-2, T-3 仅检查是否放量，不比较价格)
    """
    log_detail("\n========== 开始执行 条件8 (PE_Volume) 策略 ==========")
    
    # 读取配置
    rank_threshold = CONFIG.get("COND8_VOLUME_RANK_THRESHOLD", 3)
    lookback_months = CONFIG.get("COND8_VOLUME_LOOKBACK_MONTHS", 3)
    log_detail(f"配置参数: 排名阈值 = Top {rank_threshold}")

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
            
            # 数据完整性检查
            if len(dates) < 4: 
                if is_tracing: log_detail(f"    x [失败] 交易数据不足 (仅{len(dates)}天)")
                continue
            
            # 确认日期对齐：个股的 dates[date_idx] 应该是 hist_date
            # 例如 T-2 策略，dates[2] 必须等于 hist_date
            if dates[date_idx] != hist_date:
                if is_tracing: log_detail(f"    x [跳过] 个股{task_name}日期({dates[date_idx]}) 与 任务日期({hist_date}) 不一致")
                continue
            
            # 获取今日 (Today) 的成交量
            # 只需要查询 dates[0] (Today) 的数据
            query = f'SELECT volume FROM "{sector}" WHERE name = ? AND date = ?'
            cursor.execute(query, (symbol, dates[0]))
            row = cursor.fetchone()
            
            if not row:
                if is_tracing: log_detail(f"    x [失败] 缺少今日({dates[0]})数据。")
                continue
            
            today_volume = row[0]
            if today_volume is None: continue

            # 核心判断逻辑：只检查放量 (使用配置的 rank_threshold)
            vol_cond = check_volume_rank(
                cursor, sector, symbol, dates[0], today_volume, 
                CONFIG["COND8_VOLUME_LOOKBACK_MONTHS"], 
                rank_threshold, # 传入配置的阈值
                log_detail, is_tracing
            )
            
            if vol_cond:
                # ================== 财报日过滤逻辑 ==================
                # 检查今日(dates[0])是否为财报日
                if check_is_earnings_day(cursor, symbol, dates[0]):
                    if is_tracing: log_detail(f"    🛑 [过滤] 今日({dates[0]}) 为财报日，剔除。")
                    continue

                candidates_volume.add(symbol)
                if is_tracing: log_detail(f"    ✅ [通过] {task_name} 放量条件满足！")

    conn.close()
    
    result_list = sorted(list(candidates_volume))
    log_detail(f"条件8 (PE_Volume) 筛选完成，共命中 {len(result_list)} 个: {result_list}")
    return result_list

# --- 策略2: PE_Volume_up (5天内出现 + 放量上涨/缩量上涨) ---
def process_pe_volume_up(db_path, history_json_path, sector_map, target_date_override, symbol_to_trace, log_detail):
    log_detail("\n========== 开始执行 策略2 (PE_Volume_up) ==========")
    
    # 配置参数
    lookback_days = CONFIG.get("COND_UP_HISTORY_LOOKBACK_DAYS", 5)
    vol_rank_months = CONFIG.get("COND_UP_VOL_RANK_MONTHS", 1)
    vol_rank_threshold = CONFIG.get("COND_UP_VOL_RANK_THRESHOLD", 3)
    
    # 【回测逻辑】这里处理回测日期
    # 如果 target_date_override 存在，则所有逻辑都基于这个日期
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    # 1. 连接数据库获取全局日期
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    
    sample_symbol = list(sector_map.keys())[0] if sector_map else "AAPL"
    sample_sector = sector_map.get(sample_symbol, "Technology")
    # 获取最近5个交易日 (T, T-1, T-2, T-3, T-4)
    global_dates = get_trading_dates_list(cursor, sample_sector, sample_symbol, base_date, limit=lookback_days)
    
    if len(global_dates) < 2:
        log_detail("错误: 交易日数据不足，无法执行策略2。")
        conn.close()
        return []
    
    log_detail(f"扫描历史日期范围 (截止 {base_date}): {global_dates}")

    # 2. 从History中收集候选股
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
    log_detail(f"5天内历史记录共扫描到 {len(candidate_symbols)} 个候选 Symbol。")

    results = []
    
    # 3. 逐个检查逻辑
    for symbol in candidate_symbols:
        is_tracing = (symbol == symbol_to_trace)
        sector = sector_map.get(symbol)
        if not sector: continue
        
        if is_tracing: log_detail(f"--- 正在检查 {symbol} (策略2) ---")

        # 【回测逻辑】获取该股最近2天的数据 (最新, 次新)
        # 关键点：WHERE date <= base_date，确保不读取未来的数据
        query = f'SELECT date, price, volume FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2'
        cursor.execute(query, (symbol, base_date))
        rows = cursor.fetchall()
        
        if len(rows) < 2:
            if is_tracing: log_detail(f"    x 数据不足2天，跳过。")
            continue
            
        # rows[0] = Latest (T), rows[1] = Previous (T-1)
        # 在回测模式下，Latest 就是回测的目标日期
        date_curr, price_curr, vol_curr = rows[0]
        date_prev, price_prev, vol_prev = rows[1]
        
        if price_curr is None or price_prev is None or vol_curr is None or vol_prev is None:
            continue

        # 特征1: 必须上涨 (最新价 > 次新价)
        if price_curr <= price_prev:
            if is_tracing: log_detail(f"    x 价格未上涨 ({price_curr} <= {price_prev})，跳过。")
            continue
            
        # 财报日过滤 (可选，保持系统一致性)
        if check_is_earnings_day(cursor, symbol, date_curr):
            if is_tracing: log_detail(f"    🛑 今日是财报日，跳过。")
            continue

        is_match = False
        reason = ""

        # 特征2: 检查成交量关系
        if vol_curr > vol_prev:
            # === 放量上涨 ===
            # 额外条件: 最新量在过去1个月内排名前3
            is_top_vol = check_volume_rank(
                cursor, sector, symbol, date_curr, vol_curr, 
                vol_rank_months, vol_rank_threshold, log_detail, is_tracing
            )
            if is_top_vol:
                is_match = True
                reason = "放量上涨 (Top Vol)"
            else:
                if is_tracing: log_detail(f"    x 放量但未进入前{vol_rank_threshold}名。")
        else:
            # === 缩量上涨 ===
            # 条件: 量缩 (vol_curr < vol_prev) 且 价涨 (已满足)
            is_match = True
            reason = "缩量上涨"
            
        if is_match:
            results.append(symbol)
            if is_tracing: log_detail(f"    ✅ [选中] {reason} (P:{price_curr}>{price_prev}, V:{vol_curr} vs {vol_prev})")

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

    # ================= 策略 1 执行 =================
    # 传入 TARGET_DATE，内部会处理
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
    # final_pe_volume_up = sorted(list(set(raw_pe_volume_up)))

    # === 新增逻辑：去重处理 ，如果要恢复代码，只需删除下面恢复上面即可===
    # 如果 PE_Volume 已经有了，PE_Volume_up 就不再输出
    pe_volume_set = set(final_pe_volume)
    unique_pe_volume_up = set(raw_pe_volume_up)
    
    filtered_pe_volume_up = []
    
    log_detail("\n--- 开始执行交叉去重 (PE_Volume 优先) ---")
    for sym in sorted(list(unique_pe_volume_up)):
        if sym in pe_volume_set:
            log_detail(f"    [去重] Symbol {sym} 已存在于 PE_Volume，从 PE_Volume_up 中移除。")
        else:
            filtered_pe_volume_up.append(sym)
            
    final_pe_volume_up = sorted(filtered_pe_volume_up)
    log_detail(f"去重后 PE_Volume_up 剩余: {len(final_pe_volume_up)} 个。")
    # ===========================

    # 4. 构建备注 (Note)
    def build_symbol_note_map(symbols):
        note_map = {}
        for sym in symbols:
            tags = set(symbol_to_tags_map.get(sym, []))
            is_hot = bool(tags & hot_tags)
            note_map[sym] = f"{sym}热" if is_hot else ""
        return note_map
        
    pe_volume_notes = build_symbol_note_map(final_pe_volume)
    pe_volume_up_notes = build_symbol_note_map(final_pe_volume_up)

    # 5. 回测安全拦截
    # 【回测逻辑】如果设置了 TARGET_DATE，在这里直接 return，不执行下面的写入操作
    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 [安全拦截] 回测模式 (Date: {TARGET_DATE}) 已启用。")
        log_detail(f"📊 [策略1] PE_Volume 命中: {len(final_pe_volume)} 个 -> {final_pe_volume}")
        log_detail(f"📊 [策略2] PE_Volume_up 命中: {len(final_pe_volume_up)} 个 -> {final_pe_volume_up}")
        log_detail("="*60 + "\n")
        return

    # 6. 写入 Panel
    log_detail(f"\n正在写入 Panel 文件...")
    # 策略1 写入
    update_json_panel(final_pe_volume, PANEL_JSON_FILE, 'PE_Volume', symbol_to_note=pe_volume_notes)
    update_json_panel(final_pe_volume, PANEL_JSON_FILE, 'PE_Volume_backup', symbol_to_note=pe_volume_notes)
    
    # 策略2 写入
    update_json_panel(final_pe_volume_up, PANEL_JSON_FILE, 'PE_Volume_up', symbol_to_note=pe_volume_up_notes)
    update_json_panel(final_pe_volume_up, PANEL_JSON_FILE, 'PE_Volume_up_backup', symbol_to_note=pe_volume_up_notes)

    # 7. 写入 History (Raw Data)
    log_detail(f"正在更新 History 文件...")
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume", final_pe_volume, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume_up", final_pe_volume_up, log_detail, base_date_str)

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