import sqlite3
import time
import os
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tqdm import tqdm
import platform
import urllib.parse
from datetime import datetime, timedelta  # 确保添加此行导入

# ================= 配置区域 =================
USER_HOME = os.path.expanduser("~")

# 基础路径
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")

# 具体业务文件路径
DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
# 修改配置区域：先定义基础路径，文件名稍后动态决定
MODULES_DIR = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules")

# 默认文件名
SYMBOL_MAPPING_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping.json")

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

# 抓取时间范围参数
PERIOD_1 = "1039824000"  # 起始时间保持不变

# 动态计算 PERIOD_2 (昨天 23:59:59 的时间戳)
# 获取当前时间
now = datetime.now()
# 计算昨天的时间
yesterday = now - timedelta(days=1)
# 设置为昨天的 23:59:59 (确保包含全天数据)
yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)
# 转换为 Unix 时间戳并转为字符串
PERIOD_2 = str(int(yesterday_end.timestamp()))

print(f"🚀 抓取时间范围: {datetime.fromtimestamp(int(PERIOD_1)).date()} 至 {yesterday_end.date()}")

# ================= 1. 数据库与 JSON 操作 =================

def create_table_if_not_exists(cursor, table_name):
    """确保数据库表存在"""
    safe_table_name = f'"{table_name}"'
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {safe_table_name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        name TEXT,
        price REAL,
        volume INTEGER,
        open REAL,
        high REAL,
        low REAL,
        UNIQUE(date, name)
    );
    """
    cursor.execute(create_table_sql)

def insert_data_to_db(db_path, table_name, data_rows):
    """将抓取的数据直接写入数据库"""
    if not data_rows:
        return False
        
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    safe_table = f'"{table_name}"'
    
    try:
        create_table_if_not_exists(cursor, table_name)
        
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
        cursor.executemany(upsert_sql, data_rows)
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

def extract_data_via_js(driver, symbol):
    """使用注入 JS 的方式快速提取表格数据"""
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

    rows.forEach(r => {
        const cells = Array.from(r.querySelectorAll('td'));
        if (cells.length <= Math.max(cols.date, cols.close)) return;

        let rawDate = cells[cols.date].textContent.trim().split('::')[0].replace(/"/g, '');
        let d = new Date(rawDate);
        if (isNaN(d)) return;
        
        let dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        
        let price = parseFloat(cells[cols.close].textContent.trim().replace(/,/g, ''));
        if (isNaN(price)) return;

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
    });

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

def scrape_history(json_path):
    # 1. 加载任务和映射表
    tasks_dict = load_tasks_from_json(json_path)
    alias_to_symbol = load_alias_mapping(SYMBOL_MAPPING_PATH)
    
    # 将字典展平为列表，方便使用 tqdm
    task_list = []
    for group, symbols in tasks_dict.items():
        for sym in symbols:
            task_list.append((sym, group))
            
    if not task_list:
        tqdm.write("✅ JSON 文件中没有待抓取的 Symbol，任务结束。")
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
    wait = WebDriverWait(driver, 10)

    try:
        pbar = tqdm(task_list, desc="总体进度", position=0)
        
        for symbol, group in pbar:
            # 判断是否需要转译真实 Symbol 用于爬虫请求
            if group == "Crypto" and symbol in alias_to_symbol:
                scrape_symbol = alias_to_symbol[symbol]
                pbar.set_description(f"处理中: {symbol} (转译为 {scrape_symbol}) [{group}]")
            else:
                scrape_symbol = symbol
                pbar.set_description(f"处理中: {symbol} [{group}]")
            
            encoded_symbol = urllib.parse.quote(scrape_symbol)
            target_url = f"https://finance.yahoo.com/quote/{encoded_symbol}/history/?period1={PERIOD_1}&period2={PERIOD_2}"
            
            max_retries = 3
            success = False
            
            for attempt in range(max_retries):
                try:
                    driver.get(target_url)
                    
                    # 等待表格加载
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
                    time.sleep(1) # 缓冲等待 JS 渲染数据
                    
                    # 滚动页面以加载更多历史数据 (Yahoo History 是懒加载的)
                    # 如果只需要默认显示的行数，可以注释掉下面这个循环
                    for _ in range(3): 
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)
                    
                    # 提取数据 (这里传入原始的 symbol，如 "Bitcoin"，以保证写入数据库的 name 是 "Bitcoin")
                    data_rows = extract_data_via_js(driver, symbol)
                    
                    if not data_rows:
                        raise Exception("提取到的数据为空")
                        
                    # 写入数据库
                    if insert_data_to_db(DB_PATH, group, data_rows):
                        tqdm.write(f"[{symbol}] 成功写入 {len(data_rows)} 条数据到 {group} 表。")
                        # 成功后从 JSON 移除 (移除原始的 symbol)
                        remove_symbol_from_json(json_path, group, symbol)
                        success = True
                        break # 跳出重试循环
                    else:
                        raise Exception("数据库写入失败")
                        
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        tqdm.write(f"❌ [{symbol}] 抓取失败 (已重试 {max_retries} 次): {str(e)[:100]}")
            
    finally:
        driver.quit()
        tqdm.write("🎉 所有任务执行完毕。")

if __name__ == "__main__":
    # 直接指定使用 Sectors_empty.json
    target_json_path = os.path.join(MODULES_DIR, "Sectors_empty.json")
    
    print(f"🚀 正在使用配置文件: {target_json_path}")
    
    # 启动爬虫
    scrape_history(target_json_path)