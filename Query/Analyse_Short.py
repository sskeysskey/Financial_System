import json
import sqlite3
import logging
import os
from wcwidth import wcswidth
from collections import defaultdict
from datetime import datetime, timedelta

# ==========================================
# 1. 配置文件和路径管理
# ==========================================

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# 算法参数配置
CONFIG = {
    # --- 基础策略：放量下跌 ---
    "LOOKBACK_MONTHS_LONG": 12,    # 策略A回溯期
    "RANK_THRESHOLD_LONG": 2,      # 策略A排名
    "LOOKBACK_MONTHS_SHORT": 6,    # 策略B回溯期
    "RANK_THRESHOLD_SHORT": 1,     # 策略B排名

    # --- 进阶策略：M头 (Short_W) 形态参数 ---
    "M_TOP_HEIGHT_TOLERANCE": 0.038,       # 双峰高度差容忍度 (3.8%)
    "M_TOP_NECK_DEPTH": 0.025,             # 颈线深度 (2.5%)
    "M_TOP_MIN_DAYS_GAP": 3,               # 双峰之间的最小间隔天数

    # --- 新增策略：砸顶参数 ---
    "PUMP_DUMP_THRESHOLD": 0.10,   # 最新收盘价比历史信号日收盘价高出多少 (0.10 = 10%)
}

# 动态路径生成
BASE_PATH = USER_HOME
CODING_DIR = BASE_CODING_DIR
MODULES_DIR = os.path.join(CODING_DIR, 'Financial_System', 'Modules')
NEWS_DIR = os.path.join(CODING_DIR, 'News')
DB_DIR = os.path.join(CODING_DIR, 'Database')
DOWNLOADS_DIR = os.path.join(BASE_PATH, 'Downloads')

# 定义文件具体路径
DESC_FILE = os.path.join(MODULES_DIR, 'description.json')
SECTORS_FILE = os.path.join(MODULES_DIR, 'Sectors_All.json')
PANEL_FILE = os.path.join(MODULES_DIR, 'Sectors_panel.json')
EARNING_HISTORY_FILE = os.path.join(MODULES_DIR, 'Earning_History.json')
OUTPUT_FILE = os.path.join(NEWS_DIR, 'OverBuy.txt')
DB_FILE = os.path.join(DB_DIR, 'Finance.db')
DEBUG_LOG_FILE = os.path.join(DOWNLOADS_DIR, 'OverBuy_debug.log')

# ==========================================
# 2. 日志配置
# ==========================================
LOG_ENABLED = False  # True 或 False

logger = logging.getLogger(__name__)
handlers_list = [logging.StreamHandler()]

if LOG_ENABLED:
    os.makedirs(os.path.dirname(DEBUG_LOG_FILE), exist_ok=True)
    handlers_list.append(logging.FileHandler(DEBUG_LOG_FILE, encoding='utf-8'))

logging.basicConfig(
    level=logging.INFO, # 调整为 INFO 减少刷屏
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=handlers_list,
    force=True 
)
logger.disabled = False

# ==========================================
# 3. 标签过滤配置
# ==========================================
BLACKLIST_TAGS = [
    "赋能半导体", "黄金", "白银", "贵金属", "卫星",
    "国防", "军工", "生物制药", "铝", "铜", "仿制药", "卡车运输"
]

WHITELIST_TAGS = [] 

# ==========================================
# 4. 数据加载
# ==========================================

# 读取description文件
try:
    with open(DESC_FILE, 'r', encoding='utf-8') as f:
        desc_data = json.load(f)
    logger.info('Loaded DESC_FILE')
except Exception as e:
    logger.error(f"Failed to load DESC_FILE: {e}")
    desc_data = {}

# 读取sectors文件
try:
    with open(SECTORS_FILE, 'r', encoding='utf-8') as f:
        sectors_data = json.load(f)
    logger.info(f'Loaded SECTORS_FILE with {len(sectors_data)} sectors')
except Exception as e:
    logger.error(f"Failed to load SECTORS_FILE: {e}")
    sectors_data = {}

# 读取 panel.json
try:
    with open(PANEL_FILE, 'r', encoding='utf-8') as f:
        panel_data = json.load(f)
    logger.info('Loaded PANEL_FILE')
except FileNotFoundError:
    panel_data = {}
    logger.warning("PANEL_FILE not found, initializing empty.")

# 读取 Earning_History.json (全局只读一次用于检索)
try:
    with open(EARNING_HISTORY_FILE, 'r', encoding='utf-8') as f:
        earning_history_data = json.load(f)
    logger.info('Loaded EARNING_HISTORY_FILE for global lookup')
except (FileNotFoundError, json.JSONDecodeError):
    earning_history_data = {}
    logger.warning("EARNING_HISTORY_FILE not found or empty, creating empty lookup dict.")

# ==========================================
# 5. 辅助函数
# ==========================================

def update_earning_history_json_b(file_path, group_name, symbols_to_add):
    """
    更新 Earning_History.json 文件。
    """
    if not symbols_to_add:
        return
    # 获取昨天日期作为记录日期
    record_date_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    logger.info(f"--- 更新历史记录文件: {os.path.basename(file_path)} -> '{group_name}' ---")
    
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    if group_name not in data:
        data[group_name] = {}

    existing_symbols = data[group_name].get(record_date_str, [])
    combined_symbols = sorted(list(set(existing_symbols) | set(symbols_to_add)))
    data[group_name][record_date_str] = combined_symbols
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"成功更新历史记录 '{group_name}'。日期: {record_date_str}, 总计 {len(combined_symbols)} 个。")
    except Exception as e:
        logger.error(f"错误: 写入历史记录文件失败: {e}")

def pad_display(s: str, width: int, align: str = 'left') -> str:
    cur = wcswidth(s)
    if cur >= width: return s
    pad = width - cur
    return s + ' ' * pad if align == 'left' else ' ' * pad + s

def get_symbol_sector(symbol):
    for sector, symbols in sectors_data.items():
        if symbol in symbols:
            return sector
    return "Unknown"

def get_symbol_info(symbol):
    # 检查stocks列表
    for stock in desc_data.get('stocks', []):
        if stock['symbol'] == symbol:
            tags = stock.get('tag', [])
            has_blacklist = any(tag in BLACKLIST_TAGS for tag in tags)
            return {'has_blacklist': has_blacklist, 'tags': tags}
            
    for etf in desc_data.get('etfs', []):
        if etf['symbol'] == symbol:
            tags = etf.get('tag', [])
            has_blacklist = any(tag in BLACKLIST_TAGS for tag in tags)
            return {'has_blacklist': has_blacklist, 'tags': tags}
            
    return {'has_blacklist': False, 'tags': []}

# ==========================================
# 6. 核心策略函数 (新)
# ==========================================

def check_turnover_rank(cursor, sector_name, symbol, latest_date_str, latest_turnover, lookback_months, rank_threshold):
    """
    检查 latest_turnover 是否是过去 lookback_months 个月内的前 rank_threshold 名。
    """
    try:
        dt = datetime.strptime(latest_date_str, "%Y-%m-%d")
        # 粗略计算 N 个月前的日期
        start_date = dt - timedelta(days=lookback_months * 30)
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
    
    # 判定逻辑：当前成交额是否在前 N 名中，或者大于等于第 N 名的值
    if latest_turnover in top_n_turnovers:
        return True
    elif len(top_n_turnovers) >= rank_threshold and latest_turnover >= top_n_turnovers[rank_threshold - 1]:
        return True
        
    return False

def check_double_top(cursor, symbol, sector):
    """
    检查是否形成 M 形态（双峰）。
    """
    try:
        price_tolerance = CONFIG.get("M_TOP_HEIGHT_TOLERANCE", 0.038)
        min_depth = CONFIG.get("M_TOP_NECK_DEPTH", 0.025)
        min_days_gap = CONFIG.get("M_TOP_MIN_DAYS_GAP", 3)

        cursor.execute(f"""
            SELECT date, price 
            FROM {sector}
            WHERE name = ? 
            ORDER BY date DESC 
            LIMIT 60
        """, (symbol,))
        rows = cursor.fetchall()
        
        if len(rows) < 15: return False
        
        rows = rows[::-1] # 转正序
        prices = [float(r[1]) for r in rows]
        dates = [r[0] for r in rows]
        
        # 锁定 P2 (右峰) 必须是昨天 (index -2)
        # 因为我们的基础条件是今天下跌(Today < Yesterday)，所以Yesterday天然是一个潜在的短期高点
        curr_price = prices[-1]      # 今天
        p2 = prices[-2]              # 昨天 (潜在 P2)
        prev2_price = prices[-3]     # 前天
        
        # 确认昨天是局部高点
        if not (p2 > prev2_price and p2 > curr_price):
            return False
            
        idx2 = len(prices) - 2
        
        # 向前寻找 P1 (左峰)
        start_search_index = idx2 - min_days_gap
        
        found_pattern = False
        
        for i in range(start_search_index, 0, -1):
            p1 = prices[i]
            idx1 = i
            
            # A. P1 必须是局部高点
            if not (p1 > prices[i-1] and p1 > prices[i+1]):
                continue
                
            # B. 高度对称性检查
            diff_pct = abs(p1 - p2) / max(p1, p2)
            if diff_pct > price_tolerance: 
                continue

            # C. 区间极值检查 (防止中间有更高峰)
            period_prices = prices[idx1 : idx2 + 1]
            period_high = max(period_prices)
            peak_max = max(p1, p2)
            
            if period_high > peak_max * 1.001:
                continue

            # D. 颈线深度检查 (中间必须跌得够深)
            valley_prices = prices[idx1+1 : idx2]
            if not valley_prices: continue
            
            min_valley = min(valley_prices)
            avg_peak = (p1 + p2) / 2
            
            valley_depth = (avg_peak - min_valley) / avg_peak
            if valley_depth < min_depth:
                continue

            # 通过所有检查
            found_pattern = True
            break 
            
        return found_pattern

    except Exception as e:
        logger.error(f'[{symbol}] check_double_top error: {e}')
        return False
    
def get_latest_earnings_date(cursor, symbol):
    """
    从数据库的 Earning 表中获取该 symbol 的最近财报日。
    如果没有找到相关记录，则默认回退指定的配置天数（默认90天）。
    """
    try:
        # 按日期降序排列，取最近的一次财报日期
        cursor.execute('SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 1', (symbol,))
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.error(f"[{symbol}] Error querying latest earnings date: {e}")
    
    # 如果找不到财报日或者表不存在/报错，默认回退配置的天数
    fallback_date = datetime.now() - timedelta(days=CONFIG.get("EARNINGS_LOOKBACK_DAYS", 90))
    return fallback_date.strftime('%Y-%m-%d')

def check_pump_dump_top(cursor, sector, symbol, latest_date_str, latest_price, earnings_date_str):
    """
    检索从最近财报日到最新日期之间，是否在 Short 或 Short_W 中出现过。
    如果出现过，查询当天的收盘价，并比对最新收盘价是否高出配置的阈值。
    """
    threshold = CONFIG.get("PUMP_DUMP_THRESHOLD", 0.10)
    hit_dates = []
    
    # 检索是否在指定时间段内出现过
    for group in ["Short", "Short_W"]:
        if group not in earning_history_data: continue
        
        for date_str, symbols_list in earning_history_data[group].items():
            if earnings_date_str <= date_str < latest_date_str:
                if symbol in symbols_list:
                    hit_dates.append(date_str)
                    
    if not hit_dates:
        return False, ""
        
    # 如果出现过，查询历史日期的收盘价
    for past_date in hit_dates:
        try:
            cursor.execute(f'SELECT price FROM "{sector}" WHERE name = ? AND date = ?', (symbol, past_date))
            row = cursor.fetchone()
            if row and row[0] is not None:
                past_price = float(row[0])
                # 计算价格涨幅
                if past_price > 0 and (latest_price - past_price) / past_price >= threshold:
                    return True, f"较{past_date}信号日大涨{((latest_price - past_price) / past_price)*100:.1f}%"
        except Exception as e:
            logger.error(f"[{symbol}] Error querying past price for {past_date}: {e}")
            continue
            
    return False, ""

# ==========================================
# 7. 主执行逻辑
# ==========================================

# 1. 初始化 Short 和 Short_backup (清空旧数据)
panel_data['Short'] = {}
short_group = panel_data['Short']
panel_data['Short_backup'] = {}
short_backup_group = panel_data['Short_backup']

# 2. 初始化 Short_W 和 Short_W_backup (恢复使用)
panel_data['Short_W'] = {}
short_w_group = panel_data['Short_W']
panel_data['Short_W_backup'] = {}
short_w_backup_group = panel_data['Short_W_backup']

# 连接数据库
conn = sqlite3.connect(DB_FILE, timeout=60.0)
cursor = conn.cursor()

# 结果收集
sector_outputs = defaultdict(list)
final_short_symbols = []
final_short_w_symbols = []

# 定义目标板块
TARGET_SECTORS = [
    'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Technology', 'Energy', 
    'Industrials', 'Consumer_Defensive', 'Communication_Services', 
    'Financial_Services', 'Healthcare', 'Utilities', "ETFs",
]

# 收集所有 Symbol
symbols = []
for sec_name in TARGET_SECTORS:
    if sec_name in sectors_data:
        symbols.extend(sectors_data[sec_name])
    else:
        logger.warning(f"Sector '{sec_name}' not found in SECTORS_FILE.")
symbols = list(set(symbols)) # 去重

logger.info(f'Start processing {len(symbols)} symbols...')

for symbol in symbols:
    try:
        # --- A. 基础信息与过滤 ---
        symbol_info = get_symbol_info(symbol)
        sector = get_symbol_sector(symbol)
        tags_str = ", ".join(symbol_info['tags']) if symbol_info['tags'] else "无标签"
        
        # 白名单/黑名单 逻辑
        if len(WHITELIST_TAGS) > 0:
            has_whitelist_tag = any(tag in WHITELIST_TAGS for tag in symbol_info['tags'])
            if not has_whitelist_tag: continue
        else:
            if symbol_info['has_blacklist']: continue
        
        # --- B. 获取最近2天交易数据 ---
        # 获取 T (今天) 和 T-1 (昨天)
        query = f'SELECT date, price, volume FROM "{sector}" WHERE name = ? ORDER BY date DESC LIMIT 2'
        cursor.execute(query, (symbol,))
        rows = cursor.fetchall()
        
        if len(rows) < 2:
            continue
            
        # rows[0] 是最新一天, rows[1] 是前一天
        date_curr, price_curr, vol_curr = rows[0]
        date_prev, price_prev, vol_prev = rows[1]
        
        if price_curr is None or price_prev is None or vol_curr is None:
            continue
            
                # --- 提前计算今日成交额 ---
        current_turnover = price_curr * vol_curr

        # --- D2. 提前进行进阶门槛：砸顶检查 (无需下跌即可触发) ---
        # 传入 cursor 去 Earning 表查询最近的财报日
        earnings_date_str = get_latest_earnings_date(cursor, symbol)
        
        is_pump_dump = False
        pd_reason = ""
        # 只有获取到了合理的财报日期，才去检查是否砸顶
        if earnings_date_str:
            is_pump_dump, pd_reason = check_pump_dump_top(
                cursor, sector, symbol, date_curr, price_curr, earnings_date_str
            )

        # --- C. 基础门槛 1: 必须下跌 (针对原策略的拦截) ---
        # 核心改动：如果【不是砸顶】，且【今天没有下跌（价格>=昨天）】，才会被 continue 拦截跳过。
        # 换言之，如果是砸顶，即使今天上涨也不会被跳过。
        if not is_pump_dump and price_curr >= price_prev:
            continue
            
        # --- D. 基础门槛 2: 成交额排名检查 (仅针对原策略) ---
        is_hit_base = False
        hit_reason = ""
        
        # 只有在今天确实下跌的情况下，才去跑原来非常耗时的量能排名 SQL 查询
        if price_curr < price_prev:
            # 检查 1: 过去一年 (12个月) 前 2 名
            if check_turnover_rank(cursor, sector, symbol, date_curr, current_turnover, 
                                   CONFIG["LOOKBACK_MONTHS_LONG"], CONFIG["RANK_THRESHOLD_LONG"]):
                is_hit_base = True
                hit_reason = f"1年内Top{CONFIG['RANK_THRESHOLD_LONG']}天量"
                
            # 检查 2: 若不满足，检查半年 (6个月) 前 1 名
            elif check_turnover_rank(cursor, sector, symbol, date_curr, current_turnover, 
                                     CONFIG["LOOKBACK_MONTHS_SHORT"], CONFIG["RANK_THRESHOLD_SHORT"]):
                is_hit_base = True
                hit_reason = f"半年内Top{CONFIG['RANK_THRESHOLD_SHORT']}天量"

        # 如果满足砸顶，强制纳入最终名单
        if is_pump_dump:
            is_hit_base = True 
            if hit_reason:
                hit_reason += f" & 砸顶({pd_reason})"
            else:
                hit_reason = f"砸顶({pd_reason})"

        # --- E. 分流逻辑 ---
        if is_hit_base:
            # 基础规则检查 W顶（如果只是触发砸顶，根据要求它直接进Short，我们依旧让普通量能触发去查W顶）
            is_double_top = False
            if not is_pump_dump: 
                is_double_top = check_double_top(cursor, symbol, sector)
            
            # 分流赋值
            if is_pump_dump:
                # 触发了砸顶，直接进 Short 并且 panel 值赋予 'XXX砸顶'
                panel_val = f"{symbol}砸顶"
                short_group[symbol] = panel_val
                short_backup_group[symbol] = panel_val
                final_short_symbols.append(symbol)
                
                group_tag = "[Short砸顶]"
                logger.info(f'[{symbol}] Hit Short(Pump Dump): {hit_reason}')
                
            elif is_double_top:
                # 没触发砸顶，但是触发了M头
                short_w_group[symbol] = ""
                short_w_backup_group[symbol] = ""
                final_short_w_symbols.append(symbol)
                
                group_tag = "[Short_W]"
                logger.info(f'[{symbol}] Hit Short_W: {hit_reason} + M-Top')
                
            else:
                # 符合基础规则 + 不符合 W 形态 -> Short
                short_group[symbol] = ""
                short_backup_group[symbol] = ""
                final_short_symbols.append(symbol)
                
                group_tag = "[Short]"
                logger.info(f'[{symbol}] Hit Short: {hit_reason}')

            # 准备 TXT 输出 (统一输出，带上标记)
            sector_disp = pad_display(sector, 20, 'left')
            symbol_disp = pad_display(symbol, 5, 'left')
            # 这里的 change_percent 仅用于排序，用今日跌幅代替
            pct_change = (price_curr - price_prev) / price_prev * 100
            
            output_line = {
                'text': f"{sector_disp} {symbol_disp} {pct_change:.2f}% {group_tag} {hit_reason}: {tags_str}",
                'change_percent': abs(current_turnover)
            }
            sector_outputs[sector_disp].append(output_line)

    except Exception as e:
        logger.error(f'[{symbol}] Error: {e}')
        continue

# 关闭数据库连接
conn.close()
logger.info('DB connection closed')

# 写出 txt (按成交额或跌幅排序，这里简单按添加顺序或板块)
with open(OUTPUT_FILE, 'w', encoding='utf-8') as output_file:
    output_file.write(f"OverBuy Scan Result (Down + High Turnover)\n")
    output_file.write(f"Date: {datetime.now().strftime('%Y-%m-%d')}\n")
    output_file.write("="*60 + "\n")
    for sector in sorted(sector_outputs.keys()):
        # 这里按成交额大小(change_percent存的是turnover)排序
        sorted_outputs = sorted(sector_outputs[sector], key=lambda x: x['change_percent'], reverse=True)
        for output in sorted_outputs:
            output_file.write(output['text'] + '\n')
    logger.info(f'Wrote txt output to {OUTPUT_FILE}')

# 同步写入 Earning_History.json
if final_short_symbols:
    update_earning_history_json_b(EARNING_HISTORY_FILE, "Short", final_short_symbols)
if final_short_w_symbols:
    update_earning_history_json_b(EARNING_HISTORY_FILE, "Short_W", final_short_w_symbols)

# 写回 panel JSON
with open(PANEL_FILE, 'w', encoding='utf-8') as f:
    json.dump(panel_data, f, ensure_ascii=False, indent=4)
    logger.info(f'Updated panel file {PANEL_FILE}')