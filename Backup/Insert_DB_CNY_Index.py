import sqlite3
import sys
from typing import Callable, Tuple

db_path = '/Users/yanzhang/Documents/Database/Finance.db'

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

def main():
    conn = sqlite3.connect(db_path)
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

if __name__ == '__main__':
    main()