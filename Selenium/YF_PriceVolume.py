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
import pyautogui
import threading
import argparse
import sqlite3
import datetime
import subprocess
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox, QDesktopWidget

def create_mouse_prompt():
    """创建询问是否启用鼠标移动的弹窗"""
    # 确保只创建一个QApplication实例
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # 创建消息框
    msg_box = QMessageBox()
    msg_box.setWindowTitle("功能选择")
    msg_box.setText("是否启用鼠标随机移动防止黑屏功能？")
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    msg_box.setDefaultButton(QMessageBox.No)
    
    # 设置窗口标志，使其始终显示在最前面
    msg_box.setWindowFlags(msg_box.windowFlags() | 
                          Qt.WindowStaysOnTopHint | 
                          Qt.WindowActive)
    
    # 移动到屏幕中心
    center = QDesktopWidget().availableGeometry().center()
    msg_box.move(center.x() - msg_box.width() // 2,
                 center.y() - msg_box.height() // 2)
    
    # 激活窗口
    msg_box.show()
    msg_box.activateWindow()
    msg_box.raise_()
    
    # 显示对话框并获取结果
    result = msg_box.exec_()
    
    # 转换结果为布尔值
    return result == QMessageBox.Yes

def show_alert(message):
    # AppleScript 代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    # 使用 subprocess 调用 osascript
    subprocess.run(['osascript', '-e', applescript_code], check=True)

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

def clear_empty_json(json_file_path):
    """
    清空 Sectors_empty.json 中所有分组的 symbol 列表，保留分组结构
    """
    try:
        with open(json_file_path, 'r') as f:
            data = json.load(f)
        for sector in data:
            data[sector] = []
        with open(json_file_path, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"已清空 {json_file_path} 中的所有 symbol")
    except Exception as e:
        print(f"清空整个 JSON 时出错: {e}")

def parse_arguments():
    parser = argparse.ArgumentParser(description='股票数据抓取工具')
    parser.add_argument('--mode', type=str, default='normal', 
                        help='运行模式: normal或empty。默认为normal')
    parser.add_argument('--clear', action='store_true',
                        help='在 empty 模式下，抓取结束后清空 Sectors_empty.json 中剩余的 symbols')
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
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            price REAL
        )
        ''')
    else:
        # 标准表结构，包含volume
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
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
    
    # 根据命令行参数选择JSON文件路径
    if args.mode.lower() == 'empty':
        json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json"
        if not check_empty_json_has_content(json_file_path):
            show_alert("Empty.json 文件中没有任何内容，程序将退出。")
            return
    elif args.mode.lower() == 'normal':
        # 参数为normal格式
        json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json"
    else:
        json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_US_holiday.json"
    
    # 加载symbol映射关系
    mapping_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/symbol_mapping.json"
    symbol_mapping = load_symbol_mapping(mapping_file_path)

    enable_mouse_movement = create_mouse_prompt()

    if enable_mouse_movement:
        # 开启防挂机鼠标线程
        threading.Thread(target=move_mouse_periodically, daemon=True).start()
        print("已启用鼠标随机移动功能")
    else:
        print("未启用鼠标随机移动功能")

    # 设置Chrome选项以提高性能
    chrome_options = Options()
    
    # --- Headless模式相关设置 ---
    chrome_options.add_argument('--headless=new') # 推荐使用新的 headless 模式
    chrome_options.add_argument('--window-size=1920,1080')

    # --- 伪装设置 ---
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.7049.115" # 你可以更新为一个最新的Chrome User-Agent
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

    # 设置ChromeDriver路径
    chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
    service = Service(executable_path=chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # 设置更短的超时时间
    driver.set_page_load_timeout(20)  # 页面加载超时时间
    driver.set_script_timeout(10)  # 脚本执行超时时间

    # 连接SQLite数据库
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
    conn = sqlite3.connect(db_path)
    
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
            for symbol in tqdm(symbols,
                               desc=f"{sector}",
                               unit="symbol",
                               leave=False):
                try:
                    url = f"https://finance.yahoo.com/quote/{symbol}/"
                    driver.get(url)
                    
                    # 查找Price数据 - 使用新的XPath
                    price_element = wait_for_element(driver, By.XPATH, "//span[@data-testid='qsp-price']", timeout=7)
                    price = None
                    if price_element:
                        price_text = price_element.text
                        try:
                            price = float(price_text.replace(',', ''))
                        except ValueError:
                            print(f"无法转换价格: {price_text}")
                    
                    # 决定要存储的name
                    display_name = symbol
                    if use_mapping and symbol in symbol_mapping:
                        display_name = symbol_mapping[symbol]
                    
                    if is_no_volume:
                        # 不需要volume的分组，只存储价格
                        if price is not None:
                            cursor = conn.cursor()
                            cursor.execute(f'''
                            INSERT INTO {sector} (date, name, price)
                            VALUES (?, ?, ?)
                            ''', (current_date, display_name, price))
                            conn.commit()
                            
                            print(f"已保存 {display_name} 至 {sector}：价格={price}")
                            
                            # 1) 清除 JSON 中的 symbol
                            if args.mode.lower() == 'empty':
                                clear_symbols_from_json(json_file_path, sector, symbol)
                                # 2) 比较“前天”价格
                                cursor.execute(f'''
                                    SELECT price FROM {sector}
                                    WHERE date = ? AND name = ?
                                ''', (prev_date, display_name))
                                row = cursor.fetchone()
                                if row:
                                    prev_price = row[0]
                                    if prev_price == price:
                                        # show_alert(
                                        #     f"{display_name} 在 {sector} 中：\n"
                                        #     f"{prev_date} 价格 = {prev_price}\n"
                                        #     f"{current_date} 价格 = {price}\n"
                                        #     "价格未发生变化！"
                                        # )
                                        print(f"抓取 {display_name} 成功，价格未发生变化")
                        else:
                            print(f"抓取 {symbol} 失败，未能获取到价格数据")
                    else:
                        # 需要抓取volume的分组
                        volume_element = wait_for_element(driver, By.XPATH, "//fin-streamer[@data-field='regularMarketVolume']", timeout=7)
                        volume = None
                        if volume_element:
                            volume_text = volume_element.text
                            try:
                                volume = int(volume_text.replace(',', ''))
                            except ValueError:
                                print(f"无法转换成交量: {volume_text}")
                        
                        # 如果成功获取到数据，写入数据库
                        if price is not None and volume is not None:
                            cursor = conn.cursor()
                            cursor.execute(f'''
                            INSERT INTO {sector} (date, name, price, volume)
                            VALUES (?, ?, ?, ?)
                            ''', (current_date, display_name, price, volume))
                            conn.commit()
                            
                            print(f"已保存 {display_name} 至 {sector}：价格={price}, 成交量={volume}")
                            
                            # 如果是empty模式，则在成功保存后清除该symbol
                            if args.mode.lower() == 'empty':
                                clear_symbols_from_json(json_file_path, sector, symbol)
                                
                                # 比较“前天”价格
                                cursor.execute(f'''
                                    SELECT price FROM {sector}
                                    WHERE date = ? AND name = ?
                                ''', (prev_date, display_name))
                                row = cursor.fetchone()
                                if row:
                                    prev_price = row[0]
                                    if prev_price == price:
                                        # show_alert(
                                        #     f"{display_name} 在 {sector} 中：\n"
                                        #     f"{prev_date} 价格 = {prev_price}\n"
                                        #     f"{current_date} 价格 = {price}\n"
                                        #     "价格未发生变化！"
                                        # )
                                        print(f"抓取 {display_name} 成功，价格未发生变化")
                        else:
                            print(f"抓取 {symbol} 失败，未能获取到完整数据")
                
                # 在抓取失败的逻辑中添加
                except Exception as e:
                    print(f"抓取 {symbol} 时发生错误: {e}")
                    # 添加调试代码
                    try:
                        driver.save_screenshot(f'debug_screenshot_{symbol}.png')
                        with open(f'debug_page_source_{symbol}.html', 'w', encoding='utf-8') as f:
                            f.write(driver.page_source)
                        print(f"已保存 {symbol} 的调试截图和页面源码。")
                    except Exception as debug_e:
                        print(f"保存调试信息时出错: {debug_e}")
                
                # 添加短暂延迟，避免请求过于频繁
                time.sleep(random.uniform(1, 2))

    finally:
        # 关闭数据库连接
        conn.close()
        
        # 关闭浏览器
        driver.quit()

        # 只有在 empty 模式下才做下面的判断
        if args.mode.lower() == 'empty':
            if args.clear:
                # 带了 --clear，执行整表清空
                clear_empty_json(json_file_path)
                show_alert("股票数据抓取完成并已写入数据库！\n同时已清空 Sectors_empty.json 中的所有 symbols。")
            else:
                # 未带 --clear，只检查是否所有分组都已空
                if not check_empty_json_has_content(json_file_path):
                    # --- 代码修改开始 ---
                    # 抓取完成，所有分组已清空，现在调用另一个脚本
                    show_alert("所有分组已清空 ✅\n✅ Sectors_empty.json 中没有剩余 symbols。\n\n接下来将调用补充脚本...")
                    
                    script_to_run = "/Users/yanzhang/Documents/Financial_System/Operations/Insert_Currencies_Index.py"
                    
                    try:
                        print(f"正在调用脚本: {script_to_run}")
                        # 使用 subprocess.run 执行脚本
                        # sys.executable 确保使用当前 Python 解释器
                        # check=True 会在脚本执行失败时抛出异常
                        subprocess.run([sys.executable, script_to_run], check=True)
                        
                        print(f"脚本 {script_to_run} 执行成功。")
                        show_alert(f"补充脚本执行成功！\n\n路径:\n{script_to_run}")

                    except FileNotFoundError:
                        error_message = f"错误：找不到要调用的脚本。\n请检查路径是否正确：\n{script_to_run}"
                        print(error_message)
                        show_alert(error_message)
                    except subprocess.CalledProcessError as e:
                        error_message = f"执行脚本 {script_to_run} 时发生错误。\n\n错误信息: {e}"
                        print(error_message)
                        show_alert(error_message)
                    except Exception as e:
                        error_message = f"调用脚本时发生未知错误: {e}"
                        print(error_message)
                        show_alert(error_message)
                    # --- 代码修改结束 ---
                else:
                    show_alert("⚠️ 有分组仍有 symbols 未清空\n⚠️ 请检查 Sectors_empty.json 。")

        print("数据抓取和保存完成！")

if __name__ == "__main__":
    main()