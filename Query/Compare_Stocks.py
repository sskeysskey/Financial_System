from datetime import datetime, timedelta
import sqlite3
import json

def create_connection(db_file):
    conn = None
    conn = sqlite3.connect(db_file)
    return conn

def compare_today_yesterday(config_path, output_file):
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

    for table_name, groups in data.items():
            for group_name, names in groups.items():
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
                            output.append((f"{table_name} {group_name} {name}", percentage_change))

    # 对输出进行排序，根据变化百分比
    output.sort(key=lambda x: x[1], reverse=True)

    with open(output_file, 'w') as file:
        for line in output:
            file.write(f"{line[0]}: {line[1]:.2f}%\n")
    print(f"{output_file} 已生成。")

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_Stock.json'
    output_file = '/Users/yanzhang/Documents/News/Compare_Stocks.txt'
    compare_today_yesterday(config_path, output_file)