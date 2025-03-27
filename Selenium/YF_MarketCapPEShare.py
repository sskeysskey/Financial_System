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
    if shares_str == 'N/A' or shares_str == '-':
        return 0
    
    if 'T' in shares_str:
        return float(shares_str.replace('T', '')) * 10**12
    elif 'B' in shares_str:
        return float(shares_str.replace('B', '')) * 10**9
    elif 'M' in shares_str:
        return float(shares_str.replace('M', '')) * 10**6
    elif 'K' in shares_str or 'k' in shares_str:
        return float(shares_str.replace('K', '').replace('k', '')) * 10**3
    try:
        return float(shares_str)  # 如果没有单位标识符，直接返回原始字符串
    except ValueError:
        return 0  # 如果无法转换为浮点数，返回0

# 首先添加一个处理公司名称的函数
def clean_company_name(name):
    # 移除常见的公司后缀
    suffixes = [
        ', Inc.',
        ' Inc.',
        ', LLC',
        ' LLC',
        ', Ltd.',
        ' Ltd.',
        ', Limited',
        ' Limited',
        ', Corp.',
        ' Corp.',
        ', Corporation',
        ' Corporation',
        ', Co.',
        ' Co.',
        ', Company',
        ' Company',
        ' Bros'
    ]
    
    cleaned_name = name
    for suffix in suffixes:
        cleaned_name = cleaned_name.replace(suffix, '')
    
    return cleaned_name.strip()

# 读取JSON文件获取股票符号
def get_stock_symbols_from_json(json_file_path):
    with open(json_file_path, 'r') as file:
        sectors_data = json.load(file)
    
    # 只提取指定分类的股票符号
    target_sectors = [
        'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
        'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
        'Communication_Services', 'Financial_Services', 'Healthcare'
    ]
    
    stock_symbols = []
    for sector in target_sectors:
        if sector in sectors_data:
            stock_symbols.extend(sectors_data[sector])
    
    return stock_symbols

chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 从JSON文件获取股票符号
# json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
json_file_path = "/Users/yanzhang/Documents/Financial_System/Test/Sectors_All_test.json"
stock_symbols = get_stock_symbols_from_json(json_file_path)

# 创建保存数据的文件
output_file_path = "/Users/yanzhang/Downloads/marketcap.txt"
existing_symbols = set()

# 检查文件是否存在，如果存在则读取已有内容，避免重复抓取
if os.path.exists(output_file_path):
    with open(output_file_path, 'r') as file:
        for line in file:
            if ':' in line:
                symbol = line.split(':')[0].strip()
                existing_symbols.add(symbol)

# 逐个抓取股票数据
for symbol in stock_symbols:
    # 如果已经抓取过，则跳过
    if symbol in existing_symbols:
        print(f"已抓取过 {symbol}，跳过...")
        continue
    
    try:
        url = f"https://finance.yahoo.com/quote/{symbol}/key-statistics/"
        driver.get(url)
        
        # 查找公司名称
        company_name_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//h1[@class='yf-xxbei9']"))
        )
        company_name = company_name_element.text.split('(')[0].strip()
        cleaned_company_name = clean_company_name(company_name)
        
        # 查找Shares Outstanding数据
        try:
            shares_outstanding_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//td[text()='Shares Outstanding']/following-sibling::td"))
            )
            shares_outstanding = shares_outstanding_element.text
            shares_outstanding_converted = convert_shares_format(shares_outstanding)
        except Exception as e:
            print(f"无法获取 {symbol} 的Shares Outstanding: {str(e)}")
            shares_outstanding_converted = 0
        
        # 查找Market Cap数据
        try:
            market_cap_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//td[contains(text(), 'Market Cap')]/following-sibling::td[1]"))
            )
            market_cap = market_cap_element.text
            market_cap_converted = convert_shares_format(market_cap)
        except Exception as e:
            print(f"无法获取 {symbol} 的Market Cap: {str(e)}")
            market_cap_converted = 0
        
        # 查找Trailing P/E数据
        try:
            pe_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//td[contains(text(), 'Trailing P/E')]/following-sibling::td[1]"))
            )
            pe_ratio = pe_element.text
            if pe_ratio == 'N/A' or pe_ratio == '-':
                pe_ratio = 0
            else:
                pe_ratio = float(pe_ratio)
        except Exception as e:
            print(f"无法获取 {symbol} 的Trailing P/E: {str(e)}")
            pe_ratio = 0
        
        # 保存数据到文件
        with open(output_file_path, 'a') as file:
            file.write(f"{symbol}: {market_cap_converted}, {pe_ratio}, {cleaned_company_name}, {shares_outstanding_converted}\n")
        
        print(f"成功抓取 {symbol} 的数据")
    
    except Exception as e:
        print(f"抓取 {symbol} 时发生错误: {str(e)}")
    
    # 可以添加一些延迟，避免请求过于频繁
    import time
    time.sleep(2)

# 关闭浏览器
driver.quit()

print("数据抓取完成！")