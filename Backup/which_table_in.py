import sqlite3
import json

def find_tables_with_flo(db_path):
    # 连接到数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [table[0] for table in cursor.fetchall()]

    # 存储包含 'FLO' 的表名
    tables_with_flo = []

    # 查询每个表
    for table in tables:
        query = f"SELECT 1 FROM '{table}' WHERE name = 'FLO' LIMIT 1"
        try:
            cursor.execute(query)
            if cursor.fetchone():
                tables_with_flo.append(table)
        except sqlite3.OperationalError:
            # 如果表结构不符合预期，跳过该表
            continue

    # 关闭数据库连接
    conn.close()

    return tables_with_flo

# 使用示例
db_path = '/Users/yanzhang/Documents/Database/Finance.db'
result = find_tables_with_flo(db_path)

print(json.dumps({"Tables containing 'FLO'": result}, indent=2))