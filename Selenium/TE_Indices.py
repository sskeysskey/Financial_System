from selenium import webdriver
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import sqlite3

# 获取当前时间
now = datetime.now()

# 判断今天的星期数，如果是周日(6)或周一(0)，则不执行程序
if now.weekday() in (0, 6):
    print("Today is either Sunday or Monday. The script will not run.")
else:
    # 设置Chrome选项以提高性能
    chrome_options = Options()
    chrome_options.add_argument("--disable-extensions")  # 禁用扩展
    chrome_options.add_argument("--disable-gpu")  # 禁用GPU加速
    chrome_options.add_argument("--disable-dev-shm-usage")  # 禁用开发者工具
    chrome_options.add_argument("--no-sandbox")  # 禁用沙盒模式
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
    chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

    # 设置ChromeDriver路径并初始化
    chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # 初始化数据库连接
    conn = sqlite3.connect('/Users/yanzhang/Coding/Database/Finance.db')
    cursor = conn.cursor()
    # 创建表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Indices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        name TEXT,
        price REAL,
        volume REAL,
        UNIQUE(date, name)
    );
    ''')
    conn.commit()

    try:
        # 访问网页
        driver.get('https://tradingeconomics.com/stocks')
        name_mapping = {
            "MOEX": "Russia"
        }

        all_data = []
        # 获取当前时间
        now = datetime.now()
        # 获取前一天的日期
        yesterday = now - timedelta(days=1)
        # 格式化输出
        today = yesterday.strftime('%Y-%m-%d')

        # 查找并处理数据
        for Indice in name_mapping.keys():
            try:
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.LINK_TEXT, Indice))
                )
                row = element.find_element(By.XPATH, './ancestor::tr')
                price = row.find_element(By.ID, 'p').text.strip()
                # 使用映射后的名称
                mapped_name = name_mapping[Indice]
                
                # 将数据格式化后添加到列表
                all_data.append((today, mapped_name, price, 0))
            except Exception as e:
                print(f"Failed to retrieve data for {name_mapping}: {e}")
        
        # 插入数据到数据库
        cursor.executemany('INSERT INTO Indices (date, name, price, volume) VALUES (?, ?, ?, ?)', all_data)
        conn.commit()
        # 打印插入的数据条数
        print(f"Total {len(all_data)} records have been inserted into the database.")

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()  # 回滚在异常发生时的所有操作
    finally:
        driver.quit()
        conn.close()