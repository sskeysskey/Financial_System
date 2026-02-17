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
import platform
import sys
import tkinter as tk
from tkinter import messagebox

# ================= 全局配置区域 (跨平台修改) =================

# 1. 动态获取主目录
USER_HOME = os.path.expanduser("~")

# 2. 定义基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOAD_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_DIR = os.path.join(BASE_CODING_DIR, "News")

# 3. 具体业务文件路径
DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
JSON_FILE_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_All.json")
BLACKLIST_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Blacklist.json")
OUTPUT_DIR = NEWS_DIR
OUTPUT_TXT_FILE = os.path.join(OUTPUT_DIR, 'ETFs_new.txt')
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

# 4. 浏览器与驱动路径 (跨平台适配)
if platform.system() == 'Darwin':
    CHROME_BINARY_PATH = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOAD_DIR, "backup", "chromedriver_beta")
elif platform.system() == 'Windows':
    # Windows 路径优化
    CHROME_BINARY_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(CHROME_BINARY_PATH):
        CHROME_BINARY_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOAD_DIR, "backup", "chromedriver.exe")
else:
    CHROME_BINARY_PATH = "/usr/bin/google-chrome"
    CHROME_DRIVER_PATH = "/usr/bin/chromedriver"

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ================= 通用辅助函数 =================

def get_driver():
    """创建并返回配置好的 Chrome Driver"""
    chrome_options = Options()
    
    if os.path.exists(CHROME_BINARY_PATH):
        chrome_options.binary_location = CHROME_BINARY_PATH
    else:
        logging.warning(f"Chrome binary not found at {CHROME_BINARY_PATH}, using system default.")

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
    
    if not os.path.exists(CHROME_DRIVER_PATH):
        logging.error(f"Driver not found: {CHROME_DRIVER_PATH}")
        return None

    service = Service(executable_path=CHROME_DRIVER_PATH)
    return webdriver.Chrome(service=service, options=chrome_options)

def get_db_connection():
    """获取数据库连接 (增加超时设置)"""
    # 确保数据库目录存在
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH, timeout=60.0)

def check_is_workday():
    """检查当前日期是否为周日或周一。返回: True (可执行), False (不执行)"""
    # 0=Monday, 6=Sunday. 
    return datetime.now().weekday() not in [0, 6]

def display_dialog(message):
    """跨平台弹窗提示"""
    if platform.system() == 'Darwin':
        try:
            applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        except Exception as e:
            logging.error(f"弹窗失败: {e}")
    else:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("提示", message)
        root.destroy()

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

# ================= 任务模块 1-6 =================

def run_commodities():
    logging.info(">>> 开始执行: Commodities")
    driver = get_driver()
    if not driver: return
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
            "Orange Juice", "Cotton", "Coffee", "Sugar", "Cocoa", "Lumber"
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
    if not driver: return
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
    if not driver: return
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''CREATE TABLE IF NOT EXISTS Currencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, name TEXT, price REAL);''')
        conn.commit()
        symbols = ["USDRUB"]
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
    if not driver: return
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
            # 1. 确保表格加载 (增加等待时间)
            WebDriverWait(d, 15).until(EC.presence_of_element_located((By.LINK_TEXT, "United Kingdom")))
            
            # 收集本次尝试中失败的项目
            missing_items = []
            
            for bond, mapped_name in other_bonds.items():
                try:
                    # 优化定位：只查找位于 td (表格单元格) 内的链接，避免抓到页眉/页脚的同名链接
                    # 原代码: element = d.find_element(By.LINK_TEXT, bond)
                    # 新代码: 使用 XPath 确保在表格中
                    element = d.find_element(By.XPATH, f"//td/a[normalize-space(.)='{bond}']")
                    
                    row = element.find_element(By.XPATH, './ancestor::tr')
                    price = float(row.find_element(By.ID, 'p').text.strip().replace(',', ''))
                    temp.append((yesterday_date, mapped_name, price))
                except Exception as e:
                    # 记录具体的错误，但不立即中断循环，看看其他的是否能成功
                    logging.warning(f"临时抓取失败 {mapped_name}: {e}")
                    missing_items.append(mapped_name)

            # 2. 关键修改：检查数据完整性
            # 如果 temp 的数量少于应抓取的数量，说明有数据没抓到
            if len(temp) < len(other_bonds):
                # 抛出异常！这会触发 fetch_with_retry 的 except 块
                # 从而导致：记录警告 -> 等待3秒 -> 重新 reload 页面 -> 重试
                raise Exception(f"数据抓取不完整，缺失: {missing_items}。触发重试机制。")
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
    if not driver: return
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
            # 关键修改：直接等待具体的 MOEX 链接出现，而不是等待容器
            for Indice, mapped_name in name_mapping.items():
                try:
                    # 使用 WebDriverWait 确保特定的链接已经加载到 DOM 
                    element = WebDriverWait(d, 15).until(
                        EC.presence_of_element_located((By.LINK_TEXT, Indice))
                    )
                    # 滚动到该元素，防止在 headless 模式下因为不在视口内而无法点击/读取
                    d.execute_script("arguments[0].scrollIntoView();", element)
                    row = element.find_element(By.XPATH, './ancestor::tr')
                    price_text = row.find_element(By.ID, 'p').text.strip()
                    price = float(price_text.replace(',', ''))
                    temp.append((yesterday_date, mapped_name, price, 0))
                except Exception as e: 
                    logging.warning(f"Failed Indices {mapped_name}: {e}")
            if not temp:
                raise Exception("未能提取到任何指数数据，可能是页面结构改变或被拦截")
            return temp
        all_data = fetch_with_retry(driver, 'https://tradingeconomics.com/stocks', extract_indices, task_name="Indices")
        
        if all_data:
            # 建议使用 INSERT OR REPLACE 避免主键冲突导致整个任务中断
            cursor.executemany('INSERT OR REPLACE INTO Indices (date, name, price, volume) VALUES (?, ?, ?, ?)', all_data)
            conn.commit()
            logging.info(f"Indices: 成功插入 {len(all_data)} 条数据")
    except Exception as e:
        logging.error(f"Indices 模块最终出错: {e}")
        conn.rollback()
    finally:
        driver.quit()
        conn.close()

def run_economics():
    logging.info(">>> 开始执行: Economics")
    driver = get_driver()
    if not driver: return
    conn = get_db_connection()
    
    def fetch_data_logic(driver, indicators):
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        result = []
        missing_items = []

        # 增加一个通用等待，确保表格内容至少开始渲染
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "td")))
        except:
            pass # 如果超时，下面的循环会处理并抛出异常

        for key, value in indicators.items():
            try:
                # 使用 normalize-space 容错空格
                # 只有当不仅找到元素，且内容有效时才算成功
                element = driver.find_element(By.XPATH, f"//td[normalize-space(.)=\"{key}\"]/following-sibling::td")
                price_str = element.text.strip()
                if not price_str: 
                    missing_items.append(key)
                    continue
                price = float(price_str.replace(',', ''))
                result.append((yesterday, value, price))
            except Exception:
                missing_items.append(key)

        # 【关键修改】如果抓取到的数量少于预期数量，抛出异常以触发重试
        if len(result) < len(indicators):
            raise Exception(f"数据抓取不完整 (成功 {len(result)}/{len(indicators)})。缺失指标: {missing_items}")
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
        
        c = conn.cursor()
        for entry in data_to_insert:
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

# ================= 任务模块 7: ETF 处理 =================

def count_files(prefix):
    """计算Downloads目录中指定前缀开头的文件数量"""
    files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{prefix}_*.csv"))
    return len(files)

def run_etf_processing():
    logging.info(">>> 开始执行: ETF CSV Processing (Compare_Insert)")
    
    # 1. 计算昨天日期
    yesterday = date.today() - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    
    # 2. 跨平台交互: Mac (AppleScript) / Windows (pyautogui)
    if platform.system() == 'Darwin':
        # Mac 原生逻辑
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
    else:
        # Windows/Linux 逻辑
        # 假设你已经安装了类似 Tampermonkey 脚本监听快捷键，且快捷键是 Alt+C
        try:
            import pyautogui
            # 尝试切换到 Chrome 窗口 (这一步很难自动化完美，假设用户已经把 Chrome 放在前台)
            logging.info("请确保 Chrome 浏览器在前台...")
            time.sleep(2)
            pyautogui.hotkey('alt', 'c') 
            logging.info("发送 Alt+C 快捷键成功")
        except Exception as e:
            logging.error(f"发送快捷键失败: {e}")

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
        return 

    etf_blacklist = set()
    try:
        if os.path.exists(BLACKLIST_JSON_PATH):
            with open(BLACKLIST_JSON_PATH, 'r', encoding='utf-8') as f_bl:
                bl_data = json.load(f_bl)
            etf_blacklist = set(bl_data.get('etf', []))
    except Exception as e:
        logging.warning(f"Blacklist 读取失败，将不使用过滤: {e}")

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
        # 使用 sys.executable 动态获取 python 路径
        result = subprocess.run(
            [sys.executable, CHECK_YESTERDAY_SCRIPT_PATH],
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
    # 检查是否有命令行参数传入
    # 如果参数个数大于 1 (即除了脚本名以外还有其他参数)，则 skip_etf 为 True
    skip_etf = len(sys.argv) > 1
    if skip_etf:
        logging.info(">>> 检测到命令行参数，本次运行将跳过 ETF 处理任务。")

    # 1. 检查日期 (全局控制)
    if not check_is_workday():
        msg = "今天是周日或周一，不执行更新操作。" 
        logging.info(msg)
        display_dialog(msg)
        return

    # --- 配置等待时间 (秒) ---
    TASK_INTERVAL = 3  

    def wait_between_tasks(task_name):
        """辅助函数：打印日志并等待"""
        logging.info(f"[{task_name}] 完成，休息 {TASK_INTERVAL} 秒准备下一项任务...")
        time.sleep(TASK_INTERVAL)

    # 2. 顺次执行爬虫任务 (这些任务无论如何都会执行)
    try: 
        run_commodities()
    except Exception as e: 
        logging.error(f"Main Loop - Commodities Error: {e}")
    
    wait_between_tasks("Commodities") # 等待
    try: 
        run_currency_cny2()
    except Exception as e: 
        logging.error(f"Main Loop - Currency CNY2 Error: {e}")
    
    wait_between_tasks("Currency CNY2") # 等待
    try: 
        run_currency_cny()
    except Exception as e: 
        logging.error(f"Main Loop - Currency CNY Error: {e}")
    
    wait_between_tasks("Currency CNY") # 等待
    try: 
        run_bonds()
    except Exception as e: 
        logging.error(f"Main Loop - Bonds Error: {e}")
    
    wait_between_tasks("Bonds") # 等待
    try: 
        run_indices()
    except Exception as e: 
        logging.error(f"Main Loop - Indices Error: {e}")
        
    wait_between_tasks("Indices") # 等待
    try: 
        run_economics()
    except Exception as e: 
        logging.error(f"Main Loop - Economics Error: {e}")
    wait_between_tasks("Economics") # 等待

    # 3. 执行 ETF 处理任务 (根据 skip_etf 标志决定是否执行)
    if not skip_etf:
        try:
            run_etf_processing()
        except Exception as e:
            logging.error(f"Main Loop - ETF Processing Error: {e}")
    else:
        logging.info(">>> 已跳过 ETF 处理任务 (run_etf_processing)。")

    logging.info(">>> 所有任务执行完毕")

if __name__ == "__main__":
    main()