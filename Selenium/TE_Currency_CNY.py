from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException # 导入TimeoutException异常
from datetime import datetime, timedelta
import sqlite3

# 获取当前时间
now = datetime.now()

# 判断今天的星期数，如果是周日(6)或周一(0)，则不执行程序
# 周一到周日对应的 weekday() 是 0 到 6
if now.weekday() in (0, 6):
    print("Today is either Sunday or Monday. The script will not run.")
else:
    # 初始化数据库连接
    # 请确保这里的数据库路径是正确的
    conn = sqlite3.connect('/Users/yanzhang/Coding/Database/Finance.db')
    cursor = conn.cursor()
    # 创建表 (如果不存在)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Currencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        name TEXT,
        price REAL
    );
    ''')
    conn.commit()

    # 设置Chrome选项以提高性能
    chrome_options = Options()
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
    chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始
    # chrome_options.add_argument('--headless')  # 如果需要无界面模式，可以取消此行注释

    # 设置ChromeDriver路径
    # 请确保这里的ChromeDriver路径是正确的
    chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # 定义要抓取的目标货币符号
        symbols = ["CNYIRR"]

        all_data = []
        # 获取当前时间
        now = datetime.now()
        # 获取前一天的日期
        yesterday = now - timedelta(days=1)
        # 格式化日期
        today = yesterday.strftime('%Y-%m-%d')

        # 循环遍历每个符号，访问其对应页面并抓取数据
        for symbol in symbols:
            price_text = None # 初始化价格文本变量
            try:
                # 1. 根据symbol构造URL
                url = f"https://tradingeconomics.com/{symbol}:cur"
                print(f"Navigating to {url} for symbol {symbol}...")
                
                # 2. 访问网页
                driver.get(url)
                
                # --- 核心修改部分：实现备用抓取方案 ---
                try:
                    # 方案一：优先尝试通过 ID "market_last" 抓取
                    print(f"Attempting to find price with Method 1 (id='market_last')...")
                    # 设置一个稍短的等待时间，如果页面结构不是这个，可以快速失败并尝试方案二
                    wait = WebDriverWait(driver, 5) 
                    price_element = wait.until(
                        EC.presence_of_element_located((By.ID, "market_last"))
                    )
                    price_text = price_element.text.strip()
                    print("Success with Method 1.")

                except TimeoutException:
                    # 方案二：如果方案一超时（即找不到元素），则执行这里的备用方案
                    print("Method 1 failed. Trying Method 2 (class='closeLabel')...")
                    # 使用标准等待时间来查找备用元素
                    wait = WebDriverWait(driver, 10)
                    price_element = wait.until(
                        EC.presence_of_element_located((By.CLASS_NAME, "closeLabel"))
                    )
                    price_text = price_element.text.strip()
                    print("Success with Method 2.")

                # --- 数据处理 ---
                # 只有当 price_text 被成功赋值后（即两种方法中至少有一种成功），才进行处理
                if price_text:
                    # 将价格转换为浮点数并保留两位小数
                    price = round(float(price_text), 4)
                    
                    # 将数据格式化后添加到列表
                    all_data.append((today, symbol, price))
                    print(f"Successfully retrieved and processed data for {symbol}: {price}")
                else:
                    # 理论上不会执行到这里，因为如果两种方法都失败，会抛出异常
                    print(f"Price text could not be found for {symbol}.")

            except Exception as e:
                # 如果两种方法都失败了，或者发生了其他预料之外的错误，则会捕获异常
                print(f"Failed to retrieve data for {symbol}. Both methods failed or an error occurred: {e}")
        
        # 如果成功抓取到数据，则插入数据库
        if all_data:
            # 插入数据到数据库
            cursor.executemany('INSERT INTO Currencies (date, name, price) VALUES (?, ?, ?)', all_data)
            conn.commit()
            # 打印插入的数据条数
            print(f"\nTotal {len(all_data)} records have been inserted into the database.")
        else:
            print("\nNo data was retrieved. Nothing inserted into the database.")

    except Exception as e:
        print(f"An unexpected error occurred during the process: {e}")
        conn.rollback()
    finally:
        # 确保浏览器和数据库连接都被关闭
        driver.quit()
        conn.close()
        print("Script finished. Browser and database connection closed.")