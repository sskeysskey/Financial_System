from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException
from tqdm import tqdm
import os
import re
import json
import time
import random
import sqlite3
import argparse
import platform
import subprocess
import tempfile
import atexit
import pyperclip
import tkinter as tk
from tkinter import ttk, messagebox


def log(msg=""):
    """与 tqdm 进度条兼容的输出"""
    tqdm.write(str(msg))


# ================= 防止系统休眠控制 =================
_caffeinate_proc = None

def start_caffeinate():
    """启动 caffeinate 防休眠 (仅 macOS)。-w 绑定本进程 PID，即使脚本被强杀 caffeinate 也会自动退出"""
    global _caffeinate_proc
    if platform.system() != 'Darwin' or _caffeinate_proc:
        return
    try:
        _caffeinate_proc = subprocess.Popen(["caffeinate", "-idmu", "-w", str(os.getpid())])
        log(">>> [系统] 已开启防休眠模式 (caffeinate)")
    except Exception as e:
        log(f">>> [系统] 无法启动 caffeinate: {e}")

def stop_caffeinate():
    global _caffeinate_proc
    if _caffeinate_proc:
        try:
            _caffeinate_proc.terminate()
            _caffeinate_proc.wait(timeout=3)
            log(">>> [系统] 已关闭防休眠模式")
        except Exception as e:
            log(f">>> [系统] 关闭 caffeinate 时出错: {e}")
        finally:
            _caffeinate_proc = None

atexit.register(stop_caffeinate)

# ================= 配置区域 =================
USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")
NEWS_BACKUP_DIR = os.path.join(BASE_CODING_DIR, "News", "backup")

SECTORS_EMPTY_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_empty.json")
SECTORS_ALL_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_All.json")
SECTORS_TODAY_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_today.json")
SECTORS_HOLIDAY_JSON = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_US_holiday.json")
DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")

SHARES_FILENAME = "Shares.txt"
MARKETCAP_FILENAME = "marketcap_pe.txt"

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

TARGET_SECTORS = [
    'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
    'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
    'Communication_Services', 'Financial_Services', 'Healthcare'
]

INVALID_TOKENS = {'', 'N/A', '-', '--', 'None', 'null'}
MAX_RETRIES = 3
KEY_STATS_URL = "https://finance.yahoo.com/quote/{symbol}/key-statistics/"
QUOTE_URL = "https://finance.yahoo.com/quote/{symbol}/"

# ================= 通用解析工具 =================
def parse_number(text):
    """'1,234.5' -> 1234.5；无效值返回 None"""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace(',', '')
    if s in INVALID_TOKENS:
        return None
    try:
        return float(s)
    except ValueError:
        return None

def convert_shares_format(value_str):
    """'15.33B' -> 15330000000.0；支持 T/B/M/K 和纯数字，无效返回 0"""
    if value_str is None:
        return 0
    s = str(value_str).strip().replace(',', '')
    if s in INVALID_TOKENS:
        return 0
    m = re.match(r'^(-?\d+(?:\.\d+)?)\s*([TtBbMmKk]?)$', s)
    if not m:
        return 0
    multiplier = {'T': 1e12, 'B': 1e9, 'M': 1e6, 'K': 1e3, '': 1}[m.group(2).upper()]
    return float(m.group(1)) * multiplier

def format_marketcap(value):
    """保持原有浮点格式（如 2590000000.0），并消除浮点误差"""
    return str(float(round(value)))

# ================= JSON 工具 =================
def atomic_write_text(path, content):
    """先写临时文件再 os.replace，崩溃时不会留下半截文件"""
    d = os.path.dirname(path) or '.'
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.tmp_', dir=d)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_atomic(path, data):
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))

# ================= TXT 记录读写（与 Fix 脚本使用同一套有效性规则） =================
def parse_record_line(line):
    line = line.strip()
    if not line or ':' not in line:
        return None, None
    sym, rest = line.split(':', 1)
    return sym.strip(), [p.strip() for p in rest.split(',')]

def is_valid_shares_fields(fields):
    """Shares.txt: 'SYM: shares, pb'，shares 必须 > 0"""
    if not fields or len(fields) < 2:
        return False
    v = parse_number(fields[0])
    return v is not None and v > 0

def is_valid_marketcap_fields(fields):
    """marketcap_pe.txt: 'SYM: marketcap, pe, pb'，marketcap 必须 > 0"""
    if not fields or len(fields) < 3:
        return False
    v = parse_number(fields[0])
    return v is not None and v > 0

def load_record_status(path, validator):
    """返回 (有效 symbol 集合, 出现过的 symbol 集合)。重复出现的 symbol 视为无效（需要重写去重）"""
    counts, valid = {}, set()
    if not os.path.exists(path):
        return set(), set()
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            sym, fields = parse_record_line(line)
            if not sym:
                continue
            counts[sym] = counts.get(sym, 0) + 1
            if validator(fields):
                valid.add(sym)
    dup = {s for s, c in counts.items() if c > 1}
    return valid - dup, set(counts)

def upsert_record(path, symbol, line):
    """删除该 symbol 的所有旧行（含重复/损坏行），追加新行，原子写回"""
    kept = []
    if os.path.exists(path):
        with open(path, encoding='utf-8', errors='replace') as f:
            for raw in f:
                sym, _ = parse_record_line(raw)
                if sym == symbol:
                    continue
                if raw.strip():
                    kept.append(raw.rstrip('\r\n'))
    kept.append(line)
    atomic_write_text(path, '\n'.join(kept) + '\n')

def append_record(path, line):
    """追加一行；若文件末尾没有换行（上次崩溃写了半行），先补换行，避免两行粘连"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prefix = ''
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, 'rb') as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b'\n':
                prefix = '\n'
    with open(path, 'a', encoding='utf-8') as f:
        f.write(prefix + line + '\n')
        f.flush()
        os.fsync(f.fileno())

def build_target(paths, validator, always_upsert):
    valid, present = load_record_status(paths[0], validator)
    return {'paths': paths, 'valid': valid, 'present': present, 'always_upsert': always_upsert}

def write_to_target(target, symbol, line, is_valid):
    for p in target['paths']:
        if target['always_upsert'] or symbol in target['present']:
            upsert_record(p, symbol, line)
        else:
            append_record(p, line)
    target['present'].add(symbol)
    if is_valid:
        target['valid'].add(symbol)
    else:
        target['valid'].discard(symbol)

def get_repair_paths(filename):
    """
    修复模式写入目标：Downloads 和 backup 中所有已存在的副本都更新。
    （Fix 脚本最后会用 Downloads 的文件覆盖 backup，只写 backup 会导致数据被覆盖丢失）
    两处都没有时，写到 Downloads。第一个路径作为状态判断的主文件（与 Fix 的查找顺序一致）。
    """
    candidates = [os.path.join(DOWNLOADS_DIR, filename), os.path.join(NEWS_BACKUP_DIR, filename)]
    existing = [p for p in candidates if os.path.exists(p)]
    return existing or [candidates[0]]

# ================= 数据库 =================
def create_db_connection(db_file):
    try:
        conn = sqlite3.connect(db_file, timeout=60.0)
        conn.row_factory = sqlite3.Row
        log("成功连接到数据库。")
        return conn
    except sqlite3.Error as e:
        log(f"数据库连接错误: {e}")
        show_alert(f"数据库连接错误: {e}")
        return None

def get_stock_from_db(conn, symbol):
    cur = conn.cursor()
    cur.execute("SELECT * FROM MNSPP WHERE upper(symbol) = ?", (symbol.upper(),))
    return cur.fetchone()

def should_update_field(db_value, scraped_value):
    """
    抓取值无效(空/0/--)不更新；数据库值无效则更新；两者都有效但不同（相对误差）则更新。
    返回 (是否更新, 新值)
    """
    new_val = parse_number(scraped_value)
    if new_val is None or new_val == 0:
        return False, None
    old_val = parse_number(db_value)
    if old_val is None or old_val == 0:
        return True, new_val
    if abs(old_val - new_val) > 1e-9 * max(1.0, abs(old_val)):
        return True, new_val
    return False, None

def update_stock_in_db(conn, symbol, res, db_record):
    updates, params = [], []
    for col, key, as_int in (('shares', 'shares', True), ('marketcap', 'marketcap', False),
                             ('pe_ratio', 'pe', False), ('pb', 'pb', False)):
        need, new_val = should_update_field(db_record[col], res[key])
        if need:
            updates.append(f"{col} = ?")
            params.append(int(new_val) if as_int else new_val)
    if not updates:
        log(f"数据库中 {symbol} 的数据已是最新，无需更新。")
        return True
    try:
        sql = f"UPDATE MNSPP SET {', '.join(updates)} WHERE upper(symbol) = ?"
        params.append(symbol.upper())
        conn.execute(sql, tuple(params))
        conn.commit()
        log(f"已更新数据库中 {symbol} 的记录: {', '.join(u.split(' ')[0] for u in updates)}")
        return True
    except sqlite3.Error as e:
        log(f"更新数据库中 {symbol} 的记录时出错: {e}")
        return False

def _positive_or_none(v):
    n = parse_number(v)
    return n if (n is not None and n > 0) else None

def insert_stock_into_db(conn, symbol, res):
    shares = _positive_or_none(res['shares'])
    try:
        conn.execute(
            "INSERT INTO MNSPP(symbol, shares, marketcap, pe_ratio, pb) VALUES(?,?,?,?,?)",
            (symbol,
             int(shares) if shares else None,
             _positive_or_none(res['marketcap']),
             parse_number(res['pe']),
             parse_number(res['pb'])))
        conn.commit()
        log(f"已将新symbol {symbol} 插入到数据库。")
        return True
    except sqlite3.Error as e:
        log(f"向数据库插入 {symbol} 时出错: {e}")
        return False

def sync_db(conn, symbol, res, new_db_symbols):
    try:
        record = get_stock_from_db(conn, symbol)
    except sqlite3.Error as e:
        log(f"从数据库查询 {symbol} 时出错: {e}")
        return False
    if record:
        return update_stock_in_db(conn, symbol, res, record)
    log(f"注意：新Symbol '{symbol}' 在数据库中未找到，将添加新记录。")
    ok = insert_stock_into_db(conn, symbol, res)
    if ok:
        new_db_symbols.append(symbol)
    return ok

# ================= 系统交互 / UI =================
def _escape_applescript(s):
    return str(s).replace('\\', '\\\\').replace('"', '\\"')

def show_alert(message):
    if platform.system() == 'Darwin':
        try:
            code = f'display dialog "{_escape_applescript(message)}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', code], check=False)
        except Exception:
            pass
    else:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("提示", message)
        root.destroy()

def Copy_Command_C():
    if platform.system() == 'Darwin':
        script = 'tell application "System Events" to keystroke "c" using command down'
        subprocess.run(['osascript', '-e', script])
        time.sleep(0.1)
    else:
        import pyautogui
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.1)

def show_input_dialog(default_symbol=""):
    result = {'symbol': ''}
    root = tk.Tk()
    root.title("输入Symbol")
    root.geometry("400x150")
    root.lift()
    root.focus_force()
    root.attributes('-topmost', True)

    tk.Label(root, text="请输入Stock Symbol:").pack(pady=10)
    entry = tk.Entry(root)
    entry.pack(pady=5)
    if default_symbol:
        entry.insert(0, default_symbol)
    entry.focus_set()

    def on_ok(event=None):
        result['symbol'] = entry.get().strip().upper()
        root.destroy()

    def on_cancel(event=None):
        root.destroy()

    root.bind('<Return>', on_ok)
    root.bind('<Escape>', on_cancel)
    frame = tk.Frame(root)
    frame.pack(pady=20)
    tk.Button(frame, text="确定", command=on_ok).pack(side=tk.LEFT, padx=10)
    tk.Button(frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=10)
    root.mainloop()
    return result['symbol']

def show_group_selection_dialog(groups):
    selected = {'group': ''}
    root = tk.Tk()
    root.title("请选择分组")
    root.geometry("300x120")
    root.resizable(False, False)
    root.attributes('-topmost', True)
    tk.Label(root, text="在下拉列表中选择一个分组：").pack(pady=(10, 5))
    combo = ttk.Combobox(root, values=groups, state='readonly')
    combo.pack(pady=5, padx=10, fill='x')
    if groups:
        combo.current(0)

    def on_ok():
        selected['group'] = combo.get().strip()
        root.destroy()

    frame = tk.Frame(root)
    frame.pack(pady=(10, 5))
    tk.Button(frame, text="确定", width=10, command=on_ok).pack(side='left', padx=5)
    tk.Button(frame, text="取消", width=10, command=root.destroy).pack(side='left', padx=5)
    root.mainloop()
    return selected['group']

def parse_arguments():
    parser = argparse.ArgumentParser(description='股票数据抓取工具')
    parser.add_argument('--mode', type=str, default='normal', help='运行模式: normal 或 empty')
    parser.add_argument('--clear', action='store_true',
                        help='结束后从 Sectors_empty.json 移除已成功修复的 symbol（失败的保留）')
    return parser.parse_args()

# ================= Sectors JSON =================
def check_empty_json_has_content(json_file_path):
    data = load_json(json_file_path, {}) or {}
    return any(data.get(g) for g in data)

def get_stock_symbols_from_json(json_file_path):
    data = load_json(json_file_path, {}) or {}
    seen, out = set(), []
    for sector in TARGET_SECTORS:
        for s in data.get(sector, []) or []:
            s = str(s).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out

def add_symbol_to_json_files(symbol, group):
    for file_path in [SECTORS_EMPTY_JSON, SECTORS_ALL_JSON, SECTORS_TODAY_JSON]:
        data = load_json(file_path, {}) or {}
        data.setdefault(group, [])
        if symbol not in data[group]:
            data[group].append(symbol)
        save_json_atomic(file_path, data)

def get_group_for_symbol(symbol):
    data = load_json(SECTORS_ALL_JSON, {}) or {}
    for group, symbols in data.items():
        if symbol.upper() in (s.upper() for s in symbols):
            return group
    return None

def extract_group_names():
    return list((load_json(SECTORS_ALL_JSON, {}) or {}).keys())

def finalize_empty_json(succeeded):
    """
    只从目标板块中移除成功修复的 symbol；失败/未处理的保留，方便再次修复。
    非目标分组本脚本不处理，沿用原逻辑直接清空。
    """
    data = load_json(SECTORS_EMPTY_JSON, None)
    if not isinstance(data, dict):
        return 0
    remaining = 0
    for g in list(data.keys()):
        if g in TARGET_SECTORS:
            data[g] = [s for s in (data[g] or []) if s not in succeeded]
            remaining += len(data[g])
        else:
            data[g] = []
    save_json_atomic(SECTORS_EMPTY_JSON, data)
    log(f"Sectors_empty.json 已更新：移除 {len(succeeded)} 个已修复 symbol，剩余 {remaining} 个待修复。")
    return remaining

# ================= 浏览器 & 抓取 =================
def build_driver():
    opts = Options()
    if os.path.exists(CHROME_BINARY_PATH):
        opts.binary_location = CHROME_BINARY_PATH
    else:
        log(f"警告：未找到指定 Chrome 路径 {CHROME_BINARY_PATH}，尝试使用系统默认...")
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.page_load_strategy = 'eager'

    if not os.path.exists(CHROME_DRIVER_PATH):
        log(f"错误：未找到驱动文件: {CHROME_DRIVER_PATH}")
        return None
    try:
        driver = webdriver.Chrome(service=Service(executable_path=CHROME_DRIVER_PATH), options=opts)
        driver.set_page_load_timeout(20)
        driver.set_script_timeout(20)
        return driver
    except Exception as e:
        log(f"Selenium 启动失败: {e}")
        return None

class DriverManager:
    """管理浏览器实例，会话崩溃时自动重建"""
    def __init__(self):
        self.driver = None

    def start(self):
        self.quit()
        self.driver = build_driver()
        return self.driver is not None

    def is_alive(self):
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    def ensure_alive(self):
        if not self.is_alive():
            log("⚠️ 浏览器会话不可用，正在重建...")
            if not self.start():
                raise RuntimeError("浏览器重建失败")

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

READY_STATS_JS = r"""
for (const td of document.querySelectorAll('td')) {
  const t = (td.textContent || '').trim();
  if (t.startsWith('Shares Outstanding') || t.startsWith('Market Cap')) return true;
}
return false;
"""

STATS_JS = r"""
const out = {};
document.querySelectorAll('tr').forEach(tr => {
  const cells = tr.querySelectorAll('td, th');
  if (cells.length < 2) return;
  const label = (cells[0].textContent || '').replace(/\s+/g, ' ').trim();
  const value = (cells[1].textContent || '').replace(/\s+/g, ' ').trim();
  if (label && !(label in out)) out[label] = value;
});
return out;
"""

READY_QUOTE_JS = r"""
return !!document.querySelector('fin-streamer[data-field="marketCap"], [data-testid="quote-statistics"]');
"""

PRICE_JS = r"""
const sym = arguments[0];
const pick = el => el ? ((el.textContent || '').trim() || el.getAttribute('data-value') || '') : '';
let v = pick(document.querySelector('[data-testid="qsp-price"]'));
if (!v) v = pick(document.querySelector('fin-streamer[data-field="regularMarketPrice"][data-symbol="' + sym + '"]'));
return v;
"""

QUOTE_MC_JS = r"""
const sym = arguments[0];
const pick = el => el ? ((el.textContent || '').trim() || el.getAttribute('data-value') || '') : '';
let v = pick(document.querySelector('fin-streamer[data-field="marketCap"][data-symbol="' + sym + '"]'))
     || pick(document.querySelector('fin-streamer[data-field="marketCap"]'));
if (v) return v;
for (const li of document.querySelectorAll('li')) {
  const label = li.querySelector('.label, span');
  if (label && /^Market Cap/i.test((label.textContent || '').trim())) {
    const val = li.querySelector('.value');
    if (val) return (val.textContent || '').trim();
  }
}
return '';
"""

def load_page(driver, url, ready_js, timeout=10):
    """加载页面；加载超时时停止加载并继续用已渲染的内容"""
    try:
        driver.get(url)
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
    try:
        WebDriverWait(driver, timeout).until(lambda d: d.execute_script(ready_js))
        return True
    except TimeoutException:
        return False

def find_stat(stats, prefix):
    p = prefix.lower()
    for label, value in stats.items():
        if label.lower().startswith(p):
            return value
    return None

def empty_result():
    return {'shares': 0, 'shares_absent': False, 'pb': '--', 'marketcap': 0,
            'pe': '--', 'price': 0, 'mc_source': None}

def merge_results(best, cur):
    """多次尝试的结果合并：保留任意一次拿到的有效值"""
    out = dict(best)
    if cur['shares'] > 0:
        out['shares'] = cur['shares']
    out['shares_absent'] = best['shares_absent'] or cur['shares_absent']
    if out['shares'] > 0:
        out['shares_absent'] = False
    if cur['marketcap'] > 0:
        out['marketcap'], out['mc_source'] = cur['marketcap'], cur['mc_source']
    if cur['price'] > 0:
        out['price'] = cur['price']
    for k in ('pb', 'pe'):
        if cur[k] != '--':
            out[k] = cur[k]
    return out

def scrape_symbol(driver, symbol):
    res = empty_result()

    # 1) key-statistics 页面：一次 JS 取出全部表格数据（替代原先逐字段等待）
    load_page(driver, KEY_STATS_URL.format(symbol=symbol), READY_STATS_JS)
    stats = driver.execute_script(STATS_JS) or {}

    raw_shares = find_stat(stats, 'Shares Outstanding')
    res['shares'] = convert_shares_format(raw_shares)
    # 标签存在但值为 --/N/A：页面确认没有该数据（区别于页面没加载出来的 None）
    res['shares_absent'] = raw_shares is not None and res['shares'] <= 0
    pb = parse_number(find_stat(stats, 'Price/Book'))
    if pb is not None:
        res['pb'] = str(pb)
    pe = parse_number(find_stat(stats, 'Trailing P/E'))
    if pe is not None:
        res['pe'] = str(pe)
    mc = convert_shares_format(find_stat(stats, 'Market Cap'))
    if mc > 0:
        res['marketcap'], res['mc_source'] = mc, 'key-statistics'
    price = parse_number(driver.execute_script(PRICE_JS, symbol))
    if price and price > 0:
        res['price'] = price

    # 2) 市值兜底：quote 主页面的 Market Cap (intraday)（新股/分拆股估值表常为 --）
    if res['marketcap'] <= 0:
        load_page(driver, QUOTE_URL.format(symbol=symbol), READY_QUOTE_JS)
        mc = convert_shares_format(driver.execute_script(QUOTE_MC_JS, symbol))
        if mc > 0:
            res['marketcap'], res['mc_source'] = mc, 'quote'
        if res['price'] <= 0:
            price = parse_number(driver.execute_script(PRICE_JS, symbol))
            if price and price > 0:
                res['price'] = price
    return res

def scrape_with_retries(dm, symbol, max_retries=MAX_RETRIES):
    best = empty_result()
    for attempt in range(max_retries):
        if attempt > 0:
            log(f"正在重试 {symbol} (第 {attempt + 1}/{max_retries} 次)...")
            time.sleep(random.uniform(2, 4))
        try:
            dm.ensure_alive()
            best = merge_results(best, scrape_symbol(dm.driver, symbol))
            if best['shares'] > 0 and best['marketcap'] > 0:
                break
            if best['shares_absent'] and best['marketcap'] > 0:
                log(f"{symbol} 页面确认无 Shares Outstanding，不再重试")
                break
            log(f"尝试 {attempt + 1}: {symbol} 数据不完整 (shares={best['shares']}, marketcap={best['marketcap']})")
        except WebDriverException as e:
            log(f"尝试 {attempt + 1} 抓取 {symbol} 时浏览器出错: {str(e).splitlines()[0] if str(e) else e}")
        except RuntimeError:
            raise
        except Exception as e:
            log(f"尝试 {attempt + 1} 抓取 {symbol} 时发生错误: {e}")

    # 3) 最终兜底：价格 × 股本 推算市值
    if best['marketcap'] <= 0 and best['shares'] > 0 and best['price'] > 0:
        best['marketcap'] = best['shares'] * best['price']
        best['mc_source'] = 'computed'
        log(f"⚠️ {symbol} 页面无市值，已用 价格({best['price']}) × 股本({int(best['shares'])}) 推算")
    return best

# ================= 主流程 =================
SYMBOL_RE = re.compile(r'^[A-Z0-9.\-^=]{1,15}$')

def prepare_single_symbol():
    """empty.json 为空时：从剪贴板/输入框获取单个 symbol 并写入分组。返回 symbol 或 None"""
    Copy_Command_C()
    clip = (pyperclip.paste() or "").strip().upper()
    symbol = clip if SYMBOL_RE.match(clip) else show_input_dialog(default_symbol="").strip().upper()
    if not symbol:
        log("未输入有效的股票Symbol，程序退出")
        return None

    group = get_group_for_symbol(symbol)
    if not group:
        show_alert(f"在 Sectors_All.json 中未找到 {symbol} 对应的分组，请手动选择。")
        group = show_group_selection_dialog(extract_group_names())
        if not group:
            show_alert("未选择分组，程序退出")
            return None
    if group not in TARGET_SECTORS:
        show_alert(f"{symbol} 属于分组 {group}，不在本脚本处理的板块范围内，不会被抓取。")
    add_symbol_to_json_files(symbol, group)
    log(f"已将 {symbol} 匹配到 {group} 分组并写入 Sectors_empty.json")
    return symbol

def main():
    args = parse_arguments()
    repair_mode = args.mode.lower() == 'empty'
    start_caffeinate()

    if repair_mode:
        if not check_empty_json_has_content(SECTORS_EMPTY_JSON):
            if not prepare_single_symbol():
                stop_caffeinate()
                return
        json_file_path = SECTORS_EMPTY_JSON
        shares_target = build_target(get_repair_paths(SHARES_FILENAME), is_valid_shares_fields, True)
        mc_target = build_target(get_repair_paths(MARKETCAP_FILENAME), is_valid_marketcap_fields, True)
        log(f"修复模式：强制重抓 Sectors_empty.json 中的 symbol，写入：{shares_target['paths'] + mc_target['paths']}")
    else:
        json_file_path = SECTORS_ALL_JSON
        shares_target = build_target([os.path.join(DOWNLOADS_DIR, SHARES_FILENAME)], is_valid_shares_fields, False)
        mc_target = build_target([os.path.join(DOWNLOADS_DIR, MARKETCAP_FILENAME)], is_valid_marketcap_fields, False)
        log("使用正常模式和Downloads目录（已完整的 symbol 自动跳过，不完整的会重抓并替换）...")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db_conn = create_db_connection(DB_PATH)
    if not db_conn:
        stop_caffeinate()
        return

    dm = DriverManager()
    if not dm.start():
        db_conn.close()
        stop_caffeinate()
        return

    stock_symbols = get_stock_symbols_from_json(json_file_path)
    succeeded, failed, computed_mc, new_db_symbols = set(), {}, [], []
    skipped = processed = 0

    try:
        for symbol in tqdm(stock_symbols, desc="Processing symbols", unit="sym"):
            # 正常模式断点续跑：两份文件都有效才跳过（不再逐个弹窗）
            if not repair_mode and symbol in shares_target['valid'] and symbol in mc_target['valid']:
                skipped += 1
                continue

            processed += 1
            try:
                res = scrape_with_retries(dm, symbol)
            except RuntimeError as e:
                log(f"❌ 浏览器不可用，终止抓取: {e}")
                failed[symbol] = "浏览器不可用"
                break

            shares_ok = res['shares'] > 0
            shares_absent = res['shares_absent'] and not shares_ok
            mc_ok = res['marketcap'] > 0
            pb_ok = res['pb'] != '--'
            log(f"{symbol}: shares={int(res['shares'])}, marketcap={res['marketcap']:.0f}"
                f"({res['mc_source']}), pe={res['pe']}, pb={res['pb']}")
            if res['mc_source'] == 'computed':
                computed_mc.append(symbol)

            try:
                if shares_ok:
                    write_to_target(shares_target, symbol,
                                    f"{symbol}: {int(res['shares'])}, {res['pb']}", True)
                    log(f"已保存 {symbol} 的Shares和Price/Book")
                elif (shares_absent or pb_ok) and symbol not in shares_target['valid']:
                    # 页面确认无股本：写 0。is_valid=False 使正常模式下次仍会重抓，
                    # 拿到真实数据时自动覆盖；若已有有效数据则保留旧值
                    write_to_target(shares_target, symbol,
                                    f"{symbol}: 0, {res['pb']}", False)
                    log(f"{symbol} 无 Shares Outstanding，按 0 记录")
                if mc_ok:
                    write_to_target(mc_target, symbol,
                                    f"{symbol}: {format_marketcap(res['marketcap'])}, {res['pe']}, {res['pb']}", True)
                    log(f"已保存 {symbol} 的市值和PE")
            except OSError as e:
                log(f"写入 txt 失败 {symbol}: {e}")

            db_ok = True
            if shares_ok or mc_ok or pb_ok or res['pe'] != '--':
                db_ok = sync_db(db_conn, symbol, res, new_db_symbols)

            shares_done = shares_ok or shares_absent or symbol in shares_target['valid']
            mc_done = mc_ok or symbol in mc_target['valid']
            if shares_done and mc_done and db_ok:
                succeeded.add(symbol)
            else:
                reasons = []
                if not shares_done:
                    reasons.append("无股本")
                if not mc_done:
                    reasons.append("无市值")
                if not db_ok:
                    reasons.append("数据库写入失败")
                failed[symbol] = "/".join(reasons)
                log(f"❌ {symbol} 未完全修复: {failed[symbol]}")

            time.sleep(random.uniform(1, 2))

    except KeyboardInterrupt:
        log("用户中断。")
    finally:
        dm.quit()
        try:
            db_conn.close()
            log("数据库连接已关闭。")
        except Exception:
            pass
        stop_caffeinate()

        if repair_mode and args.clear:
            try:
                finalize_empty_json(succeeded)
            except Exception as e:
                log(f"更新 Sectors_empty.json 失败: {e}")

        summary = [f"处理 {processed}，成功 {len(succeeded)}，跳过 {skipped}，失败 {len(failed)}"]
        if computed_mc:
            summary.append("市值由价格×股本推算: " + ", ".join(computed_mc[:20]))
        if new_db_symbols:
            summary.append("数据库新增: " + ", ".join(new_db_symbols[:20]))
        if failed:
            items = [f"{s}({r})" for s, r in list(failed.items())[:20]]
            summary.append("失败(保留在待修复列表): " + ", ".join(items))
        msg = "\n".join(summary)
        log("数据抓取完成！\n" + msg)
        if repair_mode or failed or new_db_symbols:
            show_alert(msg)

if __name__ == "__main__":
    main()