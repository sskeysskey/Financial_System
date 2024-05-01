from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import sqlite3

# 获取当前时间
now = datetime.now()

# 判断今天的星期数，如果是周日(6)或周一(0)，则不执行程序
if now.weekday() in (0, 6):
    print("Today is either Sunday or Monday. The script will not run.")
else:
    # 初始化数据库连接
    conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
    cursor = conn.cursor()
    # 创建表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Stocks (
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
        driver.get('https://finance.yahoo.com/world-indices/')
        indices = [
            "NASDAQ Composite", "S&P 500", "Russell 2000", "MOEX Russia Index", "Nikkei 225", "HANG SENG INDEX",
            "SSE Composite Index",  "Shenzhen Index", "S&P BSE SENSEX", "IBOVESPA", "CBOE Volatility Index",
        ]

        all_data = []
        # 获取当前时间
        now = datetime.now()
        # 获取前一天的日期
        yesterday = now - timedelta(days=1)
        # 格式化输出
        today = yesterday.strftime('%Y-%m-%d')

        # 查找所有含有特定aria-label="Name"的<td>元素
        names = driver.find_elements(By.XPATH, '//td[@aria-label="Name"]')

        for name in names:
            indice_name = name.text
            if indice_name in indices:
                # 查找相邻的价格
                price_element = name.find_element(By.XPATH, './following-sibling::td[@aria-label="Last Price"]/fin-streamer')
                price = price_element.get_attribute('value')
                parent_id = 10
                all_data.append((today, indice_name, price, parent_id))
        
        # 插入数据到数据库
        cursor.executemany('INSERT INTO Stocks (date, name, price, parent_id) VALUES (?, ?, ?, ?)', all_data)
        conn.commit()

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()  # 回滚在异常发生时的所有操作
    finally:
        driver.quit()
        conn.close()

    print("Data scraping and storage done.")