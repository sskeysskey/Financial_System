from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import sqlite3

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
    parent_id INTEGER,
    FOREIGN KEY (parent_id) REFERENCES Categories(id)
);
''')
conn.commit()

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
service = Service(executable_path=chrome_driver_path)

# 设置WebDriver
options = webdriver.ChromeOptions()
# options.add_argument('--headless')  # 无界面模式
driver = webdriver.Chrome(service=service, options=options)

try:
    # 访问网页
    driver.get('https://tradingeconomics.com/Crypto')
    Cryptos = [
        "Bitcoin", "Ether", "Binance", "Bitcoin Cash", "Solana",
        "Monero", "Litecoin"
    ]

    all_data = []
    # 获取当前时间
    now = datetime.now()
    # 获取前一天的日期
    yesterday = now - timedelta(days=1)
    # 格式化输出
    today = yesterday.strftime('%Y-%m-%d')

    # 查找并处理数据
    for Crypto in Cryptos:
        try:
            element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.LINK_TEXT, Crypto))
            )
            row = element.find_element(By.XPATH, './ancestor::tr')
            price = row.find_element(By.ID, 'p').text.strip()
            parent_id = 3
            
            # 将数据格式化后添加到列表
            all_data.append((today, Crypto, price, parent_id))
        except Exception as e:
            print(f"Failed to retrieve data for {Crypto}: {e}")
    
    # 插入数据到数据库
    cursor.executemany('INSERT INTO Crypto (date, name, price, parent_id) VALUES (?, ?, ?, ?)', all_data)
    conn.commit()

except Exception as e:
    print(f"An error occurred: {e}")
    conn.rollback()  # 回滚在异常发生时的所有操作
finally:
    driver.quit()
    conn.close()

print("Data scraping and storage done, copied to clipboard.")