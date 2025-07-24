import os
import json
import sqlite3
import shutil
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import pyautogui
import random
import time
import threading

# ———— 1. 鼠标防 AFK 线程 —————————————————————
def move_mouse_periodically():
    while True:
        try:
            w, h = pyautogui.size()
            x = random.randint(100, w-100)
            y = random.randint(100, h-100)
            pyautogui.moveTo(x, y, duration=1)
            time.sleep(random.randint(30,60))
        except Exception as e:
            print(f"鼠标移动出错: {e}")
            time.sleep(30)

threading.Thread(target=move_mouse_periodically, daemon=True).start()

# ———— 2. 路径 & 备份 —————————————————————————
file_path           = '/Users/yanzhang/Documents/News/Earnings_Release_next.txt'
backup_dir          = '/Users/yanzhang/Documents/News/backup/backup'
earnings_release_path = '/Users/yanzhang/Documents/News/backup/Earnings_Release.txt'

# （A）加载主发行日文件中的 (symbol, date) 去重集
existing_release_entries = set()
if os.path.exists(earnings_release_path):
    with open(earnings_release_path, 'r') as f:
        for line in f:
            parts = line.strip().split(':')
            if len(parts) >= 2:
                s = parts[0].strip()
                d = parts[1].strip()
                existing_release_entries.add((s,d))

# （B）备份旧 next.txt（如果存在）
file_exists = os.path.exists(file_path)
if file_exists:
    ts = datetime.now().strftime('%y%m%d')
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(file_path, os.path.join(backup_dir, f'Earnings_Release_next_{ts}.txt'))

# （C）把 next.txt 读入内存，构造 two data structures：
#     1. existing_lines: 原始行列表
#     2. existing_next_map: symbol -> (call_time, date)
existing_lines    = []
existing_next_map = {}
if file_exists:
    with open(file_path, 'r') as f:
        for line in f:
            ln = line.rstrip('\n')
            existing_lines.append(ln)
            parts = ln.split(':')
            if len(parts) >= 3:
                sym       = parts[0].strip()
                call_time = parts[1].strip()
                date      = parts[2].strip()
                existing_next_map[sym] = (call_time, date)

# 准备一个列表收新条目
new_entries = []

# ———— 3. Selenium & DB 初始化 ——————————————————
chrome_options = Options()
for arg in ["--disable-extensions","--disable-gpu","--disable-dev-shm-usage",
            "--no-sandbox","--blink-settings=imagesEnabled=false"]:
    chrome_options.add_argument(arg)
chrome_options.page_load_strategy = 'eager'
service = Service(executable_path="/Users/yanzhang/Downloads/backup/chromedriver")
driver  = webdriver.Chrome(service=service, options=chrome_options)

with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as f:
    sectors_data = json.load(f)

conn   = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

start_date = datetime(2025, 7, 28)
end_date   = datetime(2025, 8, 2)
delta      = timedelta(days=1)

# ———— 4. 爬取主逻辑 —————————————————————————
for single_date in (start_date + i*delta for i in range((end_date-start_date).days+1)):
    ds = single_date.strftime('%Y-%m-%d')
    offset = 0
    while True:
        url = (
            f"https://finance.yahoo.com/calendar/earnings"
            f"?from={start_date:%Y-%m-%d}&to={end_date:%Y-%m-%d}"
            f"&day={ds}&offset={offset}&size=100"
        )
        driver.get(url)
        try:
            tbl = WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
            )
            rows = tbl.find_elements(By.CSS_SELECTOR, "tbody > tr")
        except TimeoutException:
            break

        if not rows:
            break

        for row in rows:
            try:
                symbol = row.find_element(
                    By.CSS_SELECTOR, 'a[title][href*="/quote/"]'
                ).get_attribute('title')
                cells = row.find_elements(By.TAG_NAME, 'td')
                if len(cells) < 4:
                    continue

                event_name = cells[2].text.strip()
                call_time  = cells[3].text.strip() or "N/A"

                if not any(k in event_name for k in 
                           ["Earnings Release",
                            "Shareholders Meeting",
                            "Earnings Announcement"]):
                    continue

                # —— 主发行日文件级别去重，不变 —— 
                if (symbol, ds) in existing_release_entries:
                    continue

                # —— 确保在我们的“行业符号”合集里 —— 
                found_in_sector = any(
                    symbol in lst for lst in sectors_data.values()
                )
                if not found_in_sector:
                    continue

                new_line = f"{symbol:<7}: {call_time:<4}: {ds}"

                if symbol in existing_next_map:
                    old_ct, old_dt = existing_next_map[symbol]
                    # 若完全相同，则跳过
                    if old_ct == call_time and old_dt == ds:
                        continue
                    # 否则：移除原行，追加新行
                    # 1) 从 existing_lines 中剔除所有该 symbol 的行
                    existing_lines = [
                        ln for ln in existing_lines
                        if not ln.split(':')[0].strip() == symbol
                    ]
                    # 2) 更新映射
                    existing_next_map[symbol] = (call_time, ds)
                    # 3) 把 new_line 加到待写列表
                    new_entries.append(new_line)

                else:
                    # 第一次见到此 symbol，直接追加
                    existing_next_map[symbol] = (call_time, ds)
                    new_entries.append(new_line)

            except Exception as e:
                print(f"处理行出错: {e}")
                continue

        offset += 100

# ———— 5. 把内存中的 existing_lines + new_entries 一起写回文件 —————————
if new_entries:
    with open(file_path, 'w') as f:
        # 先写保留的旧行
        for ln in existing_lines:
            f.write(ln + "\n")
        # 再写所有新行（按发现顺序）
        for ln in new_entries:
            f.write(ln + "\n")
    print(f"更新了 {len(new_entries)} 条记录到 {file_path}")
else:
    print("没有发现可更新的新记录。")

# ———— 6. 收尾 —————————————————————————————
conn.close()
driver.quit()