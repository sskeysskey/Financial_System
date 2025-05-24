import sqlite3

# 1. 定义数据库文件路径
db_path = '/Users/yanzhang/Documents/Database/Firstrade.db'

# 2. 连接到数据库 (如果数据库不存在，则会创建一个新的)
conn = sqlite3.connect(db_path)

# 3. 创建一个游标对象，用于执行SQL语句
cursor = conn.cursor()

# 4. 定义创建表的SQL语句
create_table_query = """
CREATE TABLE IF NOT EXISTS Deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    value REAL NOT NULL
);
"""

try:
    # 5. 执行SQL语句来创建表
    cursor.execute(create_table_query)
    print("表 'Transaction' 创建成功或已存在。")

    # 6. 提交更改到数据库
    conn.commit()

except sqlite3.Error as e:
    print(f"创建表时发生错误: {e}")

finally:
    # 7. 关闭数据库连接
    if conn:
        conn.close()
        print("数据库连接已关闭。")