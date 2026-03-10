import json
import sqlite3
import os
import sys
import argparse # 1. 导入 argparse
import subprocess
from datetime import datetime, timedelta
from typing import Callable, Tuple, Optional
import pandas_market_calendars as mcal

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")

# -------- 请根据实际情况修改下面这几个路径 -------- #
DB_PATH = os.path.join(BASE_CODING_DIR, "Database", "Finance.db")
SECTORS_ALL_JSON = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_All.json")
SECTOR_EMPTY_JSON = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Sectors_empty.json")
ERROR_FILE = os.path.join(BASE_CODING_DIR, "News", "Today_error2.txt")

# 不需要写入 empty 的 symbol
FILTER_LIST = {
    'USInterest', 'USGDP', 'USCPI', 'USNonFarmA', 'USRetailM', 'USUnemploy',
    'USNonFarm', 'USConfidence', 'USInitial', 'USPPI', 'USNonPMI', 'CorePPI',
    'PCEY', 'CorePCEY', 'CorePCEM', 'CoreCPI', 'USConspending', 'ImportPriceM',
    'ImportPriceY', 'USTrade', 'CNYI', 'JPYI', 'EURI', 'CHFI', 'GBPI'
}

def insert_ratio(
    cursor: sqlite3.Cursor,
    name1: str,
    name2: str,
    result_name: str,
    op: Callable[[float, float], float] = lambda a, b: a / b,
    digits: int = 2
) -> Tuple[int, Optional[int]]:
    """
    取 name1/name2 最新日期的数据，按 op(name1_price, name2_price) 计算结果，
    四舍五入到小数点后 digits 位，插入到 result_name。
    如果 result_name 在该日期的数据已存在，则跳过。
    返回 (插入条数, lastrowid)。
    """
    # 1) 找最新日期
    cursor.execute(
        "SELECT MAX(date) FROM Currencies WHERE name IN (?, ?)",
        (name1, name2)
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        raise ValueError(f"没有找到 {name1}/{name2} 的任何数据")
    latest_date = row[0]

    # -------- 新增的核心逻辑：在插入前检查数据是否已存在 -------- #
    cursor.execute(
        "SELECT 1 FROM Currencies WHERE name = ? AND date = ?",
        (result_name, latest_date)
    )
    if cursor.fetchone():
        # 如果 fetchone() 返回了东西，说明数据已存在
        print(f"数据已存在: '{result_name}' 在 {latest_date} 的记录已存在，跳过插入。")
        return 0, None  # 返回 0 表示没有行被插入, lastrowid 为 None
    # ---------------------------------------------------- #

    # 2) 取两个品种的 price (仅当数据不存在时才执行)
    cursor.execute(
        "SELECT price FROM Currencies WHERE name = ? AND date = ?",
        (name1, latest_date)
    )
    r = cursor.fetchone()
    if not r:
        raise ValueError(f"{latest_date} 没有 {name1} 的数据")
    price1 = r[0]

    cursor.execute(
        "SELECT price FROM Currencies WHERE name = ? AND date = ?",
        (name2, latest_date)
    )
    r = cursor.fetchone()
    if not r:
        raise ValueError(f"{latest_date} 没有 {name2} 的数据")
    price2 = r[0]

    # 3) 计算并插入（保留 digits 位小数）
    raw = op(price1, price2)
    result = round(raw, digits)

    print(f"正在插入: '{result_name}' 在 {latest_date} 的数据，值为 {result}")
    cursor.execute(
        "INSERT INTO Currencies (date, name, price) VALUES (?, ?, ?)",
        (latest_date, result_name, result)
    )
    return cursor.rowcount, cursor.lastrowid

def Insert_DB():
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    cursor = conn.cursor()

    try:
        # CNYI = DXY / USDCNY，保留 3 位小数
        cnt1, lid1 = insert_ratio(
            cursor,
            'DXY',
            'USDCNY',
            'CNYI',
            digits=3
        )
        if cnt1 > 0:
            print(f"CNYI 插入: {cnt1} 条 (lastrowid={lid1})")

        # JPYI = DXY / USDJPY，保留 4 位小数
        cnt2, lid2 = insert_ratio(
            cursor,
            'DXY',
            'USDJPY',
            'JPYI',
            digits=4
        )
        if cnt2 > 0:
            print(f"JPYI 插入: {cnt2} 条 (lastrowid={lid2})")

        # EURI = DXY * EURUSD，使用默认 2 位小数
        cnt3, lid3 = insert_ratio(
            cursor,
            'DXY',
            'EURUSD',
            'EURI',
            op=lambda a, b: a * b
        )
        if cnt3 > 0:
            print(f"EURI 插入: {cnt3} 条 (lastrowid={lid3})")

        # CHFI = DXY / USDCHF，使用默认 2 位小数
        cnt4, lid4 = insert_ratio(
            cursor,
            'DXY',
            'USDCHF',
            'CHFI'
        )
        if cnt4 > 0:
            print(f"CHFI 插入: {cnt4} 条 (lastrowid={lid4})")

        # GBPI = DXY * GBPUSD，使用默认 2 位小数
        cnt5, lid5 = insert_ratio(
            cursor,
            'DXY',
            'GBPUSD',
            'GBPI',
            op=lambda a, b: a * b
        )
        if cnt5 > 0:
            print(f"GBPI 插入: {cnt5} 条 (lastrowid={lid5})")

        conn.commit()
        print("\n数据库操作完成。")

    except ValueError as ve:
        print("数据准备失败：", ve)
        conn.rollback()
        sys.exit(1)
    except sqlite3.IntegrityError as ie:
        # 这个错误现在不太可能因为重复数据而触发，但保留它是好习惯，以防其他约束问题
        print("插入失败，可能违反唯一性约束：", ie)
        conn.rollback()
        sys.exit(1)
    except sqlite3.DatabaseError as de:
        print("数据库错误：", de)
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

def read_json(path):
    """读取 JSON 文件并返回 Python 对象"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误：JSON 文件未找到 {path}")
        return {} # 返回空字典，避免后续出错
    except json.JSONDecodeError:
        print(f"错误：JSON 文件格式错误 {path}")
        return {} # 返回空字典


def write_json(path, data):
    """将 Python 对象写回 JSON，保持易读格式"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_last_trading_day() -> str:
    """
    返回距今最近的一个 NYSE 交易日（自动跳过周末和美国市场节假日）。
    向前最多查 30 天，足够覆盖任何连续长假。
    """
    nyse = mcal.get_calendar('NYSE')
    today = datetime.now().date()
    start = today - timedelta(days=30)
    end   = today - timedelta(days=1)   # 不包含今天本身

    schedule = nyse.schedule(
        start_date=start.strftime('%Y-%m-%d'),
        end_date=end.strftime('%Y-%m-%d')
    )

    if schedule.empty:
        raise RuntimeError("过去 30 天内找不到任何 NYSE 交易日，请检查日历配置。")

    last_day = schedule.index[-1].strftime('%Y-%m-%d')
    print(f"[INFO] 本次检查的目标交易日: {last_day}")
    return last_day

def query_data(table, name):
    """查询 SQLite，看表 table 中 name 和昨天日期的数据是否存在"""
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT 1 FROM {table} WHERE name = ? AND date = ?", (name, yesterday))
        found = cur.fetchone() is not None
    except sqlite3.Error as e:
        print(f"数据库查询错误: {e} (表: {table}, 名称: {name})")
        found = False # 假设查询失败等同于未找到，或者可以抛出异常
    finally:
        conn.close()
    return found


def write_error(msg):
    """追加写入错误日志"""
    with open(ERROR_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

def show_alert(message):
    """
    如果 Today_error.txt 不存在，则弹出 macOS 对话框警告，
    避免脚本无声卡住。
    """
    # 转义双引号，免得 AppleScript 语法错
    safe_msg = message.replace('"', '\\"')
    applescript = (
        f'display dialog "{safe_msg}" buttons {{"OK"}} default button "OK" '
        f'with title "脚本提示"'
    )
    try:
        subprocess.run(['osascript', '-e', applescript], check=True)
    except FileNotFoundError:
        print("osascript 命令未找到。无法显示 macOS 对话框。")
        print(f"提示信息: {message}") # 在控制台打印信息作为备用
    except subprocess.CalledProcessError as e:
        print(f"执行 AppleScript 时出错: {e}")
        print(f"提示信息: {message}") # 在控制台打印信息作为备用


def open_error_file():
    """
    尝试打开 ERROR_FILE；若不存在，就弹对话框提示。
    macOS 下用 open，Windows 下可改为 notepad。
    """
    if os.path.exists(ERROR_FILE):
        os.system(f"open {ERROR_FILE}")
    else:
        show_alert("所有数据都已成功入库，没有遗漏。")


def main():
    global yesterday  # 声明修改全局变量

    # 1. 设置参数解析
    parser = argparse.ArgumentParser(description="Check yesterday data script")
    parser.add_argument('--nopop', action='store_true', help="是否强制弹出提示框")
    args = parser.parse_args()

    # ★ 在这里动态获取最近交易日，替代原来的静态 yesterday
    try:
        yesterday = get_last_trading_day()
    except RuntimeError as e:
        print(f"错误：{e}")
        show_alert(str(e))
        return

    # 后续代码完全不变 ...
    if os.path.exists(ERROR_FILE):
        os.remove(ERROR_FILE)

    # 1. 读入 sectors 全量表 & empty 模板 & 符号映射表
    sectors_all = read_json(SECTORS_ALL_JSON)
    sector_empty = read_json(SECTOR_EMPTY_JSON)

    if not sectors_all: # 如果读取失败返回了空字典
        print("错误：Sectors_All.json 为空或读取失败，脚本终止。")
        show_alert("错误：Sectors_All.json 为空或读取失败，脚本终止。")
        return

    # 确保 empty 至少有所有表的 key
    for tbl in sectors_all:
        sector_empty.setdefault(tbl, [])

    # 标志：是否有缺失
    missing_found = False
    # --- 新增：计数器 ---
    added_count = 0

    # 2. 遍历各表各 symbol
    for table, names_in_table in sectors_all.items():
        if not isinstance(names_in_table, list):
            print(f"警告：Sectors_All.json 中表 '{table}' 的值不是列表，已跳过。")
            continue

        for original_name in names_in_table: # original_name 是 sectors_all.json 中的名称，如 "Korea"
            if original_name in FILTER_LIST:
                continue

            if not query_data(table, original_name):
                # 第一次写错误时把标志置为 True
                missing_found = True
                
                # --- 修改点：直接使用 original_name，不再进行映射 ---
                # print(f"信息：'{original_name}' 缺失，直接写入 empty。")
                if not isinstance(sector_empty.get(table), list):
                    sector_empty[table] = []
                
                # 只有当该项确实不存在于列表中时，才进行添加并计数
                if original_name not in sector_empty[table]:
                    sector_empty[table].append(original_name)
                    added_count += 1 # 计数器自增

     # 3. 根据情况决定后续行为
    if added_count > 0:
        # 情况 1: 有新缺失 (added_count > 0)
        # 写入 JSON，并提示用户
        write_json(SECTOR_EMPTY_JSON, sector_empty)
        
        msg = f"今天新增了 {added_count} 个缺失内容已注入 empty 文件！"
        if args.nopop:
            show_alert(msg)
        else:
            print(f"{msg} (未开启弹框)")

    elif missing_found:
        # 情况 2: 没有新缺失，但数据库仍有缺失 (missing_found 为 True)
        # 说明这些缺失在 JSON 里已经存在了，不需要再写 JSON，但也不应该执行入库
        msg = "数据库仍有缺失数据，且已记录在 empty 文件中，请先处理。"
        print(msg)

    else:
        # 情况 3: 数据库没有任何缺失 (missing_found 为 False)
        # 一切正常，执行入库
        Insert_DB()
        show_alert("包含CNYI等所有数据都已成功入库，没有遗漏。")

if __name__ == '__main__':
    main()