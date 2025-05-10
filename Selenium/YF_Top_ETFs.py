import os
import json
import shutil
import random
import time
import glob
import pyautogui
import threading
import logging
import subprocess             # ← 新增

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ---------------------- AppleScript 提示框 ----------------------
def show_alert(message):
    """
    使用 AppleScript 弹出对话框
    """
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

# ---------------------- 日志配置 ----------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ---------------------- 鼠标防挂机线程 ----------------------
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

# ---------------------- Selenium 配置 ----------------------
chrome_options = Options()
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
chrome_options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

chrome_driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
service = Service(executable_path=chrome_driver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

# ---------------------- 工具函数 ----------------------
def convert_volume(volume_str):
    """转换交易量字符串为整数"""
    try:
        orig = volume_str
        volume_str = volume_str.replace(",", "")
        if 'M' in volume_str:
            val = int(float(volume_str.replace('M', '')) * 1_000_000)
        elif 'K' in volume_str:
            val = int(float(volume_str.replace('K', '')) * 1_000)
        elif 'B' in volume_str:
            val = int(float(volume_str.replace('B', '')) * 1_000_000_000)
        else:
            val = int(float(volume_str))
        logging.debug(f"convert_volume: '{orig}' -> {val}")
        return val
    except Exception as e:
        logging.error(f"转换交易量出错: '{volume_str}' - {e}")
        return 0

def load_blacklist(blacklist_file):
    """加载黑名单数据"""
    try:
        with open(blacklist_file, 'r') as f:
            data = json.load(f)
        bl = set(data.get('etf', []))
        logging.info(f"已加载黑名单，共 {len(bl)} 条")
        return bl
    except Exception as e:
        logging.error(f"加载黑名单文件出错: {e}")
        return set()

def is_blacklisted(symbol, blacklist):
    return symbol in blacklist

# ---------------------- 抓取逻辑 ----------------------
def fetch_data(url):
    logging.info(f"开始抓取: {url}")
    try:
        # 为 driver.get() 设置一个超时，例如15秒
        # 这个设置是持久的，除非再次修改。可以在每次get之前设置，或在初始化driver后全局设置一次。
        # 为确保每次都生效，可以在这里设置。
        driver.set_page_load_timeout(5)
        try:
            driver.get(url)
        except TimeoutException:
            logging.warning(f"页面加载超时 {url} (在5秒内)，但将继续尝试查找元素。")
            # 可选: 尝试停止页面进一步加载，以释放资源并可能加快后续操作
            # driver.execute_script("window.stop();") # 使用时需谨慎测试

        # 等待 tbody 下至少一行 tr 出现
        # 这里的等待时间可以根据实际情况调整，如果页面加载确实慢，可以适当增加
        WebDriverWait(driver, 10).until( # 显式等待10秒
            EC.presence_of_element_located((By.CSS_SELECTOR, "tbody tr"))
        )
        rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
        logging.info(f"在 {url} 找到 {len(rows)} 行数据")

        data_list = []
        for idx, row in enumerate(rows, start=1):
            try:
                symbol = row.find_element(By.CSS_SELECTOR, "span.symbol").text.strip()
                name = row.find_element(By.CSS_SELECTOR, "td:nth-child(2) div").get_attribute("title").strip()
                
                vol_el = row.find_element(
                    By.CSS_SELECTOR,
                    "fin-streamer[data-field*='regularMarketVolume'], fin-streamer[data-field*='regular MarketVolume']"
                )
                volume_str = vol_el.text.strip()
                volume = convert_volume(volume_str)

                logging.debug(f"Row {idx}: {symbol} | {name} | {volume_str} -> {volume}")
                if symbol and name and volume > 0: # 确保name也被正确获取
                    data_list.append((symbol, name, volume))
                else:
                    logging.warning(f"Row {idx} 数据不完整或 volume=0 (Symbol: {symbol}, Name: {name}, Volume: {volume})，跳过")
            except Exception as e:
                logging.error(f"处理第 {idx} 行时出错: {e}. Row HTML (sample): {row.get_attribute('outerHTML')[:200]}") # 打印部分行HTML帮助调试

        return data_list

    except TimeoutException: # 这个是显式等待 (WebDriverWait) 的超时
        logging.error(f"等待 tbody tr 超时于 {url}. 页面可能未正确加载或结构已更改。")
        return []
    except Exception as e:
        logging.error(f"获取数据时发生未知错误于 {url}: {e}")
        return []

def save_data(urls, existing_json, new_file, blacklist_file):
    logging.info("===== 开始保存数据 =====")
    blacklist = load_blacklist(blacklist_file)

    # 预热主页
    driver.get("https://finance.yahoo.com/markets/etfs/top/")
    time.sleep(1)

    with open(existing_json, 'r') as f:
        data = json.load(f)
    existing_symbols = {etf['symbol'] for etf in data.get('etfs', [])}
    logging.info(f"已存在的 ETF 数量: {len(existing_symbols)}")

    total_data_list = []
    filter_data_list = []

    for url in urls:
        fetched = fetch_data(url)
        logging.info(f"{url} 抓取到 {len(fetched)} 条记录")
        for symbol, name, volume in fetched:
            if is_blacklisted(symbol, blacklist):
                logging.info(f"Symbol {symbol} 在黑名单中，跳过")
                continue
            if volume <= 200_000:
                logging.debug(f"{symbol} volume={volume} <=200k，跳过")
                continue

            total_data_list.append((symbol, name, volume))
            if symbol not in existing_symbols:
                logging.info(f"发现新 ETF: {symbol} ({name}), volume={volume}")
                filter_data_list.append(f"{symbol}: {name}, {volume}")
                existing_symbols.add(symbol)

    if filter_data_list:
        with open(new_file, "w") as f:
            for i, line in enumerate(filter_data_list):
                suffix = "\n" if i < len(filter_data_list) - 1 else ""
                f.write(line + suffix)
        logging.info(f"已写入 {len(filter_data_list)} 条新 ETF 到：{new_file}")
    else:
        logging.info("没有新的 ETF 需要写入。")
        show_alert("没有发现新的 ETF")   # ← 在这里弹窗

# ---------------------- 主流程 ----------------------
urls = [
    "https://finance.yahoo.com/markets/etfs/top/?start=0&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=100&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=200&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=300&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=400&count=100",
    "https://finance.yahoo.com/markets/etfs/top/?start=500&count=100"
]

existing_json = '/Users/yanzhang/Documents/Financial_System/Modules/description.json'
new_file       = '/Users/yanzhang/Documents/News/ETFs_new.txt'
blacklist_file = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'

try:
    save_data(urls, existing_json, new_file, blacklist_file)
finally:
    driver.quit()
    logging.info("Selenium 已退出，抓取任务结束。")

# ---------------------- 文件移动 ----------------------
downloads_dir = "/Users/yanzhang/Downloads/"
source_pattern = os.path.join(downloads_dir, "screener_*.txt")
source_file2   = "/Users/yanzhang/Documents/News/screener_sectors.txt"
target_dir     = "/Users/yanzhang/Documents/News/backup"

# 确保目标目录存在
os.makedirs(target_dir, exist_ok=True)

# 一次性移动所有匹配 screener_*.txt 的文件
for src in glob.glob(source_pattern):
    dst = os.path.join(target_dir, os.path.basename(src))
    shutil.move(src, dst)
    logging.info(f"已移动: {src} -> {dst}")

# 单独移动第二个文件，先检查是否存在
if os.path.exists(source_file2):
    dst2 = os.path.join(target_dir, os.path.basename(source_file2))
    shutil.move(source_file2, dst2)
    logging.info(f"已移动: {source_file2} -> {dst2}")
else:
    logging.warning(f"文件不存在，跳过移动: {source_file2}")

logging.info(f"所有文件处理完毕，目录: {target_dir}")