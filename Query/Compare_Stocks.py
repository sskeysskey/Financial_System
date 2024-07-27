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

def read_earnings_release(filepath):
    earnings_companies = {}
    pattern_single_colon = re.compile(r'(\w+)\s*:\s*(\d{4}-\d{2}-(\d{2}))')
    pattern_double_colon = re.compile(r'(\w+)\s*:\s*\w+\s*:\s*(\d{4}-\d{2}-(\d{2}))')
    
    with open(filepath, 'r') as file:
        for line in file:
            match_double = pattern_double_colon.search(line)
            match_single = pattern_single_colon.search(line)
            if match_double:
                company = match_double.group(1).strip()
                day = match_double.group(3)
                earnings_companies[company] = day
            elif match_single:
                company = match_single.group(1).strip()
                day = match_single.group(3)
                earnings_companies[company] = day
                
    return earnings_companies

def read_gainers_losers(filepath):
    with open(filepath, 'r') as file:
        data = json.load(file)
    if not data:
        return [], []
    # 找到最新的日期
    latest_date = max(data.keys(), key=lambda d: datetime.strptime(d, "%Y-%m-%d"))
    # 返回最新日期的数据
    return data.get(latest_date, {}).get('gainer', []), data.get(latest_date, {}).get('loser', [])

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

def compare_today_yesterday(config_path, blacklist, interested_sectors, db_path, earnings_path, gainers_losers_path, output_path, error_file_path):
    with open(config_path, 'r') as file:
        data = json.load(file)

    earnings_companies = read_earnings_release(earnings_path)
    gainers, losers = read_gainers_losers(gainers_losers_path)

    output = []

    with create_connection(db_path) as conn:
        cursor = conn.cursor()
        for table_name, names in data.items():
            if table_name in interested_sectors:
                for name in names:
                    if name in blacklist:
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

                            output.append((f"{table_name} {name}", percentage_change, latest_volume, percentage_volume_change, consecutive_rise))
                        else:
                            raise ValueError(f"无法比较 {table_name} 下的 {name}，因为缺少必要的数据。")
                    except Exception as e:
                        log_error_with_timestamp(str(e), error_file_path)

    if output:
        output.sort(key=lambda x: x[1], reverse=True)
        with open(output_path, 'w') as file:
            for line in output:
                sector, company = line[0].rsplit(' ', 1)
                percentage_change, latest_volume, percentage_volume_change, consecutive_rise = line[1], line[2], line[3], line[4]
                
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
                
                file.write(f"{sector:<25}{company:<15}: {percentage_change:>6.2f}%    {percentage_volume_change:>6.2f}%\n")
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
    blacklist = ['VFS','KVYO','LU','IEP','LOT','GRFS','BGNE']
    interested_sectors = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                          "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare", "Industrials",
                          "Real_Estate", "Technology", "Utilities"]
    file_path = '/Users/yanzhang/Documents/News/CompareStock.txt'
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
    
    compare_today_yesterday(config_path, blacklist, interested_sectors,
                            '/Users/yanzhang/Documents/Database/Finance.db',
                            '/Users/yanzhang/Documents/News/Earnings_Release_new.txt',
                            '/Users/yanzhang/Documents/Financial_System/Modules/Gainer_Loser.json',
                            file_path, error_file_path)
    clean_old_backups(directory_backup)