import os
import json
import shutil
import random
import time
import glob
import pyautogui
import threading
import logging
import subprocess
import sqlite3
from datetime import datetime, timedelta

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
            logging.warning(f"鼠标移动出错: {e}")
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
        s = volume_str.replace(",", "")
        if 'M' in s:
            return int(float(s.replace('M','')) * 1_000_000)
        if 'K' in s:
            return int(float(s.replace('K','')) * 1_000)
        if 'B' in s:
            return int(float(s.replace('B','')) * 1_000_000_000)
        return int(float(s))
    except Exception as e:
        logging.error(f"convert_volume 错误: '{volume_str}' -> {e}")
        return 0

def load_blacklist(blacklist_file):
    """加载黑名单数据"""
    try:
        with open(blacklist_file) as f:
            data = json.load(f)
        bl = set(data.get('etf', []))
        logging.info(f"已加载黑名单 {len(bl)} 条")
        return bl
    except Exception as e:
        logging.error(f"加载黑名单失败: {e}")
        return set()

def is_blacklisted(symbol, bl):
    return symbol in bl

# ---------------------- 数据抓取 ----------------------
def fetch_data(url):
    logging.info(f"Fetching {url}")
    driver.set_page_load_timeout(5)
    try:
        driver.get(url)
    except TimeoutException:
        logging.warning("页面加载超时，继续查找元素…")
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tbody tr"))
        )
        rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
        logging.info(f"找到 {len(rows)} 行")
    except TimeoutException:
        logging.error("tbody tr 未出现，跳过此页")
        return []

    results = []
    for idx, row in enumerate(rows, start=1):
        try:
            symbol = row.find_element(By.CSS_SELECTOR, "span.symbol").text.strip()
            name = row.find_element(By.CSS_SELECTOR, "td:nth-child(2) div").get_attribute("title").strip()
            # price
            price_el = row.find_element(
                By.CSS_SELECTOR,
                "fin-streamer[data-field*='regularMarketPrice']"
            )
            price = float(price_el.get_attribute("value") or price_el.text)
            # volume
            vol_el = row.find_element(
                By.CSS_SELECTOR,
                "fin-streamer[data-field*='regularMarketVolume']"
            )
            volume = convert_volume(vol_el.text.strip())

            if symbol and name and volume > 0:
                results.append((symbol, name, price, volume))
            else:
                logging.info(f"跳过行 {idx}: 数据不完整 or volume=0")
        except Exception as e:
            logging.error(f"处理行 {idx} 出错: {e}")
    return results

# ---------------------- 保存与写库 ----------------------
def save_data(urls, existing_json, new_file, blacklist_file, sectors_file, db_path):
    logging.info("===== 开始保存 =====")
    bl = load_blacklist(blacklist_file)

    # 预热主页
    driver.get("https://finance.yahoo.com/markets/etfs/top/")
    time.sleep(1)

    # 加载已有描述，总用来筛除 new_file 文本
    with open(existing_json) as f:
        existing = json.load(f)
    existing_symbols = {etf['symbol'] for etf in existing.get('etfs', [])}
    logging.info(f"已有 ETF: {len(existing_symbols)}")

    # 加载 sectors
    with open(sectors_file) as f:
        sectors = json.load(f)
    etf_sectors = set(sectors.get("ETFs", []))
    logging.info(f"Sectors_All 中 ETF 分组共 {len(etf_sectors)} 条")

    # 数据库连接
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 取昨天日期
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    new_txt_lines = []

    for url in urls:
        data = fetch_data(url)
        logging.info(f"{url} 抓取 {len(data)} 条")
        for symbol, name, price, volume in data:
            # 黑名单
            if is_blacklisted(symbol, bl):
                continue
            # volume 过滤
            if volume <= 200_000:
                continue
            # sector 过滤：只处理属于 sectors["ETFs"] 的
            if symbol not in etf_sectors:
                continue

            # 文本新 ETF 列表（和原逻辑保持一致）
            if symbol not in existing_symbols:
                new_txt_lines.append(f"{symbol}: {name}, {volume}")
                existing_symbols.add(symbol)

            # 数据库去重插入
            cursor.execute(
                "SELECT 1 FROM ETFs WHERE name=? AND date=? LIMIT 1",
                (symbol, yesterday)
            )
            if cursor.fetchone():
                logging.info(f"{symbol} 已有 {yesterday} 数据，跳过写库")
            else:
                cursor.execute(
                    "INSERT INTO ETFs (date, name, price, volume) VALUES (?, ?, ?, ?)",
                    (yesterday, symbol, price, volume)
                )
                logging.info(f"写入 DB: {symbol} | {yesterday} | price={price} | vol={volume}")

    conn.commit()
    conn.close()

    # 将新发现写入文本
    if new_txt_lines:
        with open(new_file, "w") as f:
            f.write("\n".join(new_txt_lines))
        logging.info(f"写入 {len(new_txt_lines)} 条新 ETF 到 {new_file}")
    else:
        logging.info("无新 ETF，弹窗提示")
        show_alert("没有发现新的 ETF")

# ---------------------- 主流程 ----------------------
if __name__ == "__main__":
    urls = [
        "https://finance.yahoo.com/markets/etfs/top/?start=0&count=100",
        "https://finance.yahoo.com/markets/etfs/top/?start=100&count=100",
        "https://finance.yahoo.com/markets/etfs/top/?start=200&count=100",
        "https://finance.yahoo.com/markets/etfs/top/?start=300&count=100",
        "https://finance.yahoo.com/markets/etfs/top/?start=400&count=100",
        "https://finance.yahoo.com/markets/etfs/top/?start=500&count=100"
    ]
    existing_json    = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"
    new_file         = "/Users/yanzhang/Documents/News/ETFs_new.txt"
    blacklist_file   = "/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json"
    sectors_file     = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
    db_path          = "/Users/yanzhang/Documents/Database/Finance.db"

    try:
        save_data(urls, existing_json, new_file, blacklist_file, sectors_file, db_path)
    finally:
        driver.quit()
        logging.info("抓取完成，浏览器已退出。")

    # ---------------------- 文件移动 ----------------------
    downloads_dir = "/Users/yanzhang/Downloads/"
    source_pattern = os.path.join(downloads_dir, "screener_*.txt")
    source_file2   = "/Users/yanzhang/Documents/News/screener_sectors.txt"
    target_dir     = "/Users/yanzhang/Documents/News/backup"
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
        logging.warning(f"不存在，跳过: {source_file2}")

    logging.info("所有文件处理完毕。")