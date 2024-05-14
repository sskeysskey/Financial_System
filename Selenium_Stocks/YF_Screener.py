import json
import os
import datetime
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support import expected_conditions as EC

# 定义黑名单
blacklist = ["CTA-PA", "FWONK", "FOXA", "NWSA", "PARAA", "LSXMA",
    "LSXMB", "LBRDA", "LBTYA", "LBTYB", "LEN-B", "BF-A", "MKC-V",
    "TAP-A", "PBR-A", "BRK-B", "JPM-PD", "JPM-PC", "BML-PH",
    "BAC-PE", "BAC-PK", "BAC-PL", "BAC-PB", "BML-PL", "BML-PJ", "WFC-PY",
    "WFC-PL", "WFC-PC", "GS-PA", "GS-PK", "GS-PD", "MS-PK", "MS-PI",
    "MS-PF", "MS-PA", "MS-PE", "USB-PH", "USB-PP", "SCHW-PD",
    "MET-PA", "MET-PE", "ALL-PH", "ALL-PB", "KEY-PK", "KEY-PI",
    "KEY-PJ", "CFG-PD", "RF-PB", "RF-PC", "HIG-PG", "STT-PG",
    "GS-PC", "RNR-PF", "VOYA-PB", "BNRE-A", "OAK-PB", "ATH-PA",
    "SNV-PD", "HEI-A", "UHAL-B", "MOG-B", "SPG-PJ", "PSA-PH",
    "PSA-PK", "DLR-PK", "DLR-PJ", "NLY-PG", "NLY-PF", "MAA-PI",
    "AGNCN", "VNO-PL", "VNO-PM", "FRT-PC", "AMH-PH", "AMH-PG",
    "KIM-PM", "KIM-PL", "DUK-PA", "EBR-B", "CIG-C", "CMS-PB",
    "CWEN-A", "ELPC", "BML-PG", "SLG-PI", "NEE-PR", "APO-PA"]

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--disable-gpu')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def login_once(driver, login_url):
    driver.get(login_url)

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "login-username"))
    )

    username_input = driver.find_element(By.ID, "login-username")
    username_input.send_keys("sskeysskey@gmail.com")
    username_input.send_keys(Keys.RETURN)

    WebDriverWait(driver, 600).until(
        EC.presence_of_element_located((By.ID, "login-passwd"))
    )
    password_input = driver.find_element(By.ID, "login-passwd")
    password_input.send_keys("1234@Abcd")
    password_input.send_keys(Keys.RETURN)
    
    # 等待登录成功的标志，如重定向到登录后页面的某个特定元素
    WebDriverWait(driver, 60).until(
        EC.presence_of_element_located((By.ID, "ybarAccountMenu"))
    )
    print("登录成功，继续执行其他任务")

def is_blacklisted(symbol):
    """检查给定的股票符号是否在黑名单中"""
    return symbol in blacklist

def process_urls(driver, urls, output):
    for url, sector in urls:
        process_sector(driver, url, sector, output)

def fetch_data(driver, url):
    driver.get(url)
    results = []
    quote_links = driver.find_elements(By.XPATH, '//a[@data-test="quoteLink"]')
    
    for quote_link in quote_links:
        symbol = quote_link.text
        if is_blacklisted(symbol):
            continue
        
        symbol_xpath = f'//fin-streamer[@data-symbol="{symbol}"]'
        market_cap_xpath = f'{symbol_xpath}[@data-field="marketCap"]'
        pe_ratio_xpath = f'{symbol_xpath}/ancestor::tr/td[@aria-label="PE Ratio (TTM)"]'
        
        try:
            market_cap_element = driver.find_element(By.XPATH, market_cap_xpath)
            market_cap = market_cap_element.get_attribute('value')
            if market_cap == 'N/A':
                print(f"Market cap data for symbol {symbol} is N/A and will be skipped.")
                continue
            market_cap = float(market_cap)
        except NoSuchElementException:
            print(f"No market cap data for symbol {symbol}")
            continue
        except ValueError:
            print(f"Invalid market cap data for symbol {symbol}")
            continue

        try:
            pe_ratio_element = driver.find_element(By.XPATH, pe_ratio_xpath)
            pe_ratio = pe_ratio_element.text.strip()
            if pe_ratio == 'N/A':
                pe_ratio = 'N/A'
            else:
                pe_ratio = float(pe_ratio)
        except NoSuchElementException:
            pe_ratio = 'N/A'
        except ValueError:
            pe_ratio = 'N/A'

        results.append((symbol, market_cap, pe_ratio))
        
    # 将结果写入到 txt 文件
    with open('/Users/yanzhang/Documents/News/backup/marketcap_pe_result.txt', 'a') as file:  # 修改 'w' 为 'a'
        for result in results:
            file.write(f"{result[0]}: {result[1]}, {result[2]}\n")
    
    return results

def update_json(data, sector, file_path, output, log_enabled):
    with open(file_path, 'r+') as file:
        json_data = json.load(file)
        
        # 创建一个反向映射，用于查找符号当前所在的类别
        current_categories = {}
        for category in json_data[sector]:
            for symbol in json_data[sector][category]:
                current_categories[symbol] = category

        for symbol, market_cap, pe_ratio in data:
            current_category = current_categories.get(symbol)
            # 检查市值是否小于 Middle 分组下限
            if market_cap < 5000000000:
                if current_category:
                    # 如果市值小于下限且符号在列表中，则移除
                    json_data[sector][current_category].remove(symbol)
                    if log_enabled:
                        message = f"Removed '{symbol}' from {current_category} in {sector} due to low market cap."
                        print(message)
                        output.append(message)
            else:
                # 否则，按照原有逻辑处理市值分类
                if market_cap >= 200000000000:
                    category = "Mega"
                elif 20000000000 <= market_cap < 200000000000:
                    category = "Large"
                elif 5000000000 <= market_cap < 20000000000:
                    category = "Middle"
                else:
                    continue
                if current_category and current_category != category:
                    json_data[sector][current_category].remove(symbol)
                    if log_enabled:
                        message = f"Removed '{symbol}' from {current_category} in {sector} as it belongs to {category}."
                        print(message)
                        output.append(message)
                if symbol not in json_data[sector][category]:
                    json_data[sector][category].append(symbol)
                    if log_enabled:
                        message = f"Added '{symbol}' to {category} in {sector}."
                        print(message)
                        output.append(message)

        file.seek(0)
        file.truncate()
        json.dump(json_data, file, indent=2)

def process_sector(driver, url, sector, output):
    data = fetch_data(driver, url)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', output, log_enabled=True)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json', output, log_enabled=False)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_Stock.json', output, log_enabled=False)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_DL_2K.json', output, log_enabled=False)

def save_output_to_file(output, directory, filename='MarketCap_Change.txt'):
    # 获取当前时间，并格式化为字符串（如'2023-03-15_12-30-00'）
    current_time = datetime.datetime.now().strftime('%m_%d')
    
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

def main():
    获取当前时间
    now = datetime.datetime.now()
    # 判断今天的星期数，如果是周日(6)或周一(0)，则不执行程序
    if now.weekday() in (0, 6):
        print("Today is either Sunday or Monday. The script will not run.")
    else:
        driver = setup_driver()
        output = []  # 用于收集输出信息的列表
        # 检查文件是否存在
        file_path = '/Users/yanzhang/Documents/News/backup/marketcap_pe.txt'
        if os.path.exists(file_path):
            # 获取昨天的日期作为时间戳
            yesterday = datetime.now() - timedelta(days=1)
            timestamp = yesterday.strftime('%Y%m%d')

            # 构建新的文件名
            directory, filename = os.path.split(file_path)
            name, extension = os.path.splitext(filename)
            new_filename = f"{name}_{timestamp}{extension}"
            new_file_path = os.path.join(directory, new_filename)

            # 重命名文件
            os.rename(file_path, new_file_path)
            print(f"文件已重命名为: {new_file_path}")
        else:
            print("文件不存在")

        login_url = "https://login.yahoo.com"
        urls = [
            ('https://finance.yahoo.com/screener/abf2a40b-6e31-4353-9af1-91f0474e353c?offset=0&count=100',
            'Technology'),
            ('https://finance.yahoo.com/screener/abf2a40b-6e31-4353-9af1-91f0474e353c?count=100&offset=100',
            'Technology'),
            ('https://finance.yahoo.com/screener/abf2a40b-6e31-4353-9af1-91f0474e353c?count=100&offset=200',
            'Technology'),
            ('https://finance.yahoo.com/screener/2e39461b-04c9-4560-bc72-9b45331669b2?offset=0&count=100',
            'Industrials'),
            ('https://finance.yahoo.com/screener/2e39461b-04c9-4560-bc72-9b45331669b2?count=100&offset=100',
            'Industrials'),
            ('https://finance.yahoo.com/screener/cf1d55c1-69b4-4f3a-b0c6-dfab869aeeda?offset=0&count=100',
            'Financial_Services'),
            ('https://finance.yahoo.com/screener/cf1d55c1-69b4-4f3a-b0c6-dfab869aeeda?count=100&offset=100',
            'Financial_Services'),
            ('https://finance.yahoo.com/screener/cf1d55c1-69b4-4f3a-b0c6-dfab869aeeda?count=100&offset=200',
            'Financial_Services'),
            ('https://finance.yahoo.com/screener/a6ae322b-684f-4a0a-a741-780ee93d91b9?offset=0&count=100',
            'Basic_Materials'),
            ('https://finance.yahoo.com/screener/d86fe323-442b-4606-a97b-10a403168772?offset=0&count=100',
            'Consumer_Defensive'),
            ('https://finance.yahoo.com/screener/b410daa9-796b-496e-93aa-5f471f2d25b3?offset=0&count=100',
            'Utilities'),
            ('https://finance.yahoo.com/screener/c0b7a27b-93dc-40e3-ba69-9d8f3d2efa3d?offset=0&count=100',
            'Energy'),
            ('https://finance.yahoo.com/screener/31b0d926-ddb8-41b0-8069-8c83433efe1f?offset=0&count=100',
            'Consumer_Cyclical'),
            ('https://finance.yahoo.com/screener/31b0d926-ddb8-41b0-8069-8c83433efe1f?count=100&offset=100',
            'Consumer_Cyclical'),
            ('https://finance.yahoo.com/screener/cbd1eeac-8eb9-4d08-9100-5917153d288a?offset=0&count=100',
            'Real_Estate'),
            ('https://finance.yahoo.com/screener/73eee657-6674-422d-8001-68e601d27811?offset=0&count=100',
            'Healthcare'),
            ('https://finance.yahoo.com/screener/73eee657-6674-422d-8001-68e601d27811?count=100&offset=100',
            'Healthcare'),
            ('https://finance.yahoo.com/screener/32c6df77-2f51-47a6-9c8a-30340ca7728b?offset=0&count=100',
            'Communication_Services'),
        ]
        
        try:
            login_once(driver, login_url)
            process_urls(driver, urls, output)
        finally:
            driver.quit()
        print("所有爬取任务完成。")
        
        # 在代码的最后部分调用save_output_to_file函数
        output_directory = '/Users/yanzhang/Documents/News/site'
        save_output_to_file(output, output_directory)

if __name__ == "__main__":
    output = []  # 用于收集输出信息的列表
    main()