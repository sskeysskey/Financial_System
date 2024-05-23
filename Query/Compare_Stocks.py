from datetime import datetime, timedelta
import sqlite3
import json
import os

def create_connection(db_file):
    conn = None
    conn = sqlite3.connect(db_file)
    return conn

def compare_today_yesterday(config_path, blacklist):
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
        if table_name in interested_sectors:  # 过滤sector
            with create_connection(db_path) as conn:
                cursor = conn.cursor()
                for name in names:
                    if name in blacklist:  # 检查黑名单
                        continue
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

    output_file = f'/Users/yanzhang/Documents/News/CompareStock.txt'
    with open(output_file, 'w') as file:
        for line in output:
            sector_and_company = line[0].split()
            sector = " ".join(sector_and_company[:-1])  # 获取sector
            company = sector_and_company[-1]  # 获取company

            if company not in blacklist:  # 再次检查黑名单
                # 格式化输出
                file.write(f"{sector:<25}{company:<8}: {line[1]:>6.2f}%\n")
    print(f"{output_file} 已生成。")

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    blacklist = ['VFS','KVYO','LU','IEP','LOT']  # 黑名单列表
    # 定义你感兴趣的sectors
    interested_sectors = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare", "Industrials",
        "Real_Estate", "Technology", "Utilities"]
    # 检查文件是否存在
    file_path = '/Users/yanzhang/Documents/News/CompareStock.txt'
    directory_backup = '/Users/yanzhang/Documents/News/site/'
    if os.path.exists(file_path):
        # 获取昨天的日期作为时间戳
        yesterday = datetime.now() - timedelta(days=1)
        timestamp = yesterday.strftime('%m%d')

        # 构建新的文件名
        directory, filename = os.path.split(file_path)
        name, extension = os.path.splitext(filename)
        new_filename = f"{name}_{timestamp}{extension}"
        new_file_path = os.path.join(directory_backup, new_filename)

        # 重命名文件
        os.rename(file_path, new_file_path)
        print(f"文件已重命名为: {new_file_path}")
    else:
        print("文件不存在")
    compare_today_yesterday(config_path, blacklist)