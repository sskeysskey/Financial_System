import os
import json
import shutil
import time
import random
import threading
import subprocess
import tkinter as tk
from datetime import datetime, timedelta

# Selenium 模块
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# 第三方辅助模块
import pyautogui
from tqdm import tqdm

# ==============================================================================
# 1. 通用模块和函数 (所有任务共用)
# ==============================================================================

# -------- 鼠标防 AFK 线程 (全局唯一) --------------------------------
def move_mouse_periodically():
    """在后台周期性地移动鼠标以防止系统休眠或 AFK 检测。"""
    # tqdm.write("启动防 AFK 鼠标移动线程...")
    while True:
        try:
            w, h = pyautogui.size()
            x = random.randint(100, w - 100)
            y = random.randint(100, h - 100)
            pyautogui.moveTo(x, y, duration=1)
            # 随机休眠
            time.sleep(random.randint(30, 60))
        except Exception:
            # 这里的 print 使用 tqdm.write 比较安全
            pass 
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
        tqdm.write(f"今天是工作日(周{'二三四五六'[today_weekday-1]})，保持现有日期配置...")
        return False

    try:
        # 读取配置文件
        if not os.path.exists(config_path):
            return False

        with open(config_path, 'r') as f:
            data = json.load(f)

        # 检查上次顺延日期
        last_advance_str = data.get('_last_advance_date')
        
        # 简单的周判断逻辑
        def get_week_start(d): return d - timedelta(days=d.weekday())
        current_week_start = get_week_start(today)

        if last_advance_str:
            last_advance_date = datetime.strptime(last_advance_str, '%Y-%m-%d').date()
            if current_week_start == get_week_start(last_advance_date):
                tqdm.write(f"本周已在 {last_advance_str} 执行过日期顺延，跳过。")
                return False

        tqdm.write(f"今天是{'周日' if today_weekday == 6 else '周一'}，开始执行日期顺延...")
        
        modified = False
        for group_name in data:
            # 跳过特殊键
            if group_name.startswith('_'):
                continue
            
            if 'start_date' in data[group_name] and 'end_date' in data[group_name]:
                try:
                    old_start = datetime.strptime(data[group_name]['start_date'], '%Y-%m-%d').date()
                    old_end = datetime.strptime(data[group_name]['end_date'], '%Y-%m-%d').date()
                    
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
            with open(config_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tqdm.write(f"所有日期已顺延一周。")
            return True
        return False

    except Exception as e:
        tqdm.write(f"顺延日期出错：{e}")
        return False

def show_alert(message):
    """Mac 系统弹窗"""
    try:
        applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    except:
        pass

# ==============================================================================
# 2. 核心抓取与处理函数 (引入 tqdm)
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

    # 使用 tqdm.write 输出初始化信息，避免打断进度条
    tqdm.write(f">> 正在初始化任务: {group_name.upper()}")

    # -------- 步骤 1: 直接从配置文件读取日期范围（已在主程序中完成顺延） --------
    last_sd, last_ed = load_last_range_by_group(group_name)
    start_date = datetime(last_sd.year, last_sd.month, last_sd.day)
    end_date = datetime(last_ed.year, last_ed.month, last_ed.day)
    
    tqdm.write(f"   日期范围: {start_date.date()} -> {end_date.date()}")

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

    # 读取现有文件内容（用于追加前的内存排重）
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

    # --- 内层进度条：遍历日期 ---
    # position=1, leave=False 表示这个条跑完一天就消失或刷新
    date_pbar = tqdm(date_list, desc=f"  [{group_name}] 日期进度", position=1, leave=False)

    for single_date in date_pbar:
        ds = single_date.strftime('%Y-%m-%d')
        offset = 0
        
        # 更新内层进度条描述
        date_pbar.set_description(f"  [{group_name}] {ds}")
        
        while True:
            # 实时更新后缀：当前 offset 和已发现条数
            date_pbar.set_postfix(offset=offset, new=len(new_entries))
            
            url = f"https://finance.yahoo.com/calendar/earnings?day={ds}&offset={offset}&size=100"
            rows = []
            found_end = False
            page_load_success = False

            # --- 页面加载重试循环 ---
            for attempt in range(3):
                try:
                    driver.get(url)
                    
                    # 优先检测“无结果”标志 (速度快)
                    end_msg = driver.find_elements(By.XPATH, "//*[contains(normalize-space(.), \"We couldn't find any results\")]")
                    if end_msg:
                        found_end = True
                        page_load_success = True
                        break

                    # 其次检测表格
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
                        pass # 可能超时，或者确实没表格但也没出 No results 提示

                    # 既无数据也无结束语，稍作等待重试
                    time.sleep(random.randint(2, 4))

                except Exception:
                    time.sleep(random.randint(2, 4))

            # --- 判断分页逻辑 ---
            if found_end: break # 到头了
            if not page_load_success: 
                tqdm.write(f"    [{ds}] Offset {offset} 加载失败，跳过。")
                break
            if not rows: break # 空行兜底

            # --- 解析表格行 ---
            for row in rows:
                try:
                    # 获取 Symbol
                    symbol_el = row.find_element(By.CSS_SELECTOR, 'a[title][href*="/quote/"]')
                    symbol = symbol_el.get_attribute('title')
                    
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) < 4: continue
                    
                    event_name = cells[2].text.strip()
                    call_time = cells[3].text.strip() or "N/A"
                    
                    # 过滤逻辑
                    if not any(k in event_name for k in ["Earnings Release", "Shareholders Meeting", "Earnings Announcement"]):
                        continue
                    if (symbol, ds) in existing_release_entries:
                        continue
                    if not any(symbol in lst for lst in sectors_data.values()):
                        continue
                    
                    # 组装行
                    new_line = f"{symbol:<7}: {call_time:<4}: {ds}"
                    
                    # 内存排重/更新逻辑
                    if symbol in existing_map:
                        old_ct, old_dt = existing_map[symbol]
                        if old_ct == call_time and old_dt == ds: 
                            continue # 完全一致跳过
                        # 有变化，先移除旧的
                        existing_lines = [ln for ln in existing_lines if ln.split(':')[0].strip() != symbol]
                        
                    existing_map[symbol] = (call_time, ds)
                    new_entries.append(new_line)

                except Exception:
                    continue
            
            offset += 100
            # 简单防封限速
            # time.sleep(0.5) 

    # 4. 写入文件处理
    symbols_to_avoid = set()
    # 读取所有配置的排重文件
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

    # (C) 将新条目分类到 target 文件或 diff 文件
    entries_for_target = []
    entries_for_diff = []

    for ln in new_entries:
        sym = ln.split(':')[0].strip()
        # 已经在其他组里的 -> 放入 Diff
        if sym in symbols_to_avoid:
            if ln not in existing_diff_lines:
                entries_for_diff.append(ln)
                existing_diff_lines.add(ln)
        # 已经在历史备份里的 -> 标记后放入 Diff
        elif sym in recent_backup_symbols:
            marked = f"{ln} #BACKUP_DUP"
            if marked not in existing_diff_lines:
                entries_for_diff.append(marked)
                existing_diff_lines.add(marked)
        # 纯新 -> 放入 Target
        else:
            entries_for_target.append(ln)

    # (D) 写入目标文件
    # 逻辑调整：总是以 'w' 模式写入，先写旧行再写新行
    all_lines_to_write = existing_lines + entries_for_target
    with open(file_path, 'w') as f:
        if all_lines_to_write:
            f.write('\n'.join(all_lines_to_write) + '\n')

    # 写入 Diff 文件
    if entries_for_diff:
        os.makedirs(os.path.dirname(diff_path), exist_ok=True)
        with open(diff_path, 'a') as f:
            for ln in entries_for_diff: f.write(ln + '\n')
            
    # ================= 修改区域：详细日志输出 =================
    
    # 判断是否完全没有任何新数据
    if not entries_for_target and not entries_for_diff:
        # 显式输出无内容提示
        tqdm.write(f"   [结果] {group_name.upper()} 任务执行完毕，未发现任何新记录。")
    else:
        # 有数据，输出详情
        tqdm.write(f"   [结果] {group_name.upper()} 任务有更新：")
        
        if entries_for_target:
            tqdm.write(f"     ✅ 主文件新增 {len(entries_for_target)} 条:")
            for item in entries_for_target:
                # item 格式为 "Symbol : Time : Date"
                tqdm.write(f"        -> {item}")
        
        if entries_for_diff:
            tqdm.write(f"     ⚠️ Diff 文件新增 {len(entries_for_diff)} 条:")
            for item in entries_for_diff:
                tqdm.write(f"        -> {item}")
    
    # 打印一个空行分隔任务
    tqdm.write("")

# ==============================================================================
# 3. 主执行逻辑
# ==============================================================================

if __name__ == "__main__":
    # 1. 启动防 AFK
    threading.Thread(target=move_mouse_periodically, daemon=True).start()

    # 2. 检查自动顺延
    check_and_advance_dates_if_needed()

    # 3. 任务配置
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

    # 4. 初始化 Selenium (Headless New 模式)
    tqdm.write("正在初始化浏览器 (Headless Mode)...")
    
    options = webdriver.ChromeOptions()
    # --- Headless 核心设置 ---
    options.add_argument('--headless=new') 
    options.add_argument('--window-size=1920,1080')
    # --- 伪装设置 ---
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    options.add_argument(f'user-agent={user_agent}')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    # --- 性能优化 ---
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--blink-settings=imagesEnabled=false") 
    options.page_load_strategy = 'eager'

    driver_path = "/Users/yanzhang/Downloads/backup/chromedriver"
    driver = None

    try:
        if not os.path.exists(driver_path):
            tqdm.write(f"错误：未找到驱动文件: {driver_path}")
            exit(1)
            
        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        
        # 额外：屏蔽 navigator.webdriver 特征
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            })
            """
        })

        # 加载基础数据
        with open('/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json', 'r') as f:
            sectors_data = json.load(f)

        # 5. 执行任务循环 (外层进度条)
        # position=0 表示最顶层
        task_pbar = tqdm(TASK_CONFIGS, desc="总任务进度", position=0)
        
        for config in task_pbar:
            task_pbar.set_description(f"执行任务: {config['group_name'].upper()}")
            run_scraper_task(driver, sectors_data, config)

        tqdm.write("\n所有任务执行完毕。")

    except Exception as e:
        tqdm.write(f"程序执行出错: {e}")
    finally:
        # -------- 统一清理资源 -----------------------------------------
        if driver:
            try:
                driver.quit()
                tqdm.write("浏览器已关闭。")
            except:
                pass
        
        # 最终弹窗
        try:
            final_root = tk.Tk()
            final_root.withdraw()
            show_alert("Earnings 抓取任务已完成！")
            final_root.destroy()
        except:
            pass
