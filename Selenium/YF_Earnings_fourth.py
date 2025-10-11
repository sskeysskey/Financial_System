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
file_path              = '/Users/yanzhang/Coding/News/Earnings_Release_fourth.txt'
backup_dir             = '/Users/yanzhang/Coding/News/backup/backup'
earnings_release_path  = '/Users/yanzhang/Coding/News/backup/Earnings_Release.txt'
# -------- 配置文件：记忆日期范围（共用 next/third/fourth 分组） ----------------
config_path = '/Users/yanzhang/Coding/Financial_System/Selenium/earnings_config.json'

def load_last_range_by_group(group_name: str):
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                data = json.load(f)
            grp = data.get(group_name, {})
            sd_s = grp.get('start_date')
            ed_s = grp.get('end_date')
            if sd_s and ed_s:
                sd = datetime.strptime(sd_s, '%Y-%m-%d').date()
                ed = datetime.strptime(ed_s, '%Y-%m-%d').date()
                return sd, ed
    except Exception as e:
        print(f"[{group_name}] 读取配置失败，将使用默认日期：{e}")
    today = datetime.now().date()
    return today, today + timedelta(days=6)

def save_last_range_by_group(group_name: str, sd: datetime.date, ed: datetime.date):
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        data = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                try:
                    data = json.load(f) or {}
                except Exception:
                    data = {}
        if group_name not in data:
            data[group_name] = {}
        data[group_name]['start_date'] = sd.strftime('%Y-%m-%d')
        data[group_name]['end_date']   = ed.strftime('%Y-%m-%d')
        with open(config_path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[{group_name}] 写入配置失败：{e}")

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

# —— 新增：算出“最近一个月内”在备份文件里出现过的 symbols ——
today = datetime.now().date()
recent_backup_symbols = set()
for s, d in existing_release_entries:
    try:
        dt = datetime.strptime(d, '%Y-%m-%d').date()
        if 0 <= (today - dt).days <= 30:
            recent_backup_symbols.add(s)
    except ValueError:
        # 如果日期格式有问题，就跳过
        continue

# （B）备份旧 fourth.txt（如果存在）
if os.path.exists(file_path):
    ts = datetime.now().strftime('%y%m%d')
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(file_path, os.path.join(backup_dir, f'Earnings_Release_fourth_{ts}.txt'))

# （C）把 fourth.txt 读入内存，构造 two data structures：
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
    group_name = "fourth"

    def on_ok():
        nonlocal start_dt, end_dt
        sd = start_cal.get_date()
        ed = end_cal.get_date()
        if sd > ed:
            messagebox.showwarning("日期错误", "开始日期不能晚于结束日期！")
            return
        start_dt = datetime(sd.year, sd.month, sd.day)
        end_dt   = datetime(ed.year, ed.month, ed.day)
        # 保存到配置（fourth 分组）
        save_last_range_by_group(group_name, sd, ed)
        root.destroy()

    def on_cancel(event=None):
        root.destroy()
        sys.exit()

    # 读取 fourth 分组上次日期范围
    last_sd, last_ed = load_last_range_by_group(group_name)

    root = tk.Tk()
    root.title("FOURTH - 选择爬取日期范围")
    
    w, h = 350, 210
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws//2) - (w//2)
    y = (hs//2) - (h//2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.resizable(False, False)

    root.lift()
    root.focus_force()
    root.bind("<Escape>", on_cancel)

    title_label = tk.Label(root, text="FOURTH", fg="red", font=("Helvetica", 36, "bold"))
    title_label.place(relx=0.5, y=35, anchor='center')

    tk.Label(root, text="开始日期：").place(x=20, y=80)
    start_cal = DateEntry(root, width=12, background='darkblue',
                          foreground='white', borderwidth=2,
                          year=last_sd.year, month=last_sd.month, day=last_sd.day)
    start_cal.place(x=100, y=80)

    tk.Label(root, text="结束日期：").place(x=20, y=120)
    end_cal = DateEntry(root, width=12, background='darkblue',
                        foreground='white', borderwidth=2,
                        year=last_ed.year, month=last_ed.month, day=last_ed.day)
    end_cal.place(x=100, y=120)

    btn_ok = tk.Button(root, text="确定", width=10, command=on_ok)
    btn_ok.place(x=60, y=160)
    btn_cancel = tk.Button(root, text="取消", width=10, command=on_cancel)
    btn_cancel.place(x=180, y=160)

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

with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json', 'r') as f:
    sectors_data = json.load(f)

conn   = sqlite3.connect('/Users/yanzhang/Coding/Database/Finance.db')
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

# -------- 5.1. 生成 next 与 diff 两份列表 -------------------------------
# （A）读取 new.txt 和 next.txt 中已有的 symbols
new_symbols = set()
files_to_read_symbols_from = [
    '/Users/yanzhang/Coding/News/Earnings_Release_new.txt',
    '/Users/yanzhang/Coding/News/Earnings_Release_next.txt',
    '/Users/yanzhang/Coding/News/Earnings_Release_third.txt',
    '/Users/yanzhang/Coding/News/Earnings_Release_fifth.txt'
]

def read_symbols_into_set(file_path, symbol_set):
    """一个辅助函数，用于从文件中读取 symbol 并添加到集合中"""
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            for line in f:
                parts = line.strip().split(':')
                if parts:
                    symbol_set.add(parts[0].strip())

# 遍历文件列表，将所有 symbols 读入 new_symbols 集合
for file in files_to_read_symbols_from:
    read_symbols_into_set(file, new_symbols)

# （B）读取已有的 diff 文件内容以便排重
diff_path = '/Users/yanzhang/Coding/News/Earnings_Release_diff_fourth.txt'
existing_diff_lines = set()
if os.path.exists(diff_path):
    with open(diff_path, 'r') as f_diff:
        for ln in f_diff:
            existing_diff_lines.add(ln.rstrip('\n'))

# -------- 5.1. 生成 next 与 diff 两份列表 -------------------------------
entries_for_next = []
entries_for_diff = []

for ln in new_entries:
    sym = ln.split(':')[0].strip()

    # A) 如果在 new.txt 或 next.txt 或 third.txt 里见过，一律归 diff（不写 next）
    if sym in new_symbols:
        if ln not in existing_diff_lines:
            entries_for_diff.append(ln)
            existing_diff_lines.add(ln)

    # B) 如果在 backup/Earnings_Release.txt 最近一个月内出现过，也归 diff，
    #    并在行尾加上特殊标识 “#BACKUP_DUP”
    elif sym in recent_backup_symbols:
        marked = f"{ln}  #BACKUP_DUP"
        if marked not in existing_diff_lines:
            entries_for_diff.append(marked)
            existing_diff_lines.add(marked)

    # C) 否则，才是真正要写进 next.txt 的新记录
    else:
        entries_for_next.append(ln)

# -------- 5.2. 写回 Earnings_Release_fourth.txt ------------------------------
if entries_for_next:
    with open(file_path, 'w') as f:
        # 先写保留的旧行
        for ln in existing_lines:
            f.write(ln + '\n')
        # 再写这次应该写回 next 的新行
        for ln in entries_for_next:
            f.write(ln + '\n')
    print(f"更新了 {len(entries_for_next)} 条记录到 {file_path}")
else:
    print("没有发现可写入 next.txt 的新记录。")

# -------- 5.3. 追加写入 Earnings_Release_diff_fourth.txt -------------------------
if entries_for_diff:
    # 确保目录存在
    os.makedirs(os.path.dirname(diff_path), exist_ok=True)
    with open(diff_path, 'a') as f:
        for ln in entries_for_diff:
            f.write(ln + '\n')
    print(f"将 {len(entries_for_diff)} 条记录追加到 diff 文件：{diff_path}")
else:
    print("没有发现需要写入 diff.txt 的记录。")

# -------- 6. 收尾 ----------
conn.close()
driver.quit()