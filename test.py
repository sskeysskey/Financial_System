import sqlite3
from datetime import date, timedelta

def add_data_to_deals(db_path, start_date_str, end_date_str, value):
    """
    向 Firstrade.db 数据库的 Deals 表中插入指定日期范围和数值的数据。

    参数:
    db_path (str):数据库文件的路径。
    start_date_str (str): 开始日期的字符串，格式为 'YYYY-MM-DD'。
    end_date_str (str): 结束日期的字符串，格式为 'YYYY-MM-DD'。
    value (float): 要插入的数值。
    """
    try:
        # 连接到 SQLite 数据库
        # 如果数据库文件不存在，会自动在当前目录创建
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 将字符串日期转换为 date 对象
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        # 生成需要插入的日期列表
        current_date = start_date
        dates_to_insert = []
        while current_date <= end_date:
            dates_to_insert.append((current_date.isoformat(), value))
            current_date += timedelta(days=1)

        # 准备 SQL 插入语句
        # 我们不需要手动插入 id，因为如果它是主键且自增，SQLite 会自动处理
        # 如果 id 不是自增的，您可能需要先查询最大的 id 然后加1，或者将其设置为 NULL（如果允许）
        # 这里假设 id 是自增的或者可以不指定
        sql = "INSERT INTO Deals (date, value) VALUES (?, ?)"

        # 执行批量插入
        cursor.executemany(sql, dates_to_insert)

        # 提交事务
        conn.commit()
        print(f"成功插入 {len(dates_to_insert)} 条数据到 Deals 表。")

    except sqlite3.Error as e:
        print(f"数据库操作发生错误: {e}")
        if conn:
            conn.rollback() # 如果发生错误，回滚更改
    finally:
        # 关闭数据库连接
        if conn:
            conn.close()

# --- 使用示例 ---
# 数据库文件路径 (请确保路径正确)
database_file = '/Users/yanzhang/Documents/Database/Firstrade.db'

# 要插入的数据
start_date_string = '2025-05-30'
end_date_string = '2025-05-31'
value_to_insert = 1097.68

# 调用函数插入数据
add_data_to_deals(database_file, start_date_string, end_date_string, value_to_insert)

# (可选) 验证插入的数据
def verify_data(db_path, start_date_str, end_date_str):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        sql = "SELECT id, date, value FROM Deals WHERE date BETWEEN ? AND ? ORDER BY date"
        cursor.execute(sql, (start_date_str, end_date_str))
        rows = cursor.fetchall()
        if rows:
            print("\n验证插入的数据:")
            for row in rows:
                print(f"id: {row[0]}, date: {row[1]}, value: {row[2]}")
        else:
            print(f"\n在日期范围 {start_date_str} 到 {end_date_str} 未找到数据。")
    except sqlite3.Error as e:
        print(f"验证数据时发生错误: {e}")
    finally:
        if conn:
            conn.close()

# 调用验证函数
verify_data(database_file, start_date_string, end_date_string)