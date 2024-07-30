import json
import os
from datetime import datetime, timedelta
from selenium import webdriver
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
    
    # 等待登录成功的标志，如重定向到登录后页面的某个特定元素
    # WebDriverWait(driver, 60).until(
    #     EC.presence_of_element_located((By.ID, "ybarAccountMenu"))
    # )
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
                pe_ratio = '--'
            else:
                pe_ratio = float(pe_ratio)
        except NoSuchElementException:
            pe_ratio = '--'
        except ValueError:
            pe_ratio = '--'

        results.append((symbol, market_cap, pe_ratio))
        
    # 将结果写入到 txt 文件
    with open('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt', 'a') as file:  # 修改 'w' 为 'a'
        for result in results:
            file.write(f"{result[0]}: {result[1]}, {result[2]}\n")
    
    return results

def update_json(data, sector, file_path, output, log_enabled):
    with open(file_path, 'r+') as file:
        json_data = json.load(file)
        
        # 创建一个反向映射，用于查找符号当前所在的sector
        current_sectors = {}
        for sec in json_data:
            for symbol in json_data[sec]:
                current_sectors[symbol] = sec

        # 处理每个传入的symbol数据
        for symbol, market_cap, pe_ratio in data:
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
                    if log_enabled:
                        message = f"Added '{symbol}' to {sector} due to a new rising star."
                        print(message)
                        output.append(message)

        # 重写文件内容
        file.seek(0)
        file.truncate()
        json.dump(json_data, file, indent=2)

def process_sector(driver, url, sector, output):
    data = fetch_data(driver, url)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', output, log_enabled=True)
    update_json(data, sector, '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json', output, log_enabled=False)

def save_output_to_file(output, directory, filename='Stock_Change.txt'):
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

def clean_old_backups(directory, prefix="marketcap_pe_", days=4):
    """删除备份目录中超过指定天数的文件"""
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    for filename in os.listdir(directory):
        if filename.startswith(prefix):  # 只处理特定前缀的文件
            try:
                date_str = filename.split('_')[-1].split('.')[0]  # 获取日期部分
                file_date = datetime.strptime(date_str, '%m%d')
                # 将年份设置为今年
                file_date = file_date.replace(year=now.year)
                if file_date < cutoff:
                    file_path = os.path.join(directory, filename)
                    os.remove(file_path)
                    print(f"删除旧备份文件：{file_path}")
            except Exception as e:
                print(f"跳过文件：{filename}，原因：{e}")

chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"

service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service)

# 定义黑名单
blacklist = {"CTA-PA", "FWONK", "FOXA", "NWSA", "PARAA", "LSXMA",
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
    "CWEN-A", "ELPC", "BML-PG", "SLG-PI", "NEE-PR", "APO-PA",
    "YNDX", "CUK", "BBDO", "SLMBP", "BPYPP", "GOOG","CPG", "PHYS",
    "CTA-PB", "FITBI", "FLUT", "ZG", "BNRE", "BZ", "VNO", "CHT",
    "SWAV", "BIO-B", "RBRK", "CNHI", "FER", "LOAR", "ACGLO", "AIRC",
    "WRK", "ETRN", "WSO-B", "DJTWW"
    }

output = []  # 用于收集输出信息的列表
# 检查文件是否存在
file_path = '/Users/yanzhang/Documents/News/backup/marketcap_pe.txt'
directory_backup = '/Users/yanzhang/Documents/News/site/'
if os.path.exists(file_path):
    # 获取昨天的日期作为时间戳
    yesterday = datetime.now() - timedelta(days=1)
    timestamp = yesterday.strftime('%m%d')

    # 构建新的文件名
    directory, filename = os.path.split(file_path)
    name, extension = os.path.splitext(filename)
    new_filename = f"{name}_{timestamp}{extension}"
    new_file_path = os.path.join(directory_backup, new_filename)

    # 重命名文件
    os.rename(file_path, new_file_path)
    print(f"文件已重命名为: {new_file_path}")
else:
    print("文件不存在")

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
    process_urls(driver, urls, output)
finally:
    driver.quit()
print("所有爬取任务完成。")

# 在代码的最后部分调用save_output_to_file函数
output_directory = '/Users/yanzhang/Documents/News'
save_output_to_file(output, output_directory)

# 调用清理旧备份文件的函数
clean_old_backups(directory_backup)