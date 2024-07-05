from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import os
import json
import shutil
from selenium.webdriver.chrome.service import Service
import sqlite3
from datetime import datetime, timedelta

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

def create_connection(db_file):
    return sqlite3.connect(db_file)

def get_latest_four_dates(cursor, name):
    query = """
    SELECT date FROM ETFs
    WHERE name = ? 
    ORDER BY date DESC
    LIMIT 4
    """
    cursor.execute(query, (name,))
    return cursor.fetchall()

def get_prices_four_days(cursor, name, dates):
    query = """
    SELECT date, price FROM ETFs
    WHERE name = ? AND date IN (?, ?, ?, ?)
    ORDER BY date DESC
    """
    cursor.execute(query, (name, *dates))
    return cursor.fetchall()

def check_consecutive_rise(prices):
    if len(prices) < 3:
        return 0
    if prices[0][1] > prices[1][1] and prices[1][1] > prices[2][1]:
        if len(prices) == 4 and prices[2][1] > prices[3][1]:
            return 3
        return 2
    return 0

def fetch_data(url):
    driver.get(url)
    data_list = []

    # 找到所有的数据行
    rows = driver.find_elements(By.CSS_SELECTOR, 'tr.simpTblRow')
    
    for row in rows:
        # 在当前行中提取Symbol
        symbol_element = row.find_element(By.CSS_SELECTOR, 'a[data-test="quoteLink"]')
        symbol = symbol_element.text.strip()
        
        # 在当前行中提取Name
        name_element = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Name"]')
        name = name_element.text.strip()

        # 在当前行中提取Volume，并移除逗号以转换为整数
        volume_element = row.find_element(By.CSS_SELECTOR, 'fin-streamer[data-field="regularMarketVolume"]')
        volume = int(volume_element.get_attribute('value').replace(',', ''))

        data_list.append((symbol, name, volume))
    
    return data_list

def save_data(urls, existing_json, new_file, today_file, diff_file, db_path):
    # 读取a.json文件中的etfs的symbol字段
    with open(existing_json, 'r') as json_file:
        data = json.load(json_file)
        existing_symbols = {etf['symbol'] for etf in data['etfs']}

    # 创建数据库连接
    conn = create_connection(db_path)
    cursor = conn.cursor()

    # 收集新数据
    total_data_list = []
    filter_data_list = []
    for url in urls:
        data_list = fetch_data(url)
        for symbol, name, volume in data_list:
            if volume > 2000000:
                # 检查连续上涨
                dates = get_latest_four_dates(cursor, symbol)
                if dates:
                    prices = get_prices_four_days(cursor, symbol, [date[0] for date in dates])
                    consecutive_rise = check_consecutive_rise(prices)
                    rise_mark = '.++' if consecutive_rise == 3 else '.+' if consecutive_rise == 2 else ''
                else:
                    rise_mark = ''

                total_data_list.append(f"{symbol}{rise_mark}: {name}, {volume}")
                if symbol not in existing_symbols:
                    filter_data_list.append(f"{symbol}{rise_mark}: {name}, {volume}")
                    existing_symbols.add(symbol)

    # 写入新数据文件
    with open(new_file, "w") as file:
        for i, line in enumerate(filter_data_list):
            if i < len(filter_data_list) - 1:
                file.write(f"{line}\n")  # 非最后一行添加换行符
            else:
                file.write(line)  # 最后一行不添加任何后缀
    if not os.path.exists(today_file):
        # 如果today_file不存在，写入所有新数据
        with open(today_file, "w") as file:
            for i, line in enumerate(total_data_list):
                if i < len(total_data_list) - 1:
                    file.write(f"{line}\n")
                else:
                    file.write(line)
    else:
        # 如果today_file存在，比较并写入diff_file
        with open(today_file, "r") as file:
            existing_lines = file.readlines()
            existing_symbols_today = {line.split(":")[0].strip() for line in existing_lines}
        
        diff_data_list = [line for line in total_data_list if line.split(":")[0].strip() not in existing_symbols_today]

        with open(diff_file, "w") as file:
            for i, line in enumerate(diff_data_list):
                if i < len(diff_data_list) - 1:
                    file.write(f"{line}\n")
                else:
                    file.write(line)
        # 覆盖写入today_file
        with open(today_file, "w") as file:
            for i, line in enumerate(total_data_list):
                if i < len(total_data_list) - 1:
                    file.write(f"{line}\n")
                else:
                    file.write(line)

def backup_diff_file(diff_file, backup_dir):
    if os.path.exists(diff_file):
        # 获取当前时间戳
        timestamp = datetime.now().strftime('%Y%m%d')
        # 新的文件名
        new_filename = f"ETFs_diff_{timestamp}.txt"
        # 目标路径
        target_path = os.path.join(backup_dir, new_filename)
        # 移动文件
        shutil.move(diff_file, target_path)

# diff 文件路径
db_path = '/Users/yanzhang/Documents/Database/Finance.db'  # 添加数据库路径
diff_file = '/Users/yanzhang/Documents/News/ETFs_diff.txt'
backup_dir = '/Users/yanzhang/Documents/News/backup/backup'
backup_diff_file(diff_file, backup_dir)

# URL列表
urls = [
    "https://finance.yahoo.com/etfs/?offset=0&count=100",
    "https://finance.yahoo.com/etfs/?count=100&offset=100",
    "https://finance.yahoo.com/etfs/?count=100&offset=200",
    "https://finance.yahoo.com/etfs/?count=100&offset=300"
]
existing_json = '/Users/yanzhang/Documents/Financial_System/Modules/Description.json'
today_file = '/Users/yanzhang/Documents/News/site/ETFs_today.txt'
diff_file = '/Users/yanzhang/Documents/News/ETFs_diff.txt'
new_file = '/Users/yanzhang/Documents/News/ETFs_new.txt'

try:
    save_data(urls, existing_json, new_file, today_file, diff_file, db_path)
finally:
    driver.quit()
print("所有爬取任务完成。")