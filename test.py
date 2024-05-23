import sqlite3
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 访问目标网页
driver.get('https://tradingeconomics.com/united-states/indicators')

# 定位到“Labour”链接并点击
# 使用WebDriverWait和expected_conditions等待元素可点击
labour_link = WebDriverWait(driver, 15).until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[data-bs-target="#labour"]'))
)
labour_link.click()

try:
    # 使用WebDriverWait和expected_conditions检查“Manufacturing Payrolls”链接是否可见
    manufacturing_payrolls_link = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.LINK_TEXT, "Manufacturing Payrolls"))
    )

    print("找到了 'Manufacturing Payrolls' 链接，继续执行程序。")
    # 这里可以继续添加你需要执行的代码，比如点击链接等
    # manufacturing_payrolls_link.click()

except TimeoutException:
    # 如果在指定时间内没有找到链接，打印错误信息
    print("未能在页面上找到 'Manufacturing Payrolls' 链接。")

Economics = {
"Initial Jobless Claims": "USJobless"
}

data_to_insert = []
now = datetime.now()
yesterday = now - timedelta(days=1)

for key in Economics.keys():
    try:
        element = driver.find_element(By.XPATH, f"//td[normalize-space(.)=\"{key}\"]/following-sibling::td")
        price = element.text
        if price.isdigit():
            price = float(price)
        data_to_insert.append((yesterday.strftime('%Y-%m-%d'), Economics[key], price))
    except Exception as e:
        print(f"Error fetching data for {key}: {e}")

conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Analysis.db')
c = conn.cursor()

c.execute('''CREATE TABLE  IF NOT EXISTS  Economics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    name TEXT,
    price REAL,
    UNIQUE(date, name)
);''')

for entry in data_to_insert:
    # 查询数据库中同一name且最接近日期的价格
    c.execute('''SELECT price FROM Economics WHERE name = ? AND date < ? 
                 ORDER BY ABS(julianday(date) - julianday(?)) LIMIT 1''', (entry[1], entry[0], entry[0]))
    result = c.fetchone()
    if result and float(result[0]) == float(entry[2]):
        print(f"Data for {entry[1]} on {entry[0]} has the same price as the most recent entry. Skipping insert.")
    else:
        try:
            c.execute('INSERT INTO Economics (date, name, price) VALUES (?, ?, ?)', entry)
            conn.commit()
        except sqlite3.IntegrityError as e:
            print(f"Data already exists and was not added. Error: {e}")

conn.close()
driver.quit()