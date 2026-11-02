import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from typing import Callable, Tuple, Optional

import pandas_market_calendars as mcal

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# -------- 路径 -------- #
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
SECTORS_ALL_JSON = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
SECTOR_EMPTY_JSON = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_empty.json")
ERROR_FILE = os.path.join(BASE_CODING_DIR, "News", "Today_error2.txt")

# 无人值守模式（由 run_pipeline.sh 设置 FS_UNATTENDED=1）：绝不弹阻塞式对话框
UNATTENDED = os.environ.get("FS_UNATTENDED") == "1"

# -------- 排除特定板块的配置 -------- #
EXCLUDE_SECTORS_SWITCH = False
EXCLUDE_SECTORS_LIST = {
    "Basic_Materials", "Communication_Services", "Consumer_Cyclical", "Consumer_Defensive",
    "Energy", "Financial_Services", "Healthcare", "Industrials", "Real_Estate",
    "Technology", "Utilities", "ETFs",
}

# 不需要写入 empty 的 symbol
FILTER_LIST = {
    'USInterest', 'USGDP', 'USCPI', 'USNonFarmA', 'USRetailM', 'USUnemploy',
    'USNonFarm', 'USConfidence', 'USInitial', 'USPPI', 'USNonPMI', 'CorePPI',
    'PCEY', 'CorePCEY', 'CorePCEM', 'CoreCPI', 'USConspending', 'ImportPriceM',
    'ImportPriceY', 'USTrade', 'CNYI', 'JPYI', 'EURI', 'CHFI', 'GBPI'
}


# ================= 提示（不阻塞自动化） =================

def notify(message: str, popup: bool = False):
    """
    popup=True 且非无人值守：弹对话框（120 秒无人点击自动关闭，绝不会永久卡住）
    其它情况：只发系统通知（非阻塞）
    """
    print(message, flush=True)
    if sys.platform != 'darwin':
        return
    safe = message.replace('\\', '\\\\').replace('"', '\\"')
    if popup and not UNATTENDED:
        script = (f'display dialog "{safe}" buttons {{"OK"}} default button "OK" '
                  f'with title "脚本提示" giving up after 120')
    else:
        script = f'display notification "{safe}" with title "Check_yesterday"'
    try:
        subprocess.run(['osascript', '-e', script], check=False, timeout=150, capture_output=True)
    except Exception as e:
        print(f"提示发送失败: {e}")


# ================= 派生指数入库 =================

def insert_ratio(
    cursor: sqlite3.Cursor,
    name1: str,
    name2: str,
    result_name: str,
    op: Callable[[float, float], float] = lambda a, b: a / b,
    digits: int = 2
) -> Tuple[int, Optional[int]]:
    """取 name1/name2 最新日期数据，按 op 计算后插入 result_name；已存在则跳过。"""
    cursor.execute("SELECT MAX(date) FROM Currencies WHERE name IN (?, ?)", (name1, name2))
    row = cursor.fetchone()
    if not row or not row[0]:
        raise ValueError(f"没有找到 {name1}/{name2} 的任何数据")
    latest_date = row[0]

    cursor.execute("SELECT 1 FROM Currencies WHERE name = ? AND date = ?", (result_name, latest_date))
    if cursor.fetchone():
        print(f"数据已存在: '{result_name}' 在 {latest_date} 的记录已存在，跳过插入。")
        return 0, None

    cursor.execute("SELECT price FROM Currencies WHERE name = ? AND date = ?", (name1, latest_date))
    r = cursor.fetchone()
    if not r:
        raise ValueError(f"{latest_date} 没有 {name1} 的数据")
    price1 = r[0]

    cursor.execute("SELECT price FROM Currencies WHERE name = ? AND date = ?", (name2, latest_date))
    r = cursor.fetchone()
    if not r:
        raise ValueError(f"{latest_date} 没有 {name2} 的数据")
    price2 = r[0]

    result = round(op(price1, price2), digits)
    print(f"正在插入: '{result_name}' 在 {latest_date} 的数据，值为 {result}")
    cursor.execute("INSERT INTO Currencies (date, name, price) VALUES (?, ?, ?)",
                   (latest_date, result_name, result))
    return cursor.rowcount, cursor.lastrowid


def Insert_DB() -> bool:
    """返回 True 表示成功（不再在内部 sys.exit，便于调用方决定后续行为）"""
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    cursor = conn.cursor()
    jobs = [
        ('DXY', 'USDCNY', 'CNYI', lambda a, b: a / b, 3),
        ('DXY', 'USDJPY', 'JPYI', lambda a, b: a / b, 4),
        ('DXY', 'EURUSD', 'EURI', lambda a, b: a * b, 2),
        ('DXY', 'USDCHF', 'CHFI', lambda a, b: a / b, 2),
        ('DXY', 'GBPUSD', 'GBPI', lambda a, b: a * b, 2),
    ]
    try:
        for n1, n2, res, op, digits in jobs:
            cnt, lid = insert_ratio(cursor, n1, n2, res, op=op, digits=digits)
            if cnt > 0:
                print(f"{res} 插入: {cnt} 条 (lastrowid={lid})")
        conn.commit()
        print("\n数据库操作完成。")
        return True
    except ValueError as ve:
        print("数据准备失败：", ve)
    except sqlite3.IntegrityError as ie:
        print("插入失败，可能违反唯一性约束：", ie)
    except sqlite3.DatabaseError as de:
        print("数据库错误：", de)
    conn.rollback()
    return False


# ================= 工具函数 =================

def read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误：JSON 文件未找到 {path}")
    except json.JSONDecodeError:
        print(f"错误：JSON 文件格式错误 {path}")
    return {}


def write_json(path, data):
    """原子写入：先写临时文件再替换，避免写一半被中断导致 JSON 损坏"""
    dir_name = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def get_last_trading_day() -> str:
    """距今最近的一个 NYSE 交易日（不含今天）"""
    nyse = mcal.get_calendar('NYSE')
    today = datetime.now().date()
    schedule = nyse.schedule(
        start_date=(today - timedelta(days=30)).strftime('%Y-%m-%d'),
        end_date=(today - timedelta(days=1)).strftime('%Y-%m-%d'),
    )
    if schedule.empty:
        raise RuntimeError("过去 30 天内找不到任何 NYSE 交易日，请检查日历配置。")
    last_day = schedule.index[-1].strftime('%Y-%m-%d')
    print(f"[INFO] 本次检查的目标交易日: {last_day}")
    return last_day


def load_existing_names(conn, table, date_str):
    """一次性取出某表在 date_str 已存在的全部 name（替代原来每个 symbol 开一次连接）"""
    safe_table = '"' + str(table).replace('"', '""') + '"'
    try:
        cur = conn.execute(f"SELECT DISTINCT name FROM {safe_table} WHERE date = ?", (date_str,))
        return {r[0] for r in cur.fetchall()}
    except sqlite3.Error as e:
        print(f"数据库查询错误: {e} (表: {table})，该表全部按缺失处理")
        return set()


# ================= 主流程 =================

def main() -> int:
    parser = argparse.ArgumentParser(description="Check yesterday data script")
    parser.add_argument('--nopop', action='store_true',
                        help="不弹对话框，只发系统通知（无人值守时自动生效）")
    parser.add_argument('--ignore_sectors', action='store_true', help="排除特定板块的缺失检查")
    args = parser.parse_args()

    popup = not args.nopop
    is_ignore_sectors_on = EXCLUDE_SECTORS_SWITCH or args.ignore_sectors

    try:
        target_date = get_last_trading_day()
    except RuntimeError as e:
        notify(f"错误：{e}", popup)
        return 1

    if os.path.exists(ERROR_FILE):
        os.remove(ERROR_FILE)

    sectors_all = read_json(SECTORS_ALL_JSON)
    sector_empty = read_json(SECTOR_EMPTY_JSON)
    if not sectors_all:
        notify("错误：Sectors_All.json 为空或读取失败，脚本终止。", popup)
        return 1

    for tbl in sectors_all:
        sector_empty.setdefault(tbl, [])

    missing_found = False
    added_count = 0

    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    try:
        for table, names_in_table in sectors_all.items():
            if is_ignore_sectors_on and table in EXCLUDE_SECTORS_LIST:
                print(f"提示：已开启排除开关，跳过检查板块 '{table}'。")
                continue
            if not isinstance(names_in_table, list):
                print(f"警告：Sectors_All.json 中表 '{table}' 的值不是列表，已跳过。")
                continue

            existing = load_existing_names(conn, table, target_date)
            if not isinstance(sector_empty.get(table), list):
                sector_empty[table] = []
            already = set(sector_empty[table])

            table_added = 0
            for name in names_in_table:
                if name in FILTER_LIST or name in existing:
                    continue
                missing_found = True
                if name not in already:
                    sector_empty[table].append(name)
                    already.add(name)
                    added_count += 1
                    table_added += 1
            if table_added:
                print(f"  [{table}] 新增缺失 {table_added} 个")
    finally:
        conn.close()

    if added_count > 0:
        write_json(SECTOR_EMPTY_JSON, sector_empty)
        notify(f"今天新增了 {added_count} 个缺失内容已注入 empty 文件！", popup)
        return 0

    if missing_found:
        print("数据库仍有缺失数据，且已记录在 empty 文件中，请先处理。")
        return 0

    if Insert_DB():
        notify("包含CNYI等所有数据都已成功入库，没有遗漏。", popup)
        return 0
    notify("数据都已入库，但 CNYI 等派生指数计算/入库失败，请查看终端输出。", popup)
    return 1


if __name__ == '__main__':
    sys.exit(main())