import re
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import time

chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 读取sectors.json文件
with open("/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json", "r") as file:
    data = json.load(file)

stock_sectors = [
    "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
    "Industrials", "Real_Estate", "Technology", "Utilities"
]

# 准备保存数据的字典
names_data = {}

# 遍历data中的每一个sector
for sector in data:
    if sector in stock_sectors:
        for stock_symbol in data[sector]:
            url = f"https://finance.yahoo.com/quote/{stock_symbol}/key-statistics"
            driver.get(url)
            time.sleep(2)  # 等待页面加载
            try:
                # 定位元素并获取文本
                element = driver.find_element(By.CSS_SELECTOR, 'section.container h1')
                text = element.text.strip()
                
                text = re.sub(r'\(.*?\)', '', text)
                if ',' in text or '.' in text:
                    split_pattern = r'[,.]'
                    parts = re.split(split_pattern, text)
                    text_part = parts[0].strip()
                else:
                    words = text.split(' ')
                    if len(words) >= 3:
                        text_part = ' '.join(words[:3])  # 获取前两个单词组成的字符串
                    elif len(words) == 2:
                        text_part = ' '.join(words[:2])  # 获取前三个单词组成的字符串
                    else:
                        text_part = words[0] # 如果不足两个单词，就返回第一个单词
                names_data[stock_symbol] = text_part
            except Exception as e:
                print(f"Error fetching data for {stock_symbol}: {str(e)}")

# 关闭浏览器
driver.quit()

# 将结果写入shares.txt，避免重复写入
with open("/Users/yanzhang/Documents/News/backup/symbol_names.txt", "a+") as file:
    file.seek(0)
    existing_data = file.read()
    for symbol, name in names_data.items():
        if f"{symbol}: {name}" not in existing_data:
            file.write(f"{symbol}: {name}\n")