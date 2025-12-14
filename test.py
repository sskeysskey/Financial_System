import sqlite3
import csv
import time
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

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
                driver.get(base_url)
                # 等待页面加载
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                # --- 第一步：获取所有日期选项 ---
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
                    
                    date_map = [] # 存储 (timestamp, date_text)
                    for opt in options_elements:
                        ts = opt.get_attribute("data-value")
                        # 文本通常直接在 div 里，或者需要进一步提取
                        # 你的 HTML 例子: "Dec 26, 2025" 就在 div 的 text 里
                        raw_text = opt.text.split('\n')[0] # 有时候会有 check 图标的文本，取第一部分
                        if ts and raw_text:
                            date_map.append((ts, raw_text))
                            
                    print(f"找到 {len(date_map)} 个到期日。")
                    
                except Exception as e:
                    print(f"获取日期列表失败 (可能只有一个日期或页面结构改变): {e}")
                    # 如果获取失败，尝试直接抓取当前页面（默认日期）
                    date_map = [] 

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

                for ts, date_text in date_map:
                    formatted_date = format_date(date_text)
                    print(f"  -> 处理日期: {formatted_date} (TS: {ts})")
                    
                    # 如果有 timestamp，构造 URL 跳转；如果是空字符串（默认页），不跳转
                    if ts:
                        target_url = f"{base_url}?date={ts}"
                        driver.get(target_url)
                        time.sleep(2) # 等待表格加载
                    
                    # --- 第三步：抓取表格数据 ---
                    # 页面通常有两个表格：Calls 和 Puts
                    # 根据你的 HTML，表格在 <section data-testid="options-list-table"> 下
                    # 里面有两个 table，第一个是 Calls，第二个是 Puts (通常如此，但也可能通过 header 判断)
                    
                    try:
                        tables = driver.find_elements(By.CSS_SELECTOR, "section[data-testid='options-list-table'] table")
                        
                        # 我们需要确认哪个是 Calls 哪个是 Puts
                        # 你的 HTML 显示 <h3 class="...">Calls</h3> 紧接着是表格
                        
                        option_types = ['Calls', 'Puts']
                        
                        # 遍历找到的表格 (通常就是两个)
                        for i, table in enumerate(tables):
                            if i >= len(option_types): break
                            
                            opt_type = option_types[i]
                            
                            # 获取所有行
                            rows = table.find_elements(By.TAG_NAME, "tr")
                            
                            data_buffer = []
                            
                            for row in rows:
                                # 跳过表头 (th)
                                cols = row.find_elements(By.TAG_NAME, "td")
                                if not cols:
                                    continue
                                
                                # 根据你的描述：
                                # Strike 是第 3 列 (索引 2)
                                # Open Interest 是第 10 列 (索引 9)
                                # 你的 HTML 表头: Contract Name, Last Trade Date, Strike, Last Price, Bid, Ask, Change, % Change, Volume, Open Interest
                                
                                if len(cols) >= 10:
                                    strike_raw = cols[2].text
                                    oi_raw = cols[9].text
                                    
                                    strike_val = clean_number(strike_raw) # Strike 也可能是带逗号的数字，虽然通常是小数
                                    # Strike 实际上通常保留原样或者转 float，这里为了保险按 float 处理再转 string
                                    # 但你的 CSV 样例里 Strike 是 40, 66 等。
                                    # 简单处理：去除逗号即可
                                    strike_clean = strike_raw.replace(',', '').strip()
                                    
                                    oi_clean = clean_number(oi_raw)
                                    
                                    data_buffer.append([symbol, formatted_date, opt_type, strike_clean, oi_clean])
                            
                            # --- 第四步：写入文件 (追加模式) ---
                            with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                                writer = csv.writer(f)
                                writer.writerows(data_buffer)
                                
                    except Exception as e:
                        print(f"  抓取表格数据出错: {e}")

            except Exception as e:
                print(f"处理 Symbol {symbol} 时发生错误: {e}")

    finally:
        driver.quit()
        print(f"所有任务完成。数据已保存至: {OUTPUT_FILE}")

if __name__ == "__main__":
    scrape_options()