from selenium import webdriver
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import sqlite3
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ChromeDriver 路径
CHROME_DRIVER_PATH = "/Users/yanzhang/Downloads/backup/chromedriver"
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'

def setup_driver():
    # 设置Chrome选项以提高性能
    chrome_options = Options()
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
    chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始
    
    service = Service(executable_path=CHROME_DRIVER_PATH)
    return webdriver.Chrome(service=service, options=chrome_options)

def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Bonds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        name TEXT,
        price REAL,
        UNIQUE(date, name)
    );
    ''')
    conn.commit()
    return conn, cursor

def fetch_bond_data(driver, bond_name, xpath='./ancestor::tr'):
    element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.LINK_TEXT, bond_name))
    )
    row = element.find_element(By.XPATH, xpath)
    return row.find_element(By.ID, 'p').text.strip()

def main():
    now = datetime.now()
    if now.weekday() in (0, 6):
        logging.info("Today is either Sunday or Monday. The script will not run.")
        return

    driver = setup_driver()
    conn, cursor = setup_database()

    try:
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        all_data = []

        # US Bond data
        driver.get('https://tradingeconomics.com/united-states/government-bond-yield')
        us_bonds = ["US 2Y"]
        for bond in us_bonds:
            try:
                price = fetch_bond_data(driver, bond)
                all_data.append((yesterday, bond.replace(" ", ""), price))
            except Exception as e:
                logging.error(f"Failed to retrieve data for {bond}: {e}")

        # Other countries' bond data
        driver.get('https://tradingeconomics.com/bonds')
        other_bonds = {
            "United Kingdom": "UK10Y",
            "Japan": "JP10Y",
            "Brazil": "BR10Y",
            "India": "IND10Y",
            "Turkey": "TUR10Y"
        }
        for bond, mapped_name in other_bonds.items():
            try:
                price = fetch_bond_data(driver, bond)
                all_data.append((yesterday, mapped_name, price))
            except Exception as e:
                logging.error(f"Failed to retrieve data for {mapped_name}: {e}")

        cursor.executemany('INSERT OR REPLACE INTO Bonds (date, name, price) VALUES (?, ?, ?)', all_data)
        conn.commit()
        logging.info(f"Total {len(all_data)} records have been inserted into the database.")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        conn.rollback()
    finally:
        driver.quit()
        conn.close()

if __name__ == "__main__":
    main()