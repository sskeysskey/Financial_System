import os
import json
import sqlite3
import shutil
import subprocess
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
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

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 加载JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as file:
    data = json.load(file)

# 加载颜色关键词JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/colors.json', 'r') as file:
    color_data = json.load(file)

# 定义颜色分组与后缀的映射关系
color_suffix_map = {
    "white_keywords": "W",
    "yellow_keywords": "Y",
    "orange_keywords": "O",
    "purple_keywords": "P",
    "black_keywords": "B",
    "blue_keywords": "b",
    "green_keywords": "G",
    "cyan_keywords": "C"  # 假设有 cyan 分组
}

# 将所有颜色关键词整合到一个集合中，排除red_keywords组别
color_keys = set()
for key, symbols in color_data.items():
    if key != "red_keywords":
        color_keys.update(symbols)

# start_date = datetime(2024, 12, 2)
# end_date = datetime(2024, 12, 9)

# 获取当前系统日期
current_date = datetime.now()
# 计算离当前最近的周天
start_date = current_date + timedelta(days=(6 - current_date.weekday()))
# 计算往后延6天的周六
end_date = start_date + timedelta(days=6)

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
                # 等待表格主体加载
                rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr.row.yf-2twxe2")))
                
                # 首先定位到表格，然后找到表格体中的所有行
                # table = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
                # rows = table.find_elements(By.CSS_SELECTOR, "tbody > tr")
            except TimeoutException:
                rows = []  # 如果超时，则设置 rows 为空列表
            
            if not rows:
                has_data = False
            else:
                for row in rows:
                    symbol = row.find_element(By.CSS_SELECTOR, 'a.loud-link[title]').get_attribute('title')
                    # symbol = row.find_element(By.CSS_SELECTOR, 'a[title][href*="/quote/"]').get_attribute('title')
                    event_name = row.find_element(By.CSS_SELECTOR, 'td.tw-text-left.tw-max-w-xs:not(.tw-whitespace-normal)').text.strip()

                    # cells = row.find_elements(By.TAG_NAME, 'td')
                    # # 假设事件名称在第三个单元格（索引2）
                    # if len(cells) >= 3:
                    #     event_name = cells[2].text.strip()
                    # else:
                    #     continue
                    
                    if "Earnings Release" in event_name or "Shareholders Meeting" in event_name:
                        for category, symbols in data.items():
                            if symbol in symbols:
                                # 查询数据库获取交易量
                                cursor.execute(f"SELECT volume FROM {category} WHERE name = ? ORDER BY date DESC LIMIT 1", (symbol,))
                                volume_row = cursor.fetchone()
                                volume = volume_row[0] if volume_row else "No volume data"
                                
                                original_symbol = symbol  # 保留原始公司名称

                                # 检查颜色关键词并根据所在分组添加后缀
                                suffix = ""
                                for color_group, group_symbols in color_data.items():
                                    if symbol in group_symbols and color_group != "red_keywords":
                                        suffix = color_suffix_map.get(color_group, "")
                                        break
                                
                                if suffix:
                                    symbol += f":{suffix}"

                                entry = f"{symbol:<7}: {volume:<10}: {formatted_change_date}"
                                if original_symbol not in existing_content:
                                    output_file.write(entry + "\n")
                                    new_content_added = True
                                
                offset += 100  # 为下一个子页面增加 offset
        change_date += delta  # 日期增加一天

# 关闭数据库连接
conn.close()

# 关闭浏览器
driver.quit()

# 如果有新内容添加，并且文件原本已经存在，显示提示
if new_content_added and file_already_exists:
    applescript_code = 'display dialog "新内容已添加。" buttons {"OK"} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)