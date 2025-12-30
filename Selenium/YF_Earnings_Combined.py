import os
import re
import shutil
import json
import time
import random
# import threading
import subprocess
import tkinter as tk
from datetime import datetime, timedelta

# 第三方模块
import pyautogui
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# ==============================================================================
# 通用工具函数 (两个脚本公用的部分)
# ==============================================================================

def show_alert_mac(message):
    """Mac 系统弹窗提示 (合并了原有的 show_alert)"""
    try:
        # AppleScript代码模板
        applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
        # 使用subprocess调用osascript
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    except Exception as e:
        print(f"弹窗提示失败: {e}")

# ==============================================================================
# PART A: 原 a.py 的逻辑
# ==============================================================================

class PartA_FileProcessor:
    def __init__(self):
        self.LOCK_FILE = os.path.join(os.path.dirname(__file__), '.last_run_date')
        
        # 文件路径配置
        self.files = {
            'Earnings_Release': '/Users/yanzhang/Coding/News/backup/Earnings_Release.txt',
            'Economic_Events': '/Users/yanzhang/Coding/News/backup/Economic_Events.txt'
        }
        self.new_files = {
            'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_new.txt',
            'Economic_Events': '/Users/yanzhang/Coding/News/Economic_Events_new.txt'
        }
        self.next_files = {
            'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_next.txt',
            'Economic_Events': '/Users/yanzhang/Coding/News/Economic_Events_next.txt'
        }
        self.third_files = {
            'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_third.txt',
        }
        self.fourth_files = {
            'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_fourth.txt',
        }
        self.fifth_files = {
            'Earnings_Release': '/Users/yanzhang/Coding/News/Earnings_Release_fifth.txt',
        }

    def check_run_conditions(self):
        """
        检查脚本是否可以运行。
        返回 True 表示可以继续运行，False 表示应中止 Part A。
        """
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        # 计算昨天的日期字符串
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_str = yesterday.strftime('%Y-%m-%d')
        
        if os.path.exists(self.LOCK_FILE):
            with open(self.LOCK_FILE, 'r') as lf:
                last_run_date = lf.read().strip()
            
            # 检查是否今天已执行
            if last_run_date == today_str:
                print(f"[Part A] 脚本今天 ({today_str}) 已执行过，跳过 Part A。")
                return False
                
            # 检查是否昨天已执行
            if last_run_date == yesterday_str:
                print(f"[Part A] 脚本昨天 ({yesterday_str}) 已执行过，今天不能执行，跳过 Part A。")
                return False
                
        # 如果检查通过，更新锁文件为今天
        with open(self.LOCK_FILE, 'w') as lf:
            lf.write(today_str)
        print(f"[Part A] 执行条件检查通过，最后运行日期已更新为 {today_str}。")
        return True

    def format_line(self, line):
        parts = re.split(r'\s*:\s*', line.strip(), 2)
        if len(parts) == 3:
            symbol, _, rest = parts
            return f"{symbol:<7}: {rest}"
        elif len(parts) == 2:
            symbol, rest = parts
            return f"{symbol:<7}: {rest}"
        else:
            return line.strip()

    def process_earnings(self, new_file, backup_file):
        if not os.path.exists(new_file):
            return
        with open(new_file, 'r') as fin, open(backup_file, 'a') as fout:
            fout.write('\n')
            lines = [L.rstrip('\n') for L in fin]
            for idx, line in enumerate(lines):
                parts = [p.strip() for p in line.split(':')]
                if len(parts) == 3:
                    symbol, _, date = parts
                    out = f"{symbol:<7}: {date}"
                elif len(parts) == 2:
                    symbol, date = parts
                    out = f"{symbol:<7}: {date}"
                else:
                    out = line.strip()
                # 最后一行不加换行
                if idx < len(lines) - 1:
                    fout.write(out + "\n")
                else:
                    fout.write(out)
        os.remove(new_file)

    def process_file(self, new_file, existing_file):
        if os.path.exists(new_file):
            with open(new_file, 'r') as file_a, open(existing_file, 'a') as file_b:
                file_b.write('\n')  # 在迁移内容前首先输入一个回车
                lines = file_a.readlines()
                for i, line in enumerate(lines):
                    if 'Earnings_Release' in new_file:
                        # 使用正则表达式去除 " : 数字" 部分
                        processed_line = re.sub(r'\s*:\s*\d+\s*', '', line, count=1)
                        formatted_line = self.format_line(processed_line)
                        if i == len(lines) - 1:  # 如果是最后一行
                            file_b.write(formatted_line.rstrip())  # 移除行尾的空白字符，但不添加新行
                        else:
                            file_b.write(formatted_line + '\n')
                    else:
                        if i == len(lines) - 1:  # 如果是最后一行
                            file_b.write(line.rstrip())  # 移除行尾的空白字符，但不添加新行
                        else:
                            file_b.write(line)
            os.remove(new_file)

    def process_and_rename_files(self):
        # 检查 Earnings_Release 的 new 和 next 文件是否存在
        earnings_files_exist = all(os.path.exists(f) for f in [
            self.new_files['Earnings_Release'],
            self.next_files['Earnings_Release']
        ])
        
        events_files_exist = all(os.path.exists(f) for f in [
            self.new_files['Economic_Events'],
            self.next_files['Economic_Events']
        ])

        if earnings_files_exist:
            # 1. 处理 Earnings_Release 的 new 文件，并将其内容追加到主文件中
            print(f"处理文件: {self.new_files['Earnings_Release']}")
            self.process_earnings(self.new_files['Earnings_Release'], self.files['Earnings_Release'])
            
            # 2. 重命名 Earnings_Release 的 next 文件为 new 文件
            print(f"重命名: {self.next_files['Earnings_Release']} -> {self.new_files['Earnings_Release']}")
            os.rename(self.next_files['Earnings_Release'], self.new_files['Earnings_Release'])
            
            # 3. 检查 third 文件是否存在，如果存在则将其重命名为 next 文件
            third_earnings_file = self.third_files.get('Earnings_Release')
            if third_earnings_file and os.path.exists(third_earnings_file):
                print(f"重命名: {third_earnings_file} -> {self.next_files['Earnings_Release']}")
                os.rename(third_earnings_file, self.next_files['Earnings_Release'])
            else:
                print(f"未找到 {third_earnings_file}，跳过 third -> next 的重命名步骤。")
                
            # 4. 检查 fourth 文件是否存在，如果存在则将其重命名为 third 文件
            fourth_earnings_file = self.fourth_files.get('Earnings_Release')
            third_earnings_file_target = self.third_files.get('Earnings_Release')
            
            if fourth_earnings_file and os.path.exists(fourth_earnings_file):
                if third_earnings_file_target:
                    print(f"重命名: {fourth_earnings_file} -> {third_earnings_file_target}")
                    os.rename(fourth_earnings_file, third_earnings_file_target)
                else:
                    print(f"错误：找到了 {fourth_earnings_file} 但未在 third_files 中为其配置目标路径。")
            else:
                print(f"未找到 {fourth_earnings_file}，跳过 fourth -> third 的重命名步骤。")

            # 5. 检查 fifth 文件是否存在，如果存在则将其重命名为 fourth 文件
            fifth_earnings_file = self.fifth_files.get('Earnings_Release')
            fourth_earnings_file_target = self.fourth_files.get('Earnings_Release')
            
            if fifth_earnings_file and os.path.exists(fifth_earnings_file):
                if fourth_earnings_file_target:
                    print(f"重命名: {fifth_earnings_file} -> {fourth_earnings_file_target}")
                    os.rename(fifth_earnings_file, fourth_earnings_file_target)
                else:
                    print(f"错误：找到了 {fifth_earnings_file} 但未在 fourth_files 中为其配置目标路径。")
            else:
                print(f"未找到 {fifth_earnings_file}，跳过 fifth -> fourth 的重命名步骤。")
        else:
            print("Earnings_Release 相关文件（new/next）缺失，未执行任何操作。")

        if events_files_exist:    
            # 如果 Economic_Events 的 new 文件存在，则处理它
            if os.path.exists(self.new_files['Economic_Events']):
                print(f"处理文件: {self.new_files['Economic_Events']}")
                self.process_file(self.new_files['Economic_Events'], self.files['Economic_Events'])
                
            # 如果 Economic_Events 的 next 文件存在，则重命名它
            if os.path.exists(self.next_files['Economic_Events']):
                print(f"重命名: {self.next_files['Economic_Events']} -> {self.new_files['Economic_Events']}")
                os.rename(self.next_files['Economic_Events'], self.new_files['Economic_Events'])
        else:
            print("Economic_Events 相关文件（new/next）缺失，未执行任何操作。")

    def run(self):
        print("\n" + "="*50)
        print(">>> 正在启动 Part A (文件重命名/迁移任务)")
        print("="*50)
        # 获取当前星期几，0是周一，6是周日
        current_day = datetime.now().weekday()
        
        # 周日或周一允许运行
        if current_day in (6, 0):
            print("日期校验通过 (周日/周一)，开始执行 Part A 逻辑...")
            if self.check_run_conditions():
                self.process_and_rename_files()
        else:
            print("Not right date. Part A 只在周一（或周日）运行。")
        print("Part A 执行结束。\n")


# ==============================================================================
# PART B: 原 b.py 的逻辑
# ==============================================================================

# 全局配置 (修改点 1: 指向 Beta 版驱动)
CHROME_DRIVER_PATH = "/Users/yanzhang/Downloads/backup/chromedriver_beta"
EARNINGS_CONFIG_PATH = '/Users/yanzhang/Coding/Financial_System/Selenium/earnings_config.json'

def create_unified_driver():
    """
    统一的 Selenium Driver 工厂函数 (已修改为使用 Chrome Beta)。
    包含：Headless New 模式、反爬虫伪装、性能优化配置。
    """
    options = Options()
    
    # --- 修改点 2: 指定 Chrome Beta 的程序位置 ---
    options.binary_location = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"
    
    # --- 1. Headless 与 窗口设置 ---
    options.add_argument('--headless=new') 
    options.add_argument('--window-size=1920,1080')
    
    # --- 2. 伪装设置 (反爬虫) ---
    # 建议顺便把 User-Agent 版本号也稍微改高一点，匹配 Beta 版
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    options.add_argument(f'user-agent={user_agent}')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # --- 3. 性能优化 ---
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    # 禁止加载图片以加快速度
    options.add_argument("--blink-settings=imagesEnabled=false") 
    options.page_load_strategy = 'eager'

    try:
        if not os.path.exists(CHROME_DRIVER_PATH):
            raise FileNotFoundError(f"未找到驱动文件: {CHROME_DRIVER_PATH}")
            
        service = Service(executable_path=CHROME_DRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        
        # --- 4. CDP 命令：彻底屏蔽 navigator.webdriver ---
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
            })
            """
        })
        
        return driver
    except Exception as e:
        tqdm.write(f"创建 Driver (Beta) 失败: {e}")
        return None

def move_mouse_periodically():
    """后台周期性移动鼠标，防止系统休眠。"""
    while True:
        try:
            screen_width, screen_height = pyautogui.size()
            # 随机生成目标位置，避免移动到屏幕边缘
            x = random.randint(100, screen_width - 100)
            y = random.randint(100, screen_height - 100)
            pyautogui.moveTo(x, y, duration=1)
            # 等待30-60秒再次移动
            time.sleep(random.randint(30, 60))
        except Exception:
            # 静默处理异常，以免打断主线程日志
            time.sleep(30)

# --- B.1: Economic Events Task ---

def update_sectors_panel():
    """更新 sectors_panel 的主要逻辑"""
    path_new = '/Users/yanzhang/Coding/News/Economic_Events_new.txt'
    path_next = '/Users/yanzhang/Coding/News/Economic_Events_next.txt'
    sectors_panel_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'
    symbol_mapping_path = '/Users/yanzhang/Coding/Financial_System/Modules/Symbol_mapping.json'

    # 按顺序收集存在的事件文件
    event_files = []
    if os.path.exists(path_new):
        event_files.append(('new', path_new))
    if os.path.exists(path_next):
        event_files.append(('next', path_next))

    if not event_files:
        tqdm.write("未找到 Economic_Events 文件，未执行更新。")
        show_alert_mac("未找到 Economic_Events 文件，未执行更新。")
        return

    try:
        # 读取 symbol_mapping 和 原 sectors_panel
        with open(symbol_mapping_path, 'r', encoding='utf-8') as f:
            symbol_mapping = json.load(f)
        
        with open(sectors_panel_path, 'r', encoding='utf-8') as f:
            sectors_panel = json.load(f)

        # 清空 Economics 分组
        sectors_panel['Economics'] = {}

        # 依次处理 new、next
        for tag, filepath in event_files:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    event = line.strip()
                    if ' : ' not in event:
                        tqdm.write(f"Warning: 跳过格式不对的行：{event}")
                        continue
                    
                    # 拆分 "YYYY-MM-DD : 描述 [区域]" -> day_field, description
                    date_part, desc_part = event.split(' : ', 1)
                    day_field = date_part.split('-')[-1].strip()
                    description = desc_part.split(' [')[0].strip()

                    if description not in symbol_mapping:
                        continue # 如果描述不在映射表中，跳过

                    economics_key = symbol_mapping[description]
                    combined_value = f"{day_field} {economics_key}"
                    
                    existing = sectors_panel['Economics'].get(economics_key)
                    
                    if existing is None:
                        # 之前未写入过，直接写
                        sectors_panel['Economics'][economics_key] = combined_value
                    else:
                        if existing == combined_value:
                            continue # 完全重复，跳过
                        else:
                            if tag == 'next':
                                # 如果是 next 文件，优先覆盖 new 的值
                                sectors_panel['Economics'][economics_key] = combined_value
        
        # 写回 sectors_panel.json
        with open(sectors_panel_path, 'w', encoding='utf-8') as f:
            json.dump(sectors_panel, f, ensure_ascii=False, indent=4)
        
        tqdm.write("Economic Events JSON 更新已完成！")

    except Exception as e:
        error_message = f"更新 Economic Events JSON 错误: {e}"
        tqdm.write(error_message)
        show_alert_mac(error_message)

def run_economic_events_task():
    tqdm.write("\n" + "="*50)
    tqdm.write(">>> 开始执行任务: Economic Events")
    tqdm.write("="*50)
    
    # ==== 1) 星期判断，设置 do_crawl / do_update ====
    today_weekday = datetime.now().weekday()
    do_crawl = False
    do_update = False
    
    if today_weekday in (4, 5): # 周五(4)、周六(5)
        do_crawl, do_update = True, True
    elif today_weekday in (0, 6): # 周一(0)、周日(6)
        do_crawl, do_update = False, True
    else: 
        tqdm.write("今天不是周五/周六/周一/周日，跳过 Economic Events 任务。")
        return 

    # ==== 2) 如果需要爬虫，启动 Selenium 爬虫 + 写文件 ====
    if do_crawl:
        # 文件路径
        file_path = '/Users/yanzhang/Coding/News/Economic_Events_next.txt'
        backup_dir = '/Users/yanzhang/Coding/News/backup/backup'
        
        # 检查原始文件是否存在并备份
        if os.path.exists(file_path):
            timestamp = datetime.now().strftime('%y%m%d')
            backup_filename = f'Economic_Events_next_{timestamp}.txt'
            backup_path = os.path.join(backup_dir, backup_filename)
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(file_path, backup_path)
            
            with open(file_path, 'r') as file:
                existing_content = set(file.read().splitlines())
        else:
            existing_content = set()

        # === 使用统一的 Driver 工厂 ===
        tqdm.write("正在启动浏览器 (Economic Events)...")
        driver = create_unified_driver()
        
        if driver:
            try:
                current_date = datetime.now()
                start_date = current_date + timedelta(days=(6 - current_date.weekday()))
                end_date = start_date + timedelta(days=6)
                
                # 事件过滤器
                Event_Filter_Bases = {
                    "GDP 2nd Estimate", "GDP Advance", "GDP Final", "GDP Cons Spending Prelim",
                    "GDP Cons Spending Final", "Non-Farm Payrolls", "ISM N-Mfg PMI", "ISM Manufacturing PMI",
                    "ADP National Employment", "Unemployment Rate", "International Trade", "Import Prices MM",
                    "Import Prices YY", "CPI MM, SA", "CPI YY, NSA", "Core CPI MM, SA", "Core CPI YY, NSA",
                    "Fed Funds Tgt Rate", "PPI Final Demand YY", "PPI exFood/Energy MM", "PPI exFood/Energy YY",
                    "PPI ex Food/Energy/Tr MM", "PPI Final Demand MM", "PCE Prices Final", "PCE Price Index MM",
                    "PCE Price Index YY", "Core PCE Prices Final", "Core PCE Prices Prelim", "Core PCE Price Index MM",
                    "Core PCE Price Index YY", "U Mich Sentiment Prelim", "Retail Sales MM", "Initial Jobless Clm",
                    "U Mich Sentiment Final", "New Home Sales Chg MM", "New Home Sales-Units",
                }
                target_countries = {"US"}
                days_count = (end_date - start_date).days + 1
                date_list = [start_date + timedelta(days=i) for i in range(days_count)]

                with open(file_path, 'a') as output_file:
                    pbar = tqdm(date_list, desc="Eco Events", unit="day")
                    
                    for change_date in pbar:
                        formatted_change_date = change_date.strftime('%Y-%m-%d')
                        pbar.set_description(f"正在抓取: {formatted_change_date}")
                        
                        offset = 0
                        has_data = True
                        
                        while has_data:
                            pbar.set_postfix(offset=offset)
                            url = f"https://finance.yahoo.com/calendar/economic?from={start_date.strftime('%Y-%m-%d')}&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100"
                            driver.get(url)
                            wait = WebDriverWait(driver, 4)
                            try:
                                table_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.table-container")))
                                rows = table_container.find_elements(By.TAG_NAME, "tr")
                            except TimeoutException:
                                rows = []
                            
                            if not rows:
                                has_data = False
                            else:
                                for row in rows:
                                    if row.get_attribute("role") == "columnheader": continue
                                    cells = row.find_elements(By.TAG_NAME, "td")
                                    if len(cells) < 2: continue
                                    try:
                                        event = cells[0].text.strip()
                                        country = cells[1].text.strip()
                                        
                                        if event and country and country in target_countries:
                                            matched_base_event = None
                                            for base_event in Event_Filter_Bases:
                                                if event.startswith(base_event):
                                                    matched_base_event = base_event
                                                    break
                                            
                                            if matched_base_event:
                                                entry = f"{formatted_change_date} : {matched_base_event} [{country}]"
                                                if entry not in existing_content:
                                                    output_file.write(entry + "\n")
                                                    existing_content.add(entry)
                                    except Exception:
                                        continue
                                offset += 100
            except Exception as e:
                tqdm.write(f"Economic Events 爬虫出错: {e}")
            finally:
                driver.quit()
                tqdm.write("Economic Events 浏览器已关闭。")
        else:
            tqdm.write("无法启动浏览器，跳过爬取。")
    else:
        tqdm.write("今天是周一或周日，跳过 Economic Events 爬虫部分。")

    if do_update:
        update_sectors_panel()
    else:
        tqdm.write("今天不更新 Economic Events JSON。")

# --- B.2: Stock Splits Task ---

def run_stock_splits_task():
    tqdm.write("\n" + "="*50)
    tqdm.write(">>> 开始执行任务: Stock Splits")
    tqdm.write("="*50)
    
    # 判断今天是否为周五（4）或周六（5），否则跳过
    today_weekday = datetime.now().weekday()
    if today_weekday not in (4, 5):
        tqdm.write(f"今天不是周五或周六，跳过 Stock Splits 任务。")
        return

    # 文件路径
    file_path = '/Users/yanzhang/Coding/News/Stock_Splits_next.txt'
    backup_dir = '/Users/yanzhang/Coding/News/backup/backup'
    sectors_json_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'

    # 检查文件是否已经存在并备份
    if os.path.exists(file_path):
        timestamp = datetime.now().strftime('%y%m%d')
        backup_filename = f'Stock_Splits_next_{timestamp}.txt'
        backup_path = os.path.join(backup_dir, backup_filename)
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(file_path, backup_path)
        tqdm.write(f"已备份原文件至: {backup_path}")

    # 读取原有内容
    existing_content = set()
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            existing_content = set(file.read().splitlines())

    # === 使用统一的 Driver 工厂 ===
    tqdm.write("正在启动浏览器 (Stock Splits)...")
    driver = create_unified_driver()
    
    if driver:
        try:
            with open(sectors_json_path, 'r') as file:
                data = json.load(file)
            
            current_date = datetime.now()
            start_date = current_date + timedelta(days=(6 - current_date.weekday())) 
            end_date = start_date + timedelta(days=6)
            
            tqdm.write(f"抓取日期范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
            
            results = []
            days_count = (end_date - start_date).days + 1
            date_list = [start_date + timedelta(days=i) for i in range(days_count)]
            
            pbar = tqdm(date_list, desc="Stock Splits", unit="day")
            
            for change_date in pbar:
                formatted_change_date = change_date.strftime('%Y-%m-%d')
                pbar.set_description(f"正在处理: {formatted_change_date}")
                
                offset = 0
                has_data = True
                
                while has_data:
                    pbar.set_postfix(offset=offset, found=len(results))
                    url = f"https://finance.yahoo.com/calendar/splits?from={start_date.strftime('%Y-%m-%d')}&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100"
                    driver.get(url)
                    try:
                        rows = WebDriverWait(driver, 4).until(EC.presence_of_all_elements_located((By.XPATH, "//table//tbody/tr")))
                    except TimeoutException:
                        has_data = False
                        continue
                    
                    if not rows:
                        has_data = False
                        continue
                        
                    for row in rows:
                        try:
                            symbol = row.find_element(By.CSS_SELECTOR, 'a.loud-link.fin-size-small').text
                            company = row.find_element(By.CSS_SELECTOR, 'td.tw-text-left.tw-max-w-xs.tw-whitespace-normal').text
                        except Exception:
                            continue
                            
                        for category, symbols in data.items():
                            if symbol in symbols:
                                entry = f"{symbol}: {formatted_change_date} - {company}"
                                if entry not in existing_content:
                                    results.append(entry)
                                    tqdm.write(f"   [+] 发现新数据: {entry}")
                                break
                    
                    if len(rows) < 100:
                        has_data = False
                    else:
                        offset += 100

            if results:
                with open(file_path, 'a') as output_file:
                    if os.path.getsize(file_path) > 0:
                        output_file.write('\n')
                    for result in results:
                        output_file.write(result + "\n")
                tqdm.write(f"成功写入 {len(results)} 条新数据。")
                
                # 清理空行
                if os.path.exists(file_path):
                    with open(file_path, 'r') as file:
                        lines = file.readlines()
                    lines = [line for line in lines if line.strip() or any(lines[i].strip() for i in range(len(lines)) if i != lines.index(line))]
                    with open(file_path, 'w') as file:
                        file.writelines(lines)
            else:
                tqdm.write("没有新内容添加，文件保持不变。")

        except Exception as e:
            tqdm.write(f"Stock Splits 任务执行出错: {e}")
        finally:
            driver.quit()
            tqdm.write("Stock Splits 浏览器已关闭。")
    else:
        tqdm.write("无法启动浏览器，跳过 Stock Splits。")

# --- B.3: Earnings Release Task ---

def load_last_range_by_group(group_name: str):
    """从配置文件中读取指定分组的日期范围，失败则返回默认值。"""
    try:
        if os.path.exists(EARNINGS_CONFIG_PATH):
            with open(EARNINGS_CONFIG_PATH, 'r') as f:
                data = json.load(f)
            grp = data.get(group_name, {})
            sd_s = grp.get('start_date')
            ed_s = grp.get('end_date')
            if sd_s and ed_s:
                sd = datetime.strptime(sd_s, '%Y-%m-%d').date()
                ed = datetime.strptime(ed_s, '%Y-%m-%d').date()
                return sd, ed
    except Exception as e:
        tqdm.write(f"[{group_name}] 读取配置失败，将使用默认日期：{e}")
    
    today = datetime.now().date()
    return today, today + timedelta(days=6)

def check_and_advance_dates_if_needed():
    """
    检查是否需要顺延日期。
    规则：只在周日或周一，且本周尚未顺延过的情况下才执行顺延。
    返回：True 表示执行了顺延，False 表示未执行
    """
    today = datetime.now().date()
    today_weekday = today.weekday() # 0=周一, 6=周日
    
    # 只在周日(6)或周一(0)时才可能顺延
    if today_weekday not in [6, 0]:
        tqdm.write(f"今天是工作日，保持现有日期配置...")
        return False

    try:
        if not os.path.exists(EARNINGS_CONFIG_PATH):
            return False

        with open(EARNINGS_CONFIG_PATH, 'r') as f:
            data = json.load(f)
        
        # 检查上次顺延日期
        last_advance_str = data.get('_last_advance_date')
        
        if last_advance_str:
            last_advance_date = datetime.strptime(last_advance_str, '%Y-%m-%d').date()
            # 如果距离上次更新不足 5 天，说明本轮（周日/周一）已经处理过了
            if (today - last_advance_date).days < 5:
                tqdm.write(f"本轮日期顺延已在 {last_advance_str} 执行过，跳过。")
                return False
        
        tqdm.write(f"检测到新周期 ({'周日' if today_weekday == 6 else '周一'})，开始执行日期顺延...")
        
        modified = False
        for group_name in data:
            # 跳过特殊键
            if group_name.startswith('_'):
                continue
            
            if 'start_date' in data[group_name] and 'end_date' in data[group_name]:
                try:
                    old_start = datetime.strptime(data[group_name]['start_date'], '%Y-%m-%d').date()
                    old_end = datetime.strptime(data[group_name]['end_date'], '%Y-%m-%d').date()
                    
                    # 执行顺延
                    new_start = old_start + timedelta(days=7)
                    new_end = old_end + timedelta(days=7)
                    
                    data[group_name]['start_date'] = new_start.strftime('%Y-%m-%d')
                    data[group_name]['end_date'] = new_end.strftime('%Y-%m-%d')
                    modified = True
                except Exception:
                    pass
        
        if modified:
            # 记录本次顺延日期
            data['_last_advance_date'] = today.strftime('%Y-%m-%d')
            with open(EARNINGS_CONFIG_PATH, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tqdm.write(f"所有日期已顺延一周。新日期已记录。")
            return True
        return False
    except Exception as e:
        tqdm.write(f"顺延日期出错：{e}")
        return False

def run_single_scraper_task(driver, sectors_data, task_config):
    group_name = task_config["group_name"]
    file_path = task_config["file_path"]
    diff_path = task_config["diff_path"]
    backup_dir = task_config["backup_dir"]
    earnings_release_path = task_config["earnings_release_path"]

    tqdm.write(f">> 正在初始化任务: {group_name.upper()}")
    
    # -------- 步骤 1: 直接从配置文件读取日期范围 --------
    last_sd, last_ed = load_last_range_by_group(group_name)
    start_date = datetime(last_sd.year, last_sd.month, last_sd.day)
    end_date = datetime(last_ed.year, last_ed.month, last_ed.day)
    
    tqdm.write(f"   日期范围: {start_date.date()} -> {end_date.date()}")

    # 数据准备
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

    # 读取现有文件内容
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

    # 3. 构造日期列表
    new_entries = []
    delta = timedelta(days=1)
    date_list = [start_date + i * delta for i in range((end_date - start_date).days + 1)]
    
    date_pbar = tqdm(date_list, desc=f"   [{group_name}] 日期进度", position=1, leave=False)
    
    for single_date in date_pbar:
        ds = single_date.strftime('%Y-%m-%d')
        offset = 0
        date_pbar.set_description(f"   [{group_name}] {ds}")
        
        while True:
            date_pbar.set_postfix(offset=offset, new=len(new_entries))
            url = f"https://finance.yahoo.com/calendar/earnings?day={ds}&offset={offset}&size=100"
            rows = []
            found_end = False
            page_load_success = False

            # --- 页面加载重试循环 ---
            for attempt in range(3):
                try:
                    driver.get(url)
                    
                    # 优先检测“无结果”标志
                    end_msg = driver.find_elements(By.XPATH, "//*[contains(normalize-space(.), \"We couldn't find any results\")]")
                    if end_msg:
                        found_end = True
                        page_load_success = True
                        break
                    
                    try:
                        tbl = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
                        )
                        current_rows = tbl.find_elements(By.CSS_SELECTOR, "tbody > tr")
                        if current_rows:
                            rows = current_rows
                            page_load_success = True
                            break 
                    except TimeoutException:
                        pass 
                    
                    time.sleep(random.randint(2, 4))
                except Exception:
                    time.sleep(random.randint(2, 4))

            if found_end: break 
            if not page_load_success: 
                tqdm.write(f"    [{ds}] Offset {offset} 加载失败，跳过。")
                break
            if not rows: break 

            # --- 解析表格行 ---
            for row in rows:
                try:
                    symbol_el = row.find_element(By.CSS_SELECTOR, 'a[title][href*="/quote/"]')
                    symbol = symbol_el.get_attribute('title')
                    
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
                        if old_ct == call_time and old_dt == ds: 
                            continue 
                        existing_lines = [ln for ln in existing_lines if ln.split(':')[0].strip() != symbol]
                    
                    existing_map[symbol] = (call_time, ds)
                    new_entries.append(new_line)
                except Exception:
                    continue
            offset += 100

    # 4. 写入文件处理
    symbols_to_avoid = set()
    for f_path in task_config["duplicate_check_files"]:
        if os.path.exists(f_path):
            with open(f_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if parts: symbols_to_avoid.add(parts[0].strip())
    
    existing_diff_lines = set()
    if os.path.exists(diff_path):
        with open(diff_path, 'r') as f_diff:
            existing_diff_lines.update(ln.rstrip('\n') for ln in f_diff)

    entries_for_target = []
    entries_for_diff = []
    
    for ln in new_entries:
        sym = ln.split(':')[0].strip()
        if sym in symbols_to_avoid:
            if ln not in existing_diff_lines:
                entries_for_diff.append(ln)
                existing_diff_lines.add(ln)
        elif sym in recent_backup_symbols:
            marked = f"{ln} #BACKUP_DUP"
            if marked not in existing_diff_lines:
                entries_for_diff.append(marked)
                existing_diff_lines.add(marked)
        else:
            entries_for_target.append(ln)

    all_lines_to_write = existing_lines + entries_for_target
    with open(file_path, 'w') as f:
        if all_lines_to_write:
            f.write('\n'.join(all_lines_to_write) + '\n')

    if entries_for_diff:
        os.makedirs(os.path.dirname(diff_path), exist_ok=True)
        with open(diff_path, 'a') as f:
            for ln in entries_for_diff: f.write(ln + '\n')
            
    if not entries_for_target and not entries_for_diff:
        tqdm.write(f"   [结果] {group_name.upper()} 任务执行完毕，未发现任何新记录。")
    else:
        tqdm.write(f"   [结果] {group_name.upper()} 任务有更新：")
        if entries_for_target:
            tqdm.write(f"     ✅ 主文件新增 {len(entries_for_target)} 条:")
            for item in entries_for_target:
                tqdm.write(f"        -> {item}")
        if entries_for_diff:
            tqdm.write(f"     ⚠️ Diff 文件新增 {len(entries_for_diff)} 条:")
            for item in entries_for_diff:
                tqdm.write(f"        -> {item}")
    tqdm.write("")

def run_earnings_task():
    tqdm.write("\n" + "="*50)
    tqdm.write(">>> 开始执行任务: Earnings Release")
    tqdm.write("="*50)
    
    check_and_advance_dates_if_needed()
    
    base_news_path = '/Users/yanzhang/Coding/News/'
    
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

    tqdm.write("正在启动浏览器 (Earnings)...")
    driver = create_unified_driver()
    if driver:
        try:
            with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json', 'r') as f:
                sectors_data = json.load(f)

            task_pbar = tqdm(TASK_CONFIGS, desc="总任务进度", position=0)
            
            for config in task_pbar:
                task_pbar.set_description(f"执行任务: {config['group_name'].upper()}")
                run_single_scraper_task(driver, sectors_data, config)
            
            tqdm.write("\n所有 Earnings 任务执行完毕。")
        except Exception as e:
            tqdm.write(f"Earnings 任务执行出错: {e}")
        finally:
            driver.quit()
            tqdm.write("Earnings 浏览器已关闭。")
            
        try:
            final_root = tk.Tk(); final_root.withdraw()
            show_alert_mac("Earnings 抓取任务已完成！")
            final_root.destroy()
        except: pass
    else:
        tqdm.write("无法启动浏览器，跳过 Earnings 任务。")

def run_part_b():
    tqdm.write("\n" + "="*50)
    tqdm.write(">>> 正在启动 Part B (Selenium 爬虫任务)")
    tqdm.write("="*50)
    
    # 启动全局防 AFK 线程
    # mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
    # mouse_thread.start()
    # tqdm.write("后台鼠标防休眠线程已启动...")

    try:
        # 1. 运行 Economic Events 任务
        run_economic_events_task()
        
        # 缓冲
        time.sleep(2)
        
        # 2. 运行 Stock Splits 任务
        run_stock_splits_task()
        
        # 缓冲
        time.sleep(2)
        
        # 3. 运行 Earnings Release 任务
        run_earnings_task()
    
    except KeyboardInterrupt:
        tqdm.write("\n程序被用户手动终止。")
    except Exception as e:
        tqdm.write(f"\nPart B 发生未知错误: {e}")

# ==============================================================================
# MAIN: 主程序入口
# ==============================================================================

if __name__ == "__main__":
    # 1. 执行 Part A (文件处理/迁移)
    # 如果 Part A 因为“今天已运行过”而退出，它不会杀掉进程，只会返回
    processor_a = PartA_FileProcessor()
    processor_a.run()
    
    # 2. 缓冲一下
    time.sleep(1)
    
    # 3. 执行 Part B (爬虫)
    run_part_b()
