import sqlite3
import subprocess
import logging
import time  # 新增：用于重试等待
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# ================= 配置区域 =================

# 请确保这个路径下的 chromedriver 版本与 Chrome Beta 版本一致
CHROME_DRIVER_PATH = "/Users/yanzhang/Downloads/backup/chromedriver_beta"
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ================= 通用辅助函数 =================

def get_driver():
    """创建并返回配置好的 Chrome Driver (Beta版)"""
    chrome_options = Options()
    # 指定使用 Chrome Beta
    chrome_options.binary_location = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"
    
    # --- Headless模式相关设置 ---
    chrome_options.add_argument('--headless=new') # 推荐使用新的 headless 模式
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
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
    chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始
    
    service = Service(executable_path=CHROME_DRIVER_PATH)
    return webdriver.Chrome(service=service, options=chrome_options)

def get_db_connection():
    """获取数据库连接 (增加超时设置，防止并发锁死)"""
    # 核心修改：timeout=60.0，给其他脚本留出排队时间
    return sqlite3.connect(DB_PATH, timeout=60.0)

def check_is_workday():
    """
    检查当前日期是否为周日或周一。
    返回: True (如果是工作日/可执行日), False (如果是周日或周一)
    """
    # 0=Monday, 6=Sunday. 原逻辑中 [0, 6] 不执行
    return datetime.now().weekday() not in [0, 6]

def display_dialog(message):
    """Mac系统弹窗提示"""
    try:
        applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    except Exception as e:
        logging.error(f"弹窗失败: {e}")

# ================= 新增：重试机制辅助函数 =================

def fetch_with_retry(driver, url, extraction_func, max_retries=3, task_name="Task"):
    """
    通用重试封装函数
    :param driver: Selenium driver 实例
    :param url: 需要加载的 URL (如果为 None，则不执行 get，直接执行逻辑)
    :param extraction_func: 执行具体抓取的函数，接收 driver 作为参数，返回抓取的数据列表
    :param max_retries: 最大尝试次数
    :param task_name: 用于日志显示的当前任务名称
    :return: 成功返回数据列表，失败返回空列表 []
    """
    for attempt in range(1, max_retries + 1):
        try:
            if url:
                logging.info(f"[{task_name}] 加载页面 (第 {attempt}/{max_retries} 次): {url}")
                driver.get(url)
            
            # 执行传入的抓取逻辑
            data = extraction_func(driver)
            
            # --- 新增日志：如果是重试后成功的，打印一条好消息 ---
            if attempt > 1:
                logging.info(f"[{task_name}] 重试成功！(在第 {attempt} 次尝试时恢复)")
            # ------------------------------------------------
            
            return data
            
        except Exception as e:
            # --- 新增：尝试获取当前 URL 和 Title，辅助判断是否被重定向 ---
            try:
                current_url = driver.current_url
                page_title = driver.title
                context_msg = f" | URL: {current_url} | Title: {page_title}"
            except:
                context_msg = " | (无法获取页面上下文)"
            # -------------------------------------------------------

            logging.warning(f"[{task_name}] 第 {attempt} 次尝试失败: {e}{context_msg}")
            
            if attempt == max_retries:
                logging.error(f"[{task_name}] 最终失败，已达最大重试次数。跳过此步骤。")
                return []
            
            # 失败等待时间（例如：第1次失败等3秒，第2次失败等3秒）
            time.sleep(3)
    return []

# ================= 任务模块 1: Commodities =================

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

        # --- 1. Baltic Dry Data (使用重试机制) ---
        def extract_baltic(d):
            WebDriverWait(d, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "table-responsive")))
            price_element = d.find_element(By.XPATH, "//div[@class='table-responsive']//table//tr/td[position()=2]")
            price = float(price_element.text.strip().replace(',', ''))
            logging.info(f"Fetched Baltic Dry: {price}")
            return [(yesterday, "BalticDry", price)]

        baltic_data = fetch_with_retry(driver, 'https://tradingeconomics.com/commodity/baltic', extract_baltic, task_name="Commodities-Baltic")
        all_data.extend(baltic_data)

        # --- 2. Other Commodities (使用重试机制) ---
        commodities_list = [
            "Coal", "Uranium", "Steel", "Lithium", "Wheat", "Palm Oil", "Aluminum",
            "Nickel", "Tin", "Zinc", "Palladium", "Poultry", "Salmon", "Iron Ore",
            "Orange Juice", "Cotton", "Coffee", "Sugar", "Cocoa"
        ]

        def extract_commodities(d):
            temp_data = []
            # 这里的等待是为了确认页面已加载核心表格，如果找不到任意一个商品链接，则视为页面加载异常，触发重试
            WebDriverWait(d, 10).until(EC.presence_of_element_located((By.LINK_TEXT, "Coal"))) 
            
            for commodity in commodities_list:
                try:
                    element = d.find_element(By.LINK_TEXT, commodity)
                    row = element.find_element(By.XPATH, './ancestor::tr')
                    price_str = row.find_element(By.ID, 'p').text.strip()
                    price = float(price_str.replace(',', ''))
                    temp_data.append((yesterday, commodity.replace(" ", ""), price))
                except Exception as inner_e:
                    # 单个商品失败不应该导致整个页面重载，只记录错误
                    logging.warning(f"Skipped {commodity}: {inner_e}")
            
            if not temp_data:
                raise Exception("页面已加载但未提取到任何商品数据")
                
            return temp_data

        others_data = fetch_with_retry(driver, 'https://tradingeconomics.com/commodities', extract_commodities, task_name="Commodities-List")
        all_data.extend(others_data)

        if all_data:
            cursor.executemany('INSERT OR REPLACE INTO Commodities (date, name, price) VALUES (?, ?, ?)', all_data)
            conn.commit()
            logging.info(f"Commodities: 插入了 {len(all_data)} 条数据")
        else:
            logging.info("Commodities: 未获取到有效数据")

    except Exception as e:
        logging.error(f"Commodities 模块出错: {e}")
        conn.rollback()
    finally:
        driver.quit()
        conn.close()

# ================= 任务模块 2: Currency CNY 2 (Currencies Base CNY) =================

def run_currency_cny2():
    logging.info(">>> 开始执行: Currency CNY 2")
    driver = get_driver()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Currencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            price REAL
        );
        ''')
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
            if not temp_data:
                raise Exception("未提取到任何货币数据")
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

# ================= 任务模块 3: Currency CNY (Specific Pairs) =================

def run_currency_cny():
    logging.info(">>> 开始执行: Currency CNY (Specific Pairs)")
    driver = get_driver()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 表结构已在 CNY2 中建立，这里直接使用
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Currencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            price REAL
        );
        ''')
        conn.commit()
        symbols = ["CNYIRR", "USDRUB"]
        yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        all_data = []

        # 针对每一个货币对单独进行重试
        for symbol in symbols:
            url = f"https://tradingeconomics.com/{symbol}:cur"
            
            def extract_single_currency(d):
                price_text = None
                # 方案一
                try:
                    wait = WebDriverWait(d, 5)
                    price_element = wait.until(EC.presence_of_element_located((By.ID, "market_last")))
                    price_text = price_element.text.strip()
                except TimeoutException:
                    # 方案二
                    wait = WebDriverWait(d, 5) # 缩短等待时间以便快速重试
                    price_element = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "closeLabel")))
                    price_text = price_element.text.strip()
                
                if price_text:
                    price = round(float(price_text.replace(',', '')), 4)
                    logging.info(f"Got {symbol}: {price}")
                    return [(yesterday_date, symbol, price)]
                else:
                    raise Exception(f"未能找到 {symbol} 的价格元素")

            # 调用重试器
            result = fetch_with_retry(driver, url, extract_single_currency, task_name=f"Currency-{symbol}")
            all_data.extend(result)

        if all_data:
            cursor.executemany('INSERT INTO Currencies (date, name, price) VALUES (?, ?, ?)', all_data)
            conn.commit()
            logging.info(f"Currency CNY: 插入了 {len(all_data)} 条数据")
        else:
            logging.info("Currency CNY: 未获取到数据")
    except Exception as e:
        logging.error(f"Currency CNY 模块出错: {e}")
        conn.rollback()
    finally:
        driver.quit()
        conn.close()

# ================= 任务模块 4: Bonds =================

def run_bonds():
    logging.info(">>> 开始执行: Bonds")
    driver = get_driver()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Bonds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            price REAL,
            UNIQUE(date, name)
        );
        ''')
        conn.commit()
        yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        all_data = []

        # --- 1. US Bonds ---
        def extract_us_bond(d):
            element = WebDriverWait(d, 10).until(EC.presence_of_element_located((By.LINK_TEXT, "US 2Y")))
            row = element.find_element(By.XPATH, './ancestor::tr')
            price = float(row.find_element(By.ID, 'p').text.strip().replace(',', ''))
            return [(yesterday_date, "US2Y", price)]

        all_data.extend(fetch_with_retry(
            driver, 
            'https://tradingeconomics.com/united-states/government-bond-yield', 
            extract_us_bond, 
            task_name="Bonds-US"
        ))

        # --- 2. Other Countries ---
        other_bonds = {
            "United Kingdom": "UK10Y",
            "Japan": "JP10Y",
            "Brazil": "BR10Y",
            "India": "IND10Y",
            "Turkey": "TUR10Y"
        }
        
        def extract_other_bonds(d):
            temp = []
            WebDriverWait(d, 10).until(EC.presence_of_element_located((By.LINK_TEXT, "United Kingdom"))) # 锚点检查
            for bond, mapped_name in other_bonds.items():
                try:
                    element = d.find_element(By.LINK_TEXT, bond)
                    row = element.find_element(By.XPATH, './ancestor::tr')
                    price = float(row.find_element(By.ID, 'p').text.strip().replace(',', ''))
                    temp.append((yesterday_date, mapped_name, price))
                except Exception as e:
                    logging.warning(f"Failed {mapped_name}: {e}")
            if not temp:
                raise Exception("未提取到任何其他国家债券数据")
            return temp

        all_data.extend(fetch_with_retry(
            driver, 
            'https://tradingeconomics.com/bonds', 
            extract_other_bonds, 
            task_name="Bonds-Others"
        ))

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

# ================= 任务模块 5: Indices =================

def run_indices():
    logging.info(">>> 开始执行: Indices")
    driver = get_driver()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Indices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            price REAL,
            volume REAL,
            UNIQUE(date, name)
        );
        ''')
        conn.commit()
        
        name_mapping = {"MOEX": "Russia"}
        yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        def extract_indices(d):
            temp = []
            # 确保页面加载
            WebDriverWait(d, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "table-responsive")))
            
            for Indice, mapped_name in name_mapping.items():
                try:
                    element = d.find_element(By.LINK_TEXT, Indice)
                    row = element.find_element(By.XPATH, './ancestor::tr')
                    price = float(row.find_element(By.ID, 'p').text.strip().replace(',', ''))
                    temp.append((yesterday_date, mapped_name, price, 0))
                except Exception as e:
                    logging.warning(f"Failed Indices {mapped_name}: {e}")
            
            # 如果配置的所有指数都没抓到，抛出异常触发重试
            if not temp and name_mapping:
                 # 只有当 mapping 不为空时才认为是异常
                 pass 
                 # 注意：如果 name_mapping 只有一个 MOEX 且没抓到，可能确实是页面问题，这里可以稍微严格一点：
                 # raise Exception("No indices found") 
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

# ================= 任务模块 6: Economics =================

def run_economics():
    logging.info(">>> 开始执行: Economics")
    driver = get_driver()
    conn = get_db_connection()
    
    # 内部帮助函数：提取数据
    def fetch_data_logic(driver, indicators):
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        result = []
        for key, value in indicators.items():
            try:
                element = driver.find_element(By.XPATH, f"//td[normalize-space(.)=\"{key}\"]/following-sibling::td")
                price_str = element.text.strip()
                if not price_str:
                    continue
                price = float(price_str.replace(',', ''))
                result.append((yesterday, value, price))
            except Exception:
                pass # 单个指标没找到不中断
        return result

    # 内部帮助函数：带重试的导航点击
    def navigate_and_fetch_retry(driver, section_css, link_text, indicators, max_retries=3):
        for i in range(max_retries):
            try:
                # 1. 尝试点击导航
                if section_css:
                    section_link = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, section_css)))
                    section_link.click()
                    # 2. 等待目标出现
                    WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.LINK_TEXT, link_text)))
                
                # 3. 提取数据
                data = fetch_data_logic(driver, indicators)
                if not data:
                    logging.warning(f"Economics: {link_text} 板块未提取到数据，尝试重试...")
                    raise Exception("No data extracted")
                return data
            except Exception as e:
                logging.warning(f"Economics 导航/抓取重试 {i+1}/{max_retries} ({link_text}): {e}")
                time.sleep(2)
        return []

    try:
        # 建立表结构
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS Economics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            price REAL,
            UNIQUE(date, name)
        );''')
        conn.commit()
        
        # 定义指标组
        Economics1 = {
            "GDP Growth Rate": "USGDP", "Non Farm Payrolls": "USNonFarm",
            "Inflation Rate": "USCPI", "Interest Rate": "USInterest",
            "Balance of Trade": "USTrade", "Consumer Confidence": "USConfidence",
            "Retail Sales MoM": "USRetailM", "Unemployment Rate": "USUnemploy",
            "Non Manufacturing PMI": "USNonPMI"
        }
        Economics2 = {"Initial Jobless Claims": "USInitial", "ADP Employment Change": "USNonFarmA"}
        Economics3 = {
            "Core PCE Price Index Annual Change": "CorePCEY", "Core PCE Price Index MoM": "CorePCEM",
            "Core Inflation Rate": "CoreCPI", "Producer Prices Change": "USPPI",
            "Core Producer Prices YoY": "CorePPI", "PCE Price Index Annual Change": "PCEY",
            "Import Prices MoM": "ImportPriceM", "Import Prices YoY": "ImportPriceY"
        }
        Economics4 = {"Real Consumer Spending": "USConspending"}

        data_to_insert = []

        # 1. 初始页面加载 + 第一组数据
        # 使用通用重试器加载主页
        data_to_insert.extend(fetch_with_retry(
            driver, 
            'https://tradingeconomics.com/united-states/indicators', 
            lambda d: fetch_data_logic(d, Economics1), 
            task_name="Economics-Main"
        ))
        
        # 2. 后续板块导航 (使用自定义的导航重试逻辑)
        # 注意：这里不需要 driver.get，因为是在当前页面操作
        
        # Labour
        data_to_insert.extend(navigate_and_fetch_retry(
            driver, 'a[data-bs-target="#labour"]', "Manufacturing Payrolls", Economics2
        ))
        
        # Prices
        data_to_insert.extend(navigate_and_fetch_retry(
            driver, 'a[data-bs-target="#prices"]', "Core Consumer Prices", Economics3
        ))
        
        # GDP
        data_to_insert.extend(navigate_and_fetch_retry(
            driver, 'a[data-bs-target="#gdp"]', "GDP Constant Prices", Economics4
        ))

        # 插入逻辑
        for entry in data_to_insert:
            # 检查是否有重复（保留原逻辑）
            c = conn.cursor()
            c.execute('''SELECT price FROM Economics WHERE name = ? AND date < ? ORDER BY ABS(julianday(date) - julianday(?)) LIMIT 1''', 
                      (entry[1], entry[0], entry[0]))
            result = c.fetchone()
            if result and float(result[0]) == float(entry[2]):
                logging.info(f"Skipping {entry[1]} on {entry[0]}: Price same as recent entry.")
            else:
                try:
                    c.execute('INSERT INTO Economics (date, name, price) VALUES (?, ?, ?)', entry)
                    conn.commit()
                    logging.info(f"Economics: 插入 {entry[1]} = {entry[2]}")
                except sqlite3.IntegrityError:
                    pass

    except Exception as e:
        logging.error(f"Economics 模块出错: {e}")
    finally:
        driver.quit()
        conn.close()

# ================= 主程序入口 =================

def main():
    # 1. 检查日期
    if not check_is_workday():
        msg = "今天是周日或周一，不执行更新操作。" 
        logging.info(msg)
        display_dialog(msg)
        return

    # 2. 顺次执行任务
    
    try:
        run_commodities()
    except Exception as e:
        logging.error(f"Main Loop - Commodities Error: {e}")

    try:
        run_currency_cny2()
    except Exception as e:
        logging.error(f"Main Loop - Currency CNY2 Error: {e}")

    try:
        run_currency_cny()
    except Exception as e:
        logging.error(f"Main Loop - Currency CNY Error: {e}")

    try:
        run_bonds()
    except Exception as e:
        logging.error(f"Main Loop - Bonds Error: {e}")

    try:
        run_indices()
    except Exception as e:
        logging.error(f"Main Loop - Indices Error: {e}")
        
    try:
        run_economics()
    except Exception as e:
        logging.error(f"Main Loop - Economics Error: {e}")

    logging.info(">>> 所有任务执行完毕")

if __name__ == "__main__":
    main()
