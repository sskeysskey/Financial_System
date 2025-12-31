import sqlite3

# 数据库路径
db_path = '/Users/yanzhang/Coding/Database/Finance.db'

def add_and_calculate_change():
    try:
        # 1. 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 尝试添加 'change' 列 (如果还没添加过)
        try:
            cursor.execute("ALTER TABLE Options ADD COLUMN change REAL")
            print("列 'change' 已添加。")
        except sqlite3.OperationalError:
            print("列 'change' 已存在，准备更新数据。")

        # --- 主要修改在这里 ---
        # 使用 ROUND(计算公式, 2) 来保留两位小数
        update_sql = """
        UPDATE Options
        SET change = ROUND(price - (
            SELECT prev.price
            FROM Options AS prev
            WHERE prev.name = Options.name 
              AND prev.date < Options.date
            ORDER BY prev.date DESC
            LIMIT 1
        ), 2)
        """
        
        print("正在计算并更新数据（保留两位小数）...")
        cursor.execute(update_sql)
        
        # 获取受影响的行数
        rows_affected = cursor.rowcount
        
        # 4. 提交更改
        conn.commit()
        print(f"成功更新了 {rows_affected} 行数据的 change 值。")

    except Exception as e:
        print(f"发生错误: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    add_and_calculate_change()
