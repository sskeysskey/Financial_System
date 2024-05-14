from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import sqlite3

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--disable-gpu')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

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

driver = setup_driver()
# 映射字典
crypto_names = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ether",
    "SOL-USD": "Solana",
    "BNB-USD": "Binance"
}

try:
    # 访问网页
    driver.get('https://finance.yahoo.com/crypto/')
    all_data = []
    # 获取当前时间
    now = datetime.now()
    # 获取前一天的日期
    yesterday = now - timedelta(days=1)
    # 格式化输出
    today = yesterday.strftime('%Y-%m-%d')

    # 查找所有含有特定aria-label="Name"的<td>元素
    names = driver.find_elements(By.XPATH, '//td[@aria-label="Symbol"]')

    for name in names:
        crypto_symbol = name.text
        if crypto_symbol in crypto_names:
            # 查找相邻的价格
            price_element = name.find_element(By.XPATH, './following-sibling::td[@aria-label="Price (Intraday)"]/fin-streamer')
            price = price_element.get_attribute('value')
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