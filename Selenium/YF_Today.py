import sqlite3
import time
import os
import sys
import json
import datetime
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tqdm import tqdm
import platform
import urllib.parse
import pandas_market_calendars as mcal

# ================= 配置区域 =================
USER_HOME = os.path.expanduser("~")

# 基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")

# 具体业务文件路径
DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
SECTORS_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_empty.json")
SYMBOL_MAPPING_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping.json") # 新增映射文件路径
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

# 浏览器与驱动路径 (跨平台适配)
if platform.system() == 'Darwin':
    CHROME_BINARY_PATH = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver_beta")
elif platform.system() == 'Windows':
    CHROME_BINARY_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(CHROME_BINARY_PATH):
        CHROME_BINARY_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    CHROME_DRIVER_PATH = os.path.join(DOWNLOADS_DIR, "backup", "chromedriver.exe")
else:
    CHROME_BINARY_PATH = "/usr/bin/google-chrome"
    CHROME_DRIVER_PATH = "/usr/bin/chromedriver"

# ================= 1. 数据库与 JSON 操作 =================

def get_table_type(sector):
    """根据分组判断表结构类型"""
    expanded_sectors = [
        'ETFs', 'Basic_Materials', 'Communication_Services', 'Consumer_Cyclical', 
        'Consumer_Defensive', 'Energy', 'Financial_Services', 'Healthcare', 
        'Industrials', 'Real_Estate', 'Technology', 'Utilities', 'Crypto'
    ]
    no_volume_sectors = ['Bonds', 'Currencies', 'Commodities', 'Economics']
    
    if sector in expanded_sectors:
        return "expanded"
    elif sector in no_volume_sectors:
        return "no_volume"
    else:
        return "standard" # 例如 Indices

def create_table_if_not_exists(cursor, table_name, table_type):
    """确保数据库表存在，根据 table_type 动态创建表结构"""
    safe_table_name = f'"{table_name}"'
    
    if table_type == "expanded":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT,
            name TEXT,
            price REAL,
            volume INTEGER,
            open REAL,
            high REAL,
            low REAL,
            UNIQUE(date, name)
        )
        ''')
    elif table_type == "no_volume":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT,
            name TEXT,
            price REAL,
            UNIQUE(date, name)
        )
        ''')
    else: # standard
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT,
            name TEXT,
            price REAL,
            volume INTEGER,
            UNIQUE(date, name)
        )
        ''')

def insert_data_to_db(db_path, table_name, data_rows, table_type):
    """将抓取的数据直接写入数据库，根据 table_type 过滤字段并执行对应的 SQL"""
    if not data_rows:
        return False
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    safe_table = f'"{table_name}"'
    try:
        create_table_if_not_exists(cursor, table_name, table_type)
        
        # 根据 table_type 准备数据和 SQL
        filtered_data = []
        if table_type == "expanded":
            # data_rows 原本就是 (date, name, price, volume, open, high, low)
            filtered_data = data_rows
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price, volume, open, high, low)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price = excluded.price,
                volume = excluded.volume,
                open = excluded.open,
                high = excluded.high,
                low = excluded.low;
            """
        elif table_type == "no_volume":
            # 只取前 3 个字段: date, name, price
            filtered_data = [(row[0], row[1], row[2]) for row in data_rows]
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price)
            VALUES (?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price = excluded.price;
            """
        else: # standard
            # 只取前 4 个字段: date, name, price, volume
            filtered_data = [(row[0], row[1], row[2], row[3]) for row in data_rows]
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price, volume)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price = excluded.price,
                volume = excluded.volume;
            """
            
        cursor.executemany(upsert_sql, filtered_data)
        conn.commit()
        return True
    except sqlite3.Error as e:
        tqdm.write(f"❌ 数据库写入失败 ({table_name}): {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def load_tasks_from_json(json_path):
    """从 JSON 加载待抓取任务"""
    if not os.path.exists(json_path):
        tqdm.write(f"⚠️ 未找到 JSON 文件: {json_path}")
        return {}
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        tqdm.write(f"⚠️ 读取 JSON 出错: {e}")
        return {}

def load_alias_mapping(json_path):
    """加载并反转 Symbol 映射表 (例如将 {"BTC-USD": "Bitcoin"} 转为 {"Bitcoin": "BTC-USD"})"""
    if not os.path.exists(json_path):
        tqdm.write(f"⚠️ 未找到映射文件: {json_path}")
        return {}
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
            # 反转字典：键为别名(Bitcoin)，值为真实代码(BTC-USD)
            return {v: k for k, v in mapping.items()}
    except Exception as e:
        tqdm.write(f"⚠️ 读取映射文件出错: {e}")
        return {}

def remove_symbol_from_json(json_path, group_name, symbol):
    """抓取成功后，从 JSON 中移除该 Symbol"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if group_name in data and symbol in data[group_name]:
            data[group_name].remove(symbol)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
    except Exception as e:
        tqdm.write(f"⚠️ 更新 JSON 失败 [{symbol}]: {e}")
    return False

# ================= 2. 核心抓取逻辑 =================

def get_last_valid_trading_date():
    """获取美股最近的一个有效开盘日（严格小于今天）"""
    nyse = mcal.get_calendar('NYSE')
    today = datetime.datetime.now().date()
    # 往前推15天，确保能覆盖到长假
    start_date = today - datetime.timedelta(days=15)
    
    # 获取这段时间内的所有交易日
    schedule = nyse.schedule(start_date=start_date, end_date=today)
    valid_days = schedule.index.date
    
    # 筛选出严格小于今天的日期
    past_days = [d for d in valid_days if d < today]
    
    if past_days:
        return past_days[-1].strftime('%Y-%m-%d')
    return None

def extract_data_via_js(driver, symbol):
    """使用注入 JS 的方式快速提取表格数据 (提取最新的前两条数据)"""
    js_script = """
    function getColumnIndices(table) {
        const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.textContent.trim());
        return {
            date: headers.indexOf('Date'),
            open: headers.findIndex(h => /0pen|Open/i.test(h)),
            high: headers.findIndex(h => /High/i.test(h)),
            low: headers.findIndex(h => /Low/i.test(h)),
            close: headers.findIndex(h => /Adj Close/i.test(h)),
            volume: headers.findIndex(h => /Volume/i.test(h))
        };
    }

    let tbl = document.querySelector('[data-testid="history-table"] table');
    if (!tbl) {
        const all = Array.from(document.querySelectorAll('table'));
        for (let t of all) {
            const ths = Array.from(t.querySelectorAll('thead th')).map(th => th.textContent.trim());
            if (ths.includes('Date') && ths.some(h => /Volume/i.test(h))) {
                tbl = t; break;
            }
        }
    }
    
    if (!tbl) return { error: "未找到数据表格" };

    const cols = getColumnIndices(tbl);
    if (cols.date < 0 || cols.close < 0) return { error: "表头解析失败" };

    const rows = Array.from(tbl.querySelectorAll('tbody tr'));
    const scraped = [];

    // 提取前两条有效数据
    for (let r of rows) {
        const cells = Array.from(r.querySelectorAll('td'));
        if (cells.length <= Math.max(cols.date, cols.close)) continue;

        let rawDate = cells[cols.date].textContent.trim().split('::')[0].replace(/"/g, '');
        let d = new Date(rawDate);
        if (isNaN(d)) continue;
        
        let dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        let price = parseFloat(cells[cols.close].textContent.trim().replace(/,/g, ''));
        if (isNaN(price)) continue;

        let volume = 0, open = null, high = null, low = null;
        if (cols.volume >= 0 && cells[cols.volume]) {
            let v = parseInt(cells[cols.volume].textContent.trim().replace(/,/g, ''), 10);
            if (!isNaN(v)) volume = v;
        }
        if (cols.open >= 0 && cells[cols.open]) {
            let o = parseFloat(cells[cols.open].textContent.trim().replace(/,/g, ''));
            if (!isNaN(o)) open = o;
        }
        if (cols.high >= 0 && cells[cols.high]) {
            let h = parseFloat(cells[cols.high].textContent.trim().replace(/,/g, ''));
            if (!isNaN(h)) high = h;
        }
        if (cols.low >= 0 && cells[cols.low]) {
            let l = parseFloat(cells[cols.low].textContent.trim().replace(/,/g, ''));
            if (!isNaN(l)) low = l;
        }

        scraped.push([dateStr, price, volume, open, high, low]);
        if (scraped.length >= 2) break; // 提取到最新的两条有效数据后退出循环
    }
    return { data: scraped };
    """
    result = driver.execute_script(js_script)
    if "error" in result:
        raise Exception(result["error"])
        
    # 格式化为数据库需要的格式: (date, name, price, volume, open, high, low)
    formatted_data = []
    for row in result["data"]:
        formatted_data.append((row[0], symbol, row[1], row[2], row[3], row[4], row[5]))
    return formatted_data

def scrape_history():
    # 1. 加载任务和映射表
    tasks_dict = load_tasks_from_json(SECTORS_JSON_PATH)
    alias_to_symbol = load_alias_mapping(SYMBOL_MAPPING_PATH)
    
    # 获取最近的有效开盘日
    last_valid_date = get_last_valid_trading_date()
    if last_valid_date:
        tqdm.write(f"📅 计算得出的最近有效开盘日为: {last_valid_date}")
    else:
        tqdm.write("⚠️ 无法计算最近有效开盘日，将使用网页原始日期。")
    
    # 将字典展平为列表，方便使用 tqdm
    task_list = []
    for group, symbols in tasks_dict.items():
        for sym in symbols:
            task_list.append((sym, group))
            
    if not task_list:
        tqdm.write("✅ JSON 文件中没有待抓取的 Symbol，任务结束。")
        # 如果一开始就为空，也直接执行 Check_yesterday
        run_check_yesterday_if_empty()
        return

    tqdm.write(f"共加载 {len(task_list)} 个待抓取任务。")

    # 2. 初始化 Selenium
    options = webdriver.ChromeOptions()
    if os.path.exists(CHROME_BINARY_PATH):
        options.binary_location = CHROME_BINARY_PATH

    options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    
    # --- 性能优化参数 ---
    options.add_argument("--disable-images")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.page_load_strategy = 'eager'

    service = Service(executable_path=CHROME_DRIVER_PATH)
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        tqdm.write(f"❌ Selenium 启动失败: {e}")
        return

    driver.set_page_load_timeout(30)
    wait = WebDriverWait(driver, 8) # 设置 8 秒超时

    try:
        pbar = tqdm(task_list, desc="总体进度", position=0)
        for symbol, group in pbar:
            # 获取当前分组的表类型
            table_type = get_table_type(group)
            
            # 判断是否需要转译真实 Symbol 用于爬虫请求
            # 无论什么分组，只要映射表里有这个 symbol，就进行转译
            if symbol in alias_to_symbol:
                scrape_symbol = alias_to_symbol[symbol]
                pbar.set_description(f"处理中: {symbol} (转译为 {scrape_symbol}) [{group}]")
            else:
                scrape_symbol = symbol
                pbar.set_description(f"处理中: {symbol} [{group}]")
            
            encoded_symbol = urllib.parse.quote(scrape_symbol)
            # 修改 URL：移除 period 参数，直接访问 history 默认页
            target_url = f"https://finance.yahoo.com/quote/{encoded_symbol}/history/"
            
            max_retries = 3
            success = False
            skip_symbol = False
            
            for attempt in range(max_retries):
                try:
                    driver.get(target_url)
                    
                    # 等待表格加载
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
                    
                    # 提取数据 (获取前两条)
                    data_rows = extract_data_via_js(driver, symbol)
                    if not data_rows:
                        raise Exception("提取到的数据为空")
                    
                    # ================= 日期校验逻辑 =================
                    selected_row = None
                    
                    if last_valid_date:
                        row0_date = data_rows[0][0]
                        row1_date = data_rows[1][0] if len(data_rows) > 1 else None
                        
                        # 规则1：如果最新一条日期与计算日期一致
                        if row0_date == last_valid_date:
                            # 检查第二条是否也一致
                            if row1_date == last_valid_date:
                                selected_row = data_rows[1]
                            else:
                                selected_row = data_rows[0]
                                
                        # 规则2：如果最新一条日期比计算日期大
                        elif row0_date > last_valid_date:
                            # 看第二条是否一致
                            if row1_date == last_valid_date:
                                selected_row = data_rows[1]
                            elif row1_date is None:
                                # 只有第一条，没有第二条，将第一条的日期修改为 last_valid_date
                                tqdm.write(f"⚠️ [{symbol}] 最新日期 {row0_date} 过大且无第二条数据，将日期修改为 {last_valid_date} 写入。")
                                row_list = list(data_rows[0])
                                row_list[0] = last_valid_date  # 替换日期
                                selected_row = tuple(row_list)
                            else:
                                # 新增规则：第二条也不匹配时，用第一条数据但修改日期为 last_valid_date
                                tqdm.write(f"⚠️ [{symbol}] 最新日期 {row0_date} 过大，第二条 {row1_date} 不匹配 {last_valid_date}，使用第一条数据并修改日期写入。")
                                row_list = list(data_rows[0])
                                row_list[0] = last_valid_date  # 替换日期
                                selected_row = tuple(row_list)
                                
                        # 规则3：如果最新一条日期比计算日期小
                        else: # row0_date < last_valid_date
                            # 【新增逻辑】检查第一条和第二条的日期是否相同
                            if row1_date == row0_date:
                                tqdm.write(f"⚠️ [{symbol}] 网页最新日期 {row0_date} < 预期日期 {last_valid_date}，但存在两条相同日期数据，取第二条完整数据并修改日期写入。")
                                row_list = list(data_rows[1])
                                row_list[0] = last_valid_date  # 强行替换为正确的日期
                                selected_row = tuple(row_list)
                            else:
                                tqdm.write(f"⚠️ [{symbol}] 网页最新日期 {row0_date} < 预期日期 {last_valid_date}，数据未更新，跳过。")
                                skip_symbol = True
                                break # 跳出重试循环，不再重试
                    else:
                        # 如果无法计算 last_valid_date，默认取第一条
                        selected_row = data_rows[0]
                    # ======================================================

                    if selected_row:
                        # 写入数据库（将选中的单行包装为列表传入）
                        if insert_data_to_db(DB_PATH, group, [selected_row], table_type):
                            tqdm.write(f"[{symbol}] 成功写入最新 1 条数据 ({selected_row[0]}) 到 {group} 表。")
                            remove_symbol_from_json(SECTORS_JSON_PATH, group, symbol)
                            success = True
                            break # 跳出重试循环
                        else:
                            raise Exception("数据库写入失败")
                        
                except Exception as e:
                    if skip_symbol:
                        break
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        tqdm.write(f"❌ [{symbol}] 抓取失败 (已重试 {max_retries} 次): {str(e)[:100]}")
            
    finally:
        driver.quit()
        tqdm.write("🎉 所有任务执行完毕。")

    # 9. 检查 JSON 是否为空，如果为空则调用子脚本 Check_yesterday
    run_check_yesterday_if_empty()

def run_check_yesterday_if_empty():
    """检查 JSON 文件是否已清空，如果清空则执行 Check_yesterday.py"""
    final_tasks = load_tasks_from_json(SECTORS_JSON_PATH)
    
    # 检查字典中所有的列表是否都为空
    is_empty = True
    if final_tasks:
        for group, symbols in final_tasks.items():
            if len(symbols) > 0:
                is_empty = False
                break
                
    if is_empty:
        print("✅ Sectors_empty.json 已全部清空，开始执行 Check_yesterday.py...")
        try:
            subprocess.run([sys.executable, CHECK_YESTERDAY_SCRIPT_PATH], check=True, capture_output=True, text=True, encoding='utf-8')
            print("✅ Check_yesterday.py 执行完毕。")
        except Exception as e:
            print(f"❌ 调用 Check_yesterday 出错: {e}")
    else:
        print("⚠️ Sectors_empty.json 中仍有未完成的任务，跳过执行 Check_yesterday.py。")

if __name__ == "__main__":
    # 获取当前日期 (0=周一, 1=周二, ..., 5=周六, 6=周日)
    today_num = datetime.datetime.now().weekday()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    today_str = weekdays[today_num]
    
    # # 逻辑：周二(1) 到 周六(5) 允许执行
    # if today_num in [1, 2, 3, 4, 5]:
    #     print(f"✅ 当前是 {today_str} (星期{today_num})，符合执行条件 (周二至周六)，开始任务...")
    scrape_history()
    # else:
    #     print(f"⚠️ 当前是 {today_str} (星期{today_num})，不符合执行条件 (周二至周六)，程序退出。")