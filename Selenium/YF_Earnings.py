import os
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
import json

# 文件路径
file_path = '/Users/yanzhang/Documents/News/Earnings_Release_next.txt'
backup_dir = '/Users/yanzhang/Documents/News/backup/backup'

# 如果文件存在，进行备份
if os.path.exists(file_path):
    timestamp = datetime.now().strftime('%y%m%d')
    backup_filename = f'Earnings_Release_next_{timestamp}.txt'
    backup_path = os.path.join(backup_dir, backup_filename)
    
    # 确保备份目录存在
    os.makedirs(backup_dir, exist_ok=True)
    
    # 复制文件到备份目录
    shutil.copy2(file_path, backup_path)

# 读取原有内容（如果文件存在）
existing_content = set()
if os.path.exists(file_path):
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

# 将所有颜色关键词整合到一个集合中，排除red_keywords组别
color_keys = set()
for key, symbols in color_data.items():
    if key != "red_keywords":
        color_keys.update(symbols)

# start_date = datetime(2024, 9, 8)
# end_date = datetime(2024, 9, 14)

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
    output_file.write('\n')
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
                rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr.simpTblRow")))
            except TimeoutException:
                rows = []  # 如果超时，则设置 rows 为空列表
            
            if not rows:
                has_data = False
            else:
                for row in rows:
                    symbol = row.find_element(By.CSS_SELECTOR, 'a[data-test="quoteLink"]').text
                    event_name = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Event Name"]').text
                    try:
                        call_time = row.find_element(By.XPATH, './/td[contains(@aria-label, "Earnings Call Time")]/span').text
                    except NoSuchElementException:
                        call_time = "No call time available"
                    if "Earnings Release" in event_name or "Shareholders Meeting" in event_name:
                        for category, symbols in data.items():
                            if symbol in symbols:
                                # 查询数据库获取交易量
                                cursor.execute(f"SELECT volume FROM {category} WHERE name = ? ORDER BY date DESC LIMIT 1", (symbol,))
                                volume_row = cursor.fetchone()
                                volume = volume_row[0] if volume_row else "No volume data"
                                
                                original_symbol = symbol  # 保留原始公司名称
                                # 检查颜色关键词
                                if symbol in color_keys:
                                    symbol += ":L"
                                entry = f"{symbol:<7}: {volume:<10}: {formatted_change_date} - {call_time}"
                                if original_symbol not in existing_content:
                                    output_file.write(entry + "\n")
                                    new_content_added = True
                                
                offset += 100  # 为下一个子页面增加 offset
        change_date += delta  # 日期增加一天

# 关闭数据库连接
conn.close()

# 关闭浏览器
driver.quit()

# 移除最后一行的回车换行符
with open(file_path, 'r') as file:
    lines = file.readlines()

# 去掉最后一行的换行符
if lines and lines[-1].endswith("\n"):
    lines[-1] = lines[-1].rstrip("\n")

# 重新写回文件
with open(file_path, 'w') as file:
    file.writelines(lines)

# 如果有新内容添加，显示提示
if new_content_added:
    applescript_code = 'display dialog "新内容已添加。" buttons {"OK"} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)