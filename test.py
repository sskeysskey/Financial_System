import sqlite3

def search_qint_in_tables(db_path):
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    found_tables = []
    
    # 遍历每个表
    for table in tables:
        table_name = table[0]
        try:
            # 检查表是否包含name列
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            has_name_column = any(col[1].lower() == 'name' for col in columns)
            
            if has_name_column:
                # 查询包含QINT的记录
                cursor.execute(f"SELECT * FROM {table_name} WHERE name = 'QINT'")
                results = cursor.fetchall()
                
                if results:
                    found_tables.append({
                        'table': table_name,
                        'records': results
                    })
                    print(f"\n在表 {table_name} 中找到QINT:")
                    for row in results:
                        print(row)
        except sqlite3.Error as e:
            print(f"查询表 {table_name} 时出错: {e}")
    
    # 关闭连接
    conn.close()
    
    if not found_tables:
        print("\n没有找到包含name为QINT的记录")
    
    return found_tables

# 使用示例
db_path = '/Users/yanzhang/Coding/Database/Finance.db'
results = search_qint_in_tables(db_path)