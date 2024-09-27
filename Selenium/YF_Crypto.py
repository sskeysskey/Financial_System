from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import sqlite3
import logging
import time

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 Chrome 选项
chrome_options = Options()
# chrome_options.add_argument("--headless")  # 无头模式
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

# 初始化数据库连接
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 创建表
cursor.execute('''
CREATE TABLE IF NOT EXISTS Crypto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    name TEXT,
    price REAL,
    UNIQUE(date, name)
);
''')
conn.commit()

# 映射字典
crypto_names = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ether",
    "SOL-USD": "Solana",
    "BNB-USD": "Binance"
}

def fetch_data(max_retries=3):
    for attempt in range(max_retries):
        try:
            logging.info(f"Attempt {attempt + 1} to fetch data")
            driver.get('https://finance.yahoo.com/markets/crypto/all/')
            
            # 等待页面加载
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//tbody[@class="body yf-1dbt8wv"]/tr'))
            )
            
            all_data = []
            now = datetime.now()
            yesterday = now - timedelta(days=1)
            today = yesterday.strftime('%Y-%m-%d')

            rows = driver.find_elements(By.XPATH, '//tbody[@class="body yf-1dbt8wv"]/tr')
            
            for row in rows:
                symbol_element = WebDriverWait(row, 10).until(
                    EC.presence_of_element_located((By.XPATH, './/span[@class="symbol yf-1jpysdn"]'))
                )
                crypto_symbol = symbol_element.text.strip()
                
                if crypto_symbol in crypto_names:
                    price_element = WebDriverWait(row, 10).until(
                        EC.presence_of_element_located((By.XPATH, './/fin-streamer[@data-field="regularMarketPrice"]'))
                    )
                    price = price_element.get_attribute('data-value').replace(',', '')
                    full_name = crypto_names[crypto_symbol]
                    all_data.append((today, full_name, price))
            
            logging.info(f"Successfully fetched {len(all_data)} records")
            return all_data
        
        except Exception as e:
            logging.error(f"An error occurred during attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                logging.info("Retrying...")
                time.sleep(3)  # 等待5秒后重试
            else:
                logging.error("Max retries reached. Exiting...")
                return []

try:
    data = fetch_data()
    
    if data:
        cursor.executemany('INSERT OR REPLACE INTO Crypto (date, name, price) VALUES (?, ?, ?)', data)
        conn.commit()
        logging.info(f"Total {len(data)} records have been inserted into the database.")
    else:
        logging.warning("No data was fetched. Check the logs for details.")

except Exception as e:
    logging.error(f"An unexpected error occurred: {e}")
    conn.rollback()

finally:
    driver.quit()
    conn.close()