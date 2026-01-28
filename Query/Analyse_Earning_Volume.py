import json
import sqlite3
import os
import datetime

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 1. 配置文件和路径 ---
BASE_PATH = USER_HOME

# ================= 配置区域 =================
SYMBOL_TO_TRACE = "" 
TARGET_DATE = ""

# SYMBOL_TO_TRACE = "LRN"
# TARGET_DATE = "2025-11-11"

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
    # ========== 条件8 (PE_Volume) 参数 ==========
    "COND8_VOLUME_LOOKBACK_MONTHS": 3,   # 过去3个月
    "COND8_VOLUME_RANK_THRESHOLD": 3,    # 【新增配置】成交量排名前 N 名 (默认3)
    "COND8_TARGET_GROUPS": [             # 需要去历史文件中扫描的分组
        "OverSell_W", "PE_Deeper", "PE_Deep", 
        "PE_W", "PE_valid", "PE_invalid", "season", "no_season"
    ],
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

def update_earning_history_json(file_path, group_name, symbols_to_add, log_detail):
    log_detail(f"\n--- 更新历史记录文件: {os.path.basename(file_path)} -> '{group_name}' ---")
    
    # 注意：这里使用 TARGET_DATE 作为记录日期，如果为空则用昨天（原逻辑习惯）
    # 但对于 PE_Volume 这种当日策略，通常记录在当日。
    # 为了保持与原代码一致性（原代码是用 yesterday 记录），这里保持原样，
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    record_date_str = yesterday.isoformat()
    
    # 如果是回测模式，理论上不应该写入，但如果强制写入，应使用回测日期
    if TARGET_DATE:
        record_date_str = TARGET_DATE

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

# --- 3. 核心逻辑模块 (Condition 8) ---

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
    检查 latest_volume 是否是过去 N 个月内的前 rank_threshold 名
    """
    # 计算 N 个月前的日期
    try:
        dt = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d")
        start_date = dt - datetime.timedelta(days=lookback_months * 30)
        start_date_str = start_date.strftime("%Y-%m-%d")
    except Exception:
        return False

    # 查询过去3个月的所有成交量
    query = f'SELECT volume FROM "{sector_name}" WHERE name = ? AND date >= ? AND date <= ?'
    cursor.execute(query, (symbol, start_date_str, latest_date_str))
    rows = cursor.fetchall()
    
    volumes = [r[0] for r in rows if r[0] is not None]
    
    if not volumes:
        return False
        
    # 排序（从大到小）
    sorted_volumes = sorted(volumes, reverse=True)
    
    # 截取前 N 名
    top_n_volumes = sorted_volumes[:rank_threshold]
    
    is_top_n = latest_volume in top_n_volumes
    
    # 另一种判定：如果最新成交量 >= 第N名的值，也算（处理重复值情况）
    # 注意：数组索引是从0开始的，所以第N名的索引是 rank_threshold - 1
    if len(top_n_volumes) >= rank_threshold and latest_volume >= top_n_volumes[rank_threshold - 1]:
        is_top_n = True
        
    if is_tracing:
        log_detail(f"   - [放量检查] 过去{lookback_months}个月记录数: {len(volumes)}")
        log_detail(f"   - 前{rank_threshold}名Vol: {top_n_volumes}")
        log_detail(f"   - 当前Vol:   {latest_volume}")
        log_detail(f"   - 结果: {is_top_n}")
        
    return is_top_n

def check_is_earnings_day(cursor, symbol, target_date_str):
    """
    检查 target_date_str 是否为该 symbol 在 Earning 表中的最新财报日。
    如果 Earning 表中有该日期且与 target_date_str 匹配，返回 True。
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

def process_condition_8(db_path, history_json_path, sector_map, target_date_override, symbol_to_trace, log_detail):
    """
    执行条件8策略：PE_Volume (修改版：T-1, T-2, T-3 仅检查是否放量，不比较价格)
    """
    log_detail("\n========== 开始执行 条件8 (PE_Volume) 策略 ==========")
    
    # 读取配置
    rank_threshold = CONFIG.get("COND8_VOLUME_RANK_THRESHOLD", 3)
    log_detail(f"配置参数: 排名阈值 = Top {rank_threshold}")

    # 1. 确定基准日期 (Today)
    base_date = target_date_override if target_date_override else datetime.date.today().isoformat()
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
    target_groups = CONFIG["COND8_TARGET_GROUPS"]
    
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
        
    # global_dates[0] = Today
    date_t1 = global_dates[1]
    date_t2 = global_dates[2]
    date_t3 = global_dates[3]
    
    log_detail(f"系统计算出的关键日期: T-1={date_t1}, T-2={date_t2}, T-3={date_t3}")
    
    # 定义任务列表
    # 格式: (Target_Date_In_History, Date_Index_In_List, Task_Name)
    # Date_Index_In_List: 1代表T-1, 2代表T-2, 3代表T-3
    tasks = [
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
        if symbol_to_trace:
            log_detail(f" -> 正在扫描 {task_name} (日期: {hist_date})，包含 {len(symbols_on_date)} 个候选。")
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
                # =================================================

                candidates_volume.add(symbol)
                if is_tracing: log_detail(f"    ✅ [通过] {task_name} 放量条件满足！")

    conn.close()
    
    result_list = sorted(list(candidates_volume))
    log_detail(f"条件8 (PE_Volume) 筛选完成，共命中 {len(result_list)} 个: {result_list}")
    return result_list

# --- 4. 主执行流程 ---

def run_pe_volume_logic(log_detail):
    log_detail("PE_Volume 独立程序开始运行...")
    if SYMBOL_TO_TRACE: log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")
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

    # 2. 执行核心策略
    raw_pe_volume = process_condition_8(
        DB_FILE, 
        EARNING_HISTORY_JSON_FILE, 
        symbol_to_sector_map, 
        TARGET_DATE, 
        SYMBOL_TO_TRACE, 
        log_detail
    )

    # 3. 过滤 Tag 黑名单 (已修改：不再过滤，直接使用原始结果)
    # def filter_tags(syms):
    #     return [s for s in syms if not set(symbol_to_tags_map.get(s, [])).intersection(tag_blacklist)]
    
    # final_pe_volume_to_write = sorted(list(set(filter_tags(raw_pe_volume))))
    
    # 直接赋值，不过滤黑名单Tag
    final_pe_volume_to_write = sorted(list(set(raw_pe_volume)))
    
    # 4. 构建备注 (Note) - 依然保留热点标记逻辑
    def build_symbol_note_map(symbols):
        note_map = {}
        for sym in symbols:
            tags = set(symbol_to_tags_map.get(sym, []))
            is_hot = bool(tags & hot_tags)
            note_map[sym] = f"{sym}热" if is_hot else ""
        return note_map
        
    pe_volume_notes = build_symbol_note_map(final_pe_volume_to_write)

    # 5. 回测安全拦截
    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 [安全拦截] 回测模式 (Date: {TARGET_DATE}) 已启用。")
        log_detail(f"📊 [模拟结果] PE_Volume 命中数量: {len(final_pe_volume_to_write)} 个")
        log_detail(f"   列表: {final_pe_volume_to_write}")
        if SYMBOL_TO_TRACE:
            in_list = SYMBOL_TO_TRACE in final_pe_volume_to_write
            log_detail(f"🔎 [验证] Symbol '{SYMBOL_TO_TRACE}' 是否命中: {in_list}")
        log_detail("="*60 + "\n")
        return

    # 6. 写入 Panel
    log_detail(f"\n正在写入 Panel 文件... (数量: {len(final_pe_volume_to_write)})")
    update_json_panel(final_pe_volume_to_write, PANEL_JSON_FILE, 'PE_Volume', symbol_to_note=pe_volume_notes)
    update_json_panel(final_pe_volume_to_write, PANEL_JSON_FILE, 'PE_Volume_backup', symbol_to_note=pe_volume_notes)

    # 7. 写入 History (Raw Data)
    log_detail(f"正在更新 History 文件... (Raw 数量: {len(raw_pe_volume)})")
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume", raw_pe_volume, log_detail)

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