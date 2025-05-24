import sqlite3
from datetime import datetime, timedelta

def update_dates_in_database(db_path):
    """
    连接到 SQLite 数据库，并将 "Deposit" 表中的日期向前移动两天。

    参数:
    db_path (str): SQLite 数据库文件的路径。
    """
    try:
        # 连接到 SQLite 数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 选取所有需要更新的行 (id 和 date)
        cursor.execute("SELECT id, date FROM Deposit")
        rows = cursor.fetchall()

        updated_rows = []
        for row in rows:
            row_id, date_str = row
            try:
                # 将日期字符串转换为 datetime 对象
                current_date = datetime.strptime(date_str, '%Y-%m-%d')
                # 计算新的日期 (向前移动两天)
                new_date = current_date - timedelta(days=2)
                # 将新的日期格式化为字符串
                new_date_str = new_date.strftime('%Y-%m-%d')
                updated_rows.append((new_date_str, row_id))
            except ValueError as e:
                print(f"处理行 ID {row_id} 的日期 {date_str} 时出错: {e}")
                continue # 如果日期格式不正确，跳过这一行

        if not updated_rows:
            print("没有找到需要更新的日期。")
            return

        # 执行批量更新操作
        # 使用参数化查询来防止 SQL 注入
        update_query = "UPDATE Deposit SET date = ? WHERE id = ?"
        cursor.executemany(update_query, updated_rows)

        # 提交事务
        conn.commit()
        print(f"成功更新了 {len(updated_rows)} 行的日期。")

    except sqlite3.Error as e:
        print(f"数据库操作发生错误: {e}")
        if conn:
            conn.rollback() # 如果发生错误，回滚更改
    finally:
        # 关闭数据库连接
        if conn:
            conn.close()
            print("数据库连接已关闭。")

# --- 主程序 ---
if __name__ == "__main__":
    # 请将这里的路径替换成您数据库文件的实际路径
    database_file_path = "/Users/yanzhang/Documents/Database/Firstrade.db"
    update_dates_in_database(database_file_path)