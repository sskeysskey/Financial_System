import sqlite3
import json
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# 定义黑名单
blacklist = ["YNDX"]

def is_blacklisted(name):
    """检查给定的股票符号是否在黑名单中"""
    return name in blacklist

def create_connection(db_file):
    conn = None
    conn = sqlite3.connect(db_file)
    return conn

def get_price_comparison(cursor, table_name, months_back, name, today):
    yesterday = today - timedelta(days=1)
    day_of_week = yesterday.weekday()  # 周一为0，周日为6

    if day_of_week == 5:  # 昨天是周六
        yesterday = today - timedelta(days=2)  # 取周五
    elif day_of_week == 6:  # 昨天是周日
        yesterday = today - timedelta(days=3)  # 取上周五

    ex_yesterday = yesterday - timedelta(days=1)
    past_date = yesterday - relativedelta(months=months_back)
    
    query = f"""
    SELECT MAX(price), MIN(price)
    FROM {table_name} WHERE date BETWEEN ? AND ? AND name = ?
    """
    cursor.execute(query, (past_date.strftime("%Y-%m-%d"), ex_yesterday.strftime("%Y-%m-%d"), name))
    return cursor.fetchone()

def save_output_to_file(output, directory, filename):
    # 获取当前时间，并格式化为字符串（如'2023-03-15_12-30-00'）
    current_time = datetime.now().strftime('%m%d')
    
    # 在文件名中加入时间戳
    filename = f"{filename.split('.')[0]}_{current_time}.txt"
    
    # 创建文件夹如果它不存在
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    # 定义完整的文件路径
    file_path = os.path.join(directory, filename)
    
    # 将输出写入到文件
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(output)
    print(f"输出已保存到文件：{file_path}")

def main():
    today = datetime.now()
    day_of_week = today.weekday()  # 周一为0，周日为6
    if day_of_week == 0:  # 昨天是周一
        real_today = today - timedelta(days=3)  # 取上周六
    elif day_of_week == 6:  # 昨天是周日
        real_today = today - timedelta(days=2)  # 取上周五
    else:
        real_today = today - timedelta(days=1)

    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_Stock.json', 'r') as file:
        data = json.load(file)

    output = []
    output1 = []
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    intervals = [600, 360, 240, 120, 60, 24, 13, 6, 3, 1]  # 以月份表示的时间间隔列表

    # 遍历JSON中的每个表和股票代码
    for table_name, names in data.items():
        with create_connection(db_path) as conn:
            cursor = conn.cursor()
            for name in names:
                if is_blacklisted(name):
                    print(f"{name} is blacklisted and will be skipped.")
                    continue  # 跳过黑名单中的符号
                today_price_query = f"SELECT price FROM {table_name} WHERE date = ? AND name = ?"
                cursor.execute(today_price_query, (real_today.strftime("%Y-%m-%d"), name))
                result = cursor.fetchone()

                if result:
                    today_price = result[0]
                else:
                    output.append(f"没有找到今天的{name}价格。")
                    continue

                price_extremes = {}
                for months in intervals:
                    max_price, min_price = get_price_comparison(cursor, table_name, months, name, today)
                    price_extremes[months] = (max_price, min_price)  # 存储最大和最小价格

                # 检查是否接近最高价格
                found_max = False
                for months in intervals:
                    if found_max:
                        break
                    max_price, _ = price_extremes.get(months, (None, None))
                    if max_price is not None and today_price >= max_price:
                        found_max = True
                        if today_price >= max_price:
                            if months >= 12:
                                years = months // 12
                                print(f"{table_name} {name} {years}Y_newhigh")
                                output.append(f"{table_name} {name} {years}Y_newhigh")
                            else:
                                print(f"{table_name} {name} {months}M_newhigh")
                                output.append(f"{table_name} {name} {months}M_newhigh")

                # 检查是否接近最低价格
                found_min = False
                for months in intervals:
                    if found_min:
                        break
                    _, min_price = price_extremes.get(months, (None, None))
                    if min_price is not None and today_price <= min_price:
                        found_min = True
                        if today_price <= min_price:
                            if months >= 12:
                                years = months // 12
                                print(f"{table_name} {name} {years}Y_newlow")
                                output.append(f"{table_name} {name} {years}Y_newlow")
                                output1.append(f"{table_name} {name} {years}Y_newlow")
                            else:
                                print(f"{table_name} {name} {months}M_newlow")
                                output.append(f"{table_name} {name} {months}M_newlow")

            output.append("\n")
            cursor.close()

    final_output = "\n".join(output)
    final_output1 = "\n".join(output1)

    # 在代码的最后部分调用save_output_to_file函数
    output_directory = '/Users/yanzhang/Documents/News'
    filename = 'Analyse_Stock.txt'
    filename1 = '52week_newlow.txt'
    save_output_to_file(final_output, output_directory, filename)
    save_output_to_file(final_output1, output_directory, filename1)

if __name__ == "__main__":
    main()