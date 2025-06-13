import sqlite3
import sys
from typing import Callable, Tuple, Dict, Set

db_path = '/Users/yanzhang/Documents/Database/Finance.db'

def fill_missing_ratio_data(
    cursor: sqlite3.Cursor,
    name1: str,
    name2: str,
    result_name: str,
    op: Callable[[float, float], float] = lambda a, b: a / b,
    digits: int = 2
) -> int:
    """
    补充 result_name 的历史缺失数据。
    数据基于 name1 和 name2 在相同日期的数据，通过 op 计算得到。
    如果某日期的 result_name 数据已存在，则不会重复插入。
    返回实际插入的条数。
    """
    print(f"\n开始为 {result_name} 检查并补充历史缺失数据...")

    # 1. 获取 name1 的所有 (date, price) 数据
    cursor.execute("SELECT date, price FROM Currencies WHERE name = ? ORDER BY date", (name1,))
    data1_map: Dict[str, float] = {row[0]: row[1] for row in cursor.fetchall()}
    if not data1_map:
        print(f"警告: 未找到 {name1} 的任何数据，无法为 {result_name} 补充数据。")
        return 0

    # 2. 获取 name2 的所有 (date, price) 数据
    cursor.execute("SELECT date, price FROM Currencies WHERE name = ? ORDER BY date", (name2,))
    data2_map: Dict[str, float] = {row[0]: row[1] for row in cursor.fetchall()}
    if not data2_map:
        print(f"警告: 未找到 {name2} 的任何数据，无法为 {result_name} 补充数据。")
        return 0

    # 3. 获取 result_name 已有的所有日期
    cursor.execute("SELECT date FROM Currencies WHERE name = ?", (result_name,))
    existing_result_dates: Set[str] = {row[0] for row in cursor.fetchall()}
    print(f"{result_name} 当前已有 {len(existing_result_dates)} 条数据。")

    # 4. 找出 name1 和 name2 都有数据，但 result_name 缺失的日期
    dates_to_fill = []
    # 获取 name1 和 name2 共同拥有的日期
    common_dates_name1_name2 = set(data1_map.keys()) & set(data2_map.keys())

    for date_val in sorted(list(common_dates_name1_name2)): # 按日期排序处理，便于观察
        if date_val not in existing_result_dates:
            dates_to_fill.append(date_val)

    if not dates_to_fill:
        print(f"✅ 没有找到需要为 {result_name} 补充的历史数据。")
        return 0

    print(f"找到 {len(dates_to_fill)} 个日期需要为 {result_name} 补充数据。")

    # 5. 遍历这些日期，计算并插入数据
    inserted_count = 0
    for date_to_process in dates_to_fill:
        price1 = data1_map.get(date_to_process)
        price2 = data2_map.get(date_to_process)

        # 这层检查理论上不需要，因为 common_dates_name1_name2 保证了两者都有数据
        if price1 is None or price2 is None:
            print(f"内部逻辑错误：在日期 {date_to_process} 未能同时获取 {name1} ({price1}) 和 {name2} ({price2}) 的价格，跳过。")
            continue

        try:
            raw_value = op(price1, price2)
            result_value = round(raw_value, digits)

            cursor.execute(
                "INSERT INTO Currencies (date, name, price) VALUES (?, ?, ?)",
                (date_to_process, result_name, result_value)
            )
            if cursor.rowcount > 0:
                inserted_count += 1
                # print(f"  为 {result_name} 在日期 {date_to_process} 插入数据: {result_value} (由 {name1}:{price1} 和 {name2}:{price2} 计算)")
        except ZeroDivisionError:
            print(f"警告：在日期 {date_to_process} 计算 {result_name} 时发生除零错误 ({name1}={price1}, {name2}={price2})，跳过。")
        except sqlite3.IntegrityError:
            # 理论上不应发生，因为我们已经检查了 existing_result_dates
            # 但如果存在并发操作或数据不一致，这可以作为一道防线
            print(f"警告：在日期 {date_to_process} 插入 {result_name} 时违反唯一性约束（数据可能已存在），跳过。")
        except Exception as e:
            print(f"警告：在日期 {date_to_process} 处理 {result_name} 时发生错误: {e}，跳过。")
    
    if inserted_count > 0:
        print(f"✅ 成功为 {result_name} 补充了 {inserted_count} 条历史数据。")
    else:
        print(f"🤔 {result_name} 没有补充新的历史数据（可能都已存在或无法计算）。")
    return inserted_count


def insert_ratio(
    cursor: sqlite3.Cursor,
    name1: str,
    name2: str,
    result_name: str,
    op: Callable[[float, float], float] = lambda a, b: a / b,
    digits: int = 2
) -> Tuple[int, int]:
    """
    取 name1/name2 最新共同日期的数据，按 op 计算结果并插入或更新。
    - 如果目标数据不存在，则插入。
    - 如果目标数据已存在但值不同，则更新。
    - 如果目标数据已存在且值相同，则跳过。
    返回 (操作行数, lastrowid)。
    - 插入: (1, new_id)
    - 更新: (1, -1)
    - 跳过: (0, -1)
    """
    # 1) 找 name1 和 name2 共同的最新日期
    cursor.execute(
        """
        SELECT T1.date
        FROM Currencies T1
        INNER JOIN Currencies T2 ON T1.date = T2.date
        WHERE T1.name = ? AND T2.name = ?
        ORDER BY T1.date DESC
        LIMIT 1
        """, (name1, name2)
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        raise ValueError(f"没有找到 {name1} 和 {name2} 拥有共同数据的任何日期")
    latest_date = row[0]
    
    # print(f"找到 {name1} 和 {name2} 的最新共同日期: {latest_date}")

    # 2) 取两个品种在该最新日期的 price
    cursor.execute(
        "SELECT price FROM Currencies WHERE name = ? AND date = ?",
        (name1, latest_date)
    )
    r = cursor.fetchone()
    if not r: # 理论上不会发生，因为上面的查询保证了数据存在
        raise ValueError(f"{latest_date} 没有 {name1} 的数据（逻辑错误）")
    price1 = r[0]

    cursor.execute(
        "SELECT price FROM Currencies WHERE name = ? AND date = ?",
        (name2, latest_date)
    )
    r = cursor.fetchone()
    if not r: # 理论上不会发生
        raise ValueError(f"{latest_date} 没有 {name2} 的数据（逻辑错误）")
    price2 = r[0]

    # 检查目标数据是否已存在
    cursor.execute(
        "SELECT price FROM Currencies WHERE date = ? AND name = ?",
        (latest_date, result_name)
    )
    existing_data = cursor.fetchone()
    
    raw = op(price1, price2)
    result = round(raw, digits)

    if existing_data:
        if abs(existing_data[0] - result) < (10**-(digits+1)): # 比较浮点数，允许微小误差
            # print(f"{result_name} 在 {latest_date} 的数据已存在且值相同 ({result})，跳过最新数据插入。")
            return 0, -1 
        else:
            # 如果值不同，执行更新操作
            print(f"🔄 信息: {result_name} 在 {latest_date} 的数据已存在但值不同，将执行更新。")
            print(f"    数据库旧值: {existing_data[0]}")
            print(f"    新计算值:   {result}")
            cursor.execute(
                "UPDATE Currencies SET price = ? WHERE date = ? AND name = ?",
                (result, latest_date, result_name)
            )
            # 返回更新的行数 (通常是1) 和 -1 (因为没有新 lastrowid)
            return cursor.rowcount, -1

    # 3) 如果数据不存在，则计算并插入
    cursor.execute(
        "INSERT INTO Currencies (date, name, price) VALUES (?, ?, ?)",
        (latest_date, result_name, result)
    )
    return cursor.rowcount, cursor.lastrowid

def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # --- 首先，补充历史缺失数据 ---
        # 为 CNYI 补充历史数据
        fill_missing_ratio_data(cursor, 'DXY', 'USDCNY', 'CNYI', op=lambda a, b: a / b, digits=3)
        # 为 JPYI 补充历史数据
        fill_missing_ratio_data(cursor, 'DXY', 'USDJPY', 'JPYI', op=lambda a, b: a / b, digits=4)
        # 为 EURI 补充历史数据
        fill_missing_ratio_data(cursor, 'DXY', 'EURUSD', 'EURI', op=lambda a, b: a * b, digits=2)
        # 为 CHFI 补充历史数据
        fill_missing_ratio_data(cursor, 'DXY', 'USDCHF', 'CHFI', op=lambda a, b: a / b, digits=2)
        # 为 GBPI 补充历史数据
        fill_missing_ratio_data(cursor, 'DXY', 'GBPUSD', 'GBPI', op=lambda a, b: a * b, digits=2)

        print("\n开始处理（或确认）最新日期的数据：")
        
        # --- 然后，处理（或确认）最新日期的数据 ---
        # 定义要处理的指数列表，简化代码
        ratios_to_process = [
            {'n1': 'DXY', 'n2': 'USDCNY', 'res': 'CNYI', 'op': lambda a, b: a / b, 'dig': 3},
            {'n1': 'DXY', 'n2': 'USDJPY', 'res': 'JPYI', 'op': lambda a, b: a / b, 'dig': 4},
            {'n1': 'DXY', 'n2': 'EURUSD', 'res': 'EURI', 'op': lambda a, b: a * b, 'dig': 2},
            {'n1': 'DXY', 'n2': 'USDCHF', 'res': 'CHFI', 'op': lambda a, b: a / b, 'dig': 2},
            {'n1': 'DXY', 'n2': 'GBPUSD', 'res': 'GBPI', 'op': lambda a, b: a * b, 'dig': 2},
        ]

        for r in ratios_to_process:
            cnt, lid = insert_ratio(cursor, r['n1'], r['n2'], r['res'], op=r['op'], digits=r['dig'])
            
            if cnt > 0:  # cnt > 0 意味着发生了插入或更新
                if lid > 0:  # lid > 0 意味着是插入操作
                    date_val = cursor.execute('SELECT date FROM Currencies WHERE rowid=?', (lid,)).fetchone()[0]
                    print(f"✔️  {r['res']:<4} 最新数据已插入: {cnt} 条 (日期={date_val}, ID={lid})")
                else:  # lid == -1 意味着是更新操作
                    print(f"🔄  {r['res']:<4} 最新数据已更新。")
            else:  # cnt == 0 意味着数据已存在且值相同，跳过
                print(f"👌  {r['res']:<4} 最新数据已存在且值相同，无需操作。")


        conn.commit()
        print("\n所有操作完成并已提交。")

    except ValueError as ve:
        print("数据准备失败：", ve)
        conn.rollback()
        sys.exit(1)
    except sqlite3.IntegrityError as ie:
        # 这个错误主要可能在 fill_missing_ratio_data 中被捕获，或者 insert_ratio 未能正确处理并发/特殊情况时
        print("插入失败，可能违反唯一性约束：", ie)
        conn.rollback()
        sys.exit(1)
    except sqlite3.DatabaseError as de:
        print("数据库错误：", de)
        conn.rollback()
        sys.exit(1)
    except Exception as e:
        print(f"发生未预料的错误: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    main()