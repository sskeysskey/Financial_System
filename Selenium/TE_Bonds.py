from selenium import webdriver
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import sqlite3

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

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
    CREATE TABLE IF NOT EXISTS Bonds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        name TEXT,
        price REAL,
        UNIQUE(date, name)
    );
    ''')
    conn.commit()

    # driver = setup_driver()
    try:
        # 访问网页
        driver.get('https://tradingeconomics.com/bonds')
        name_mapping = {
            "United Kingdom": "UK10Y",
            "Japan": "JP10Y",
            "Russia": "RU10Y",
            "Brazil": "BR10Y",
            "India": "IND10Y",
            "Turkey": "TUR10Y"
        }

        all_data = []
        # 获取当前时间
        now = datetime.now()
        # 获取前一天的日期
        yesterday = now - timedelta(days=1)
        # 格式化输出
        today = yesterday.strftime('%Y-%m-%d')

        # 查找并处理数据
        for bond in name_mapping.keys():
            try:
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.LINK_TEXT, bond))
                )
                row = element.find_element(By.XPATH, './ancestor::tr')
                price = row.find_element(By.ID, 'p').text.strip()
                # 使用映射后的名称
                mapped_name = name_mapping[bond]
                
                # 将数据格式化后添加到列表
                all_data.append((today, mapped_name, price))
            except Exception as e:
                print(f"Failed to retrieve data for {name_mapping}: {e}")
        
        # 插入数据到数据库
        cursor.executemany('INSERT INTO Bonds (date, name, price) VALUES (?, ?, ?)', all_data)
        conn.commit()
        # 打印插入的数据条数
        print(f"Total {len(all_data)} records have been inserted into the database.")

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()  # 回滚在异常发生时的所有操作
    finally:
        driver.quit()
        conn.close()