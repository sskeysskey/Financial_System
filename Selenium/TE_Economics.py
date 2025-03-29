import sqlite3
import subprocess
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options  # 添加这行导入

def fetch_data(driver, indicators, data_to_insert):
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    for key, value in indicators.items():
        try:
            element = driver.find_element(By.XPATH, f"//td[normalize-space(.)=\"{key}\"]/following-sibling::td")
            price_str = element.text.strip()  # 去除首尾空白
            if not price_str:
                print(f"指标 {key} 没有数据，跳过。")
                continue
            
            # 尝试将数字中的逗号去掉后转换为浮点数
            try:
                price = float(price_str.replace(',', ''))
            except ValueError:
                print(f"指标 {key} 数值 '{price_str}' 转换为浮点数失败，跳过。")
                continue

            data_to_insert.append((yesterday, value, price))
        except Exception as e:
            print(f"获取 {key} 数据时出现错误: {e}")
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
    except Exception as e:
        print(f"未能在页面上找到 '{link_text}' 的链接。错误：{e}")

def display_dialog(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def check_day():
    """检查当前日期是否为周日或周一"""
    return datetime.now().weekday() in [6, 0]  # 6 代表周日，0 代表周一

def main():
    if check_day():
        message = "今天不是周日或周一，不执行更新操作。"
        display_dialog(message)
        return

    # 设置Chrome选项以提高性能
    chrome_options = Options()
    chrome_options.add_argument("--disable-extensions")  # 禁用扩展
    chrome_options.add_argument("--disable-gpu")  # 禁用GPU加速
    chrome_options.add_argument("--disable-dev-shm-usage")  # 禁用/dev/shm使用
    chrome_options.add_argument("--no-sandbox")  # 禁用沙箱
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
    chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

    # 设置ChromeDriver路径和服务
    chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
    service = Service(executable_path=chrome_driver_path)

    # 使用优化后的选项创建driver
    with webdriver.Chrome(service=service, options=chrome_options) as driver:
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

if __name__ == "__main__":
    main()