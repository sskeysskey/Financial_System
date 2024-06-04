import yfinance as yf
import sqlite3
import json
from datetime import datetime, timedelta

def log_error_with_timestamp(error_message):
    # 获取当前日期和时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 在错误信息前加入时间戳
    return f"[{timestamp}] {error_message}\n"

# 适合于纯自定义抓取
# start_date = "2024-05-23"
# end_date = "2024-06-03"

# 适合于半自定义抓取
start_date = "2000-09-16"
today = datetime.now()
end_date = today.strftime('%Y-%m-%d')

# 适合于只抓今天
# today = datetime.now()
# yesterday = today - timedelta(days=1)
# start_date = yesterday.strftime('%Y-%m-%d')
# end_date = today.strftime('%Y-%m-%d')

# 读取JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json', 'r') as file:
    stock_groups = json.load(file)

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
c = conn.cursor()

# 读取symbol_mapping JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json', 'r') as file:
    symbol_mapping = json.load(file)

# 定义需要特殊处理的group_name
special_groups = ["Currencies", "Bonds", "Crypto", "Commodities"]

# 遍历所有组
for group_name, tickers in stock_groups.items():
    for ticker_symbol in tickers:
        try:
            # 使用 yfinance 下载股票数据
            data = yf.download(ticker_symbol, start=start_date, end=end_date)
            if data.empty:
                raise ValueError(f"{ticker_symbol}: No price data found for the given date range.")

            # 插入数据到相应的表中
            table_name = group_name.replace(" ", "_")  # 确保表名没有空格
            mapped_name = symbol_mapping.get(ticker_symbol, ticker_symbol)
            for index, row in data.iterrows():
                date = index.strftime('%Y-%m-%d')
                if group_name in ["Currencies", "Bonds", "Crypto"]:
                    price = round(row['Close'], 6)
                elif group_name in ["Commodities", "Indices"]:
                    price = round(row['Close'], 4)
                else:
                    price = round(row['Close'], 2)

                if group_name in special_groups:
                    c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price) VALUES (?, ?, ?)",
                                (date, mapped_name, price))
                else:
                    volume = int(row['Volume'])
                    c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price, volume) VALUES (?, ?, ?, ?)",
                                (date, mapped_name, price, volume))
        except Exception as e:
                formatted_error_message = log_error_with_timestamp(str(e))
                # 将错误信息追加到文件中
                with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                    error_file.write(formatted_error_message)

        print(f"{ticker_symbol} 已成功写入数据库")  # 添加打印语句

# 提交事务
conn.commit()
# 关闭连接
conn.close()