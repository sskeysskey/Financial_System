import sqlite3
import json
from datetime import datetime
from collections import defaultdict

def read_json(json_path):
    with open(json_path, 'r') as file:
        return json.load(file)

def get_monthly_avg_prices(cursor, table_name, symbol):
    cursor.execute(f"SELECT date, price FROM {table_name} WHERE name = ?", (symbol,))
    data = cursor.fetchall()
    
    monthly_data = defaultdict(list)
    
    for date_str, price in data:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        month_key = (date.year, date.month)
        monthly_data[month_key].append(price)
    
    monthly_avg_prices = {month: sum(prices) / len(prices) for month, prices in monthly_data.items()}
    
    return monthly_avg_prices, len(monthly_avg_prices)

def check_increasing_prices(monthly_avg_prices):
    sorted_months = sorted(monthly_avg_prices.keys())
    decrease_count = 0
    for i in range(1, len(sorted_months)):
        if monthly_avg_prices[sorted_months[i]] <= monthly_avg_prices[sorted_months[i - 1]]:
            decrease_count += 1
            if decrease_count > 10:
                return False
    return True

def find_increasing_symbols(db_path, json_path):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        sectors = read_json(json_path)
        
        for table_name, symbols in sectors.items():
            for symbol in symbols:
                monthly_avg_prices, month_count = get_monthly_avg_prices(cursor, table_name, symbol)
                if month_count >= 12 and check_increasing_prices(monthly_avg_prices):
                    print(f"Symbol '{symbol}' in table '{table_name}' has increasing monthly average prices with at most three decreases.")

# 路径替换为实际路径
db_path = '/Users/yanzhang/Documents/Database/Finance.db'
json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'

find_increasing_symbols(db_path, json_path)