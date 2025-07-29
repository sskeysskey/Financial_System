# o1优化后代码
import os
import json
import pickle
import random
import time
import threading
import subprocess
from datetime import datetime, timedelta

import pyautogui
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    InvalidCookieDomainException
)

def save_cookies(driver, cookie_file):
    """
    保存Cookie到文件
    """
    with open(cookie_file, 'wb') as file:
        pickle.dump(driver.get_cookies(), file)
    print("Cookie已保存到文件。")


def load_cookies(driver, cookie_file):
    """
    从文件加载Cookie
    """
    if os.path.exists(cookie_file):
        with open(cookie_file, 'rb') as file:
            cookies = pickle.load(file)
            for cookie in cookies:
                # 删除过期的Cookie
                if 'expiry' in cookie and cookie['expiry'] < time.time():
                    continue
                driver.add_cookie(cookie)
        print("Cookie已从文件加载。")
        return True
    else:
        print("Cookie文件不存在，需要重新登录。")
        return False


def move_mouse_periodically():
    """
    定期移动鼠标位置，以防止会话或远程环境断开
    """
    while True:
        try:
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


def login_once(driver, login_url, username, password):
    """
    登录函数
    """
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
        EC.presence_of_element_located((By.ID, "ybarAccountMenu")),
        EC.presence_of_element_located((By.ID, "ybarAccountMenuOpener"))
    ))
    print("登录成功，继续执行其他任务")


def is_blacklisted(symbol, blacklist):
    """
    检查是否在黑名单中。给定的股票符号是否在黑名单中
    """
    return symbol in blacklist.get('screener', [])


def load_blacklist(file_path):
    """
    加载黑名单
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def process_urls(driver, urls, output, output_500, output_5000, blacklist):
    """
    批量处理给定的URL列表
    """
    for url, sector in urls:
        process_sector(driver, url, sector, output, output_500, output_5000, blacklist)


def retry_on_stale(max_attempts=5, delay=1):
    """
    装饰器: 处理StaleElementReferenceException并增加重试间隔
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except StaleElementReferenceException:
                    if attempt == max_attempts - 1:
                        raise
                    print(f"Stale element, retrying... (attempt {attempt + 1})")
                    time.sleep(delay)
        return wrapper
    return decorator

def fetch_data(driver, url, blacklist):
    """
    从指定URL抓取数据，并处理黑名单过滤逻辑
    """
    driver.get(url)
    results = []

    try:
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table tbody tr")))

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        rows = soup.select("table tbody tr")

        for row in rows:
            try:
                symbol = row.select_one("a[data-testid='table-cell-ticker'] span.symbol").get_text(strip=True)
                name = row.select_one("div[title]").get('title').strip()
                price = row.select_one("fin-streamer[data-field='regularMarketPrice']").get('data-value').strip()
                volume = row.select("td")[7].get_text(strip=True)
                market_cap = row.select("td")[9].get_text(strip=True)
                pe_ratio = row.select("td")[10].get_text(strip=True)

                if is_blacklisted(symbol, blacklist):
                    continue

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
    except Exception as e:
        print(f"获取数据时出错: {str(e)}")
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
        if text in ['--', '-', '', 'N/A']:
            return '--'

        clean_text = text.strip()

        if '<span' in clean_text:
            clean_text = clean_text.split('>')[1].split('<')[0].strip()

        clean_text = clean_text.replace(',', '').replace(' ', '')

        return float(clean_text)
    except (ValueError, AttributeError, IndexError) as e:
        print(f"数字解析错误: {text} - {str(e)}")
        return '--'


def parse_volume(text):
    """
    解析交易量
    """
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
    """
    解析市值，并确保精确的整数输出
    """
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
    """
    批量写入文件
    """
    with open('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt', 'a', encoding='utf-8') as f1, \
         open('/Users/yanzhang/Documents/News/backup/price_volume.txt', 'a', encoding='utf-8') as f2:
        for result in results:
            f1.write(f"{result[0]}: {result[1]}, {result[2]}\n")
            f2.write(f"{result[0]}: {result[4]}, {result[5]}\n")


def simplify_market_cap_threshold(market_cap_threshold):
    """
    将市值门槛除以1e8，返回简化后的数字
    """
    return market_cap_threshold / 1e8


def update_json(data, sector, file_path, output, log_enabled,
                market_cap_threshold, write_symbols=False, check_removal=False):
    """
    在JSON文件中更新记录，根据市值要求添加或删除股票符号
    check_removal: True表示执行删除操作(用于500亿和5000亿文件)
    """
    with open(file_path, 'r+', encoding='utf-8') as file:
        json_data = json.load(file)

        # 构建现有symbol到sectors的映射
        symbol_to_sectors = {}
        for sec, symbols in json_data.items():
            for sym in symbols:
                if sym not in symbol_to_sectors:
                    symbol_to_sectors[sym] = []
                symbol_to_sectors[sym].append(sec)

        new_symbols = []
        simplified_market_cap_threshold = simplify_market_cap_threshold(market_cap_threshold)

        # 处理每个symbol的数据
        for symbol, market_cap, pe_ratio, name, price, volume in data:
            current_sectors = symbol_to_sectors.get(symbol, [])

            if market_cap != '--' and float(market_cap) < market_cap_threshold:
                # 市值低于阈值的处理
                if check_removal:
                    # 500亿和5000亿文件执行实际删除
                    for sec in list(json_data.keys()):
                        if symbol in json_data[sec]:
                            json_data[sec].remove(symbol)
                            if log_enabled:
                                message = f"Removed '{symbol}' from {sec} due to market cap below {int(simplified_market_cap_threshold)}."
                                print(message)
                                output.append(message)
                else:
                    # 50亿文件只记录日志，不删除
                    if symbol in json_data.get(sector, []):
                        if log_enabled:
                            message = f"'{symbol}' should be Removed from {sector} {int(simplified_market_cap_threshold)}."
                            print(message)
                            output.append(message)
            else:
                # 市值达标，添加新股票
                if symbol not in json_data.get(sector, []):
                    json_data.setdefault(sector, []).append(symbol)
                    new_symbols.append((symbol, name))
                    if log_enabled:
                        message = f"Added '{symbol}' to {sector} {int(simplified_market_cap_threshold)}."
                        other_sectors = [sec for sec in current_sectors if sec != sector]
                        if other_sectors:
                            message += f" 已存在于其他 sectors: {', '.join(other_sectors)}."
                        print(message)
                        output.append(message)

        file.seek(0)
        file.truncate()
        json.dump(json_data, file, indent=2)

    if new_symbols and write_symbols:
        symbol_names_path = '/Users/yanzhang/Documents/News/backup/symbol_names.txt'
        existing_symbols = set()
        if os.path.exists(symbol_names_path):
            with open(symbol_names_path, 'r', encoding='utf-8') as symbol_file:
                for line in symbol_file:
                    if ':' in line:
                        existing_symbols.add(line.split(':')[0].strip())
        with open(symbol_names_path, 'a', encoding='utf-8') as symbol_file:
            for symbol, name in new_symbols:
                if symbol not in existing_symbols:
                    symbol_file.write(f"{symbol}: {name}\n")


def process_sector(driver, url, sector, output, output_500, output_5000, blacklist):
    """
    处理不同的市值区间，并更新相应的JSON文件
    """
    data = fetch_data(driver, url, blacklist)
    
    # 50亿普通文件，不执行删除操作
    update_json(
        data,
        sector,
        '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json',
        output,
        log_enabled=True,
        market_cap_threshold=5000000000,
        write_symbols=True,
        check_removal=False
    )
    update_json(
        data,
        sector,
        '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json',
        output,
        log_enabled=False,
        market_cap_threshold=5000000000,
        check_removal=False
    )

    # 500亿和5000亿文件，执行删除操作
    update_json(
        data,
        sector,
        '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_500.json',
        output_500,
        log_enabled=True,
        market_cap_threshold=50000000000,
        check_removal=True
    )
    update_json(
        data,
        sector,
        '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_5000.json',
        output_5000,
        log_enabled=True,
        market_cap_threshold=500000000000,
        check_removal=True
    )


def save_output_to_file(output, directory, filename):
    """
    保存输出到文件
    """
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


def clean_old_backups(directory, file_patterns, days=4):
    """
    删除超过指定天数的旧备份文件
    """
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


def backup_file(file_name, source_dir, backup_dir):
    """
    备份文件，将原文件重命名并移动到备份目录
    """
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

def display_dialog(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def check_day():
    """检查当前日期是否为周日或周一"""
    return datetime.now().weekday() in [6, 0]  # 6 代表周日，0 代表周一

def main():
    if check_day():
        message = "今天是周日或周一，不需要执行抓取操作。"
        display_dialog(message)
        return

    # 在主程序开始前启动鼠标移动线程
    mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
    mouse_thread.start()

    chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
    service = Service(executable_path=chrome_driver_path)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-animations')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--disable-popup-blocking')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')

    driver = webdriver.Chrome(service=service, options=chrome_options)
    blacklist_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'
    blacklist = load_blacklist(blacklist_file_path)

    output, output_500, output_5000 = [], [], []

    source_directory = '/Users/yanzhang/Documents/News/backup/'
    backup_directory = '/Users/yanzhang/Documents/News/backup/site'

    files_to_backup = ['marketcap_pe.txt', 'price_volume.txt']
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

    cookie_file = '/Users/yanzhang/Documents/Financial_System/Modules/yahoo_cookies.pkl'

    try:
        driver.get("https://www.yahoo.com/")
        if load_cookies(driver, cookie_file):
            driver.refresh()
            try:
                WebDriverWait(driver, 60).until(EC.any_of(
                    EC.presence_of_element_located((By.ID, "header-profile-button")),
                    EC.presence_of_element_located((By.ID, "ybarMailIndicator")),
                    EC.presence_of_element_located((By.ID, "ybarAccountMenu")),
                    EC.presence_of_element_located((By.ID, "ybarAccountMenuOpener"))
                ))
                print("通过Cookie登录成功。")
            except TimeoutException:
                print("Cookie失效，需重新登录。")
                login_once(driver, login_url, "yansteven188@gmail.com", "2345@Abcd")
                save_cookies(driver, cookie_file)
        else:
            login_once(driver, login_url, "yansteven188@gmail.com", "2345@Abcd")
            save_cookies(driver, cookie_file)

        for url, sector in urls:
            process_sector(driver, url, sector, output, output_500, output_5000, blacklist)

    finally:
        driver.quit()

    output_directory = '/Users/yanzhang/Documents/News/backup/backup'
    save_output_to_file(output, output_directory, filename='Stock_50.txt')
    save_output_to_file(output_500, output_directory, filename='Stock_500.txt')
    save_output_to_file(output_5000, output_directory, filename='Stock_5000.txt')

    file_patterns = [
        ("marketcap_pe_", -1),
        ("price_volume_", -1),
        ("NewLow_", -1),
        ("NewLow500_", -1),
        ("NewLow5000_", -1)
    ]
    clean_old_backups(backup_directory, file_patterns)

if __name__ == "__main__":
    main()