import sqlite3
from datetime import date # 用于获取今天的日期 (虽然题目已指定，但通常获取当日日期会用到)

def add_balance_record(record_date, record_value):
    """
    向 Balance 表中添加一条新的记录。

    参数:
    record_date (str): 记录的日期，格式为 'YYYY-MM-DD'。
    record_value (float): 记录的金额。
    """
    db_name = '/Users/yanzhang/Documents/Database/Firstrade.db'
    try:
        # 1. 连接到数据库文件
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # 2. 定义插入数据的 SQL 语句
        # 使用占位符 (?) 来防止 SQL 注入，更安全
        insert_query = """
        INSERT INTO Balance (date, value)
        VALUES (?, ?);
        """

        # 3. 执行插入操作
        # 将要插入的数据作为一个元组传递给 execute 方法的第二个参数
        cursor.execute(insert_query, (record_date, record_value))

        # 4. 提交事务，将更改保存到数据库
        conn.commit()
        print(f"成功向 Balance 表插入记录：日期 {record_date}, 金额 {record_value}")
        print(f"新记录的 ID 是: {cursor.lastrowid}") # 获取最后插入行的 ID

    except sqlite3.Error as e:
        print(f"数据库操作发生错误: {e}")
        if conn:
            conn.rollback() # 如果发生错误，回滚更改

    finally:
        # 5. 关闭数据库连接
        if conn:
            conn.close()
            print(f"数据库 {db_name} 连接已关闭。")

if __name__ == '__main__':
    # 获取今天的日期 (题目已指定，这里作为演示)
    # today_date_str = date.today().strftime('%Y-%m-%d')

    # 指定要插入的日期和金额
    target_date = '2025-05-21'
    target_value = 28000.0  # 确保 value 是浮点数或整数

    # 调用函数插入数据
    add_balance_record(target_date, target_value)