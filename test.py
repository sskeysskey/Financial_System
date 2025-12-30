import sqlite3
import subprocess
import logging
import time
import os
import glob
import csv
import json
from datetime import datetime, date, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# ================= 全局配置区域 =================

# --- 路径配置 (来自两个脚本) ---
CHROME_DRIVER_PATH = "/Users/yanzhang/Downloads/backup/chromedriver_beta"
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'

# ETF 处理相关路径
JSON_FILE_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
BLACKLIST_JSON_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Blacklist.json'
OUTPUT_DIR = '/Users/yanzhang/Coding/News'
OUTPUT_TXT_FILE = os.path.join(OUTPUT_DIR, 'ETFs_new.txt')
DOWNLOAD_DIR = "/Users/yanzhang/Downloads/"
CHECK_YESTERDAY_SCRIPT_PATH = '/Users/yanzhang/Coding/Financial_System/Query/Check_yesterday.py'

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ================= 通用辅助函数 (来自 TE_Merged) =================

def get_driver():
    """创建并返回配置好的 Chrome Driver (Beta版)"""
    chrome_options = Options()
    # 指定使用 Chrome Beta
    chrome_options.binary_location = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"
    
    # --- Headless模式相关设置 ---
    chrome_options.add_argument('--headless=new') 
    chrome_options.add_argument('--window-size=1920,1080')
    
    # --- 伪装设置 ---
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    chrome_options.add_argument(f'user-agent={user_agent}')
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # --- 性能优化 ---
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.page_load_strategy = 'eager'
    
    service = Service(executable_path=CHROME_DRIVER_PATH)
    return webdriver.Chrome(service=service, options=chrome_options)

def get_db_connection():
    """获取数据库连接 (增加超时设置)"""
    return sqlite3.connect(DB_PATH, timeout=60.0)

def check_is_workday():
    """检查当前日期是否为周日或周一。返回: True (可执行), False (不执行)"""
    # 0=Monday, 6=Sunday. 
    return datetime.now().weekday() not in [0, 6]

def display_dialog(message):
    """Mac系统弹窗提示"""
    try:
        applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    except Exception as e:
        logging.error(f"弹窗失败: {e}")

def fetch_with_retry(driver, url, extraction_func, max_retries=3, task_name="Task"):
    """通用重试封装函数"""
    for attempt in range(1, max_retries + 1):
        try:
            if url:
                logging.info(f"[{task_name}] 加载页面 (第 {attempt}/{max_retries} 次): {url}")
                driver.get(url)
            
            data = extraction_func(driver)
            
            if attempt > 1:
                logging.info(f"[{task_name}] 重试成功！")
            return data
            
        except Exception as e:
            try:
                current_url = driver.current_url
                page_title = driver.title
                context_msg = f" | URL: {current_url} | Title: {page_title}"
            except:
                context_msg = " | (无法获取页面上下文)"
            logging.warning(f"[{task_name}] 第 {attempt} 次尝试失败: {e}{context_msg}")
            
            if attempt == max_retries:
                logging.error(f"[{task_name}] 最终失败，已达最大重试次数。")
                return []
            time.sleep(3)
    return []

# ================= 任务模块 1-6 (来自 TE_Merged) =================

def run_commodities():
    logging.info(">>> 开始执行: Commodities")
    driver = get_driver()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Commodities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            price REAL,
            UNIQUE(date, name)
        );
        ''')
        conn.commit()
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        all_data = []

        def extract_baltic(d):
            WebDriverWait(d, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "table-responsive")))
            price_element = d.find_element(By.XPATH, "//div[@class='table-responsive']//table//tr/td[position()=2]")
            price = float(price_element.text.strip().replace(',', ''))
            return [(yesterday, "BalticDry", price)]

        baltic_data = fetch_with_retry(driver, 'https://tradingeconomics.com/commodity/baltic', extract_baltic, task_name="Commodities-Baltic")
        all_data.extend(baltic_data)

        commodities_list = [
            "Coal", "Uranium", "Steel", "Lithium", "Wheat", "Palm Oil", "Aluminum",
            "Nickel", "Tin", "Zinc", "Palladium", "Poultry", "Salmon", "Iron Ore",
            "Orange Juice", "Cotton", "Coffee", "Sugar", "Cocoa"
        ]

        def extract_commodities(d):
            temp_data = []
            WebDriverWait(d, 10).until(EC.presence_of_element_located((By.LINK_TEXT, "Coal"))) 
            for commodity in commodities_list:
                try:
                    element = d.find_element(By.LINK_TEXT, commodity)
                    row = element.find_element(By.XPATH, './ancestor::tr')
                    price_str = row.find_element(By.ID, 'p').text.strip()
                    price = float(price_str.replace(',', ''))
                    temp_data.append((yesterday, commodity.replace(" ", ""), price))
                except Exception as inner_e:
                    logging.warning(f"Skipped {commodity}: {inner_e}")
            if not temp_data: raise Exception("页面已加载但未提取到任何商品数据")
            return temp_data

        others_data = fetch_with_retry(driver, 'https://tradingeconomics.com/commodities', extract_commodities, task_name="Commodities-List")
        all_data.extend(others_data)

        if all_data:
            cursor.executemany('INSERT OR REPLACE INTO Commodities (date, name, price) VALUES (?, ?, ?)', all_data)
            conn.commit()
            logging.info(f"Commodities: 插入了 {len(all_data)} 条数据")
    except Exception as e:
        logging.error(f"Commodities 模块出错: {e}")
        conn.rollback()
    finally:
        driver.quit()
        conn.close()

def run_currency_cny2():
    logging.info(">>> 开始执行: Currency CNY 2")
    driver = get_driver()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''CREATE TABLE IF NOT EXISTS Currencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, name TEXT, price REAL);''')
        conn.commit()
        target_currencies = ["CNYARS", "CNYIDR", "CNYIRR", "CNYEGP", "CNYMXN"]
        yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        def extract_currency_list(d):
            WebDriverWait(d, 10).until(EC.presence_of_element_located((By.LINK_TEXT, "CNYARS")))
            temp_data = []
            for curr in target_currencies:
                try:
                    element = d.find_element(By.LINK_TEXT, curr)
                    row = element.find_element(By.XPATH, './ancestor::tr')
                    price = float(row.find_element(By.ID, 'p').text.strip().replace(',', ''))
                    temp_data.append((yesterday_date, curr, price))
                except Exception as inner_e:
                    logging.warning(f"Skipped {curr}: {inner_e}")
            if not temp_data: raise Exception("未提取到任何货币数据")
            return temp_data
        all_data = fetch_with_retry(driver, 'https://tradingeconomics.com/currencies?base=cny', extract_currency_list, task_name="Currency-CNY2")
        if all_data:
            cursor.executemany('INSERT INTO Currencies (date, name, price) VALUES (?, ?, ?)', all_data)
            conn.commit()
            logging.info(f"Currency CNY2: 插入了 {len(all_data)} 条数据")
    except Exception as e:
        logging.error(f"Currency CNY2 模块出错: {e}")
        conn.rollback()
    finally:
        driver.quit()
        conn.close()

def run_currency_cny():
    logging.info(">>> 开始执行: Currency CNY (Specific Pairs)")
    driver = get_driver()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''CREATE TABLE IF NOT EXISTS Currencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, name TEXT, price REAL);''')
        conn.commit()
        symbols = ["CNYIRR", "USDRUB"]
        yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        all_data = []
        for symbol in symbols:
            url = f"https://tradingeconomics.com/{symbol}:cur"
            def extract_single_currency(d):
                price_text = None
                try:
                    wait = WebDriverWait(d, 5)
                    price_element = wait.until(EC.presence_of_element_located((By.ID, "market_last")))
                    price_text = price_element.text.strip()
                except TimeoutException:
                    wait = WebDriverWait(d, 5)
                    price_element = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "closeLabel")))
                    price_text = price_element.text.strip()
                if price_text:
                    price = round(float(price_text.replace(',', '')), 4)
                    return [(yesterday_date, symbol, price)]
                else: raise Exception(f"未能找到 {symbol} 的价格元素")
            result = fetch_with_retry(driver, url, extract_single_currency, task_name=f"Currency-{symbol}")
            all_data.extend(result)
        if all_data:
            cursor.executemany('INSERT INTO Currencies (date, name, price) VALUES (?, ?, ?)', all_data)
            conn.commit()
            logging.info(f"Currency CNY: 插入了 {len(all_data)} 条数据")
    except Exception as e:
        logging.error(f"Currency CNY 模块出错: {e}")
        conn.rollback()
    finally:
        driver.quit()
        conn.close()

def run_bonds():
    logging.info(">>> 开始执行: Bonds")
    driver = get_driver()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''CREATE TABLE IF NOT EXISTS Bonds (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, name TEXT, price REAL, UNIQUE(date, name));''')
        conn.commit()
        yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        all_data = []
        
        def extract_us_bond(d):
            element = WebDriverWait(d, 10).until(EC.presence_of_element_located((By.LINK_TEXT, "US 2Y")))
            row = element.find_element(By.XPATH, './ancestor::tr')
            price = float(row.find_element(By.ID, 'p').text.strip().replace(',', ''))
            return [(yesterday_date, "US2Y", price)]
        
        all_data.extend(fetch_with_retry(driver, 'https://tradingeconomics.com/united-states/government-bond-yield', extract_us_bond, task_name="Bonds-US"))
        
        other_bonds = {"United Kingdom": "UK10Y", "Japan": "JP10Y", "Brazil": "BR10Y", "India": "IND10Y", "Turkey": "TUR10Y"}
        def extract_other_bonds(d):
            temp = []
            WebDriverWait(d, 10).until(EC.presence_of_element_located((By.LINK_TEXT, "United Kingdom")))
            for bond, mapped_name in other_bonds.items():
                try:
                    element = d.find_element(By.LINK_TEXT, bond)
                    row = element.find_element(By.XPATH, './ancestor::tr')
                    price = float(row.find_element(By.ID, 'p').text.strip().replace(',', ''))
                    temp.append((yesterday_date, mapped_name, price))
                except Exception as e: logging.warning(f"Failed {mapped_name}: {e}")
            if not temp: raise Exception("未提取到任何其他国家债券数据")
            return temp
            
        all_data.extend(fetch_with_retry(driver, 'https://tradingeconomics.com/bonds', extract_other_bonds, task_name="Bonds-Others"))
        if all_data:
            cursor.executemany('INSERT OR REPLACE INTO Bonds (date, name, price) VALUES (?, ?, ?)', all_data)
            conn.commit()
            logging.info(f"Bonds: 插入了 {len(all_data)} 条数据")
    except Exception as e:
        logging.error(f"Bonds 模块出错: {e}")
        conn.rollback()
    finally:
        driver.quit()
        conn.close()

def run_indices():
    logging.info(">>> 开始执行: Indices")
    driver = get_driver()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''CREATE TABLE IF NOT EXISTS Indices (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, name TEXT, price REAL, volume REAL, UNIQUE(date, name));''')
        conn.commit()
        name_mapping = {"MOEX": "Russia"}
        yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        def extract_indices(d):
            temp = []
            WebDriverWait(d, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "table-responsive")))
            for Indice, mapped_name in name_mapping.items():
                try:
                    element = d.find_element(By.LINK_TEXT, Indice)
                    row = element.find_element(By.XPATH, './ancestor::tr')
                    price = float(row.find_element(By.ID, 'p').text.strip().replace(',', ''))
                    temp.append((yesterday_date, mapped_name, price, 0))
                except Exception as e: logging.warning(f"Failed Indices {mapped_name}: {e}")
            return temp
        all_data = fetch_with_retry(driver, 'https://tradingeconomics.com/stocks', extract_indices, task_name="Indices")
        if all_data:
            cursor.executemany('INSERT INTO Indices (date, name, price, volume) VALUES (?, ?, ?, ?)', all_data)
            conn.commit()
            logging.info(f"Indices: 插入了 {len(all_data)} 条数据")
    except Exception as e:
        logging.error(f"Indices 模块出错: {e}")
        conn.rollback()
    finally:
        driver.quit()
        conn.close()

def run_economics():
    logging.info(">>> 开始执行: Economics")
    driver = get_driver()
    conn = get_db_connection()
    
    def fetch_data_logic(driver, indicators):
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        result = []
        for key, value in indicators.items():
            try:
                element = driver.find_element(By.XPATH, f"//td[normalize-space(.)=\"{key}\"]/following-sibling::td")
                price_str = element.text.strip()
                if not price_str: continue
                price = float(price_str.replace(',', ''))
                result.append((yesterday, value, price))
            except Exception: pass
        return result

    def navigate_and_fetch_retry(driver, section_css, link_text, indicators, max_retries=3):
        for i in range(max_retries):
            try:
                if section_css:
                    section_link = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, section_css)))
                    section_link.click()
                    WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.LINK_TEXT, link_text)))
                data = fetch_data_logic(driver, indicators)
                if not data: raise Exception("No data extracted")
                return data
            except Exception as e:
                logging.warning(f"Economics 导航/抓取重试 {i+1}/{max_retries} ({link_text}): {e}")
                time.sleep(2)
        return []

    try:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS Economics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, name TEXT, price REAL, UNIQUE(date, name));''')
        conn.commit()
        Economics1 = {"GDP Growth Rate": "USGDP", "Non Farm Payrolls": "USNonFarm", "Inflation Rate": "USCPI", "Interest Rate": "USInterest", "Balance of Trade": "USTrade", "Consumer Confidence": "USConfidence", "Retail Sales MoM": "USRetailM", "Unemployment Rate": "USUnemploy", "Non Manufacturing PMI": "USNonPMI"}
        Economics2 = {"Initial Jobless Claims": "USInitial", "ADP Employment Change": "USNonFarmA"}
        Economics3 = {"Core PCE Price Index Annual Change": "CorePCEY", "Core PCE Price Index MoM": "CorePCEM", "Core Inflation Rate": "CoreCPI", "Producer Prices Change": "USPPI", "Core Producer Prices YoY": "CorePPI", "PCE Price Index Annual Change": "PCEY", "Import Prices MoM": "ImportPriceM", "Import Prices YoY": "ImportPriceY"}
        Economics4 = {"Real Consumer Spending": "USConspending"}
        
        data_to_insert = []
        data_to_insert.extend(fetch_with_retry(driver, 'https://tradingeconomics.com/united-states/indicators', lambda d: fetch_data_logic(d, Economics1), task_name="Economics-Main"))
        data_to_insert.extend(navigate_and_fetch_retry(driver, 'a[data-bs-target="#labour"]', "Manufacturing Payrolls", Economics2))
        data_to_insert.extend(navigate_and_fetch_retry(driver, 'a[data-bs-target="#prices"]', "Core Consumer Prices", Economics3))
        data_to_insert.extend(navigate_and_fetch_retry(driver, 'a[data-bs-target="#gdp"]', "GDP Constant Prices", Economics4))
        
        for entry in data_to_insert:
            c = conn.cursor()
            c.execute('''SELECT price FROM Economics WHERE name = ? AND date < ? ORDER BY ABS(julianday(date) - julianday(?)) LIMIT 1''', (entry[1], entry[0], entry[0]))
            result = c.fetchone()
            if result and float(result[0]) == float(entry[2]):
                logging.info(f"Skipping {entry[1]} on {entry[0]}: Price same as recent entry.")
            else:
                try:
                    c.execute('INSERT INTO Economics (date, name, price) VALUES (?, ?, ?)', entry)
                    conn.commit()
                    logging.info(f"Economics: 插入 {entry[1]} = {entry[2]}")
                except sqlite3.IntegrityError: pass
    except Exception as e:
        logging.error(f"Economics 模块出错: {e}")
    finally:
        driver.quit()
        conn.close()

# ================= 任务模块 7: ETF 处理 (来自 Compare_Insert.py) =================

def count_files(prefix):
    """计算Downloads目录中指定前缀开头的文件数量"""
    files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{prefix}_*.csv"))
    return len(files)

def run_etf_processing():
    logging.info(">>> 开始执行: ETF CSV Processing (Compare_Insert)")
    
    # 1. 计算昨天日期
    yesterday = date.today() - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    
    # 2. 触发 AppleScript (Chrome操作)
    script = '''
    delay 1
    tell application "Google Chrome"
        activate
    end tell
    delay 1
    tell application "System Events"
        keystroke "c" using option down
    end tell
    '''
    try:
        subprocess.run(['osascript', '-e', script], check=True)
        logging.info("AppleScript 触发成功")
    except Exception as e:
        logging.error(f"AppleScript 执行失败: {e}")

    # 3. 等待文件下载
    print("正在等待 topetf_*.csv 文件下载...", end="")
    waited = 0
    while count_files("topetf") < 1:
        time.sleep(2)
        waited += 2
        print(".", end="", flush=True)
        # 防止死循环，可选设置最大等待时间，例如120秒
        if waited > 120:
             logging.error("\n等待 CSV 文件超时。")
             return
    print("\n文件已找到。")

    # 4. 获取最新文件
    topetf_files = glob.glob(os.path.join(DOWNLOAD_DIR, 'topetf_*.csv'))
    if not topetf_files:
        logging.error("未找到 topetf 文件")
        return
    topetf_file = max(topetf_files, key=os.path.getmtime)
    logging.info(f"使用 topetf 文件: {topetf_file}")

    # 5. 读取 JSON 配置
    known_etfs = set()
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            sectors_data = json.load(f)
        known_etfs = set(sectors_data.get('ETFs', []))
        if not known_etfs: logging.warning("JSON ETFs 列表为空")
    except Exception as e:
        logging.error(f"读取 JSON 失败: {e}")
        return # 关键配置缺失，终止

    etf_blacklist = set()
    try:
        with open(BLACKLIST_JSON_PATH, 'r', encoding='utf-8') as f_bl:
            bl_data = json.load(f_bl)
        etf_blacklist = set(bl_data.get('etf', []))
    except Exception as e:
        logging.warning(f"Blacklist 读取失败或不存在，将不使用过滤: {e}")

    # 6. 处理 CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    etfs_to_db = []
    new_etfs_to_file = []

    try:
        with open(topetf_file, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            if not reader.fieldnames or not all(col in reader.fieldnames for col in ['Symbol', 'Name', 'Price', 'Volume']):
                logging.error("CSV 缺少必要列")
                return

            for row in reader:
                symbol = row.get('Symbol')
                name = row.get('Name')
                price_str = row.get('Price')
                volume_str = row.get('Volume')

                if not all([symbol, name, price_str, volume_str]): continue
                try:
                    price_val = float(price_str)
                    volume_val = int(volume_str)
                except ValueError: continue

                if symbol in known_etfs:
                    etfs_to_db.append((yesterday_str, symbol, round(price_val, 2), volume_val))
                else:
                    if volume_val > 200000 and symbol not in etf_blacklist:
                        new_etfs_to_file.append(f"{symbol}: {name}, {volume_val}")
    except Exception as e:
        logging.error(f"处理 CSV 出错: {e}")
        return

    # 7. 写入数据库
    if etfs_to_db:
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH, timeout=60.0)
            cursor = conn.cursor()
            cursor.executemany("INSERT INTO ETFs (date, name, price, volume) VALUES (?, ?, ?, ?)", etfs_to_db)
            conn.commit()
            logging.info(f"成功写入 {len(etfs_to_db)} 条 ETF 数据")
        except Exception as e:
            logging.error(f"数据库写入错误: {e}")
            if conn: conn.rollback()
        finally:
            if conn: conn.close()
    else:
        logging.info("无匹配 ETF 数据写入数据库")

    # 8. 写入新文件
    if new_etfs_to_file:
        try:
            with open(OUTPUT_TXT_FILE, 'a', encoding='utf-8') as txtfile:
                for line in new_etfs_to_file:
                    txtfile.write(line + '\n')
            logging.info(f"写入 {len(new_etfs_to_file)} 条新 ETF 数据到文件")
        except Exception as e:
            logging.error(f"写入文件失败: {e}")

    # 9. 调用子脚本 Check_yesterday
    logging.info("--- 开始执行 Check_yesterday.py ---")
    try:
        result = subprocess.run(
            ['/Library/Frameworks/Python.framework/Versions/Current/bin/python3', CHECK_YESTERDAY_SCRIPT_PATH],
            check=True, capture_output=True, text=True, encoding='utf-8'
        )
        logging.info("Check_yesterday 执行成功")
        print("--- Subprocess Output ---\n" + result.stdout)
    except subprocess.CalledProcessError as e:
        logging.error(f"Check_yesterday 执行失败 code={e.returncode}")
        print(e.stderr)
    except Exception as e:
        logging.error(f"调用 Check_yesterday 失败: {e}")

# ================= 主程序入口 =================

def main():
    # 1. 检查日期 (全局控制)
    if not check_is_workday():
        msg = "今天是周日或周一，不执行更新操作。" 
        logging.info(msg)
        display_dialog(msg)
        return

    # 2. 顺次执行爬虫任务
    try: run_commodities()
    except Exception as e: logging.error(f"Main Loop - Commodities Error: {e}")
    
    try: run_currency_cny2()
    except Exception as e: logging.error(f"Main Loop - Currency CNY2 Error: {e}")
    
    try: run_currency_cny()
    except Exception as e: logging.error(f"Main Loop - Currency CNY Error: {e}")
    
    try: run_bonds()
    except Exception as e: logging.error(f"Main Loop - Bonds Error: {e}")
    
    try: run_indices()
    except Exception as e: logging.error(f"Main Loop - Indices Error: {e}")
        
    try: run_economics()
    except Exception as e: logging.error(f"Main Loop - Economics Error: {e}")

    # 3. 执行 ETF 处理任务 (原 Compare_Insert 逻辑)
    try:
        run_etf_processing()
    except Exception as e:
        logging.error(f"Main Loop - ETF Processing Error: {e}")

    logging.info(">>> 所有任务执行完毕")

if __name__ == "__main__":
    main()
