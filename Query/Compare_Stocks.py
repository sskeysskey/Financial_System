from datetime import datetime, timedelta
import sqlite3
import json
import os

def create_connection(db_file):
    conn = None
    conn = sqlite3.connect(db_file)
    return conn

def compare_today_yesterday(config_path):
    with open(config_path, 'r') as file:
            data = json.load(file)

    output = []  # 用于收集输出信息的列表
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    day_of_week = yesterday.weekday()
    if day_of_week == 0:  # 昨天是周一
        ex_yesterday = yesterday - timedelta(days=3)  # 取上周五
    elif day_of_week in {5, 6}:  # 昨天是周六或周日
        yesterday = yesterday - timedelta(days=(day_of_week - 4))  # 周五
        ex_yesterday = yesterday - timedelta(days=1)
    else:
        ex_yesterday = yesterday - timedelta(days=1)

    for table_name, names in data.items():
        with create_connection(db_path) as conn:
            cursor = conn.cursor()
            for name in names:
                query = f"""
                SELECT date, price FROM {table_name} 
                WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
                """
                cursor.execute(query, (name, yesterday.strftime("%Y-%m-%d"), ex_yesterday.strftime("%Y-%m-%d")))
                results = cursor.fetchall()

                if len(results) == 2:
                    yesterday_price = results[0][1]
                    ex_yesterday_price = results[1][1]
                    change = yesterday_price - ex_yesterday_price
                    percentage_change = (change / ex_yesterday_price) * 100
                    output.append((f"{table_name} {name}", percentage_change))

    # 对输出进行排序，根据变化百分比
    output.sort(key=lambda x: x[1], reverse=True)

    # 生成输出文件名，包含时间戳
    # timestamp = datetime.now().strftime("%m_%d")
    # output_file = f'/Users/yanzhang/Documents/News/Compare_Stocks_{timestamp}.txt'
    output_file = f'/Users/yanzhang/Documents/News/Compare_Stocks.txt'
    with open(output_file, 'w') as file:
        for line in output:
            file.write(f"{line[0]}: {line[1]:.2f}%\n")
    print(f"{output_file} 已生成。")

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_Stock.json'
    # 检查文件是否存在
    file_path = '/Users/yanzhang/Documents/News/Compare_Stocks.txt'
    if os.path.exists(file_path):
        # 获取昨天的日期作为时间戳
        yesterday = datetime.now() - timedelta(days=1)
        timestamp = yesterday.strftime('%m%d')

        # 构建新的文件名
        directory, filename = os.path.split(file_path)
        name, extension = os.path.splitext(filename)
        new_filename = f"{name}_{timestamp}{extension}"
        new_file_path = os.path.join(directory, new_filename)

        # 重命名文件
        os.rename(file_path, new_file_path)
        print(f"文件已重命名为: {new_file_path}")
    else:
        print("文件不存在")
    compare_today_yesterday(config_path)