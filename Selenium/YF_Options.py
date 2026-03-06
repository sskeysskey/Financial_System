import sqlite3
import csv
import time
import os
import pyautogui
import random
import json
# import threading
import sys
import tkinter as tk
import subprocess  # <--- 新增：用于执行外部脚本
from tkinter import messagebox
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from tqdm import tqdm
import platform
import urllib.parse  # 导入用于处理 URL 编码

# ================= 配置区域 =================
USER_HOME = os.path.expanduser("~")

# 2. 定义基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_BACKUP_DIR = os.path.join(BASE_CODING_DIR, "News", "backup")

# 3. 具体业务文件路径
DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
OUTPUT_DIR = NEWS_BACKUP_DIR
SECTORS_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_panel.json")
BLACKLIST_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Blacklist.json")

# 4. 分析脚本路径 (新增)
ANALYSE_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Analyse_Options.py")

# 5. 浏览器与驱动路径 (跨平台适配)
if platform.system() == 'Darwin':
    CHROME_BINARY_PATH = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver_beta")
elif platform.system() == 'Windows':
    # Windows 路径优化
    CHROME_BINARY_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(CHROME_BINARY_PATH):
        CHROME_BINARY_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver.exe")
else:
    CHROME_BINARY_PATH = "/usr/bin/google-chrome"
    CHROME_DRIVER_PATH = "/usr/bin/chromedriver"

# 市值阈值 (1000亿) - 仅在数据库模式下生效
MARKET_CAP_THRESHOLD = 400000000000

# 文件名生成
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
            # 使用 tqdm.write 防止打断主线程进度条
            pass

# ================= 1. 数据库操作 =================

def get_target_symbols(db_path, threshold, silent=False):
    """从数据库中获取符合市值要求的 Symbol，并按市值降序排列"""
    if not silent:
        tqdm.write(f"正在连接数据库: {db_path}...")
    try:
        if not os.path.exists(db_path):
            tqdm.write(f"❌ 数据库文件不存在: {db_path}")
            return []
            
        conn = sqlite3.connect(db_path, timeout=60.0)
        cursor = conn.cursor()
        
        # 增加 ORDER BY marketcap DESC
        query = "SELECT symbol, marketcap FROM MNSPP WHERE marketcap > ? ORDER BY marketcap DESC"
        cursor.execute(query, (threshold,))
        symbols = cursor.fetchall()
        if not silent:
            tqdm.write(f"共找到 {len(symbols)} 个市值大于 {threshold} 的代码。")
        return symbols
    except Exception as e:
        tqdm.write(f"数据库读取错误: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
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
    """处理 Open Interest：去除逗号，转为整数"""
    if not num_str or num_str.strip() == '-' or num_str.strip() == '':
        return 0
    try:
        # 去除逗号
        clean_str = num_str.replace(',', '').strip()
        return int(clean_str) # Open Interest 应该是整数
    except ValueError:
        return 0

def clean_price_and_multiply(price_str):
    """
    处理 Last Price：
    1. 去除逗号
    2. 将 '-' 转为 0
    3. 转为 float 并乘以 100
    """
    if not price_str or price_str.strip() == '-' or price_str.strip() == '':
        return 0.0
    try:
        clean_str = price_str.replace(',', '').strip()
        price_val = float(clean_str)
        return round(price_val * 100, 2) # 乘以100并保留两位小数
    except ValueError:
        return 0.0

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

def update_sectors_json(symbol, json_path):
    """将 Open Interest 异常的 Symbol 更新到 JSON 文件的 Options_zero 分组"""
    try:
        if not os.path.exists(json_path):
            tqdm.write(f"⚠️ JSON 文件不存在，无法更新: {json_path}")
            return

        # 1. 读取现有 JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 2. 确保 Options_zero 分组存在
        if "Options_zero" not in data:
            data["Options_zero"] = {}

        # 3. 更新/覆盖写入 Symbol (保留原有内容，追加新 Symbol)
        # 如果需要彻底清空 Options_zero 只保留当前这一个，请改为 data["Options_zero"] = {symbol: ""}
        data["Options_zero"][symbol] = ""

        # 4. 写回文件
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        tqdm.write(f"📝JSON已更新: [{symbol}] -> Options_zero")

    except Exception as e:
        tqdm.write(f"⚠️ 更新 JSON 失败: {e}")

def show_final_summary_popup_from_json(json_path):
    """任务结束后，从 JSON 读取 Options_zero 分组并显示汇总弹窗"""
    try:
        if not os.path.exists(json_path):
            return

        # 1. 读取 JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 2. 获取 Options_zero 列表
        zero_group = data.get("Options_zero", {})
        zero_list = list(zero_group.keys())
        
        if not zero_list:
            # 如果列表为空，不需要弹窗
            return

        count = len(zero_list)
        
        # 创建临时窗口
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        
        # 如果列表太长，只显示前20个，后面用...代替
        if count > 20:
            details = "\n".join(zero_list[:20]) + f"\n...以及其他 {count - 20} 个"
        else:
            details = "\n".join(zero_list)

        messagebox.showinfo(
            "数据质量监控报告 (Options_zero)", 
            f"任务结束。\n\n"
            f"目前【Options_zero】分组中共有 {count} 个 Symbol。\n"
            f"这些 Symbol 因 Open Interest 数据无效已被记录，\n"
            f"并在下次运行时自动跳过。\n\n"
            f"列表如下：\n{details}"
        )
        root.destroy()
    except Exception as e:
        print(f"弹窗显示失败: {e}")

# ================= 3. 自动执行分析脚本 =================

def run_analysis_program():
    """执行 Analyse_Options.py 脚本"""
    print("\n" + "="*50)
    print("🚀 准备启动分析程序...")
    
    if os.path.exists(ANALYSE_SCRIPT_PATH):
        try:
            print(f"📂 脚本路径: {ANALYSE_SCRIPT_PATH}")
            # 使用当前的 python 解释器执行脚本
            subprocess.run([sys.executable, ANALYSE_SCRIPT_PATH], check=True)
            print("✅ 分析程序执行完毕。")
        except subprocess.CalledProcessError as e:
            print(f"❌ 分析程序执行出错 (Exit Code: {e.returncode})")
        except Exception as e:
            print(f"❌ 启动分析程序时发生未知错误: {e}")
    else:
        print(f"⚠️ 未找到分析脚本文件: {ANALYSE_SCRIPT_PATH}")
        print("请检查路径是否正确。")
    print("="*50 + "\n")

# ================= 4. 爬虫核心逻辑 =================

def scrape_options():
    # 在主程序开始前启动鼠标移动线程
    # mouse_thread = threading.Thread(target=move_mouse_periodically, daemon=True)
    # mouse_thread.start()
    
    # --- 1. 获取目标 Symbols (合并模式) ---

    # === 步骤 A: 初始化各个分组集合 (变量名已统一为 JSON Key 风格) ===
    json_options_set = set() 
    json_pe_volume_set = set()      # 原 json_must_set
    json_pe_volume_up_set = set()   # 原 json_today_set
    json_zero_set = set()   
    blacklist_options_set = set() 
    
    # 用于日志显示的计数
    count_json_options = 0
    count_json_pe_volume = 0        # 原 count_json_must
    count_json_pe_volume_up = 0     # 原 count_json_today
    count_json_zero = 0     

    # === 步骤 A: 加载黑名单 ===
    try:
        if os.path.exists(BLACKLIST_JSON_PATH):
            with open(BLACKLIST_JSON_PATH, 'r', encoding='utf-8') as f:
                bl_data = json.load(f)
                # 获取 Blacklist.json 中 Options 分组下的列表
                blacklist_options_set = {str(s).strip() for s in bl_data.get("Options", [])}
        else:
            tqdm.write(f"⚠️ 提示: 未找到黑名单文件: {BLACKLIST_JSON_PATH}")
    except Exception as e:
        tqdm.write(f"⚠️ 读取黑名单出错: {e}")

    # === 步骤 B: 从 Sectors_panel 加载基础列表 ===
    try:
        if os.path.exists(SECTORS_JSON_PATH):
            with open(SECTORS_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 1. 提取 Options 分组
                options_keys = data.get("Options", {}).keys()
                json_options_set = set(options_keys)
                count_json_options = len(json_options_set)
                
                # 2. [更名] 提取 PE_Volume 分组 (原 Must)
                pe_vol_keys = data.get("PE_Volume", {}).keys()
                json_pe_volume_set = set(pe_vol_keys)
                count_json_pe_volume = len(json_pe_volume_set)
                
                # 3. [更名] 提取 PE_Volume_up 分组 (原 Today)
                pe_vol_up_keys = data.get("PE_Volume_up", {}).keys()
                json_pe_volume_up_set = set(pe_vol_up_keys) 
                count_json_pe_volume_up = len(json_pe_volume_up_set)

                # 4. 提取 Options_zero 分组 (用于过滤)
                zero_keys = data.get("Options_zero", {}).keys()
                json_zero_set = set(zero_keys)
                count_json_zero = len(json_zero_set)

        else:
            tqdm.write(f"⚠️ 警告: 未找到 JSON 文件: {SECTORS_JSON_PATH}")
    except Exception as e:
        tqdm.write(f"⚠️ 读取 JSON 配置文件出错: {e}")

    # 4. 合并去重 (移除了 Short 和 Short_W)
    merged_symbols_set = (
        json_options_set
        .union(json_pe_volume_set)      # Changed
        .union(json_pe_volume_up_set)   # Changed
    )
    
    symbol_cap_map = {} # 用于存储 symbol -> marketcap 的字典
    try:
        if os.path.exists(DB_PATH):
            # 建立临时连接查询所有市值
            temp_conn = sqlite3.connect(DB_PATH, timeout=30.0)
            temp_cursor = temp_conn.cursor()
            # 查询所有有市值的记录
            temp_cursor.execute("SELECT symbol, marketcap FROM MNSPP WHERE marketcap IS NOT NULL")
            all_caps = temp_cursor.fetchall()
            
            # 存入字典
            for s, c in all_caps:
                symbol_cap_map[s] = c
                
            temp_conn.close()
            # tqdm.write(f"已加载 {len(symbol_cap_map)} 条市值数据用于匹配 JSON 列表。")
    except Exception as e:
        tqdm.write(f"⚠️ 读取数据库市值映射失败: {e}")

    # 生成自定义列表：如果字典里有市值就用字典的，没有则默认为 0
    custom_symbols_list = []
    for s in merged_symbols_set:
        # 获取市值，默认为 0
        cap = symbol_cap_map.get(s, 0)
        # 确保 cap 是数字类型 (防止数据库取出的不是 float/int)
        if not isinstance(cap, (int, float)):
            cap = 0
        custom_symbols_list.append((s, cap))

    # === 步骤 B: 获取数据库筛选列表 (静默模式) ===
    # 这里开启 silent=True，防止打印 redundant logs
    db_symbols_list = get_target_symbols(DB_PATH, MARKET_CAP_THRESHOLD, silent=True)
    
    # === 步骤 C: 合并列表与去重 ===
    # 逻辑：优先保留自定义列表中的顺序和项，数据库列表中若有重复则跳过
    
    # 1. 建立自定义 Symbol 的快速查询集合
    custom_names_set = {s[0] for s in custom_symbols_list}
    
    # 2. 筛选数据库列表：只保留不在自定义列表中的
    db_unique_list = [s for s in db_symbols_list if s[0] not in custom_names_set]
    
    all_symbols_before_blacklist = custom_symbols_list + db_unique_list
    
    # === 步骤 E: 执行黑名单及 Options_zero 过滤 (核心修改) ===
    # 过滤掉存在于 blacklist_options_set 和 json_zero_set 中的 symbol
    # 构造总的排除集合
    total_exclusion_set = blacklist_options_set.union(json_zero_set)
    symbols = [s for s in all_symbols_before_blacklist if s[0] not in total_exclusion_set]
    
    # 统计被过滤的数量
    blacklisted_count = len(all_symbols_before_blacklist) - len(symbols)
    
    if not symbols:
        tqdm.write("未找到任何 Symbol 或全部被黑名单/Options_zero 过滤，程序结束。")
        return

    # ================= 检查已存在的 Symbol 并过滤 =================
    # 获取已经抓取过的 symbol 列表
    existing_symbols = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None) # 跳过表头
                if header:
                    for row in reader:
                        if row and len(row) > 0:
                            existing_symbols.add(row[0]) 
            # tqdm.write(f"🔍 检测到现有文件，已包含 {len(existing_symbols)} 个 Symbol 的数据。")
        except Exception as e:
            tqdm.write(f"⚠️ 读取现有文件检查 Symbol 时出错: {e}，将重新抓取所有。")

    # 过滤列表：只保留不在 existing_symbols 中的代码
    # s 是 (symbol, market_cap)，所以判断 s[0]
    original_count = len(symbols)
    symbols = [s for s in symbols if s[0] not in existing_symbols]
    
    skipped_count = original_count - len(symbols)
    
    # --- 统一的日志输出 (修改部分) ---
    # 计算 JSON 总数 (移除了 Short 和 Short_W)
    total_json_count = (
        count_json_options + 
        count_json_pe_volume +      # Changed
        count_json_pe_volume_up     # Changed
    )

    log_msg = (
        f"任务列表加载完成: [JSON({total_json_count}) + 数据库({len(db_symbols_list)})] | "
        f"排除列表(Blacklist+Zero): {blacklisted_count} (其中Zero:{count_json_zero}) | "
        f"总去重: {len(symbols) + skipped_count} | "
        f"已完成: {skipped_count} | 待抓取: {len(symbols)}"
    )
    tqdm.write(log_msg)

    # 如果所有都抓完了，直接退出，不启动浏览器
    if not symbols:
        tqdm.write("✅ 所有目标 Symbol 均已存在于 CSV 中，无需执行抓取任务。")
        # [修改] 即便这里退出了，也展示一下当前的 Zero 列表状态，防止用户遗忘
        show_final_summary_popup_from_json(SECTORS_JSON_PATH)
        return True # 返回 True 表示数据状态OK，可以进行下一步分析

    # --- 2. 初始化 CSV 文件 (修改点：增加 Last Price 表头) ---
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # --- 修改开始：改为追加模式检测 ---
    # 检查文件是否存在
    file_exists = os.path.exists(OUTPUT_FILE)
    # 只有当文件不存在时，才以 'w' 模式创建并写入表头
    if not file_exists:
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # 增加 Last Price 到表头末尾
            writer.writerow(['Symbol', 'Expiry Date', 'Type', 'Strike', 'Open Interest', 'Last Price'])
        tqdm.write(f"创建新文件: {OUTPUT_FILE}")
    else:
        tqdm.write(f"文件已存在，将以追加模式运行: {OUTPUT_FILE}")

    # 3. 初始化 Selenium
    options = webdriver.ChromeOptions()
    if os.path.exists(CHROME_BINARY_PATH):
        options.binary_location = CHROME_BINARY_PATH
    else:
        tqdm.write(f"警告：未找到指定 Chrome 路径 {CHROME_BINARY_PATH}，尝试使用系统默认...")

    # --- Headless模式相关设置 ---
    options.add_argument('--headless=new') # 推荐使用新的 headless 模式
    options.add_argument('--window-size=1920,1080')

    # --- 伪装设置 ---
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    options.add_argument(f'user-agent={user_agent}')
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # --- 性能优化 ---
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--blink-settings=imagesEnabled=false")  # 禁用图片加载
    options.page_load_strategy = 'eager'  # 使用eager策略，DOM准备好就开始

    # 检查驱动是否存在
    if not os.path.exists(CHROME_DRIVER_PATH):
        tqdm.write(f"错误：未找到驱动文件: {CHROME_DRIVER_PATH}")
        exit()

    service = Service(executable_path=CHROME_DRIVER_PATH)
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        tqdm.write(f"Selenium 启动失败: {e}")
        return False

    # 设置页面加载超时，防止卡死
    driver.set_page_load_timeout(30) 
    
    wait = WebDriverWait(driver, 5) # 稍微增加默认等待时间

    try:
        # === 注意：不再初始化内存列表 skipped_zero_symbols，完全依赖 JSON ===
        
        # === 外层进度条：遍历 Symbols ===
        symbol_pbar = tqdm(symbols, desc="总体进度", position=0)
        
        # --- 修改点 4: 循环解包 ---
        for symbol_data in symbol_pbar:
            # 解包 Symbol 和 市值
            symbol, market_cap = symbol_data
            
            # 格式化市值显示 (例如: 2.3T, 500B)
            if market_cap >= 1000000000000:
                cap_str = f"{market_cap/1000000000000:.2f}T" # 万亿
            elif market_cap >= 1000000000:
                cap_str = f"{market_cap/1000000000:.2f}B"    # 十亿
            elif market_cap > 0:
                cap_str = f"{market_cap/1000000:.1f}M"       # 百万
            else:
                cap_str = "N/A" # 自定义列表显示 N/A

            # 更新进度条描述，增加显示市值
            symbol_pbar.set_description(f"处理中: {symbol} [市值: {cap_str}]")
            
            # 使用 quote 确保 ^VIX 变成 %5EVIX
            encoded_symbol = urllib.parse.quote(symbol)
            base_url = f"https://finance.yahoo.com/quote/{encoded_symbol}/options/"
            
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

            # 过滤 6 个月日期
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

            # 1. 暂存当前 symbol 所有日期的数据
            symbol_all_data = [] 
            
            # === 内层进度条：遍历日期 ===
            date_pbar = tqdm(date_map, desc=f"  {symbol} 日期", position=1, leave=False)
            
            for ts, date_text in date_pbar:
                formatted_date = format_date(date_text)
                target_url = f"{base_url}?date={ts}" if ts else base_url

                # === 重试机制 (针对具体日期的数据抓取) ===
                MAX_PAGE_RETRIES = 3
                for attempt in range(MAX_PAGE_RETRIES):
                    try:
                        # [核心修复]：在请求新 URL 前，强制删除旧表格
                        # 这样 wait.until 必须等待新表格真正加载出来
                        try:
                            driver.execute_script("""
                                var tables = document.querySelectorAll("section[data-testid='options-list-table'] table");
                                if (tables.length > 0) {
                                    tables.forEach(t => t.remove());
                                }
                            """)
                        except Exception:
                            pass # 忽略JS错误

                        # 如果不是第一次循环且有 timestamp，需要跳转
                        # 如果是默认页且是第一次，其实已经在页面上了，但为了稳妥还是 get 一下
                        try:
                            driver.get(target_url)
                        except TimeoutException:
                            driver.execute_script("window.stop();")
                        
                        # 等待表格出现
                        # 增加等待时间，因为切换日期是 AJAX 加载
                        # time.sleep(random.uniform(1.5, 2.5)) # 移除固定等待，依赖 wait
                        
                        # 这里的 wait 现在非常有意义，因为旧表格已经被删除了
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-testid='options-list-table'] table")))
                        
                        # 稍微缓冲一下，确保表格内容渲染完毕
                        time.sleep(1.0)

                        # --- 抓取表格 ---
                        tables = driver.find_elements(By.CSS_SELECTOR, "section[data-testid='options-list-table'] table")
                        
                        # 检查是否真的有数据行
                        has_data = False
                        data_buffer = [] # 单个页面的缓存
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
                                    strike = cols[2].text.strip().replace(',', '')
                                    # --- 修改点：提取 Last Price (索引3) 并清洗 ---
                                    last_price_raw = cols[3].text.strip()
                                    last_price_final = clean_price_and_multiply(last_price_raw)
                                    
                                    if strike:
                                        # 提取 Open Interest (索引9)
                                        oi = clean_number(cols[9].text.strip())
                                        # 将数据存入 buffer
                                        data_buffer.append([symbol, formatted_date, opt_type, strike, oi, last_price_final])
                                        has_data = True
                        
                        if not has_data and attempt < MAX_PAGE_RETRIES - 1:
                            time.sleep(2)
                            continue

                        # [核心修改]
                        # 成功抓取后，追加到 symbol 总表，而不是写入 CSV
                        if data_buffer:
                            symbol_all_data.extend(data_buffer)
                        
                        break # 成功则跳出重试循环
                    except Exception as e:
                        if attempt < MAX_PAGE_RETRIES - 1:
                            time.sleep(2)
                        else:
                            pass
            
            # [核心修改]
            # 当该 Symbol 的所有日期循环结束后，进行数据检查和写入
            if symbol_all_data:
                # ================= 新增：检查 Open Interest 0 值比例 =================
                try:
                    total_rows = len(symbol_all_data)
                    # 统计 Open Interest (index 4) 为 0 的行数
                    zero_count = sum(1 for row in symbol_all_data if row[4] == 0)
                    zero_ratio = zero_count / total_rows if total_rows > 0 else 0
                    
                    # === 判断逻辑 ===
                    if zero_ratio > 0.95:
                        # 场景 A: 数据质量太差
                        tqdm.write(f"⚠️ [{symbol}] 数据无效 (0值率: {zero_ratio:.1%}) -> 跳过写入，更新JSON。")
                        
                        # 1. 立即更新 JSON (持久化存储)
                        update_sectors_json(symbol, SECTORS_JSON_PATH)
                        
                        # 2. [修改] 不再写入内存列表，也不弹窗，直接 pass
                    else:
                        # 场景 B: 数据正常，写入 CSV
                        try:
                            with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                                writer = csv.writer(f)
                                writer.writerows(symbol_all_data)
                            # tqdm.write(f"[{symbol}] 数据保存完毕。")
                        except Exception as e:
                            tqdm.write(f"[{symbol}] 写入文件失败: {e}")
                            
                except Exception as e:
                    tqdm.write(f"⚠️ 处理 [{symbol}] 数据逻辑时出错: {e}")
            else:
                pass
        
        # === [核心修改] 循环结束后，从 JSON 文件读取并弹窗 ===
        # 无论中间是否中断，最后这一步只读文件，确保数据源可靠
        tqdm.write("正在生成最终报告...")
        show_final_summary_popup_from_json(SECTORS_JSON_PATH)
        
        return True # 表示任务正常结束

    finally:
        # 防止重复 quit
        try:
            if 'driver' in locals():
                driver.quit()
        except:
            pass
        tqdm.write(f"任务结束。数据已保存至: {OUTPUT_FILE}")

if __name__ == "__main__":
    # 执行爬虫任务
    # 如果 scrape_options 返回 True (无论是抓取完成，还是因为数据已存在而跳过)，都执行分析脚本
    task_success = scrape_options()
    
    if task_success:
        run_analysis_program()