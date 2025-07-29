import sqlite3

# 数据库文件的路径
db_path = '/Users/yanzhang/Documents/Database/Firstrade.db'

# 要插入的数据
date_value = '2020-11-29'
value_value = 5000
type_value = 1

try:
    # 1. 连接到 SQLite 数据库
    # 如果数据库文件不存在，会自动在当前目录创建一个
    conn = sqlite3.connect(db_path)

    # 2. 创建一个 Cursor 对象
    # Cursor 对象用于执行 SQL 语句
    cursor = conn.cursor()

    # 3. 准备 SQL INSERT 语句
    # 我们不需要为 id 列插入值，因为它通常是自动生成的
    sql_insert_query = """
    INSERT INTO Deposit (date, value, type)
    VALUES (?, ?, ?);
    """
    # 将要插入的数据放入一个元组中
    data_to_insert = (date_value, value_value, type_value)

    # 4. 执行 SQL 语句
    cursor.execute(sql_insert_query, data_to_insert)

    # 5. 提交事务
    # 对于修改数据的操作（INSERT, UPDATE, DELETE），需要提交事务才能使更改生效
    conn.commit()

    print(f"数据 ('{date_value}', {value_value}, {type_value}) 已成功插入到 Deposit 表中。")
    print(f"新插入行的 rowid (通常是 id) 为: {cursor.lastrowid}")

except sqlite3.Error as e:
    print(f"数据库操作发生错误: {e}")
    if conn:
        # 如果发生错误，回滚任何更改
        conn.rollback()
finally:
    # 6. 关闭数据库连接
    # 无论操作是否成功，都应该关闭连接
    if conn:
        conn.close()
        print("数据库连接已关闭。")