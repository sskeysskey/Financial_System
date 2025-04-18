from selenium import webdriver
from selenium.webdriver.common.by import By
import os
import json
import shutil
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import pyautogui
import random
import time
import glob
import threading

# 添加鼠标移动功能的函数x
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

# 在主程序开始前启动鼠标移动线程
mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
mouse_thread.start()

chrome_options = Options()
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

# ChromeDriver 路径
chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
# 设置 ChromeDriver
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

def convert_volume(volume_str):
    """转换交易量字符串为整数"""
    try:
        # 移除所有逗号
        volume_str = volume_str.replace(",", "")
        
        # 处理百万单位
        if 'M' in volume_str:
            return int(float(volume_str.replace('M', '')) * 1000000)
        # 处理千单位
        elif 'K' in volume_str:
            return int(float(volume_str.replace('K', '')) * 1000)
        # 处理十亿单位
        elif 'B' in volume_str:
            return int(float(volume_str.replace('B', '')) * 1000000000)
        # 处理普通数字
        else:
            return int(float(volume_str))
    except Exception as e:
        print(f"转换交易量出错: {volume_str} - {str(e)}")
        return 0

def fetch_data(url):
    try:
        # 等待页面加载
        driver.get(url)
        data_list = []
        
        # 找到所有的行
        rows = driver.find_elements(By.CSS_SELECTOR, "tbody.body tr.row")
        
        for row in rows:
            try:
                # 获取symbol
                symbol_element = row.find_element(By.CSS_SELECTOR, "span.symbol")
                symbol = symbol_element.text.strip()
                
                # 获取name
                name_element = row.find_element(By.CSS_SELECTOR, "div[title]")
                name = name_element.get_attribute("title").strip()
                
                # 获取volume并处理
                volume_element = row.find_element(By.CSS_SELECTOR, "fin-streamer[data-field='regularMarketVolume']")
                volume_str = volume_element.text.strip()
                volume = convert_volume(volume_str)
                
                # 添加到数据列表
                if symbol and name and volume > 0:
                    data_list.append((symbol, name, volume))
                    
            except Exception as e:
                print(f"处理行时出错: {str(e)}")
                continue
                
        return data_list
        
    except Exception as e:
        print(f"获取数据时出错: {str(e)}")
        return []

def save_data(urls, existing_json, new_file, blacklist_file):
    # 加载黑名单
    blacklist = load_blacklist(blacklist_file)

    # 首先访问Yahoo Finance主页
    driver.get("https://finance.yahoo.com/markets/etfs/top/")
    # 等待2秒
    time.sleep(2)

    # 读取已存在的 symbol
    with open(existing_json, 'r') as json_file:
        data = json.load(json_file)
        existing_symbols = {etf['symbol'] for etf in data['etfs']}
    
    # 收集新数据
    total_data_list = []
    filter_data_list = []
    for url in urls:
        data_list = fetch_data(url)
        for symbol, name, volume in data_list:
            # 检查是否在黑名单中
            if is_blacklisted(symbol, blacklist):
                continue  # 跳过黑名单中的symbol
                
            if volume > 200000:
                total_data_list.append((symbol, name, volume))
                if symbol not in existing_symbols:
                    filter_data_list.append(f"{symbol}: {name}, {volume}")
                    existing_symbols.add(symbol)

    # 如果有新的条目，写入 new_file，否则打印提示
    if filter_data_list:
        with open(new_file, "w") as file:
            for i, line in enumerate(filter_data_list):
                # 最后一行不加换行
                suffix = "\n" if i < len(filter_data_list) - 1 else ""
                file.write(line + suffix)
        print(f"已写入 {len(filter_data_list)} 条新ETF 到：{new_file}")
    else:
        print("没有新的 ETF 需要写入。")

def load_blacklist(blacklist_file):
    """加载黑名单数据"""
    try:
        with open(blacklist_file, 'r') as file:
            blacklist_data = json.load(file)
            return set(blacklist_data.get('etf', []))  # 只返回etf分组的数据
    except Exception as e:
        print(f"加载黑名单文件出错: {str(e)}")
        return set()

def is_blacklisted(symbol, blacklist):
    """检查symbol是否在黑名单中"""
    return symbol in blacklist

# URL列表
urls = [
    "https://finance.yahoo.com/markets/etfs/top/?start=0&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=100&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=200&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=300&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=400&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=500&count=100"
]

existing_json = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'
new_file = '/Users/yanzhang/Documents/News/ETFs_new.txt'
blacklist_file = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'

try:
    save_data(urls, existing_json, new_file, blacklist_file)
finally:
    driver.quit()
print("所有爬取任务完成。")

# 源目录和文件模式
downloads_dir = "/Users/yanzhang/Downloads/"
source_pattern = os.path.join(downloads_dir, "screener_*.txt")
source_file2 = "/Users/yanzhang/Documents/News/screener_sectors.txt"

# 目标目录
target_dir = "/Users/yanzhang/Documents/News/backup"

# 确保目标目录存在
os.makedirs(target_dir, exist_ok=True)

# 一次性移动所有匹配 screener_*.txt 的文件
for src in glob.glob(source_pattern):
    dst = os.path.join(target_dir, os.path.basename(src))
    shutil.move(src, dst)
    print(f"已移动: {src} -> {dst}")

# 单独移动第二个文件，先检查是否存在
if os.path.exists(source_file2):
    dst2 = os.path.join(target_dir, os.path.basename(source_file2))
    shutil.move(source_file2, dst2)
    print(f"已移动: {source_file2} -> {dst2}")
else:
    print(f"警告: 文件不存在，跳过移动: {source_file2}")

print(f"所有文件处理完毕，目录: {target_dir}")