import sqlite3

def delete_records(db_file, table_name, ids):
    """删除指定表中的记录。
    
    Args:
        db_file (str): 数据库文件的路径。
        table_name (str): 要操作的表名。
        ids (list of int): 要删除的记录的ID列表。
    """
    # 将ID列表转换为字符串，用于SQL语句中
    id_str = ', '.join(map(str, ids))
    
    # 连接数据库
    conn = sqlite3.connect(db_file)
    
    try:
        # 创建一个cursor对象并执行SQL语句
        cur = conn.cursor()
        sql = f"DELETE FROM {table_name} WHERE id IN ({id_str});"
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
# db_path = '/Users/yanzhang/Documents/Database/Analysis.db'  # 配置数据库文件路径
table = 'Bonds'
ids_to_delete = [15700]

delete_records(db_path, table, ids_to_delete)