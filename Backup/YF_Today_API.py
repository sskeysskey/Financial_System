import sqlite3
import os
import sys
import json
import datetime
import subprocess
from tqdm import tqdm
import pandas_market_calendars as mcal
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ================= 配置区域 =================
USER_HOME = os.path.expanduser("~")

BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
FINANCIAL_SYSTEM_DIR = os.path.join(BASE_CODING_DIR, "Financial_System")
DATABASE_DIR = os.path.join(BASE_CODING_DIR, "Database")

DB_PATH = os.path.join(DATABASE_DIR, "Finance.db")
SECTORS_JSON_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Sectors_empty.json")
SYMBOL_MAPPING_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Modules", "Symbol_mapping.json")
CHECK_YESTERDAY_SCRIPT_PATH = os.path.join(FINANCIAL_SYSTEM_DIR, "Query", "Check_yesterday.py")

# 并发线程数（建议 8~20，网络差或被限速时可降低）
MAX_WORKERS = 8


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
        return "standard"


def create_table_if_not_exists(cursor, table_name, table_type):
    """确保数据库表存在"""
    safe_table_name = f'"{table_name}"'
    if table_type == "expanded":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT, name TEXT, price REAL, volume INTEGER,
            open REAL, high REAL, low REAL,
            UNIQUE(date, name)
        )''')
    elif table_type == "no_volume":
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT, name TEXT, price REAL,
            UNIQUE(date, name)
        )''')
    else:
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {safe_table_name} (
            date TEXT, name TEXT, price REAL, volume INTEGER,
            UNIQUE(date, name)
        )''')


def insert_data_to_db(db_path, table_name, data_rows, table_type):
    """将数据写入数据库（支持批量）"""
    if not data_rows:
        return False
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    safe_table = f'"{table_name}"'
    try:
        create_table_if_not_exists(cursor, table_name, table_type)

        if table_type == "expanded":
            filtered_data = data_rows
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price, volume, open, high, low)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price=excluded.price, volume=excluded.volume,
                open=excluded.open, high=excluded.high, low=excluded.low;
            """
        elif table_type == "no_volume":
            filtered_data = [(r[0], r[1], r[2]) for r in data_rows]
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price)
            VALUES (?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET price=excluded.price;
            """
        else:
            filtered_data = [(r[0], r[1], r[2], r[3]) for r in data_rows]
            upsert_sql = f"""
            INSERT INTO {safe_table} (date, name, price, volume)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, name) DO UPDATE SET
                price=excluded.price, volume=excluded.volume;
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
    """加载并反转 Symbol 映射表"""
    if not os.path.exists(json_path):
        tqdm.write(f"⚠️ 未找到映射文件: {json_path}")
        return {}
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
            return {v: k for k, v in mapping.items()}
    except Exception as e:
        tqdm.write(f"⚠️ 读取映射文件出错: {e}")
        return {}


def batch_remove_symbols_from_json(json_path, group_symbols_dict):
    """批量从 JSON 中移除已完成的 symbols（只做一次文件读写，代替逐个操作）"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for group, symbols in group_symbols_dict.items():
            if group in data:
                for sym in symbols:
                    if sym in data[group]:
                        data[group].remove(sym)

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        tqdm.write(f"⚠️ 批量更新 JSON 失败: {e}")
        return False


# ================= 2. 日期计算 =================

def get_last_valid_trading_date():
    """获取美股最近的一个有效开盘日（严格小于今天）"""
    nyse = mcal.get_calendar('NYSE')
    today = datetime.datetime.now().date()
    start_date = today - datetime.timedelta(days=15)
    schedule = nyse.schedule(start_date=start_date, end_date=today)
    valid_days = schedule.index.date
    past_days = [d for d in valid_days if d < today]
    if past_days:
        return past_days[-1].strftime('%Y-%m-%d')
    return None


# ================= 3. yfinance 抓取核心 =================

def _safe_float(val):
    try:
        if pd.isna(val):
            return None
        return round(float(val), 6)
    except (TypeError, ValueError):
        return None


def _safe_int(val):
    try:
        if pd.isna(val):
            return 0
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def _make_row(date_str, name, row):
    """构造标准数据行: (date, name, price, volume, open, high, low)"""
    return (
        date_str,
        name,
        _safe_float(row.get('Close')),
        _safe_int(row.get('Volume', 0)),
        _safe_float(row.get('Open')),
        _safe_float(row.get('High')),
        _safe_float(row.get('Low')),
    )


def fetch_one_symbol(display_name, scrape_symbol, last_valid_date):
    """
    使用 yfinance 获取单个 symbol 最近 5 天的历史数据，
    根据 last_valid_date 选取正确的那一行。
    返回: (data_row_tuple, error_string)
    """
    try:
        ticker = yf.Ticker(scrape_symbol)
        hist = ticker.history(period="5d")

        if hist.empty:
            return None, "yfinance 返回数据为空"

        # 统一移除时区信息
        if hist.index.tz is not None:
            hist.index = hist.index.tz_localize(None)
        hist = hist.sort_index()

        # 过滤掉 Close 为 NaN 的行
        hist = hist.dropna(subset=['Close'])
        if hist.empty:
            return None, "无有效收盘价"

        dates = [d.strftime('%Y-%m-%d') for d in hist.index]

        # 如果无法计算目标日期，取最新一条
        if not last_valid_date:
            return _make_row(dates[-1], display_name, hist.iloc[-1]), None

        # ===== 日期匹配逻辑（等价于原始 Selenium 版本）=====

        # 1) 精确匹配目标日期
        if last_valid_date in dates:
            idx = dates.index(last_valid_date)
            return _make_row(last_valid_date, display_name, hist.iloc[idx]), None

        # 2) 所有数据都比目标日期新（例如当天已有实时数据但尚未收盘）
        #    → 用最新一条数据，但日期修正为 last_valid_date
        if all(d > last_valid_date for d in dates):
            return _make_row(last_valid_date, display_name, hist.iloc[-1]), None

        # 3) 所有数据都比目标日期旧 → 数据未更新，跳过
        if all(d < last_valid_date for d in dates):
            return None, f"数据未更新 (最新 {dates[-1]} < {last_valid_date})"

        # 4) 混合情况：取最接近且 <= last_valid_date 的那一天
        past = [(i, d) for i, d in enumerate(dates) if d <= last_valid_date]
        if past:
            idx, d = past[-1]
            return _make_row(d, display_name, hist.iloc[idx]), None

        return None, "无匹配日期"

    except Exception as e:
        return None, str(e)[:150]


# ================= 4. 主流程 =================

def scrape_history():
    # 1. 加载任务与配置
    tasks_dict = load_tasks_from_json(SECTORS_JSON_PATH)
    alias_to_symbol = load_alias_mapping(SYMBOL_MAPPING_PATH)

    last_valid_date = get_last_valid_trading_date()
    if last_valid_date:
        tqdm.write(f"📅 最近有效开盘日: {last_valid_date}")
    else:
        tqdm.write("⚠️ 无法计算最近有效开盘日，将使用网页原始日期。")

    # 展平任务列表
    task_list = []
    for group, symbols in tasks_dict.items():
        for sym in symbols:
            task_list.append((sym, group))

    if not task_list:
        tqdm.write("✅ JSON 文件中没有待抓取的 Symbol，任务结束。")
        run_check_yesterday_if_empty()
        return

    tqdm.write(f"📊 共 {len(task_list)} 个任务，{MAX_WORKERS} 线程并发抓取中...")

    # 2. Phase 1 —— 多线程并发抓取（纯网络 IO，不涉及文件/数据库操作）
    results = []  # (display_name, group, data_row, error)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {}
        for sym, group in task_list:
            scrape_sym = alias_to_symbol.get(sym, sym)
            future = executor.submit(fetch_one_symbol, sym, scrape_sym, last_valid_date)
            future_map[future] = (sym, group)

        for future in tqdm(as_completed(future_map), total=len(future_map), desc="抓取进度"):
            sym, group = future_map[future]
            try:
                data_row, error = future.result()
                results.append((sym, group, data_row, error))
            except Exception as e:
                results.append((sym, group, None, str(e)[:100]))

    # 3. Phase 2 —— 按 group 分组，批量写入数据库（顺序执行，避免并发锁问题）
    success_data = defaultdict(list)
    success_symbols = defaultdict(list)
    fail_count = 0
    skip_count = 0

    for sym, group, data_row, error in results:
        if data_row:
            success_data[group].append(data_row)
            success_symbols[group].append(sym)
        elif error:
            if "数据未更新" in str(error):
                skip_count += 1
            else:
                tqdm.write(f"⚠️ [{sym}] {error}")
                fail_count += 1

    total_written = 0
    written_symbols = defaultdict(list)

    for group, rows in success_data.items():
        table_type = get_table_type(group)
        if insert_data_to_db(DB_PATH, group, rows, table_type):
            total_written += len(rows)
            written_symbols[group] = success_symbols[group]
        else:
            tqdm.write(f"❌ [{group}] 批量写入失败 ({len(rows)} 条)")
            fail_count += len(rows)

    # 4. Phase 3 —— 一次性更新 JSON（代替原来逐个 remove 的 1800 次文件读写）
    if written_symbols:
        batch_remove_symbols_from_json(SECTORS_JSON_PATH, dict(written_symbols))

    tqdm.write(f"🎉 完成！成功写入 {total_written} | 跳过(未更新) {skip_count} | 失败 {fail_count}")

    # 5. 检查是否全部完成
    run_check_yesterday_if_empty()


def run_check_yesterday_if_empty():
    """检查 JSON 是否已清空，如清空则执行 Check_yesterday.py"""
    final_tasks = load_tasks_from_json(SECTORS_JSON_PATH)
    is_empty = True
    if final_tasks:
        for group, symbols in final_tasks.items():
            if len(symbols) > 0:
                is_empty = False
                break

    if is_empty:
        print("✅ Sectors_empty.json 已全部清空，开始执行 Check_yesterday.py...")
        try:
            subprocess.run([sys.executable, CHECK_YESTERDAY_SCRIPT_PATH],
                           check=True, capture_output=True, text=True, encoding='utf-8')
            print("✅ Check_yesterday.py 执行完毕。")
        except Exception as e:
            print(f"❌ 调用 Check_yesterday 出错: {e}")
    else:
        print("⚠️ Sectors_empty.json 中仍有未完成的任务，跳过执行 Check_yesterday.py。")


if __name__ == "__main__":
    today_num = datetime.datetime.now().weekday()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    today_str = weekdays[today_num]
    scrape_history()