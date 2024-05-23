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

driver.get('https://tradingeconomics.com/united-states/indicators')

Economics1 = {
    "GDP Growth Rate": "USGDP",
    "Non Farm Payrolls": "USPayroll",
    "Inflation Rate": "USInflation",
    "Interest Rate": "USInterest",
    "Balance of Trade": "USTrade", 
    "Consumer Confidence": "USConfidence",
}

data_to_insert = []
now = datetime.now()
yesterday = now - timedelta(days=1)

for key in Economics1.keys():
    try:
        element = driver.find_element(By.XPATH, f"//td[normalize-space(.)=\"{key}\"]/following-sibling::td")
        price = element.text
        if price.isdigit():
            price = float(price)
        data_to_insert.append((yesterday.strftime('%Y-%m-%d'), Economics1[key], price))
    except Exception as e:
        print(f"Error fetching data for {key}: {e}")

labour_tab = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[data-bs-target="#labour"]'))
)

Economics2 = {
    "Initial Jobless Claims": "USJoblessClaim"
}

for key in Economics2.keys():
    try:
        element = driver.find_element(By.XPATH, f"//td[normalize-space(.)=\"{key}\"]/following-sibling::td")
        # element = driver.find_element(By.XPATH, f"//td[normalize-space(.)='{key}']/following-sibling::td[1]")
        price = element.text
        if price.isdigit():
            price = float(price)
        data_to_insert.append((yesterday.strftime('%Y-%m-%d'), Economics2[key], price))
    except Exception as e:
        print(f"Error fetching data for {key}: {e}")


# 点击“Labour”标签
labour_tab.click()

conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS Economics (
    date TEXT,
    name TEXT,
    price REAL,
    PRIMARY KEY (date, name)
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