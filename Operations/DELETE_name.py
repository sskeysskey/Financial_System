import sqlite3

def delete_records_by_name(db_file, table_name, stock_name):
    """删除指定表中的特定名称的所有记录。
    
    Args:
        db_file (str): 数据库文件的路径。
        table_name (str): 要操作的表名。
        stock_name (str): 要删除的股票名称。
    """
    # 连接数据库
    conn = sqlite3.connect(db_file)
    
    try:
        # 创建一个cursor对象并执行SQL语句
        cur = conn.cursor()
        # 使用参数化查询来避免SQL注入
        sql = f"DELETE FROM {table_name} WHERE name = ?;"
        cur.execute(sql, (stock_name,))
        
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
table = 'Financial_Services'
stock_name_to_delete = 'SLMBP'

delete_records_by_name(db_path, table, stock_name_to_delete)