import os
import shutil
import subprocess
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, TimeoutException
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
file_path = '/Users/yanzhang/Documents/News/Economic_Events_next.txt'
backup_dir = '/Users/yanzhang/Documents/News/backup/backup'

# 检查原始文件是否存在
original_file_exists = os.path.exists(file_path)

# 如果原始文件存在，进行备份
if original_file_exists:
    timestamp = datetime.now().strftime('%y%m%d')
    backup_filename = f'Economic_Events_next_{timestamp}.txt'
    backup_path = os.path.join(backup_dir, backup_filename)
    
    # 确保备份目录存在
    os.makedirs(backup_dir, exist_ok=True)
    
    # 复制文件到备份目录
    shutil.copy2(file_path, backup_path)

    # 读取原有内容
    with open(file_path, 'r') as file:
        existing_content = set(file.read().splitlines())
else:
    existing_content = set()

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# start_date = datetime(2024, 9, 8)
# end_date = datetime(2024, 9, 14)

# 获取当前系统日期
current_date = datetime.now()
# 计算离当前最近的周天
start_date = current_date + timedelta(days=(6 - current_date.weekday()))
# 计算往后延6天的周六
end_date = start_date + timedelta(days=6)

Event_Filter = {
    "GDP 2nd Estimate*", "Non-Farm Payrolls*", "Core PCE Price Index MM *",
    "Core PCE Price Index YY*", "ISM Manufacturing PMI",
    "ADP National Employment*", "International Trade $ *",
    "ISM N-Mfg PMI", "CPI YY, NSA*", "Core CPI MM, SA*",
    "CPI MM, SA*", "Core CPI YY, NSA*", "Fed Funds Tgt Rate *",
    "PPI Final Demand YY*", "PPI exFood/Energy MM*", "PPI ex Food/Energy/Tr MM*",
    "PPI Final Demand MM*", "Retail Sales MM *", "GDP Final*", "Core PCE Prices Fnal*",
    "PCE Prices Final *", "GDP Cons Spending Final*", "Pending Homes Index",
    "PCE Price Index MM*", "Unemployment Rate*", "ISM N-Mfg PMI",
    "U Mich Sentiment Prelim", "New Home Sales-Units *", "New Home Sales Chg MM *",
    "GDP Cons Spending Prelim*", "Core PCE Prices Prelim*",
    "Corporate Profits Prelim*", "Initial Jobless Clm*", "U Mich Sentiment Final"
}

# 定义一个包含所有目标国家代码的集合
target_countries = {
    "US"
}

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
            url = f"https://finance.yahoo.com/calendar/economic?from={start_date.strftime('%Y-%m-%d')}&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100"
            driver.get(url)
            
            wait = WebDriverWait(driver, 4)
            try:
                rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr.simpTblRow")))
            except TimeoutException:
                rows = []  # 如果超时，则设置 rows 为空列表
            
            if not rows:
                has_data = False
            else:
                try:
                    for row in rows:
                        event = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Event"]').text
                        country = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Country"]').text

                        if event in Event_Filter and country in target_countries:
                            try:
                                event_time = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Event Time"]').text
                            except NoSuchElementException:
                                event_time = "No event time available"

                            entry = f"{formatted_change_date} : {event} [{country}]"
                            if entry not in existing_content:
                                output_file.write(entry + "\n")
                                new_content_added = True
                    offset += 100   # 为下一个子页面增加 offset
                except TimeoutException:
                    print(f"No data found for date {formatted_change_date}. Skipping to next date.")
        change_date += delta

# 关闭浏览器
driver.quit()

# 只有当原始文件存在且有新内容添加时才显示弹窗
if original_file_exists and new_content_added:
    applescript_code = 'display dialog "新内容已添加。" buttons {"OK"} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)