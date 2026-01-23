#!/usr/bin/env python3
# a.py

import sys
import sqlite3

def get_table_primary_key(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = cursor.fetchall()
    for column in columns:
        if column[5] == 1:  # PK 标记在第 6 项
            return column[1]
    return None

def get_table_data_as_dict(conn, table_name, id_column):
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name};")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    if id_column not in columns:
        print(f"错误：在表 {table_name} 的查询结果中未找到主键列 {id_column}。")
        return {}, columns
    idx = columns.index(id_column)

    data_dict = {}
    for row in rows:
        if idx < len(row):
            data_dict[row[idx]] = row
        else:
            print(f"警告：表 {table_name} 中，行 {row} 长度不足以获取主键 {id_column}。")
    return data_dict, columns

def get_table_columns(conn, table_name):
    """返回表的列名列表（按定义顺序）。"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name});")
    return [info[1] for info in cursor.fetchall()]

def compare_table_data(data1, data2):
    ids_only_in_db1 = []
    ids_only_in_db2 = []
    ids_with_mismatched_data = []

    all_ids = set(data1.keys()).union(data2.keys())
    for record_id in all_ids:
        row1 = data1.get(record_id)
        row2 = data2.get(record_id)
        if row1 is not None and row2 is None:
            ids_only_in_db1.append(record_id)
        elif row1 is None and row2 is not None:
            ids_only_in_db2.append(record_id)
        elif row1 != row2:
            ids_with_mismatched_data.append(record_id)
    return ids_only_in_db1, ids_only_in_db2, ids_with_mismatched_data

def main(db1_path, db2_path):
    class Colors:
        RED = '\033[91m'
        RESET = '\033[0m'

    conn1 = sqlite3.connect(db1_path)
    conn2 = sqlite3.connect(db2_path)
    c1 = conn1.cursor()
    c2 = conn2.cursor()

    c1.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables1 = {t[0] for t in c1.fetchall() if t[0] != 'sqlite_sequence'}
    c2.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables2 = {t[0] for t in c2.fetchall() if t[0] != 'sqlite_sequence'}

    # 表级别差异
    only1 = tables1 - tables2
    only2 = tables2 - tables1
    if only1:
        print(f"{Colors.RED}--- 仅在 {db1_path} 中存在的表 ---{Colors.RESET}")
        for t in sorted(only1):
            print(f"{Colors.RED}{t}{Colors.RESET}")
        print("-"*40)
    if only2:
        print(f"{Colors.RED}--- 仅在 {db2_path} 中存在的表 ---{Colors.RESET}")
        for t in sorted(only2):
            print(f"{Colors.RED}{t}{Colors.RESET}")
        print("-"*40)

    common = sorted(tables1 & tables2)
    if common:
        print("--- 开始比较共有表的数据 ---")

    for table in common:
        id1 = get_table_primary_key(conn1, table)
        id2 = get_table_primary_key(conn2, table)
        if not id1 or not id2 or id1 != id2:
            print(f"表 {table}: 主键不匹配或缺失，跳过。 (DB1={id1}, DB2={id2})")
            print("-"*40)
            continue

        data1, cols1 = get_table_data_as_dict(conn1, table, id1)
        data2, _     = get_table_data_as_dict(conn2, table, id1)
        only_in_1, only_in_2, mismatched = compare_table_data(data1, data2)
        total = len(only_in_1) + len(only_in_2) + len(mismatched)

        if total == 0:
            print(f"表 {table}: 无差异。")
            print("-"*40)
            continue

        print(f"表 {table} 存在差异，共 {total} 条：")
        for rid in sorted(set(only_in_1 + only_in_2 + mismatched)):
            if rid in only_in_1:
                print(f"  ID={rid} 仅在 第一个数据库 存在")
            elif rid in only_in_2:
                print(f"  ID={rid} 仅在 第二个数据库 存在")
            else:
                print(f"  ID={rid} 在两库均存在，但数据不一致")

        # 如果是 Bonds 表，输出字段级差异
        if table == 'sync_log' and mismatched:
            print("  >>> Bonds 表字段级差异详情:")
            cols = get_table_columns(conn1, table)
            for rid in sorted(mismatched):
                row1 = data1[rid]
                row2 = data2[rid]
                print(f"    -- ID={rid} 的字段差异 --")
                for idx, col in enumerate(cols):
                    v1 = row1[idx] if idx < len(row1) else None
                    v2 = row2[idx] if idx < len(row2) else None
                    if v1 != v2:
                        print(f"       字段 {col}: DB1 = {v1!r} | DB2 = {v2!r}")
            print("  <<< End of Bonds 详情")

        print("-"*40)

    conn1.close()
    conn2.close()

if __name__ == '__main__':
    db1 = '/Users/yanzhang/Coding/Database/Finance copy.db'
    db2 = '/Users/yanzhang/Coding/Database/Finance.db'
    out_file = '/Users/yanzhang/Downloads/a.txt'

    # 重定向所有 print 到文件
    with open(out_file, 'w', encoding='utf-8') as f:
        orig = sys.stdout
        sys.stdout = f
        try:
            main(db1, db2)
        finally:
            sys.stdout = orig

    print(f"比较结果已写入 {out_file}")