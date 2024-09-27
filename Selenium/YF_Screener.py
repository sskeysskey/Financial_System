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

def login_once(driver, login_url):
    driver.get(login_url)

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "login-username"))
    )

    username_input = driver.find_element(By.ID, "login-username")
    username_input.send_keys("yansteven188@gmail.com")
    username_input.send_keys(Keys.RETURN)

    WebDriverWait(driver, 600).until(
        EC.presence_of_element_located((By.ID, "login-passwd"))
    )
    password_input = driver.find_element(By.ID, "login-passwd")
    password_input.send_keys("!@#$Abcd")
    password_input.send_keys(Keys.RETURN)
    
    # 等待找到id为header-profile-button或ybarAccountMenu其中任意一个表示登录成功
    WebDriverWait(driver, 120).until(
        EC.any_of(
            EC.presence_of_element_located((By.ID, "header-profile-button")),
            EC.presence_of_element_located((By.ID, "ybarAccountMenu"))
        )
    )
    print("登录成功，继续执行其他任务")

def is_blacklisted(symbol, blacklist):
    """检查给定的股票符号是否在黑名单中"""
    return symbol in blacklist.get('screener', [])

def load_blacklist(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def process_urls(driver, urls, output, output_500, output_5000, blacklist):
    for url, sector in urls:
        process_sector(driver, url, sector, output, output_500, output_5000, blacklist)

def fetch_data(driver, url, blacklist):
    driver.get(url)
    results = []
    quote_links = driver.find_elements(By.XPATH, '//a[@data-test="quoteLink"]')

    for quote_link in quote_links:
        symbol = quote_link.text
        if is_blacklisted(symbol, blacklist):
            continue
        
        symbol_xpath = f'//fin-streamer[@data-symbol="{symbol}"]'
        name_xpath = f'{symbol_xpath}/ancestor::tr/td[@aria-label="Name"]'
        market_cap_xpath = f'{symbol_xpath}[@data-field="marketCap"]'
        price_xpath = f'{symbol_xpath}[@data-field="regularMarketPrice"]'
        volume_xpath = f'{symbol_xpath}[@data-field="regularMarketVolume"]'
        pe_ratio_xpath = f'{symbol_xpath}/ancestor::tr/td[@aria-label="PE Ratio (TTM)"]'
        
        try:
            market_cap_element = driver.find_element(By.XPATH, market_cap_xpath)
            market_cap = market_cap_element.get_attribute('value')
            if market_cap == 'N/A':
                print(f"Market cap data for symbol {symbol} is N/A and will be skipped.")
                continue
            market_cap = float(market_cap)
        except NoSuchElementException:
            print(f"No market cap data for symbol {symbol} on Yahoo Financial website")
            continue
        except ValueError:
            print(f"Invalid market cap data for symbol {symbol} on Yahoo Financial website")
            continue

        try:
            price_element = driver.find_element(By.XPATH, price_xpath)
            price = price_element.get_attribute('value')
            if price == 'N/A':
                print(f"price data for symbol {symbol} is N/A and will be skipped.")
                continue
            price = float(price)
        except NoSuchElementException:
            print(f"No price data for symbol {symbol}")
            continue
        except ValueError:
            print(f"Invalid price data for symbol {symbol}")
            continue

        try:
            volume_element = driver.find_element(By.XPATH, volume_xpath)
            volume = volume_element.get_attribute('value')
            if volume == 'N/A':
                print(f"volume data for symbol {symbol} is N/A and will be skipped.")
                continue
            volume = float(volume)
        except NoSuchElementException:
            print(f"No volume data for symbol {symbol}")
            continue
        except ValueError:
            print(f"Invalid volume data for symbol {symbol}")
            continue
        
        try:
            pe_ratio_element = driver.find_element(By.XPATH, pe_ratio_xpath)
            pe_ratio = pe_ratio_element.text.strip()
            if pe_ratio == 'N/A':
                pe_ratio = '--'
            else:
                pe_ratio = float(pe_ratio)
        except NoSuchElementException:
            pe_ratio = '--'
        except ValueError:
            pe_ratio = '--'

        try:
            name_element = driver.find_element(By.XPATH, name_xpath)
            name = name_element.text.strip()
        except NoSuchElementException:
            name = '--'

        results.append((symbol, market_cap, pe_ratio, name, price, volume))
        
    # 将结果写入到 txt 文件
    with open('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt', 'a') as file:  # 修改 'w' 为 'a'
        for result in results:
            file.write(f"{result[0]}: {result[1]}, {result[2]}\n")
    with open('/Users/yanzhang/Documents/News/backup/price_volume.txt', 'a') as file:  # 修改 'w' 为 'a'
        for result in results:
            file.write(f"{result[0]}: {result[4]}, {result[5]}\n")
    return results

def update_json(data, sector, file_path, output, log_enabled, write_symbols=False):
    with open(file_path, 'r+') as file:
        json_data = json.load(file)
        
        # 创建一个反向映射，用于查找符号当前所在的sector
        current_sectors = {}
        for sec in json_data:
            for symbol in json_data[sec]:
                current_sectors[symbol] = sec
        
        # 创建一个集合，包含所有组别的所有符号
        all_symbols = set()
        for sec, symbols in json_data.items():
            all_symbols.update(symbols)

        new_symbols = []  # 用于存储新添加的符号和名称

        for symbol, market_cap, pe_ratio, name, price, volume in data:
            current_sector = current_sectors.get(symbol)
            
            # 检查市值是否小于50亿，如果是，则可能需要移除
            if market_cap < 5000000000:
                if current_sector and symbol in json_data[current_sector]:
                    # json_data[current_sector].remove(symbol)
                    if log_enabled:
                        message = f"'{symbol}' should be Removed from {current_sector}."
                        print(message)
                        output.append(message)
            else:
                # 市值大于等于50亿，需要加入到对应的sector中
                if symbol not in json_data[sector]:
                    json_data[sector].append(symbol)
                    new_symbols.append((symbol, name))  # 添加新的符号和名称
                    if log_enabled:
                        message = f"Added '{symbol}' to {sector} due to a new rising star."
                        print(message)
                        output.append(message)
                        if symbol in all_symbols:
                            for sec, symbols in json_data.items():
                                if symbol in symbols:
                                    error_message = f"'{symbol}' 已经在 {sec} 中了，请处理。"
                                    print(error_message)
                                    log_error_with_timestamp(error_message, ERROR_FILE_PATH)

        # 重写文件内容
        file.seek(0)
        file.truncate()
        json.dump(json_data, file, indent=2)

    if new_symbols and write_symbols:
        with open('/Users/yanzhang/Documents/News/backup/symbol_names.txt', 'a') as symbol_file:
            for symbol, name in new_symbols:
                symbol_file.write(f"{symbol}: {name}\n")  # 修改为确保每个symbol在新行中写入

def update_json_500(data, sector, file_path_500, output_500, log_enabled):
    with open(file_path_500, 'r+') as file:
        json_data = json.load(file)
        
        # 创建一个反向映射，用于查找符号当前所在的sector
        current_sectors = {}
        for sec in json_data:
            for symbol in json_data[sec]:
                current_sectors[symbol] = sec
        
        # 创建一个集合，包含所有组别的所有符号
        all_symbols = set()
        for sec, symbols in json_data.items():
            all_symbols.update(symbols)

        for symbol, market_cap, pe_ratio, name, price, volume in data:
            current_sector = current_sectors.get(symbol)
            if market_cap > 50000000000:  # 500亿
                if symbol not in json_data[sector]:
                    json_data[sector].append(symbol)
                    if log_enabled:
                        message = f"Added '{symbol}' to {sector} in Sectors_500.json due to market cap > 500亿."
                        print(message)
                        output_500.append(message)
                        if symbol in all_symbols:
                            for sec, symbols in json_data.items():
                                if symbol in symbols:
                                    error_message = f"500亿里的 '{symbol}' 已经在 {sec} 中存在了，请处理。"
                                    print(error_message)
                                    log_error_with_timestamp(error_message, ERROR_FILE_PATH)
        # 重写文件内容
        file.seek(0)
        file.truncate()
        json.dump(json_data, file, indent=2)

def update_json_5000(data, sector, file_path_5000, output_5000, log_enabled):
    with open(file_path_5000, 'r+') as file:
        json_data = json.load(file)
        
        # 创建一个反向映射，用于查找符号当前所在的sector
        current_sectors = {}
        for sec in json_data:
            for symbol in json_data[sec]:
                current_sectors[symbol] = sec
        
        # 创建一个集合，包含所有组别的所有符号
        all_symbols = set()
        for sec, symbols in json_data.items():
            all_symbols.update(symbols)

        for symbol, market_cap, pe_ratio, name, price, volume in data:
            current_sector = current_sectors.get(symbol)
            if market_cap > 500000000000:  # 5000亿
                if symbol not in json_data[sector]:
                    json_data[sector].append(symbol)
                    if log_enabled:
                        message = f"Added '{symbol}' to {sector} in Sectors_5000.json due to market cap > 5000亿."
                        print(message)
                        output_5000.append(message)
                        if symbol in all_symbols:
                            for sec, symbols in json_data.items():
                                if symbol in symbols:
                                    error_message = f"5000亿里的 '{symbol}' 已经在 {sec} 中存在了，请处理。"
                                    print(error_message)
                                    log_error_with_timestamp(error_message, ERROR_FILE_PATH)
        # 重写文件内容
        file.seek(0)
        file.truncate()
        json.dump(json_data, file, indent=2)

def process_sector(driver, url, sector, output, output_500, output_5000, blacklist):
    data = fetch_data(driver, url, blacklist)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', output, log_enabled=True, write_symbols=True)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json', output, log_enabled=False, write_symbols=False)
    # 处理 Sectors_500.json
    update_json_500(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_500.json', output_500, log_enabled=True)
    # 处理 Sectors_5000.json
    update_json_5000(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_5000.json', output_5000, log_enabled=True)

def save_output_to_file(output, directory, filename='Stock_50.txt'):
    if not output:  # 如果输出列表为空，直接返回
        print(f"没有内容需要保存到 {filename}")
        return

    current_time = datetime.now().strftime('%m%d')
    # 在文件名中加入时间戳
    filename = f"{filename.split('.')[0]}_{current_time}.txt"
    # 创建文件夹如果它不存在
    if not os.path.exists(directory):
        os.makedirs(directory)
    # 定义完整的文件路径
    file_path = os.path.join(directory, filename)
    # 将输出写入到文件
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write("\n".join(output))
    print(f"输出已保存到文件：{file_path}")

def clean_old_backups(directory, file_patterns, days=4):
    """
    删除备份目录中超过指定天数的文件
    
    :param directory: 备份文件所在的目录
    :param file_patterns: 要清理的文件模式列表，每个元素是一个元组 (前缀, 日期位置)
    :param days: 保留的天数
    """
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    for filename in os.listdir(directory):
        for prefix, date_position in file_patterns:
            if filename.startswith(prefix):
                try:
                    parts = filename.split('_')
                    date_str = parts[date_position].split('.')[0]  # 获取日期部分
                    file_date = datetime.strptime(date_str, '%m%d')
                    file_date = file_date.replace(year=now.year)
                    
                    if file_date < cutoff:
                        file_path = os.path.join(directory, filename)
                        os.remove(file_path)
                        print(f"删除旧备份文件：{file_path}")
                    break  # 文件已处理，无需检查其他模式
                except Exception as e:
                    print(f"跳过文件：{filename}，原因：{e}")

def log_error_with_timestamp(error_message, file_path):
    """记录带时间戳的错误信息"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(file_path, 'a') as error_file:
        error_file.write(f"[{timestamp}] {error_message}\n")

def backup_file(file_name, source_dir, backup_dir):
    file_path = os.path.join(source_dir, file_name)
    if os.path.exists(file_path):
        yesterday = datetime.now() - timedelta(days=1)
        timestamp = yesterday.strftime('%m%d')

        name, extension = os.path.splitext(file_name)
        new_filename = f"{name}_{timestamp}{extension}"
        new_file_path = os.path.join(backup_dir, new_filename)

        os.rename(file_path, new_file_path)
        print(f"文件已重命名为: {new_file_path}")
        return True
    else:
        print(f"文件不存在: {file_path}")
        return False

chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 加载blacklist.json文件
blacklist_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'
blacklist = load_blacklist(blacklist_file_path)

output = []  # 用于收集50亿以上信息的列表
output_500 = []  # 用于收集500亿以上信息的列表
output_5000 = []  # 用于收集5000亿以上信息的列表
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
    login_once(driver, login_url)
    process_urls(driver, urls, output, output_500, output_5000, blacklist)
finally:
    driver.quit()
print("所有爬取任务完成。")

# 在代码的最后部分调用save_output_to_file函数
output_directory = '/Users/yanzhang/Documents/News'
save_output_to_file(output, output_directory, filename='Stock_50.txt')
if output_500:  # 只有在 output_500 不为空时才保存
    save_output_to_file(output_500, output_directory, filename='Stock_500.txt')
if output_5000:  # 只有在 output_5000 不为空时才保存
    save_output_to_file(output_5000, output_directory, filename='Stock_5000.txt')

# 定义要清理的文件模式
file_patterns = [
    ("marketcap_pe_", -1),  # 日期在最后一个下划线后
    ("price_volume_", -1)
]

# 调用清理旧备份文件的函数
clean_old_backups(backup_directory, file_patterns)