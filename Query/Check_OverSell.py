import json
import sqlite3
import re
from wcwidth import wcswidth
from collections import defaultdict

# 文件路径
PRICE_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/10Y_newhigh.json'
DESC_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
SECTORS_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
COMPARE_FILE = '/Users/yanzhang/Coding/News/backup/Compare_All.txt'
DB_FILE = '/Users/yanzhang/Coding/Database/Finance.db'
OUTPUT_FILE = '/Users/yanzhang/Coding/News/OverSold.txt'
PANEL_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'

# 定义tag黑名单
BLACKLIST_TAGS = []

# 读取JSON文件
with open(PRICE_FILE, 'r') as f:
    price_data = json.load(f)

# 读取description文件
with open(DESC_FILE, 'r') as f:
    desc_data = json.load(f)

# 读取sectors文件
with open(SECTORS_FILE, 'r') as f:
    sectors_data = json.load(f)

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

# 读取并载入 panel.json
with open(PANEL_FILE, 'r') as f:
    panel_data = json.load(f)

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
    return "Unknown"  # 如果没有找到对应的sector，返回"Unknown"

# 创建一个函数来检查symbol的tags并返回tags
def get_symbol_info(symbol):
    # 检查stocks列表
    for stock in desc_data.get('stocks', []):
        if stock['symbol'] == symbol:
            return {
                'has_blacklist': any(tag in BLACKLIST_TAGS for tag in stock.get('tag', [])),
                'tags': stock.get('tag', [])
            }
    
    # 检查etfs列表
    for etf in desc_data.get('etfs', []):
        if etf['symbol'] == symbol:
            return {
                'has_blacklist': any(tag in BLACKLIST_TAGS for tag in etf.get('tag', [])),
                'tags': etf.get('tag', [])
            }
    
    return {
        'has_blacklist': False,
        'tags': []
    }

def get_price_change_percent(cursor, symbol, sector):
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
        return None
    
    earning_date = earning_result[0]
    
    # 获取最新收盘价
    cursor.execute(f"""
        SELECT price 
        FROM {sector}
        WHERE name = ? 
        ORDER BY date DESC 
        LIMIT 1
    """, (symbol,))
    
    latest_price_result = cursor.fetchone()
    if not latest_price_result:
        return None
    
    latest_price = float(latest_price_result[0])
    
    # 获取财报日期的收盘价
    cursor.execute(f"""
        SELECT price 
        FROM {sector}
        WHERE name = ? AND date = ?
    """, (symbol, earning_date))
    
    earning_price_result = cursor.fetchone()
    if not earning_price_result:
        return None
    
    earning_price = float(earning_price_result[0])
    
    if earning_price == 0:
        return None
    
    # 计算价格变化百分比
    price_change_percent = (latest_price - earning_price) / earning_price * 100
    return price_change_percent

# 解析 compare_data 中的第一个百分比，返回 float 或 None
_percent_pattern = re.compile(r'([-+]?\d+(?:\.\d+)?)%')

def parse_compare_percent(compare_str: str):
    if not compare_str:
        return None
    m = _percent_pattern.search(compare_str)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None

# 准备 Short 分组容器，确保结构存在且为 dict
if 'Short' not in panel_data or not isinstance(panel_data['Short'], dict):
    panel_data['Short'] = {}
short_group = panel_data['Short']

# 连接数据库
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# 创建一个字典来存储按sector分组的输出内容
sector_outputs = defaultdict(list)

# 处理每个symbol
for symbol in price_data.keys():
    # 获取symbol信息
    symbol_info = get_symbol_info(symbol)
    
    # 如果有黑名单tag，跳过
    if symbol_info['has_blacklist']:
        continue
        
    # 查询该symbol最新的price
    cursor.execute("""
        SELECT price 
        FROM Earning 
        WHERE name = ? 
        ORDER BY date DESC 
        LIMIT 1
    """, (symbol,))
    
    result = cursor.fetchone()
    
    # 如果有结果且price为负数
    if result and result[0] is not None and float(result[0]) < 0:
        # 获取sector名称
        sector = get_symbol_sector(symbol)
        price_change = get_price_change_percent(cursor, symbol, sector)
        
        if price_change is not None:
            # 新增过滤逻辑：财报日至最新收盘价的百分比变化若小于 30%，则跳过
            if abs(price_change) < 30:
                continue

            tags_str = ", ".join(symbol_info['tags']) if symbol_info['tags'] else "无标签"
            # 获取compare数据
            compare_str = compare_data.get(symbol, '')

            # 解析 compare 的第一个百分比，如果为负数，则加入 Short 分组
            cmp_pct = parse_compare_percent(compare_str)
            if cmp_pct is not None and cmp_pct < 0:
                # 若 Short 分组不存在该 symbol，则加入，值设为 ""，保持你原来的结构
                if symbol not in short_group:
                    short_group[symbol] = ""

            sector_disp = pad_display(sector, 20, 'left')
            symbol_disp = pad_display(symbol, 5, 'left')

            output_line = {
                'text': f"{sector_disp} {symbol_disp} {price_change:.2f}% {compare_str}: {tags_str}",
                'change_percent': price_change
            }
            sector_outputs[sector_disp].append(output_line)

# 关闭数据库连接
conn.close()

# 打开输出文件，按sector排序写入内容
with open(OUTPUT_FILE, 'w') as output_file:
    # 按sector名称排序
    for sector in sorted(sector_outputs.keys()):
        # 按价格变化百分比排序（从大到小）
        sorted_outputs = sorted(sector_outputs[sector], 
                              key=lambda x: x['change_percent'], 
                              reverse=True)
        # 写入该sector的所有内容
        for output in sorted_outputs:
            output_file.write(output['text'] + '\n')

# 将更新后的 panel_data 写回 Sectors_panel.json（保持 UTF-8 编码和可读格式）
with open(PANEL_FILE, 'w', encoding='utf-8') as f:
    json.dump(panel_data, f, ensure_ascii=False, indent=4)