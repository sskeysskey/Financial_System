from datetime import datetime, timedelta
import sqlite3
import json
import os

def create_connection(db_file):
    conn = sqlite3.connect(db_file)
    return conn

def log_error_with_timestamp(error_message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"[{timestamp}] {error_message}\n"

def read_earnings_release(filepath):
    with open(filepath, 'r') as file:
        companies_with_earnings = {line.split(':')[0] for line in file}
    return companies_with_earnings

def compare_today_yesterday(config_path, blacklist):
    with open(config_path, 'r') as file:
        data = json.load(file)

    output = []
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'
    earnings_companies = read_earnings_release('/Users/yanzhang/Documents/News/Earnings_Release_new.txt')

    for table_name, names in data.items():
        if table_name in interested_sectors:
            with create_connection(db_path) as conn:
                cursor = conn.cursor()
                for name in names:
                    if name in blacklist:
                        continue
                    try:
                        query_two_latest_dates = f"""
                        SELECT date FROM {table_name}
                        WHERE name = ? 
                        ORDER BY date DESC
                        LIMIT 2
                        """
                        cursor.execute(query_two_latest_dates, (name,))
                        results = cursor.fetchall()

                        if len(results) < 2:
                            raise Exception(f"错误：无法找到{table_name}下的{name}足够的历史数据进行比较。")

                        latest_date, second_latest_date = map(lambda x: datetime.strptime(x[0], "%Y-%m-%d"), results)

                        query = f"""
                        SELECT date, price FROM {table_name}
                        WHERE name = ? AND date IN (?, ?) ORDER BY date DESC
                        """
                        cursor.execute(query, (name, latest_date.strftime("%Y-%m-%d"), second_latest_date.strftime("%Y-%m-%d")))
                        prices = cursor.fetchall()

                        if len(prices) == 2:
                            latest_price, second_latest_price = prices[0][1], prices[1][1]
                            change = latest_price - second_latest_price
                            percentage_change = (change / second_latest_price) * 100
                            output.append((f"{table_name} {name}", percentage_change))
                        else:
                            raise Exception(f"错误：无法比较{table_name}下的{name}，因为缺少必要的数据。")
                    except Exception as e:
                        formatted_error_message = log_error_with_timestamp(str(e))
                        with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
                            error_file.write(formatted_error_message)

    if output:
        output.sort(key=lambda x: x[1], reverse=True)
        output_file = '/Users/yanzhang/Documents/News/CompareStock.txt'
        with open(output_file, 'w') as file:
            for line in output:
                sector, company = line[0].rsplit(' ', 1)
                if company in earnings_companies:
                    company += '.*'
                file.write(f"{sector:<25}{company:<8}: {line[1]:>6.2f}%\n")
        print(f"{output_file} 已生成。")
    else:
        error_message = "输出为空，无法进行保存文件操作。"
        formatted_error_message = log_error_with_timestamp(error_message)
        with open('/Users/yanzhang/Documents/News/Today_error.txt', 'a') as error_file:
            error_file.write(formatted_error_message)

if __name__ == '__main__':
    config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    blacklist = ['VFS','KVYO','LU','IEP','LOT','GRFS','BGNE']
    interested_sectors = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
                          "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare", "Industrials",
                          "Real_Estate", "Technology", "Utilities"]
    file_path = '/Users/yanzhang/Documents/News/CompareStock.txt'
    directory_backup = '/Users/yanzhang/Documents/News/site/'
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
    compare_today_yesterday(config_path, blacklist)