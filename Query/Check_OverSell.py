import json
import sqlite3
import re
import logging
from wcwidth import wcswidth
from collections import defaultdict
from datetime import datetime, timedelta
import os
import traceback

# 文件路径
PRICE_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/10Y_newhigh.json'
DESC_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
SECTORS_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
COMPARE_FILE = '/Users/yanzhang/Coding/News/backup/Compare_All.txt'
DB_FILE = '/Users/yanzhang/Coding/Database/Finance.db'
OUTPUT_FILE = '/Users/yanzhang/Coding/News/OverSell.txt'
PANEL_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'
DEBUG_LOG_FILE = '/Users/yanzhang/Downloads/OverSell_debug.log'

LOG_ENABLED = False  # True 或 False

logger = logging.getLogger(__name__)

if LOG_ENABLED:
    os.makedirs(os.path.dirname(DEBUG_LOG_FILE), exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(DEBUG_LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
else:
    logging.basicConfig(handlers=[])
    logging.getLogger().handlers.clear()
    logging.getLogger().setLevel(logging.CRITICAL + 1)
    logger.disabled = True

# 定义tag黑名单
# BLACKLIST_TAGS = ["联合医疗","黄金","金矿","白银","光纤","赋能半导体","赋能芯片制造","数据中心","贵金属"]
BLACKLIST_TAGS = []

# 【修改点 1】定义tag白名单
# 如果这里填入了内容（例如 ["SaaS", "半导体"]），程序将只筛选包含这些tag的股票，且无视黑名单。
# 如果这里为空 []，程序将执行原有的黑名单过滤逻辑。
WHITELIST_TAGS = [] 


# 读取JSON文件
with open(PRICE_FILE, 'r') as f:
    # 1. 先将整个新的JSON结构加载到一个临时变量中
    raw_price_data = json.load(f)

# 2. 从新的结构中提取我们需要的股票字典
#    使用 .get() 方法以防止 'stocks' 键不存在时报错
stocks_list = raw_price_data.get('stocks', [])

# 3. 检查列表是否非空，然后获取第一个元素
if stocks_list and isinstance(stocks_list, list) and len(stocks_list) > 0:
    price_data = stocks_list[0]
else:
    # 如果结构不符合预期，给 price_data 一个空字典，以防后续代码出错
    price_data = {}
    logger.warning(f"PRICE_FILE ({PRICE_FILE}) did not contain the expected 'stocks' list or the list was empty.")

logger.info(f'Loaded PRICE_FILE with {len(price_data)} symbols from the "stocks" key')


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
with open(COMPARE_FILE, 'r') as f:
    for line in f:
        if line.strip():
            parts = line.strip().split(':')
            if len(parts) == 2:
                symbol = parts[0].strip()
                percent = parts[1].strip()
                compare_data[symbol] = percent
logger.info(f'Loaded COMPARE_FILE with {len(compare_data)} entries')

# 读取并载入 panel.json
with open(PANEL_FILE, 'r') as f:
    panel_data = json.load(f)
logger.info('Loaded PANEL_FILE')

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
    except Exception as e:
        logger.error(f'[{symbol}] get_price_peak_date: failed to query latest: {e}')
        return False

    if not latest_result:
        return False

    latest_date_str, latest_price = latest_result[0], latest_result[1]
    
    # 2. 查询上一个实际的交易日，而不是通过日期计算
    try:
        cursor.execute(f"""
            SELECT date
            FROM {sector}
            WHERE name = ? AND date < ?
            ORDER BY date DESC
            LIMIT 1
        """, (symbol, latest_date_str))
        previous_trading_day_result = cursor.fetchone()
    except Exception as e:
        return False

    if not previous_trading_day_result:
        return False
    
    previous_trading_day_str = previous_trading_day_result[0]

    # 3. 获取最近一个月的价格窗口，找到期间的最高价及其日期
    try:
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
    except Exception as e:
        return False

    if not prices:
        return False

    peak_date_str = prices[0][0]
    return peak_date_str == previous_trading_day_str

# 【新增功能】检查是否为 M 形态（双峰）
def check_double_top(cursor, symbol, sector):
    """
    检查是否【刚刚】形成了双峰（M形态）。
    时效性约束：第二个高峰必须出现在【上一个交易日】。
    如果今天是12.12，只有当12.11是高峰时才触发。如果是12.13，则不再触发。
    """
    try:
        # 1. 获取过去60个交易日的数据 (按日期倒序取，然后反转为正序)
        cursor.execute(f"""
            SELECT date, price 
            FROM {sector}
            WHERE name = ? 
            ORDER BY date DESC 
            LIMIT 60
        """, (symbol,))
        rows = cursor.fetchall()
        
        # 数据太少无法判断
        if len(rows) < 10: 
            return False
            
        # 转为正序：index 0 是最旧的，index -1 是最新的（今天），index -2 是上一个交易日
        rows = rows[::-1]
        prices = [float(r[1]) for r in rows]
        dates = [r[0] for r in rows]

        # -------------------------------------------------------------------------
        # 【核心修改】锁定右峰 (Peak 2) 必须是 "昨天" (index -2)
        # -------------------------------------------------------------------------
        curr_price = prices[-1]      # 今天 (12.12)
        prev_price = prices[-2]      # 昨天 (12.11) - 候选 Peak 2
        prev2_price = prices[-3]     # 前天 (12.10)

        # 判定 A: 昨天必须是局部高点 (比前天高，且比今天高)
        # 如果今天还在涨 (curr > prev)，说明高点还没确定，不是M头右侧，排除
        if not (prev_price > prev2_price and prev_price > curr_price):
            return False

        # 此时，我们锁定了 p2 就是 prices[-2]
        idx2 = len(prices) - 2
        p2 = prev_price
        
        # -------------------------------------------------------------------------
        # 寻找左峰 (Peak 1)
        # -------------------------------------------------------------------------
        # 我们从昨天往前找，至少隔 3 天 (根据之前的优化)，搜索范围直到开头
        # range参数: start=idx2-3, stop=0, step=-1
        
        found_pattern = False
        
        for i in range(idx2 - 3, 0, -1):
            p1 = prices[i]
            idx1 = i
            
            # 1. 判断 p1 是否是局部高点 (比左右都高)
            if not (p1 > prices[i-1] and p1 > prices[i+1]):
                continue

            # 2. 判断高度差 (Peak 1 和 Peak 2 差距不能太大)
            # ABVX 案例: 128.23 vs 133.09，差距约 3.7%。
            # 这里的阈值设为 5% (0.05) 以兼容 ABVX
            diff_pct = abs(p1 - p2) / max(p1, p2)
            if diff_pct > 0.05:
                continue
                
            # 3. 判断中间是否有低谷 (颈线)
            # 获取两个峰值中间的数据
            valley_prices = prices[idx1+1 : idx2]
            if not valley_prices: continue
            
            min_valley = min(valley_prices)
            avg_peak = (p1 + p2) / 2
            
            # 4. 颈线深度判定
            # ABVX 案例: Valley 110.64, Peaks ~130. 跌幅很大。
            # 只要跌破峰值均值的 2.5% (0.975) 就算有效回调
            if min_valley > avg_peak * 0.975:
                continue
            
            # 如果所有条件满足，说明找到了对应的左峰
            # 且因为 p2 被强制锁定为 "昨天"，所以这一定是【刚刚】形成的形态
            logger.info(f"[{symbol}] Immediate Double Top Detected: "
                        f"Peak1@{p1:.2f}({dates[idx1]}), "
                        f"Peak2@{p2:.2f}({dates[idx2]} - Yesterday), "
                        f"Valley@{min_valley:.2f}")
            found_pattern = True
            break # 找到最近的一个匹配即可
            
        return found_pattern
        
    except Exception as e:
        logger.error(f'[{symbol}] check_double_top error: {e}')
        return False

_percent_pattern = re.compile(r'([-+]?\d+(?:\.\d+)?)%')

def parse_compare_percent(compare_str: str, symbol: str):
    if not compare_str:
        logger.info(f'[{symbol}] Compare parse: empty string')
        return None
    m = _percent_pattern.search(compare_str)
    if not m:
        logger.info(f'[{symbol}] Compare parse: no percent found in "{compare_str}"')
        return None
    try:
        return float(m.group(1))
    except ValueError:
        logger.info(f'[{symbol}] Compare parse: failed to parse "{compare_str}"')
        return None

# -----------------------------------------------------------------------------
# 【修改点 4】 准备 Short 和 Short_Shift 分组容器
# -----------------------------------------------------------------------------
# 1. Short 分组
short_group = panel_data.get('Short')
if not isinstance(short_group, dict):
    short_group = {}
panel_data['Short'] = short_group

# 2. Short_Shift 分组
short_shift_group = panel_data.get('Short_Shift')
if not isinstance(short_shift_group, dict):
    short_shift_group = {}
panel_data['Short_Shift'] = short_shift_group

# 连接数据库
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# 创建一个字典来存储按sector分组的输出内容
sector_outputs = defaultdict(list)

symbols = list(price_data.keys())
logger.info(f'Start processing {len(symbols)} symbols')

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

        # 查询最新财报涨跌幅记录（不再根据正负进行过滤）
        cursor.execute("""
            SELECT price 
            FROM Earning 
            WHERE name = ? 
            ORDER BY date DESC 
            LIMIT 1
        """, (symbol,))
        earning_price_row = cursor.fetchone()
        if earning_price_row is None or earning_price_row[0] is None:
            continue

        # 计算财报日至最新收盘价变化百分比
        price_change = None
        try:
            price_change = None
            # 获取最新财报日期
            cursor.execute("""
                SELECT date, price 
                FROM Earning 
                WHERE name = ? 
                ORDER BY date DESC 
                LIMIT 1
            """, (symbol,))
            earning_result = cursor.fetchone()
            if not earning_result:
                logger.info(f'[{symbol}] Skip: Earning query returned empty')
                continue
            earning_date = earning_result[0]

            # 最新收盘价
            cursor.execute(f"""
                SELECT price 
                FROM {sector}
                WHERE name = ? 
                ORDER BY date DESC 
                LIMIT 1
            """, (symbol,))
            latest_price_result = cursor.fetchone()
            if not latest_price_result:
                logger.info(f'[{symbol}] Skip: no latest price in table {sector}')
                continue
            latest_price = float(latest_price_result[0])

            # 财报日收盘价
            cursor.execute(f"""
                SELECT price 
                FROM {sector}
                WHERE name = ? AND date = ?
            """, (symbol, earning_date))
            earning_price_result = cursor.fetchone()
            if not earning_price_result:
                logger.info(f'[{symbol}] Skip: no price on earning date {earning_date} in table {sector}')
                continue
            earning_price = float(earning_price_result[0])

            if earning_price == 0:
                logger.info(f'[{symbol}] Skip: earning day price is 0 (division by zero)')
                continue

            price_change = (latest_price - earning_price) / earning_price * 100
            logger.info(f'[{symbol}] Price change from earning_date={earning_date}: earning_price={earning_price}, latest_price={latest_price}, change={price_change:.2f}%')

        except Exception as e:
            logger.error(f'[{symbol}] Error computing price change: {e}')
            logger.debug(traceback.format_exc())
            continue

        # 【修改点 3】过滤小于30% (原先是 abs(price_change) < 30，现在改为 price_change < 30)
        # 这样只保留正向涨幅超过30%的，负数（如-35%）将被过滤
        if price_change is None or price_change < 30:
            logger.info(f'[{symbol}] Skip: price_change < 30 (actual: {price_change})')
            continue

        compare_str = compare_data.get(symbol, '')
        cmp_pct = parse_compare_percent(compare_str, symbol)

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
        # 【修改点 5】 分组逻辑重构：Short vs Short_Shift
        # -----------------------------------------------------------------------------
        
        # 1. 检查 M 形态 (双峰) -> 对应 Short_Shift
        is_double_top = check_double_top(cursor, symbol, sector)
        
        # 2. 检查 单日新高转折 -> 对应 Short
        is_single_peak = get_price_peak_date(cursor, symbol, sector)

        # 优先判断 M 形态
        if is_double_top:
            if symbol not in short_shift_group:
                short_shift_group[symbol] = ""
                logger.info(f'[{symbol}] Added to Short_Shift group (M-Pattern Detected)')
            else:
                logger.info(f'[{symbol}] Already in Short_Shift group')
        
        # 如果不是 M 形态，再看是否是单日新高 (Fallback)
        elif is_single_peak:
            if symbol not in short_group:
                short_group[symbol] = ""
                logger.info(f'[{symbol}] Added to Short group (Single Peak only)')
            else:
                logger.info(f'[{symbol}] Already in Short group')
        
        else:
            logger.info(f'[{symbol}] Not added to Short/Short_Shift')

    except Exception as e:
        logger.error(f'[{symbol}] Unexpected error: {e}')
        logger.debug(traceback.format_exc())
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

# 写回 panel JSON
with open(PANEL_FILE, 'w', encoding='utf-8') as f:
    json.dump(panel_data, f, ensure_ascii=False, indent=4)
logger.info(f'Updated panel file {PANEL_FILE}')