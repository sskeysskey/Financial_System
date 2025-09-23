import json
import sqlite3

# 定义tag黑名单
BLACKLIST_TAGS = ["黄金", "矿产", "建筑材料", "白银", "住房抵押贷款", "抵押贷款"]

# 读取JSON文件
with open('/Users/yanzhang/Coding/Financial_System/Modules/10Y_newhigh.json', 'r') as f:
    price_data = json.load(f)

# 读取description文件
with open('/Users/yanzhang/Coding/Financial_System/Modules/description.json', 'r') as f:
    desc_data = json.load(f)

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

# 连接数据库
conn = sqlite3.connect('/Users/yanzhang/Coding/Database/Finance.db')
cursor = conn.cursor()

# 对JSON中的每个symbol进行检查
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
        tags_str = ", ".join(symbol_info['tags']) if symbol_info['tags'] else "无标签"
        print(f"{symbol}: {tags_str}")

# 关闭数据库连接
conn.close()