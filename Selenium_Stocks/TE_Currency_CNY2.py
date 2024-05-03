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
    CREATE TABLE IF NOT EXISTS Currencies (
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
        driver.get('https://tradingeconomics.com/currencies?base=cny')
        Currencies = [
            "CNYJPY", "CNYARS", "CNYINR", "CNYKRW", "CNYMXN", "CNYRUB", "CNYSGD", "CNYBRL",
            "CNYPHP", "CNYIDR", "CNYEGP", "CNYTHB", "CNYEUR", "CNYUSD", "CNYGBP",
        ]

        all_data = []
        # 获取当前时间
        now = datetime.now()
        # 获取前一天的日期
        yesterday = now - timedelta(days=1)
        # 格式化输出
        today = yesterday.strftime('%Y-%m-%d')

        # 查找并处理数据
        for Currency in Currencies:
            try:
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.LINK_TEXT, Currency))
                )
                row = element.find_element(By.XPATH, './ancestor::tr')
                price = row.find_element(By.ID, 'p').text.strip()
                parent_id = 4
                
                # 将数据格式化后添加到列表
                all_data.append((today, Currency, price, parent_id))
            except Exception as e:
                print(f"Failed to retrieve data for {Currencies}: {e}")
        
        # 插入数据到数据库
        cursor.executemany('INSERT INTO Currencies (date, name, price, parent_id) VALUES (?, ?, ?, ?)', all_data)
        conn.commit()
        # 打印插入的数据条数
        print(f"Total {len(all_data)} records have been inserted into the database.")

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()  # 回滚在异常发生时的所有操作
    finally:
        driver.quit()
        conn.close()