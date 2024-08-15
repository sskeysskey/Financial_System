from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
import sqlite3

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

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

try:
    # 访问网页
    driver.get('https://finance.yahoo.com/markets/crypto/all/')
    all_data = []
    # 获取当前时间
    now = datetime.now()
    # 获取前一天的日期
    yesterday = now - timedelta(days=1)
    # 格式化输出
    today = yesterday.strftime('%Y-%m-%d')

    # 查找所有包含加密货币信息的<tr>元素
    rows = driver.find_elements(By.XPATH, '//tbody[@class="body yf-42jv6g"]/tr')
    
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
    # 打印插入的数据条数
    print(f"Total {len(all_data)} records have been inserted into the database.")

except Exception as e:
    print(f"An error occurred: {e}")
    conn.rollback()  # 回滚在异常发生时的所有操作
finally:
    driver.quit()
    conn.close()