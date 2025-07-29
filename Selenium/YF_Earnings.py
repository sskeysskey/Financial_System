import os
import sys
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

# GUI 相关
import tkinter as tk
from tkinter import messagebox
from tkcalendar import DateEntry

# -------- 1. 鼠标防 AFK 线程 ------------------------------------------
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

# -------- 2. 路径 & 备份 --------------------------------------------------
file_path              = '/Users/yanzhang/Documents/News/Earnings_Release_next.txt'
backup_dir             = '/Users/yanzhang/Documents/News/backup/backup'
earnings_release_path  = '/Users/yanzhang/Documents/News/backup/Earnings_Release.txt'

# （A）加载主发行日文件中的 (symbol, date) 去重集
existing_release_entries = set()
if os.path.exists(earnings_release_path):
    with open(earnings_release_path, 'r') as f:
        for line in f:
            parts = line.strip().split(':')
            if len(parts) >= 2:
                s = parts[0].strip()
                d = parts[1].strip()
                existing_release_entries.add((s, d))

# （B）备份旧 next.txt（如果存在）
if os.path.exists(file_path):
    ts = datetime.now().strftime('%y%m%d')
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(file_path, os.path.join(backup_dir, f'Earnings_Release_next_{ts}.txt'))

# （C）把 next.txt 读入内存，构造 two data structures：
existing_lines    = []
existing_next_map = {}
if os.path.exists(file_path):
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

# -------- 3. 弹出日期选择界面 ----------------------------------------
def pick_date_range():
    def on_ok():
        nonlocal start_dt, end_dt
        sd = start_cal.get_date()
        ed = end_cal.get_date()
        if sd > ed:
            messagebox.showwarning("日期错误", "开始日期不能晚于结束日期！")
            return
        start_dt = datetime(sd.year, sd.month, sd.day)
        end_dt   = datetime(ed.year, ed.month, ed.day)
        root.destroy()

    def on_cancel(event=None):
        root.destroy()
        sys.exit()

    root = tk.Tk()
    root.title("选择爬取日期范围")
    # 固定大小并居中
    w, h = 350, 150
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws//2) - (w//2)
    y = (hs//2) - (h//2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.resizable(False, False)

    # 置顶
    root.lift()
    root.focus_force()

    # 绑定 ESC
    root.bind("<Escape>", on_cancel)

    tk.Label(root, text="开始日期：").place(x=20, y=20)
    start_cal = DateEntry(root, width=12, background='darkblue',
                          foreground='white', borderwidth=2, year=datetime.now().year)
    start_cal.place(x=100, y=20)

    tk.Label(root, text="结束日期：").place(x=20, y=60)
    end_cal = DateEntry(root, width=12, background='darkblue',
                        foreground='white', borderwidth=2, year=datetime.now().year)
    end_cal.place(x=100, y=60)

    btn_ok = tk.Button(root, text="确定", width=10, command=on_ok)
    btn_ok.place(x=60, y=100)
    btn_cancel = tk.Button(root, text="取消", width=10, command=on_cancel)
    btn_cancel.place(x=180, y=100)

    # 等待用户操作
    start_dt = None
    end_dt   = None
    root.mainloop()
    return start_dt, end_dt

start_date, end_date = pick_date_range()
delta = timedelta(days=1)

# -------- 4. Selenium & DB 初始化 ------------------------------------
chrome_options = Options()
for arg in [
    "--disable-extensions",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--blink-settings=imagesEnabled=false"
]:
    chrome_options.add_argument(arg)
chrome_options.page_load_strategy = 'eager'
service = Service(executable_path="/Users/yanzhang/Downloads/backup/chromedriver")
driver  = webdriver.Chrome(service=service, options=chrome_options)

with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as f:
    sectors_data = json.load(f)

conn   = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# -------- 5. 爬取主逻辑 --------------------------------------------------
for single_date in (start_date + i*delta for i in range((end_date - start_date).days + 1)):
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

                if not any(k in event_name for k in [
                    "Earnings Release",
                    "Shareholders Meeting",
                    "Earnings Announcement"
                ]):
                    continue

                # 去重主文件
                if (symbol, ds) in existing_release_entries:
                    continue

                if not any(symbol in lst for lst in sectors_data.values()):
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
                        if ln.split(':')[0].strip() != symbol
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