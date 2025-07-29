import sqlite3
import json
from datetime import datetime
import os

def optimize_database(db_path, json_path):
    # 读取 JSON 文件
    with open(json_path, 'r') as f:
        sector_data = json.load(f)
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 设置截止日期
    cutoff_date = '2002-09-01'
    
    try:
        # 遍历所有表
        for table_name in sector_data.keys():
            # 检查表是否存在
            cursor.execute(f"""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, (table_name,))
            
            if cursor.fetchone() is None:
                continue
                
            # 获取表中的符号列表
            symbols = sector_data[table_name]
            if not symbols:
                continue
                
            # 为每个符号删除早期数据
            for symbol in symbols:
                print(f"Processing {table_name} - {symbol}")
                cursor.execute(f"""
                    DELETE FROM {table_name}
                    WHERE date < ? AND name = ?
                """, (cutoff_date, symbol))
            
        # 提交更改
        conn.commit()
        
        # 优化数据库
        print("Optimizing database...")
        cursor.execute("VACUUM")
        conn.commit()
        
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    # 获取数据库文件大小（优化前）
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'  # 替换为实际的数据库路径
    json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'  # JSON 文件路径
    
    initial_size = os.path.getsize(db_path) / (1024 * 1024)  # 转换为 MB
    
    print(f"Original database size: {initial_size:.2f} MB")
    
    # 执行优化
    optimize_database(db_path, json_path)
    
    # 获取优化后的文件大小
    final_size = os.path.getsize(db_path) / (1024 * 1024)
    
    print(f"Final database size: {final_size:.2f} MB")
    print(f"Reduced by: {initial_size - final_size:.2f} MB")

if __name__ == "__main__":
    main()