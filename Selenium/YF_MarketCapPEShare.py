from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import os
import re
import json
import time
import random
import pyautogui
import threading

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
        ' Bros',
        ' plc',
        ' Group',
        ' S.A.',
        ' N.V.',
        ' Holdings',
        ' S.A.B.',
        ' C.V.',
        ' Ltd',
        ' Holding',
        ' Companies',
        ' PLC',
        '& plc',
        ' Incorporated',
        ' AG',
        ' &',
        ' SE',
        '- Petrobras',
        ' L.P.',
        ', L.P.',
        ', LP',
        'de C.V.',
        ' Inc',
        ', Incorporated'
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

# 获取已处理的股票符号列表
def get_existing_symbols(file_path):
    existing_symbols = set()
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if ':' in line:
                    symbol = line.split(':')[0].strip()
                    existing_symbols.add(symbol)
    return existing_symbols

# 添加鼠标移动功能的函数x
def move_mouse_periodically():
    while True:
        try:
            # 获取屏幕尺寸
            screen_width, screen_height = pyautogui.size()
            
            # 随机生成目标位置，避免移动到屏幕边缘
            x = random.randint(100, screen_width - 100)
            y = random.randint(100, screen_height - 100)
            
            # 缓慢移动鼠标到随机位置
            pyautogui.moveTo(x, y, duration=1)
            
            # 等待30-60秒再次移动
            time.sleep(random.randint(30, 60))
            
        except Exception as e:
            print(f"鼠标移动出错: {str(e)}")
            time.sleep(30)

# 在主程序开始前启动鼠标移动线程
mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
mouse_thread.start()

# 设置Chrome选项以提高性能
chrome_options = Options()
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

# 设置ChromeDriver路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

# 设置更短的超时时间
driver.set_page_load_timeout(20)  # 页面加载超时时间
driver.set_script_timeout(10)  # 脚本执行超时时间

# 从JSON文件获取股票符号
json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
# json_file_path = "/Users/yanzhang/Documents/Financial_System/Test/Sectors_All_test.json"
stock_symbols = get_stock_symbols_from_json(json_file_path)

# 定义输出文件路径
# shares_file_path = "/Users/yanzhang/Documents/News/backup/Shares.txt"
shares_file_path = "/Users/yanzhang/Downloads/Shares.txt"

# symbol_names_file_path = "/Users/yanzhang/Documents/News/backup/symbol_names.txt"
symbol_names_file_path = "/Users/yanzhang/Downloads/symbol_names.txt"

marketcap_pe_file_path = "/Users/yanzhang/Downloads/marketcap_pe.txt"

# 获取已处理的股票符号
existing_shares = get_existing_symbols(shares_file_path)
existing_names = get_existing_symbols(symbol_names_file_path)
existing_marketcap_pe = get_existing_symbols(marketcap_pe_file_path)

# 合并所有已处理的符号
all_processed = existing_shares.union(existing_names).union(existing_marketcap_pe)

# 优化等待策略的函数
def wait_for_element(driver, by, value, timeout=10):
    """等待元素加载完成并返回"""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        return element
    except Exception as e:
        return None

# 逐个抓取股票数据
for symbol in stock_symbols:
    # 如果已经处理过，则跳过
    if symbol in all_processed:
        print(f"已抓取过 {symbol}，跳过...")
        continue
    
    try:
        url = f"https://finance.yahoo.com/quote/{symbol}/key-statistics/"
        driver.get(url)
        
        # 首先等待公司名称出现，这通常是最快加载的元素之一
        company_name_element = wait_for_element(driver, By.XPATH, "//h1[@class='yf-xxbei9']", timeout=5)
        
        if company_name_element:
            company_name = company_name_element.text.split('(')[0].strip()
            cleaned_company_name = clean_company_name(company_name)
            
            # 保存公司名称到symbol_names.txt
            with open(symbol_names_file_path, 'a', encoding='utf-8') as file:
                file.write(f"{symbol}: {cleaned_company_name}\n")
            
            print(f"已保存 {symbol} 的公司名称: {cleaned_company_name}")
        else:
            print(f"无法获取 {symbol} 的公司名称")
            cleaned_company_name = symbol  # 如果无法获取公司名称，使用股票符号作为替代
        
        # 查找Shares Outstanding数据
        shares_outstanding_element = wait_for_element(driver, By.XPATH, "//td[text()='Shares Outstanding']/following-sibling::td", timeout=3)
        if shares_outstanding_element:
            shares_outstanding = shares_outstanding_element.text
            shares_outstanding_converted = convert_shares_format(shares_outstanding)
            
            # 保存股票数量到Shares.txt
            with open(shares_file_path, 'a', encoding='utf-8') as file:
                file.write(f"{symbol}: {int(shares_outstanding_converted)}\n")
            
            print(f"已保存 {symbol} 的股票数量: {int(shares_outstanding_converted)}")
        else:
            print(f"无法获取 {symbol} 的股票数量")
        
        # 查找Market Cap数据
        market_cap_element = wait_for_element(driver, By.XPATH, "//td[contains(text(), 'Market Cap')]/following-sibling::td[1]", timeout=3)
        market_cap_converted = 0
        if market_cap_element:
            market_cap = market_cap_element.text
            market_cap_converted = convert_shares_format(market_cap)
        
        # 查找Trailing P/E数据
        pe_element = wait_for_element(driver, By.XPATH, "//td[contains(text(), 'Trailing P/E')]/following-sibling::td[1]", timeout=3)
        pe_str = "--"  # 默认为--，表示没有PE值
        if pe_element:
            pe_ratio_text = pe_element.text
            if pe_ratio_text != 'N/A' and pe_ratio_text != '-':
                try:
                    pe_ratio = float(pe_ratio_text)
                    pe_str = str(pe_ratio)
                except ValueError:
                    pass
        
        # 保存市值和PE到marketcap_pe.txt
        with open(marketcap_pe_file_path, 'a', encoding='utf-8') as file:
            file.write(f"{symbol}: {market_cap_converted}, {pe_str}\n")
        
        print(f"已保存 {symbol} 的市值和PE: {market_cap_converted}, {pe_str}")
        
        print(f"成功抓取 {symbol} 的所有数据")
    
    except Exception as e:
        print(f"抓取 {symbol} 时发生错误: {str(e)}")
    
    # 添加短暂延迟，避免请求过于频繁
    time.sleep(1)

# 关闭浏览器
driver.quit()

print("数据抓取完成！")