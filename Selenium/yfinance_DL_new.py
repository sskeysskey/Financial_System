import yfinance as yf
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

def log_error_with_timestamp(error_message: str) -> str:
    """为错误消息添加时间戳"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"[{timestamp}] {error_message}\n"

def is_stock_groups_empty(stock_groups: Dict[str, List[str]]) -> bool:
    """检查所有股票组是否为空"""
    return all(len(tickers) == 0 for tickers in stock_groups.values())

def get_price_format(group_name: str) -> int:  # 改为返回整数
    """根据组名决定价格小数位数"""
    if group_name in ["Currencies", "Bonds"]:
        return 4
    elif group_name == "Crypto":
        return 1
    elif group_name == "Commodities":
        return 3
    else:
        return 2

def insert_data(c: sqlite3.Cursor, table_name: str, date: str, name: str, price: float, volume: int = None):
    """插入数据到数据库"""
    if volume is None:
        c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price) VALUES (?, ?, ?)",
                  (date, name, price))
    else:
        c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price, volume) VALUES (?, ?, ?, ?)",
                  (date, name, price, volume))

def process_stock_data(stock_groups: Dict[str, List[str]], start_date: str, end_date: str, 
                       db_path: str, symbol_mapping: Dict[str, str], error_file_path: str):
    """处理股票数据的主要逻辑"""
    special_groups = ["Currencies", "Bonds", "Crypto", "Commodities"]
    
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        
        for group_name, tickers in stock_groups.items():
            for ticker_symbol in tickers:
                try:
                    data = yf.download(ticker_symbol, start=start_date, end=end_date)
                    if data.empty:
                        raise ValueError(f"{group_name} {ticker_symbol}: No price data found for the given date range.")

                    table_name = group_name.replace(" ", "_")
                    mapped_name = symbol_mapping.get(ticker_symbol, ticker_symbol)
                    decimal_places = get_price_format(group_name)  # 获取小数位数

                    for index, row in data.iterrows():
                        date = index.strftime('%Y-%m-%d')
                        price = round(float(row['Close']), decimal_places)  # 直接使用整数作为小数位数
                        
                        if group_name in special_groups:
                            insert_data(c, table_name, date, mapped_name, price)
                        else:
                            volume = int(row['Volume'])
                            insert_data(c, table_name, date, mapped_name, price, volume)

                except Exception as e:
                    formatted_error_message = log_error_with_timestamp(str(e))
                    with open(error_file_path, 'a') as error_file:
                        error_file.write(formatted_error_message)

        conn.commit()

def main():
    start_date = "2002-09-17"
    end_date = datetime.now().strftime('%Y-%m-%d')
    sectors_file = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
    symbol_mapping_file = '/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json'
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    error_file_path = '/Users/yanzhang/Documents/News/Today_error.txt'

    with open(sectors_file, 'r') as file:
        stock_groups = json.load(file)

    if is_stock_groups_empty(stock_groups):
        print("Sectors_empty.json 文件为空，跳过后续操作。")
        return

    with open(symbol_mapping_file, 'r') as file:
        symbol_mapping = json.load(file)

    process_stock_data(stock_groups, start_date, end_date, db_path, symbol_mapping, error_file_path)

    # 清空各组内的symbol
    stock_groups = {group: [] for group in stock_groups}

    with open(sectors_file, 'w') as file:
        json.dump(stock_groups, file, indent=4)

if __name__ == "__main__":
    main()