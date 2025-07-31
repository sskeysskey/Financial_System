from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import sqlite3
import time

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver 选项
from selenium.webdriver.chrome.options import Options
chrome_options = Options()
chrome_options.add_argument("--headless")  # 无头模式
chrome_options.add_argument("--disable-gpu")  # 禁用GPU加速
chrome_options.add_argument("--no-sandbox")  # 解决DevToolsActivePort文件不存在的报错
chrome_options.add_argument("--disable-dev-shm-usage")  # 解决资源限制问题
chrome_options.add_argument("--window-size=1920x1080")  # 设置窗口大小

# 初始化 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

# 初始化数据库连接
conn = sqlite3.connect('/Users/yanzhang/Coding/Database/Finance.db')
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

# 获取当前时间
now = datetime.now()
# 获取前一天的日期
yesterday = now - timedelta(days=1)
# 格式化输出
today = yesterday.strftime('%Y-%m-%d')

max_attempts = 3
attempts = 0
success = False

try:
    while attempts < max_attempts and not success:
        try:
            # 访问网页
            driver.get('https://finance.yahoo.com/markets/crypto/all/')
            # 等待页面元素加载完成
            rows = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, '//tbody[@class="body yf-42jv6g"]/tr')))
            all_data = []
            for row in rows:
                # 获取加密货币的Symbol
                symbol_element = row.find_element(By.XPATH, './/span[@class="symbol yf-ravs5v"]')
                crypto_symbol = symbol_element.text.strip()
                if crypto_symbol in crypto_names:
                    # 获取加密货币的价格，并去掉逗号
                    price_element = row.find_element(By.XPATH, './/fin-streamer[@data-field="regularMarketPrice"]')
                    price = price_element.get_attribute('data-value').replace(',', '')
                    full_name = crypto_names[crypto_symbol]
                    all_data.append((today, full_name, price))
            
            # 插入数据到数据库
            cursor.executemany('INSERT OR REPLACE INTO Crypto (date, name, price) VALUES (?, ?, ?)', all_data)
            conn.commit()
            print(f"Total {len(all_data)} records have been inserted into the database.")
            success = True  # 如果抓取成功，设置成功标志
        except Exception as e:
            attempts += 1
            print(f"Attempt {attempts} failed: {e}")
            time.sleep(2)  # 重试前等待2秒
except Exception as e:
    print(f"An error occurred: {e}")
    conn.rollback()  # 回滚在异常发生时的所有操作
finally:
    driver.quit()
    conn.close()