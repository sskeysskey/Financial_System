import sqlite3

# 数据库路径
db_path = '/Users/yanzhang/Coding/Database/Finance.db'

# 需要修改的表列表
target_tables = [
    'Real_Estate', 'Industrials', 'Healthcare', 'ETFs', 
    'Technology', 'Financial_Services', 'Consumer_Defensive', 
    'Consumer_Cyclical', 'Communication_Services', 'Basic_Materials', 
    'Energy', 'Utilities'
]

def add_columns_to_tables():
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        for table in target_tables:
            print(f"正在处理表: {table}...")
            
            # 检查表是否存在
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';")
            if not cursor.fetchone():
                print(f"警告: 表 {table} 不存在，跳过。")
                continue
            
            # 尝试添加列
            # 注意：如果列已经存在，直接执行 ALTER 会报错，这里使用 try-except 捕获
            try:
                # 添加 open, high, low 列，类型设为 REAL (与 price 兼容)
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN open REAL;")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN high REAL;")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN low REAL;")
                print(f"成功: 已为 {table} 添加 open, high, low 列。")
            except sqlite3.OperationalError as e:
                print(f"跳过: {table} 可能已经包含这些列 (错误信息: {e})")
        
        # 提交更改
        conn.commit()
        print("\n所有操作已完成。")
        
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    add_columns_to_tables()