from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
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
        price REAL
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
        driver.get('https://finance.yahoo.com/commodities/')
        # 映射表将商品符号与商品名称关联
        commodity_mapping = {
            "CC=F": "Cocoa", "KC=F": "Coffee", "CT=F": "Cotton", "OJ=F": "Orange Juice", "SB=F": "Sugar",
            "HE=F": "Lean Hogs", "CL=F": "Crude Oil", "BZ=F": "Brent", "LE=F": "Live Cattle", "HG=F": "Copper",
            "ZC=F": "Corn", "GC=F": "Gold", "SI=F": "Silver", "NG=F": "Natural gas",
            "ZR=F": "Rice", "ZS=F": "Soybeans"
        }
        #  "ZO=F": "Oat",

        all_data = []
        # 获取当前时间
        now = datetime.now()
        # 获取前一天的日期
        yesterday = now - timedelta(days=1)
        # 格式化输出
        today = yesterday.strftime('%Y-%m-%d')

        symbols = driver.find_elements(By.XPATH, '//a[@data-test="quoteLink"]')
        for symbol in symbols:
            commodity_symbol = symbol.text
            if commodity_symbol in commodity_mapping:
                commodity_name = commodity_mapping[commodity_symbol]
                price_element = symbol.find_element(By.XPATH, './ancestor::td/following-sibling::td[@aria-label="Last Price"]/fin-streamer')
                price = price_element.get_attribute('value')
                all_data.append((today, commodity_name, price))
        
        # 插入数据到数据库
        cursor.executemany('INSERT INTO Commodities (date, name, price) VALUES (?, ?, ?)', all_data)
        conn.commit()
        # 打印插入的数据条数
        print(f"Total {len(all_data)} records have been inserted into the database.")

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()  # 回滚在异常发生时的所有操作
    finally:
        driver.quit()
        conn.close()