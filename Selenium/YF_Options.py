import sqlite3
import csv
import time
import os
import pyautogui
import random
import threading
import sys  # 新增：用于终止程序
import tkinter as tk # 新增：用于弹窗
from tkinter import messagebox # 新增：用于弹窗
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from tqdm import tqdm

# ================= 配置区域 =================

# --- 1. 基础路径配置 ---
# 数据库路径
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'
# 输出文件保存目录
OUTPUT_DIR = '/Users/yanzhang/Coding/News/backup/'
# 市值阈值 (10000亿) - 仅在数据库模式下生效
MARKET_CAP_THRESHOLD = 4000000000000

# --- 2. 数据源开关配置 ---
# 设置为 True: 使用下方的 CUSTOM_SYMBOLS_DATA 列表 (默认)
# 设置为 False: 使用数据库 MNSPP 表进行筛选
USE_CUSTOM_LIST = True 

# True 改成 False 用于切换从哪里获取Symbol
# USE_CUSTOM_LIST = False 

# 自定义 Symbol 列表
CUSTOM_SYMBOLS_DATA = [
    "^VIX", "NVDA", "AAPL", "GOOGL", "MSFT", "META",
    "TSM", "WMT", "HYG", "QQQ", "SPY"
]

# --- 3. 文件名生成 ---
# 生成当天的文件名 Options_YYMMDD.csv
today_str = datetime.now().strftime('%y%m%d')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f'Options_{today_str}.csv')

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
            # 使用 tqdm.write 防止打断主线程进度条，但这里是在子线程，直接 print 也可以，
            # 为了安全起见，尽量少输出
            pass

# ================= 1. 数据库操作 =================
def get_target_symbols(db_path, threshold):
    """从数据库中获取符合市值要求的 Symbol"""
    tqdm.write(f"正在连接数据库: {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查询 marketcap 大于阈值的 symbol
        query = "SELECT symbol, marketcap FROM MNSPP WHERE marketcap > ?"
        cursor.execute(query, (threshold,))
        results = cursor.fetchall()
        
        symbols = [row[0] for row in results]
        tqdm.write(f"共找到 {len(symbols)} 个市值大于 {threshold} 的代码。")
        return symbols
    except Exception as e:
        tqdm.write(f"数据库读取错误: {e}")
        return []
    finally:
        if conn:
            conn.close()

# ================= 2. 数据处理工具函数 =================
def format_date(date_str):
    """将 'Dec 19, 2025' 转换为 '2025/12/19'"""
    try:
        # 移除可能存在的额外空格
        date_str = date_str.strip()
        dt = datetime.strptime(date_str, "%b %d, %Y")
        return dt.strftime("%Y/%m/%d")
    except ValueError:
        return date_str

def clean_number(num_str):
    """处理数字字符串：去除逗号，将 '-' 转为 0"""
    if not num_str or num_str.strip() == '-' or num_str.strip() == '':
        return 0
    try:
        # 去除逗号
        clean_str = num_str.replace(',', '').strip()
        return int(clean_str) # Open Interest 应该是整数
    except ValueError:
        return 0

def show_error_popup(symbol):
    """显示错误弹窗"""
    try:
        # 创建一个隐藏的主窗口
        root = tk.Tk()
        root.withdraw() 
        # 保持窗口在最上层
        root.attributes("-topmost", True)
        messagebox.showerror(
            "严重错误 - 程序终止", 
            f"无法获取代码 [{symbol}] 的期权日期列表！\n\n已尝试重试 5 次均失败。\n程序将停止运行以避免数据缺失。"
        )
        root.destroy()
    except Exception as e:
        print(f"弹窗显示失败: {e}")

# ================= 3. 爬虫核心逻辑 =================
def scrape_options():
    # 在主程序开始前启动鼠标移动线程
    # mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
    # mouse_thread.start()
    
    # --- 1. 获取目标 Symbols (根据开关决定来源) ---
    symbols = []
    if USE_CUSTOM_LIST:
        tqdm.write(f"【模式】使用自定义列表模式")
        symbols = CUSTOM_SYMBOLS_DATA
        tqdm.write(f"加载了 {len(symbols)} 个目标代码")
    else:
        tqdm.write(f"【模式】使用数据库筛选模式 (阈值: {MARKET_CAP_THRESHOLD})")
        symbols = get_target_symbols(DB_PATH, MARKET_CAP_THRESHOLD)

    if not symbols:
        tqdm.write("未找到任何 Symbol，程序结束。")
        return

    # 2. 初始化 CSV 文件 (写入表头)
    # 确保目录存在
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Symbol', 'Expiry Date', 'Type', 'Strike', 'Open Interest'])

    # 3. 初始化 Selenium
    options = webdriver.ChromeOptions()
    
    # --- Headless模式相关设置 ---
    options.add_argument('--headless=new') # 推荐使用新的 headless 模式
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
    options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
    options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

    driver_path = '/Users/yanzhang/Downloads/backup/chromedriver' 

    # 检查路径是否存在，避免报错
    if not os.path.exists(driver_path):
        tqdm.write(f"错误：未找到驱动文件: {driver_path}")
        exit()

    driver = webdriver.Chrome(service=Service(driver_path), options=options)
    
    # 设置页面加载超时，防止卡死
    driver.set_page_load_timeout(30) 
    
    wait = WebDriverWait(driver, 5) # 稍微增加默认等待时间

    try:
        # === 外层进度条：遍历 Symbols ===
        # position=0 表示这是最顶层的进度条
        symbol_pbar = tqdm(symbols, desc="总体进度", position=0)
        
        for symbol in symbol_pbar:
            # 更新进度条描述，显示当前正在处理谁
            symbol_pbar.set_description(f"处理中: {symbol}")
            
            base_url = f"https://finance.yahoo.com/quote/{symbol}/options/"
            
            # --- 阶段一：获取日期列表 (包含重试机制) ---
            date_map = []
            max_date_retries = 5
            
            for date_attempt in range(max_date_retries):
                try:
                    # 每次尝试都重新加载页面
                    try:
                        driver.get(base_url)
                    except TimeoutException:
                        tqdm.write(f"[{symbol}] 页面加载超时，停止加载并尝试操作...")
                        driver.execute_script("window.stop();")
                    
                    # 确保页面基本结构加载
                    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    
                    # 尝试点击日期下拉菜单
                    date_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-ylk*='slk:date-select']")))
                    
                    # 滚动到元素可见，防止被广告遮挡
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_button)
                    time.sleep(1) # 稍微多等待一点时间让JS执行
                    date_button.click()
                    
                    # 显式等待下拉菜单出现 (查找带有 data-value 的 div 或 option)
                    # Yahoo 新版下拉菜单通常在 div 中，且带有 data-value 属性
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-value]")))
                    time.sleep(0.5) # 动画缓冲
                    
                    # 提取所有日期选项
                    # 策略：查找所有带有 data-value 属性且看起来像时间戳的元素
                    # 这里的选择器不再局限于 .dialog-content，而是更宽泛地查找菜单项
                    options_elements = driver.find_elements(By.CSS_SELECTOR, "div[role='menu'] div[data-value], div.itm[data-value]")
                    
                    # 如果上面没找到，尝试更暴力的查找所有带 data-value 的 div，然后过滤
                    if not options_elements:
                         options_elements = driver.find_elements(By.CSS_SELECTOR, "div[data-value]")

                    temp_date_map = []
                    for opt in options_elements:
                        ts = opt.get_attribute("data-value")
                        raw_text = opt.text.split('\n')[0].strip()
                        
                        # 验证 ts 是否为数字（时间戳）
                        if ts and ts.isdigit() and raw_text:
                            if (ts, raw_text) not in temp_date_map:
                                temp_date_map.append((ts, raw_text))
                    
                    if temp_date_map:
                        date_map = temp_date_map
                        # 成功获取，关闭菜单并跳出重试循环
                        try:
                            webdriver.ActionChains(driver).send_keys(u'\ue00c').perform() # ESC
                        except:
                            pass
                        break # 成功，退出重试循环
                    else:
                        raise Exception("找到菜单元素但未提取到有效日期")

                except Exception as e:
                    tqdm.write(f"[{symbol}] 获取日期列表失败 (尝试 {date_attempt + 1}/{max_date_retries}): {str(e)[:100]}")
                    time.sleep(random.uniform(2, 4)) # 失败后等待几秒再重试

            # --- 检查是否获取到日期 ---
            if not date_map:
                tqdm.write(f"[{symbol}] ❌ 严重错误：经过 {max_date_retries} 次尝试仍无法获取日期列表！")
                
                # 1. 关闭浏览器
                driver.quit()
                
                # 2. 弹窗提示
                show_error_popup(symbol)
                
                # 3. 终止程序
                sys.exit(1)

            # --- 过滤日期 (6个月) ---
            filtered_date_map = []
            try:
                temp_list = []
                for ts, d_text in date_map:
                    try:
                        d_obj = datetime.strptime(d_text, "%b %d, %Y")
                        temp_list.append((ts, d_text, d_obj))
                    except:
                        continue
                
                temp_list.sort(key=lambda x: x[2])
                
                if temp_list:
                    start_dt = temp_list[0][2]
                    cutoff_dt = start_dt + timedelta(days=180)
                    
                    for ts, d_text, d_obj in temp_list:
                        if d_obj <= cutoff_dt:
                            filtered_date_map.append((ts, d_text))
                
                date_map = filtered_date_map
                tqdm.write(f"[{symbol}] 成功获取 {len(date_map)} 个日期 (6个月内)")
                
            except Exception as e:
                tqdm.write(f"[{symbol}] 日期过滤出错: {e}，将使用所有获取到的日期")

            # === 内层进度条：遍历日期 ===
            date_pbar = tqdm(date_map, desc=f"  {symbol} 日期", position=1, leave=False)
            
            for ts, date_text in date_pbar:
                formatted_date = format_date(date_text)
                target_url = f"{base_url}?date={ts}" if ts else base_url

                # === 重试机制 (针对具体日期的数据抓取) ===
                MAX_PAGE_RETRIES = 3
                for attempt in range(MAX_PAGE_RETRIES):
                    try:
                        # 如果不是第一次循环且有 timestamp，需要跳转
                        # 如果是默认页且是第一次，其实已经在页面上了，但为了稳妥还是 get 一下
                        try:
                            driver.get(target_url)
                        except TimeoutException:
                            driver.execute_script("window.stop();")
                        
                        # 等待表格出现
                        # 增加等待时间，因为切换日期是 AJAX 加载
                        time.sleep(random.uniform(1.5, 2.5)) 
                        
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-testid='options-list-table'] table")))

                        # --- 抓取表格 ---
                        tables = driver.find_elements(By.CSS_SELECTOR, "section[data-testid='options-list-table'] table")
                        
                        # 检查是否真的有数据行
                        has_data = False
                        data_buffer = []
                        option_types = ['Calls', 'Puts']

                        for i, table in enumerate(tables):
                            if i >= len(option_types): break
                            opt_type = option_types[i]
                            
                            # 优化：直接获取 tbody 下的 tr，避开表头
                            rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
                            
                            for row in rows:
                                cols = row.find_elements(By.TAG_NAME, "td")
                                if not cols: continue
                                # 确保列数足够 (Yahoo Options 表格通常有很多列)
                                if len(cols) >= 10:
                                    # 针对不同分辨率，列索引可能微调，但通常 Strike 在 2 (index 2), OI 在 9 (index 9)
                                    # 检查列内容是否有效
                                    strike_text = cols[2].text.strip()
                                    oi_text = cols[9].text.strip()
                                    
                                    if strike_text:
                                        strike = strike_text.replace(',', '')
                                        oi = clean_number(oi_text)
                                        data_buffer.append([symbol, formatted_date, opt_type, strike, oi])
                                        has_data = True
                        
                        if not has_data and attempt < MAX_PAGE_RETRIES - 1:
                            time.sleep(2)
                            continue

                        # --- 写入文件 ---
                        if data_buffer:
                            with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                                writer = csv.writer(f)
                                writer.writerows(data_buffer)
                        
                        break # 成功则跳出重试循环

                    except Exception as e:
                        if attempt < MAX_PAGE_RETRIES - 1:
                            time.sleep(2)
                        else:
                            pass

    finally:
        # 防止重复 quit
        try:
            driver.quit()
        except:
            pass
        tqdm.write(f"任务结束。数据已保存至: {OUTPUT_FILE}")

if __name__ == "__main__":
    scrape_options()