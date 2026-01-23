import json
import sqlite3
import re
import logging
from wcwidth import wcswidth
from collections import defaultdict
from datetime import datetime, timedelta
import os

# ==========================================
# 1. 配置文件和路径管理 (已优化)
# ==========================================

# 算法参数配置
CONFIG = {
    "MIN_PRICE_CHANGE_THRESHOLD": 27,      # 财报后涨幅阈值
    "CONDITIONAL_THRESHOLD": 16.9,           # 【新增】特定条件下（如前次财报更高）的涨幅阈值
    "M_TOP_HEIGHT_TOLERANCE": 0.038,       # 双峰高度差容忍度 (3.8%)
    "M_TOP_NECK_DEPTH": 0.025,             # 颈线深度 (2.5%)
    "M_TOP_MIN_DAYS_GAP": 3,               # 双峰之间的最小间隔天数
    "M_TOP_NOISE_TOLERANCE": 0.01          # 噪音容忍度
}

# 动态路径生成
BASE_PATH = os.path.expanduser('~')

# 定义基础目录
CODING_DIR = os.path.join(BASE_PATH, 'Coding')
MODULES_DIR = os.path.join(CODING_DIR, 'Financial_System', 'Modules')
NEWS_DIR = os.path.join(CODING_DIR, 'News')
DB_DIR = os.path.join(CODING_DIR, 'Database')
DOWNLOADS_DIR = os.path.join(BASE_PATH, 'Downloads')

# 定义文件具体路径
DESC_FILE = os.path.join(MODULES_DIR, 'description.json')
SECTORS_FILE = os.path.join(MODULES_DIR, 'Sectors_All.json')
PANEL_FILE = os.path.join(MODULES_DIR, 'Sectors_panel.json')
EARNING_HISTORY_FILE = os.path.join(MODULES_DIR, 'Earning_History.json')
COMPARE_FILE = os.path.join(NEWS_DIR, 'backup', 'Compare_All.txt')
OUTPUT_FILE = os.path.join(NEWS_DIR, 'OverBuy.txt')
DB_FILE = os.path.join(DB_DIR, 'Finance.db')
DEBUG_LOG_FILE = os.path.join(DOWNLOADS_DIR, 'OverBuy_debug.log')

# ==========================================
# 2. 日志配置
# ==========================================
LOG_ENABLED = False  # True 或 False

logger = logging.getLogger(__name__)

# 1. 定义基础的 Handlers 列表，默认始终包含终端输出 (StreamHandler)
handlers_list = [logging.StreamHandler()]

# 2. 只有当 LOG_ENABLED 为 True 时，才添加文件输出 (FileHandler)
if LOG_ENABLED:
    os.makedirs(os.path.dirname(DEBUG_LOG_FILE), exist_ok=True)
    handlers_list.append(logging.FileHandler(DEBUG_LOG_FILE, encoding='utf-8'))

# 3. 统一配置 logging
# force=True 确保覆盖可能存在的旧配置，Python 3.8+ 支持
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=handlers_list,
    force=True 
)

# 确保 logger 处于开启状态
logger.disabled = False

# ==========================================
# 3. 标签过滤配置
# ==========================================
BLACKLIST_TAGS = [
    "赋能半导体", "黄金", "白银", "贵金属", "卫星",
    "国防", "军工", "生物制药", "铝", "铜", "仿制药", "卡车运输"
    ]

# 【修改点 1】定义tag白名单
# 如果这里填入了内容（例如 ["SaaS", "半导体"]），程序将只筛选包含这些tag的股票，且无视黑名单。
# 如果这里为空 []，程序将执行原有的黑名单过滤逻辑。
WHITELIST_TAGS = [] 

# ==========================================
# 4. 数据加载函数与预处理
# ==========================================

# 读取description文件
with open(DESC_FILE, 'r') as f:
    desc_data = json.load(f)
    logger.info('Loaded DESC_FILE')

# 读取sectors文件
with open(SECTORS_FILE, 'r') as f:
    sectors_data = json.load(f)
    logger.info(f'Loaded SECTORS_FILE with {len(sectors_data)} sectors')

# 读取 Compare_All.txt 文件并解析数据
compare_data = {}
try:
    with open(COMPARE_FILE, 'r') as f:
        for line in f:
            if line.strip():
                parts = line.strip().split(':')
                if len(parts) == 2:
                    symbol = parts[0].strip()
                    percent = parts[1].strip()
                    compare_data[symbol] = percent
    logger.info(f'Loaded COMPARE_FILE with {len(compare_data)} entries')
except FileNotFoundError:
    logger.warning(f"Compare file not found at {COMPARE_FILE}")

# 读取 panel.json
try:
    with open(PANEL_FILE, 'r') as f:
        panel_data = json.load(f)
    logger.info('Loaded PANEL_FILE')
except FileNotFoundError:
    panel_data = {}
    logger.warning("PANEL_FILE not found, initializing empty.")

# ==========================================
# 5. 辅助函数
# ==========================================

def update_earning_history_json_b(file_path, group_name, symbols_to_add):
    """
    同步 a.py 的逻辑：更新 Earning_History.json 文件。
    """
    if not symbols_to_add:
        return
    # 获取昨天日期
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    logger.info(f"--- 更新历史记录文件: {os.path.basename(file_path)} -> '{group_name}' ---")
    
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("信息: 历史记录文件不存在或格式错误，将创建新的。")
        data = {}

    # 确保顶层分组存在
    if group_name not in data:
        data[group_name] = {}

    # 获取该日期已有的 symbols
    existing_symbols = data[group_name].get(yesterday_str, [])
    
    # 合并、去重、排序
    combined_symbols = sorted(list(set(existing_symbols) | set(symbols_to_add)))
    data[group_name][yesterday_str] = combined_symbols
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"成功更新历史记录 '{group_name}'。日期: {yesterday_str}, 总计 {len(combined_symbols)} 个。")
    except Exception as e:
        logger.error(f"错误: 写入历史记录文件失败: {e}")


def pad_display(s: str, width: int, align: str = 'left') -> str:
    """按照真实列宽（CJK=2，ASCII=1）来给 s 补空格到 width 列."""
    cur = wcswidth(s)
    if cur >= width:
        return s
    pad = width - cur
    if align == 'left':
        return s + ' ' * pad
    else:
        return ' ' * pad + s

# 创建一个函数来获取symbol所属的sector
def get_symbol_sector(symbol):
    for sector, symbols in sectors_data.items():
        if symbol in symbols:
            return sector
    return "Unknown"

# 创建一个函数来检查symbol的tags并返回tags
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

_percent_pattern = re.compile(r'([-+]?\d+(?:\.\d+)?)%')
def parse_compare_percent(compare_str: str, symbol: str):
    if not compare_str:
        return None
    m = _percent_pattern.search(compare_str)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None

# ==========================================
# 6. 核心策略函数
# ==========================================

def get_price_peak_date(cursor, symbol, sector):
    """
    检查最近一个月内的最高价是否出现在最新交易日的前一个交易日。
    (单峰判断逻辑)
    """
    try:
        # 1. 获取最新交易日
        cursor.execute(f"""
            SELECT date, price 
            FROM {sector}
            WHERE name = ? 
            ORDER BY date DESC 
            LIMIT 1
        """, (symbol,))
        latest_result = cursor.fetchone()
        if not latest_result: return False
    
        latest_date_str, latest_price = latest_result[0], latest_result[1]

        # 2. 查询上一个实际的交易日
        cursor.execute(f"""
            SELECT date
            FROM {sector}
            WHERE name = ? AND date < ?
            ORDER BY date DESC
            LIMIT 1
        """, (symbol, latest_date_str))
        previous_trading_day_result = cursor.fetchone()
        if not previous_trading_day_result: return False
        
        previous_trading_day_str = previous_trading_day_result[0]

        # 3. 获取最近一个月的价格窗口
        latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d')
        one_month_ago = latest_date - timedelta(days=30)
        
        cursor.execute(f"""
            SELECT date, price 
            FROM {sector}
            WHERE name = ? 
            AND date >= ? 
            AND date <= ?
            ORDER BY price DESC, date DESC
        """, (symbol, one_month_ago.strftime('%Y-%m-%d'), latest_date.strftime('%Y-%m-%d')))
        prices = cursor.fetchall()
        if not prices: return False
        
        peak_date_str = prices[0][0]
        return peak_date_str == previous_trading_day_str
    except Exception as e:
        logger.error(f'[{symbol}] get_price_peak_date error: {e}')
        return False

def check_double_top(cursor, symbol, sector):
    """
    检查是否形成 M 形态（双峰）。
    借鉴了 Script A (W底) 的严谨逻辑：
    1. 严格的高度差 (CONFIG控制)
    2. 颈线深度 (CONFIG控制)
    3. 最小间隔 (CONFIG控制)
    4. 【新增】区间绝对高点检查 (防止中间有更高峰)
    """
    try:
        # 获取配置 (假设你已经添加了 CONFIG 字典)
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
        
        if len(rows) < 15: return False # 数据太少
        
        rows = rows[::-1] # 转正序
        prices = [float(r[1]) for r in rows]
        dates = [r[0] for r in rows]
        
        # 锁定 P2 (右峰) 必须是昨天 (index -2)
        curr_price = prices[-1]      # 今天
        p2 = prices[-2]              # 昨天 (潜在 P2)
        prev2_price = prices[-3]     # 前天
        
        # 昨天必须是局部高点
        if not (p2 > prev2_price and p2 > curr_price):
            return False
            
        idx2 = len(prices) - 2
        
        # 向前寻找 P1 (左峰)
        # start_search_index 确保了最小间隔
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

            # C. 区间极值检查 (核心移植逻辑)
            # 确保 P1 和 P2 是这段时间内的天花板
            period_prices = prices[idx1 : idx2 + 1]
            period_high = max(period_prices)
            peak_max = max(p1, p2)
            
            # 允许 0.1% 的误差
            if period_high > peak_max * 1.001:
                # logger.debug(f"[{symbol}] 失败: 区间内存在更高价 {period_high} > Peak {peak_max}")
                continue

            # D. 颈线深度检查 (中间必须跌得够深)
            valley_prices = prices[idx1+1 : idx2]
            if not valley_prices: continue
            
            min_valley = min(valley_prices)
            avg_peak = (p1 + p2) / 2
            
            # ---------------------------------------------------------
            # 【修改点 2】增加颈线深度 (Valley Depth) 检查
            # M头中间必须有一个明显的 "V" 字下跌。
            # 如果中间只跌了 0.5% (如 PSLV 12.15-12.17 的情况)，那不是M头。
            # 这里要求中间至少回撤 2.5%
            # ---------------------------------------------------------
            valley_depth = (avg_peak - min_valley) / avg_peak
            if valley_depth < min_depth:
                continue
                
            # E. 颈线不能破位太深 (可选，防止变成 huge V shape)
            # 脚本 A 中防止了 min_trough 过低，这里 M 头通常不用太担心跌太深，
            # 因为跌得深代表 M 头确立的概率更大，但如果跌破了启动点可能就不是顶部构造了。
            # 暂时不加，保持策略B的原意。

            # 通过所有检查
            logger.info(f"[{symbol}] M-Top Confirmed: "
                        f"P1@{p1:.2f}({dates[idx1]}), "
                        f"P2@{p2:.2f}({dates[idx2]}), "
                        f"Diff:{diff_pct*100:.2f}%, Depth:{valley_depth*100:.2f}%")
            found_pattern = True
            break 
            
        return found_pattern

    except Exception as e:
        logger.error(f'[{symbol}] check_double_top error: {e}')
        return False

# ==========================================
# 7. 主执行逻辑
# ==========================================

# 1. 初始化 Short 和 Short_backup
panel_data['Short'] = {}
short_group = panel_data['Short']
panel_data['Short_backup'] = {}
short_backup_group = panel_data['Short_backup']

# 2. 初始化 Short_W 和 Short_W_backup
panel_data['Short_W'] = {}
short_w_group = panel_data['Short_W']
panel_data['Short_W_backup'] = {}
short_w_backup_group = panel_data['Short_W_backup']

# 连接数据库
conn = sqlite3.connect(DB_FILE, timeout=60.0)
cursor = conn.cursor()

# 创建一个字典来存储按sector分组的输出内容
sector_outputs = defaultdict(list)

# --- 【修改开始】更改 symbols 来源 ---

# 定义你需要提取的目标板块
TARGET_SECTORS = [
    'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Technology', 'Energy', 
    'Industrials', 'Consumer_Defensive', 'Communication_Services', 
    'Financial_Services', 'Healthcare', 'Utilities'
]

symbols = []
# 遍历目标板块，从 sectors_data 中收集所有 symbol
for sec_name in TARGET_SECTORS:
    # sectors_data 在第4部分已经加载，直接使用
    if sec_name in sectors_data:
        # 提取该板块下的所有 symbol 并加入列表
        sec_symbols = sectors_data[sec_name]
        symbols.extend(sec_symbols)
    else:
        logger.warning(f"Sector '{sec_name}' not found in SECTORS_FILE.")

# 去重 (防止同一个 symbol 出现在不同板块导致的重复计算)
symbols = list(set(symbols))

# --- 【修改结束】 ---

logger.info(f'Start processing {len(symbols)} symbols from Sectors_All.json')

final_short_symbols = []
final_short_w_symbols = []

for symbol in symbols:
    try:
        symbol_info = get_symbol_info(symbol)
        sector = get_symbol_sector(symbol)
        tags_str = ", ".join(symbol_info['tags']) if symbol_info['tags'] else "无标签"
        
        # 白名单/黑名单 逻辑
        if len(WHITELIST_TAGS) > 0:
            # 如果白名单有内容，只检查白名单 (忽略黑名单)
            has_whitelist_tag = any(tag in WHITELIST_TAGS for tag in symbol_info['tags'])
            if not has_whitelist_tag:
                logger.info(f'[{symbol}] Skip: Not in whitelist tags')
                continue
        else:
            # 如果白名单为空，执行原有的黑名单逻辑
            if symbol_info['has_blacklist']:
                logger.info(f'[{symbol}] Skip due to blacklist tag')
                continue
        
        # --- 修改部分开始：动态确定涨幅阈值 ---
        # 1. 查询最近 2 次财报日期 (只取日期)
        cursor.execute("SELECT date FROM Earning WHERE name = ? ORDER BY date DESC LIMIT 2", (symbol,))
        earning_rows = cursor.fetchall()
        if not earning_rows:
            continue

        # 获取最新一次财报日期
        earning_date = earning_rows[0][0]
        
        # --- 核心修复：从板块表(Sector)获取真实收盘价，而不是依赖 Earning 表 ---
        cursor.execute(f"SELECT price FROM {sector} WHERE name = ? AND date = ?", (symbol, earning_date))
        earning_res = cursor.fetchone()
        
        # 如果板块数据里找不到这天（比如停牌或数据缺失），跳过
        if not earning_res:
            logger.warning(f"[{symbol}] Missing price in sector table for earning date: {earning_date}")
            continue
            
        earning_price = float(earning_res[0]) # 这是最新的财报日价格
        if earning_price == 0:
            continue

        # 确定动态阈值：默认值
        current_threshold = CONFIG["MIN_PRICE_CHANGE_THRESHOLD"]

        # 如果有两次财报数据，计算前一次的真实价格并比较
        if len(earning_rows) == 2:
            prev_earning_date = earning_rows[1][0]
            
            # 去板块表查上一次财报日的收盘价
            cursor.execute(f"SELECT price FROM {sector} WHERE name = ? AND date = ?", (symbol, prev_earning_date))
            prev_res = cursor.fetchone()
            
            if prev_res:
                prev_earning_price = float(prev_res[0])
                
                # 只有当：上一次真实收盘价 > 这一次真实收盘价，才降低阈值
                if prev_earning_price > earning_price:
                    current_threshold = CONFIG["CONDITIONAL_THRESHOLD"]

        # 获取当前最新价格 (用于计算涨幅)
        cursor.execute(f"SELECT price FROM {sector} WHERE name = ? ORDER BY date DESC LIMIT 1", (symbol,))
        latest_res = cursor.fetchone()
        if not latest_res:
            continue
        latest_price = float(latest_res[0])

        # 计算涨幅
        price_change = (latest_price - earning_price) / earning_price * 100
        
        # 记录日志方便调试
        # logger.info(f'[{symbol}] Date:{earning_date}, Price:{earning_price:.2f} | Latest:{latest_price:.2f} | Change:{price_change:.2f}% | Threshold:{current_threshold}%')

        # 过滤涨幅
        if price_change < current_threshold:
            continue
            
        compare_str = compare_data.get(symbol, '')
        
        # 写入 txt 候选
        sector_disp = pad_display(sector, 20, 'left')
        symbol_disp = pad_display(symbol, 5, 'left')
        output_line = {
            'text': f"{sector_disp} {symbol_disp} {price_change:.2f}% {compare_str}: {tags_str}",
            'change_percent': price_change
        }
        sector_outputs[sector_disp].append(output_line)
        logger.info(f'[{symbol}] Added to txt candidates')

        # -----------------------------------------------------------------------------
        # 分组逻辑：同步写入 backup 分组
        # -----------------------------------------------------------------------------
        
        # 1. 检查 M 形态 (双峰) -> 对应 Short_W
        is_double_top = check_double_top(cursor, symbol, sector)
        
        # 2. 检查 单日新高转折 -> 对应 Short
        is_single_peak = get_price_peak_date(cursor, symbol, sector)

        # 优先判断 M 形态
        if is_double_top:
            if symbol not in short_w_group:
                short_w_group[symbol] = ""
                # --- 修改点：同步写入 backup ---
                short_w_backup_group[symbol] = "" 
                final_short_w_symbols.append(symbol)
                logger.info(f'[{symbol}] Added to Short_W and Short_W_backup')
        
        # 如果不是 M 形态，再看是否是单日新高 (Fallback)
        elif is_single_peak:
            if symbol not in short_group:
                short_group[symbol] = ""
                # --- 修改点：同步写入 backup ---
                short_backup_group[symbol] = ""
                final_short_symbols.append(symbol)
                logger.info(f'[{symbol}] Added to Short and Short_backup')

    except Exception as e:
        logger.error(f'[{symbol}] Unexpected error: {e}')
        continue

# 关闭数据库连接
conn.close()
logger.info('DB connection closed')

# 写出 txt
with open(OUTPUT_FILE, 'w', encoding='utf-8') as output_file:
    for sector in sorted(sector_outputs.keys()):
        sorted_outputs = sorted(sector_outputs[sector], key=lambda x: x['change_percent'], reverse=True)
        for output in sorted_outputs:
            output_file.write(output['text'] + '\n')
    logger.info(f'Wrote txt output to {OUTPUT_FILE}')

# --- 新增：同步写入 Earning_History.json ---
if final_short_symbols:
    update_earning_history_json_b(EARNING_HISTORY_FILE, "Short", final_short_symbols)
if final_short_w_symbols:
    update_earning_history_json_b(EARNING_HISTORY_FILE, "Short_W", final_short_w_symbols)

# 原有的写回 panel JSON 代码
with open(PANEL_FILE, 'w', encoding='utf-8') as f:
    json.dump(panel_data, f, ensure_ascii=False, indent=4)
    logger.info(f'Updated panel file {PANEL_FILE}')