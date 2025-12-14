import sqlite3
import csv
import time
import os
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

# ================= 配置区域 =================
# 数据库路径
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'
# 输出文件保存目录
OUTPUT_DIR = '/Users/yanzhang/Coding/News/backup/'
# 市值阈值 (10000亿)
MARKET_CAP_THRESHOLD = 4000000000000

# 生成当天的文件名 Options_YYMMDD.csv
today_str = datetime.now().strftime('%y%m%d')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f'Options_{today_str}.csv')

# ================= 1. 数据库操作 =================
def get_target_symbols(db_path, threshold):
    """从数据库中获取符合市值要求的 Symbol"""
    print(f"正在连接数据库: {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查询 marketcap 大于阈值的 symbol
        query = "SELECT symbol, marketcap FROM MNSPP WHERE marketcap > ?"
        cursor.execute(query, (threshold,))
        results = cursor.fetchall()
        
        symbols = [row[0] for row in results]
        print(f"共找到 {len(symbols)} 个市值大于 {threshold} 的代码。")
        return symbols
    except Exception as e:
        print(f"数据库读取错误: {e}")
        return []
    finally:
        if conn:
            conn.close()

# ================= 2. 数据处理工具函数 =================
def format_date(date_str):
    """将 'Dec 19, 2025' 转换为 '2025/12/19'"""
    try:
        # Yahoo 的日期格式通常是 "%b %d, %Y"
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

# ================= 3. 爬虫核心逻辑 =================
def scrape_options():
    # 1. 获取目标 Symbols
    symbols = get_target_symbols(DB_PATH, MARKET_CAP_THRESHOLD)
    if not symbols:
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
    # options.add_argument('--headless')  # 如果想后台运行，取消注释这一行
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    # 伪装 User-Agent 防止被轻易拦截
    options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 10)

    try:
        for symbol in symbols:
            print(f"---------- 开始抓取: {symbol} ----------")
            base_url = f"https://finance.yahoo.com/quote/{symbol}/options/"
            
            try:
                # 初始加载页面以获取日期列表
                driver.get(base_url)
                # 等待页面加载
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                # --- 第一步：获取所有日期选项 ---
                date_map = [] # 存储 (timestamp, date_text)
                # Yahoo Finance 的日期是通过 URL 参数 ?date=timestamp 控制的
                # 我们先点击下拉菜单，获取所有的 timestamp 和对应的文本，然后通过构造 URL 遍历
                # 这样比模拟点击更稳定，不会出现 StaleElementReferenceException
                
                # 点击下拉菜单以加载选项
                try:
                    # 根据你提供的 HTML，按钮有特定的 class 和 data-ylk 属性
                    # 使用 CSS Selector 定位下拉按钮
                    date_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-ylk*='slk:date-select']")))
                    date_button.click()
                    time.sleep(1) # 稍等下拉菜单动画
                    
                    # 获取下拉菜单里的所有选项
                    # 根据 HTML: <div class="itm ..." data-value="1766707200">...</div>
                    options_elements = driver.find_elements(By.CSS_SELECTOR, "div.dialog-content div.itm")
                    
                    for opt in options_elements:
                        ts = opt.get_attribute("data-value")
                        # 文本通常直接在 div 里，或者需要进一步提取
                        # 你的 HTML 例子: "Dec 26, 2025" 就在 div 的 text 里
                        raw_text = opt.text.split('\n')[0] # 有时候会有 check 图标的文本，取第一部分
                        if ts and raw_text:
                            date_map.append((ts, raw_text))
                            
                    print(f"原始找到 {len(date_map)} 个到期日。")
                    
                except Exception as e:
                    print(f"获取日期列表失败 (可能只有一个日期或页面结构改变): {e}")
                    # 如果获取失败，尝试直接抓取当前页面（默认日期）
                    date_map = [] 

                # --- 按6个月时间窗口过滤日期 ---
                if date_map:
                    filtered_date_map = []
                    start_dt = None
                    cutoff_dt = None

                    # 假设 date_map 是按时间顺序排列的（Yahoo通常是这样）
                    # 我们需要先解析第一个日期来确定基准
                    
                    # 1. 确定基准日期 (第一条有效日期)
                    try:
                        first_date_str = date_map[0][1]
                        start_dt = datetime.strptime(first_date_str, "%b %d, %Y")
                        # 往后推 180 天 (约6个月)
                        cutoff_dt = start_dt + timedelta(days=180)
                        print(f"时间过滤启动: 基准日期 {start_dt.strftime('%Y-%m-%d')}, 截止日期 {cutoff_dt.strftime('%Y-%m-%d')}")
                    except ValueError:
                        print("无法解析第一条日期格式，将不进行时间过滤，抓取所有日期。")
                        cutoff_dt = None

                    # 2. 遍历过滤
                    if cutoff_dt:
                        for ts, date_text in date_map:
                            try:
                                curr_dt = datetime.strptime(date_text, "%b %d, %Y")
                                if curr_dt <= cutoff_dt:
                                    filtered_date_map.append((ts, date_text))
                                else:
                                    # 因为列表通常是有序的，一旦超过，后面的肯定也超过，可以直接 break 提高效率
                                    # 但为了保险起见（万一乱序），这里用 continue 也可以，break 更快
                                    pass 
                            except ValueError:
                                # 如果解析失败，为了安全起见，保留该条目或跳过，这里选择跳过
                                continue
                        
                        print(f"过滤后剩余 {len(filtered_date_map)} 个到期日 (6个月内)。")
                        date_map = filtered_date_map

                # --- 第二步：遍历每个日期 ---
                # 如果没找到下拉菜单，可能只有默认的一个日期，尝试抓取当前页
                if not date_map:
                    # 尝试从当前按钮读取日期
                    try:
                        current_date_text = driver.find_element(By.CSS_SELECTOR, "button[data-ylk*='slk:date-select'] span").text
                        # 假设当前页面的 timestamp 不需要参数
                        date_map.append(("", current_date_text))
                    except:
                        print(f"无法确定 {symbol} 的日期，跳过。")
                        continue

                # --- 第二步：遍历每个日期 (包含重试机制) ---
                for ts, date_text in date_map:
                    formatted_date = format_date(date_text)
                    
                    # 构造目标 URL
                    target_url = base_url
                    if ts:
                        target_url = f"{base_url}?date={ts}"

                    # === 新增重试机制 ===
                    MAX_RETRIES = 3  # 最大重试次数
                    success = False
                    
                    for attempt in range(MAX_RETRIES):
                        try:
                            print(f"  -> [尝试 {attempt + 1}/{MAX_RETRIES}] 处理日期: {formatted_date} (TS: {ts})")
                            
                            # 只有当不是默认页面或者不是第一次加载时才跳转
                            # 为了保证稳定性，即使是默认页，如果重试了也重新 get 一下
                            driver.get(target_url)
                            
                            # 稍微增加等待时间，确保表格渲染
                            # 如果是重试，等待时间可以稍微加长一点
                            sleep_time = 2 if attempt == 0 else 4
                            time.sleep(sleep_time) 
                            
                            # 检查页面是否真的加载了表格，如果找不到表格，抛出异常触发重试
                            # 使用 WebDriverWait 确保表格出现
                            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-testid='options-list-table'] table")))

                            # --- 第三步：抓取表格数据 ---
                            tables = driver.find_elements(By.CSS_SELECTOR, "section[data-testid='options-list-table'] table")
                            
                            if not tables:
                                raise Exception("页面已加载但未找到表格元素")

                            option_types = ['Calls', 'Puts']
                            data_buffer = []

                            for i, table in enumerate(tables):
                                if i >= len(option_types): break
                                opt_type = option_types[i]
                                rows = table.find_elements(By.TAG_NAME, "tr")
                                
                                for row in rows:
                                    cols = row.find_elements(By.TAG_NAME, "td")
                                    if not cols: continue
                                    
                                    if len(cols) >= 10:
                                        strike_raw = cols[2].text
                                        oi_raw = cols[9].text
                                        strike_clean = strike_raw.replace(',', '').strip()
                                        oi_clean = clean_number(oi_raw)
                                        data_buffer.append([symbol, formatted_date, opt_type, strike_clean, oi_clean])
                            
                            # --- 第四步：写入文件 ---
                            if data_buffer:
                                with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                                    writer = csv.writer(f)
                                    writer.writerows(data_buffer)
                                print(f"     成功抓取 {len(data_buffer)} 条数据。")
                            else:
                                print("     页面加载成功但无数据行。")

                            # 如果代码运行到这里没有报错，说明成功，跳出重试循环
                            success = True
                            break 

                        except Exception as e:
                            print(f"     [警告] 第 {attempt + 1} 次尝试失败: {e}")
                            if attempt < MAX_RETRIES - 1:
                                print("     等待 3 秒后重试...")
                                time.sleep(3)
                            else:
                                print(f"     [错误] 已达到最大重试次数，跳过日期 {formatted_date}。")
                    
                    if not success:
                        # 这里可以选择记录日志，或者只是简单跳过
                        pass
                    # =====================

            except Exception as e:
                print(f"处理 Symbol {symbol} 时发生严重错误: {e}")

    finally:
        driver.quit()
        print(f"所有任务完成。数据已保存至: {OUTPUT_FILE}")

if __name__ == "__main__":
    scrape_options()