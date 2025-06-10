import sqlite3

def get_table_primary_key(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = cursor.fetchall()
    for column in columns:
        if column[5] == 1:  # The 6th element in the tuple indicates whether it's a primary key
            return column[1]
    return None

def get_table_data_as_dict(conn, table_name, id_column):
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name};")
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    # 确保主键列名存在于查询结果的列名中
    if id_column not in columns:
        print(f"错误：在表 {table_name} 的查询结果中未找到主键列 {id_column}。")
        return {}
    try:
        idx = columns.index(id_column)
    except ValueError:
        # 这种情况理论上不应该发生，因为上面已经检查了 id_column in columns
        # 但为了健壮性，可以再次确认
        print(f"严重错误：主键列 {id_column} 在列名列表 {columns} 中未找到，即使之前检查通过。")
        return {}
        
    data_dict = {}
    for row in rows:
        # 确保行数据足够长以访问主键索引
        if idx < len(row):
            data_dict[row[idx]] = row
        else:
            # 这种情况可能发生在数据行不完整或存在问题时
            print(f"警告：在表 {table_name} 中，行 {row} 的长度不足以获取主键列 {id_column} (索引 {idx})。")
    return data_dict

def compare_table_data(table_name, data1, data2):
    # table_name 参数在此函数中未被使用，但保留以备将来用于更详细的日志
    
    ids_only_in_db1 = []
    ids_only_in_db2 = []
    ids_with_mismatched_data = []
    
    all_ids = set(data1.keys()).union(set(data2.keys()))
    
    for record_id in all_ids:
        row1 = data1.get(record_id)
        row2 = data2.get(record_id)
        
        if row1 is not None and row2 is None:
            ids_only_in_db1.append(record_id)
        elif row1 is None and row2 is not None:
            ids_only_in_db2.append(record_id)
        elif row1 is not None and row2 is not None:
            # 两个数据库中都存在该ID的记录
            if row1 != row2:
                ids_with_mismatched_data.append(record_id)
        # else: row1 is None and row2 is None - 这种情况不应发生，因为 record_id 来自至少一个库的keys
            
    return ids_only_in_db1, ids_only_in_db2, ids_with_mismatched_data

def main(db1_path, db2_path):
    # 定义一个内部类或直接定义变量来存储 ANSI 颜色代码
    class Colors:
        RED = '\033[91m'   # 亮红色
        RESET = '\033[0m'  # 重置颜色

    conn1 = sqlite3.connect(db1_path)
    conn2 = sqlite3.connect(db2_path)

    cursor1 = conn1.cursor()
    cursor2 = conn2.cursor()

    cursor1.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables1_tuples = cursor1.fetchall()
    cursor2.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables2_tuples = cursor2.fetchall()

    tables1 = set([table[0] for table in tables1_tuples if table[0] != 'sqlite_sequence'])
    tables2 = set([table[0] for table in tables2_tuples if table[0] != 'sqlite_sequence'])

    # --- 报告表级别的差异 (使用红色高亮) ---
    
    # 1. 找出只在 db1 中存在的表
    only_in_db1 = tables1 - tables2
    if only_in_db1:
        # 使用 f-string 将颜色代码包裹在字符串两端
        print(f"{Colors.RED}--- 仅存在于第一个数据库 ({db1_path}) 的表 ---{Colors.RESET}")
        for table in sorted(list(only_in_db1)):
            print(f"{Colors.RED}表 '{table}'{Colors.RESET}")
        print("-" * 30)

    # 2. 找出只在 db2 中存在的表
    only_in_db2 = tables2 - tables1
    if only_in_db2:
        print(f"{Colors.RED}--- 仅存在于第二个数据库 ({db2_path}) 的表 ---{Colors.RESET}")
        for table in sorted(list(only_in_db2)):
            print(f"{Colors.RED}表 '{table}'{Colors.RESET}")
        print("-" * 30)

    # --- 比较共有表的数据 (保持原样) ---
    common_tables = tables1.intersection(tables2)
    
    if common_tables:
        print("--- 开始比较共有表的数据 ---")

    for table in sorted(list(common_tables)):
        # (这部分代码与之前版本完全相同，为了简洁此处省略)
        # (在您的文件中，请保留这部分完整的代码)
        # print(f"--- 正在比较表: {table} ---")
        id_column1 = get_table_primary_key(conn1, table)
        id_column2 = get_table_primary_key(conn2, table)
        
        if id_column1 is None and id_column2 is None:
            print(f"表 {table}: 在两个数据库中均缺少主键。跳过比较。")
            print("-" * 30) # 添加分隔线
            continue
        elif id_column1 is None:
            print(f"表 {table}: 在第一个数据库中缺少主键 (DB2 主键: {id_column2})。跳过比较。")
            print("-" * 30) # 添加分隔线
            continue
        elif id_column2 is None:
            print(f"表 {table}: 在第二个数据库中缺少主键 (DB1 主键: {id_column1})。跳过比较。")
            print("-" * 30) # 添加分隔线
            continue
        elif id_column1 != id_column2:
            print(f"表 {table}: 主键不匹配。DB1 主键: {id_column1}, DB2 主键: {id_column2}。跳过比较。")
            print("-" * 30) # 添加分隔线
            continue
        
        primary_key_column = id_column1 
        
        data1 = get_table_data_as_dict(conn1, table, primary_key_column)
        data2 = get_table_data_as_dict(conn2, table, primary_key_column)
        
        ids_only_in_db1, ids_only_in_db2, ids_with_mismatched_data = compare_table_data(table, data1, data2)
        
        total_diff_count = len(ids_only_in_db1) + len(ids_only_in_db2) + len(ids_with_mismatched_data)

        if total_diff_count > 0:
            print(f"表 {table} 存在数据差异:")

            # 进一步细化到每个ID的归属
            all_differing_ids = sorted(list(set(ids_only_in_db1 + ids_only_in_db2 + ids_with_mismatched_data)))
            if len(all_differing_ids) > 0 : # 确保列表不是空的才打印
                # print(f"  详细差异说明:")
                for diff_id in all_differing_ids:
                    if diff_id in ids_only_in_db1:
                        print(f"    ID {diff_id}: 仅存在于第一个数据库 ({db1_path})。")
                    elif diff_id in ids_only_in_db2:
                        print(f"    ID {diff_id}: 仅存在于第二个数据库 ({db2_path})。")
                    elif diff_id in ids_with_mismatched_data:
                        print(f"    ID {diff_id}: 在两个数据库中均存在，但数据不一致。")
            
            print(f"  在表 {table} 中，总共有 {total_diff_count} 条记录存在差异。")
        else:
            print(f"表 {table}: 没有数据差异。")
        print("-" * 30) # 添加分隔线

    conn1.close()
    conn2.close()

if __name__ == "__main__":
    # 请确保路径正确
    db1_path = '/Users/yanzhang/Downloads/backup/DB_backup/Finance.db'
    db2_path = '/Users/yanzhang/Documents/Database/Finance.db'
    
    # db1_path = '/Users/yanzhang/Downloads/backup/DB_backup/Firstrade.db'
    # db2_path = '/Users/yanzhang/Documents/Database/Firstrade.db'
    main(db1_path, db2_path)