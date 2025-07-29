import yfinance as yf
import sqlite3
import json
from datetime import datetime, timedelta

def log_error_with_timestamp(error_message):
    # 获取当前日期和时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 在错误信息前加入时间戳
    return f"[{timestamp}] {error_message}\n"

def get_price_format(group_name: str) -> int:
    """根据组名决定价格小数位数"""
    if group_name in ["Currencies", "Bonds"]:
        return 4
    elif group_name == "Crypto":
        return 1
    elif group_name == "Commodities":
        return 3
    else:
        return 2

now = datetime.now()
# 判断今天的星期数，如果是周日(6)或周一(0)，则不执行程序
if now.weekday() in (0, 6):
    print("Today is either Sunday or Monday. The script will not run.")
else:
    # 读取JSON文件
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_US_holiday.json', 'r') as file:
        stock_groups = json.load(file)

    # 读取symbol_mapping JSON文件
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json', 'r') as file:
        symbol_mapping = json.load(file)

    today = now.date()
    yesterday = today - timedelta(days=1)

    # 定义时间范围
    start_date = yesterday.strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')

    # start_date = "2025-01-02"
    # end_date = "2025-01-03"

    # 连接到SQLite数据库
    conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
    c = conn.cursor()

    # 定义需要特殊处理的group_name
    special_groups = ["Currencies", "Bonds", "Crypto", "Commodities"]

    for group_name, tickers in stock_groups.items():
        data_count = 0  # 初始化计数器
        for ticker_symbol in tickers:
            try:
                # 使用 yfinance 下载股票数据
                data = yf.download(ticker_symbol, start=start_date, end=end_date, auto_adjust=True)
                if data is None or data.empty:
                    raise ValueError(f"{group_name} {ticker_symbol}: No price data found for the given date range.")

                # 插入数据到相应的表中
                table_name = group_name.replace(" ", "_")  # 确保表名没有空格
                mapped_name = symbol_mapping.get(ticker_symbol, ticker_symbol)  # 从映射字典获取名称，如果不存在则使用原始 ticker_symbol
                decimal_places = get_price_format(group_name)
                for index, row in data.iterrows():
                    date = index.strftime('%Y-%m-%d')
                    # 使用.iloc[0]来获取Series的值
                    price = round(float(row['Close'].iloc[0]), decimal_places)

                    if group_name in special_groups:
                        c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price) VALUES (?, ?, ?)", (date, mapped_name, price))
                    else:
                        # 使用.iloc[0]来获取Series的值
                        volume = int(row['Volume'].iloc[0])
                        c.execute(f"INSERT OR REPLACE INTO {table_name} (date, name, price, volume) VALUES (?, ?, ?, ?)", (date, mapped_name, price, volume))
                    
                    data_count += 1  # 成功插入一条数据，计数器增加
            except Exception as e:
                formatted_error_message = log_error_with_timestamp(str(e))
                # 将错误信息追加到文件中
                with open('/Users/yanzhang/Documents/News/Today_error1.txt', 'a') as error_file:
                    error_file.write(formatted_error_message)

        # 在完成每个group_name后打印信息
        print(f"{group_name} 数据处理完成，总共下载了 {data_count} 条数据。")

    print("所有数据已成功写入数据库")
    # 提交事务
    conn.commit()
    # 关闭连接
    conn.close()