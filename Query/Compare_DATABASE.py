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
        # 理论上，如果 get_table_primary_key 成功返回了 id_column，
        # 那么 SELECT * 的结果中应该包含这一列。
        # 但为保险起见，可以添加错误处理。
        print(f"错误：在表 {table_name} 的查询结果中未找到主键列 {id_column}。")
        return {}
    idx = columns.index(id_column)
    data_dict = {row[idx]: row for row in rows}
    return data_dict

def compare_table_data(table_name, data1, data2):
    # table_name 参数在此函数中未被使用，可以考虑移除或在未来用于更详细的日志
    diff_ids = []
    all_ids = set(data1.keys()).union(set(data2.keys()))
    for record_id in all_ids: # 将变量名 id 改为 record_id 以避免与内置函数 id冲突
        row1 = data1.get(record_id)
        row2 = data2.get(record_id)
        if row1 != row2:
            diff_ids.append(record_id)
    return diff_ids

def main(db1_path, db2_path):
    conn1 = sqlite3.connect(db1_path)
    conn2 = sqlite3.connect(db2_path)

    cursor1 = conn1.cursor()
    cursor2 = conn2.cursor()

    cursor1.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables1_tuples = cursor1.fetchall()
    cursor2.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables2_tuples = cursor2.fetchall()

    tables1 = set([table[0] for table in tables1_tuples])
    tables2 = set([table[0] for table in tables2_tuples])
    common_tables = tables1.intersection(tables2)

    for table in common_tables:
        id_column1 = get_table_primary_key(conn1, table)
        id_column2 = get_table_primary_key(conn2, table)
        
        if id_column1 is None and id_column2 is None:
            print(f"表 {table} 在两个数据库中均缺少主键。")
            continue
        elif id_column1 is None:
            print(f"表 {table} 在第一个数据库中缺少主键 (DB2 主键: {id_column2})。")
            continue
        elif id_column2 is None:
            print(f"表 {table} 在第二个数据库中缺少主键 (DB1 主键: {id_column1})。")
            continue
        elif id_column1 != id_column2:
            print(f"表 {table} 的主键不匹配。DB1 主键: {id_column1}, DB2 主键: {id_column2}。")
            continue
        
        # 此时 id_column1 和 id_column2 相同且不为 None
        primary_key_column = id_column1 
        
        data1 = get_table_data_as_dict(conn1, table, primary_key_column)
        data2 = get_table_data_as_dict(conn2, table, primary_key_column)
        
        diff_ids = compare_table_data(table, data1, data2)
        if diff_ids:
            print(f"表 {table} 在以下ID的数据存在差异: {diff_ids}")
            # --- 新增代码开始 ---
            print(f"在表 {table} 中，总共有 {len(diff_ids)} 个不同的ID。")
            # --- 新增代码结束 ---
        else:
            print(f"表 {table} 没有数据差异。")

    conn1.close()
    conn2.close()

if __name__ == "__main__":
    # 请确保路径正确，如果路径包含中文或特殊字符，可能需要特别处理或使用原始字符串 (r"路径")
    db1_path = '/Users/yanzhang/Downloads/backup/DB_backup/Finance.db'
    db2_path = '/Users/yanzhang/Documents/Database/Finance.db'
    main(db1_path, db2_path)