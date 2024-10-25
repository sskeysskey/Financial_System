import os
import json
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support import expected_conditions as EC
import pyautogui
import random
import time
import threading

# 添加鼠标移动功能的函数
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

# 登录函数
def login_once(driver, login_url, username, password):
    driver.get(login_url)
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "login-username")))
    username_input = driver.find_element(By.ID, "login-username")
    username_input.send_keys(username)
    username_input.send_keys(Keys.RETURN)

    WebDriverWait(driver, 600).until(EC.presence_of_element_located((By.ID, "login-passwd")))
    password_input = driver.find_element(By.ID, "login-passwd")
    password_input.send_keys(password)
    password_input.send_keys(Keys.RETURN)

    WebDriverWait(driver, 120).until(EC.any_of(
        EC.presence_of_element_located((By.ID, "header-profile-button")),
        EC.presence_of_element_located((By.ID, "ybarMailIndicator")),
        EC.presence_of_element_located((By.ID, "ybarAccountMenu"))
    ))
    print("登录成功，继续执行其他任务")

# 检查是否在黑名单中
def is_blacklisted(symbol, blacklist):
    """检查给定的股票符号是否在黑名单中"""
    return symbol in blacklist.get('screener', [])

# 加载黑名单
def load_blacklist(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def process_urls(driver, urls, output, output_500, output_5000, blacklist):
    for url, sector in urls:
        process_sector(driver, url, sector, output, output_500, output_5000, blacklist)

# 辅助函数，用于获取元素并处理异常
def get_element_value(driver, xpath, default='--', as_float=False):
    try:
        element = driver.find_element(By.XPATH, xpath)
        value = element.get_attribute('value') if as_float else element.text.strip()
        # 如果是浮点数模式，则转换为浮点数
        if as_float:
            return float(value)
        else:
            # 如果不是浮点数模式，专门处理 "N/A" 的情况
            return float(value) if value != 'N/A' else default
    except (NoSuchElementException, ValueError):
        return default

def get_element_name(driver, xpath, default='--'):
    try:
        element = driver.find_element(By.XPATH, xpath)
        value = element.text.strip()
        return value
    except (NoSuchElementException, ValueError):
        return default

def fetch_data(driver, url, blacklist):
    driver.get(url)
    results = []
    quote_links = driver.find_elements(By.XPATH, '//a[@data-test="quoteLink"]')

    for quote_link in quote_links:
        symbol = quote_link.text
        if is_blacklisted(symbol, blacklist):
            continue
        
        # 使用辅助函数来获取数据
        symbol_xpath = f'//fin-streamer[@data-symbol="{symbol}"]'
        market_cap = get_element_value(driver, f'{symbol_xpath}[@data-field="marketCap"]', as_float=True)
        price = get_element_value(driver, f'{symbol_xpath}[@data-field="regularMarketPrice"]', as_float=True)
        volume = get_element_value(driver, f'{symbol_xpath}[@data-field="regularMarketVolume"]', as_float=True)
        pe_ratio = get_element_value(driver, f'{symbol_xpath}/ancestor::tr/td[@aria-label="PE Ratio (TTM)"]', as_float=False)
        name = get_element_name(driver, f'{symbol_xpath}/ancestor::tr/td[@aria-label="Name"]')

        if market_cap != '--':
            results.append((symbol, market_cap, pe_ratio, name, price, volume))
        
    # 将结果写入到 txt 文件
    with open('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt', 'a') as file:  # 修改 'w' 为 'a'
        for result in results:
            file.write(f"{result[0]}: {result[1]}, {result[2]}\n")
    with open('/Users/yanzhang/Documents/News/backup/price_volume.txt', 'a') as file:  # 修改 'w' 为 'a'
        for result in results:
            file.write(f"{result[0]}: {result[4]}, {result[5]}\n")
    return results

# 辅助函数：将市值转换为“亿”单位
def simplify_market_cap_threshold(market_cap_threshold):
    """将市值门槛除以1e8，返回简化后的数字"""
    return market_cap_threshold / 1e8

# 通用的更新JSON函数
def update_json(data, sector, file_path, output, log_enabled, market_cap_threshold, write_symbols=False):
    with open(file_path, 'r+') as file:
        json_data = json.load(file)
        current_sectors = {symbol: sec for sec, symbols in json_data.items() for symbol in symbols}
        all_symbols = set(current_sectors.keys())
        new_symbols = []

        # 计算简化后的市值门槛
        simplified_market_cap_threshold = simplify_market_cap_threshold(market_cap_threshold)

        for symbol, market_cap, pe_ratio, name, price, volume in data:
            current_sector = current_sectors.get(symbol)

            # 市值判断逻辑
            if market_cap < market_cap_threshold:
                if current_sector and symbol in json_data[current_sector]:
                    if log_enabled:
                        message = f"'{symbol}' should be Removed from {current_sector} {int(simplified_market_cap_threshold)}."
                        print(message)
                        output.append(message)
            else:
                if symbol not in json_data[sector]:
                    json_data[sector].append(symbol)
                    new_symbols.append((symbol, name))
                    if log_enabled:
                        # 在这里将简化后的市值门槛值加入消息
                        message = f"Added '{symbol}' to {sector} {int(simplified_market_cap_threshold)}."
                        print(message)
                        output.append(message)

        file.seek(0)
        file.truncate()
        json.dump(json_data, file, indent=2)

    if new_symbols and write_symbols:
        with open('/Users/yanzhang/Documents/News/backup/symbol_names.txt', 'a') as symbol_file:
            for symbol, name in new_symbols:
                symbol_file.write(f"{symbol}: {name}\n")

# 处理不同的市值条件
def process_sector(driver, url, sector, output, output_500, output_5000, blacklist):
    data = fetch_data(driver, url, blacklist)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', output, log_enabled=True, market_cap_threshold=5000000000, write_symbols=True)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json', output, log_enabled=False, market_cap_threshold=5000000000)

    # 处理 500 亿和 5000 亿市值
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_500.json', output_500, log_enabled=True, market_cap_threshold=50000000000)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_5000.json', output_5000, log_enabled=True, market_cap_threshold=500000000000)

# 保存输出到文件
def save_output_to_file(output, directory, filename):
    if not output:
        print(f"没有内容需要保存到 {filename}")
        return

    current_time = datetime.now().strftime('%m%d')
    filename = f"{filename.split('.')[0]}_{current_time}.txt"
    os.makedirs(directory, exist_ok=True)
    file_path = os.path.join(directory, filename)
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write("\n".join(output))
    print(f"输出已保存到文件：{file_path}")

# 删除旧备份
def clean_old_backups(directory, file_patterns, days=4):
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    for filename in os.listdir(directory):
        for prefix, date_position in file_patterns:
            if filename.startswith(prefix):
                try:
                    date_str = filename.split('_')[date_position].split('.')[0]
                    file_date = datetime.strptime(date_str, '%m%d').replace(year=now.year)
                    if file_date < cutoff:
                        file_path = os.path.join(directory, filename)
                        os.remove(file_path)
                        print(f"删除旧备份文件：{file_path}")
                    break
                except Exception as e:
                    print(f"跳过文件：{filename}，原因：{e}")

def log_error_with_timestamp(error_message, file_path):
    """记录带时间戳的错误信息"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(file_path, 'a') as error_file:
        error_file.write(f"[{timestamp}] {error_message}\n")

# 备份文件
def backup_file(file_name, source_dir, backup_dir):
    file_path = os.path.join(source_dir, file_name)
    if os.path.exists(file_path):
        timestamp = (datetime.now() - timedelta(days=1)).strftime('%m%d')
        new_filename = f"{os.path.splitext(file_name)[0]}_{timestamp}{os.path.splitext(file_name)[1]}"
        new_file_path = os.path.join(backup_dir, new_filename)
        os.rename(file_path, new_file_path)
        print(f"文件已重命名为: {new_file_path}")
        return True
    print(f"文件不存在: {file_path}")
    return False

# 在主程序开始前启动鼠标移动线程
mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
mouse_thread.start()

# 主程序逻辑
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 加载blacklist.json文件
blacklist_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'
blacklist = load_blacklist(blacklist_file_path)

output, output_500, output_5000 = [], [], []
ERROR_FILE_PATH = '/Users/yanzhang/Documents/News/Today_error.txt'

# 定义源目录和备份目录
source_directory = '/Users/yanzhang/Documents/News/backup/'
backup_directory = '/Users/yanzhang/Documents/News/site/'

# 需要备份的文件列表
files_to_backup = ['marketcap_pe.txt', 'price_volume.txt']

# 对每个文件执行备份操作
for file in files_to_backup:
    backup_file(file, source_directory, backup_directory)

login_url = "https://login.yahoo.com"
urls = [
    ('https://finance.yahoo.com/screener/511d9b57-07dd-4d6a-8188-0c812754034f?offset=0&count=100',
    'Technology'),
    ('https://finance.yahoo.com/screener/511d9b57-07dd-4d6a-8188-0c812754034f?count=100&offset=100',
    'Technology'),
    ('https://finance.yahoo.com/screener/511d9b57-07dd-4d6a-8188-0c812754034f?count=100&offset=200',
    'Technology'),
    ('https://finance.yahoo.com/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b?offset=0&count=100',
    'Industrials'),
    ('https://finance.yahoo.com/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b?count=100&offset=100',
    'Industrials'),
    ('https://finance.yahoo.com/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78?offset=0&count=100',
    'Financial_Services'),
    ('https://finance.yahoo.com/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78?count=100&offset=100',
    'Financial_Services'),
    ('https://finance.yahoo.com/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78?count=100&offset=200',
    'Financial_Services'),
    ('https://finance.yahoo.com/screener/e5221069-608f-419e-a3ff-24e61e4a07ac?offset=0&count=100',
    'Basic_Materials'),
    ('https://finance.yahoo.com/screener/90966b0c-2902-425c-870a-f19eb1ffd0b8?offset=0&count=100',
    'Consumer_Defensive'),
    ('https://finance.yahoo.com/screener/84e650e0-3916-4907-ad56-2fba4209fa3f?offset=0&count=100',
    'Utilities'),
    ('https://finance.yahoo.com/screener/1788e450-82cf-449a-b284-b174e8e3f6d6?offset=0&count=100',
    'Energy'),
    ('https://finance.yahoo.com/screener/877aec73-036f-40c3-9768-1c03e937afb7?offset=0&count=100',
    'Consumer_Cyclical'),
    ('https://finance.yahoo.com/screener/877aec73-036f-40c3-9768-1c03e937afb7?count=100&offset=100',
    'Consumer_Cyclical'),
    ('https://finance.yahoo.com/screener/9a217ba3-966a-4340-83b9-edb160f05f8e?offset=0&count=100',
    'Real_Estate'),
    ('https://finance.yahoo.com/screener/f99d96f0-a144-48be-b220-0be74c55ebf4?offset=0&count=100',
    'Healthcare'),
    ('https://finance.yahoo.com/screener/f99d96f0-a144-48be-b220-0be74c55ebf4?count=100&offset=100',
    'Healthcare'),
    ('https://finance.yahoo.com/screener/360b16ee-2692-4617-bd1a-a6c715dd0c29?offset=0&count=100',
    'Communication_Services'),
]

try:
    login_once(driver, login_url, "yansteven188@gmail.com", "2345@Abcd")
    for url, sector in urls:
        process_sector(driver, url, sector, output, output_500, output_5000, blacklist)
finally:
    driver.quit()

output_directory = '/Users/yanzhang/Documents/News'
save_output_to_file(output, output_directory, filename='Stock_50.txt')
save_output_to_file(output_500, output_directory, filename='Stock_500.txt')
save_output_to_file(output_5000, output_directory, filename='Stock_5000.txt')

# 定义要清理的文件模式
file_patterns = [
    ("marketcap_pe_", -1),  # 日期在最后一个下划线后
    ("price_volume_", -1)
]

# 调用清理旧备份文件的函数
clean_old_backups(backup_directory, file_patterns)