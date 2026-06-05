import sqlite3
import pandas as pd

# 数据库路径（你提供的路径）
DB_PATH = "/Users/yanzhang/Coding/Database/Finance.db"

def fix_rice_prices():
    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    
    # 1. 先查看当前 Rice 的所有数据（确认问题）
    print("=== 修复前 Rice 价格 ===")
    df_before = pd.read_sql("SELECT * FROM Commodities WHERE name = 'Rice' ORDER BY date DESC", conn)
    print(df_before)
    
    # 2. 执行修复：把大于 100 的价格（四位数）除以 100
    # 只更新 Rice，且只更新错误的大数值，非常安全
    update_sql = """
    UPDATE Commodities
    SET price = price / 100.0
    WHERE name = 'Rice' AND price > 100;
    """
    
    conn.execute(update_sql)
    conn.commit()
    print("\n✅ 修复完成！已将所有四位数价格除以 100")
    
    # 3. 查看修复后结果
    print("\n=== 修复后 Rice 价格 ===")
    df_after = pd.read_sql("SELECT * FROM Commodities WHERE name = 'Rice' ORDER BY date DESC", conn)
    print(df_after)
    
    conn.close()

if __name__ == "__main__":
    fix_rice_prices()