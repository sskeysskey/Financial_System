import sqlite3
import os

# 数据库路径
old_db_path = '/Users/yanzhang/Coding/Database/Finance.db'
new_db_path = '/Users/yanzhang/Coding/Database/Finance_new.db'

# 如果新数据库已存在，先删除它以防冲突（可选，根据需要保留或删除）
if os.path.exists(new_db_path):
    os.remove(new_db_path)

# 连接到旧数据库和新数据库
conn_old = sqlite3.connect(old_db_path)
conn_new = sqlite3.connect(new_db_path)

cursor_old = conn_old.cursor()
cursor_new = conn_new.cursor()

# 1. 定义新表的创建语句（去掉了 id，把 UNIQUE 改为 PRIMARY KEY）
create_table_queries = {
    "MNSPP": """
        CREATE TABLE IF NOT EXISTS MNSPP (
            symbol TEXT PRIMARY KEY,
            shares REAL,
            marketcap REAL,
            pe_ratio REAL,
            pb REAL
        )
    """,
    "Options": """
        CREATE TABLE IF NOT EXISTS Options (
            date TEXT,
            name TEXT,
            call TEXT,
            put TEXT,
            price REAL,
            change REAL,
            iv REAL,
            iv2 REAL,
            PRIMARY KEY(date, name)
        )
    """,
    "Earning": """
        CREATE TABLE IF NOT EXISTS Earning (
            date TEXT,
            name TEXT,
            price REAL,
            PRIMARY KEY(date, name)
        )
    """,
    "Bonds": """
        CREATE TABLE IF NOT EXISTS Bonds (
            date TEXT,
            name TEXT,
            price REAL,
            PRIMARY KEY(date, name)
        )
    """,
    "Economics": """
        CREATE TABLE IF NOT EXISTS Economics (
            date TEXT,
            name TEXT,
            price REAL,
            PRIMARY KEY(date, name)
        )
    """,
    "Currencies": """
        CREATE TABLE IF NOT EXISTS Currencies (
            date TEXT,
            name TEXT,
            price REAL,
            PRIMARY KEY(date, name)
        )
    """,
    "Indices": """
        CREATE TABLE IF NOT EXISTS Indices (
            date TEXT,
            name TEXT,
            price REAL,
            volume INTEGER,
            PRIMARY KEY(date, name)
        )
    """,
    "Commodities": """
        CREATE TABLE IF NOT EXISTS Commodities (
            date TEXT,
            name TEXT,
            price REAL,
            PRIMARY KEY(date, name)
        )
    """
}

# 包含 volume 字段的表（包括 Crypto 和其他板块表）
sector_tables = [
    "ETFs", "Basic_Materials", "Communication_Services", "Consumer_Cyclical", 
    "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare", 
    "Industrials", "Real_Estate", "Technology", "Utilities", "Crypto"
]

for table in sector_tables:
    create_table_queries[table] = f"""
        CREATE TABLE IF NOT EXISTS {table} (
            date TEXT,
            name TEXT,
            price REAL,
            volume INTEGER,
            PRIMARY KEY(date, name)
        )
    """

# 2. 在新数据库中创建所有表
for table_name, query in create_table_queries.items():
    cursor_new.execute(query)
    print(f"创建表成功: {table_name}")

# 3. 定义需要迁移数据的表及其对应的列（不包含 id）
tables_to_migrate = {
    "MNSPP": ["symbol", "shares", "marketcap", "pe_ratio", "pb"],
    "Options": ["date", "name", "call", "put", "price", "change", "iv", "iv2"],
    "Earning": ["date", "name", "price"],
    "Bonds": ["date", "name", "price"],
    "Economics": ["date", "name", "price"],
    "Currencies": ["date", "name", "price"],
    "Indices": ["date", "name", "price", "volume"],
    "Commodities": ["date", "name", "price"]
}

# 4. 迁移数据
for table_name, columns in tables_to_migrate.items():
    try:
        # 从旧数据库读取数据
        cols_str = ", ".join(columns)
        cursor_old.execute(f"SELECT {cols_str} FROM {table_name}")
        rows = cursor_old.fetchall()
        
        if rows:
            # 插入到新数据库
            placeholders = ", ".join(["?"] * len(columns))
            insert_query = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})"
            cursor_new.executemany(insert_query, rows)
            print(f"成功迁移 {len(rows)} 条数据到表: {table_name}")
        else:
            print(f"表 {table_name} 在旧数据库中为空，跳过数据迁移。")
            
    except sqlite3.OperationalError as e:
        print(f"迁移表 {table_name} 时出错 (可能是旧库中不存在此表): {e}")

# 5. 提交更改并关闭连接
conn_new.commit()
conn_old.close()
conn_new.close()

print("\n数据库重建和数据迁移完成！新数据库位于:", new_db_path)