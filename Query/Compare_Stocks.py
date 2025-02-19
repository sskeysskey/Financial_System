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

# def read_earnings_release(filepath, error_file_path):
#     if not os.path.exists(filepath):
#         log_error_with_timestamp(f"文件 {filepath} 不存在。", error_file_path)
#         return {}

#     earnings_companies = {}

#     # 修改后的正则表达式
#     pattern_colon = re.compile(r'([\w-]+)(?::[\w]+)?\s*:\s*\d+\s*:\s*(\d{4}-\d{2}-\d{2})')

#     with open(filepath, 'r') as file:
#         for line in file:
#             match = pattern_colon.search(line)
#             company = match.group(1).strip()
#             date = match.group(2)
#             day = date.split('-')[2]  # 只取日期的天数
#             earnings_companies[company] = day
#     return earnings_companies

def read_earnings_release(filepath, error_file_path):
    if not os.path.exists(filepath):
        log_error_with_timestamp(f"文件 {filepath} 不存在。", error_file_path)
        return {}

    earnings_companies = {}

    # 修改正则表达式以更好地匹配文件格式
    pattern_colon = re.compile(r'^([^:]+)(?::[YWBCOb])?\s*:\s*\d+\s*:\s*(\d{4}-\d{2}-\d{2})')

    with open(filepath, 'r') as file:
        for line_number, line in enumerate(file, 1):  # 添加行号
            line = line.strip()
            if not line:  # 跳过空行
                continue
                
            match = pattern_colon.search(line)
            if match:  # 添加判断，确保match不是None
                company = match.group(1).strip()
                date = match.group(2)
                day = date.split('-')[2]  # 只取日期的天数
                earnings_companies[company] = day
            else:
                log_error_with_timestamp(f"第 {line_number} 行无法解析: '{line}'", error_file_path)
                
    return earnings_companies

def read_gainers_losers(filepath):
    if not os.path.exists(filepath):
        return [], []

    with open(filepath, 'r') as file:
        data = json.load(file)
        
    if not data:
        return [], []

    today_date = datetime.now().strftime("%Y-%m-%d")
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 尝试获取今天的数据
    if today_date in data:
        return data[today_date].get('gainer', []), data[today_date].get('loser', [])
    # 如果今天的数据不存在，尝试获取昨天的数据
    elif yesterday_date in data:
        return data[yesterday_date].get('gainer', []), data[yesterday_date].get('loser', [])
    else:
        return [], []

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

def get_latest_available_dates(cursor, table_name, name, limit=4):
    query = f"""
    SELECT date FROM {table_name}
    WHERE name = ? 
    ORDER BY date DESC
    LIMIT ?
    """
    cursor.execute(query, (name, limit))
    return cursor.fetchall()

def get_prices_available_days(cursor, table_name, name, dates):
    placeholders = ', '.join('?' for _ in dates)
    query = f"""
    SELECT date, price, volume FROM {table_name}
    WHERE name = ? AND date IN ({placeholders})
    ORDER BY date DESC
    """
    cursor.execute(query, (name, *dates))
    return cursor.fetchall()

def compare_today_yesterday(config_path, description_path, blacklist, interested_sectors, db_path, earnings_path, gainers_losers_path, output_path, error_file_path):
    with open(config_path, 'r') as file:
        data = json.load(file)

    earnings_companies = read_earnings_release(earnings_path, error_file_path)
    gainers, losers = read_gainers_losers(gainers_losers_path)

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
                        log_error_with_timestamp(f"跳过黑名单中的股票: {name}", error_file_path)
                        continue
                    try:
                        results = get_latest_available_dates(cursor, table_name, name)
                        if len(results) < 2:
                            raise ValueError(f"无法找到 {table_name} 下的 {name} 足够的历史数据进行比较。")

                        dates = [result[0] for result in results]
                        prices = get_prices_available_days(cursor, table_name, name, dates)

                        if len(prices) >= 2:
                            latest_price, second_latest_price = prices[0][1], prices[1][1]
                            latest_volume, second_latest_volume = prices[0][2], prices[1][2]
                            change = latest_price - second_latest_price
                            if second_latest_price != 0:
                                percentage_change = (change / second_latest_price) * 100
                            else:
                                raise ValueError(f" {table_name} 下的 {name} 的 second_latest_price 为零")
                            volume_change = latest_volume - second_latest_volume
                            if second_latest_volume != 0:
                                percentage_volume_change = (volume_change / second_latest_volume) * 100
                            else:
                                raise ValueError(f" {table_name} 下的 {name} 的 second_latest_volume 为零")

                            # 检查连续上涨
                            consecutive_rise = 0
                            if len(prices) >= 3 and prices[0][1] > prices[1][1] and prices[1][1] > prices[2][1]:
                                consecutive_rise = 2
                                if len(prices) >= 4 and prices[2][1] > prices[3][1]:
                                    consecutive_rise = 3

                            # 检查连续下跌
                            consecutive_fall = 0
                            if len(prices) >= 3 and prices[0][1] < prices[1][1] and prices[1][1] < prices[2][1]:
                                consecutive_fall = 2
                                if len(prices) >= 4 and prices[2][1] < prices[3][1]:
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
                if original_company in earnings_companies:
                    company += f'.{earnings_companies[original_company]}'
                if latest_volume > 5000000:
                    company += '.*'
                if original_company in gainers:
                    company += '.>'
                elif original_company in losers:
                    company += '.<'
                
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
                
                file.write(f"{sector:<25}{company:<15}: {percentage_change:>6.2f}%  {tags_str}\n")
        print(f"{output_path} 已生成。")
    else:
        log_error_with_timestamp("输出为空，无法进行保存文件操作。", error_file_path)

def clean_old_backups(directory, prefix="CompareStock_", days=4):
    """删除备份目录中超过指定天数的文件"""
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    for filename in os.listdir(directory):
        if filename.startswith(prefix):  # 只处理特定前缀的文件
            try:
                date_str = filename.split('_')[-1].split('.')[0]  # 获取日期部分
                file_date = datetime.strptime(date_str, '%y%m%d')
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
    blacklist = []
    interested_sectors = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                          "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare", "Industrials",
                          "Real_Estate", "Technology", "Utilities"]
    file_path = '/Users/yanzhang/Documents/News/CompareStock.txt'
    directory_backup = '/Users/yanzhang/Documents/News/site/'
    error_file_path = '/Users/yanzhang/Documents/News/Today_error.txt'
    
    if os.path.exists(file_path):
        yesterday = datetime.now() - timedelta(days=1)
        timestamp = yesterday.strftime('%y%m%d')
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
                            '/Users/yanzhang/Documents/News/Earnings_Release_new.txt',
                            '/Users/yanzhang/Documents/Financial_System/Modules/Gainer_Loser.json',
                            file_path, error_file_path)
    clean_old_backups(directory_backup)