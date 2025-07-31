import sqlite3

def clean_duplicate_records(db_path, table_name):
    # 连接到SQLite数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 查询出所有name和date组合的重复记录，只保留id最大的记录
    query = """
    SELECT name, date
    FROM {0}
    GROUP BY name, date
    HAVING COUNT(*) > 1
    """.format(table_name)  # 使用format方法来插入表名
    cursor.execute(query)
    duplicates = cursor.fetchall()

    # 对于每一组重复的name和date，删除除了id最大的记录以外的所有记录
    for name, date in duplicates:
        delete_query = """
        DELETE FROM {0}
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM {0}
            WHERE name = ? AND date = ?
        ) AND name = ? AND date = ?
        """.format(table_name)  # 同样使用format方法来插入表名

        # delete_query = """
        # DELETE FROM {0}
        # WHERE id NOT IN (
        #     SELECT MIN(id)
        #     FROM {0}
        #     WHERE name = ? AND date = ?
        # ) AND name = ? AND date = ?
        # """.format(table_name)  # 同样使用format方法来插入表名

        cursor.execute(delete_query, (name, date, name, date))
        conn.commit()

    print("重复记录已清除。")

    # 关闭数据库连接
    cursor.close()
    conn.close()

# 调用函数，传入数据库路径和表名
db_path = '/Users/yanzhang/Coding/Database/Finance.db'
table_name = 'Commodities'

clean_duplicate_records(db_path, table_name)