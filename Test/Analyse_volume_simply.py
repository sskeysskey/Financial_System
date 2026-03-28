import json
import os
import datetime

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 1. 配置文件和路径 ---
BASE_PATH = USER_HOME

# ================= 配置区域 =================
# 如果为空，则运行"今天"模式；如果填入日期（如 "2024-11-03"），则运行回测模式
SYMBOL_TO_TRACE = "" 
TARGET_DATE = "" 

# SYMBOL_TO_TRACE = "NET"
# TARGET_DATE = "2026-02-23"

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
    "ETF_COND_LOW_DROP_THRESHOLD": 0.098,           # 距最高点跌幅超过 9.8%
    "ETF_COND_LOW_TURNOVER_MONTHS": 3,             # 成交额回溯3个月
    "ETF_COND_LOW_TURNOVER_RANK_THRESHOLD": 2,     # [新增] 成交额排名前 N 名 (前2名)
}

# --- 2. 辅助与文件操作模块 ---

def clean_symbol(symbol_with_suffix):
    """
    从带后缀的 symbol 中提取纯净的 symbol
    例如: "BLK黑听" -> "BLK", "ALGM甲抄底" -> "ALGM"
    """
    if not symbol_with_suffix:
        return ""
    
    # 定义所有可能的后缀字符
    suffix_chars = set("黑听追嗨甲乙丙丁抄底")
    
    # 从右往左移除后缀字符
    clean = symbol_with_suffix.rstrip(''.join(suffix_chars))
    
    return clean

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

def update_panel_with_conflict_check(json_path, pe_vol_list, pe_vol_notes, pe_vol_up_list, pe_vol_up_notes, pe_vol_high_list, pe_vol_high_notes, etf_vol_high_list, etf_vol_high_notes, etf_vol_low_list, etf_vol_low_notes, log_detail):
    """
    专门用于 PE_Volume, PE_Volume_up, PE_Volume_high, 以及 ETF_Volume_high 的写入。
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

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log_detail("Panel 文件更新完成 (包含冲突清理及 ETF 写入)。")
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

    # ================= 策略 3 执行 (增加接纳新返回参数) =================
    raw_pe_volume_high_jia, raw_pe_volume_high_yi, raw_pe_volume_high_bing, raw_pe_volume_high_chaodi = process_pe_volume_high(
        DB_FILE, 
        EARNING_HISTORY_JSON_FILE, # 新增传入参数
        PANEL_JSON_FILE,           # 新增传入参数
        symbol_to_sector_map, 
        TARGET_DATE, 
        SYMBOL_TO_TRACE, 
        log_detail
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
    # === 新增 ===
    filtered_etf_volume_low = filter_blacklisted_tags(final_etf_volume_low)

    if SYMBOL_TO_TRACE:
        # (保留原有的 trace 提示)
        if SYMBOL_TO_TRACE in final_pe_volume and SYMBOL_TO_TRACE not in filtered_pe_volume:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略1) 通过，但因黑名单标签将会被打上‘黑’字。")
        if SYMBOL_TO_TRACE in final_pe_volume_up and SYMBOL_TO_TRACE not in filtered_pe_volume_up:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略2) 通过，但因黑名单标签将会被打上‘黑’字。")
        if SYMBOL_TO_TRACE in final_pe_volume_high and SYMBOL_TO_TRACE not in filtered_pe_volume_high:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略3) 通过，但因黑名单标签将会被打上‘黑’字。")
        # === 新增 ===：ETF 追踪提示
        if SYMBOL_TO_TRACE in final_etf_volume_high and SYMBOL_TO_TRACE not in filtered_etf_volume_high:
             log_detail(f"追踪提示: {SYMBOL_TO_TRACE} (策略4) 通过，但因黑名单标签将会被打上‘黑’字。")
        # === 新增 ===
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
                
    # === 新增：第三步：如果该 symbol 同时存在于 PE_Volume_high 中，追加“嗨”字 ===
    for sym in filtered_pe_volume:
        if sym in filtered_pe_volume_high:
            if sym in pe_volume_notes and "嗨" not in pe_volume_notes[sym]:
                pe_volume_notes[sym] += "嗨"
                
    # 此时 pe_volume_notes 里的格式应该是： "LSCC听追嗨" 或者 "LSCC听" (如果不是捞回的)
    
    pe_volume_up_notes = build_symbol_note_map(filtered_pe_volume_up)
    
    # 为策略3生成带分类后缀的备注 
    # 创建一个映射：symbol -> 它属于哪些类别
    symbol_to_categories = {}
    for sym in filtered_pe_volume_high:
        categories = []
        if sym in filtered_pe_volume_high_jia:
            categories.append("甲")
        elif sym in filtered_pe_volume_high_yi:
            categories.append("乙")
        elif sym in filtered_pe_volume_high_bing:
            categories.append("丙")
            
        # 如果是抄底入选的，加上“抄底”二字
        if sym in filtered_pe_volume_high_chaodi:
            categories.append("抄底")
            
        symbol_to_categories[sym] = categories
    
    # 构建策略3的备注 (例如：ALGM抄底 或 ALGM甲抄底)
    pe_vol_high_notes = {}
    for sym in filtered_pe_volume_high:
        categories = symbol_to_categories.get(sym, [])
        suffix = "".join(categories)  # 例如 "甲乙" 或 "乙"
        
        # === 新增：如果该股在黑名单里，追加“黑”字 ===
        s_tags = set(symbol_to_tags_map.get(sym, []))
        if s_tags.intersection(tag_blacklist):
            suffix += "黑"
            
        pe_vol_high_notes[sym] = f"{sym}{suffix}"
    
    # === 新增 ===：生成 ETF 的备注 (正常情况下直接写入symbol本体即可)
    etf_vol_high_notes = build_symbol_note_map(filtered_etf_volume_high)
    etf_vol_low_notes = build_symbol_note_map(filtered_etf_volume_low) # === 新增 ===

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
        log_detail(f"📊 [策略5] ETF_Volume_low 命中: {len(filtered_etf_volume_low)} 个") # === 新增 ===
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
        filtered_etf_volume_low, etf_vol_low_notes, # === 新增传入参数 ===
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
    history_etf_volume_low = sorted(list(etf_vol_low_notes.values())) # === 新增 ===

    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume", history_pe_volume, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume_up", history_pe_volume_up, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume_high", history_pe_volume_high, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "ETF_Volume_high", history_etf_volume_high, log_detail, base_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "ETF_Volume_low", history_etf_volume_low, log_detail, base_date_str) # === 新增 ===

    # 写入 Tag 黑名单标记分组 (包含所有策略)
    all_volume_symbols = set(final_pe_volume) | set(final_pe_volume_up) | set(final_pe_volume_high) | set(final_etf_volume_high) | set(final_etf_volume_low) 
    
    blocked_symbols_to_log = []
    for sym in all_volume_symbols:
        s_tags = set(symbol_to_tags_map.get(sym, []))
        if s_tags.intersection(tag_blacklist):
            blocked_symbols_to_log.append(sym)
            
    if blocked_symbols_to_log:
        blocked_symbols_to_log = sorted(list(set(blocked_symbols_to_log)))
        update_earning_history_json(EARNING_HISTORY_JSON_FILE, "_Tag_Blacklist", blocked_symbols_to_log, log_detail, base_date_str)
        log_detail(f"已将 {len(blocked_symbols_to_log)} 个命中黑名单Tag的symbol额外记入 '_Tag_Blacklist' 分组。")

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