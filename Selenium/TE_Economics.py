import sqlite3
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def fetch_data(driver, indicators, data_to_insert):
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    for key, value in indicators.items():
        try:
            element = driver.find_element(By.XPATH, f"//td[normalize-space(.)=\"{key}\"]/following-sibling::td")
            price = element.text
            if price.isdigit():
                price = float(price)
            data_to_insert.append((yesterday, value, price))
        except Exception as e:
            print(f"Error fetching data for {key}: {e}")
    return data_to_insert

def insert_data(conn, data):
    for entry in data:
        c = conn.cursor()
        c.execute('''SELECT price FROM Economics WHERE name = ? AND date < ? ORDER BY ABS(julianday(date) - julianday(?)) LIMIT 1''', 
                  (entry[1], entry[0], entry[0]))
        result = c.fetchone()
        if result and float(result[0]) == float(entry[2]):
            print(f"Data for {entry[1]} on {entry[0]} has the same price as the most recent entry. Skipping insert.")
        else:
            try:
                c.execute('INSERT INTO Economics (date, name, price) VALUES (?, ?, ?)', entry)
                conn.commit()
                print(f"[成功] 插入 {entry[0]} 的 {entry[1]} 数据 (价格: {entry[2]})")
            except sqlite3.IntegrityError as e:
                print(f"Data already exists and was not added. Error: {e}")

def setup_database(conn):
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Economics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        name TEXT,
        price REAL,
        UNIQUE(date, name)
    );''')
    conn.commit()

def navigate_to_section(driver, section_css, link_text):
    try:
        section_link = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, section_css))
        )
        section_link.click()
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.LINK_TEXT, link_text))
        )
        print(f"成功切换到 {section_css} 并找到 '{link_text}' 的链接，继续执行程序。")
    except TimeoutException:
        print(f"未能在页面上找到 '{link_text}' 的链接。")

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
service = Service(executable_path=chrome_driver_path)

with webdriver.Chrome(service=service) as driver:
    driver.get('https://tradingeconomics.com/united-states/indicators')
    Economics1 = {
        "GDP Growth Rate": "USGDP",
        "Non Farm Payrolls": "USNonFarm",
        "Inflation Rate": "USCPI",
        "Interest Rate": "USInterest",
        "Balance of Trade": "USTrade",
        "Consumer Confidence": "USConfidence",
        "Retail Sales MoM": "USRetailM",
        "Unemployment Rate": "USUnemploy",
        "Non Manufacturing PMI": "USNonPMI"
    }
    Economics2 = {
        "Initial Jobless Claims": "USInitial",
        "ADP Employment Change": "USNonFarmA",
    }
    Economics3 = {
        "Core PCE Price Index Annual Change": "CorePCEY",
        "Core PCE Price Index MoM": "CorePCEM",
        "Core Inflation Rate": "CoreCPI",
        "Producer Prices Change": "USPPI",
        "Core Producer Prices YoY": "CorePPI",
        "PCE Price Index Annual Change": "PCEY",
        "Import Prices MoM": "ImportPriceM",
        "Import Prices YoY": "ImportPriceY"
    }
    Economics4 = {
        "Real Consumer Spending": "USConspending"
    }
    data_to_insert = []
    data_to_insert = fetch_data(driver, Economics1, data_to_insert)
    navigate_to_section(driver, 'a[data-bs-target="#labour"]', "Manufacturing Payrolls")
    data_to_insert = fetch_data(driver, Economics2, data_to_insert)
    navigate_to_section(driver, 'a[data-bs-target="#prices"]', "Core Consumer Prices")
    data_to_insert = fetch_data(driver, Economics3, data_to_insert)
    navigate_to_section(driver, 'a[data-bs-target="#gdp"]', "GDP Constant Prices")
    data_to_insert = fetch_data(driver, Economics4, data_to_insert)

with sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db') as conn:
    setup_database(conn)
    insert_data(conn, data_to_insert)