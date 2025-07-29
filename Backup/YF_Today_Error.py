import os
import re
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
from contextlib import contextmanager

# 配置常量
CHROME_DRIVER_PATH = "/Users/yanzhang/Downloads/backup/chromedriver"
TXT_FILE_PATH = "/Users/yanzhang/Documents/News/Today_error.txt"
DB_PATH = "/Users/yanzhang/Documents/Database/Finance.db"

@contextmanager
def get_driver():
    service = Service(executable_path=CHROME_DRIVER_PATH)
    driver = webdriver.Chrome(service=service)
    try:
        yield driver
    finally:
        driver.quit()

def read_tasks():
    with open(TXT_FILE_PATH, 'r') as txt_file:
        content = txt_file.read()
    pattern = re.compile(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] (\w+) (\w+):")
    return [{"tablename": match[0], "symbol": match[1]} for match in pattern.findall(content)]

def get_stock_data(driver, symbol):
    url = f"https://finance.yahoo.com/quote/{symbol}/"
    driver.get(url)
    
    price_element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "fin-streamer[data-testid='qsp-price'] > span"))
    )
    price = float(price_element.text.replace(',', ''))

    volume_element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//span[@class='value yf-tx3nkj']/fin-streamer[@data-field='regularMarketVolume']"))
    )
    volume = volume_element.get_attribute("data-value")
    volume = int(volume.replace(',', '')) if volume != '--' else 0

    return price, volume

def insert_data(cursor, tablename, symbol, date, price, volume):
    cursor.execute(f"""
        INSERT INTO {tablename} (date, name, price, volume)
        VALUES (?, ?, ?, ?)
    """, (date, symbol, price, volume))

def main():
    tasks = read_tasks()
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    with get_driver() as driver, sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for task in tasks:
            try:
                price, volume = get_stock_data(driver, task["symbol"])
                insert_data(cursor, task["tablename"], task["symbol"], yesterday, price, volume)
                print(f"成功插入数据: {task['tablename']}, {task['symbol']}, {price}, {volume}")
            except Exception as e:
                print(f"爬取 {task['symbol']} 时出错: {str(e)}")
        conn.commit()

if __name__ == "__main__":
    main()