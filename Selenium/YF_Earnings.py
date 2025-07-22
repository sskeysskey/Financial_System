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
            print(f"鼠标移动出错: {str(e)}")
            time.sleep(30)

# 在主程序开始前启动鼠标移动线程
mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
mouse_thread.start()

# 文件路径
file_path = '/Users/yanzhang/Documents/News/Earnings_Release_next.txt'
backup_dir = '/Users/yanzhang/Documents/News/backup/backup'
# 1. 先加载已有的 Earnings_Release.txt，把 (symbol, date) 存到一个 set 里
earnings_release_path = '/Users/yanzhang/Documents/News/backup/Earnings_Release.txt'

existing_release_entries = set()
if os.path.exists(earnings_release_path):
    with open(earnings_release_path, 'r') as f:
        for line in f:
            parts = line.strip().split(':')
            if len(parts) >= 2:
                sym = parts[0].strip()
                date = parts[1].strip()
                existing_release_entries.add((sym, date))

# 检查文件是否已经存在
file_already_exists = os.path.exists(file_path)

# 如果文件存在，进行备份
if file_already_exists:
    timestamp = datetime.now().strftime('%y%m%d')
    backup_filename = f'Earnings_Release_next_{timestamp}.txt'
    backup_path = os.path.join(backup_dir, backup_filename)
    
    # 确保备份目录存在
    os.makedirs(backup_dir, exist_ok=True)
    
    # 复制文件到备份目录
    shutil.copy2(file_path, backup_path)

# 读取原有内容（如果文件存在）
existing_content = set()
if file_already_exists:
    with open(file_path, 'r') as file:
        for line in file:
            # 只取第一个冒号之前的部分作为键
            stock_symbol = line.split(':')[0].strip()
            existing_content.add(stock_symbol)

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

# 加载JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as file:
    data = json.load(file)

start_date = datetime(2025, 7, 20)
end_date = datetime(2025, 7, 26)

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
            url = f"https://finance.yahoo.com/calendar/earnings?from={start_date.strftime('%Y-%m-%d')}&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100"
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
                        # 检查单元格数量是否足够，我们需要至少4个单元格来获取时间和事件名称
                        if len(cells) >= 4:
                            event_name = cells[2].text.strip()
                            # "Earnings Call Time" 在第四个单元格 (索引为3)
                            call_time = cells[3].text.strip()
                            # 如果 call_time 为空，则给一个默认的占位符
                            if not call_time or call_time == '-':
                                call_time = "N/A"
                        else:
                            # 如果单元格不够，则无法获取所需信息，跳过此行
                            continue

                        # --- 新增：在写入前进行日期过滤 ---
                        event_date_obj = datetime.strptime(formatted_change_date, '%Y-%m-%d')
                        if event_date_obj < start_date or event_date_obj > end_date:
                            # 日期超出范围，跳过这一行
                            continue
                        # --- 新增结束 ---

                        if "Earnings Release" in event_name or "Shareholders Meeting" in event_name or "Earnings Announcement" in event_name:
                            for category, symbols in data.items():
                                if symbol in symbols:
                                    # 构建新的输出格式: "SYMBOL   BMO: YYYY-MM-DD"
                                    # 使用 f-string 和对齐来格式化输出
                                    entry = f"{symbol:<7}: {call_time:<4}: {formatted_change_date}"
                                    key = (symbol, formatted_change_date)
                                    
                                    if symbol not in existing_content and key not in existing_release_entries:
                                        output_file.write(entry + "\n")
                                        new_content_added = True
                                        # 将新添加的symbol也加入到集合中，防止在同一次运行中重复添加
                                        existing_content.add(symbol)
                        # --- 修改结束 ---
                                        
                    except Exception as e:
                        # 捕获处理单行时可能出现的错误，避免整个循环中断
                        print(f"处理行数据时出错: {e}, Symbol: {symbol if 'symbol' in locals() else 'N/A'}")
                        continue

                offset += 100
        change_date += delta

# 关闭数据库连接
conn.close()

# 关闭浏览器
driver.quit()