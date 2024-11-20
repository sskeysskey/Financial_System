from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import re
import json
import glob
from datetime import datetime

def convert_shares_format(shares_str):
    # 转换股票数量的表示方式，例如 "15.33B" 转换为 15330000000
    if 'B' in shares_str:
        return int(float(shares_str.replace('B', '')) * 10**9)
    elif 'M' in shares_str:
        return int(float(shares_str.replace('M', '')) * 10**6)
    elif 'K' in shares_str:
        return int(float(shares_str.replace('K', '')) * 10**3)
    elif 'k' in shares_str:
        return int(float(shares_str.replace('k', '')) * 10**3)
    return int(shares_str)  # 如果没有单位标识符，直接返回原始字符串

chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 文件目录路径
txt_file_directory = "/Users/yanzhang/Documents/News/backup/backup/"

# 找到以Stock_50_开头的第一个TXT文件
txt_file_pattern = os.path.join(txt_file_directory, "Stock_50_*.txt")
txt_files = glob.glob(txt_file_pattern)

if not txt_files:
    raise FileNotFoundError("未找到以 'Stock_50_' 开头的TXT文件。")

# 用字典存储文件路径和对应的日期
file_dates = {}

# 正则表达式匹配文件名中的日期
date_pattern = re.compile(r"Stock_50_(\d{6})\.txt$")

for file_path in txt_files:
    match = date_pattern.search(os.path.basename(file_path))
    if match:
        try:
            # 将匹配到的日期字符串转换为datetime对象
            date_str = match.group(1)
            file_date = datetime.strptime(date_str, "%y%m%d")
            file_dates[file_path] = file_date
        except ValueError:
            continue

if not file_dates:
    raise FileNotFoundError("未找到含有有效日期的Stock_50_文件。")

# 获取日期最新的文件路径
latest_file = max(file_dates.items(), key=lambda x: x[1])[0]

# 读取TXT文件内容
with open(latest_file, 'r') as txt_file:
    txt_content = txt_file.read()

# 使用正则表达式匹配 "Added 'XXX' to YYY" 的模式
pattern = re.compile(r"Added\s+'(\w+(-\w+)?)'\s+to\s+(\w+)")

# 在TXT文件内容中查找所有匹配项
matches = pattern.findall(txt_content)

# 提取股票代码
stock_symbols = [match[0] for match in matches]

# 准备保存数据的字典
shares_data = {}

# 将匹配的内容添加到JSON数据中对应的组别
for symbol in stock_symbols:
    url = f"https://finance.yahoo.com/quote/{symbol}/key-statistics"
    driver.get(url)
    try:
        # 查找Shares Outstanding的数据
        shares_outstanding_element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//td[text()='Shares Outstanding']/following-sibling::td"))
        )
        shares_outstanding = shares_outstanding_element.text
        shares_outstanding_converted = convert_shares_format(shares_outstanding)
        shares_data[symbol] = shares_outstanding_converted
    except Exception as e:
        print(f"Error fetching data for {symbol}: {str(e)}")

# 关闭浏览器
driver.quit()

# 将结果写入shares.txt，避免重复写入
with open("/Users/yanzhang/Documents/News/backup/Shares.txt", "a+") as file:
    file.seek(0)
    existing_data = file.read()
    for symbol, shares in shares_data.items():
        if f"{symbol}: {shares}" not in existing_data:
            file.write(f"{symbol}: {shares}\n")