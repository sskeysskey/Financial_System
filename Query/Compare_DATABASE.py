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
    idx = columns.index(id_column)
    data_dict = {row[idx]: row for row in rows}
    return data_dict

def compare_table_data(table_name, data1, data2):
    diff_ids = []
    all_ids = set(data1.keys()).union(set(data2.keys()))
    for id in all_ids:
        row1 = data1.get(id)
        row2 = data2.get(id)
        if row1 != row2:
            diff_ids.append(id)
    return diff_ids

def main(db1_path, db2_path):
    conn1 = sqlite3.connect(db1_path)
    conn2 = sqlite3.connect(db2_path)

    cursor1 = conn1.cursor()
    cursor2 = conn2.cursor()

    cursor1.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables1 = cursor1.fetchall()
    cursor2.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables2 = cursor2.fetchall()

    tables1 = set([table[0] for table in tables1])
    tables2 = set([table[0] for table in tables2])
    common_tables = tables1.intersection(tables2)

    for table in common_tables:
        id_column1 = get_table_primary_key(conn1, table)
        id_column2 = get_table_primary_key(conn2, table)
        if id_column1 != id_column2 or id_column1 is None:
            print(f"Primary key mismatch or missing in table {table}.")
            continue
        
        data1 = get_table_data_as_dict(conn1, table, id_column1)
        data2 = get_table_data_as_dict(conn2, table, id_column2)
        
        diff_ids = compare_table_data(table, data1, data2)
        if diff_ids:
            print(f"Table {table} has different data on IDs: {diff_ids}")
        else:
            print(f"Table {table} has no data differences.")

    conn1.close()
    conn2.close()

if __name__ == "__main__":
    db1_path = '/Users/yanzhang/Downloads/backup/DB_backup/Finance.db'
    db2_path = '/Users/yanzhang/Documents/Database/Finance.db'
    main(db1_path, db2_path)