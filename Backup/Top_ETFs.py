import sqlite3

def get_top_etfs_by_turnover(db_path):
    """
    连接数据库，计算最新日期的成交额 (price * volume)，并返回前20名。
    """
    try:
        # 1. 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 2. 获取最新日期
        # 使用 MAX(date) 找到表中最大的日期字符串
        cursor.execute("SELECT MAX(date) FROM ETFs")
        latest_date = cursor.fetchone()[0]

        if not latest_date:
            print("数据库中没有数据。")
            return

        print(f"当前最新日期为: {latest_date}")

        # 3. 查询并计算
        # 计算逻辑: price * volume AS turnover
        # 筛选条件: WHERE date = ?
        # 排序: ORDER BY turnover DESC (降序)
        # 限制: LIMIT 20
        query = """
        SELECT name, price, volume, (price * volume) AS turnover
        FROM ETFs
        WHERE date = ?
        ORDER BY turnover DESC
        LIMIT 30
        """
        
        cursor.execute(query, (latest_date,))
        results = cursor.fetchall()

        # 4. 打印结果
        print(f"{'名称':<10} | {'价格':<10} | {'成交量':<12} | {'成交额':<15}")
        print("-" * 55)
        for row in results:
            name, price, volume, turnover = row
            # 格式化输出，保留两位小数
            print(f"{name:<10} | {price:<10.2f} | {volume:<12,} | {turnover:<15,.2f}")

    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    finally:
        if conn:
            conn.close()

# 执行函数
if __name__ == "__main__":
    db_file = "/Users/yanzhang/Coding/Database/Finance.db"
    get_top_etfs_by_turnover(db_file)