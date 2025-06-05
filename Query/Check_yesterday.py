import json
import sqlite3
import os
import sys
import subprocess
from datetime import datetime, timedelta
from typing import Callable, Tuple

# ———— 请根据实际情况修改下面这几个路径 ———— #
DB_PATH = '/Users/yanzhang/Documents/Database/Finance.db'
SECTORS_ALL_JSON = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
SECTOR_EMPTY_JSON = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
ERROR_FILE = '/Users/yanzhang/Documents/News/Today_error2.txt'
# 新增：符号映射文件路径
SYMBOL_MAPPING_JSON = '/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json'


# 不需要写入 empty 的 symbol
FILTER_LIST = {
    'USInterest', 'USGDP', 'USCPI', 'USNonFarmA', 'USRetailM', 'USUnemploy',
    'USNonFarm', 'USConfidence', 'USInitial', 'USPPI', 'USNonPMI', 'CorePPI',
    'PCEY', 'CorePCEY', 'CorePCEM', 'CoreCPI', 'USConspending', 'ImportPriceM',
    'ImportPriceY', 'USTrade', 'CNYI', 'JPYI', 'EURI', 'CHFI', 'GBPI'
}

yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


def insert_ratio(
    cursor: sqlite3.Cursor,
    name1: str,
    name2: str,
    result_name: str,
    op: Callable[[float, float], float] = lambda a, b: a / b,
    digits: int = 2
) -> Tuple[int, int]:
    """
    取 name1/name2 最新日期的数据，按 op(name1_price, name2_price) 计算结果，
    四舍五入到小数点后 digits 位，插入到 result_name。
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

    # 2) 取两个品种的 price
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

    cursor.execute(
        "INSERT INTO Currencies (date, name, price) VALUES (?, ?, ?)",
        (latest_date, result_name, result)
    )
    return cursor.rowcount, cursor.lastrowid

def Insert_DB():
    conn = sqlite3.connect(DB_PATH)
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
        print(f"CNYI 插入: {cnt1} 条 (lastrowid={lid1})")

        # JPYI = DXY / USDJPY，保留 4 位小数
        cnt2, lid2 = insert_ratio(
            cursor,
            'DXY',
            'USDJPY',
            'JPYI',
            digits=4
        )
        print(f"JPYI 插入: {cnt2} 条 (lastrowid={lid2})")

        # EURI = DXY * EURUSD，使用默认 2 位小数
        cnt3, lid3 = insert_ratio(
            cursor,
            'DXY',
            'EURUSD',
            'EURI',
            op=lambda a, b: a * b
        )
        print(f"EURI 插入: {cnt3} 条 (lastrowid={lid3})")

        # CHFI = DXY / USDCHF，使用默认 2 位小数
        cnt4, lid4 = insert_ratio(
            cursor,
            'DXY',
            'USDCHF',
            'CHFI'
        )
        print(f"CHFI 插入: {cnt4} 条 (lastrowid={lid4})")

        # GBPI = DXY * GBPUSD，使用默认 2 位小数
        cnt5, lid5 = insert_ratio(
            cursor,
            'DXY',
            'GBPUSD',
            'GBPI',
            op=lambda a, b: a * b
        )
        print(f"GBPI 插入: {cnt5} 条 (lastrowid={lid5})")

        conn.commit()

    except ValueError as ve:
        print("数据准备失败：", ve)
        conn.rollback()
        sys.exit(1)
    except sqlite3.IntegrityError as ie:
        print("插入失败，可能违反唯一性约束：", ie)
        conn.rollback()
        sys.exit(1)
    except sqlite3.DatabaseError as de:
        print("数据库错误：", de)
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

def show_alert(message):
    # AppleScript 代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    # 使用 subprocess 调用 osascript
    subprocess.run(['osascript', '-e', applescript_code], check=True)

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


def query_data(table, name):
    """查询 SQLite，看表 table 中 name 和昨天日期的数据是否存在"""
    conn = sqlite3.connect(DB_PATH)
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
    # 0. 不要一开始就清空，而是：如果存在旧的 error 文件先删掉
    if os.path.exists(ERROR_FILE):
        os.remove(ERROR_FILE)

    # 1. 读入 sectors 全量表 & empty 模板 & 符号映射表
    sectors_all = read_json(SECTORS_ALL_JSON)
    sector_empty = read_json(SECTOR_EMPTY_JSON)
    symbol_mapping_original = read_json(SYMBOL_MAPPING_JSON)

    if not sectors_all: # 如果读取失败返回了空字典
        print("错误：Sectors_All.json 为空或读取失败，脚本终止。")
        show_alert("错误：Sectors_All.json 为空或读取失败，脚本终止。")
        return

    # 反向映射
    symbol_reverse_mapping = {v: k for k, v in symbol_mapping_original.items()}

    # 确保 empty 至少有所有表的 key
    for tbl in sectors_all:
        sector_empty.setdefault(tbl, [])

    # 标志：是否有缺失
    missing_found = False

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

                err = f"在表 {table} 中找不到名称为 {original_name} 且日期为 {yesterday} 的数据"
                write_error(err)

                # 决定写入 empty 列表的符号
                if original_name in symbol_reverse_mapping:
                    symbol_to_write = symbol_reverse_mapping[original_name]
                    print(f"信息：'{original_name}' 缺失，用映射符号 '{symbol_to_write}' 写入 empty。")
                else:
                    symbol_to_write = original_name
                    print(f"信息：'{original_name}' 缺失，用原符号写入 empty。")

                # 确保是列表并去重
                if not isinstance(sector_empty.get(table), list):
                    sector_empty[table] = []
                if symbol_to_write not in sector_empty[table]:
                    sector_empty[table].append(symbol_to_write)

    # 3. 根据 missing_found 决定后续行为
    if missing_found:
        # 写回 empty JSON
        write_json(SECTOR_EMPTY_JSON, sector_empty)
        # 打开错误文件，方便查看
        open_error_file()
    else:
        Insert_DB()
        # 无任何缺失，直接弹框提示
        show_alert("所有数据都已成功入库，没有遗漏。")
if __name__ == '__main__':
    main()