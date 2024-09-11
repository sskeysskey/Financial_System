import os
import re
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta

# 浏览器设置
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 读取 today_error.txt 文件
txt_file_path = "/Users/yanzhang/Documents/News/Today_error.txt"
with open(txt_file_path, 'r') as txt_file:
    txt_content = txt_file.read()

# 匹配 "ETFs HYG" 或 "Basic_Materials RIO" 的模式
pattern = re.compile(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] (\w+) (\w+):")
matches = pattern.findall(txt_content)

# 提取 tablename 和 symbol
tasks = [{"tablename": match[0], "symbol": match[1]} for match in matches]

# 获取昨天的日期
now = datetime.now()
yesterday = (now - timedelta(days=1)).date()

# 打开数据库连接
db_path = "/Users/yanzhang/Documents/Database/Finance.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 爬取股票数据并写入数据库
for task in tasks:
    tablename = task["tablename"]
    symbol = task["symbol"]
    
    # 爬取页面 https://finance.yahoo.com/quote/{symbol}/
    url = f"https://finance.yahoo.com/quote/{symbol}/"
    driver.get(url)

    try:
        # 提取价格 (price)
        price_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "fin-streamer[data-testid='qsp-price'] > span"))
        )
        price = price_element.text
        price = float(price.replace(',', ''))  # 转换为浮点数

        # 提取成交量 (volume)
        volume_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//span[@class='value yf-tx3nkj']/fin-streamer[@data-field='regularMarketVolume']"))
        )
        volume = volume_element.get_attribute("data-value")
        if volume == '--':
            print(f"Symbol {symbol} has no available volume data.")
            volume = 0.0  # 设置默认价格
        else:
            volume = int(volume.replace(',', ''))  # 转换为整数

        # 插入数据到 SQLite 数据库
        cursor.execute(f"""
            INSERT INTO {tablename} (date, name, price, volume)
            VALUES (?, ?, ?, ?)
        """, (yesterday, symbol, price, volume))

        print(f"成功插入数据: {tablename}, {symbol}, {price}, {volume}")

    except Exception as e:
        print(f"爬取 {symbol} 时出错: {str(e)}")

# 提交事务并关闭数据库
conn.commit()
conn.close()

# 关闭浏览器
driver.quit()