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
import tkinter as tk
from tkinter import messagebox
from tkcalendar import DateEntry

# ==============================================================================
# 1. 通用模块和函数 (所有任务共用)
# ==============================================================================

# -------- 鼠标防 AFK 线程 (全局唯一) --------------------------------
def move_mouse_periodically():
    """在后台周期性地移动鼠标以防止系统休眠或 AFK 检测。"""
    print("启动防 AFK 鼠标移动线程...")
    while True:
        try:
            w, h = pyautogui.size()
            x = random.randint(100, w - 100)
            y = random.randint(100, h - 100)
            pyautogui.moveTo(x, y, duration=1)
            time.sleep(random.randint(30, 60))
        except Exception as e:
            print(f"鼠标移动出错: {e}")
            time.sleep(30)

# -------- 配置文件读写：记忆日期范围 --------------------------------
config_path = '/Users/yanzhang/Coding/Financial_System/Selenium/earnings_config.json'

def load_last_range_by_group(group_name: str):
    """从配置文件中读取指定分组的日期范围，失败则返回默认值。"""
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
    """将日期范围写入配置文件的指定分组。"""
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
        data[group_name]['end_date'] = ed.strftime('%Y-%m-%d')
        with open(config_path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[{group_name}] 写入配置失败：{e}")

def advance_all_dates_by_one_week():
    """将配置文件中所有分组的日期向后顺延一周（7天）。"""
    try:
        if not os.path.exists(config_path):
            print("配置文件不存在，无法顺延日期。")
            return False
        
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        modified = False
        for group_name in data:
            if 'start_date' in data[group_name] and 'end_date' in data[group_name]:
                try:
                    old_start = datetime.strptime(data[group_name]['start_date'], '%Y-%m-%d').date()
                    old_end = datetime.strptime(data[group_name]['end_date'], '%Y-%m-%d').date()
                    
                    new_start = old_start + timedelta(days=7)
                    new_end = old_end + timedelta(days=7)
                    
                    data[group_name]['start_date'] = new_start.strftime('%Y-%m-%d')
                    data[group_name]['end_date'] = new_end.strftime('%Y-%m-%d')
                    
                    print(f"[{group_name}] 日期已顺延: {old_start} ~ {old_end} => {new_start} ~ {new_end}")
                    modified = True
                except Exception as e:
                    print(f"[{group_name}] 日期顺延失败：{e}")
        
        if modified:
            with open(config_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print("所有日期已成功顺延一周并保存到配置文件。")
            return True
        else:
            print("没有需要顺延的日期。")
            return False
            
    except Exception as e:
        print(f"顺延日期过程中发生错误：{e}")
        return False

# -------- 日期选择界面 (Tkinter) - 保留但不再使用 ------------------------------------
def pick_date_range(group_name: str):
    """弹出一个 Tkinter 窗口让用户选择日期范围，并与指定分组关联。"""
    
    def on_ok():
        nonlocal start_dt, end_dt
        sd = start_cal.get_date()
        ed = end_cal.get_date()
        if sd > ed:
            messagebox.showwarning("日期错误", "开始日期不能晚于结束日期！")
            return
        start_dt = datetime(sd.year, sd.month, sd.day)
        end_dt = datetime(ed.year, ed.month, ed.day)
        save_last_range_by_group(group_name, sd, ed)
        root.destroy()

    def on_cancel(event=None):
        nonlocal start_dt, end_dt
        start_dt, end_dt = None, None
        root.destroy()

    last_sd, last_ed = load_last_range_by_group(group_name)

    root = tk.Tk()
    title = f"{group_name.upper()} - 选择爬取日期范围"
    root.title(title)
    
    w, h = 350, 210
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws // 2) - (w // 2)
    y = (hs // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.resizable(False, False)

    root.lift()
    root.focus_force()
    root.bind("<Escape>", on_cancel)
    root.protocol("WM_DELETE_WINDOW", on_cancel)

    title_label = tk.Label(root, text=group_name.upper(), fg="red", font=("Helvetica", 36, "bold"))
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

    start_dt, end_dt = None, None
    root.mainloop()
    return start_dt, end_dt

# ==============================================================================
# 2. 核心抓取与处理函数
# ==============================================================================

def run_scraper_task(driver, sectors_data, task_config):
    """
    执行一次完整的抓取、处理和写入任务。
    
    :param driver: Selenium WebDriver 实例。
    :param sectors_data: 包含所有行业 symbol 的数据。
    :param task_config: 一个包含此任务所有特定配置的字典。
    """
    group_name = task_config["group_name"]
    file_path = task_config["file_path"]
    diff_path = task_config["diff_path"]
    backup_dir = task_config["backup_dir"]
    earnings_release_path = task_config["earnings_release_path"]
    
    print("\n" + "="*80)
    print(f"开始执行任务: {group_name.upper()}")
    print("="*80)

    # -------- 步骤 1: 直接从配置文件读取日期范围（已在主程序中完成顺延） --------
    last_sd, last_ed = load_last_range_by_group(group_name)
    start_date = datetime(last_sd.year, last_sd.month, last_sd.day)
    end_date = datetime(last_ed.year, last_ed.month, last_ed.day)

    print(f"已为任务 [{group_name.upper()}] 确定日期范围: {start_date.date()} 到 {end_date.date()}")

    # -------- 步骤 2: 数据准备和备份 --------------------------------
    # (A) 加载主发行日文件中的 (symbol, date) 去重集
    existing_release_entries = set()
    if os.path.exists(earnings_release_path):
        with open(earnings_release_path, 'r') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) >= 2:
                    existing_release_entries.add((parts[0].strip(), parts[1].strip()))

    # (B) 计算最近一个月内已发布的 symbols
    today = datetime.now().date()
    recent_backup_symbols = set()
    for s, d in existing_release_entries:
        try:
            dt = datetime.strptime(d, '%Y-%m-%d').date()
            if 0 <= (today - dt).days <= 30:
                recent_backup_symbols.add(s)
        except ValueError:
            continue

    # (C) 备份旧的目标文件
    if os.path.exists(file_path):
        ts = datetime.now().strftime('%y%m%d')
        os.makedirs(backup_dir, exist_ok=True)
        backup_filename = f'Earnings_Release_{group_name}_{ts}.txt'
        shutil.copy2(file_path, os.path.join(backup_dir, backup_filename))
        print(f"已备份旧文件到: {backup_filename}")

    # (D) 读取目标文件内容到内存
    existing_lines = []
    existing_map = {}
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            for line in f:
                ln = line.rstrip('\n')
                existing_lines.append(ln)
                parts = ln.split(':')
                if len(parts) >= 3:
                    existing_map[parts[0].strip()] = (parts[1].strip(), parts[2].strip())

    # -------- 步骤 3: 爬取主逻辑 ------------------------------------
    new_entries = []
    delta = timedelta(days=1)
    
    # 注意：雅虎财经的URL参数中 from 和 to 似乎没有实际作用于分页，day参数才是关键。
    # 为了简化和确保正确性，我们只使用 day 参数。
    for single_date in (start_date + i * delta for i in range((end_date - start_date).days + 1)):
        ds = single_date.strftime('%Y-%m-%d')
        offset = 0
        while True:
            url = f"https://finance.yahoo.com/calendar/earnings?day={ds}&offset={offset}&size=100"
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
                    symbol = row.find_element(By.CSS_SELECTOR, 'a[title][href*="/quote/"]').get_attribute('title')
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) < 4: continue

                    event_name = cells[2].text.strip()
                    call_time = cells[3].text.strip() or "N/A"

                    if not any(k in event_name for k in ["Earnings Release", "Shareholders Meeting", "Earnings Announcement"]):
                        continue
                    if (symbol, ds) in existing_release_entries:
                        continue
                    if not any(symbol in lst for lst in sectors_data.values()):
                        continue

                    new_line = f"{symbol:<7}: {call_time:<4}: {ds}"

                    if symbol in existing_map:
                        old_ct, old_dt = existing_map[symbol]
                        if old_ct == call_time and old_dt == ds: continue
                        
                        existing_lines = [ln for ln in existing_lines if ln.split(':')[0].strip() != symbol]
                        existing_map[symbol] = (call_time, ds)
                        new_entries.append(new_line)
                    else:
                        existing_map[symbol] = (call_time, ds)
                        new_entries.append(new_line)

                except Exception:
                    continue
            offset += 100
    print(f"在 {start_date.date()} 到 {end_date.date()} 范围内共发现 {len(new_entries)} 个潜在新条目。")

    # -------- 步骤 4: 分类与写入 ------------------------------------
    # (A) 加载用于去重的 symbol 集合
    symbols_to_avoid = set()
    def read_symbols_into_set(f_path, symbol_set):
        if os.path.exists(f_path):
            with open(f_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if parts: symbol_set.add(parts[0].strip())

    for f in task_config["duplicate_check_files"]:
        read_symbols_into_set(f, symbols_to_avoid)

    # (B) 读取已有的 diff 文件内容以便排重
    existing_diff_lines = set()
    if os.path.exists(diff_path):
        with open(diff_path, 'r') as f_diff:
            existing_diff_lines.update(ln.rstrip('\n') for ln in f_diff)

    # (C) 将新条目分类到 target 文件或 diff 文件
    entries_for_target = []
    entries_for_diff = []

    for ln in new_entries:
        sym = ln.split(':')[0].strip()
        if sym in symbols_to_avoid:
            if ln not in existing_diff_lines:
                entries_for_diff.append(ln)
                existing_diff_lines.add(ln)
        elif sym in recent_backup_symbols:
            marked = f"{ln}  #BACKUP_DUP"
            if marked not in existing_diff_lines:
                entries_for_diff.append(marked)
                existing_diff_lines.add(marked)
        else:
            entries_for_target.append(ln)

    # (D) 写入目标文件
    # 逻辑调整：总是以 'w' 模式写入，先写旧行再写新行
    all_lines_to_write = existing_lines + entries_for_target
    with open(file_path, 'w') as f:
        if all_lines_to_write:
            f.write('\n'.join(all_lines_to_write) + '\n')
    
    if entries_for_target:
        print(f"更新了 {len(entries_for_target)} 条记录到 {os.path.basename(file_path)}")
    else:
        print(f"没有发现可写入 {os.path.basename(file_path)} 的新记录。")


    # (E) 追加写入 diff 文件
    if entries_for_diff:
        os.makedirs(os.path.dirname(diff_path), exist_ok=True)
        with open(diff_path, 'a') as f:
            for ln in entries_for_diff: f.write(ln + '\n')
        print(f"将 {len(entries_for_diff)} 条记录追加到 diff 文件：{os.path.basename(diff_path)}")
    else:
        print(f"没有发现需要写入 diff 文件的记录。")
    
    print(f"任务 [{group_name.upper()}] 执行完毕。")


# ==============================================================================
# 3. 主执行逻辑
# ==============================================================================
if __name__ == "__main__":
    # -------- 启动唯一的防 AFK 线程 ------------------------------------
    threading.Thread(target=move_mouse_periodically, daemon=True).start()

    # -------- 检查是否需要自动顺延日期 ---------------------------------
    today_weekday = datetime.now().weekday()
    
    # 周日(6)和周一(0)自动顺延配置文件中的所有日期
    if today_weekday == 6 or today_weekday == 0:
        print(f"\n今天是{'周日' if today_weekday == 6 else '周一'}，自动将所有日期顺延一周...")
        advance_all_dates_by_one_week()
    else:
        print(f"\n今天是工作日(周二至周六)，使用配置文件中的现有日期...")

    # -------- 定义所有任务的配置 ---------------------------------------
    base_news_path = '/Users/yanzhang/Coding/News/'
    
    # 定义各个文件的路径
    new_file = os.path.join(base_news_path, 'Earnings_Release_new.txt')
    next_file = os.path.join(base_news_path, 'Earnings_Release_next.txt')
    third_file = os.path.join(base_news_path, 'Earnings_Release_third.txt')
    fourth_file = os.path.join(base_news_path, 'Earnings_Release_fourth.txt')
    fifth_file = os.path.join(base_news_path, 'Earnings_Release_fifth.txt')

    TASK_CONFIGS = [
        {
            "group_name": "next",
            "file_path": next_file,
            "diff_path": os.path.join(base_news_path, 'Earnings_Release_diff_next.txt'),
            "backup_dir": os.path.join(base_news_path, 'backup/backup'),
            "earnings_release_path": os.path.join(base_news_path, 'backup/Earnings_Release.txt'),
            "duplicate_check_files": [new_file]
        },
        {
            "group_name": "third",
            "file_path": third_file,
            "diff_path": os.path.join(base_news_path, 'Earnings_Release_diff_third.txt'),
            "backup_dir": os.path.join(base_news_path, 'backup/backup'),
            "earnings_release_path": os.path.join(base_news_path, 'backup/Earnings_Release.txt'),
            "duplicate_check_files": [new_file, next_file]
        },
        {
            "group_name": "fourth",
            "file_path": fourth_file,
            "diff_path": os.path.join(base_news_path, 'Earnings_Release_diff_fourth.txt'),
            "backup_dir": os.path.join(base_news_path, 'backup/backup'),
            "earnings_release_path": os.path.join(base_news_path, 'backup/Earnings_Release.txt'),
            "duplicate_check_files": [new_file, next_file, third_file]
        },
        {
            "group_name": "fifth",
            "file_path": fifth_file,
            "diff_path": os.path.join(base_news_path, 'Earnings_Release_diff_fifth.txt'),
            "backup_dir": os.path.join(base_news_path, 'backup/backup'),
            "earnings_release_path": os.path.join(base_news_path, 'backup/Earnings_Release.txt'),
            "duplicate_check_files": [new_file, next_file, third_file, fourth_file]
        }
    ]

    # -------- 全局初始化 Selenium 和其他资源 -----------------------------
    print("正在初始化 Selenium WebDriver...")
    driver = None
    conn = None
    try:
        chrome_options = Options()
        for arg in ["--disable-extensions", "--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox", "--blink-settings=imagesEnabled=false"]:
            chrome_options.add_argument(arg)
        chrome_options.page_load_strategy = 'eager'
        service = Service(executable_path="/Users/yanzhang/Downloads/backup/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json', 'r') as f:
            sectors_data = json.load(f)
        
        # 您的代码中初始化了数据库但未使用，这里保持该逻辑
        conn = sqlite3.connect('/Users/yanzhang/Coding/Database/Finance.db')
        
        # -------- 按顺序执行所有任务 -------------------------------------
        for config in TASK_CONFIGS:
            run_scraper_task(driver, sectors_data, config)
            
        print("\n所有任务已执行完毕。")

    except Exception as e:
        print(f"\n程序执行过程中发生严重错误: {e}")
    finally:
        # -------- 统一清理资源 -----------------------------------------
        if conn:
            conn.close()
            print("数据库连接已关闭。")
        if driver:
            driver.quit()
            print("WebDriver 已关闭。")
        
        final_root = tk.Tk()
        final_root.withdraw() 
        messagebox.showinfo("任务完成", "所有抓取任务已执行完毕！")
        final_root.destroy()