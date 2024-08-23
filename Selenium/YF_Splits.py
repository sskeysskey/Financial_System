import os
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
import subprocess
import json

# 文件路径
file_path = '/Users/yanzhang/Documents/News/Stock_Splits_new.txt'

# 检查文件是否存在
if os.path.exists(file_path):
    # 弹窗通知用户
    applescript_code = 'display dialog "Stock_Splits_new文件已存在，请先处理后再执行。" buttons {"OK"} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)
    exit()

# ChromeDriver 设置
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 加载JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as file:
    data = json.load(file)

# start_date = datetime(2024, 6, 30)
# end_date = datetime(2024, 7, 6)

# 获取当前系统日期
current_date = datetime.now()
# 计算离当前最近的周天
start_date = current_date + timedelta(days=(6 - current_date.weekday()))
# 计算往后延6天的周六
end_date = start_date + timedelta(days=6)

# 用于存储结果的列表
results = []

change_date = start_date
delta = timedelta(days=1)

while change_date <= end_date:
    formatted_change_date = change_date.strftime('%Y-%m-%d')
    offset = 0
    has_data = True
    
    while has_data:
        url = f"https://finance.yahoo.com/calendar/splits?from={start_date.strftime('%Y-%m-%d')}&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100"
        driver.get(url)
        
        try:
            rows = WebDriverWait(driver, 4).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr.simpTblRow")))
        except TimeoutException:
            has_data = False
            continue
        
        for row in rows:
            symbol = row.find_element(By.CSS_SELECTOR, 'a[data-test="quoteLink"]').text
            company = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Company"]').text
            
            for category, symbols in data.items():
                if symbol in symbols:
                    results.append(f"{symbol}: {formatted_change_date} - {company}")
                    break
        
        offset += 100
    
    change_date += delta

# 关闭浏览器
driver.quit()

# 只有在有结果时才创建文件
if results:
    with open(file_path, 'w') as output_file:
        for result in results:
            output_file.write(result + "\n")
    print(f"已成功创建文件 {file_path} 并写入 {len(results)} 条记录。")
else:
    print("没有找到符合条件的数据，未创建文件。")