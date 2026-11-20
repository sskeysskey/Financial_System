import json
import sqlite3
import os
import re
import bisect
import datetime
from Analyse_run_mode import resolve_run_mode

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# --- 1. 配置文件和路径 ---
BASE_PATH = USER_HOME

# ================= 配置区域 =================
# 如果为空，则运行"今天"模式；如果填入日期（如 "2024-11-03"），则运行回测模式
# SYMBOL_TO_TRACE = "" 
# TARGET_DATE = "" 

SYMBOL_TO_TRACE = "WSM"
TARGET_DATE = "2026-09-16"

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
        "OverSell_W", "PE_Deeper", "PE_Deep", "PE_W", "PE_valid",
    ],
    "COND_HIGH_JIA_REQUIRE_ER_INCREASING": False,  # True=甲类要求两次财报价格递增; False=不要求
    # ========== 策略1 (PE_Volume放量下跌) 参数 ==========
    "COND8_REQUIRE_TURNOVER_UP": True,   # 原生PE_Volume: 今日成交额必须 > 昨日成交额
    "COND8_VOLUME_LOOKBACK_MONTHS": 1.5,   # 过去 N 个月
    "COND8_VOLUME_RANK_THRESHOLD": 3,    # 成交量排名前 N 名
    "COND8_ALLOW_UP_PERCENT": 0.005,  # 允许小幅上涨的幅度，0.005 表示 0.5%
    "COND8_EARNINGS_CHECK_DAYS": 2,      # [新增配置] 检查财报日的回溯天数 (填2则检查前2天: T-1, T-2)
    
    # ========== PE_Volume 回溯保留(窗口版)参数 ==========
    "RETENTION_WINDOW_TRADING_DAYS": 15,          # 起点之后多少个交易日内可持续捞回
    "RETENTION_ALLOW_UP_PERCENT": 0.0,            # "下跌"容忍的小幅上涨比例,0=严格下跌(收盘<昨收)
    "RETENTION_REQUIRE_CLOSE_BELOW_OPEN": False,  # True=还要求收盘<=开盘
    "RETENTION_REQUIRE_VALID_POOL": False,        # True=还要求当天在验证池(PE_Deep等)里
    "RETENTION_VOLUME_MAX_DROP": 0.60,            # 当天成交量相对起点日成交量最多允许低多少(0.10=最多低10%, 即 >= 起点量*90%)

    # ========== PE_Volume 回溯保留 - 新增「深跌追」规则 ==========
    "RETENTION_DEEP_ENABLED": True,               # 总开关
    "RETENTION_DEEP_WINDOW_TRADING_DAYS": 20,     # 起点之后多少个交易日内有效
    "RETENTION_DEEP_MIN_DROP_PERCENT": 0.08,      # 收盘价较起点收盘价下跌超过该比例 (0.10=10%)
    "RETENTION_DEEP_REQUIRE_VOLUME": False,       # True=深跌规则也要求成交量不低于起点量*(1-RETENTION_VOLUME_MAX_DROP)
    
    # ========== 策略2 (PE_Volume_up) 总开关 ==========
    "ENABLE_PE_VOLUME_UP": False,   # True=启用策略2及其回溯追; False=全部屏蔽(计算/写入Panel/写入History/日志)
    
    # ========== 策略2 (PE_Volume_up活跃上涨) 参数 ==========
    "COND_UP_HISTORY_LOOKBACK_DAYS": 5,  # 历史记录回溯天数
    "COND_UP_VOL_RANK_MONTHS": 2,        # 放量检查回溯月份
    "COND_UP_VOL_RANK_THRESHOLD": 3,     # 放量检查前 N 名

    # ========== 策略3 (PE_Volume_high 财报突破放量) 参数 ==========
    "COND_HIGH_TURNOVER_LOOKBACK_MONTHS": 6,       # 甲类：成交额回溯6个月 (原12)
    "COND_HIGH_TURNOVER_YI_LOOKBACK_MONTHS": 4,    # [新增] 乙类：成交额回溯4个月 (原6)
    "COND_HIGH_TURNOVER_RANK_THRESHOLD": 2,        # 成交额排名前3名
    # [新增] 丙类专用配置
    "COND_HIGH_TURNOVER_BING_DAYS": 45,        # 丙类：成交额回溯45天
    "COND_HIGH_TURNOVER_BING_RANK_THRESHOLD": 2,  # 丙类：排名前3名

    # ========== 策略3 甲类回溯 (财报日甲 -> 深跌追) 参数 ==========
    "HIGH_JIA_CHASE_ENABLED": True,          # 总开关
    "HIGH_JIA_CHASE_DROP_PERCENT": 0.052,    # 较财报日收盘 或 较财报日以来最高收盘, 下跌超过该比例即"追"
    "HIGH_YI_CHASE_DROP_PERCENT": 0.11,      # [新增] 乙类(需命中HOT_TAGS_T)：同上逻辑，阈值单独设定
    "HIGH_JIA_CHASE_MAX_TRADING_DAYS": 0,    # 财报日之后最多多少个交易日内有效; 0=不限(直到下一次财报)

    # ========== 策略6 (PE_Hot 白名单/超大市值) 参数 ==========
    "PE_HOT_MIN_MARKET_CAP": 150000000000,         # 超大市值门槛 (默认 1500亿)
    "PE_HOT_MIN_TURNOVER": 200000000,                   # PE_Hot 最新成交额门槛 (默认 2亿)
    "PE_HOT_CONTINUE_DOWN_TURNOVER_RATIO": 0.8,         # 前一日已在 PE_Hot 且今日继续下跌时, 门槛乘以该比例 (0.8 => 1.6亿)

    # ========== 动态白名单 参数 ==========
    "WHITELIST_LOOKBACK_DAYS": 365,   # 回溯自然日天数
    "WHITELIST_MIN_GROWTH": 1.1,      # (区间最高价 - 区间最低价) / 区间最低价 > 1.1，即涨幅 > 110%，且最高点必须晚于最低点

    # ========== [新增] PE_Volume 补捞机制 (今日在回调池但无任何 PE_Volume) ==========
    "VOL_BACKFILL_ENABLED": True,
    "VOL_BACKFILL_POOL_GROUPS": ["PE_valid", "PE_Deep", "PE_Deeper", "OverSell_W"],  # 需要的话可加 "PE_W"
    "VOL_BACKFILL_WINDOW_TRADING_DAYS": 15,       # 往前追溯 T-1 ~ T-15
    "VOL_BACKFILL_MIN_DROP_PERCENT": 0.035,       # 今日收盘较放量下跌日收盘低超过 3.5%
    "VOL_BACKFILL_DOWN_ALLOW_UP_PERCENT": 0.0,    # 放量日"下跌"容忍上涨比例, 0=严格下跌
    "VOL_BACKFILL_REQUIRE_CLOSE_BELOW_OPEN": False,  # 放量日是否还要求收盘<=开盘
    "VOL_BACKFILL_SKIP_DAYS_WITH_PE_VOLUME": True,   # 放量日当天已是原生 PE_Volume 则跳过(交给回溯保留)
    "VOL_BACKFILL_INVALIDATE_ON_EARNINGS": True,     # 放量日之后出现新财报 -> 该放量日作废

    # ========== [新增] PE_Volume_up 回溯追 ==========
    "VOL_UP_CHASE_ENABLED": True,
    "VOL_UP_CHASE_WINDOW_TRADING_DAYS": 20,       # 起点在 T-1 ~ T-15 内
    "VOL_UP_CHASE_DROP_PERCENT": 0.03,            # 今日收盘 < 起点前一交易日收盘 * (1-3%)
    "VOL_UP_CHASE_REQUIRE_TODAY_DOWN": False,     # 是否要求今日下跌
    "VOL_UP_CHASE_REQUIRE_POOL": False,           # 是否要求今日在池子中
    "VOL_UP_CHASE_POOL_GROUPS": ["OverSell_W", "PE_Deeper", "PE_Deep", "PE_W", "PE_valid"],
    "VOL_UP_CHASE_INVALIDATE_ON_EARNINGS": True,  # 起点之后出现财报 -> 起点作废

    # ========== [新增] 性能 ==========
    "AUTO_CREATE_DB_INDEXES": True,               # 自动为板块表/Earning 建 (name, date) 索引(已有等价索引则跳过)
}

# --- 2. 辅助与文件操作模块 ---
def atomic_json_dump(data, path):
    """原子写入:先写临时文件再替换,避免中途崩溃导致 JSON 被截断。"""
    tmp_path = path + ".tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)

def load_json_for_update(path):
    """用于"读-改-写"。文件不存在返回 {};文件损坏则抛出 JSONDecodeError(由调用方中止写入,绝不覆盖)。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    
def clean_symbol(symbol_with_suffix):
    """
    更强大的清洗函数：
    1. 提取连续的字母。
    2. 允许中间包含 '-'（例如 "BRK-B"），但 '-' 必须出现在字母之间。
    3. 忽略末尾的数字、中文或其他非字母字符（如 "BRK-B15", "C9热"）。
    """
    if not symbol_with_suffix:
        return ""
    
    # 正则表达式解析：
    # [A-Za-z]+       : 匹配一个或多个字母（如 "BRK"）
    # (?: ... )?      : 这是一个可选的非捕获组，表示这一部分可以出现 0 次或 1 次
    # -[A-Za-z]+      : 匹配一个 '-' 紧接着一个或多个字母（如 "-B"）
    # 组合起来就是：匹配纯字母，或者 "字母-字母" 的格式
    match = re.match(r'([A-Za-z]+(?:-[A-Za-z]+)?)', symbol_with_suffix)
    
    if match:
        return match.group(1).upper()
    
    # 如果没有匹配到（极其罕见，比如纯数字或纯中文开头），则返回原字符串
    return symbol_with_suffix

def format_chase(n, compress_threshold=3):
    """
    把追的次数格式化成后缀。
    n < compress_threshold: 追追
    n >= compress_threshold: 追✖️8
    """
    if n <= 0:
        return ""
    if n < compress_threshold:
        return "追" * n
    return f"追✖️{n}"

def strip_chase(text):
    """
    去掉备注里的所有追标记，同时兼容新旧两种格式：
    - 旧格式: 追追追追
    - 新格式: 追✖️8
    """
    if not text:
        return text
    return re.sub(r'追(?:✖\ufe0f?\d+)?', '', text)

def resolve_base_date(target_date_override):
    """实盘=昨天(自然日), 回测=TARGET_DATE。"""
    if target_date_override:
        return target_date_override
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

def load_pool_symbols(history_data, panel_json_path, pool_names, date_str, allow_panel_fallback, log_detail=None):
    """
    读取指定日期的池子 symbol (已清洗)。优先 History[group][date_str]；
    History 无数据且允许降级(实盘)时，从 Panel 读取。返回 (set, 来源描述)。
    """
    pool = set()
    for name in pool_names:
        grp = history_data.get(name, {})
        if isinstance(grp, dict):
            syms = grp.get(date_str)
            if isinstance(syms, list):
                pool.update(clean_symbol(s) for s in syms if isinstance(s, str))
    if pool:
        return pool, "History"
    if allow_panel_fallback:
        try:
            with open(panel_json_path, 'r', encoding='utf-8') as f:
                panel_data = json.load(f)
            for name in pool_names:
                grp = panel_data.get(name, {})
                if isinstance(grp, dict):
                    pool.update(clean_symbol(k) for k in grp.keys())
            return pool, "Panel"
        except Exception as e:
            if log_detail:
                log_detail(f"    x 从 Panel 读取池子失败: {e}")
    return pool, "无"

def get_earning_dates(cursor, symbol, end_date_str):
    """返回 <= end_date_str 的全部财报日 (升序、去重)。"""
    try:
        cursor.execute("SELECT DISTINCT date FROM Earning WHERE name = ? AND date <= ? ORDER BY date ASC",
                       (symbol, end_date_str))
        return [r[0] for r in cursor.fetchall()]
    except sqlite3.OperationalError:
        return []

def is_top_n_in_window(turnovers, cur, k):
    """
    在 cur 本身就在窗口内时，与 check_turnover_rank / check_turnover_since_earning 判定等价:
    窗口内严格大于 cur 的个数 < k 即为前 k 名(并列算入)。
    """
    return sum(1 for t in turnovers if t is not None and t > cur) < k

def ensure_db_indexes(db_path, table_names, log_detail):
    """为各表建立 (name, date) 复合索引；已存在前两列为 (name, date) 的索引则跳过。只需建一次。"""
    def has_name_date_index(cur, table):
        cur.execute(f'PRAGMA index_list("{table}")')
        for row in cur.fetchall():
            idx_name = row[1]
            cur.execute(f'PRAGMA index_info("{idx_name}")')
            cols = [r[2] for r in sorted(cur.fetchall())]
            if [c.lower() if c else c for c in cols[:2]] == ["name", "date"]:
                return True
        return False

    created = []
    conn = sqlite3.connect(db_path, timeout=60.0)
    try:
        cur = conn.cursor()
        for table in sorted(table_names):
            try:
                if has_name_date_index(cur, table):
                    continue
                cur.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_name_date" ON "{table}" (name, date)')
                created.append(table)
            except sqlite3.OperationalError as e:
                log_detail(f"提示: 表 {table} 建索引失败(可忽略): {e}")
        conn.commit()
    finally:
        conn.close()
    if created:
        log_detail(f"[性能] 已为以下表新建 (name, date) 索引: {created}")

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

def update_panel_with_conflict_check(json_path, pe_vol_list, pe_vol_notes, pe_vol_up_list, pe_vol_up_notes, pe_vol_high_list, pe_vol_high_notes, pe_hot_list, pe_hot_notes, log_detail):
    """
    专门用于 PE_Volume, PE_Volume_up, PE_Volume_high、pe_hot_list、pe_hot_notes 的写入。
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
        data = load_json_for_update(json_path)
    except json.JSONDecodeError as e:
        log_detail(f"错误: Panel JSON 已损坏,为避免覆盖丢失数据,放弃写入: {e}")
        return

    all_new_volume_symbols = set(pe_vol_list) | set(pe_vol_up_list) | set(pe_vol_high_list)
    
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
    
    # 写入策略2 (受开关控制；关闭时保留 Panel 中原有数据，不做覆盖)
    if CONFIG.get("ENABLE_PE_VOLUME_UP", False):
        data['PE_Volume_up'] = build_group_dict(pe_vol_up_list, pe_vol_up_notes)
        data['PE_Volume_up_backup'] = build_group_dict(pe_vol_up_list, pe_vol_up_notes)
    
    # 写入策略3
    data['PE_Volume_high'] = build_group_dict(pe_vol_high_list, pe_vol_high_notes)
    data['PE_Volume_high_backup'] = build_group_dict(pe_vol_high_list, pe_vol_high_notes)

    # === 新增：写入 PE_Hot 分组 ===
    data['PE_Hot'] = build_group_dict(pe_hot_list, pe_hot_notes)
    data['PE_Hot_backup'] = build_group_dict(pe_hot_list, pe_hot_notes)

    try:
        atomic_json_dump(data, json_path)
        log_detail("Panel 文件更新完成 (包含冲突清理及 PE_Hot 写入)。")
    except Exception as e:
        log_detail(f"错误: 写入 Panel JSON 文件失败: {e}")

def update_earning_history_json(file_path, group_name, symbols_to_add, log_detail, base_date_str):
    log_detail(f"\n--- 更新历史记录文件: {os.path.basename(file_path)} -> '{group_name}' ---")

    if not symbols_to_add:
        log_detail(f" - 列表为空,跳过写入历史记录。")
        return

    record_date_str = base_date_str

    try:
        data = load_json_for_update(file_path)
    except json.JSONDecodeError as e:
        log_detail(f"错误: 历史记录文件已损坏,为避免覆盖丢失数据,放弃写入: {e}")
        return

    if group_name not in data:
        data[group_name] = {}

    existing_symbols = data[group_name].get(record_date_str, [])

    # 按纯净 symbol 去重合并:同一天重跑时,新备注覆盖旧备注,避免 "KKR" 与 "KKR追" 并存
    merged = {clean_symbol(s): s for s in existing_symbols}
    for s in symbols_to_add:
        merged[clean_symbol(s)] = s
    updated_symbols = sorted(merged.values())

    if not updated_symbols:
        return

    data[group_name][record_date_str] = updated_symbols
    num_added = len(updated_symbols) - len(existing_symbols)

    try:
        atomic_json_dump(data, file_path)
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

def get_global_trading_dates(cursor, sector_map, end_date_str, limit=10):
    """
    获取全市场交易日历 (倒序，含 end_date_str 当天)。
    优先用流动性极好的大盘股作基准，避免用 JSON 第一个 symbol 时因停牌/退市/缺数据导致日历错位；
    若都不可用，则退回到板块表的 DISTINCT date。
    """
    benchmarks = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "XOM"]
    for sym in benchmarks:
        sec = sector_map.get(sym)
        if not sec:
            continue
        try:
            dates = get_trading_dates_list(cursor, sec, sym, end_date_str, limit)
        except sqlite3.OperationalError:
            continue
        if len(dates) >= limit:
            return dates

    for sec in sorted(set(sector_map.values())):
        try:
            cursor.execute(
                f'SELECT DISTINCT date FROM "{sec}" WHERE date <= ? ORDER BY date DESC LIMIT ?',
                (end_date_str, limit)
            )
            dates = [r[0] for r in cursor.fetchall()]
            if dates:
                return dates
        except sqlite3.OperationalError:
            continue
    return []

# ========== 动态生成白名单 (区间最低点 -> 其后的区间最高点 涨幅 > 阈值) ==========
def generate_whitelist_symbols(db_path, sector_map, base_date_str, symbol_to_trace, log_detail):
    """
    规则:
    - 区间: [base_date - N天, base_date]，N = WHITELIST_LOOKBACK_DAYS
    - 最低点: 区间内最低收盘价 (多日并列取最早那天)
    - 最高点: 区间内最高收盘价 (多日并列取最晚那天)
    - 合格: 最高点日期 严格晚于 最低点日期，且 (最高 - 最低) / 最低 > WHITELIST_MIN_GROWTH
    性能: 每个板块表只查询一次，在 Python 中单次遍历完成计算。
    """
    lookback_days = CONFIG.get("WHITELIST_LOOKBACK_DAYS", 365)
    min_growth = CONFIG.get("WHITELIST_MIN_GROWTH", 1.1)

    log_detail(f"\n========== 开始动态生成白名单 (近{lookback_days}天: 最低点之后的最高点涨幅 > {min_growth*100:.0f}%) ==========")

    if not sector_map:
        log_detail("错误: 板块映射为空，无法生成白名单。")
        return []

    try:
        base_dt = datetime.datetime.strptime(base_date_str, '%Y-%m-%d')
    except ValueError:
        log_detail(f"错误: 基准日期格式不正确: {base_date_str}")
        return []
    start_date_str = (base_dt - datetime.timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    log_detail(f"白名单区间: {start_date_str} ~ {base_date_str}")

    # 按板块归类 symbol
    sector_to_symbols = {}
    for sym, sec in sector_map.items():
        sector_to_symbols.setdefault(sec, set()).add(sym)

    final_symbols = []
    trace_found = False

    conn = sqlite3.connect(db_path, timeout=60.0)
    try:
        cursor = conn.cursor()
        for sector in sorted(sector_to_symbols):
            wanted = sector_to_symbols[sector]
            try:
                cursor.execute(
                    f'SELECT name, date, price FROM "{sector}" '
                    f'WHERE date >= ? AND date <= ? AND price IS NOT NULL AND price > 0 '
                    f'ORDER BY date ASC',
                    (start_date_str, base_date_str)
                )
                rows = cursor.fetchall()
            except sqlite3.OperationalError as e:
                log_detail(f"警告: 读取板块表 {sector} 失败，跳过: {e}")
                continue

            # name -> [run_min_p, run_min_d, best_growth, best_low_p, best_low_d, best_high_p, best_high_d]
            # run_min: 截至当前遍历位置的"历史最低点"
            # best_*:  所有 "(某日价 - 其之前的最低价)/其之前的最低价" 中最大的一组
            stats = {}
            for name, d, p in rows:          # rows 已按 date ASC 排序
                if name not in wanted:
                    continue
                s = stats.get(name)
                if s is None:
                    stats[name] = [p, d, 0.0, p, d, p, d]
                    continue

                # 先用"此前的最低点"计算今天的涨幅 (保证高点严格晚于低点)
                g = (p - s[0]) / s[0]
                if g > s[2]:
                    s[2] = g
                    s[3], s[4] = s[0], s[1]   # 对应低点
                    s[5], s[6] = p, d         # 对应高点

                # 再更新滚动最低点 (严格小于, 并列保留最早)
                if p < s[0]:
                    s[0], s[1] = p, d

            for name in sorted(stats):
                _, _, growth, low_p, low_d, high_p, high_d = stats[name]
                order_ok = high_d > low_d
                passed = order_ok and growth > min_growth
                if passed:
                    final_symbols.append(name)

                if symbol_to_trace and name == symbol_to_trace:
                    trace_found = True
                    log_detail(f"    - [白名单追踪] {name}: 最佳低点 {low_p:.2f} ({low_d}) -> 其后高点 {high_p:.2f} ({high_d}), "
                               f"涨幅 {growth*100:.1f}% (阈值 >{min_growth*100:.0f}%), 高点晚于低点: {order_ok} "
                               f"-> {'✅ 入选' if passed else '❌ 未入选'}")
    finally:
        conn.close()

    if symbol_to_trace and not trace_found:
        log_detail(f"    - [白名单追踪] {symbol_to_trace}: 区间内无有效价格数据或不在目标板块中 -> ❌ 未入选")

    final_symbols = sorted(set(final_symbols))
    log_detail(f"动态白名单生成完成，共命中 {len(final_symbols)} 个 Symbol。")
    return final_symbols

# --- 策略1: PE_Volume (T, T-1, T-2, T-3... 放量下跌) ---
def pe_volume(db_path, history_json_path, sector_map, target_date_override, symbol_to_trace, log_detail):
    """
    执行条件8策略：PE_Volume (修改版：T-1, T-2, T-3... 检查是否放量且下跌，使用成交额 Price * Volume 进行排名)
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
    
    # 获取大盘基准日期 (使用稳定基准，避免日历错位)
    # global_dates[0] = Today, global_dates[1] = T-1 (上一个有效交易日)
    global_dates = get_global_trading_dates(cursor, sector_map, base_date, limit=5)
    
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

    symbol_dates_cache = {}     # symbol -> 交易日列表 (所有任务共用同一个 base_date，可缓存)
    evaluated_symbols = set()   # 已完整评估过的 symbol (后续判断只取决于今日数据，结果相同，无需重复计算)
    
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
            
            if symbol not in symbol_dates_cache:
                symbol_dates_cache[symbol] = get_trading_dates_list(cursor, sector, symbol, base_date, limit=5)
            dates = symbol_dates_cache[symbol]
            
            if len(dates) < 4:
                if is_tracing: log_detail(f"    x [失败] 交易日数据不足4天。")
                continue
            if dates[date_idx] != hist_date:
                if is_tracing: log_detail(f"    x [失败] 日期对齐不匹配: dates[{date_idx}]={dates[date_idx]} != {hist_date}。")
                continue

            if symbol in evaluated_symbols:
                if is_tracing: log_detail(f"    --- {symbol} 已在之前任务中完成评估 (判定只依赖今日数据，结果相同)，跳过重复计算。")
                continue
            evaluated_symbols.add(symbol)
            
            query = f'SELECT price, volume, open FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2'
            cursor.execute(query, (symbol, dates[0]))
            rows = cursor.fetchall()

            if len(rows) < 2:
                if is_tracing: log_detail(f"    x [失败] 缺少足够的价格数据进行涨跌幅对比。")
                continue

            price_curr, vol_curr, open_curr = rows[0]
            price_prev, vol_prev, _ = rows[1]

            if price_curr is None or price_prev is None or vol_curr is None or vol_prev is None or open_curr is None:
                if is_tracing: log_detail(f"    x [失败] 价格/成交量数据存在 None。")
                continue

            # 获取允许上涨的幅度
            allow_up_pct = CONFIG.get("COND8_ALLOW_UP_PERCENT", 0.005)

            # ========== 修改：允许小幅上涨 (收盘价 <= 昨收 * (1 + 允许幅度) 且 收盘价 < 今日开盘) ==========
            # 逻辑：如果价格上涨超过了允许的幅度，或者收盘价高于开盘价，则视为不满足条件
            if price_curr > price_prev * (1 + allow_up_pct) or price_curr > open_curr:
                if is_tracing: 
                    log_detail(f"    x [失败] 价格未满足条件 (收盘{price_curr:.2f}, 昨收{price_prev:.2f}, 允许上限{price_prev * (1 + allow_up_pct):.2f}, 今开{open_curr:.2f})。")
                continue

            turnover_curr = price_curr * vol_curr
            turnover_prev = price_prev * vol_prev

            # 新增: 今日成交额必须大于昨日成交额 (仅作用于原生 PE_Volume)
            if CONFIG.get("COND8_REQUIRE_TURNOVER_UP", False) and turnover_curr <= turnover_prev:
                if is_tracing:
                    log_detail(f"    x [失败] 成交额未放大 (今日{turnover_curr:,.0f} <= 昨日{turnover_prev:,.0f})。")
                continue
            
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
    窗口版回溯保留机制(双规则):
    - 起点(anchor): 历史 PE_Volume 中不带"追"的记录(真正新触发的),窗口内取最近一个。
    - 规则A(原规则, 窗口=RETENTION_WINDOW_TRADING_DAYS, 默认15个交易日):
        今日下跌 且 今日收盘 < 起点收盘 且 成交量 >= 起点量*(1-容忍)  (可选: 收盘<=开盘)
    - 规则B(新增"深跌追", 窗口=RETENTION_DEEP_WINDOW_TRADING_DAYS, 默认20个交易日):
        今日下跌 且 今日收盘较起点收盘下跌超过 RETENTION_DEEP_MIN_DROP_PERCENT (默认10%)
        (可选: 成交量要求 / 收盘<=开盘,由配置开关控制)
    - 任一规则满足即捞回;两规则共同的过滤: 今日不是新触发、数据未过期、近N天无财报日、(可选)在验证池。
    返回: dict {symbol: 追字个数}。追字个数 = 起点之后"满足规则A或规则B"的交易日数(含今日)。
    """
    log_detail("\n========== 执行 PE_Volume 回溯保留机制 (窗口版 Retention Check, 含深跌追) ==========")

    window_a = CONFIG.get("RETENTION_WINDOW_TRADING_DAYS", 15)
    allow_up_pct = CONFIG.get("RETENTION_ALLOW_UP_PERCENT", 0.0)
    require_below_open = CONFIG.get("RETENTION_REQUIRE_CLOSE_BELOW_OPEN", False)
    require_pool = CONFIG.get("RETENTION_REQUIRE_VALID_POOL", False)
    earnings_days = CONFIG.get("COND8_EARNINGS_CHECK_DAYS", 2)
    vol_max_drop = CONFIG.get("RETENTION_VOLUME_MAX_DROP", 0.10)

    deep_enabled = CONFIG.get("RETENTION_DEEP_ENABLED", True)
    window_b = CONFIG.get("RETENTION_DEEP_WINDOW_TRADING_DAYS", 20) if deep_enabled else 0
    deep_drop = CONFIG.get("RETENTION_DEEP_MIN_DROP_PERCENT", 0.10)
    deep_require_vol = CONFIG.get("RETENTION_DEEP_REQUIRE_VOLUME", False)
    max_window = max(window_a, window_b)

    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    log_detail(f"    配置[规则A]: 窗口={window_a}个交易日, 容忍上涨={allow_up_pct*100:.2f}%, "
               f"成交量最多低{vol_max_drop*100:.0f}%, 要求收盘<=开盘={require_below_open}")
    log_detail(f"    配置[规则B-深跌追]: 启用={deep_enabled}, 窗口={window_b}个交易日, "
               f"较起点收盘跌幅>{deep_drop*100:.0f}%, 要求成交量={deep_require_vol}")
    log_detail(f"    配置[公共]: 要求在验证池={require_pool}, 财报过滤前{earnings_days}天")

    # 1. 读取历史
    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
    except Exception as e:
        log_detail(f"    x 读取历史文件失败: {e}")
        return {}

    hist_pe_vol = history_data.get("PE_Volume", {})
    if not hist_pe_vol:
        log_detail("    x 历史记录中无 PE_Volume 数据,跳过回溯。")
        if symbol_to_trace:
            log_detail(f"📌 [回溯总结] {symbol_to_trace}: ❌ 无历史数据可回溯。")
        return {}

    # 2. (可选)加载验证池
    valid_pool = set()
    if require_pool:
        target_pool_names = ["PE_Deep", "PE_Deeper", "OverSell_W", "PE_W", "PE_valid", "PE_invalid", "season"]
        try:
            for name in target_pool_names:
                group_history = history_data.get(name, {})
                if base_date in group_history:
                    valid_pool.update(clean_symbol(s) for s in group_history[base_date])
            if not valid_pool and not target_date_override:
                with open(panel_json_path, 'r', encoding='utf-8') as f:
                    panel_data = json.load(f)
                for name in target_pool_names:
                    group_data = panel_data.get(name, {})
                    if isinstance(group_data, dict):
                        valid_pool.update(group_data.keys())
            log_detail(f"    -> 已加载验证池,共 {len(valid_pool)} 个 unique symbol")
        except Exception as e:
            log_detail(f"    x 读取验证池数据失败: {e}")
            return {}

    result = {}
    anchors = {}
    conn = sqlite3.connect(db_path, timeout=60.0)
    try:
        cursor = conn.cursor()

        # 3. 全市场交易日历: [T, T-1, ..., T-max_window]
        global_dates = get_global_trading_dates(cursor, sector_map, base_date, limit=max_window + 1)
        if len(global_dates) < 2:
            log_detail("    x 无法获取足够的交易日历,跳过回溯。")
            return {}
        today_trading = global_dates[0]
        log_detail(f"    -> 最新交易日 T={today_trading}, 窗口最早可用起点日期 > {global_dates[-1]}")

        # 4. 收集窗口内的起点: sym -> 最近一次"新触发"(不带追)的日期 (按最大窗口收集)
        for d, raw_list in hist_pe_vol.items():
            if not isinstance(d, str) or d >= base_date:
                continue
            elapsed = sum(1 for c in global_dates if c > d)
            if elapsed < 1 or elapsed > max_window:
                continue
            for raw in raw_list:
                if "追" in raw:
                    continue
                sym = clean_symbol(raw)
                if sym not in anchors or d > anchors[sym]:
                    anchors[sym] = d

        log_detail(f"    -> 窗口内共找到 {len(anchors)} 个有效起点 symbol。")
        if symbol_to_trace:
            if symbol_to_trace in anchors:
                log_detail(f"    !!! 目标 {symbol_to_trace} 起点日期: {anchors[symbol_to_trace]},开始逐条件检查...")
            else:
                log_detail(f"    --- 目标 {symbol_to_trace} 在窗口内没有新触发的 PE_Volume 起点,无需回溯。")

        current_set = set(current_pe_volume)

        # 5. 逐个检查
        for sym in sorted(anchors):
            is_tracing = (sym == symbol_to_trace)
            anchor_date = anchors[sym]

            if sym in current_set:
                if is_tracing: log_detail(f"    --- [回溯] {sym}: 今日已是新触发,无需捞回。")
                continue
            if require_pool and sym not in valid_pool:
                if is_tracing: log_detail(f"    x [回溯] {sym}: 不在验证池中,无法捞回。")
                continue
            sector = sector_map.get(sym)
            if not sector:
                if is_tracing: log_detail(f"    x [回溯] {sym}: 未找到板块映射。")
                continue

            # 起点日(或其前最近一个交易日)的收盘价、成交量
            cursor.execute(
                f'SELECT date, price, open, volume FROM "{sector}" WHERE name = ? AND date <= ? AND price IS NOT NULL '
                f'ORDER BY date DESC LIMIT 1', (sym, anchor_date))
            anchor_row = cursor.fetchone()
            if not anchor_row:
                if is_tracing: log_detail(f"    x [回溯] {sym}: 找不到起点日 {anchor_date} 的价格。")
                continue
            anchor_close = anchor_row[1]
            anchor_volume = anchor_row[3]
            if anchor_close is None or anchor_close <= 0:
                if is_tracing: log_detail(f"    x [回溯] {sym}: 起点日 {anchor_row[0]} 收盘价无效。")
                continue

            # 起点成交量缺失 -> 仅影响"需要成交量"的判断
            vol_ok = anchor_volume is not None and anchor_volume > 0
            rule_a_usable = vol_ok  # 规则A必须比较成交量
            rule_b_usable = deep_enabled and (not deep_require_vol or vol_ok)
            if not rule_a_usable and not rule_b_usable:
                if is_tracing: log_detail(f"    x [回溯] {sym}: 起点日 {anchor_row[0]} 成交量缺失，且无可用的不依赖成交量的规则。")
                continue

            # 起点之后到今天的全部行情(升序)
            cursor.execute(
                f'SELECT date, price, open, volume FROM "{sector}" WHERE name = ? AND date > ? AND date <= ? '
                f'AND price IS NOT NULL ORDER BY date ASC', (sym, anchor_row[0], base_date))
            after_rows = cursor.fetchall()
            seq = [anchor_row] + after_rows
            if len(seq) < 2:
                if is_tracing: log_detail(f"    x [回溯] {sym}: 起点之后无行情数据。")
                continue

            # 数据过期校验(停牌/缺数据时不能拿陈旧数据判断)
            if seq[-1][0] != today_trading:
                if is_tracing: log_detail(f"    x [回溯] {sym}: 最新数据日期 {seq[-1][0]} != 最新交易日 {today_trading},跳过。")
                continue

            def elapsed_at(date_str, _anchor=anchor_date):
                """date_str 距起点已过多少个全市场交易日"""
                return sum(1 for c in global_dates if _anchor < c <= date_str)

            vol_floor = anchor_volume * (1 - vol_max_drop) if vol_ok else None
            deep_price_limit = anchor_close * (1 - deep_drop)

            def check_rules(prev_row, cur_row, _elapsed_fn=elapsed_at, _vol_floor=vol_floor,
                            _a_ok=rule_a_usable, _b_ok=rule_b_usable, _deep_limit=deep_price_limit,
                            _anchor_close=anchor_close):
                """返回 (规则A是否满足, 规则B是否满足)"""
                p_prev = prev_row[1]
                _, p_cur, o_cur, v_cur = cur_row

                # 公共: 今日下跌
                if not (p_cur < p_prev * (1 + allow_up_pct)):
                    return False, False
                # 公共(可选): 收盘<=开盘
                if require_below_open and (o_cur is None or p_cur > o_cur):
                    return False, False

                e = _elapsed_fn(cur_row[0])

                # 规则A: 低于起点收盘 + 成交量达标, 仅在 window_a 内有效
                hit_a = False
                if _a_ok and e <= window_a:
                    if p_cur < _anchor_close and v_cur is not None and v_cur >= _vol_floor:
                        hit_a = True

                # 规则B: 较起点收盘跌幅 > deep_drop, 仅在 window_b 内有效
                hit_b = False
                if _b_ok and e <= window_b:
                    if p_cur < _deep_limit:
                        if deep_require_vol:
                            hit_b = (v_cur is not None and v_cur >= _vol_floor)
                        else:
                            hit_b = True

                return hit_a, hit_b

            hit_a_today, hit_b_today = check_rules(seq[-2], seq[-1])
            today_ok = hit_a_today or hit_b_today
            if is_tracing:
                drop_pct = (anchor_close - seq[-1][1]) / anchor_close * 100
                vol_floor_str = f"{vol_floor:,.0f}" if vol_floor is not None else "N/A"
                anchor_vol_str = f"{anchor_volume:,.0f}" if vol_ok else "N/A"
                cur_vol_str = f"{seq[-1][3]:,.0f}" if seq[-1][3] is not None else "N/A"
                log_detail(f"    - [回溯] {sym}: 起点 {anchor_date} 收盘 {anchor_close:.2f} 成交量 {anchor_vol_str}; "
                           f"今日({seq[-1][0]}, 距起点第{elapsed_at(seq[-1][0])}个交易日) 收盘 {seq[-1][1]:.2f}, "
                           f"昨收 {seq[-2][1]:.2f}, 今开 {seq[-1][2]}, 成交量 {cur_vol_str} (规则A下限 {vol_floor_str})")
                log_detail(f"      较起点收盘跌幅 {drop_pct:.2f}% (规则B需 >{deep_drop*100:.0f}%, 即收盘 < {deep_price_limit:.2f})")
                log_detail(f"      规则A(15日内下跌+低于起点+量达标): {hit_a_today} | 规则B(20日内下跌+深跌): {hit_b_today}")
            if not today_ok:
                if is_tracing: log_detail(f"    x [回溯] {sym}: 今日规则A、规则B均未满足,未捞回。")
                continue

            # 财报日过滤(与策略1一致)
            recent_dates = [r[0] for r in after_rows][-(earnings_days + 1):]
            hit_er = next((d for d in recent_dates if check_is_earnings_day(cursor, sym, d)), None)
            if hit_er:
                if is_tracing: log_detail(f"    🛑 [回溯过滤] {sym}: {hit_er} 为财报日(前{earnings_days}天内),不捞回。")
                continue

            # "追"字个数 = 起点之后所有满足(规则A 或 规则B)的天数(含今日)
            chase_n = 0
            for i in range(1, len(seq)):
                ha, hb = check_rules(seq[i - 1], seq[i])
                if ha or hb:
                    chase_n += 1
            result[sym] = chase_n
            reason = "+".join(r for r, h in (("规则A", hit_a_today), ("规则B深跌", hit_b_today)) if h)
            log_detail(f"    + [捞回] {sym}: 起点 {anchor_date}(收盘{anchor_close}) -> 今日收盘 {seq[-1][1]} "
                       f"(追×{chase_n}, 今日命中: {reason})")

    finally:
        conn.close()

    if symbol_to_trace:
        if symbol_to_trace in result:
            log_detail(f"📌 [回溯总结] {symbol_to_trace}: ✅ 被捞回 (追×{result[symbol_to_trace]})")
        elif symbol_to_trace in anchors:
            log_detail(f"📌 [回溯总结] {symbol_to_trace}: ❌ 在窗口内但未满足捞回条件(见上方详细日志)。")
        else:
            log_detail(f"📌 [回溯总结] {symbol_to_trace}: ❌ 窗口内无起点,无需回溯。")

    return result

# --- 策略1 补捞: 今日在回调池但无 PE_Volume -> 回看 15 日放量下跌日 ---
def check_pe_volume_backfill(db_path, history_json_path, panel_json_path, current_pe_volume,
                             sector_map, target_date_override, symbol_to_trace, log_detail):
    """
    场景: 某天放量下跌(成交额满足 PE_Volume 规则)但当天不在回调池 -> 没出 PE_Volume；
          之后价格更低进入回调池，但当天又不放量 -> 也没出。此机制在今天把它补出来(带追)。
    条件(全部满足):
      1. 今日(T) 在 VOL_BACKFILL_POOL_GROUPS 中，且今日无任何形式 PE_Volume(原生/回溯追)
      2. T-1 ~ T-N 中存在放量下跌日 d:
         a. d 当日下跌 (收盘 < 前一交易日收盘)
         b. d 成交额满足策略1规则 (财报日起TopK 或 近1.5月TopK，均以 d 为截止日，无前视)
         c. d 及其前 COND8_EARNINGS_CHECK_DAYS 个交易日非财报日
         d. (可选) d 当天不是原生 PE_Volume
         e. (可选) d 之后至今日无新财报
      3. 今日收盘 < d 收盘 * (1 - VOL_BACKFILL_MIN_DROP_PERCENT)
      4. 今日及前 COND8_EARNINGS_CHECK_DAYS 个交易日非财报日；今日有最新行情
    多个 d 满足时取离今天最近者为锚点。
    返回: {symbol: 追字个数}
    """
    log_detail("\n========== 执行 PE_Volume 补捞机制 (今日在回调池但无 PE_Volume -> 回看放量下跌日) ==========")
    if not CONFIG.get("VOL_BACKFILL_ENABLED", True):
        log_detail("    - 已关闭 (VOL_BACKFILL_ENABLED=False)，跳过。")
        return {}

    window = int(CONFIG.get("VOL_BACKFILL_WINDOW_TRADING_DAYS", 15))
    min_drop = CONFIG.get("VOL_BACKFILL_MIN_DROP_PERCENT", 0.035)
    pool_names = CONFIG.get("VOL_BACKFILL_POOL_GROUPS", ["PE_valid", "PE_Deep", "PE_Deeper", "OverSell_W"])
    down_allow = CONFIG.get("VOL_BACKFILL_DOWN_ALLOW_UP_PERCENT", 0.0)
    require_below_open = CONFIG.get("VOL_BACKFILL_REQUIRE_CLOSE_BELOW_OPEN", False)
    skip_native = CONFIG.get("VOL_BACKFILL_SKIP_DAYS_WITH_PE_VOLUME", True)
    invalidate_er = CONFIG.get("VOL_BACKFILL_INVALIDATE_ON_EARNINGS", True)
    rank_k = CONFIG.get("COND8_VOLUME_RANK_THRESHOLD", 3)
    lookback_months = CONFIG.get("COND8_VOLUME_LOOKBACK_MONTHS", 1.5)
    lookback_days = lookback_months * 30
    earnings_days = CONFIG.get("COND8_EARNINGS_CHECK_DAYS", 2)

    base_date = resolve_base_date(target_date_override)
    log_detail(f"    配置: 池子={pool_names}, 窗口=T-1~T-{window}, 今日较放量日收盘跌幅>{min_drop*100:.2f}%, "
               f"成交额规则=财报日起Top{rank_k} 或 近{lookback_months}月Top{rank_k}")
    log_detail(f"    配置: 跳过原生PE_Volume日={skip_native}, 中途财报作废={invalidate_er}, 财报过滤前{earnings_days}天")

    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
    except Exception as e:
        log_detail(f"    x 读取历史文件失败: {e}")
        return {}

    # sym -> {原生 PE_Volume 日期}
    native_days = {}
    hist_pv = history_data.get("PE_Volume", {})
    if isinstance(hist_pv, dict):
        for d, lst in hist_pv.items():
            if not isinstance(lst, list):
                continue
            for raw in lst:
                if isinstance(raw, str) and "追" not in raw:
                    native_days.setdefault(clean_symbol(raw), set()).add(d)

    result = {}
    conn = sqlite3.connect(db_path, timeout=60.0)
    try:
        cursor = conn.cursor()
        global_dates = get_global_trading_dates(cursor, sector_map, base_date, limit=window + 1)
        if len(global_dates) < 2:
            log_detail("    x 交易日历不足，跳过补捞。")
            return {}
        today = global_dates[0]
        window_dates = global_dates[1:]          # 由近及远: T-1, T-2, ...
        window_start = window_dates[-1]

        pool, src = load_pool_symbols(history_data, panel_json_path, pool_names, today,
                                      allow_panel_fallback=not target_date_override, log_detail=log_detail)
        current_set = set(current_pe_volume)
        candidates = sorted(pool - current_set)
        log_detail(f"    -> T={today}, 今日池子共 {len(pool)} 个(来源: {src})，其中无 PE_Volume 的候选 {len(candidates)} 个。")

        if symbol_to_trace:
            if symbol_to_trace not in pool:
                log_detail(f"    --- 目标 {symbol_to_trace} 今日不在 {pool_names} 中，不参与补捞。")
            elif symbol_to_trace in current_set:
                log_detail(f"    --- 目标 {symbol_to_trace} 今日已有 PE_Volume(原生或回溯)，无需补捞。")
            else:
                log_detail(f"    !!! 目标 {symbol_to_trace} 今日在池中且无 PE_Volume，开始补捞检查...")

        for sym in candidates:
            is_tracing = (sym == symbol_to_trace)
            sector = sector_map.get(sym)
            if not sector:
                if is_tracing: log_detail(f"    x [补捞] {sym}: 未找到板块映射。")
                continue

            er_dates = get_earning_dates(cursor, sym, today)
            er_set = set(er_dates)

            # 取数范围: 覆盖窗口最早日的 1.5 月回看 & 其所在财报区间起点
            fetch_start = (datetime.datetime.strptime(window_start, "%Y-%m-%d")
                           - datetime.timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            k = bisect.bisect_right(er_dates, window_start)
            if k > 0 and er_dates[k - 1] < fetch_start:
                fetch_start = er_dates[k - 1]

            cursor.execute(
                f'SELECT date, price, open, volume FROM "{sector}" WHERE name = ? AND date >= ? AND date <= ? '
                f'AND price IS NOT NULL AND price > 0 ORDER BY date ASC', (sym, fetch_start, today))
            rows = cursor.fetchall()
            if not rows or rows[-1][0] != today:
                if is_tracing:
                    log_detail(f"    x [补捞] {sym}: 最新数据日期 {rows[-1][0] if rows else 'N/A'} != {today}，跳过。")
                continue

            dates_list = [r[0] for r in rows]
            turnovers = [(r[1] * r[3]) if r[3] is not None else None for r in rows]
            idx_map = {d: i for i, d in enumerate(dates_list)}
            today_close = rows[-1][1]

            recent = dates_list[-(earnings_days + 1):]
            er_today = next((d for d in recent if d in er_set), None)
            if er_today:
                if is_tracing: log_detail(f"    🛑 [补捞过滤] {sym}: {er_today} 为财报日(今日及前{earnings_days}天内)。")
                continue

            anchor = None
            for d in window_dates:
                i = idx_map.get(d)
                if i is None or i == 0:
                    if is_tracing: log_detail(f"      · {d}: 无行情(停牌/缺数据)，跳过。")
                    continue
                _, p, o, v = rows[i]
                p_prev = rows[i - 1][1]
                to = turnovers[i]
                if to is None or to <= 0:
                    continue
                if not (p < p_prev * (1 + down_allow)):
                    if is_tracing: log_detail(f"      · {d}: 未下跌 ({p_prev:.2f}->{p:.2f})。")
                    continue
                if require_below_open and (o is None or p > o):
                    if is_tracing: log_detail(f"      · {d}: 收盘 {p:.2f} > 开盘 {o}。")
                    continue
                if skip_native and d in native_days.get(sym, ()):
                    if is_tracing: log_detail(f"      · {d}: 当天已是原生 PE_Volume，交给回溯保留机制处理。")
                    continue
                lo_e = max(0, i - earnings_days)
                er_near = next((dates_list[j] for j in range(lo_e, i + 1) if dates_list[j] in er_set), None)
                if er_near:
                    if is_tracing: log_detail(f"      · {d}: {er_near} 为财报日(该日及前{earnings_days}天)。")
                    continue
                if invalidate_er:
                    nxt = bisect.bisect_right(er_dates, d)
                    if nxt < len(er_dates):
                        if is_tracing: log_detail(f"      · {d}: 之后出现新财报 {er_dates[nxt]}，作废。")
                        continue

                # 成交额规则 (与策略1一致，以 d 为截止日)
                vol_ok, how = False, ""
                ke = bisect.bisect_right(er_dates, d)
                if ke > 0:
                    er_d = er_dates[ke - 1]
                    lo = bisect.bisect_left(dates_list, er_d)
                    if is_top_n_in_window(turnovers[lo:i + 1], to, rank_k):
                        vol_ok, how = True, f"财报日({er_d})起Top{rank_k}"
                if not vol_ok:
                    start_d = (datetime.datetime.strptime(d, "%Y-%m-%d")
                               - datetime.timedelta(days=lookback_days)).strftime("%Y-%m-%d")
                    lo = bisect.bisect_left(dates_list, start_d)
                    if is_top_n_in_window(turnovers[lo:i + 1], to, rank_k):
                        vol_ok, how = True, f"近{lookback_months}月Top{rank_k}"
                if not vol_ok:
                    if is_tracing: log_detail(f"      · {d}: 下跌但成交额 {to:,.0f} 未进 Top{rank_k}。")
                    continue

                limit = p * (1 - min_drop)
                if today_close < limit:
                    anchor = (i, d, p, to, how, limit)
                    break
                if is_tracing:
                    log_detail(f"      · {d}: 放量下跌满足({how}, 收盘{p:.2f})，但今日 {today_close:.2f} "
                               f"未低于 {limit:.2f} (跌幅 {(p - today_close) / p * 100:.2f}%)。")

            if not anchor:
                if is_tracing: log_detail(f"    x [补捞] {sym}: 窗口内无满足条件的放量下跌日。")
                continue

            ai, a_date, a_close, a_to, how, limit = anchor
            chase_n = sum(1 for j in range(ai + 1, len(rows)) if rows[j][1] < limit)
            chase_n = max(chase_n, 1)
            result[sym] = chase_n
            log_detail(f"    + [补捞] {sym}: 放量下跌日 {a_date}(收盘{a_close:.2f}, 成交额{a_to:,.0f}, {how}) -> "
                       f"今日 {today_close:.2f} (跌{(a_close - today_close) / a_close * 100:.2f}%, 追×{chase_n})")
    except sqlite3.OperationalError as e:
        log_detail(f"    x [补捞] 数据库查询失败: {e}")
    finally:
        conn.close()

    log_detail(f"PE_Volume 补捞完成，共补出 {len(result)} 个: {sorted(result)}")
    if symbol_to_trace:
        if symbol_to_trace in result:
            log_detail(f"📌 [补捞总结] {symbol_to_trace}: ✅ 补出 PE_Volume (追×{result[symbol_to_trace]})")
        else:
            log_detail(f"📌 [补捞总结] {symbol_to_trace}: ❌ 未补出（见上方日志）")
    return result


# --- 策略2 回溯: PE_Volume_up 原生起点 -> 跌破上涨前一日收盘 "追" ---
def check_pe_volume_up_retention(db_path, history_json_path, panel_json_path, current_vol_up,
                                 sector_map, target_date_override, symbol_to_trace, log_detail):
    """
    - 起点: T-1~T-N 内 History PE_Volume_up 中不带"追"的记录(含"空")，取最近一次
    - 参考价: 起点日前一个交易日的收盘价 (up 要求上涨，所以比较涨之前那天)
    - 触发: 今日收盘 < 参考价 * (1 - VOL_UP_CHASE_DROP_PERCENT)
    - 过滤: 今日已是原生 up / 数据过期 / 起点后出现财报(可关) / (可选)今日须下跌 / (可选)须在池中
    返回: {symbol: 追字个数}，追字个数 = 起点之后收盘 < 触发价 的天数(含今日)
    """
    log_detail("\n========== 执行 PE_Volume_up 回溯追机制 (原生 up 起点 -> 跌破上涨前一日收盘) ==========")
    if not CONFIG.get("VOL_UP_CHASE_ENABLED", True):
        log_detail("    - 已关闭 (VOL_UP_CHASE_ENABLED=False)，跳过。")
        return {}

    window = int(CONFIG.get("VOL_UP_CHASE_WINDOW_TRADING_DAYS", 15))
    drop_th = CONFIG.get("VOL_UP_CHASE_DROP_PERCENT", 0.03)
    require_down = CONFIG.get("VOL_UP_CHASE_REQUIRE_TODAY_DOWN", False)
    require_pool = CONFIG.get("VOL_UP_CHASE_REQUIRE_POOL", False)
    pool_names = CONFIG.get("VOL_UP_CHASE_POOL_GROUPS", CONFIG["TARGET_GROUPS"])
    invalidate_er = CONFIG.get("VOL_UP_CHASE_INVALIDATE_ON_EARNINGS", True)
    earnings_days = CONFIG.get("COND8_EARNINGS_CHECK_DAYS", 2)
    base_date = resolve_base_date(target_date_override)

    log_detail(f"    配置: 窗口=T-1~T-{window}, 今日收盘较起点前一日收盘跌幅>{drop_th*100:.2f}%, "
               f"要求今日下跌={require_down}, 要求在池={require_pool}, 起点后财报作废={invalidate_er}")

    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
    except Exception as e:
        log_detail(f"    x 读取历史文件失败: {e}")
        return {}

    hist_up = history_data.get("PE_Volume_up", {})
    if not isinstance(hist_up, dict) or not hist_up:
        log_detail("    x 历史记录中无 PE_Volume_up 数据，跳过。")
        return {}

    result, anchors = {}, {}
    conn = sqlite3.connect(db_path, timeout=60.0)
    try:
        cursor = conn.cursor()
        global_dates = get_global_trading_dates(cursor, sector_map, base_date, limit=window + 1)
        if len(global_dates) < 2:
            log_detail("    x 交易日历不足，跳过。")
            return {}
        today = global_dates[0]

        for d, raw_list in hist_up.items():
            if not isinstance(d, str) or not isinstance(raw_list, list) or d >= today:
                continue
            elapsed = sum(1 for c in global_dates if c > d)
            if elapsed < 1 or elapsed > window:
                continue
            for raw in raw_list:
                if not isinstance(raw, str) or "追" in raw:
                    continue
                sym = clean_symbol(raw)
                if sym not in anchors or d > anchors[sym]:
                    anchors[sym] = d

        log_detail(f"    -> T={today}, 窗口内共 {len(anchors)} 个原生 PE_Volume_up 起点。")
        if symbol_to_trace:
            if symbol_to_trace in anchors:
                log_detail(f"    !!! 目标 {symbol_to_trace} 起点: {anchors[symbol_to_trace]}，开始检查...")
            else:
                log_detail(f"    --- 目标 {symbol_to_trace} 窗口内无原生 PE_Volume_up 起点。")

        pool = set()
        if require_pool:
            pool, src = load_pool_symbols(history_data, panel_json_path, pool_names, today,
                                          allow_panel_fallback=not target_date_override, log_detail=log_detail)
            log_detail(f"    -> 已加载池子 {len(pool)} 个(来源: {src})")

        current_set = set(current_vol_up)
        for sym in sorted(anchors):
            is_tracing = (sym == symbol_to_trace)
            anchor_key = anchors[sym]
            if sym in current_set:
                if is_tracing: log_detail(f"    --- [up追] {sym}: 今日已是原生 PE_Volume_up，无需追。")
                continue
            if require_pool and sym not in pool:
                if is_tracing: log_detail(f"    x [up追] {sym}: 今日不在池中。")
                continue
            sector = sector_map.get(sym)
            if not sector:
                if is_tracing: log_detail(f"    x [up追] {sym}: 未找到板块映射。")
                continue

            cursor.execute(
                f'SELECT date, price FROM "{sector}" WHERE name = ? AND date <= ? AND price IS NOT NULL AND price > 0 '
                f'ORDER BY date DESC LIMIT 2', (sym, anchor_key))
            ar = cursor.fetchall()
            if len(ar) < 2:
                if is_tracing: log_detail(f"    x [up追] {sym}: 起点 {anchor_key} 及其前一日行情不足。")
                continue
            (anchor_date, anchor_close), (ref_date, ref_close) = ar[0], ar[1]

            cursor.execute(
                f'SELECT date, price FROM "{sector}" WHERE name = ? AND date > ? AND date <= ? '
                f'AND price IS NOT NULL AND price > 0 ORDER BY date ASC', (sym, anchor_date, today))
            after = cursor.fetchall()
            if not after or after[-1][0] != today:
                if is_tracing:
                    log_detail(f"    x [up追] {sym}: 最新数据 {after[-1][0] if after else 'N/A'} != {today}，跳过。")
                continue

            er_dates = get_earning_dates(cursor, sym, today)
            if invalidate_er:
                er_hit = next((e for e in er_dates if anchor_date < e <= today), None)
                er_desc = "起点之后出现财报"
            else:
                er_set = set(er_dates)
                recent = ([anchor_date] + [r[0] for r in after])[-(earnings_days + 1):]
                er_hit = next((x for x in recent if x in er_set), None)
                er_desc = f"今日及前{earnings_days}天内为财报日"
            if er_hit:
                if is_tracing: log_detail(f"    🛑 [up追过滤] {sym}: {er_hit} {er_desc}。")
                continue

            today_close = after[-1][1]
            prev_close = after[-2][1] if len(after) >= 2 else anchor_close
            limit = ref_close * (1 - drop_th)
            drop_pct = (ref_close - today_close) / ref_close * 100

            if is_tracing:
                log_detail(f"    - [up追] {sym}: 起点 {anchor_date}(收盘{anchor_close:.2f}), 参考日 {ref_date} 收盘 {ref_close:.2f}, "
                           f"今日 {today_close:.2f} (昨收 {prev_close:.2f}), 跌幅 {drop_pct:.2f}% (需 >{drop_th*100:.2f}%, 即 < {limit:.2f})")

            if require_down and not (today_close < prev_close):
                if is_tracing: log_detail(f"    x [up追] {sym}: 今日未下跌。")
                continue
            if not (today_close < limit):
                if is_tracing: log_detail(f"    x [up追] {sym}: 跌幅不足，不追。")
                continue

            chase_n = max(1, sum(1 for _, p in after if p < limit))
            result[sym] = chase_n
            log_detail(f"    + [up追] {sym}: 起点 {anchor_date} -> 今日 {today_close:.2f} 较 {ref_date} 收盘 "
                       f"{ref_close:.2f} 跌 {drop_pct:.2f}% (追×{chase_n})")
    except sqlite3.OperationalError as e:
        log_detail(f"    x [up追] 数据库查询失败: {e}")
    finally:
        conn.close()

    log_detail(f"PE_Volume_up 回溯追完成，共命中 {len(result)} 个: {sorted(result)}")
    if symbol_to_trace:
        if symbol_to_trace in result:
            log_detail(f"📌 [up追总结] {symbol_to_trace}: ✅ 输出 PE_Volume_up 追 (追×{result[symbol_to_trace]})")
        elif symbol_to_trace in anchors:
            log_detail(f"📌 [up追总结] {symbol_to_trace}: ❌ 有起点但未满足条件（见上方日志）")
        else:
            log_detail(f"📌 [up追总结] {symbol_to_trace}: ❌ 窗口内无起点")
    return result

# --- 策略2: PE_Volume_up (T, T-1, T-2 ...活跃且今日上涨) ---
def process_pe_volume_up(db_path, history_json_path, sector_map, target_date_override, symbol_to_trace, log_detail):
    log_detail("\n========== 开始执行 策略2 (PE_Volume_up) ==========")
    
    # 配置参数
    lookback_days = CONFIG.get("COND_UP_HISTORY_LOOKBACK_DAYS", 5) 
    # 修改点：放量检查回溯月份改为3个月
    vol_rank_months = CONFIG.get("COND_UP_VOL_RANK_MONTHS", 2)
    vol_rank_threshold = CONFIG.get("COND_UP_VOL_RANK_THRESHOLD", 4)
    
    log_detail(f"配置: 历史池扫描范围=近N天(T, T-1, T-2...), 放量标准=近{vol_rank_months}个月前{vol_rank_threshold}名")

    # 【回测逻辑】这里处理回测日期
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    # 1. 连接数据库获取全局日期
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    
    # 获取最近 lookback_days 个交易日 (使用稳定基准，避免日历错位)
    global_dates = get_global_trading_dates(cursor, sector_map, base_date, limit=lookback_days)
    
    if len(global_dates) < 2: # 至少需要 T 和 T-1
        log_detail("错误: 交易日数据不足，无法执行策略2。")
        conn.close()
        return [], []
    
    log_detail(f"扫描历史日期范围 (T, T-1, T-2...): {global_dates}")

    # 2. 从History中收集候选股 (仅限 T, T-1, T-2...)
    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
    except Exception:
        conn.close()
        return [], []

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
    log_detail(f"在 T, T-1, T-2... 的历史记录中共扫描到 {len(candidate_symbols)} 个候选 Symbol。")

    # ===== 新增：追踪 symbol 候选池检查 =====
    if symbol_to_trace:
        if symbol_to_trace in candidate_symbols:
            log_detail(f"    !!! 目标 {symbol_to_trace} 在策略2候选池中，将进行条件检查...")
        else:
            log_detail(f"    --- 目标 {symbol_to_trace} 不在策略2候选池中 (未在扫描日期的历史记录中找到)。")

    # [修改点] 拆分分支A和分支B的记录列表
    results_a = [] # 分支A：放量上涨
    results_b = [] # 分支B：缩量上涨
    
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
        # if price_curr <= price_prev or price_curr <= open_curr:
        if price_curr <= price_prev:
            # if is_tracing: log_detail(f"    x 价格未上涨 (收盘{price_curr} <= 昨收{price_prev} 或 <= 今开{open_curr})，跳过。")
            if is_tracing: log_detail(f"    x 价格未上涨 (收盘{price_curr} <= 昨收{price_prev}，跳过。")
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

        # 规则3: 成交量分支逻辑
        if turnover_curr > turnover_prev:
            # === 分支 A: 放量上涨 ===
            # 修改点: 检查今日(T)是否为 3个月内前3名
            is_top_vol = check_turnover_rank(
                cursor, sector, symbol, date_curr, turnover_curr, 
                vol_rank_months, vol_rank_threshold, log_detail, is_tracing
            )
            if is_top_vol:
                results_a.append(symbol)
                if is_tracing: log_detail(f"    ✅ [选中] 放量上涨 (3个月Top3)")
            else:
                if is_tracing: log_detail(f"    x 放量但未满足3个月Top{vol_rank_threshold}。")
        else:
            # === 分支 B: 缩量上涨 ===
            # 修改点: 检查 T, T-1, T-2... 中是否有任意一天是"3个月内前3名"
            # 已经满足: 量缩 (vol_curr < vol_prev) 且 价涨 (price_curr > price_prev)
            
            # 检查列表中的每一天 (T, T-1, T-2)...
            has_high_volume_history = False
            
            # 检查 T, T-1, T-2...
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
                results_b.append(symbol)
                if is_tracing: log_detail(f"    ✅ [选中] 缩量上涨 (近3日存在高量)")
            else:
                if is_tracing: log_detail(f"    x 缩量上涨，但近3日(T,T-1,T-2)均无高量记录。")

    conn.close()
    log_detail(f"策略2 (PE_Volume_up) 筛选完成，共命中 {len(results_a) + len(results_b)} 个 (放量: {len(results_a)}, 缩量: {len(results_b)})。")

    # ===== 新增：策略2 追踪总结 =====
    if symbol_to_trace:
        if symbol_to_trace not in candidate_symbols:
            log_detail(f"📌 [策略2总结] {symbol_to_trace}: ❌ 未命中 — 不在候选池中。")
        elif symbol_to_trace in results_a or symbol_to_trace in results_b:
            log_detail(f"📌 [策略2总结] {symbol_to_trace}: ✅ 命中 PE_Volume_up")
        else:
            log_detail(f"📌 [策略2总结] {symbol_to_trace}: ❌ 未命中 — 在候选池中但未通过筛选条件（见上方详细日志）。")

    # 返回两个列表，以便主函数能够区分分支B
    return sorted(results_a), sorted(results_b)

# --- 策略3: PE_Volume_high (财报持续上升 + 价格突破 + 成交额放量) ---
def process_pe_volume_high(db_path, history_json_path, panel_json_path, sector_map, target_date_override, symbol_to_trace, log_detail, symbol_to_tags_map, hot_tags, hot_tags_t):
    """
    执行策略3：PE_Volume_high
    返回四个分类：
    - 甲类: 两次财报递增 + 最新财报涨跌幅>0 + 价格突破 + 成交额6个月前3名
    - 乙类: 财报日当天 + 最新财报涨跌幅>0 + 成交额4个月前3名
    - 丙类: (无需财报递增/涨跌幅要求) + 价格突破 + 成交额45天前3名
    - 抄底类: 最新日期到最近财报之间曾入选 PE_Volume_high 且今日在指定回调池中
    
    【修改说明】抄底逻辑已移至成交额门槛(门槛1)之前，不再受 2亿成交额门槛限制；
                并补全了抄底逻辑的详细 trace 日志。
    """
    log_detail("\n========== 开始执行 策略3 (PE_Volume_high - 财报突破放量 & 抄底扫描) ==========")
    
    # 读取配置
    turnover_lookback_months = CONFIG.get("COND_HIGH_TURNOVER_LOOKBACK_MONTHS", 6)
    turnover_yi_lookback_months = CONFIG.get("COND_HIGH_TURNOVER_YI_LOOKBACK_MONTHS", 4)  # [新增]
    turnover_rank_threshold = CONFIG.get("COND_HIGH_TURNOVER_RANK_THRESHOLD", 3)
    
    # 丙类专用配置
    bing_lookback_days = CONFIG.get("COND_HIGH_TURNOVER_BING_DAYS", 45)
    bing_rank_threshold = CONFIG.get("COND_HIGH_TURNOVER_BING_RANK_THRESHOLD", 3)
    
    log_detail(f"配置参数: 成交额回溯 = {turnover_lookback_months} 个月(甲类) / {turnover_yi_lookback_months} 个月(乙类) / {bing_lookback_days} 天(丙类), 排名阈值 = Top {turnover_rank_threshold}")
    
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

    # 预建索引 symbol -> [(date, 原始带后缀记录)]，避免每个 symbol 都全量遍历历史 (原为 O(symbol数×历史条数))
    hist_high_index = {}
    if isinstance(hist_pe_vol_high, dict):
        for h_date, h_list in hist_pe_vol_high.items():
            if not isinstance(h_list, list):
                continue
            for s in h_list:
                hist_high_index.setdefault(clean_symbol(s), []).append((h_date, s))

    # ================= 加载当前回调池 (拆分基础池和扩展池) =================
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
    
    # 四个分类的结果集
    results_jia = []     # 甲类
    results_yi = []      # 乙类
    results_bing = []    # 丙类
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
        
        # 获取当前 symbol 的所有 tags，并检查是否命中 HOT_TAGS_T / HOT_TAGS
        s_tags = set(symbol_to_tags_map.get(symbol, []))
        has_hot_tag_t = bool(s_tags.intersection(hot_tags_t))
        has_hot_tag = bool(s_tags.intersection(hot_tags))
        
        if is_tracing:
            log_detail(f"\n--- 正在检查 {symbol} (策略3) ---")
            log_detail(f"    - Tags: {sorted(list(s_tags))}")
            log_detail(f"    - 命中 HOT_TAGS: {has_hot_tag}, 命中 HOT_TAGS_T: {has_hot_tag_t}")
        
        # 实盘/回测统一按 base_date 截止，避免读到未来排期的财报日或与回调池日期错位
        cursor.execute("SELECT date, price FROM Earning WHERE name = ? AND date <= ? ORDER BY date ASC", (symbol, base_date))
        
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
                log_detail(f"    x [失败] 财报日收盘价数据不完整 (期望{len(all_er_dates)}条, 实际{len(price_data)}条)")
            continue
        
        all_er_prices = [p[1] for p in price_data]
        latest_er_price = all_er_prices[-1]
        
        # 3. 计算财报条件
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
        
        query = f'SELECT date, price, volume, open FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 2'
        cursor.execute(query, (symbol, base_date))
        
        rows = cursor.fetchall()
        
        if len(rows) < 2 or rows[0][1] is None or rows[0][2] is None or rows[0][3] is None or rows[1][1] is None or rows[1][2] is None:
            if is_tracing:
                log_detail(f"    x [失败] 无法获取最新两天交易数据")
            continue
        
        latest_date, latest_price, latest_volume, latest_open = rows[0]
        prev_date, prev_price, prev_volume, _ = rows[1]
        
        latest_turnover = latest_price * latest_volume
        prev_turnover = prev_price * prev_volume
        
        if is_tracing:
            log_detail(f"    - 最新交易日: {latest_date}, 今日价: {latest_price}, 昨日价: {prev_price}, 今日开盘: {latest_open}")
            log_detail(f"    - 今日成交额: {latest_turnover:,.0f}, 昨日成交额: {prev_turnover:,.0f}")

        # ================= 抄底逻辑 (已上移至成交额门槛之前) =================
        # ================= 不受 2亿成交额门槛 / 今日上涨放量门槛 限制 =========
        cond_chaodi = False
        
        # 1. 检查历史：从最新财报日到今天，该股是否以"甲"(或带HOT_TAGS_T的乙/丙)进入过 PE_Volume_high
        was_in_high_history = False
        latest_jia_history_date = None  # 追踪最近一次有效历史出现的日期，用于路径C
        
        for h_date, s_with_suffix in hist_high_index.get(symbol, ()):
            # 用 "<" 排除当天自身的记录：回测/同日重跑时当天的甲已写入 history，不能拿来证明"曾入选"(前视偏差)
            if not (latest_er_date <= h_date < latest_date):
                continue
            is_valid_history = False
            if "甲" in s_with_suffix:
                is_valid_history = True
            # elif ("乙" in s_with_suffix or "丙" in s_with_suffix) and has_hot_tag_t:
            #     is_valid_history = True

            if is_tracing and ("乙" in s_with_suffix) and not is_valid_history:
                log_detail(f"    - [抄底] 忽略乙类记录 {h_date} -> {s_with_suffix}（乙不参与抄底）")
            if is_valid_history:
                was_in_high_history = True
                if is_tracing:
                    log_detail(f"    - [抄底] 发现有效历史记录: {h_date} -> {s_with_suffix}")
                if latest_jia_history_date is None or h_date > latest_jia_history_date:
                    latest_jia_history_date = h_date
        
        if is_tracing:
            log_detail(f"    - [抄底] 历史区间: {latest_er_date} ~ {latest_date}, 是否有有效历史: {was_in_high_history}")
            if latest_jia_history_date:
                log_detail(f"    - [抄底] 最近有效历史(甲/带Tag乙丙)出现日期: {latest_jia_history_date}")
        
        if was_in_high_history:
            # 路径 A: 跌幅池抄底
            in_base_pool = symbol in base_valid_pool
            in_extended_pool = has_hot_tag and (symbol in extended_valid_pool)
            
            if is_tracing:
                log_detail(f"    - [抄底-路径A] 在基础回调池: {in_base_pool} | 在扩展池且含HOT_TAGS: {in_extended_pool} (has_hot_tag={has_hot_tag}, in_extended={symbol in extended_valid_pool})")
            
            if in_base_pool or in_extended_pool:
                cond_chaodi = True
                if is_tracing: 
                    pool_match_reason = "基础回调池" if in_base_pool else "扩展回调池(带HOT_TAGS)"
                    log_detail(f"    ✅ [抄底] 命中 [回调池路径A] ({pool_match_reason})")
            
            # 路径 B: 放量下跌抄底 (今日价格下跌 且 成交额是近45天前2名)
            else:
                cond_price_down_today = (latest_price < prev_price) and (latest_price < latest_open)
                if is_tracing:
                    log_detail(f"    - [抄底-路径B] 今日下跌(收盘<昨收 且 收盘<今开): {cond_price_down_today}")
                if cond_price_down_today:
                    lookback_days = CONFIG.get("COND_HIGH_TURNOVER_BING_DAYS", 45) 
                    rank_threshold = 2 # 保持您要求的排名前2名
                    
                    is_top2_recent = check_turnover_rank_by_days(
                        cursor, sector, symbol, latest_date, latest_turnover,
                        lookback_days, rank_threshold, log_detail, is_tracing
                    )
                    if is_top2_recent:
                        cond_chaodi = True
                        if is_tracing: log_detail(f"    ✅ [抄底] 命中 [放量下跌路径B] (近{lookback_days}天成交额Top{rank_threshold})")
                    else:
                        if is_tracing: log_detail(f"    - [抄底-路径B] 成交额未进入近{lookback_days}天Top{rank_threshold}，路径B失败")
            
            # 路径 C: 缩量回调后缩量上涨
            if not cond_chaodi and latest_jia_history_date is not None:
                cond_c_price_up = (latest_price > prev_price) and (latest_price > latest_open)
                cond_c_turnover_down = (latest_turnover < prev_turnover)
                
                if is_tracing:
                    log_detail(f"    - [抄底-路径C] 今日缩量上涨? 价格上涨={cond_c_price_up}, 成交额缩量={cond_c_turnover_down}")
                
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
                                log_detail(f"    - [抄底-路径C] 中断: 今日收盘价 {latest_price:.2f} 是自甲日({latest_jia_history_date})以来最高价，不符合抄底逻辑。")
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
                                        log_detail(f"      [路径C] 中断于 {curr_d}: 价格 {prev_p_c:.2f}->{curr_p:.2f}, 开盘 {curr_open:.2f}, 成交额 {prev_to:,.0f}->{curr_to:,.0f}")
                                    break
                            
                            if all_shrink_down:
                                cond_chaodi = True
                                middle_days = len(all_rows_c) - 2
                                if is_tracing:
                                    log_detail(f"    ✅ [抄底] 命中 [缩量回调路径C] (甲日: {latest_jia_history_date}, 连续缩量下跌天数: {middle_days})")
                    else:
                        if is_tracing:
                            log_detail(f"    - [抄底-路径C] 数据不足，甲日到今天仅 {len(all_rows_c)} 条记录 (需要>=3)")
        else:
            if is_tracing:
                log_detail(f"    - [抄底] 财报日至今未发现有效历史入选记录，跳过抄底判断。")

        if cond_chaodi:
            results_chaodi.append(symbol)
            if is_tracing:
                log_detail(f"    ✅ [选中-抄底类] 满足历史入选+今日回调/放量/缩量回调条件")

        # ================= 以下为甲乙丙逻辑，仍受成交额门槛限制 ===============
        
        # 门槛 (仅甲乙丙): 成交额门槛
        turnover_threshold = 80000000
        threshold_desc = "8千万"
        if has_hot_tag_t:
            turnover_threshold = 50000000
            threshold_desc = "0.5亿 (命中 HOT_TAGS_T)"
            
        # 门槛 1: 成交额检查 (只过滤甲乙丙，抄底已在上方处理完毕)
        if latest_turnover < turnover_threshold:
            if is_tracing:
                log_detail(f"    x [过滤-甲乙丙] 最新成交额 {latest_turnover:,.0f} 不足 {threshold_desc}，跳过甲乙丙判断 (抄底已单独处理)。")
            continue
        
        # 门槛 2: 今日上涨
        cond_price_up_today = (latest_price > prev_price) or (latest_price > latest_open)
        # 门槛 3: 今日成交额 > 昨日成交额
        cond_turnover_up_today = (latest_turnover > prev_turnover)
        
        if is_tracing:
            log_detail(f"    - [甲乙丙] 今日上涨: {cond_price_up_today}, 今日放量: {cond_turnover_up_today}")

        # 如果未上涨 或 未放量，则跳过甲乙丙的判断
        if not (cond_price_up_today and cond_turnover_up_today):
            if is_tracing: log_detail(f"    x [失败-甲乙丙] 今日未上涨 或 今日未放量")
            continue 
        
        # 条件D: 价格突破财报日收盘价
        cond_price_breakout = (latest_price >= latest_er_price)
        if is_tracing:
            log_detail(f"    - 条件D (价格突破财报): {latest_price:.2f} >= {latest_er_price:.2f} = {cond_price_breakout}")
                
        # 条件E: 成交额为 N 个月前3名 (甲类，N=6)
        cond_turnover_jia_top3 = check_turnover_rank(
            cursor, sector, symbol, latest_date, latest_turnover,
            turnover_lookback_months, turnover_rank_threshold,
            log_detail, is_tracing
        )

        # 条件E2: 成交额为 N 个月前3名 (乙类，N=4)
        cond_turnover_yi_top3 = check_turnover_rank(
            cursor, sector, symbol, latest_date, latest_turnover,
            turnover_yi_lookback_months, turnover_rank_threshold,
            log_detail, is_tracing
        )

        # 丙类：检查成交额是否为过去45天的前3名
        cond_turnover_45d_top3 = check_turnover_rank_by_days(
            cursor, sector, symbol, latest_date, latest_turnover,
            bing_lookback_days, bing_rank_threshold,
            log_detail, is_tracing
        )
        
        # ========== 分类判定 ==========
        er_ok = (not CONFIG.get("COND_HIGH_JIA_REQUIRE_ER_INCREASING", True)) or cond_er_increasing
        # 财报发布当日: 最新交易日 == 最新财报日 (与甲回溯中 "er_date 当天出现甲" 的口径一致)
        is_er_day = (latest_date == latest_er_date)

        if er_ok and cond_turnover_jia_top3:
            results_jia.append(symbol)
            if is_tracing:
                log_detail(f"    ✅ [选中-甲类] 价格突破 + {turnover_lookback_months}个月Top{turnover_rank_threshold} "
                           f"(要求财报递增={CONFIG.get('COND_HIGH_JIA_REQUIRE_ER_INCREASING', True)}, 实际递增={cond_er_increasing})")
        
        elif cond_er_pct_positive and cond_turnover_yi_top3:
            # 乙类: 仅财报发布当日出现的才输出
            if is_er_day:
                results_yi.append(symbol)
                if is_tracing:
                    log_detail(f"    ✅ [选中-乙类] 财报日当天({latest_er_date}) + 财报涨幅>0 + {turnover_yi_lookback_months}个月Top{turnover_rank_threshold} "
                               f"(HOT_TAGS_T={has_hot_tag_t}, {'后续可享受深跌追' if has_hot_tag_t else '后续不参与深跌追'})")
            else:
                if is_tracing:
                    log_detail(f"    x [乙类-不输出] 满足乙类条件，但今日({latest_date})非财报日(最新财报日 {latest_er_date})")
        
        elif cond_turnover_45d_top3:
            # 丙类: 继续不输出
            # results_bing.append(symbol)
            if is_tracing:
                log_detail(f"    - [丙类-不输出] 满足丙类条件 ({bing_lookback_days}天Top{bing_rank_threshold})，按配置不输出")
    
    conn.close()
    
    # 去重并排序
    results_jia = sorted(list(set(results_jia)))
    results_yi = sorted(list(set(results_yi)))
    results_bing = sorted(list(set(results_bing)))
    results_chaodi = sorted(list(set(results_chaodi))) # 排序抄底结果
    
    log_detail(f"\n————策略3 Volume_high 最终筛选结果:")
    log_detail(f"  - 甲类 (财报递增+突破+{turnover_lookback_months}月Top{turnover_rank_threshold}): {len(results_jia)} 个: {results_jia}")
    log_detail(f"  - 乙类 (财报日当天+财报涨幅>0+{turnover_yi_lookback_months}月Top{turnover_rank_threshold}): {len(results_yi)} 个: {results_yi}")
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

# --- 策略3 回溯: PE_Volume_high 甲类/乙类(HOT_TAGS_T) -> 财报后深跌 "追" ---
def check_pe_volume_high_jia_retention(db_path, history_json_path, sector_map, current_high_new_symbols,
                                       target_date_override, symbol_to_trace, log_detail,
                                       symbol_to_tags_map=None, hot_tags_t=None):
    """
    修改后规则:
    - 起点：【最新财报日 ～ 基准日之间】出现的、不带"追"的原生甲记录，取区间内最晚一条甲作为锚点
      * 不再强制要求甲出现在财报当天！
    - 乙类维持原有逻辑：仅财报日本身的乙 + 命中HOT_TAGS_T才有资格
    - 触发(任一):
        A. 今日收盘 < 【甲触发日收盘】 * (1 - 阈值)
        B. 今日收盘 < 【甲触发日, 今日】区间最高收盘 * (1 - 阈值)
    - 过滤: 今日已是甲/乙/丙(新触发优先) / 今日即财报日 / 数据过期 / 锚点日无行情 / 超过可选有效期。
    返回: dict {symbol: info_dict}  (info_dict["origin"] = "甲" 或 "乙")
    """
    log_detail("\n========== 执行 PE_Volume_high 甲/乙类回溯机制 (【财报后任意日期出现的甲都可以作为锚点】，财报日乙+HOT_TAGS_T -> 深跌追) ==========")

    if not CONFIG.get("HIGH_JIA_CHASE_ENABLED", True):
        log_detail("    - 已关闭 (HIGH_JIA_CHASE_ENABLED=False)，跳过。")
        return {}

    symbol_to_tags_map = symbol_to_tags_map or {}
    hot_tags_t = set(hot_tags_t or ())

    def has_hot_tag_t(sym):
        return bool(set(symbol_to_tags_map.get(sym, [])) & hot_tags_t)

    drop_th_jia = CONFIG.get("HIGH_JIA_CHASE_DROP_PERCENT", 0.052)
    drop_th_yi = CONFIG.get("HIGH_YI_CHASE_DROP_PERCENT", 0.11)
    max_days = CONFIG.get("HIGH_JIA_CHASE_MAX_TRADING_DAYS", 0) or 0
    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    log_detail(f"   配置: 甲类跌幅阈值 > {drop_th_jia*100:.2f}%, 乙类跌幅阈值 > {drop_th_yi*100:.2f}% "
               f"(较【甲触发日收盘】或【甲触发日以来最高收盘】), "
               f"有效期 = {'不限(直到下次财报)' if max_days <= 0 else f'{max_days}个交易日'}")
    log_detail(f"    配置: 乙类需命中 HOT_TAGS_T 才参与 (HOT_TAGS_T 共 {len(hot_tags_t)} 个标签)")
    log_detail(f"    ✅【修改后】甲锚点：最新财报日之后、基准日之前任意一天原生甲（取最晚一条甲），不再限制财报当日！")

    # 1. 读取历史, 建立 symbol -> {date: {"甲","乙"}} 索引 (只取基准日之前, 避免前视)
    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
    except Exception as e:
        log_detail(f"    x 读取历史文件失败: {e}")
        return {}

    hist_high = history_data.get("PE_Volume_high", {})
    if not isinstance(hist_high, dict) or not hist_high:
        log_detail("    x 历史记录中无 PE_Volume_high 数据，跳过。")
        return {}

    origin_index = {}  # sym -> {date: set(origin)}
    for d, raw_list in hist_high.items():
        if not isinstance(d, str) or d >= base_date or not isinstance(raw_list, list):
            continue
        for raw in raw_list:
            if not isinstance(raw, str) or "追" in raw:
                continue
            if "甲" in raw:
                origin = "甲"
            elif "乙" in raw:
                origin = "乙"
            else:
                continue
            origin_index.setdefault(clean_symbol(raw), {}).setdefault(d, set()).add(origin)

    log_detail(f"   -> 历史中共有 {len(origin_index)} 个 symbol 曾出现过甲/乙类记录，逐个核对。")
    if symbol_to_trace and symbol_to_trace not in origin_index:
        log_detail(f"    --- 目标 {symbol_to_trace} 在基准日之前从未出现过甲/乙类记录，无需回溯。")

    current_set = set(current_high_new_symbols)
    result = {}

    conn = sqlite3.connect(db_path, timeout=60.0)
    try:
        cursor = conn.cursor()
        global_dates = get_global_trading_dates(cursor, sector_map, base_date, limit=1)
        if not global_dates:
            log_detail("    x 无法获取交易日历，跳过。")
            return {}
        today_trading = global_dates[0]
        log_detail(f"    -> 最新交易日 T={today_trading}")

        for sym in sorted(origin_index):
            is_tracing = (sym == symbol_to_trace)
            date_map = origin_index[sym]

            if sym in current_set:
                if is_tracing: log_detail(f"    --- [甲乙回溯] {sym}: 今日已是甲/乙/丙新触发，无需追。")
                continue

            sector = sector_map.get(sym)
            if not sector:
                if is_tracing: log_detail(f"    x [甲乙回溯] {sym}: 未找到板块映射。")
                continue

            # 拿到该标的最新财报日
            cursor.execute("SELECT date FROM Earning WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                           (sym, base_date))
            er_row = cursor.fetchone()
            if not er_row:
                if is_tracing: log_detail(f"    x [甲乙回溯] {sym}: 无财报记录。")
                continue
            er_date = er_row[0]

            if er_date >= today_trading:
                if is_tracing: log_detail(f"    --- [甲乙回溯] {sym}: 今日({er_date})即为财报日，不追。")
                continue

            # ====================== 【核心改动块 START】 ======================
            # 原逻辑：只看财报当天有没有甲/乙
            # 新逻辑：筛选：er_date <= 甲记录日期 < base_date 的所有原生甲，取最晚一条甲作为锚点
            candidate_jia_dates = [d for d in date_map.keys()
                                   if er_date <= d < base_date and "甲" in date_map[d]]
            candidate_yi_dates = [d for d in date_map.keys()
                                  if d == er_date and "乙" in date_map[d]] # 乙类不变：仍然只认财报日本身的乙

            anchor_jia_date = None
            if candidate_jia_dates:
                anchor_jia_date = max(candidate_jia_dates) # 财报后多条甲，取时间最晚的甲作为锚点

            anchor_yi_date = None
            if candidate_yi_dates:
                anchor_yi_date = candidate_yi_dates[0]

            # 资格判定：优先甲（财报后任意时间的甲），其次是财报日的乙+HOT_TAGS_T
            anchor_date = None
            origin = None
            if anchor_jia_date is not None:
                anchor_date = anchor_jia_date
                origin = "甲"
                if is_tracing:
                    log_detail(f"    ✅【甲锚点】最新财报日{er_date}之后，找到原生甲记录，锚定甲触发日：{anchor_jia_date}")
            elif anchor_yi_date is not None:
                if not has_hot_tag_t(sym):
                    if is_tracing:
                        log_detail(f"    x [甲乙回溯] {sym}: 财报日 {er_date} 当天为乙，但未命中 HOT_TAGS_T "
                                   f"(Tags: {sorted(symbol_to_tags_map.get(sym, []))})，不享受追。")
                    continue
                anchor_date = anchor_yi_date
                origin = "乙"
                if is_tracing:
                    log_detail(f"    ✅【乙锚点】财报日本身乙记录，锚定财报日：{anchor_yi_date}")
            else:
                # 既没有财报后甲，也没有合格财报日乙，跳过
                if is_tracing:
                    log_detail(f"    x [甲乙回溯] {sym}: 财报{er_date}之后，没有合格甲；财报当日也无合格乙，跳过")
                continue
            # ====================== 【核心改动块 END】 ======================

            # 从【锚点日期（甲发生日/财报日乙）】取行情，一直到base_date
            cursor.execute(
                f'SELECT date, price FROM "{sector}" WHERE name = ? AND date >= ? AND date <= ? '
                f'AND price IS NOT NULL AND price > 0 ORDER BY date ASC',
                (sym, anchor_date, base_date))
            rows = cursor.fetchall()

            if not rows or rows[0][0] != anchor_date:
                if is_tracing: log_detail(f"     x [甲乙回溯] {sym}: 锚点日 {anchor_date} 无有效收盘价。")
                continue
            if len(rows) < 2:
                if is_tracing: log_detail(f"     x [甲乙回溯] {sym}: 锚点日之后无行情数据。")
                continue
            if rows[-1][0] != today_trading:
                if is_tracing: log_detail(f"    x [甲乙回溯] {sym}: 最新数据日期 {rows[-1][0]} != 最新交易日 {today_trading}，跳过。")
                continue

            elapsed = len(rows) - 1
            if max_days > 0 and elapsed > max_days:
                if is_tracing: log_detail(f"    x [甲乙回溯] {sym}: 距财报日已 {elapsed} 个交易日，超过有效期 {max_days}。")
                continue

            anchor_close = rows[0][1]
            latest_date, latest_close = rows[-1]
            peak_close = max(r[1] for r in rows)
            peak_date = max(r[0] for r in rows if r[1] == peak_close)  # 并列取最晚

            # 按来源选阈值: 甲用 drop_th_jia，乙用 drop_th_yi
            drop_th_sym = drop_th_jia if origin == "甲" else drop_th_yi

            drop_anchor = (anchor_close - latest_close) / anchor_close
            drop_peak = (peak_close - latest_close) / peak_close
            hit_anchor = latest_close < anchor_close * (1 - drop_th_sym)
            hit_peak = latest_close < peak_close * (1 - drop_th_sym)

            if is_tracing:
                log_detail(f"    - [甲乙回溯] {sym}: 锚点日 {anchor_date} 收盘 {anchor_close:.2f} (锚点类型={origin}"
                           f"{'+HOT_TAGS_T' if origin == '乙' else ''}) | "
                           f"区间最高 {peak_close:.2f} ({peak_date}) | 今日 {latest_date} 收盘 {latest_close:.2f} "
                           f"| 距锚点第 {elapsed} 个交易日")
                log_detail(f"      较锚点日收盘跌幅 {drop_anchor*100:.2f}% -> {hit_anchor} | "
                           f"较区间最高跌幅 {drop_peak*100:.2f}% -> {hit_peak} (本条阈值 >{drop_th_sym*100:.2f}%, 来源{origin})")

            if not (hit_anchor or hit_peak):
                if is_tracing: log_detail(f"    x [甲乙回溯] {sym}: 两项跌幅均未超过阈值({origin}类 >{drop_th_sym*100:.2f}%)，不追。")
                continue

            reasons = []
            if hit_anchor: reasons.append(f"较锚点日({anchor_date})跌{drop_anchor*100:.1f}%")
            if hit_peak: reasons.append(f"较高点({peak_date})跌{drop_peak*100:.1f}%")
            result[sym] = {
                "origin": origin,
                "anchor_date": anchor_date, "anchor_close": anchor_close,
                "peak_date": peak_date, "peak_close": peak_close,
                "latest_close": latest_close, "reasons": reasons,
            }
            log_detail(f"    + [{origin}回溯-追] {sym}: 锚点 {anchor_date} {origin} -> 今日 {latest_close:.2f} ({' & '.join(reasons)})")
    except sqlite3.OperationalError as e:
        log_detail(f"    x [甲乙回溯] 数据库查询失败: {e}")
    finally:
        conn.close()

    n_jia = sum(1 for v in result.values() if v["origin"] == "甲")
    n_yi = len(result) - n_jia
    log_detail(f"PE_Volume_high 甲/乙类回溯完成，共命中 {len(result)} 个 (甲源 {n_jia}, 乙源 {n_yi}): {sorted(result.keys())}")
    if symbol_to_trace:
        if symbol_to_trace in result:
            log_detail(f"📌 [甲乙回溯总结] {symbol_to_trace}: ✅ 输出为 PE_Volume_high 追 (来源: {result[symbol_to_trace]['origin']}, 锚点日期：{result[symbol_to_trace]['anchor_date']})")
        else:
            log_detail(f"📌 [甲乙回溯总结] {symbol_to_trace}: ❌ 未命中（见上方详细日志）")
    return result

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
def process_pe_hot(db_path, sector_map, target_date_override, panel_json_path, history_json_path,
                   exclude_symbols, whitelist_symbols, prev_hot_symbols, log_detail):
    """
    检索候选池中，满足 (白名单 或 超大市值) 且不在 exclude_symbols 中的 symbol，并满足:
    - 最新成交额 >= 门槛 (PE_HOT_MIN_TURNOVER, 默认2亿)
      * 若前一交易日已在 PE_Hot 中，且今日继续下跌(收盘 < 昨收)，门槛放宽为 门槛 * PE_HOT_CONTINUE_DOWN_TURNOVER_RATIO
    - 过去10天内的最低收盘价没有比最新收盘价低超过3%
    返回: pe_hot_list (list), pe_hot_notes (dict)
    """
    min_mcap = CONFIG.get("PE_HOT_MIN_MARKET_CAP", 150000000000)
    min_mcap_yi = min_mcap / 100000000

    min_turnover = CONFIG.get("PE_HOT_MIN_TURNOVER", 200000000)
    continue_ratio = CONFIG.get("PE_HOT_CONTINUE_DOWN_TURNOVER_RATIO", 0.8)
    relaxed_turnover = min_turnover * continue_ratio

    log_detail(f"\n========== 开始执行 策略: PE_Hot (白名单/超大市值检索 + 成交额过滤 + 10天防暴涨过滤) ==========")
    log_detail(f"配置参数: 超大市值门槛 = {min_mcap_yi:.0f}亿")
    log_detail(f"配置参数: 成交额门槛 = {min_turnover/1e8:.2f}亿; "
               f"前日在PE_Hot且今日继续下跌时放宽为 {relaxed_turnover/1e8:.2f}亿 (比例 {continue_ratio})")

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

    base_date = target_date_override if target_date_override else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    # 超大市值
    high_mcap_symbols = set()
    try:
        cursor.execute("SELECT symbol FROM MNSPP WHERE marketcap >= ?", (min_mcap,))
        high_mcap_symbols = {r[0] for r in cursor.fetchall()}
        log_detail(f"从 MNSPP 表成功获取 {len(high_mcap_symbols)} 个市值 >= {min_mcap_yi:.0f}亿 的 Symbol。")
    except Exception as e:
        log_detail(f"警告: 无法读取 MNSPP 表的市值数据: {e}")

    # 候选池
    pool_symbols_with_notes = {}
    try:
        with open(history_json_path, 'r', encoding='utf-8') as f:
            history_data = json.load(f)

        history_loaded = False
        for group in target_groups:
            group_history = history_data.get(group, {})
            if base_date in group_history:
                history_loaded = True
                for sym_with_note in group_history[base_date]:
                    pool_symbols_with_notes[clean_symbol(sym_with_note)] = sym_with_note

        if not history_loaded and not target_date_override:
            with open(panel_json_path, 'r', encoding='utf-8') as f:
                panel_data = json.load(f)
            for group in target_groups:
                if group in panel_data and isinstance(panel_data[group], dict):
                    for sym, note in panel_data[group].items():
                        pool_symbols_with_notes[sym] = note if note else sym

        log_detail(f"已加载 PE_Hot 候选池，共 {len(pool_symbols_with_notes)} 个 unique symbol。")
    except Exception as e:
        log_detail(f"错误: 读取候选池数据失败: {e}")

    try:
        for sym, note in pool_symbols_with_notes.items():
            is_whitelist = sym in whitelist_symbols
            is_high_mcap = sym in high_mcap_symbols
            if not (is_whitelist or is_high_mcap):
                continue
            if sym in exclude_symbols:
                continue

            sector = sector_map.get(sym)
            if not sector:
                continue

            query = f'SELECT price, volume FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 10'
            cursor.execute(query, (sym, base_date))
            rows = cursor.fetchall()

            if not rows or rows[0][0] is None or rows[0][1] is None:
                log_detail(f"    x [过滤-PE_Hot] {sym} 无法获取最新交易数据")
                continue

            latest_price, latest_volume = rows[0]
            turnover = latest_price * latest_volume

            # 是否满足"前日在 PE_Hot 且今日继续下跌"的放宽条件
            prev_price = rows[1][0] if len(rows) > 1 else None
            was_in_prev_hot = sym in prev_hot_symbols
            is_continue_down = prev_price is not None and latest_price < prev_price
            relaxed = was_in_prev_hot and is_continue_down
            threshold = relaxed_turnover if relaxed else min_turnover
            threshold_desc = f"{threshold/1e8:.2f}亿" + ("(放宽: 前日在PE_Hot+今日继续下跌)" if relaxed else "")

            if turnover < threshold:
                log_detail(f"    x [过滤-PE_Hot] {sym} 成交额不足{threshold_desc} (仅 {turnover/1e8:.2f}亿)")
                continue

            # 10天防暴涨过滤
            valid_prices = [r[0] for r in rows if r[0] is not None]
            min_price_10d = min(valid_prices) if valid_prices else latest_price
            if min_price_10d < latest_price * 0.97:
                log_detail(f"    x [过滤-PE_Hot] {sym} 10天内最低价({min_price_10d:.2f})比最新价({latest_price:.2f})低超过3%")
                continue

            if sym not in pe_hot_list:
                pe_hot_list.append(sym)
                pe_hot_notes[sym] = note
                reasons = []
                if is_whitelist: reasons.append("白名单")
                if is_high_mcap: reasons.append("超大市值")
                log_detail(f"    ✅ [选中-PE_Hot] {sym} (理由: {'+'.join(reasons)}, 成交额: {turnover/1e8:.2f}亿, "
                           f"门槛: {threshold_desc}, 10天最低: {min_price_10d:.2f})")
    except Exception as e:
        log_detail(f"错误: 执行 PE_Hot 策略失败: {e}")
    finally:
        conn.close()

    pe_hot_list = sorted(pe_hot_list)
    log_detail(f"PE_Hot 筛选完成，共命中 {len(pe_hot_list)} 个: {pe_hot_list}")
    return pe_hot_list, pe_hot_notes

# --- 4. 主执行流程 ---
def run_pe_volume_logic(log_detail):
    log_detail("PE_Volume 双策略程序开始运行...")
    if SYMBOL_TO_TRACE: log_detail(f"当前追踪的 SYMBOL: {SYMBOL_TO_TRACE}")

    base_date_str = resolve_base_date(TARGET_DATE)

    if TARGET_DATE:
        log_detail(f"\n⚠️⚠️⚠️ 注意：当前处于【回测模式】，目标日期：{TARGET_DATE} ⚠️⚠️⚠️")
        log_detail("本次运行将【不会】更新 Panel 和 History JSON 文件。")

    # 1. 加载配置和映射
    tag_blacklist, hot_tags, hot_tags_t = load_tag_settings(TAGS_SETTING_JSON_FILE)
    symbol_to_sector_map = load_all_symbols(SECTORS_JSON_FILE, CONFIG["TARGET_SECTORS"])
    symbol_to_tags_map = load_symbol_tags(DESCRIPTION_JSON_FILE)

    if not symbol_to_sector_map:
        log_detail("错误: 无法加载板块映射，程序终止。")
        return

    # [新增] 性能: 自动建索引 (只建一次)
    if CONFIG.get("AUTO_CREATE_DB_INDEXES", True):
        try:
            ensure_db_indexes(DB_FILE, set(symbol_to_sector_map.values()) | {"Earning"}, log_detail)
        except sqlite3.Error as e:
            log_detail(f"提示: 自动建索引失败(不影响运行): {e}")

    # [修复] History 记录日期统一使用"实际最新交易日"，避免周一/节后用自然日(周日)做 key
    history_date_str = base_date_str
    try:
        _conn = sqlite3.connect(DB_FILE, timeout=60.0)
        try:
            _gd = get_global_trading_dates(_conn.cursor(), symbol_to_sector_map, base_date_str, limit=1)
        finally:
            _conn.close()
        if _gd:
            history_date_str = _gd[0]
    except sqlite3.Error as e:
        log_detail(f"提示: 获取最新交易日失败，History 日期退回 {base_date_str}: {e}")
    if history_date_str != base_date_str:
        log_detail(f"提示: 基准日 {base_date_str} 非交易日，History 记录日期使用最新交易日 {history_date_str}")

    # ================= 动态白名单 =================
    whitelist_symbols = generate_whitelist_symbols(
        DB_FILE, symbol_to_sector_map, base_date_str, SYMBOL_TO_TRACE, log_detail
    )

    # ================= 策略 1 =================
    raw_pe_volume = pe_volume(
        DB_FILE, EARNING_HISTORY_JSON_FILE, symbol_to_sector_map,
        TARGET_DATE, SYMBOL_TO_TRACE, log_detail
    )
    final_pe_volume = sorted(list(set(raw_pe_volume)))

    # 回溯保留
    retention_info = check_pe_volume_retention(
        DB_FILE, EARNING_HISTORY_JSON_FILE, PANEL_JSON_FILE, final_pe_volume,
        symbol_to_sector_map, TARGET_DATE, SYMBOL_TO_TRACE, log_detail
    )
    retention_symbols = sorted(retention_info.keys())
    if retention_symbols:
        final_pe_volume = sorted(list(set(final_pe_volume) | set(retention_symbols)))
        log_detail(f"合并回溯结果后，PE_Volume 总数: {len(final_pe_volume)} (新增 {len(retention_symbols)} 个)")

    # [新增] 补捞 (必须在回溯保留之后：只处理今日没有任何形式 PE_Volume 的)
    backfill_info = check_pe_volume_backfill(
        DB_FILE, EARNING_HISTORY_JSON_FILE, PANEL_JSON_FILE, final_pe_volume,
        symbol_to_sector_map, TARGET_DATE, SYMBOL_TO_TRACE, log_detail
    )
    backfill_symbols = sorted(backfill_info.keys())
    if backfill_symbols:
        final_pe_volume = sorted(list(set(final_pe_volume) | set(backfill_symbols)))
        log_detail(f"合并补捞结果后，PE_Volume 总数: {len(final_pe_volume)} (新增 {len(backfill_symbols)} 个)")

    volume_chase_info = dict(retention_info)
    volume_chase_info.update(backfill_info)

    # ================= 策略 2 (受 ENABLE_PE_VOLUME_UP 控制) =================
    ENABLE_UP = CONFIG.get("ENABLE_PE_VOLUME_UP", False)
    raw_pe_volume_up_a, raw_pe_volume_up_b = [], []
    vol_up_new = set()
    vol_up_chase_info = {}
    vol_up_chase_symbols = []
    final_pe_volume_up = []

    if ENABLE_UP:
        raw_pe_volume_up_a, raw_pe_volume_up_b = process_pe_volume_up(
            DB_FILE, EARNING_HISTORY_JSON_FILE, symbol_to_sector_map,
            TARGET_DATE, SYMBOL_TO_TRACE, log_detail
        )
        vol_up_new = set(raw_pe_volume_up_a) | set(raw_pe_volume_up_b)

        # PE_Volume_up 回溯追
        vol_up_chase_info = check_pe_volume_up_retention(
            DB_FILE, EARNING_HISTORY_JSON_FILE, PANEL_JSON_FILE, vol_up_new,
            symbol_to_sector_map, TARGET_DATE, SYMBOL_TO_TRACE, log_detail
        )
        vol_up_chase_symbols = sorted(vol_up_chase_info.keys())
        final_pe_volume_up = sorted(list(vol_up_new | set(vol_up_chase_symbols)))
    else:
        log_detail("\n[策略2 PE_Volume_up] 已屏蔽 (ENABLE_PE_VOLUME_UP=False)，跳过计算与输出。")

    # ================= 策略 3 =================
    raw_pe_volume_high_jia, raw_pe_volume_high_yi, raw_pe_volume_high_bing, raw_pe_volume_high_chaodi = process_pe_volume_high(
        DB_FILE, EARNING_HISTORY_JSON_FILE, PANEL_JSON_FILE, symbol_to_sector_map,
        TARGET_DATE, SYMBOL_TO_TRACE, log_detail,
        symbol_to_tags_map, hot_tags, hot_tags_t
    )

    high_new_symbols = set(raw_pe_volume_high_jia) | set(raw_pe_volume_high_yi) | set(raw_pe_volume_high_bing)
    high_chase_info = check_pe_volume_high_jia_retention(
        DB_FILE, EARNING_HISTORY_JSON_FILE, symbol_to_sector_map, high_new_symbols,
        TARGET_DATE, SYMBOL_TO_TRACE, log_detail,
        symbol_to_tags_map=symbol_to_tags_map, hot_tags_t=hot_tags_t,
    )
    raw_pe_volume_high_chase = sorted(high_chase_info.keys())
    final_pe_volume_high = sorted(list(high_new_symbols | set(raw_pe_volume_high_chaodi) | set(raw_pe_volume_high_chase)))

    # ================= Tag 黑名单 (仅标记，不剔除) =================
    def filter_blacklisted_tags(symbols):
        for sym in symbols:
            intersect = set(symbol_to_tags_map.get(sym, [])) & tag_blacklist
            if intersect and sym == SYMBOL_TO_TRACE:
                log_detail(f"🛑 [Tag过滤] {sym} 命中黑名单标签: {intersect} -> 已保留并标记为'黑'。")
        return sorted(symbols)

    filtered_pe_volume = filter_blacklisted_tags(final_pe_volume)
    filtered_pe_volume_up = filter_blacklisted_tags(final_pe_volume_up)
    filtered_pe_volume_high_jia = filter_blacklisted_tags(raw_pe_volume_high_jia)
    filtered_pe_volume_high_yi = filter_blacklisted_tags(raw_pe_volume_high_yi)
    filtered_pe_volume_high_bing = filter_blacklisted_tags(raw_pe_volume_high_bing)
    filtered_pe_volume_high_chaodi = filter_blacklisted_tags(raw_pe_volume_high_chaodi)
    filtered_pe_volume_high_chase = filter_blacklisted_tags(raw_pe_volume_high_chase)
    filtered_pe_volume_high = filter_blacklisted_tags(final_pe_volume_high)

    # 4. 构建备注
    def build_symbol_note_map(symbols, existing_notes=None, suffix_tag=""):
        note_map = {}
        for sym in symbols:
            orig_note = ""
            if existing_notes and sym in existing_notes:
                n = existing_notes[sym]
                orig_note = n[len(sym):] if n.startswith(sym) else n.replace(sym, "")
                orig_note = strip_chase(orig_note)
            new_suffix = orig_note
            if suffix_tag and suffix_tag not in new_suffix:
                new_suffix += suffix_tag
            if set(symbol_to_tags_map.get(sym, [])) & tag_blacklist:
                if "黑" not in new_suffix:
                    new_suffix += "黑"
            note_map[sym] = f"{sym}{new_suffix}"
        return note_map

    all_existing_notes = {}
    try:
        if TARGET_DATE:
            with open(EARNING_HISTORY_JSON_FILE, 'r', encoding='utf-8') as f:
                hist_data = json.load(f)
            group_content = hist_data.get("PE_Volume", {})
            if isinstance(group_content, dict) and history_date_str in group_content:
                for sym_with_note in group_content[history_date_str]:
                    sym = clean_symbol(sym_with_note)
                    note_clean = strip_chase(sym_with_note)
                    if len(note_clean) > len(all_existing_notes.get(sym, "")):
                        all_existing_notes[sym] = note_clean
        else:
            with open(PANEL_JSON_FILE, 'r', encoding='utf-8') as f:
                p_data = json.load(f)
            group_content = p_data.get("PE_Volume", {})
            if isinstance(group_content, dict):
                for s, n in group_content.items():
                    n_clean = strip_chase(n)
                    if len(n_clean) > len(all_existing_notes.get(s, "")):
                        all_existing_notes[s] = n_clean
    except Exception as e:
        log_detail(f"提示: 读取现有备注时出错: {e}")

    # PE_Volume 备注 + 追 (回溯保留 & 补捞)
    pe_volume_notes = build_symbol_note_map(filtered_pe_volume, existing_notes=all_existing_notes)
    for sym, chase_n in volume_chase_info.items():
        if sym in pe_volume_notes:
            pe_volume_notes[sym] += format_chase(chase_n)

    # PE_Volume_up 备注: 缩量加"空"，回溯追加"追"
    pe_volume_up_notes = build_symbol_note_map(filtered_pe_volume_up)
    for sym in raw_pe_volume_up_b:
        if sym in pe_volume_up_notes and "空" not in pe_volume_up_notes[sym]:
            pe_volume_up_notes[sym] += "空"
    for sym, chase_n in vol_up_chase_info.items():
        if sym in pe_volume_up_notes:
            pe_volume_up_notes[sym] += format_chase(chase_n)

    # 策略3 备注
    pe_vol_high_notes = {}
    for sym in filtered_pe_volume_high:
        categories = []
        if sym in filtered_pe_volume_high_jia:
            categories.append("甲")
        elif sym in filtered_pe_volume_high_yi:
            categories.append("乙")
        elif sym in filtered_pe_volume_high_bing:
            categories.append("丙")
        if not categories:
            if sym in filtered_pe_volume_high_chaodi:
                categories.append("抄底")
            if sym in filtered_pe_volume_high_chase:
                categories.append("追")
        suffix = "".join(categories)
        if set(symbol_to_tags_map.get(sym, [])) & tag_blacklist:
            suffix += "黑"
        pe_vol_high_notes[sym] = f"{sym}{suffix}"

    # ================= 读取前一交易日 PE_Hot 名单 (供 PE_Hot 放宽规则 & 连续命中追字 共用) =================
    prev_hot_date = None
    prev_hot_symbols = set()
    try:
        with open(EARNING_HISTORY_JSON_FILE, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
        hist_pe_hot = history_data.get("PE_Hot", {})
        if hist_pe_hot:
            prev_hot_date = next((d for d in sorted(hist_pe_hot.keys(), reverse=True) if d < history_date_str), None)
            if prev_hot_date:
                prev_hot_symbols = {clean_symbol(s) for s in hist_pe_hot[prev_hot_date]}
    except Exception as e:
        log_detail(f"读取前一日 PE_Hot 名单失败: {e}")
        
    # ================= PE_Hot =================
    exclude_symbols_for_hot = set()
    pe_hot_list, pe_hot_notes = process_pe_hot(
        DB_FILE, symbol_to_sector_map, TARGET_DATE, PANEL_JSON_FILE,
        EARNING_HISTORY_JSON_FILE, exclude_symbols_for_hot, whitelist_symbols,
        prev_hot_symbols, log_detail
    )

    # ================= PE_Hot 连续命中追加"追" =================
    if prev_hot_date:
        for sym in pe_hot_list:
            if sym in prev_hot_symbols and sym in pe_hot_notes:
                pe_hot_notes[sym] = strip_chase(pe_hot_notes[sym]) + "追"
                if SYMBOL_TO_TRACE == sym:
                    log_detail(f"    - [PE_Hot连续命中] {sym} 在上一期({prev_hot_date})也存在，追加'追'字。")

    # ================= 追踪汇总 =================
    if SYMBOL_TO_TRACE:
        T = SYMBOL_TO_TRACE
        log_detail(f"\n{'='*60}")
        log_detail(f"📌📌📌 [{T}] 全策略命中汇总 📌📌📌")
        log_detail(f"  策略1 PE_Volume (放量下跌):     {'✅ 命中' if T in filtered_pe_volume else '❌ 未命中'}")
        log_detail(f"  策略1 回溯保留 (Retention):     {'✅ 被捞回' if T in retention_symbols else '❌ 未捞回'}")
        log_detail(f"  策略1 补捞 (Backfill):          {'✅ 补出' if T in backfill_symbols else '❌ 未补出'}")
        if ENABLE_UP:
            log_detail(f"  策略2 PE_Volume_up (活跃上涨):  {'✅ 命中' if T in filtered_pe_volume_up else '❌ 未命中'}")
            log_detail(f"  策略2 回溯追 (Up Chase):        {'✅ 追' if T in vol_up_chase_symbols else '❌ 未追'}")
        high_parts = []
        if T in filtered_pe_volume_high_jia: high_parts.append("甲")
        if T in filtered_pe_volume_high_yi: high_parts.append("乙")
        if T in filtered_pe_volume_high_bing: high_parts.append("丙")
        if T in filtered_pe_volume_high_chaodi: high_parts.append("抄底")
        if T in filtered_pe_volume_high_chase:
            high_parts.append(f"追({high_chase_info[T]['origin']}回溯)")
        log_detail(f"  策略3 PE_Volume_high (财报突破):{'✅ 命中 (' + ','.join(high_parts) + ')' if high_parts else '❌ 未命中'}")
        log_detail(f"  动态白名单 (低点后涨幅>{CONFIG.get('WHITELIST_MIN_GROWTH', 1.1)*100:.0f}%): {'✅ 在白名单' if T in whitelist_symbols else '❌ 不在白名单'}")
        log_detail(f"  策略6 PE_Hot (白名单/超大市值):   {'✅ 命中' if T in pe_hot_list else '❌ 未命中'}")
        log_detail(f"{'='*60}")

    # 5. 回测安全拦截
    if TARGET_DATE:
        log_detail("\n" + "="*60)
        log_detail(f"🛑 [安全拦截] 回测模式 (Date: {TARGET_DATE}) 已启用。")
        log_detail(f"📊 [策略1] PE_Volume 命中: {len(filtered_pe_volume)} 个 (回溯 {len(retention_symbols)}, 补捞 {len(backfill_symbols)})")
        if ENABLE_UP:
            log_detail(f"📊 [策略2] PE_Volume_up 命中: {len(filtered_pe_volume_up)} 个 (回溯追 {len(vol_up_chase_symbols)})")
        log_detail(f"📊 [策略3] PE_Volume_high 总计命中: {len(filtered_pe_volume_high)} 个")
        log_detail(f"    - 甲类: {len(filtered_pe_volume_high_jia)} 个")
        log_detail(f"    - 乙类: {len(filtered_pe_volume_high_yi)} 个")
        log_detail(f"    - 丙类: {len(filtered_pe_volume_high_bing)} 个")
        log_detail(f"    - 抄底类: {len(filtered_pe_volume_high_chaodi)} 个")
        n_chase_yi = sum(1 for v in high_chase_info.values() if v["origin"] == "乙")
        log_detail(f"    - 甲/乙回溯追: {len(filtered_pe_volume_high_chase)} 个 (其中乙源 {n_chase_yi} 个)")
        log_detail(f"📊 [策略-Hot] PE_Hot 命中: {len(pe_hot_list)} 个")
        log_detail("="*60 + "\n")
        return

    # 6. 写入 Panel
    log_detail(f"\n正在写入 Panel 文件...")
    update_panel_with_conflict_check(
        PANEL_JSON_FILE,
        filtered_pe_volume, pe_volume_notes,
        filtered_pe_volume_up, pe_volume_up_notes,
        filtered_pe_volume_high, pe_vol_high_notes,
        pe_hot_list, pe_hot_notes,
        log_detail
    )

    # 7. 写入 History ([修复] 使用实际交易日作为 key)
    log_detail(f"\n正在更新 History 文件 (日期: {history_date_str})...")
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume", sorted(pe_volume_notes.values()), log_detail, history_date_str)
    if ENABLE_UP:
        update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume_up", sorted(pe_volume_up_notes.values()), log_detail, history_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Volume_high", sorted(pe_vol_high_notes.values()), log_detail, history_date_str)
    update_earning_history_json(EARNING_HISTORY_JSON_FILE, "PE_Hot", sorted(pe_hot_notes.values()), log_detail, history_date_str)

    log_detail("程序运行结束。")

def main():
    if SYMBOL_TO_TRACE:
        print(f"追踪模式已启用，目标: {SYMBOL_TO_TRACE}。日志仅输出到控制台。")
    else:
        print("追踪模式未启用。日志仅输出到控制台。")
        
    def log_detail_console(message):
        print(message)
        
    run_pe_volume_logic(log_detail_console)

if __name__ == '__main__':
    SYMBOL_TO_TRACE, TARGET_DATE = resolve_run_mode(SYMBOL_TO_TRACE, TARGET_DATE)
    main()