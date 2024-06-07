from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import os
import json
# from collections import defaultdict
from selenium.webdriver.chrome.service import Service

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

def fetch_data(url):
    driver.get(url)
    data_list = []

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

def save_data(urls, existing_file, new_file, json_file):
# def save_data(urls, url_tag, existing_file, new_file, json_file):
    # with open(json_file, 'r') as file:
    #     json_data = json.load(file)
    #     etf_data = {item['name']: item['tag'] for item in json_data['etfs']}
    
    # tag_counts = defaultdict(int)
    existing_symbols = set()

    # 检查new_file是否存在，如果存在，则迁移内容到existing_file
    if os.path.exists(new_file):
        with open(new_file, 'r') as file_a, open(existing_file, 'a') as file_b:
            file_b.write('\n')  # 在迁移内容前首先输入一个回车
            for line in file_a:
                file_b.write(line)
        open(new_file, 'w').close()  # 清空new_file

    # 读取现有的symbols
    with open(existing_file, 'r') as file:
        for line in file:
            existing_symbol = line.split(': ')[0].strip()
            existing_symbols.add(existing_symbol)

    # 对每个URL中的数据进行处理
    with open(new_file, "w") as file:
        for url in urls:
            data_list = fetch_data(url)
            for symbol, name, volume in data_list:
                if volume > 200000 and symbol not in existing_symbols:
                    file.write(f"{symbol}: {name}, {volume}\n")
                    existing_symbols.add(symbol)
                
    # data_list_tag = fetch_data(url_tag[0])
    # for symbol, name, volume in data_list_tag:
    #     if volume > 200000 and symbol in etf_data:
    #             for tag in etf_data[symbol]:
    #                 tag_counts[tag] += 1

    # 将标签计数结果保存到文件
    # with open('/Users/yanzhang/Documents/News/Analyse_ETFs.txt', 'w') as file:
    #     for tag, count in tag_counts.items():
    #         file.write(f"{tag}: {count}\n")

# URL列表
urls = ["https://finance.yahoo.com/etfs/?offset=0&count=100", "https://finance.yahoo.com/etfs/?count=100&offset=100", "https://finance.yahoo.com/etfs/?count=100&offset=200"]
# url_tag = ["https://finance.yahoo.com/etfs/?offset=0&count=100"]
existing_file = '/Users/yanzhang/Documents/News/backup/ETFs.txt'
new_file = '/Users/yanzhang/Documents/News/ETFs_new.txt'
json_file = '/Users/yanzhang/Documents/Financial_System/Modules/Description.json'

try:
    # save_data(urls, url_tag, existing_file, new_file, json_file)
    save_data(urls, existing_file, new_file, json_file)
finally:
    driver.quit()
print("所有爬取任务完成，并已处理标签计数。")