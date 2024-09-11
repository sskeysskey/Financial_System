from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import re
import sqlite3
from datetime import datetime, timedelta

def setup_driver():
    chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
    service = Service(executable_path=chrome_driver_path)
    return webdriver.Chrome(service=service)

def parse_error_file(file_path):
    data = []
    pattern = r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\] (\w+) (\w+): No price data found for the given date range\.'
    with open(file_path, 'r') as file:
        for line in file:
            match = re.match(pattern, line.strip())
            if match:
                _, tablename, symbol = match.groups()
                data.append((tablename, symbol))
    return data

def safe_float(value):
    try:
        return float(value.replace(',', ''))
    except (ValueError, AttributeError):
        return None

def safe_int(value):
    try:
        return int(value.replace(',', ''))
    except (ValueError, AttributeError):
        return None

def fetch_data(driver, symbol):
    url = f"https://finance.yahoo.com/quote/{symbol}/"
    driver.get(url)
    
    try:
        price_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//fin-streamer[@data-field='regularMarketPrice']/span"))
        )
        price = safe_float(price_element.text)

        volume_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//fin-streamer[@data-field='regularMarketVolume']"))
        )
        volume = safe_int(volume_element.text)

        if price is None and volume is None:
            print(f"Warning: No valid data for {symbol}. Price: {price_element.text}, Volume: {volume_element.text}")
            return None, None

        if price is None:
            print(f"Warning: Invalid price for {symbol}. Price: {price_element.text}")
        if volume is None:
            print(f"Warning: Invalid volume for {symbol}. Volume: {volume_element.text}")

        return price, volume
    except Exception as e:
        print(f"Error fetching data for {symbol}: {str(e)}")
        return None, None

def insert_data(conn, tablename, symbol, date, price, volume):
    cursor = conn.cursor()
    cursor.execute(f'''
        INSERT INTO {tablename} (date, name, price, volume)
        VALUES (?, ?, ?, ?)
    ''', (date, symbol, price, volume))
    conn.commit()

def adapt_date(date):
    return date.isoformat()

def main():
    error_file_path = "/Users/yanzhang/Documents/News/Today_error.txt"
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"

    driver = setup_driver()
    data = parse_error_file(error_file_path)

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    sqlite3.register_adapter(datetime, adapt_date)
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)

    try:
        for tablename, symbol in data:
            price, volume = fetch_data(driver, symbol)
            if price is not None or volume is not None:
                insert_data(conn, tablename, symbol, yesterday, price, volume)
                print(f"Data inserted for {symbol} in {tablename}. Price: {price}, Volume: {volume}")
            else:
                print(f"Skipping {symbol} due to no valid data")
    finally:
        driver.quit()
        conn.close()

if __name__ == "__main__":
    main()