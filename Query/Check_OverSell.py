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
BLACKLIST_TAGS = ["联合医疗","黄金","金矿"]

# 读取JSON文件
with open(PRICE_FILE, 'r') as f:
    price_data = json.load(f)
logger.info(f'Loaded PRICE_FILE with {len(price_data)} symbols')

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
    此版本通过数据库查询来确定前一个交易日，以正确处理周末和节假日。
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
        logger.error(f'[{symbol}] get_price_peak_date: failed to query latest from table {sector}: {e}')
        logger.debug(traceback.format_exc())
        return False

    if not latest_result:
        logger.warning(f'[{symbol}] get_price_peak_date: no latest record found in {sector}')
        return False

    latest_date_str, latest_price = latest_result[0], latest_result[1]
    try:
        latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d')
    except Exception as e:
        logger.error(f'[{symbol}] get_price_peak_date: invalid latest date "{latest_date_str}": {e}')
        return False

    # 2. 【核心修改】查询上一个实际的交易日，而不是通过日期计算
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
        logger.error(f'[{symbol}] get_price_peak_date: failed to query previous trading day from table {sector}: {e}')
        logger.debug(traceback.format_exc())
        return False

    if not previous_trading_day_result:
        logger.warning(f'[{symbol}] get_price_peak_date: no trading day found before {latest_date_str}')
        return False
    
    previous_trading_day_str = previous_trading_day_result[0]

    # 3. 获取最近一个月的价格窗口，找到期间的最高价及其日期
    one_month_ago = latest_date - timedelta(days=30)
    try:
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
        logger.error(f'[{symbol}] get_price_peak_date: failed to query 1M window from {sector}: {e}')
        logger.debug(traceback.format_exc())
        return False

    if not prices:
        logger.warning(f'[{symbol}] get_price_peak_date: no price rows in last 30d window')
        return False

    peak_date_str, peak_price = prices[0][0], prices[0][1]

    # 4. 【核心修改】比较峰值日期是否等于我们查询到的上一个交易日
    ok = peak_date_str == previous_trading_day_str

    # 5. 【核心修改】更新日志，使其反映新的逻辑
    logger.info(
        f'[{symbol}] Peak check: latest_date={latest_date_str}, latest_price={latest_price}; '
        f'window>={one_month_ago.strftime("%Y-%m-%d")} <= {latest_date_str}; '
        f'peak_date={peak_date_str}, peak_price={peak_price}; '
        f'expected_peak_date (previous trading day)={previous_trading_day_str}; result={ok}'
    )
    return ok

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
        val = float(m.group(1))
        logger.info(f'[{symbol}] Compare parse: "{compare_str}" -> {val}%')
        return val
    except ValueError:
        logger.info(f'[{symbol}] Compare parse: failed to parse "{compare_str}"')
        return None

# 准备 Short 分组容器，确保结构存在且为 dict
short_group = panel_data.get('Short')
if not isinstance(short_group, dict):
    short_group = {}
panel_data['Short'] = short_group

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
        logger.info(f'[{symbol}] Start: sector="{sector}", tags="{tags_str}", blacklist={symbol_info["has_blacklist"]}')

        if symbol_info['has_blacklist']:
            logger.info(f'[{symbol}] Skip due to blacklist tag')
            continue

        # 查询最新财报涨跌幅记录是否为负（你的原逻辑）
        cursor.execute("""
            SELECT price 
            FROM Earning 
            WHERE name = ? 
            ORDER BY date DESC 
            LIMIT 1
        """, (symbol,))
        earning_price_row = cursor.fetchone()
        if earning_price_row is None or earning_price_row[0] is None:
            logger.info(f'[{symbol}] Skip: no latest Earning record')
            continue

        earning_last_change = float(earning_price_row[0])
        logger.info(f'[{symbol}] Latest Earning change record price={earning_last_change}')

        if not (earning_last_change < 0):
            logger.info(f'[{symbol}] Skip: latest Earning change not negative')
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

        # 过滤小于30%
        if price_change is None or abs(price_change) < 30:
            logger.info(f'[{symbol}] Skip: abs(price_change) < 30 ({price_change})')
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

        # Short 分组逻辑：compare < 0 且 peak 在最新交易日前一天
        if cmp_pct is None:
            logger.info(f'[{symbol}] Not added to Short: compare percent is None (raw="{compare_str}")')
            continue
        if cmp_pct >= 0:
            logger.info(f'[{symbol}] Not added to Short: compare percent >= 0 ({cmp_pct})')
            continue

        # 检查峰值日期为最新交易日前一天
        if get_price_peak_date(cursor, symbol, sector):
            if symbol not in short_group:
                short_group[symbol] = ""
                logger.info(f'[{symbol}] Added to Short group')
            else:
                logger.info(f'[{symbol}] Already in Short group (no change)')
        else:
            logger.info(f'[{symbol}] Not added to Short: peak check failed')

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