import os
import tkinter as tk
from tkinter import messagebox
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
import json

# 文件路径
file_path = '/Users/yanzhang/Documents/News/Stock_Splits_new.txt'

# 检查文件是否存在
if os.path.exists(file_path):
    # 创建一个Tkinter根窗口并隐藏
    root = tk.Tk()
    root.withdraw()
    
    # 弹窗通知用户
    messagebox.showinfo("文件存在", f"Stock_Splits_new文件已存在，请先处理后再执行。")
    
    # 退出程序
    exit()

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 加载JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as file:
    data = json.load(file)

# 获取当前系统日期
current_date = datetime.now()
# 计算离当前最近的周天
start_date = current_date + timedelta(days=(6 - current_date.weekday()))
# 计算离当前最近的周六
end_date = start_date + timedelta(days=6)

# 初始化结果文件，使用追加模式
with open(file_path, 'a') as output_file:
    change_date = start_date
    delta = timedelta(days=1)
    
    while change_date <= end_date:
        formatted_change_date = change_date.strftime('%Y-%m-%d')
        offset = 0
        has_data = True
        
        while has_data:
            url = f"https://finance.yahoo.com/calendar/splits?from={start_date.strftime('%Y-%m-%d')}&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100"
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
                    company = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Company"]').text
                    
                    for category, symbols in data.items():
                        if symbol in symbols:
                            entry = f"{symbol}: {formatted_change_date} - {company}"
                            output_file.write(entry + "\n")
                                
                offset += 100  # 为下一个子页面增加 offset
        change_date += delta  # 日期增加一天

# 关闭浏览器
driver.quit()