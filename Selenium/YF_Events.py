import os
import tkinter as tk
from tkinter import messagebox
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# 文件路径
file_path = '/Users/yanzhang/Documents/News/Economic_Events_new.txt'

# 检查文件是否存在
if os.path.exists(file_path):
    # 创建一个Tkinter根窗口并隐藏
    root = tk.Tk()
    root.withdraw()
    
    # 弹窗通知用户
    messagebox.showinfo("文件存在", f"Economic_Events_new文件已存在，请先处理后再执行。")
    
    # 退出程序
    exit()

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 获取当前系统日期
current_date = datetime.now()
# 计算离当前最近的周天
start_date = current_date + timedelta(days=(6 - current_date.weekday()))
# 计算离当前最近的周六
end_date = start_date + timedelta(days=6)

Event_Filter = {
    "Initial Jobless Clm*", "GDP 2nd Estimate*",
    "Non-Farm Payrolls*", "Core PCE Price Index MM *",
    "Core PCE Price Index YY*", "ISM Manufacturing PMI",
    "ADP National Employment*", "International Trade $ *",
    "ISM N-Mfg PMI", "CPI YY, NSA*", "Core CPI MM, SA*",
    "CPI MM, SA*", "Core CPI YY, NSA*", "Fed Funds Tgt Rate *",
    "PPI Final Demand YY*", "PPI exFood/Energy MM*", "PPI ex Food/Energy/Tr MM*",
    "PPI Final Demand MM*", "Retail Sales MM *", "GDP Final*", "Core PCE Prices Fnal*"
}

# 定义一个包含所有目标国家代码的集合
target_countries = {
    "US"
}

# 初始化结果文件，使用追加模式
with open(file_path, 'a') as output_file:
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

                        if event in Event_Filter and country not in target_countries:
                            try:
                                event_time = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Event Time"]').text
                            except NoSuchElementException:
                                event_time = "No event time available"

                            entry = f"{formatted_change_date} : {event} [{country}]"
                            output_file.write(entry + "\n")
                    offset += 100  # 为下一个子页面增加 offset
                except TimeoutException:
                    print(f"No data found for date {formatted_change_date}. Skipping to next date.")
        change_date += delta

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