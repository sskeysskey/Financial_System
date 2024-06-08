import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import time

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

# 读取sectors.json文件
with open("/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json", "r") as file:
    data = json.load(file)

# 指定有效的行业分类
# stock_sectors = [
#     "Energy"
# ]

stock_sectors = [
    "Basic_Materials", "Communication_Services", "Consumer_Cyclical",
    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare",
    "Industrials", "Real_Estate", "Technology", "Utilities"
]

# 准备保存数据的字典
shares_data = {}

# 遍历data中的每一个sector
for sector in data:
    if sector in stock_sectors:
        for stock_symbol in data[sector]:
            url = f"https://finance.yahoo.com/quote/{stock_symbol}/key-statistics"
            driver.get(url)
            time.sleep(2)  # 等待页面加载
            try:
                # 查找Shares Outstanding的数据
                shares_outstanding = driver.find_element(By.XPATH, "//td[text()='Shares Outstanding']/following-sibling::td").text
                shares_outstanding_converted = convert_shares_format(shares_outstanding)
                shares_data[stock_symbol] = shares_outstanding_converted
            except Exception as e:
                print(f"Error fetching data for {stock_symbol}: {str(e)}")

# 关闭浏览器
driver.quit()

# 将结果写入shares.txt，避免重复写入
with open("/Users/yanzhang/Documents/News/backup/Shares.txt", "a+") as file:
    file.seek(0)
    existing_data = file.read()
    for symbol, shares in shares_data.items():
        if f"{symbol}: {shares}" not in existing_data:
            file.write(f"{symbol}: {shares}\n")