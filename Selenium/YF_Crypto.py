import yfinance as yf
import sqlite3
import json
from datetime import datetime, timedelta
import traceback  # 用于获取完整的错误信息
import re
import os

def log_error_with_timestamp(error_message):
    # 获取当前日期和时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 在错误信息前加入时间戳
    return f"[{timestamp}] {error_message}\n"

def process_error_file(error_file_path, sectors_file_path):
    with open(error_file_path, 'r') as error_file:
        error_content = error_file.read()
    
    # 修改正则表达式以匹配包含连字符的股票代码
    pattern = r'\[.*?\] (\w+) ([\w.\-^=]+): No price data found for the given date range\.'
    matches = re.findall(pattern, error_content)
    print(f"在 today_error1 中找到 {len(matches)} 个匹配项。")
    
    with open(sectors_file_path, 'r') as sectors_file:
        sectors_data = json.load(sectors_file)
    
    # 将匹配的symbol添加到相应的分组中
    for group, symbol in matches:
        if group in sectors_data:
            if symbol not in sectors_data[group]:
                print(f"将 {symbol} 添加到 {group} 组中。")
                sectors_data[group].append(symbol)
                print(f"成功添加 {symbol} 到 {group} 组。")  # 添加确认信息
        else:
            print(f"警告: {group} 组不存在于 sectors 文件中。")

    # 将更新后的数据写回 sectors 文件
    with open(sectors_file_path, 'w') as sectors_file:
        json.dump(sectors_data, sectors_file, indent=4)

def process_crypto(sectors_file_path):
    with open(sectors_file_path, 'r') as sectors_file:
        sectors_data = json.load(sectors_file)
    
    # 手动添加加密货币项到 Crypto 分组
    crypto_symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]
    
    # 检查是否存在 Crypto 分组，如果没有则创建
    if "Crypto" not in sectors_data:
        sectors_data["Crypto"] = []

    # 将四个加密货币项添加到 Crypto 分组中（避免重复添加）
    for crypto_symbol in crypto_symbols:
        if crypto_symbol not in sectors_data["Crypto"]:
            print(f"将 {crypto_symbol} 添加到 Crypto 组中。")  # 日志：添加Crypto symbol
            sectors_data["Crypto"].append(crypto_symbol)

    # 将更新后的数据写回 sectors 文件
    with open(sectors_file_path, 'w') as sectors_file:
        json.dump(sectors_data, sectors_file, indent=4)

def clear_sectors(sectors_file_path):
    with open(sectors_file_path, 'r') as sectors_file:
        sectors_data = json.load(sectors_file)
    
    for group in sectors_data:
        sectors_data[group] = []
    
    with open(sectors_file_path, 'w') as sectors_file:
        json.dump(sectors_data, sectors_file, indent=4)
    print(f"清除完成，empty的所有组内symbol已被清空。")  # 日志：清除完成

def download_and_process_data(ticker_symbol, start_date, end_date, group_name, c, symbol_mapping, yesterday_date, special_groups):
    """尝试下载和处理数据的函数"""
    data = yf.download(ticker_symbol, start=start_date, end=end_date, auto_adjust=True)
    if data.empty:
        return False, 0
    
    # 插入数据到相应的表中
    data_count = 0
    table_name = group_name.replace(" ", "_")
    mapped_name = symbol_mapping.get(ticker_symbol, ticker_symbol)
    
    for index, row in data.iterrows():
        date = yesterday_date
        if group_name in ["Currencies", "Bonds"]:
            price = round(float(row['Close'].iloc[0]), 4)
        elif group_name in ["Crypto"]:
            price = round(float(row['Close'].iloc[0]), 1)
        elif group_name in ["Commodities"]:
            price = round(float(row['Close'].iloc[0]), 3)
        else:
            price = round(float(row['Close'].iloc[0]), 2)

        if group_name in special_groups:
            c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price) VALUES (?, ?, ?)", 
                     (date, mapped_name, price))
        else:
            volume = int(row['Volume'].iloc[0])
            c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price, volume) VALUES (?, ?, ?, ?)", 
                     (date, mapped_name, price, volume))
        
        data_count += 1
    
    return True, data_count

# 主程序开始
sectors_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
error_file_path = '/Users/yanzhang/Documents/News/Today_error1.txt'

# 检查错误文件是否存在
if not os.path.exists(error_file_path):
    print(f"Error: 文件 {error_file_path} 不存在.")
else:    
    # 处理错误文件并更新sectors文件
    process_error_file(error_file_path, sectors_file_path)

process_crypto(sectors_file_path)

now = datetime.now()
today = now.date()
yesterday = today - timedelta(days=1)
ex_yesterday = yesterday - timedelta(days=1)
tomorrow = today + timedelta(days=1)

yesterday_date = yesterday.strftime('%Y-%m-%d')

# 定义三种不同的日期范围配置
date_ranges = [
    (yesterday.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')),
    (today.strftime('%Y-%m-%d'), tomorrow.strftime('%Y-%m-%d')),
    (ex_yesterday.strftime('%Y-%m-%d'), yesterday.strftime('%Y-%m-%d'))
]

# 读取JSON文件
with open(sectors_file_path, 'r') as file:
    stock_groups = json.load(file)

with open('/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json', 'r') as file:
    symbol_mapping = json.load(file)

conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
c = conn.cursor()

# 定义需要特殊处理的group_name
special_groups = ["Currencies", "Bonds", "Crypto", "Commodities"]

# 初始化总数据计数器
total_data_count = 0

for group_name, tickers in stock_groups.items():
    data_count = 0  # 初始化分组数据计数器
    for ticker_symbol in tickers:
        success = False
        
        for start_date, end_date in date_ranges:
            try:
                print(f"尝试下载 {ticker_symbol} 的数据，日期范围: {start_date} 到 {end_date}")
                success, current_count = download_and_process_data(
                    ticker_symbol, start_date, end_date, group_name, c,
                    symbol_mapping, yesterday_date, special_groups
                )
                
                if success:
                    print(f"成功插入 第{current_count}条 {ticker_symbol} 的数据")
                    data_count += current_count
                    break  # 如果成功，退出日期范围循环
            
            except Exception as e:
                if start_date == date_ranges[-1][0]:  # 如果是最后一次尝试
                    formatted_error_message = log_error_with_timestamp(f"{group_name} {ticker_symbol}: {str(e)}")
                    with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                        error_file.write(formatted_error_message)
                continue  # 如果失败，继续尝试下一个日期范围
        
        if not success:
            print(f"无法获取 {ticker_symbol} 的数据，所有日期范围都已尝试")

    if data_count > 0:
        print(f"{group_name} 数据处理完成，总共下载了 {data_count} 条数据。")

    # 累加到总数据计数器
    total_data_count += data_count

# 根据总计数器的值输出最终日志信息
if total_data_count == 0:
    print("没有数据被写入数据库")
else:
    print(f"共有 {total_data_count} 个数据成功写入数据库")

# 提交事务
conn.commit()
conn.close()

# 清除所有组别中的symbol
clear_sectors(sectors_file_path)