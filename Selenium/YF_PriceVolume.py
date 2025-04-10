from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import json
import time
import random
import pyautogui
import threading
import argparse
import sqlite3
import datetime
import subprocess

def show_alert(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    process = subprocess.run(['osascript', '-e', applescript_code], check=True)

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

# 新增：命令行参数处理
def parse_arguments():
    parser = argparse.ArgumentParser(description='股票数据抓取工具')
    parser.add_argument('--mode', type=str, default='normal', 
                        help='运行模式: normal或empty。默认为normal')
    return parser.parse_args()

def check_empty_json_has_content(json_file_path):
    """检查empty.json中是否有任何分组包含内容"""
    with open(json_file_path, 'r') as file:
        data = json.load(file)
    
    for group, items in data.items():
        if items:  # 如果该分组有任何项目
            return True
    
    return False

# 读取JSON文件获取股票符号和分组
def get_stock_symbols_from_json(json_file_path):
    # 指定要提取的目标分类
    target_sectors = [
        'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
        'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
        'Communication_Services', 'Financial_Services', 'Healthcare'
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

# 确保数据库表存在
def ensure_table_exists(conn, table_name):
    cursor = conn.cursor()
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

def main():
    # 解析命令行参数
    args = parse_arguments()
    
    # 根据命令行参数选择JSON文件路径
    if args.mode.lower() == 'empty':
        json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json"
        
        # 检查empty.json是否有内容
        has_content = check_empty_json_has_content(json_file_path)
        
        # 如果没有内容，弹窗提示并退出程序
        if not has_content:
            show_alert(f"Empty.json文件中没有任何内容，程序将退出。")
            return
    else:
        # 参数为normal格式
        json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
        # json_file_path = "/Users/yanzhang/Documents/Financial_System/Test/Sectors_All_test.json"
    
    # 在主程序开始前启动鼠标移动线程
    mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
    mouse_thread.start()

    # 设置Chrome选项以提高性能
    chrome_options = Options()
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
    
    try:
        # 逐个分组抓取股票数据
        for sector, symbols in symbols_by_sector.items():
            # 确保表存在
            ensure_table_exists(conn, sector)
            
            for symbol in symbols:
                try:
                    url = f"https://finance.yahoo.com/quote/{symbol}/"
                    driver.get(url)
                    
                    # 查找Price数据 - 使用新的XPath
                    price_element = wait_for_element(driver, By.XPATH, "//span[@data-testid='qsp-price']", timeout=5)
                    price = None
                    if price_element:
                        price_text = price_element.text
                        try:
                            price = float(price_text.replace(',', ''))
                        except ValueError:
                            print(f"无法转换价格: {price_text}")
                    
                    # 查找Volume数据 - 使用新的XPath
                    volume_element = wait_for_element(driver, By.XPATH, "//fin-streamer[@data-field='regularMarketVolume']", timeout=5)
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
                        ''', (current_date, symbol, price, volume))
                        conn.commit()
                        
                        print(f"已保存 {symbol} 到 {sector} 表: 价格={price}, 成交量={volume}")
                        
                        # 如果是empty模式，则在成功保存后清除该symbol
                        if args.mode.lower() == 'empty':
                            clear_symbols_from_json(json_file_path, sector, symbol)
                    else:
                        print(f"抓取 {symbol} 失败，未能获取到完整数据")
                
                except Exception as e:
                    print(f"抓取 {symbol} 时发生错误: {str(e)}")
                
                # 添加短暂延迟，避免请求过于频繁
                time.sleep(random.uniform(1, 2))
    
    finally:
        # 关闭数据库连接
        conn.close()
        
        # 关闭浏览器
        driver.quit()
        
        # 显示成功提示
        show_alert(f"股票数据抓取完成并已写入数据库！")
        print("数据抓取和保存完成！")

if __name__ == "__main__":
    main()