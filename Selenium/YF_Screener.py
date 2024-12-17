import os
import json
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
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
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

def process_urls(driver, urls, output, output_500, output_5000, blacklist):
    for url, sector in urls:
        process_sector(driver, url, sector, output, output_500, output_5000, blacklist)

def retry_on_stale(max_attempts=3):
    """装饰器: 处理StaleElementReferenceException"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except StaleElementReferenceException:
                    if attempt == max_attempts - 1:
                        raise
                    print(f"Stale element, retrying... (attempt {attempt + 1})")
            return None
        return wrapper
    return decorator

def fetch_data(driver, url, blacklist):
    driver.get(url)
    results = []
    
    try:
        # 等待页面加载完成
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "tbody"))
        )
        
        @retry_on_stale(max_attempts=3)
        def extract_row_data(row):
            """提取单行数据"""
            # 使用WebDriverWait确保元素可见
            wait = WebDriverWait(row, 5)
            
            symbol = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span.symbol"))
            ).text.strip()
            
            name = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.lalign"))
            ).text.strip()
            
            price = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "fin-streamer[data-field='regularMarketPrice']"))
            ).text.strip()
            
            volume = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "fin-streamer[data-field='regularMarketVolume']"))
            ).text.strip()
            
            market_cap = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "fin-streamer[data-field='marketCap']"))
            ).text.strip()
            
            pe_ratio = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "fin-streamer[data-field='peRatioLtm']"))
            ).text.strip()
            
            return symbol, name, price, volume, market_cap, pe_ratio

        # 获取所有行
        rows = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//table/tbody/tr"))
        )
        
        for row in rows:
            try:
                symbol, name, price, volume, market_cap, pe_ratio = extract_row_data(row)
                
                if is_blacklisted(symbol, blacklist):
                    continue
                    
                # 数据处理
                price_parsed = parse_number(price)
                volume_parsed = parse_volume(volume)
                market_cap_parsed = parse_market_cap(market_cap)
                pe_ratio_parsed = parse_number(pe_ratio)
                
                if market_cap_parsed != '--':
                    results.append((
                        symbol,
                        market_cap_parsed,
                        pe_ratio_parsed,
                        name,
                        price_parsed,
                        volume_parsed
                    ))
                    
            except Exception as e:
                print(f"处理行时出错: {str(e)}")
                continue
                
        write_results_to_files(results)
        return results
        
    except TimeoutException:
        print("页面加载超时")
        return []

def parse_number(text):
    """
    解析数字，处理无效值、负数、逗号等特殊情况
    """
    try:
        if isinstance(text, (int, float)):
            return float(text)
            
        if not isinstance(text, str):
            return '--'
            
        # 处理无效值
        if text in ['--', '-', '', 'N/A']:
            return '--'
            
        # 清理文本
        clean_text = text.strip()
        
        # 如果是带span标签的文本，提取数字部分
        if '<span' in clean_text:
            # 使用简单的文本提取方法
            clean_text = clean_text.split('>')[1].split('<')[0].strip()
        
        # 移除所有逗号和多余的空格
        clean_text = clean_text.replace(',', '').replace(' ', '')
        
        # 转换为浮点数
        return float(clean_text)
        
    except (ValueError, AttributeError, IndexError) as e:
        print(f"数字解析错误: {text} - {str(e)}")
        return '--'

def parse_volume(text):
    """解析交易量"""
    if text in ['--', '-', '']:
        return '--'
    multiplier = 1
    if 'M' in text:
        multiplier = 1e6
        text = text.replace('M', '')
    elif 'K' in text:
        multiplier = 1e3
        text = text.replace('K', '')
    return float(text.replace(',', '')) * multiplier

def parse_market_cap(text):
    """解析市值，并确保精确的整数输出"""
    if text in ['--', '-', '']:
        return '--'
        
    multiplier = 1
    clean_text = text.strip()
    
    if 'T' in clean_text:
        multiplier = 1e12
        clean_text = clean_text.replace('T', '')
    elif 'B' in clean_text:
        multiplier = 1e9
        clean_text = clean_text.replace('B', '')
    elif 'M' in clean_text:
        multiplier = 1e6
        clean_text = clean_text.replace('M', '')
        
    return float(clean_text.replace(',', '')) * multiplier

def write_results_to_files(results):
    """批量写入文件"""
    with open('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt', 'a', encoding='utf-8') as f1, \
         open('/Users/yanzhang/Documents/News/backup/price_volume.txt', 'a', encoding='utf-8') as f2:
        for result in results:
            f1.write(f"{result[0]}: {result[1]}, {result[2]}\n")
            f2.write(f"{result[0]}: {result[4]}, {result[5]}\n")

# 辅助函数：将市值转换为“亿”单位
def simplify_market_cap_threshold(market_cap_threshold):
    """将市值门槛除以1e8，返回简化后的数字"""
    return market_cap_threshold / 1e8

# 通用的更新JSON函数
def update_json(data, sector, file_path, output, log_enabled, market_cap_threshold, write_symbols=False):
    with open(file_path, 'r+', encoding='utf-8') as file:
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
                if symbol not in json_data.get(sector, []):
                    json_data.setdefault(sector, []).append(symbol)
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
        with open('/Users/yanzhang/Documents/News/backup/symbol_names.txt', 'a', encoding='utf-8') as symbol_file:
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

    current_time = datetime.now().strftime('%y%m%d')
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
                    file_date = datetime.strptime(date_str, '%y%m%d').replace(year=now.year)
                    if file_date < cutoff:
                        file_path = os.path.join(directory, filename)
                        os.remove(file_path)
                        print(f"删除旧备份文件：{file_path}")
                    break
                except Exception as e:
                    print(f"跳过文件：{filename}，原因：{e}")

# 备份文件
def backup_file(file_name, source_dir, backup_dir):
    file_path = os.path.join(source_dir, file_name)
    if os.path.exists(file_path):
        timestamp = (datetime.now() - timedelta(days=1)).strftime('%y%m%d')
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
    ('https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=0&count=100', 'Technology'),
    ('https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=100&count=100', 'Technology'),
    ('https://finance.yahoo.com/research-hub/screener/511d9b57-07dd-4d6a-8188-0c812754034f/?start=200&count=100', 'Technology'),
    ('https://finance.yahoo.com/research-hub/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b/?start=0&count=100', 'Industrials'),
    ('https://finance.yahoo.com/research-hub/screener/8e86de0a-46e0-469f-85d0-a367d5aa6e6b/?start=100&count=100', 'Industrials'),
    ('https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=0&count=100', 'Financial_Services'),
    ('https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=100&count=100', 'Financial_Services'),
    ('https://finance.yahoo.com/research-hub/screener/45ecdc79-d64e-46ce-8491-62261d2f0c78/?start=200&count=100', 'Financial_Services'),
    ('https://finance.yahoo.com/research-hub/screener/e5221069-608f-419e-a3ff-24e61e4a07ac/?start=0&count=100', 'Basic_Materials'),
    ('https://finance.yahoo.com/research-hub/screener/90966b0c-2902-425c-870a-f19eb1ffd0b8/?start=0&count=100', 'Consumer_Defensive'),
    ('https://finance.yahoo.com/research-hub/screener/84e650e0-3916-4907-ad56-2fba4209fa3f/?start=0&count=100', 'Utilities'),
    ('https://finance.yahoo.com/research-hub/screener/1788e450-82cf-449a-b284-b174e8e3f6d6/?start=0&count=100', 'Energy'),
    ('https://finance.yahoo.com/research-hub/screener/877aec73-036f-40c3-9768-1c03e937afb7/?start=0&count=100', 'Consumer_Cyclical'),
    ('https://finance.yahoo.com/research-hub/screener/877aec73-036f-40c3-9768-1c03e937afb7/?start=100&count=100', 'Consumer_Cyclical'),
    ('https://finance.yahoo.com/research-hub/screener/9a217ba3-966a-4340-83b9-edb160f05f8e/?start=0&count=100', 'Real_Estate'),
    ('https://finance.yahoo.com/research-hub/screener/f99d96f0-a144-48be-b220-0be74c55ebf4/?start=0&count=100', 'Healthcare'),
    ('https://finance.yahoo.com/research-hub/screener/f99d96f0-a144-48be-b220-0be74c55ebf4/?start=100&count=100', 'Healthcare'),
    ('https://finance.yahoo.com/research-hub/screener/360b16ee-2692-4617-bd1a-a6c715dd0c29/?start=0&count=100', 'Communication_Services'),
]

try:
    login_once(driver, login_url, "yansteven188@gmail.com", "2345@Abcd")
    for url, sector in urls:
        process_sector(driver, url, sector, output, output_500, output_5000, blacklist)
finally:
    driver.quit()

output_directory = '/Users/yanzhang/Documents/News/backup/backup'
save_output_to_file(output, output_directory, filename='Stock_50.txt')
save_output_to_file(output_500, output_directory, filename='Stock_500.txt')
save_output_to_file(output_5000, output_directory, filename='Stock_5000.txt')

# 定义要清理的文件模式
file_patterns = [
    ("marketcap_pe_", -1),  # 日期在最后一个下划线后
    ("price_volume_", -1),
    ("NewLow_", -1),
    ("NewLow500_", -1),
    ("NewLow5000_", -1)
]

# 调用清理旧备份文件的函数
clean_old_backups(backup_directory, file_patterns)