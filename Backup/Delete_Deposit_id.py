import sqlite3

# 数据库文件的路径
db_path = '/Users/yanzhang/Documents/Database/Firstrade.db'

# 要删除的数据的 id
ids_to_delete = [30]

try:
    # 1. 连接到 SQLite 数据库
    conn = sqlite3.connect(db_path)

    # 2. 创建一个 Cursor 对象
    cursor = conn.cursor()

    # 3. 准备 SQL DELETE 语句并执行
    # 我们可以逐个删除，或者使用 IN 操作符一次性删除多个（如果适用且更方便）
    # 这里我们选择逐个删除，以便清晰地看到每条记录的删除操作

    for record_id in ids_to_delete:
        sql_delete_query = """
        DELETE FROM Deposit
        WHERE id = ?;
        """
        cursor.execute(sql_delete_query, (record_id,)) # 注意这里传递的是一个单元素的元组 (record_id,)
        
        # 检查是否有行被删除
        if cursor.rowcount > 0:
            print(f"ID 为 {record_id} 的数据已成功从 Deposit 表中删除。")
        else:
            print(f"在 Deposit 表中未找到 ID 为 {record_id} 的数据，或数据已被删除。")

    # 4. 提交事务
    # 对于修改数据的操作（INSERT, UPDATE, DELETE），需要提交事务才能使更改生效
    conn.commit()
    print("数据库事务已提交。")

except sqlite3.Error as e:
    print(f"数据库操作发生错误: {e}")
    if conn:
        # 如果发生错误，回滚任何更改
        conn.rollback()
        print("数据库事务已回滚。")
finally:
    # 5. 关闭数据库连接
    # 无论操作是否成功，都应该关闭连接
    if conn:
        conn.close()
        print("数据库连接已关闭。")