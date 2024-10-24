from selenium import webdriver
from selenium.webdriver.common.by import By
import os
import json
import shutil
from selenium.webdriver.chrome.service import Service
from datetime import datetime, timedelta
import pyautogui
import random
import time
import threading

# 添加鼠标移动功能的函数
def move_mouse_periodically():
    while True:
        try:
            # 获取屏幕尺寸
            screen_width, screen_height = pyautogui.size()
            
            # 随机生成目标位置，避免移动到屏幕边缘
            x = random.randint(100, screen_width - 100)
            y = random.randint(100, screen_height - 100)
            
            # 缓慢移动鼠标到随机位置
            pyautogui.moveTo(x, y, duration=1)
            
            # 等待30-60秒再次移动
            time.sleep(random.randint(30, 60))
            
        except Exception as e:
            print(f"鼠标移动出错: {str(e)}")
            time.sleep(30)

# 在主程序开始前启动鼠标移动线程
mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
mouse_thread.start()

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

def fetch_data(url):
    driver.get(url)
    data_list = []

    # 找到所有的数据行
    rows = driver.find_elements(By.CSS_SELECTOR, 'tr.row.false.yf-1dbt8wv')
    
    for row in rows:
        # 在当前行中提取Symbol
        symbol_element = row.find_element(By.CSS_SELECTOR, 'span.symbol.yf-138ga19')
        symbol = symbol_element.text.strip()
        
        # 在当前行中提取Name
        name_element = row.find_element(By.CSS_SELECTOR, 'span.yf-138ga19.longName')
        name = name_element.text.strip()

        # 在当前行中提取Volume，并移除逗号以转换为整数
        volume_element = row.find_element(By.CSS_SELECTOR, 'fin-streamer[data-field="regularMarketVolume"]')
        volume = int(volume_element.get_attribute('data-value').replace(',', ''))

        data_list.append((symbol, name, volume))
    
    return data_list

def load_compare_data(compare_file):
    compare_data = {}
    with open(compare_file, 'r') as file:
        for line in file:
            parts = line.split(':')
            if len(parts) == 2:
                symbol, percentage = parts[0].strip(), parts[1].strip()
                compare_data[symbol] = percentage
    return compare_data

def save_data(urls, existing_json, new_file, today_file, diff_file, compare_file):
    # 首先访问Yahoo Finance主页
    driver.get("https://finance.yahoo.com/markets/etfs/top/")
    # 等待2秒
    time.sleep(2)
    
    # 读取a.json文件中的etfs的symbol字段
    with open(existing_json, 'r') as json_file:
        data = json.load(json_file)
        existing_symbols = {etf['symbol'] for etf in data['etfs']}
    
    # 读取compare_all.txt文件中的百分比数据
    compare_data = load_compare_data(compare_file)
    
    # 收集新数据
    total_data_list = []
    filter_data_list = []
    for url in urls:
        data_list = fetch_data(url)
        for symbol, name, volume in data_list:
            if volume > 200000:
                total_data_list.append(f"{symbol}: {name}, {volume}")
                if symbol not in existing_symbols:
                    filter_data_list.append(f"{symbol}: {name}, {volume}")
                    existing_symbols.add(symbol)

    # 写入新数据文件（仅在filter_data_list不为空时）
    if filter_data_list:
        with open(new_file, "w") as file:
            for i, line in enumerate(filter_data_list):
                if i < len(filter_data_list) - 1:
                    file.write(f"{line}\n")  # 非最后一行添加换行符
                else:
                    file.write(line)  # 最后一行不添加任何后缀

    # 获取昨天的日期
    yesterday = (datetime.now() - timedelta(1)).strftime('%m%d')

    if os.path.exists(today_file):
        # 备份今天的文件
        backup_today_file = f"/Users/yanzhang/Documents/News/site/ETFs_today_{yesterday}.txt"
        shutil.copy2(today_file, backup_today_file)

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
        
        diff_data_list = []
        for line in total_data_list:
            symbol = line.split(":")[0].strip()
            if symbol not in existing_symbols_today:
                percentage = compare_data.get(symbol, "")
                if percentage:
                    line = f"{symbol:<7} {percentage if percentage else '':<10}: {line.split(':', 1)[1]}"
                diff_data_list.append(line)

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
        timestamp = datetime.now().strftime('%y%m%d')
        # 新的文件名
        new_filename = f"ETFs_diff_{timestamp}.txt"
        # 目标路径
        target_path = os.path.join(backup_dir, new_filename)
        # 移动文件
        shutil.move(diff_file, target_path)

def clean_old_backups(directory, prefix="ETFs_today_", days=4):
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

# diff 文件路径
diff_file = '/Users/yanzhang/Documents/News/ETFs_diff.txt'
backup_dir = '/Users/yanzhang/Documents/News/backup/backup'
backup_diff_file(diff_file, backup_dir)

# URL列表
urls = [
    "https://finance.yahoo.com/markets/etfs/top/?start=0&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=100&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=200&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=300&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=400&count=100"
]
existing_json = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'
today_file = '/Users/yanzhang/Documents/News/site/ETFs_today.txt'
diff_file = '/Users/yanzhang/Documents/News/ETFs_diff.txt'
new_file = '/Users/yanzhang/Documents/News/ETFs_new.txt'
compare_file = '/Users/yanzhang/Documents/News/backup/Compare_All.txt'

try:
    save_data(urls, existing_json, new_file, today_file, diff_file, compare_file)
finally:
    driver.quit()
print("所有爬取任务完成。")

# 调用清理旧备份文件的函数
directory_backup = '/Users/yanzhang/Documents/News/site/'
clean_old_backups(directory_backup)