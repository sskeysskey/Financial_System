from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import sqlite3

def get_parent_id(commodity):
    if commodity in ["Crude Oil", "Brent", "Natural gas", "Coal", "Uranium"]:
        return 5
    elif commodity in ["Gold", "Silver", "Copper", "Steel", "Lithium"]:
        return 6
    elif commodity in ["Soybeans", "Wheat", "Palm Oil", "Orange Juice", "Cocoa", "Rice", "Corn", "Coffee", "Sugar",
        "Oat", "Orange Juice"]:
        return 7
    elif commodity in ["Aluminum", "Nickel", "Tin", "Zinc", "Palladium"]:
        return 8
    elif commodity in ["Live Cattle", "Lean Hogs", "Live Cattle", "Poultry", "Salmon"]:
        return 9
    elif commodity in ["CRB Index", "LME Index", "Nuclear Energy Index", "Solar Energy Index", "EU Carbon Permits",
        "Containerized Freight Index"]:
        return 23
    return None

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
    CREATE TABLE  IF NOT EXISTS  Commodities (
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
        driver.get('https://tradingeconomics.com/commodities')
        commodities = [
            "Crude Oil", "Brent", "Natural gas", "Coal", "Uranium",
            "Gold", "Silver", "Copper", "Steel", "Lithium",
            "Soybeans", "Wheat", "Palm Oil", "Orange Juice", "Cocoa", "Rice", "Sugar", "Coffee",
            "Corn", "Oat", "Orange Juice", "Aluminum", "Nickel", "Tin", "Zinc", "Palladium",
            "Live Cattle", "Lean Hogs", "Live Cattle", "Poultry", "Salmon",
            "CRB Index", "LME Index", "Nuclear Energy Index", "Solar Energy Index", "EU Carbon Permits",
            "Containerized Freight Index"
        ]

        all_data = []
        # 获取当前时间
        now = datetime.now()
        # 获取前一天的日期
        yesterday = now - timedelta(days=1)
        # 格式化输出
        today = yesterday.strftime('%Y-%m-%d')

        # 查找并处理数据
        for commodity in commodities:
            try:
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.LINK_TEXT, commodity))
                )
                row = element.find_element(By.XPATH, './ancestor::tr')
                price = row.find_element(By.ID, 'p').text.strip()
                parent_id = get_parent_id(commodity)
                
                # 将数据格式化后添加到列表
                all_data.append((today, commodity, price, parent_id))
            except Exception as e:
                print(f"Failed to retrieve data for {commodity}: {e}")
        
        # 插入数据到数据库
        cursor.executemany('INSERT INTO Commodities (date, name, price, parent_id) VALUES (?, ?, ?, ?)', all_data)
        conn.commit()

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()  # 回滚在异常发生时的所有操作
    finally:
        driver.quit()
        conn.close()

    print("Data scraping and storage done.")