import sqlite3
import json
import os
from datetime import datetime, timedelta

# 配置路径
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'
JSON_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'

# 允许的分组范围
ALLOWED_SECTORS = [
    "Communication_Services", "Consumer_Cyclical", 
    "Consumer_Defensive", "Financial_Services", 
    "Healthcare", "Industrials", "Real_Estate", "Technology", "Utilities"
]

def get_growth_stocks():
    if not os.path.exists(JSON_PATH):
        return json.dumps({"error": "配置文件不存在"})

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        sectors_data = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 当前日期和一年前的日期
    today = datetime(2026, 3, 19)
    one_year_ago = today - timedelta(days=365)
    
    today_str = today.strftime('%Y-%m-%d')
    one_year_ago_str = one_year_ago.strftime('%Y-%m-%d')
    
    final_symbols = []

    for sector, symbols in sectors_data.items():
        if sector not in ALLOWED_SECTORS:
            continue
        
        for symbol in symbols:
            # SQL 查询逻辑：
            # 1. 获取当前最新价格 (日期 <= today_str 的最新记录)
            # 2. 获取过去一年内的最低价格 (date 介于 one_year_ago_str 和 today_str 之间)
            query = f"""
                SELECT 
                    (SELECT price FROM "{sector}" WHERE name = ? AND date <= ? ORDER BY date DESC LIMIT 1) as latest_price,
                    (SELECT MIN(price) FROM "{sector}" WHERE name = ? AND date >= ? AND date <= ?) as min_price
            """
            
            try:
                # 注意这里传入参数的数量和顺序发生了变化
                cursor.execute(query, (symbol, today_str, symbol, one_year_ago_str, today_str))
                row = cursor.fetchone()
                
                if row and row[0] is not None and row[1] is not None:
                    latest_p, min_p = row
                    
                    # 只有当最低价格大于0时才计算，避免除零错误
                    if min_p > 0:
                        growth = (latest_p - min_p) / min_p
                        
                        # 增长超过 150% (即增长率 > 1.5)
                        if growth > 1.5:
                            final_symbols.append(symbol)
            
            except sqlite3.OperationalError:
                # 表不存在则跳过
                continue

    conn.close()
    
    # 输出简单 JSON 列表
    return json.dumps(final_symbols, indent=4)

if __name__ == "__main__":
    result_json = get_growth_stocks()
    print(result_json)