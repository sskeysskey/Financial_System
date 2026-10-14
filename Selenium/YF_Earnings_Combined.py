import os
import re
import shutil
import json
import time
import random
import subprocess
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta, date
import platform

# 第三方模块
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# Playwright 依赖 (用于 Part C)
from playwright.sync_api import sync_playwright

# ================= 配置区域 (跨平台) =================

USER_HOME = os.path.expanduser("~")

BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
NEWS_DIR = os.path.join(BASE_CODING_DIR, "News")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")

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

SECTORS_ALL_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, 'Modules', 'Sectors_All.json')
SECTORS_PANEL_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, 'Modules', 'Sectors_panel.json')
SYMBOL_MAPPING_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, 'Modules', 'Symbol_mapping.json')
POLYMARKET_FILE_PATH = os.path.join(NEWS_DIR, "earning_polymarket.txt")

BACKUP_ROOT_DIR = os.path.join(NEWS_DIR, 'backup', 'backup')
EARNINGS_ARCHIVE_PATH = os.path.join(NEWS_DIR, 'backup', 'Earnings_Release.txt')
ECONOMIC_ARCHIVE_PATH = os.path.join(NEWS_DIR, 'backup', 'Economic_Events.txt')
EARNINGS_DIFF_EXPIRED_PATH = os.path.join(BACKUP_ROOT_DIR, 'Earnings_Release_diff_expired.txt')

# 分组顺序 = 相对本周的周偏移 (new=0, next=1, ...)
EARNINGS_GROUPS = ['new', 'next', 'third', 'fourth', 'fifth']
ECONOMIC_GROUPS = ['new', 'next']

def earnings_file(group):
    return os.path.join(NEWS_DIR, f'Earnings_Release_{group}.txt')

def earnings_diff_file(group):
    return os.path.join(NEWS_DIR, f'Earnings_Release_diff_{group}.txt')

def economic_file(group):
    return os.path.join(NEWS_DIR, f'Economic_Events_{group}.txt')

# 不在 fifth 轮次收录的股票黑名单（可随时扩充）
EXCLUDE_FROM_FIFTH = {"HDB", "IBN", "BRK-B"}

# 经济事件过滤器
EVENT_FILTER_BASES = {
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

# 整个运行过程统一使用启动时的日期，避免跨午夜导致周归属前后不一致
RUN_TODAY = datetime.now().date()

# ================= 通用工具函数 =================

DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2})')

def week_start(d: date) -> date:
    """返回 d 所在周的周日（周日~周六为一周，周日属于其后的那个周一所在周）"""
    return d - timedelta(days=(d.weekday() + 1) % 7)

def week_index_of(d: date, today: date = None) -> int:
    """d 相对 today 所在周的周偏移：<0 已过期，0 本周(new)，1 下周(next)..."""
    today = today or RUN_TODAY
    return (week_start(d) - week_start(today)).days // 7

def extract_date(line: str, use_last: bool = True):
    found = DATE_RE.findall(line)
    if not found:
        return None
    try:
        return datetime.strptime(found[-1] if use_last else found[0], '%Y-%m-%d').date()
    except ValueError:
        return None

def read_clean_lines(path):
    """读取非空行（去除行尾空白）。surrogateescape 保证任意字节都能原样写回。"""
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8', errors='surrogateescape') as f:
        return [ln.rstrip() for ln in f if ln.strip()]

def file_has_dated_entries(path, use_last=True):
    return any(extract_date(ln, use_last) for ln in read_clean_lines(path))

def atomic_write_lines(path, lines):
    """原子写入：先写临时文件再替换，避免中途崩溃导致文件损坏"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', errors='surrogateescape') as f:
        if lines:
            f.write('\n'.join(lines) + '\n')
    os.replace(tmp, path)

def append_archive_lines(path, lines):
    """追加到汇总文件（沿用原格式：与前文以换行分隔，末行不加换行）"""
    if not lines:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    need_newline = False
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, 'rb') as f:
            f.seek(-1, os.SEEK_END)
            need_newline = f.read(1) != b'\n'
    with open(path, 'a', encoding='utf-8', errors='surrogateescape') as f:
        f.write(('\n' if need_newline else '') + '\n'.join(lines))

def show_alert(message):
    """跨平台弹窗提示"""
    if platform.system() == 'Darwin':
        try:
            safe_msg = str(message).replace('\\', '\\\\').replace('"', '\\"')
            applescript_code = f'display dialog "{safe_msg}" buttons {{"OK"}} default button "OK"'
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        except Exception as e:
            print(f"弹窗提示失败: {e}")
    else:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("提示", message)
            root.destroy()
        except Exception as e:
            print(f"弹窗提示失败: {e}")


# ================= Part A: 按日期自动对账/归档 =================

class PartA_Reconciler:
    """
    每次运行都根据"每行数据自身的日期"把数据放进正确的文件：
      - 早于本周      -> 汇总(归档)文件
      - 本周          -> *_new.txt
      - 下周          -> *_next.txt
      - +2/+3/+4 周   -> *_third / *_fourth / *_fifth
    幂等：无论哪天运行、运行几次、之前漏跑几次，结果都一致。
    """

    def __init__(self, today: date = None):
        self.today = today or RUN_TODAY
        self.snapshot_dir = None

    def _snapshot(self, paths):
        if self.snapshot_dir is None:
            self.snapshot_dir = os.path.join(
                BACKUP_ROOT_DIR, 'reconcile_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
            os.makedirs(self.snapshot_dir, exist_ok=True)
        for p in paths:
            if os.path.exists(p):
                dst = os.path.join(self.snapshot_dir, os.path.basename(p))
                if not os.path.exists(dst):
                    shutil.copy2(p, dst)

    def _reconcile(self, label, group_paths, archive_path, use_last_date,
                   key_fn, archive_line_fn, prefer_new_fn=None):
        n = len(group_paths)
        placed = [dict() for _ in range(n)]       # key -> (line, date)，保持插入顺序
        unparsed = [[] for _ in range(n)]
        archive_candidates = {}                    # key -> archive line
        moved, overflow = 0, 0

        for gi, (gname, path) in enumerate(group_paths):
            for ln in read_clean_lines(path):
                d = extract_date(ln, use_last_date)
                key = key_fn(ln, d) if d else None
                if key is None:
                    unparsed[gi].append(ln)
                    print(f"   [警告] {os.path.basename(path)} 中无法识别日期的行已原样保留: {ln}")
                    continue

                idx = week_index_of(d, self.today)
                if idx < 0:
                    archive_candidates.setdefault(key, archive_line_fn(ln, d))
                    continue
                if idx >= n:
                    overflow += 1
                    print(f"   [警告] {ln} 日期超出最远分组，暂放入 {group_paths[-1][0]}")
                    idx = n - 1
                if idx != gi:
                    moved += 1

                bucket = placed[idx]
                if key in bucket:
                    old_line = bucket[key][0]
                    if prefer_new_fn and prefer_new_fn(ln, old_line):
                        bucket[key] = (ln, d)
                else:
                    bucket[key] = (ln, d)

        # 生成各文件新内容（按日期稳定排序，同一天保持原顺序）
        new_contents = []
        for i in range(n):
            items = sorted(placed[i].values(), key=lambda x: x[1])
            new_contents.append(unparsed[i] + [ln for ln, _ in items])

        # 归档去重
        to_append = []
        if archive_path:
            existing_keys = set()
            for ln in read_clean_lines(archive_path):
                d = extract_date(ln, use_last_date)
                if d:
                    k = key_fn(ln, d)
                    if k is not None:
                        existing_keys.add(k)
            to_append = [line for k, line in archive_candidates.items() if k not in existing_keys]

        changed = bool(to_append) or any(
            new_contents[i] != read_clean_lines(p) for i, (_, p) in enumerate(group_paths))

        if not changed:
            print(f"[{label}] 已是正确状态，无需调整。")
            return

        all_paths = [p for _, p in group_paths] + ([archive_path] if archive_path else [])
        self._snapshot(all_paths)

        # 先归档、后改分组文件：即使中途崩溃，下次运行也会因去重而自动修复
        if to_append:
            append_archive_lines(archive_path, to_append)
        for i, (_, p) in enumerate(group_paths):
            if new_contents[i] or os.path.exists(p):
                atomic_write_lines(p, new_contents[i])

        print(f"[{label}] 调整完成：归档 {len(to_append)} 条（过期共 {len(archive_candidates)} 条），"
              f"跨文件移动 {moved} 条，超范围 {overflow} 条。")
        for i, (g, _) in enumerate(group_paths):
            print(f"      {g:<7}: {len(new_contents[i])} 行")

    # ---- 各类文件的规则 ----
    @staticmethod
    def _earn_key(ln, d):
        if ':' not in ln:
            return None
        sym = ln.split(':', 1)[0].strip()
        return (sym, d) if sym else None

    @staticmethod
    def _earn_prefer_new(new_ln, old_ln):
        # 同一 (symbol, 日期) 重复时，优先保留有真实发布时间的那条
        return 'N/A' in old_ln and 'N/A' not in new_ln

    def run(self):
        print("\n" + "=" * 50)
        print(">>> 正在启动 Part A (按日期自动对账/归档)")
        print(f"    基准日期: {self.today}  本周: {week_start(self.today)} ~ "
              f"{week_start(self.today) + timedelta(days=6)}")
        print("=" * 50)
        try:
            self._reconcile(
                "Earnings_Release",
                [(g, earnings_file(g)) for g in EARNINGS_GROUPS],
                EARNINGS_ARCHIVE_PATH,
                use_last_date=True,
                key_fn=self._earn_key,
                archive_line_fn=lambda ln, d: f"{ln.split(':', 1)[0].strip():<7}: {d.strftime('%Y-%m-%d')}",
                prefer_new_fn=self._earn_prefer_new,
            )
            self._reconcile(
                "Earnings_Release_diff",
                [(g, earnings_diff_file(g)) for g in EARNINGS_GROUPS],
                EARNINGS_DIFF_EXPIRED_PATH,
                use_last_date=True,
                key_fn=lambda ln, d: ln,
                archive_line_fn=lambda ln, d: ln,
            )
            self._reconcile(
                "Economic_Events",
                [(g, economic_file(g)) for g in ECONOMIC_GROUPS],
                ECONOMIC_ARCHIVE_PATH,
                use_last_date=False,
                key_fn=lambda ln, d: ln,
                archive_line_fn=lambda ln, d: ln,
            )
            if self.snapshot_dir:
                print(f"调整前的原始文件已备份至: {self.snapshot_dir}")
        except Exception as e:
            msg = f"Part A 对账出错（原文件已备份，未完成的部分下次运行会自动续做）: {e}"
            print(msg)
            show_alert(msg)
        print("Part A 执行结束.\n")


# ================= Part B: Selenium 爬虫 =================

def create_unified_driver():
    """统一的 Selenium Driver 工厂函数 (跨平台)。"""
    options = Options()

    if os.path.exists(CHROME_BINARY_PATH):
        options.binary_location = CHROME_BINARY_PATH
    else:
        tqdm.write(f"警告：未找到 Chrome 路径 {CHROME_BINARY_PATH}，使用系统默认。")

    options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')

    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    options.add_argument(f'user-agent={user_agent}')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-images")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.page_load_strategy = 'eager'

    try:
        if not os.path.exists(CHROME_DRIVER_PATH):
            raise FileNotFoundError(f"未找到驱动文件: {CHROME_DRIVER_PATH}")

        service = Service(executable_path=CHROME_DRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)

        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
            })
            """
        })
        return driver
    except Exception as e:
        tqdm.write(f"创建 Driver 失败: {e}")
        return None

def move_mouse_periodically():
    """后台周期性移动鼠标，防止系统休眠（当前未启用）。"""
    import pyautogui  # 延迟导入：无图形界面环境下不影响主程序
    while True:
        try:
            screen_width, screen_height = pyautogui.size()
            x = random.randint(100, screen_width - 100)
            y = random.randint(100, screen_height - 100)
            pyautogui.moveTo(x, y, duration=1)
            time.sleep(random.randint(30, 60))
        except Exception:
            time.sleep(30)

# --- B.1: Economic Events Task ---

def update_sectors_panel():
    """根据 Economic_Events new/next 文件刷新 sectors_panel 的 Economics 分组"""
    path_new = economic_file('new')
    path_next = economic_file('next')

    event_files = []
    if os.path.exists(path_new):
        event_files.append(('new', path_new))
    if os.path.exists(path_next):
        event_files.append(('next', path_next))

    if not event_files:
        tqdm.write("未找到 Economic_Events 文件，未执行更新。")
        show_alert("未找到 Economic_Events 文件，未执行更新。")
        return

    try:
        with open(SYMBOL_MAPPING_JSON_PATH, 'r', encoding='utf-8') as f:
            symbol_mapping = json.load(f)

        with open(SECTORS_PANEL_JSON_PATH, 'r', encoding='utf-8') as f:
            sectors_panel = json.load(f)

        sectors_panel['Economics'] = {}

        for tag, filepath in event_files:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    event = line.strip()
                    if not event:
                        continue
                    if ' : ' not in event:
                        tqdm.write(f"Warning: 跳过格式不对的行：{event}")
                        continue

                    date_part, desc_part = event.split(' : ', 1)
                    day_field = date_part.split('-')[-1].strip()
                    description = desc_part.split(' [')[0].strip()

                    if description not in symbol_mapping:
                        continue

                    economics_key = symbol_mapping[description]
                    combined_value = f"{day_field} {economics_key}"

                    existing = sectors_panel['Economics'].get(economics_key)
                    if existing is None:
                        sectors_panel['Economics'][economics_key] = combined_value
                    elif existing != combined_value and tag == 'next':
                        sectors_panel['Economics'][economics_key] = combined_value

        with open(SECTORS_PANEL_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(sectors_panel, f, ensure_ascii=False, indent=4)

        tqdm.write("Economic Events JSON 更新已完成！")

    except Exception as e:
        error_message = f"更新 Economic Events JSON 错误: {e}"
        tqdm.write(error_message)
        show_alert(error_message)

def crawl_economic_week(driver, week_idx, file_path):
    """抓取相对本周偏移 week_idx 的那一周（周日~周六）的经济事件，追加到 file_path"""
    start_date = week_start(RUN_TODAY) + timedelta(weeks=week_idx)
    end_date = start_date + timedelta(days=6)
    tqdm.write(f"抓取经济事件: {start_date} ~ {end_date} -> {os.path.basename(file_path)}")

    if os.path.exists(file_path):
        timestamp = datetime.now().strftime('%y%m%d')
        os.makedirs(BACKUP_ROOT_DIR, exist_ok=True)
        base = os.path.splitext(os.path.basename(file_path))[0]
        shutil.copy2(file_path, os.path.join(BACKUP_ROOT_DIR, f'{base}_{timestamp}.txt'))
        with open(file_path, 'r') as file:
            existing_content = set(file.read().splitlines())
    else:
        existing_content = set()

    target_countries = {"US"}
    date_list = [start_date + timedelta(days=i) for i in range(7)]
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    MAX_OFFSET = 2000  # 防死循环保险

    with open(file_path, 'a') as output_file:
        pbar = tqdm(date_list, desc="Eco Events", unit="day")
        for change_date in pbar:
            formatted_change_date = change_date.strftime('%Y-%m-%d')
            pbar.set_description(f"正在抓取: {formatted_change_date}")

            offset = 0
            last_signature = None
            while offset <= MAX_OFFSET:
                pbar.set_postfix(offset=offset)
                url = (f"https://finance.yahoo.com/calendar/economic?from={start_date.strftime('%Y-%m-%d')}"
                       f"&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100")
                driver.get(url)
                try:
                    table_container = WebDriverWait(driver, 4).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.table-container")))
                    rows = table_container.find_elements(By.TAG_NAME, "tr")
                except TimeoutException:
                    rows = []

                data_rows = []
                for row in rows:
                    try:
                        if row.get_attribute("role") == "columnheader":
                            continue
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if len(cells) < 2:
                            continue
                        data_rows.append((cells[0].text.strip(), cells[1].text.strip()))
                    except Exception:
                        continue

                if not data_rows:
                    break
                signature = tuple(data_rows)
                if signature == last_signature:  # 翻页后内容相同，说明已到末尾
                    break
                last_signature = signature

                for event, country in data_rows:
                    if event and country and country in target_countries:
                        matched = next((b for b in EVENT_FILTER_BASES if event.startswith(b)), None)
                        if matched:
                            entry = f"{formatted_change_date} : {matched} [{country}]"
                            if entry not in existing_content:
                                output_file.write(entry + "\n")
                                existing_content.add(entry)
                offset += 100

def run_economic_events_task():
    tqdm.write("\n" + "=" * 50)
    tqdm.write(">>> 开始执行任务: Economic Events")
    tqdm.write("=" * 50)

    today_weekday = RUN_TODAY.weekday()
    weeks_to_crawl = []

    # 补抓：本周文件为空（通常是漏跑导致），则补抓本周
    if not file_has_dated_entries(economic_file('new'), use_last=False):
        tqdm.write("检测到 Economic_Events_new 为空，将补抓本周数据。")
        weeks_to_crawl.append((0, economic_file('new')))
    # 常规：周五/周六抓取下周
    if today_weekday in (4, 5):
        weeks_to_crawl.append((1, economic_file('next')))

    if weeks_to_crawl:
        tqdm.write("正在启动浏览器 (Economic Events)...")
        driver = create_unified_driver()
        if driver:
            try:
                for week_idx, path in weeks_to_crawl:
                    crawl_economic_week(driver, week_idx, path)
            except Exception as e:
                tqdm.write(f"Economic Events 爬虫出错: {e}")
            finally:
                driver.quit()
                tqdm.write("Economic Events 浏览器已关闭。")
        else:
            tqdm.write("无法启动浏览器，跳过爬取。")
    else:
        tqdm.write("今天无需抓取 Economic Events（仅周五/周六抓取下周，或本周缺数据时补抓）。")

    # 每次都刷新：保证 sectors_panel 与当前 new/next 文件完全一致
    update_sectors_panel()

# --- B.2: Stock Splits Task ---

def run_stock_splits_task():
    tqdm.write("\n" + "=" * 50)
    tqdm.write(">>> 开始执行任务: Stock Splits")
    tqdm.write("=" * 50)

    today_weekday = RUN_TODAY.weekday()
    if today_weekday not in (4, 5):
        tqdm.write("今天不是周五或周六，跳过 Stock Splits 任务。")
        return

    file_path = os.path.join(NEWS_DIR, 'Stock_Splits_next.txt')

    if os.path.exists(file_path):
        timestamp = datetime.now().strftime('%y%m%d')
        backup_path = os.path.join(BACKUP_ROOT_DIR, f'Stock_Splits_next_{timestamp}.txt')
        os.makedirs(BACKUP_ROOT_DIR, exist_ok=True)
        shutil.copy2(file_path, backup_path)
        tqdm.write(f"已备份原文件至: {backup_path}")

    existing_content = set()
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            existing_content = set(file.read().splitlines())

    tqdm.write("正在启动浏览器 (Stock Splits)...")
    driver = create_unified_driver()

    if driver:
        try:
            with open(SECTORS_ALL_JSON_PATH, 'r') as file:
                data = json.load(file)

            start_date = week_start(RUN_TODAY) + timedelta(weeks=1)
            end_date = start_date + timedelta(days=6)
            tqdm.write(f"抓取日期范围: {start_date} 至 {end_date}")

            results = []
            date_list = [start_date + timedelta(days=i) for i in range(7)]
            pbar = tqdm(date_list, desc="Stock Splits", unit="day")

            for change_date in pbar:
                formatted_change_date = change_date.strftime('%Y-%m-%d')
                pbar.set_description(f"正在处理: {formatted_change_date}")

                offset = 0
                has_data = True
                while has_data:
                    pbar.set_postfix(offset=offset, found=len(results))
                    url = (f"https://finance.yahoo.com/calendar/splits?from={start_date.strftime('%Y-%m-%d')}"
                           f"&to={end_date.strftime('%Y-%m-%d')}&day={formatted_change_date}&offset={offset}&size=100")
                    driver.get(url)
                    try:
                        rows = WebDriverWait(driver, 4).until(
                            EC.presence_of_all_elements_located((By.XPATH, "//table//tbody/tr")))
                    except TimeoutException:
                        break

                    if not rows:
                        break

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
                                    existing_content.add(entry)
                                    tqdm.write(f"   [+] 发现新数据: {entry}")
                                break

                    if len(rows) < 100:
                        has_data = False
                    else:
                        offset += 100

            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            if results:
                old_lines = []
                if os.path.exists(file_path):
                    with open(file_path, 'r') as file:
                        old_lines = [ln.rstrip('\n') for ln in file if ln.strip()]
                with open(file_path, 'w') as file:
                    file.write('\n'.join(old_lines + results) + '\n')
                tqdm.write(f"成功写入 {len(results)} 条新数据。")
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

def compute_group_date_range(group_name: str):
    """
    根据 RUN_TODAY 计算各分组的抓取范围（周一至周六），与 Part A 的周归属规则完全一致：
      new=本周, next=+1周, third=+2周, fourth=+3周, fifth=+4周
    （周日属于其后的那个周一所在周）
    """
    idx = EARNINGS_GROUPS.index(group_name) if group_name in EARNINGS_GROUPS else 1
    ws = week_start(RUN_TODAY) + timedelta(weeks=idx)
    return ws + timedelta(days=1), ws + timedelta(days=6)

NO_RESULT_XPATH = "//*[contains(normalize-space(.), \"We couldn't find any results\")]"

def _earnings_page_state(d):
    if d.find_elements(By.CSS_SELECTOR, "table tbody > tr"):
        return 'rows'
    if d.find_elements(By.XPATH, NO_RESULT_XPATH):
        return 'end'
    return False

def run_single_scraper_task(driver, sectors_data, task_config):
    group_name = task_config["group_name"]
    file_path = task_config["file_path"]
    diff_path = task_config["diff_path"]
    backup_dir = task_config["backup_dir"]
    earnings_release_path = task_config["earnings_release_path"]

    tqdm.write(f">> 正在初始化任务: {group_name.upper()}")

    last_sd, last_ed = compute_group_date_range(group_name)
    start_date = datetime(last_sd.year, last_sd.month, last_sd.day)
    end_date = datetime(last_ed.year, last_ed.month, last_ed.day)
    tqdm.write(f"   日期范围: {start_date.date()} -> {end_date.date()}")

    existing_release_entries = set()
    if os.path.exists(earnings_release_path):
        with open(earnings_release_path, 'r') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) >= 2:
                    existing_release_entries.add((parts[0].strip(), parts[-1].strip()))

    # 最近一个月内已发布的 symbols
    recent_backup_symbols = set()
    for s, d in existing_release_entries:
        try:
            dt = datetime.strptime(d, '%Y-%m-%d').date()
            if 0 <= (RUN_TODAY - dt).days <= 30:
                recent_backup_symbols.add(s)
        except ValueError:
            continue

    if os.path.exists(file_path):
        ts = datetime.now().strftime('%y%m%d')
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(file_path, os.path.join(backup_dir, f'Earnings_Release_{group_name}_{ts}.txt'))

    existing_lines = []
    existing_map = {}
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            for line in f:
                ln = line.rstrip('\n')
                if not ln.strip():
                    continue
                existing_lines.append(ln)
                parts = ln.split(':')
                if len(parts) >= 3:
                    existing_map[parts[0].strip()] = (parts[1].strip(), parts[-1].strip())

    new_entries = []
    date_list = [start_date + i * timedelta(days=1) for i in range((end_date - start_date).days + 1)]
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

            for attempt in range(3):
                try:
                    driver.get(url)
                    state = WebDriverWait(driver, 8).until(_earnings_page_state)
                    if state == 'end':
                        found_end = True
                        page_load_success = True
                        break
                    rows = driver.find_elements(By.CSS_SELECTOR, "table tbody > tr")
                    if rows:
                        page_load_success = True
                        break
                except TimeoutException:
                    pass
                except Exception:
                    pass
                time.sleep(random.randint(2, 4))

            if found_end:
                break
            if not page_load_success:
                tqdm.write(f"    [{ds}] Offset {offset} 加载失败，跳过。")
                break
            if not rows:
                break

            for row in rows:
                try:
                    symbol_el = row.find_element(By.CSS_SELECTOR, 'a[title][href*="/quote/"]')
                    symbol = symbol_el.get_attribute('title')

                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) < 4:
                        continue

                    if group_name == "fifth" and symbol in EXCLUDE_FROM_FIFTH:
                        continue

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

                    existing_map[symbol] = (call_time, ds)
                    new_entries.append(new_line)
                except Exception:
                    continue
            offset += 100

    # 写入文件处理
    symbols_to_avoid = set()
    for f_path in task_config["duplicate_check_files"]:
        if os.path.exists(f_path):
            with open(f_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if parts and parts[0].strip():
                        symbols_to_avoid.add(parts[0].strip())

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

    # 修复：仅当新记录确实写入主文件时，才删除该 symbol 的旧记录（原逻辑会导致旧行被删、新行进 diff，两头丢失）
    replaced_syms = {ln.split(':')[0].strip() for ln in entries_for_target}
    kept_lines = [ln for ln in existing_lines if ln.split(':')[0].strip() not in replaced_syms]

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    all_lines_to_write = kept_lines + entries_for_target
    atomic_write_lines(file_path, all_lines_to_write)

    if entries_for_diff:
        os.makedirs(os.path.dirname(diff_path), exist_ok=True)
        with open(diff_path, 'a') as f:
            for ln in entries_for_diff:
                f.write(ln + '\n')

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
    tqdm.write("\n" + "=" * 50)
    tqdm.write(">>> 开始执行任务: Earnings Release")
    tqdm.write("=" * 50)

    TASK_CONFIGS = []
    # 补抓：new 为空（通常是漏跑太久导致），则先补抓本周
    if not file_has_dated_entries(earnings_file('new')):
        tqdm.write("检测到 Earnings_Release_new 为空，将补抓本周数据。")
        TASK_CONFIGS.append({"group_name": "new", "duplicate_check_files": []})

    for i, g in enumerate(EARNINGS_GROUPS[1:], start=1):
        TASK_CONFIGS.append({
            "group_name": g,
            "duplicate_check_files": [earnings_file(x) for x in EARNINGS_GROUPS[:i]],
        })

    for cfg in TASK_CONFIGS:
        cfg["file_path"] = earnings_file(cfg["group_name"])
        cfg["diff_path"] = earnings_diff_file(cfg["group_name"])
        cfg["backup_dir"] = BACKUP_ROOT_DIR
        cfg["earnings_release_path"] = EARNINGS_ARCHIVE_PATH

    tqdm.write("正在启动浏览器 (Earnings)...")
    driver = create_unified_driver()
    if driver:
        try:
            with open(SECTORS_ALL_JSON_PATH, 'r') as f:
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
            show_alert("Earnings 抓取任务已完成！")
        except Exception:
            pass
    else:
        tqdm.write("无法启动浏览器，跳过 Earnings 任务。")

def run_part_b():
    tqdm.write("\n" + "=" * 50)
    tqdm.write(">>> 正在启动 Part B (Selenium 爬虫任务)")
    tqdm.write("=" * 50)
    try:
        run_economic_events_task()
        time.sleep(2)
        run_stock_splits_task()
        time.sleep(2)
        run_earnings_task()
    except KeyboardInterrupt:
        tqdm.write("\n程序被用户手动终止。")
    except Exception as e:
        tqdm.write(f"\nPart B 发生未知错误: {e}")


# ================= Part C: Polymarket =================

def load_existing_polymarket_data(filename):
    """读取本地已有的数据，返回一个字典 { 'MBWM': '93%', ... }"""
    data = {}
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if ':' in line:
                    ticker, percent = line.split(':', 1)
                    data[ticker.strip()] = percent.strip()
    return data

def save_polymarket_data(filename, data):
    """将合并后的数据保存回 txt 文件"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w', encoding='utf-8') as f:
        for ticker, percent in data.items():
            f.write(f"{ticker}: {percent}\n")
    print(f"数据已成功保存至 {filename}，共 {len(data)} 条记录。")

def run_part_c():
    print("\n" + "=" * 50)
    print(">>> 正在启动 Part C (Polymarket 爬虫任务)")
    print("=" * 50)

    earnings_data = load_existing_polymarket_data(POLYMARKET_FILE_PATH)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"
            )

            print("正在访问 Polymarket 页面...")
            page.goto("https://polymarket.com/earnings",
                      wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)

            results = page.evaluate("""
                () => {
                    const out = [];
                    const all = Array.from(document.querySelectorAll('*'));
                    for (const el of all) {
                        const txt = (el.textContent || '').trim();
                        if (el.children.length === 0 && /^\\d{1,3}%$/.test(txt)) {
                            let node = el;
                            let ticker = null;
                            for (let i = 0; i < 6 && node; i++) {
                                node = node.parentElement;
                                if (!node) break;
                                const cand = Array.from(node.querySelectorAll('*'))
                                    .map(x => (x.childElementCount === 0 ? x.textContent.trim() : ''))
                                    .find(t => /^[A-Z]{1,6}$/.test(t));
                                if (cand) { ticker = cand; break; }
                            }
                            if (ticker) out.push([ticker, txt]);
                        }
                    }
                    return out;
                }
            """)

            print(f"提取到 {len(results)} 条原始记录，正在合并...")
            skip_values = ["0%", "100%", "0", "100", "0.0%", "100.0%"]

            for ticker, percent in results:
                ticker = ticker.strip()
                clean_percent = percent.strip()
                if not ticker or not clean_percent:
                    continue
                if ticker in earnings_data:
                    if clean_percent in skip_values:
                        print(f"跳过更新: {ticker} (本地已存在, 新值 {percent})")
                    else:
                        earnings_data[ticker] = percent
                        print(f"更新覆盖: {ticker} -> {percent}")
                else:
                    earnings_data[ticker] = percent
                    print(f"抓取新增: {ticker} -> {percent}")

            browser.close()

        save_polymarket_data(POLYMARKET_FILE_PATH, earnings_data)
    except Exception as e:
        print(f"Part C (Polymarket) 执行出错: {e}")


if __name__ == "__main__":
    # 1. Part A：按日期对账归档（任何一天运行都安全，幂等）
    PartA_Reconciler().run()
    time.sleep(1)

    # 2. Part B：Selenium 爬虫
    run_part_b()
    time.sleep(1)

    # 3. Part C：Playwright 爬虫
    run_part_c()