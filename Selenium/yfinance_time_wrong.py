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
    
    # 修改后的正则表达式，确保匹配带有特殊符号的股票代码
    pattern = r'\[.*?\] (\w+) ([\w.^=]+): No price data found for the given date range\.'
    matches = re.findall(pattern, error_content)
    print(f"在 today_error1 中找到 {len(matches)} 个匹配项。")  # 日志：匹配结果数量
    
    with open(sectors_file_path, 'r') as sectors_file:
        sectors_data = json.load(sectors_file)
    
    # 将匹配的symbol添加到相应的分组中
    for group, symbol in matches:
        if group in sectors_data and symbol not in sectors_data[group]:
            print(f"将 {symbol} 添加到 {group} 组中。")  # 日志：添加symbol
            sectors_data[group].append(symbol)

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

# 读取JSON文件
with open(sectors_file_path, 'r') as file:
    stock_groups = json.load(file)

# 读取symbol_mapping JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json', 'r') as file:
    symbol_mapping = json.load(file)

today = now.date()
yesterday = today - timedelta(days=1)
tomorrow = today + timedelta(days=1)

# 定义时间范围
yesterday_date = yesterday.strftime('%Y-%m-%d')
start_date = today.strftime('%Y-%m-%d')
end_date = tomorrow.strftime('%Y-%m-%d')

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
c = conn.cursor()

# 定义需要特殊处理的group_name
special_groups = ["Currencies", "Bonds", "Crypto", "Commodities"]

# 初始化总数据计数器
total_data_count = 0

for group_name, tickers in stock_groups.items():
    data_count = 0  # 初始化分组数据计数器
    for ticker_symbol in tickers:
        try:
            print(f"开始下载 {ticker_symbol} 的数据，日期范围: {start_date} 到 {end_date}.")  # 日志：下载数据
            data = yf.download(ticker_symbol, start=start_date, end=end_date)
            if data.empty:
                # raise ValueError(f"{ticker_symbol}: No price data found for the given date range.")
                raise ValueError(f"{group_name} {ticker_symbol}: No price data found for the given date range.")

            # 插入数据到相应的表中
            table_name = group_name.replace(" ", "_")  # 确保表名没有空格
            mapped_name = symbol_mapping.get(ticker_symbol, ticker_symbol)  # 从映射字典获取名称，如果不存在则使用原始 ticker_symbol
            for index, row in data.iterrows():
                date = yesterday_date  # 使用昨天的日期
                if group_name in ["Currencies", "Bonds"]:
                    price = round(row['Close'], 4)
                elif group_name in ["Crypto"]:
                    price = round(row['Close'], 1)
                elif group_name in ["Commodities"]:
                    price = round(row['Close'], 3)
                else:
                    price = round(row['Close'], 2)

                if group_name in special_groups:
                    c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price) VALUES (?, ?, ?)", (date, mapped_name, price))
                else:
                    volume = int(row['Volume'])
                    c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price, volume) VALUES (?, ?, ?, ?)", (date, mapped_name, price, volume))
                
                data_count += 1  # 成功插入一条数据，计数器增加

            print(f"成功插入 第{data_count}条 {ticker_symbol} 的数据到 {table_name} 中。")  # 日志：插入数据

        except Exception as e:
            formatted_error_message = log_error_with_timestamp(str(e))
            # 将错误信息追加到文件中
            with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                error_file.write(formatted_error_message)

    # Only print if data_count > 0
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