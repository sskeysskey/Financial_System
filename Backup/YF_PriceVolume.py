from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from tqdm import tqdm
import sys
import json
import time
import random
import argparse
import sqlite3
import datetime
import subprocess
import os
import platform
import tkinter as tk
from tkinter import messagebox

# ================= 配置区域 (跨平台修改) =================

# 1. 动态获取主目录
USER_HOME = os.path.expanduser("~")

# 2. 定义基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")

# 3. 具体业务文件路径
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")
SECTORS_EMPTY_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_empty.json")
SECTORS_TODAY_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_today.json")
SECTORS_HOLIDAY_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_US_holiday.json")
SYMBOL_MAPPING_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "symbol_mapping.json")
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
INSERT_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Operations", "Insert_Currencies_Index.py")

# 4. 浏览器与驱动路径 (跨平台适配)
if platform.system() == 'Darwin':
    CHROME_BINARY_PATH = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver_beta")
elif platform.system() == 'Windows':
    CHROME_BINARY_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(CHROME_BINARY_PATH):
        CHROME_BINARY_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver.exe")
else:
    CHROME_BINARY_PATH = "/usr/bin/google-chrome"
    CHROME_DRIVER_PATH = "/usr/bin/chromedriver"

# ========================================================

def show_alert(message):
    """跨平台弹窗提示"""
    if platform.system() == 'Darwin':
        try:
            applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        except Exception:
            pass
    else:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("提示", message)
        root.destroy()

def run_check_yesterday():
    """执行 Check_yesterday.py 脚本"""
    try:
        print(f"\n[系统信息] 正在调用补充脚本: {CHECK_YESTERDAY_SCRIPT_PATH}")
        result = subprocess.run(
            [sys.executable, CHECK_YESTERDAY_SCRIPT_PATH],
            check=True, 
            capture_output=True, 
            text=True, 
            encoding='utf-8'
        )
        print("--- Check_yesterday 输出 ---")
        print(result.stdout)
        print("---------------------------")
        return True
    except Exception as e:
        print(f"❌ 执行 Check_yesterday 失败: {e}")
        return False

def clear_symbols_from_json(json_file_path, sector, symbol):
    """从指定的JSON文件中清除特定分组中的特定符号"""
    try:
        with open(json_file_path, 'r') as file:
            data = json.load(file)
            
        if sector in data and symbol in data[sector]:
            data[sector].remove(symbol)
            
        with open(json_file_path, 'w') as file:
            json.dump(data, file, indent=4)
            
    except Exception as e:
        print(f"清除symbol时发生错误: {str(e)}")

def parse_arguments():
    parser = argparse.ArgumentParser(description='股票数据抓取工具')
    parser.add_argument('--mode', type=str, default='normal', 
                        help='运行模式: normal或empty。默认为normal')
    parser.add_argument('--clear', action='store_true',
                        help='在 empty 模式下，抓取结束后清空 Sectors_empty.json 中剩余的 symbols')
    parser.add_argument('--weekend', action='store_true',
                        help='在 周末 模式下，只抓取，不执行清空 Sectors_empty.json 操作')
    return parser.parse_args()

def check_empty_json_has_content(json_file_path):
    """检查empty.json中是否有任何分组包含内容"""
    if not os.path.exists(json_file_path):
        return False
    with open(json_file_path, 'r') as file:
        data = json.load(file)
    for group, items in data.items():
        if items:
            return True
    return False

def load_symbol_mapping(mapping_file_path):
    try:
        if not os.path.exists(mapping_file_path):
            return {}
        with open(mapping_file_path, 'r') as file:
            return json.load(file)
    except Exception as e:
        print(f"读取symbol映射文件时发生错误: {str(e)}")
        return {}

def get_stock_symbols_from_json(json_file_path):
    target_sectors = [
        'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
        'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
        'Communication_Services', 'Financial_Services', 'Healthcare', 'ETFs',
        'Bonds', 'Currencies', 'Crypto', 'Commodities', 'Economics', 'Indices'
    ]
    
    if not os.path.exists(json_file_path):
        print(f"错误：找不到配置文件 {json_file_path}")
        return {}

    with open(json_file_path, 'r') as file:
        sectors_data = json.load(file)
    
    symbols_by_sector = {}
    for sector, symbols in sectors_data.items():
        if sector in target_sectors and symbols:
            symbols_by_sector[sector] = symbols
    
    return symbols_by_sector

# ================= 数据库与表结构定义 =================

def get_table_type(sector):
    """根据分组判断表结构类型"""
    expanded_sectors = [
        'ETFs', 'Basic_Materials', 'Communication_Services', 'Consumer_Cyclical', 
        'Consumer_Defensive', 'Energy', 'Financial_Services', 'Healthcare', 
        'Industrials', 'Real_Estate', 'Technology', 'Utilities', 'Crypto'
    ]
    no_volume_sectors = ['Bonds', 'Currencies', 'Commodities', 'Economics']
    
    if sector in expanded_sectors:
        return "expanded"
    elif sector in no_volume_sectors:
        return "no_volume"
    else:
        return "standard" # 例如 Indices

def ensure_table_exists(conn, table_name, table_type):
    """确保数据库表存在，去除id字段，使用(date, name)作为联合主键"""
    cursor = conn.cursor()
    safe_table_name = f'"{table_name}"'
    
    if table_type == "expanded":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT,
            name TEXT,
            price REAL,
            volume INTEGER,
            open REAL,
            high REAL,
            low REAL,
            UNIQUE(date, name)
        )
        ''')
    elif table_type == "no_volume":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT,
            name TEXT,
            price REAL,
            UNIQUE(date, name)
        )
        ''')
    else: # standard
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT,
            name TEXT,
            price REAL,
            volume INTEGER,
            UNIQUE(date, name)
        )
        ''')
    conn.commit()

def needs_symbol_mapping(sector):
    mapping_sectors = ['Bonds', 'Currencies', 'Crypto', 'Commodities', 'Economics', 'Indices']
    return sector in mapping_sectors

# ================= JS 注入提取数据 =================

def extract_data_via_js(driver):
    """使用注入 JS 的方式快速提取表格最新一条数据"""
    js_script = """
    function getColumnIndices(table) {
        const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.textContent.trim());
        return {
            date: headers.indexOf('Date'),
            open: headers.findIndex(h => /0pen|Open/i.test(h)),
            high: headers.findIndex(h => /High/i.test(h)),
            low: headers.findIndex(h => /Low/i.test(h)),
            close: headers.findIndex(h => /Adj Close/i.test(h) || /Close\\*/i.test(h) || /^Close/i.test(h)),
            volume: headers.findIndex(h => /Volume/i.test(h))
        };
    }

    let tbl = document.querySelector('[data-testid="history-table"] table');
    if (!tbl) {
        const all = Array.from(document.querySelectorAll('table'));
        for (let t of all) {
            const ths = Array.from(t.querySelectorAll('thead th')).map(th => th.textContent.trim());
            if (ths.includes('Date')) {
                tbl = t; break;
            }
        }
    }
    
    if (!tbl) return { error: "未找到数据表格" };

    const cols = getColumnIndices(tbl);
    if (cols.date < 0 || cols.close < 0) return { error: "表头解析失败" };

    const rows = Array.from(tbl.querySelectorAll('tbody tr'));
    
    for (let r of rows) {
        const cells = Array.from(r.querySelectorAll('td'));
        if (cells.length <= Math.max(cols.date, cols.close)) continue;

        let rawDate = cells[cols.date].textContent.trim().split('::')[0].replace(/"/g, '');
        let d = new Date(rawDate);
        if (isNaN(d)) continue;
        
        let dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        
        let priceText = cells[cols.close].textContent.trim().replace(/,/g, '');
        let price = priceText === '-' ? 0.0 : parseFloat(priceText);
        if (isNaN(price)) continue;

        let volume = 0, open = null, high = null, low = null;
        if (cols.volume >= 0 && cells[cols.volume]) {
            let vText = cells[cols.volume].textContent.trim().replace(/,/g, '');
            let v = (vText === 'N/A' || vText === '-') ? 0 : parseInt(vText, 10);
            if (!isNaN(v)) volume = v;
        }
        if (cols.open >= 0 && cells[cols.open]) {
            let o = parseFloat(cells[cols.open].textContent.trim().replace(/,/g, ''));
            if (!isNaN(o)) open = o;
        }
        if (cols.high >= 0 && cells[cols.high]) {
            let h = parseFloat(cells[cols.high].textContent.trim().replace(/,/g, ''));
            if (!isNaN(h)) high = h;
        }
        if (cols.low >= 0 && cells[cols.low]) {
            let l = parseFloat(cells[cols.low].textContent.trim().replace(/,/g, ''));
            if (!isNaN(l)) low = l;
        }

        return { data: { date: dateStr, price: price, volume: volume, open: open, high: high, low: low } };
    }
    return { error: "未找到有效数据行" };
    """
    return driver.execute_script(js_script)

# ================= 主程序 =================

def main():
    args = parse_arguments()
    
    if args.mode.lower() == 'empty':
        json_file_path = SECTORS_EMPTY_JSON
        if not check_empty_json_has_content(json_file_path):
            print("\n[通知] Sectors_empty.json 为空，准备执行 Check_yesterday...")
            # run_check_yesterday()
            show_alert("Sectors_empty.json 为空。\nCheck_yesterday 脚本已执行完毕，程序将退出。")
            return
    elif args.mode.lower() == 'normal':
        json_file_path = SECTORS_TODAY_JSON
    else:
        json_file_path = SECTORS_HOLIDAY_JSON
    
    symbol_mapping = load_symbol_mapping(SYMBOL_MAPPING_JSON)

    # Selenium 配置
    chrome_options = Options()
    if os.path.exists(CHROME_BINARY_PATH):
        chrome_options.binary_location = CHROME_BINARY_PATH

    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--window-size=1920,1080')
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    chrome_options.add_argument(f'user-agent={user_agent}')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-images")
    chrome_options.page_load_strategy = 'eager'

    service = Service(executable_path=CHROME_DRIVER_PATH)
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Selenium 启动失败: {e}")
        return
        
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(10)  

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    symbols_by_sector = get_stock_symbols_from_json(json_file_path)
    
    # 这里的 prev_date 用于 empty 模式比对
    prev_date = (datetime.datetime.now() - datetime.timedelta(days=2)).strftime('%Y-%m-%d')
    
    try:
        for sector, symbols in tqdm(list(symbols_by_sector.items()), desc="Sectors", unit="sector"):
            table_type = get_table_type(sector)
            ensure_table_exists(conn, sector, table_type)
            use_mapping = needs_symbol_mapping(sector)
            
            for symbol in tqdm(symbols, desc=f"{sector}", unit="symbol", leave=False):
                max_retries = 3
                success = False
                
                for attempt in range(max_retries):
                    try:
                        url = f"https://finance.yahoo.com/quote/{symbol}/history/"
                        if attempt > 0:
                            time.sleep(random.uniform(2, 4))
                            print(f"\n正在重试 {symbol} (第 {attempt+1}/{max_retries} 次)...")
                        
                        driver.get(url)
                        
                        # 等待表格加载
                        WebDriverWait(driver, 8).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
                        )
                        time.sleep(1) # 缓冲等待JS渲染
                        
                        # 使用 JS 提取数据
                        result = extract_data_via_js(driver)
                        if "error" in result:
                            raise Exception(result["error"])
                            
                        data = result["data"]
                        scraped_date = data["date"]
                        price = data["price"]
                        volume = data["volume"]
                        open_p = data["open"]
                        high_p = data["high"]
                        low_p = data["low"]

                        # 决定 display_name
                        display_name = symbol
                        if use_mapping and symbol in symbol_mapping:
                            display_name = symbol_mapping[symbol]
                        
                        cursor = conn.cursor()
                        safe_table = f'"{sector}"'
                        
                        # 根据表类型插入数据 (使用 ON CONFLICT DO UPDATE 替代 REPLACE 以符合新主键)
                        if table_type == "expanded":
                            cursor.execute(f'''
                            INSERT INTO {safe_table} (date, name, price, volume, open, high, low)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(date, name) DO UPDATE SET
                                price=excluded.price, volume=excluded.volume,
                                open=excluded.open, high=excluded.high, low=excluded.low
                            ''', (scraped_date, display_name, price, volume, open_p, high_p, low_p))
                        elif table_type == "no_volume":
                            cursor.execute(f'''
                            INSERT INTO {safe_table} (date, name, price)
                            VALUES (?, ?, ?)
                            ON CONFLICT(date, name) DO UPDATE SET price=excluded.price
                            ''', (scraped_date, display_name, price))
                        else: # standard
                            cursor.execute(f'''
                            INSERT INTO {safe_table} (date, name, price, volume)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(date, name) DO UPDATE SET
                                price=excluded.price, volume=excluded.volume
                            ''', (scraped_date, display_name, price, volume))
                            
                        conn.commit()
                        print(f"已保存 {display_name} 至 {sector}：日期={scraped_date}, 价格={price}")
                        
                        # empty 模式处理
                        if args.mode.lower() == 'empty':
                            clear_symbols_from_json(json_file_path, sector, symbol)
                            cursor.execute(f'SELECT price FROM {safe_table} WHERE date = ? AND name = ?', (prev_date, display_name))
                            row = cursor.fetchone()
                            if row and row[0] == price:
                                print(f"抓取 {display_name} 成功，价格未发生变化")
                        
                        success = True
                        break # 成功则跳出重试循环

                    except Exception as e:
                        print(f"尝试 {attempt+1} 发生错误: {str(e)}")

                if not success:
                    print(f"❌ 最终失败: {symbol} 在尝试 {max_retries} 次后仍未获取到数据。")
                
                time.sleep(random.uniform(1, 2))

    finally:
        conn.close()
        driver.quit()

        if args.mode.lower() == 'empty':
            if not check_empty_json_has_content(json_file_path):
                if args.weekend:
                    show_alert("所有分组已清空 ✅\n✅ Sectors_empty.json 中没有剩余 symbols。\n\n接下来程序将结束...")
                else:
                    show_alert("所有分组已清空 ✅\n✅ Sectors_empty.json 中没有剩余 symbols。\n\n接下来将调用补充脚本...")
                    try:
                        print(f"正在调用脚本: {INSERT_SCRIPT_PATH}")
                        subprocess.run([sys.executable, INSERT_SCRIPT_PATH], check=True)
                        show_alert(f"补充脚本执行成功！\n\n路径:\n{INSERT_SCRIPT_PATH}")
                    except Exception as e:
                        print(f"调用脚本出错: {e}")
            else:
                show_alert("⚠️ 有分组仍有 symbols 未清空\n⚠️ 请检查 Sectors_empty.json 。")
        print("数据抓取和保存完成！")

if __name__ == "__main__":
    main()