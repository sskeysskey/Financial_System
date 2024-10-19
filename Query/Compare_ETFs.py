from datetime import datetime, timedelta
import sqlite3
import json
import os
import re

def create_connection(db_file):
    return sqlite3.connect(db_file)

def log_error_with_timestamp(error_message, error_file_path):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(error_file_path, 'a') as error_file:
        error_file.write(f"[{timestamp}] {error_message}\n")

def get_latest_two_dates(cursor, table_name, name):
    query = f"""
    SELECT date FROM {table_name}
    WHERE name = ? 
    ORDER BY date DESC
    LIMIT 2
    """
    cursor.execute(query, (name,))
    return cursor.fetchall()

def get_prices(cursor, table_name, name, dates):
    query = f"""
    SELECT date, price, volume FROM {table_name}
    WHERE name = ? AND date IN (?, ?)
    ORDER BY date DESC
    """
    cursor.execute(query, (name, *dates))
    return cursor.fetchall()

def get_latest_four_dates(cursor, table_name, name):
    query = f"""
    SELECT date FROM {table_name}
    WHERE name = ? 
    ORDER BY date DESC
    LIMIT 4
    """
    cursor.execute(query, (name,))
    return cursor.fetchall()

def get_prices_four_days(cursor, table_name, name, dates):
    query = f"""
    SELECT date, price, volume FROM {table_name}
    WHERE name = ? AND date IN (?, ?, ?, ?)
    ORDER BY date DESC
    """
    cursor.execute(query, (name, *dates))
    return cursor.fetchall()

def compare_today_yesterday(config_path, description_path, blacklist, interested_sectors, db_path, output_path, error_file_path):
    with open(config_path, 'r') as file:
        data = json.load(file)

    with open(description_path, 'r') as file:
        description_data = json.load(file)

    # 构建symbol到tag的映射
    symbol_to_tags = {}
    for item in description_data.get("stocks", []) + description_data.get("etfs", []):
        symbol_to_tags[item["symbol"]] = item.get("tag", [])

    output = []
    with create_connection(db_path) as conn:
        cursor = conn.cursor()
        for table_name, names in data.items():
            if table_name in interested_sectors:
                for name in names:
                    if name in blacklist:
                        print(f"跳过黑名单中的ETF: {name}", error_file_path)
                        continue
                    try:
                        results = get_latest_four_dates(cursor, table_name, name)
                        if len(results) < 4:
                            raise ValueError(f"无法找到 {table_name} 下的 {name} 足够的历史数据进行比较。")

                        dates = [result[0] for result in results]
                        prices = get_prices_four_days(cursor, table_name, name, dates)

                        if len(prices) == 4:
                            latest_price, second_latest_price = prices[0][1], prices[1][1]
                            latest_volume, second_latest_volume = prices[0][2], prices[1][2]
                            change = latest_price - second_latest_price
                            percentage_change = (change / second_latest_price) * 100
                            volume_change = latest_volume - second_latest_volume
                            percentage_volume_change = (volume_change / second_latest_volume) * 100

                            # 检查连续上涨
                            consecutive_rise = 0
                            if prices[0][1] > prices[1][1] and prices[1][1] > prices[2][1]:
                                consecutive_rise = 2
                                if prices[2][1] > prices[3][1]:
                                    consecutive_rise = 3

                            # 检查连续下跌
                            consecutive_fall = 0
                            if prices[0][1] < prices[1][1] and prices[1][1] < prices[2][1]:
                                consecutive_fall = 2
                                if prices[2][1] < prices[3][1]:
                                    consecutive_fall = 3

                            output.append((f"{table_name} {name}", percentage_change, latest_volume, percentage_volume_change, consecutive_rise, consecutive_fall))
                        else:
                            raise ValueError(f"无法比较 {table_name} 下的 {name}，因为缺少必要的数据。")
                    except Exception as e:
                        log_error_with_timestamp(str(e), error_file_path)

    if output:
        output.sort(key=lambda x: x[1], reverse=True)
        with open(output_path, 'w') as file:
            for line in output:
                sector, company = line[0].rsplit(' ', 1)
                percentage_change, latest_volume, percentage_volume_change, consecutive_rise, consecutive_fall = line[1], line[2], line[3], line[4], line[5]
                
                original_company = company  # 保留原始公司名称
                if latest_volume > 3000000:
                    company += '.*'
                
                # 添加连续上涨标记
                if consecutive_rise == 2:
                    company += '.+'
                elif consecutive_rise == 3:
                    company += '.++'

                # 添加连续下跌标记
                if consecutive_fall == 2:
                    company += '.-'
                elif consecutive_fall == 3:
                    company += '.--'
                
                # 获取对应symbol的tags
                tags = symbol_to_tags.get(original_company, [])
                tags_str = ', '.join(f'{tag}' for tag in tags)
                
                file.write(f"{company:<10}: {percentage_change:>6.2f}%   {latest_volume:<10} {percentage_volume_change:>7.2f}%   {tags_str}\n")
        print(f"{output_path} 已生成。")
    else:
        log_error_with_timestamp("输出为空，无法进行保存文件操作。", error_file_path)

def clean_old_backups(directory, prefix="CompareETFs_", days=4):
    """删除备份目录中超过指定天数的文件"""
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    for filename in os.listdir(directory):
        if filename.startswith(prefix):  # 只处理特定前缀的文件
            try:
                date_str = filename.split('_')[-1].split('.')[0]  # 获取日期部分
                file_date = datetime.strptime(date_str, '%m%d')
                # 将年份设置为今年
                file_date = file_date.replace(year=now.year)
                if file_date < cutoff:
                    file_path = os.path.join(directory, filename)
                    os.remove(file_path)
                    print(f"删除旧备份文件：{file_path}")
            except Exception as e:
                print(f"跳过文件：{filename}，原因：{e}")

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    description_path = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'
    
    blacklist = ["ERY","TQQQ","QLD","SOXL","SPXL","SVXY","YINN","CHAU","UVXY",
                "VIXY","VXX","SPXS","SPXU","ZSL","AGQ","SCO","UCO","TMF","SOXS","BOIL"]

    interested_sectors = ["ETFs"]
    file_path = '/Users/yanzhang/Documents/News/CompareETFs.txt'
    directory_backup = '/Users/yanzhang/Documents/News/site/'
    error_file_path = '/Users/yanzhang/Documents/News/Today_error.txt'
    
    if os.path.exists(file_path):
        yesterday = datetime.now() - timedelta(days=1)
        timestamp = yesterday.strftime('%m%d')
        directory, filename = os.path.split(file_path)
        name, extension = os.path.splitext(filename)
        new_filename = f"{name}_{timestamp}{extension}"
        new_file_path = os.path.join(directory_backup, new_filename)
        os.rename(file_path, new_file_path)
        print(f"文件已重命名为: {new_file_path}")
    else:
        print("文件不存在")
    
    compare_today_yesterday(config_path, description_path, blacklist, interested_sectors,
                            '/Users/yanzhang/Documents/Database/Finance.db',
                            file_path, error_file_path)
    clean_old_backups(directory_backup)