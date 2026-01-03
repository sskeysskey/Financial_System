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

# 新增：定义 Check_yesterday 脚本的路径
CHECK_YESTERDAY_SCRIPT_PATH = '/Users/yanzhang/Coding/Financial_System/Query/Check_yesterday.py'
# 新增：定义 Python 解释器路径（参考你第二个程序中的路径）
PYTHON_INTERPRETER = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'

def show_alert(message):
    # AppleScript 代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    # 使用 subprocess 调用 osascript
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def run_check_yesterday():
    """执行 Check_yesterday.py 脚本"""
    try:
        print(f"\n[系统信息] 正在调用补充脚本: {CHECK_YESTERDAY_SCRIPT_PATH}")
        # 使用指定的 Python 解释器运行
        result = subprocess.run(
            [PYTHON_INTERPRETER, CHECK_YESTERDAY_SCRIPT_PATH],
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
    with open(json_file_path, 'r') as file:
        data = json.load(file)
    
    for group, items in data.items():
        if items:  # 如果该分组有任何项目
            return True
    
    return False

# 新增：读取symbol_mapping.json
def load_symbol_mapping(mapping_file_path):
    try:
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
        json_file_path = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_empty.json"
        
        # --- [修改点 1]：如果一开始就是空的，执行脚本并退出 ---
        if not check_empty_json_has_content(json_file_path):
            print("\n[通知] Sectors_empty.json 为空，准备执行 Check_yesterday...")
            run_check_yesterday() # 执行你的查询脚本
            show_alert("Sectors_empty.json 为空。\nCheck_yesterday 脚本已执行完毕，程序将退出。")
            return
            
    elif args.mode.lower() == 'normal':
        # 参数为normal格式
        json_file_path = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_today.json"
    else:
        json_file_path = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_US_holiday.json"
    
    # 加载symbol映射关系
    mapping_file_path = "/Users/yanzhang/Coding/Financial_System/Modules/symbol_mapping.json"
    symbol_mapping = load_symbol_mapping(mapping_file_path)

    # ==========================================
    # [修改点] Selenium 配置区域
    # ==========================================
    chrome_options = Options()
    
    # 1. 指定使用 Chrome Beta 浏览器应用
    chrome_options.binary_location = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"

    # --- Headless模式相关设置 ---
    chrome_options.add_argument('--headless=new') # 推荐使用新的 headless 模式
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
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
    chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

    # 2. 设置 ChromeDriver 路径 (指向 Beta 版驱动)
    # 确保这个文件存在于你的文件夹中
    chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver_beta"
    
    # 检查驱动是否存在，防止报错
    import os
    if not os.path.exists(chrome_driver_path):
        print(f"错误: 未找到驱动文件 {chrome_driver_path}")
        return

    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # 设置超时
    driver.set_page_load_timeout(30) # 稍微增加一点容错
    driver.set_script_timeout(10)  

    # ==========================================
    # 连接SQLite数据库
    db_path = "/Users/yanzhang/Coding/Database/Finance.db"
    conn = sqlite3.connect(db_path, timeout=60.0)
    
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
                    # 可选：这里可以记录失败的 symbol 到一个列表，或者保存截图
                    
                # [修改结束]
                
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
                    script_to_run = "/Users/yanzhang/Coding/Financial_System/Operations/Insert_Currencies_Index.py"
                    try:
                        print(f"正在调用脚本: {script_to_run}")
                        # 使用 subprocess.run 执行脚本
                        # sys.executable 确保使用当前 Python 解释器
                        # check=True 会在脚本执行失败时抛出异常
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
