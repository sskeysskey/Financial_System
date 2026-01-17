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
    # Windows 路径优化：使用 raw string (r"...") 时，单斜杠即可
    CHROME_BINARY_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(CHROME_BINARY_PATH):
        CHROME_BINARY_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver.exe")
else:
    CHROME_BINARY_PATH = "/usr/bin/google-chrome"
    CHROME_DRIVER_PATH = "/usr/bin/chromedriver"

# ========================================================

def show_alert(message):
    """
    跨平台弹窗提示
    """
    if platform.system() == 'Darwin':
        # Mac 原生 AppleScript
        try:
            applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        except Exception:
            pass
    else:
        # Windows Tkinter
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("提示", message)
        root.destroy()

def run_check_yesterday():
    """执行 Check_yesterday.py 脚本"""
    try:
        print(f"\n[系统信息] 正在调用补充脚本: {CHECK_YESTERDAY_SCRIPT_PATH}")
        # 使用当前运行环境的 Python 解释器，无需硬编码路径
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
        if items:  # 如果该分组有任何项目
            return True
    return False

# 新增：读取symbol_mapping.json
def load_symbol_mapping(mapping_file_path):
    try:
        if not os.path.exists(mapping_file_path):
            return {}
        with open(mapping_file_path, 'r') as file:
            return json.load(file)
    except Exception as e:
        print(f"读取symbol映射文件时发生错误: {str(e)}")
        return {}

# 读取JSON文件获取股票符号和分组
def get_stock_symbols_from_json(json_file_path):
    # 扩展目标分类
    target_sectors = [
        'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
        'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
        'Communication_Services', 'Financial_Services', 'Healthcare', 'ETFs',
        # 新增分组
        'Bonds', 'Currencies', 'Crypto', 'Commodities', 'Economics', 'Indices'
    ]
    
    if not os.path.exists(json_file_path):
        print(f"错误：找不到配置文件 {json_file_path}")
        return {}

    with open(json_file_path, 'r') as file:
        sectors_data = json.load(file)
    
    symbols_by_sector = {}
    for sector, symbols in sectors_data.items():
        # 只保留目标分类且有内容的数据
        if sector in target_sectors and symbols:
            symbols_by_sector[sector] = symbols
    
    return symbols_by_sector

# 优化等待策略的函数
def wait_for_element(driver, by, value, timeout=10):
    """等待元素加载完成并返回"""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        return element
    except Exception as e:
        return None

# 确保数据库表存在 - 针对不同类型的表使用不同的结构
def ensure_table_exists(conn, table_name, table_type="standard"):
    cursor = conn.cursor()
    
    if table_type == "no_volume":
        # 不需要volume字段的表结构
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS "{table_name}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            price REAL
        )
        ''')
    else:
        # 标准表结构，包含volume
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS "{table_name}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            price REAL,
            volume INTEGER
        )
        ''')
    
    conn.commit()

# 修改：判断分组类型的函数，从no_volume_sectors中移除'Indices'
def is_no_volume_sector(sector):
    """判断是否为不需要抓取volume的分组"""
    no_volume_sectors = ['Bonds', 'Currencies', 'Crypto', 'Commodities', 'Economics']
    return sector in no_volume_sectors

# 新增：判断是否需要使用symbol映射的函数
def needs_symbol_mapping(sector):
    """判断是否需要使用symbol_mapping中的名称"""
    mapping_sectors = ['Bonds', 'Currencies', 'Crypto', 'Commodities', 'Economics', 'Indices']
    return sector in mapping_sectors

def main():
    # 解析命令行参数
    args = parse_arguments()
    
    # 1. 根据命令行参数选择JSON文件路径
    if args.mode.lower() == 'empty':
        json_file_path = SECTORS_EMPTY_JSON
        
        # 如果一开始就是空的，执行脚本并退出
        if not check_empty_json_has_content(json_file_path):
            print("\n[通知] Sectors_empty.json 为空，准备执行 Check_yesterday...")
            run_check_yesterday() # 执行你的查询脚本
            show_alert("Sectors_empty.json 为空。\nCheck_yesterday 脚本已执行完毕，程序将退出。")
            return
            
    elif args.mode.lower() == 'normal':
        json_file_path = SECTORS_TODAY_JSON
    else:
        json_file_path = SECTORS_HOLIDAY_JSON
    
    symbol_mapping = load_symbol_mapping(SYMBOL_MAPPING_JSON)

    # ==========================================
    # [修改点] Selenium 配置区域
    # ==========================================
    chrome_options = Options()
    
    if os.path.exists(CHROME_BINARY_PATH):
        chrome_options.binary_location = CHROME_BINARY_PATH
    else:
        print(f"警告：未找到指定 Chrome 路径 {CHROME_BINARY_PATH}，尝试使用系统默认...")

    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # --- 伪装设置 ---
    # 更新 User-Agent 为较新的版本，匹配 Beta
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    chrome_options.add_argument(f'user-agent={user_agent}')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # --- 性能相关设置 ---
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.page_load_strategy = 'eager'

    if not os.path.exists(CHROME_DRIVER_PATH):
        print(f"错误: 未找到驱动文件 {CHROME_DRIVER_PATH}")
        return

    service = Service(executable_path=CHROME_DRIVER_PATH)
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Selenium 启动失败: {e}")
        return
        
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(10)  

    # ==========================================
    # 连接SQLite数据库
    # [新增] 确保数据库目录存在，防止新机器报错
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    
    # 从JSON文件获取股票符号和分组
    symbols_by_sector = get_stock_symbols_from_json(json_file_path)
    
    # 获取当前日期
    current_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    # 计算“前天”日期
    prev_date = (datetime.datetime.now() - datetime.timedelta(days=2)).strftime('%Y-%m-%d')
    
    try:
        # 逐个分组抓取股票数据
        for sector, symbols in tqdm(list(symbols_by_sector.items()),
                                   desc="Sectors",
                                   unit="sector"):
            # 判断该分组是否需要抓取volume
            is_no_volume = is_no_volume_sector(sector)
            
            # 判断是否需要使用symbol映射
            use_mapping = needs_symbol_mapping(sector)
            
            # 根据分组类型确保对应表存在
            table_type = "no_volume" if is_no_volume else "standard"
            ensure_table_exists(conn, sector, table_type)
            
            # 内层进度：每个分组里的 symbol
            for symbol in tqdm(symbols, desc=f"{sector}", unit="symbol", leave=False):
                
                # --- [修改开始] 重试机制 ---
                max_retries = 3
                success = False # 标记是否成功
                
                for attempt in range(max_retries):
                    try:
                        url = f"https://finance.yahoo.com/quote/{symbol}/history/"
                        
                        # 每次尝试都重新加载页面
                        if attempt > 0:
                            # 如果是重试，稍微多等一下再请求
                            time.sleep(random.uniform(2, 4))
                            print(f"\n正在重试 {symbol} (第 {attempt+1}/{max_retries} 次)...")
                        
                        driver.get(url)
                        
                        # 查找 Price
                        price_element = wait_for_element(driver, By.XPATH, "//span[@data-testid='qsp-price']", timeout=7)
                        price = None
                        if price_element:
                            price_text = price_element.text
                            try:
                                if price_text == '-':
                                    price = 0.0
                                else:
                                    price = float(price_text.replace(',', ''))
                            except ValueError:
                                print(f"无法转换价格: {price_text}")

                        # 决定 display_name
                        display_name = symbol
                        if use_mapping and symbol in symbol_mapping:
                            display_name = symbol_mapping[symbol]
                        
                        # --- 核心逻辑分支 ---
                        
                        if is_no_volume:
                            # 1. 不需要 Volume 的情况
                            if price is not None:
                                cursor = conn.cursor()
                                cursor.execute(f'''
                                INSERT OR REPLACE INTO "{sector}" (date, name, price)
                                VALUES (?, ?, ?)
                                ''', (current_date, display_name, price))
                                conn.commit()
                                
                                print(f"已保存/更新 {display_name} 至 {sector}：价格={price}")
                                
                                # 处理 empty 模式的清除和对比
                                if args.mode.lower() == 'empty':
                                    clear_symbols_from_json(json_file_path, sector, symbol)
                                    cursor.execute(f'SELECT price FROM "{sector}" WHERE date = ? AND name = ?', (prev_date, display_name))
                                    row = cursor.fetchone()
                                    if row and row[0] == price:
                                        print(f"抓取 {display_name} 成功，价格未发生变化")
                                
                                success = True # 标记成功
                                break # 跳出重试循环
                            else:
                                # 如果 price 是 None，抛出异常或继续循环以触发重试
                                print(f"尝试 {attempt+1}: 抓取 {symbol} 失败，未能获取到价格。")
                        
                        else:
                            # 2. 需要 Volume 的情况
                            volume_xpath = "//div[@data-testid='history-table']//table/tbody/tr[1]/td[last()]"
                            volume_element = wait_for_element(driver, By.XPATH, volume_xpath, timeout=7)
                            volume = None
                            if volume_element:
                                volume_text = volume_element.text
                                try:
                                    if volume_text == 'N/A' or volume_text == '-':
                                        volume = 0
                                    else:
                                        volume = int(volume_text.replace(',', ''))
                                except ValueError:
                                    print(f"无法转换成交量: {volume_text}")
                            
                            if price is not None and volume is not None:
                                cursor = conn.cursor()
                                cursor.execute(f'''
                                INSERT OR REPLACE INTO "{sector}" (date, name, price, volume)
                                VALUES (?, ?, ?, ?)
                                ''', (current_date, display_name, price, volume))
                                conn.commit()
                                
                                print(f"已保存/更新 {display_name} 至 {sector}：价格={price}, 成交量={volume}")
                                
                                if args.mode.lower() == 'empty':
                                    clear_symbols_from_json(json_file_path, sector, symbol)
                                    cursor.execute(f'SELECT price FROM "{sector}" WHERE date = ? AND name = ?', (prev_date, display_name))
                                    row = cursor.fetchone()
                                    if row and row[0] == price:
                                        print(f"抓取 {display_name} 成功，价格未发生变化")
                                
                                success = True # 标记成功
                                break # 跳出重试循环
                            else:
                                print(f"尝试 {attempt+1}: 抓取 {symbol} 失败 (Price: {price}, Volume: {volume})。")

                    except Exception as e:
                        print(f"尝试 {attempt+1} 发生错误: {str(e)}")
                        # 继续下一次循环重试

                # --- 循环结束后的判断 ---
                if not success:
                    print(f"❌ 最终失败: {symbol} 在尝试 {max_retries} 次后仍未获取到数据，跳转下一个。")
                
                # 添加短暂延迟，避免请求过于频繁
                time.sleep(random.uniform(1, 2))

    finally:
        # 关闭数据库连接
        conn.close()
        
        # 关闭浏览器
        driver.quit()

        # 只有在 empty 模式下才做下面的判断
        if args.mode.lower() == 'empty':
            # 检查是否所有 symbol 都抓取完并清空了
            if not check_empty_json_has_content(json_file_path):
                if args.weekend:
                    # 带了 --weekend，执行简单指令即可
                    show_alert("所有分组已清空 ✅\n✅ Sectors_empty.json 中没有剩余 symbols。\n\n接下来程序将结束...")
                else:
                    # 抓取完成，所有分组已清空，现在调用另一个脚本
                    show_alert("所有分组已清空 ✅\n✅ Sectors_empty.json 中没有剩余 symbols。\n\n接下来将调用补充脚本...")
                    script_to_run = INSERT_SCRIPT_PATH
                    try:
                        print(f"正在调用脚本: {script_to_run}")
                        subprocess.run([sys.executable, script_to_run], check=True)
                        print(f"脚本 {script_to_run} 执行成功。")
                        show_alert(f"补充脚本执行成功！\n\n路径:\n{script_to_run}")
                    except Exception as e:
                        print(f"调用脚本出错: {e}")
            else:
                show_alert("⚠️ 有分组仍有 symbols 未清空\n⚠️ 请检查 Sectors_empty.json 。")
        print("数据抓取和保存完成！")

if __name__ == "__main__":
    main()
