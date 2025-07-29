import sqlite3

def delete_records_between(db_file, table_name, start_id, end_id):
    """删除指定表中指定ID范围的记录。
    
    Args:
        db_file (str): 数据库文件的路径。
        table_name (str): 要操作的表名。
        start_id (int): ID范围的起始值。
        end_id (int): ID范围的结束值。
    """
    # 连接数据库
    conn = sqlite3.connect(db_file)
    
    try:
        # 创建一个cursor对象并执行SQL语句
        cur = conn.cursor()
        sql = f"DELETE FROM {table_name} WHERE id BETWEEN {start_id} AND {end_id};"
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
table = 'Bonds'                # 配置表名
start_id = 23
end_id = 35

delete_records_between(db_path, table, start_id, end_id)