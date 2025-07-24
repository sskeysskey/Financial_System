import os
import json
import sqlite3
import shutil
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
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
            print(f"鼠标移动出错: {e}")
            time.sleep(30)

# 在主程序开始前启动鼠标移动线程
mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
mouse_thread.start()

# 文件路径
file_path = '/Users/yanzhang/Documents/News/Earnings_Release_next.txt'
backup_dir = '/Users/yanzhang/Documents/News/backup/backup'
# 1. 先加载已有的 Earnings_Release.txt，把 (symbol, date) 存到一个 set 里
earnings_release_path = '/Users/yanzhang/Documents/News/backup/Earnings_Release.txt'

# 1. 加载主发行日文件，记录已存在的 (symbol, date)
existing_release_entries = set()
if os.path.exists(earnings_release_path):
    with open(earnings_release_path, 'r') as f:
        for line in f:
            parts = line.strip().split(':')
            if len(parts) >= 2:
                sym = parts[0].strip()
                date = parts[1].strip()
                existing_release_entries.add((sym, date))

# 2. 如果 next.txt 已存在，先备份
file_already_exists = os.path.exists(file_path)

# 如果文件存在，进行备份
if file_already_exists:
    timestamp = datetime.now().strftime('%y%m%d')
    backup_filename = f'Earnings_Release_next_{timestamp}.txt'
    backup_path = os.path.join(backup_dir, backup_filename)
    
    # 确保备份目录存在
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(file_path, os.path.join(backup_dir, backup_filename))

# 3. 读取 next.txt 已有的三元组 (symbol, call_time, date)
existing_next_entries = set()
if file_already_exists:
    with open(file_path, 'r') as f:
        for line in f:
            parts = line.strip().split(':')
            if len(parts) >= 3:
                sym = parts[0].strip()
                call_time = parts[1].strip()
                date = parts[2].strip()
                existing_next_entries.add((sym, call_time, date))

# Selenium + Chrome 配置
chrome_options = Options()
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

# 加载行业 JSON
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as f:
    data = json.load(f)

# 时间区间
start_date = datetime(2025, 7, 28)
end_date   = datetime(2025, 8, 3)

# # 获取当前系统日期
# current_date = datetime.now()
# # 计算离当前最近的周天
# start_date = current_date + timedelta(days=(6 - current_date.weekday()))
# # 计算往后延6天的周六
# end_date = start_date + timedelta(days=6)

# 初始化数据库连接
db_path = '/Users/yanzhang/Documents/Database/Finance.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

new_content_added = False

# 使用追加模式打开文件
with open(file_path, 'a') as output_file:
    # output_file.write('\n')
    change_date = start_date
    delta = timedelta(days=1)

    while change_date <= end_date:
        formatted_change_date = change_date.strftime('%Y-%m-%d')
        offset = 0
        has_data = True

        while has_data:
            url = (
                f"https://finance.yahoo.com/calendar/earnings"
                f"?from={start_date.strftime('%Y-%m-%d')}"
                f"&to={end_date.strftime('%Y-%m-%d')}"
                f"&day={formatted_change_date}"
                f"&offset={offset}&size=100"
            )
            driver.get(url)
            
            # 使用显式等待确保元素加载
            wait = WebDriverWait(driver, 4)
            try:
                # 首先定位到表格，然后找到表格体中的所有行
                table = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
                rows = table.find_elements(By.CSS_SELECTOR, "tbody > tr")
            except TimeoutException:
                rows = []  # 如果超时，则设置 rows 为空列表
            
            if not rows:
                has_data = False
            else:
                for row in rows:
                    try:
                        symbol = row.find_element(By.CSS_SELECTOR, 'a[title][href*="/quote/"]').get_attribute('title')
                        cells = row.find_elements(By.TAG_NAME, 'td')
                        if len(cells) < 4:
                            continue
                        event_name = cells[2].text.strip()
                        call_time  = cells[3].text.strip() or "N/A"

                        # 只要含有下列关键词之一
                        if not any(k in event_name for k in
                                   ["Earnings Release", "Shareholders Meeting", "Earnings Announcement"]):
                            continue

                        # --- 新增：在写入前进行日期过滤 ---
                        event_date_obj = datetime.strptime(formatted_change_date, '%Y-%m-%d')
                        if event_date_obj < start_date or event_date_obj > end_date:
                            # 日期超出范围，跳过这一行
                            continue
                        # --- 新增结束 ---

                        # 检查是否在行业列表里
                        for category, symbols in data.items():
                            if symbol in symbols:
                                key_main = (symbol, formatted_change_date)
                                key_next = (symbol, call_time, formatted_change_date)

                                # 1) 如果主发行日文件已经有 (symbol, date)，跳过
                                # 2) 如果 next.txt 已经有完全一致的三元组，也跳过
                                if key_main in existing_release_entries or key_next in existing_next_entries:
                                    break

                                # 否则追加
                                entry = f"{symbol:<7}: {call_time:<4}: {formatted_change_date}"
                                output_file.write(entry + "\n")
                                new_content_added = True
                                existing_next_entries.add(key_next)
                                break  # 找到所属 category 即可，不再在其它 category 中重复写

                    except Exception as e:
                        print(f"处理行数据时出错: {e}")
                        continue

                offset += 100

        change_date += delta

# 清理
conn.close()
driver.quit()