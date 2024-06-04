from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 获取当前日期和结束日期
start_date = datetime(2024, 5, 28)
end_date = datetime(2024, 5, 30)

# 文件路径
file_path = '/Users/yanzhang/Documents/News/backup/Economic_Events.txt'

Event_Filter = [
    "Initial Jobless Clm*", "GDP 2nd Estimate*",
    "Non-Farm Payrolls*", "Core PCE Price Index MM *",
    "Core PCE Price Index YY*", "ISM Manufacturing PMI"
]

# 在写入之前先读取文件中的现有内容，避免重复写入
existing_entries = set()
try:
    with open(file_path, 'r') as file:
        for line in file:
            existing_entries.add(line.strip())
except FileNotFoundError:
    pass

# 初始化结果文件，使用追加模式
with open(file_path, 'a') as output_file:
    change_date = start_date
    delta = timedelta(days=1)
    
    while change_date <= end_date:
        formatted_change_date = change_date.strftime('%Y-%m-%d')
        url = f"https://finance.yahoo.com/calendar/economic?from={start_date.strftime('%Y-%m-%d')}&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}"
        driver.get(url)
        
        wait = WebDriverWait(driver, 2)
        try:
            rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr.simpTblRow")))
            for row in rows:
                event = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Event"]').text
                if event in Event_Filter:
                    try:
                        event_time = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Event Time"]').text
                    except NoSuchElementException:
                        event_time = "No event time available"

                    entry = f"{event}:{formatted_change_date}-{event_time}"
                    if entry not in existing_entries:
                        output_file.write(entry + "\n")
                        existing_entries.add(entry)
        except TimeoutException:
            print(f"No data found for date {formatted_change_date}. Skipping to next date.")
        change_date += delta

# 关闭浏览器
driver.quit()