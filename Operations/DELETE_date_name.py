import sqlite3

def delete_records_by_name_and_date(db_file, table_name, names, date):
    """删除指定表中符合特定名称和日期的记录。
    
    Args:
        db_file (str): 数据库文件的路径。
        table_name (str): 要操作的表名。
        names (list of str): 要删除记录的名称列表。
        date (str): 指定的日期，格式应为'YYYY-MM-DD'。
    """
    # 将名称列表转换为SQL语句中的字符串形式
    names_str = ', '.join(f"'{name}'" for name in names)
    
    # 连接数据库
    conn = sqlite3.connect(db_file)
    
    try:
        # 创建一个cursor对象并执行SQL语句
        cur = conn.cursor()
        sql = f"""
        DELETE FROM {table_name}
        WHERE name IN ({names_str}) AND date = '{date}';
        """
        cur.execute(sql)
        
        # 提交事务
        conn.commit()
        print(f"成功删除{cur.rowcount}条记录。")
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    finally:
        # 关闭连接
        conn.close()

# 使用示例
db_path = '/Users/yanzhang/Documents/Database/Finance.db'  # 配置数据库文件路径
table = 'Stocks'                                      # 配置表名
names_to_delete = [
    "Cocoa", "Coffee", "Cotton", "Orange Juice", "Sugar", "Lean Hogs", "Crude Oil", 
    "Brent", "Live Cattle", "Copper", "Corn", "Gold", "Silver", "Natural gas", "Oat", 
    "Rice", "Soybeans"
]
date_to_delete = '2024-05-02'

delete_records_by_name_and_date(db_path, table, names_to_delete, date_to_delete)