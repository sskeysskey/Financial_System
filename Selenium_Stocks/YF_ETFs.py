from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import os

def fetch_data(url):
    # 初始化WebDriver
    driver = webdriver.Chrome()
    driver.get(url)
    
    # 等待页面加载
    time.sleep(5)  # 根据网络情况调整等待时间
    
    data_list = []

    try:
        # 找到所有的数据行
        rows = driver.find_elements(By.CSS_SELECTOR, 'tr.simpTblRow')
        
        for row in rows:
            # 在当前行中提取Symbol
            symbol_element = row.find_element(By.CSS_SELECTOR, 'a[data-test="quoteLink"]')
            symbol = symbol_element.text.strip()
            
            # 在当前行中提取Name
            name_element = row.find_element(By.CSS_SELECTOR, 'td[aria-label="Name"]')
            name = name_element.text.strip()

            # 在当前行中提取Volume，并移除逗号以转换为整数
            volume_element = row.find_element(By.CSS_SELECTOR, 'fin-streamer[data-field="regularMarketVolume"]')
            volume = int(volume_element.get_attribute('value').replace(',', ''))

            data_list.append((symbol, name, volume))
        
        return data_list
    finally:
        driver.quit()

def save_data(urls, existing_file, new_file):
    # 检查new_file是否存在，如果存在，则迁移内容到existing_file
    if os.path.exists(new_file):
        with open(new_file, 'r') as file_a, open(existing_file, 'a') as file_b:
            file_b.write('\n')  # 在迁移内容前首先输入一个回车
            for line in file_a:
                file_b.write(line)
        open(new_file, 'w').close()  # 清空a.txt

    # 读取现有的symbols
    existing_symbols = set()
    with open(existing_file, 'r') as file:
        for line in file:
            existing_symbol = line.split(': ')[0].strip()
            existing_symbols.add(existing_symbol)

    # 写入新数据到new_file
    with open(new_file, "w") as file:
        for url in urls:
            data_list = fetch_data(url)
            for symbol, name, volume in data_list:
                if volume > 200000 and symbol not in existing_symbols:
                    file.write(f"{symbol}: {name}, {volume}\n")
                    existing_symbols.add(symbol)

# URL列表
urls = ["https://finance.yahoo.com/etfs/?offset=0&count=100", "https://finance.yahoo.com/etfs/?count=100&offset=100"]
existing_file = '/Users/yanzhang/Documents/News/backup/ETFs.txt'
new_file = '/Users/yanzhang/Documents/News/ETFs_new.txt'

save_data(urls, existing_file, new_file)