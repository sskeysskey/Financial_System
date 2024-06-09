from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
import json

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 加载JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as file:
    data = json.load(file)

# 获取当前日期和结束日期
# start_date = datetime(2024, 5, 27)
# end_date = datetime(2024, 8, 1)
start_date = datetime(2024, 6, 9)
end_date = datetime(2024, 6, 15)

# 文件路径
file_path = '/Users/yanzhang/Documents/News/Earnings_Release.txt'

# 在写入之前先读取文件中的现有内容，避免重复写入
existing_entries = set()
try:
    with open(file_path, 'r') as file:
        for line in file:
            existing_entries.add(line.strip())
except FileNotFoundError:
    # 如果文件不存在，则无需读取
    pass

# 初始化结果文件，使用追加模式
with open(file_path, 'a') as output_file:
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
                    if "Earnings Release" in event_name:
                        for category, symbols in data.items():
                            if symbol in symbols:
                                entry = f"{symbol}:{formatted_change_date}-{call_time}"
                                if entry not in existing_entries:
                                    output_file.write(entry + "\n")
                                    existing_entries.add(entry)
                offset += 100  # 为下一个子页面增加 offset
        
        change_date += delta  # 日期增加一天

# 关闭浏览器
driver.quit()