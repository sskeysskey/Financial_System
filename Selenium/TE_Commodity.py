from selenium import webdriver
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import sqlite3
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ChromeDriver 路径
CHROME_DRIVER_PATH = "/Users/yanzhang/Downloads/backup/chromedriver"
DB_PATH = '/Users/yanzhang/Documents/Database/Finance.db'

def setup_driver():
    service = Service(executable_path=CHROME_DRIVER_PATH)
    return webdriver.Chrome(service=service)

def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Commodities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        name TEXT,
        price REAL,
        UNIQUE(date, name)
    );
    ''')
    conn.commit()
    return conn, cursor

# def fetch_commodity_data_str(driver, commodity_name, xpath='./ancestor::tr'):
#     element = WebDriverWait(driver, 10).until(
#         EC.presence_of_element_located((By.LINK_TEXT, commodity_name))
#     )
#     row = element.find_element(By.XPATH, xpath)
#     price_str = row.find_element(By.ID, 'p').text.strip()
#     return float(price_str.replace(',', ''))

def fetch_baltic_dry_price(driver):
    try:
        logging.info("Starting to fetch Baltic Dry price...")
        table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "table-responsive"))
        )
        logging.info("Table found successfully")
        
        price_element = driver.find_element(
            By.XPATH, 
            "//div[@class='table-responsive']//table//tr/td[position()=2]"
        )
        price_str = price_element.text.strip()
        price = float(price_str.replace(',', ''))
        logging.info(f"Successfully fetched Baltic Dry price: {price}")
        return price
    except Exception as e:
        logging.error(f"Failed to fetch Baltic Dry price: {e}")
        return None

def fetch_commodity_data(driver, commodity_name, xpath='./ancestor::tr'):
    element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.LINK_TEXT, commodity_name))
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

        # Baltic Dry data
        driver.get('https://tradingeconomics.com/commodity/baltic')
        price = fetch_baltic_dry_price(driver)
        if price is not None:
            all_data.append((yesterday, "BalticDry", price))

        # Other commodity data
        driver.get('https://tradingeconomics.com/commodities')
        commodities = [
            "Coal", "Uranium", "Steel", "Lithium", "Wheat", "Palm Oil", "Aluminum",
            "Nickel", "Tin", "Zinc", "Palladium", "Poultry", "Salmon", "Iron Ore", "Orange Juice"
        ]

        for commodity in commodities:
            try:
                price = fetch_commodity_data(driver, commodity)
                all_data.append((yesterday, commodity.replace(" ", ""), price))
            except Exception as e:
                logging.error(f"Failed to retrieve data for {commodity}: {e}")

        cursor.executemany('INSERT OR REPLACE INTO Commodities (date, name, price) VALUES (?, ?, ?)', all_data)
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