import pandas as pd
import sqlite3

def read_and_process_csv(file_path):
    # 读取CSV文件，注意匹配列名的大小写
    df = pd.read_csv(file_path, usecols=['Date', 'Close'])
    # 保留小数点后三位
    df['Close'] = df['Close'].round(3)
    return df

def insert_data_to_db(df, db_file, table_name, name, parent_id):
    # 连接到SQLite数据库
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # 确保指定的表存在
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT UNIQUE,
        name TEXT,
        price REAL,
        parent_id INTEGER
    )
    ''')
    conn.commit()

    # 插入或更新数据
    for index, row in df.iterrows():
        # 检查日期和name是否已存在
        cursor.execute(f'SELECT id FROM {table_name} WHERE date = ? AND name = ?', (row['Date'], name))
        result = cursor.fetchone()
        if result:
            # 如果存在，更新记录
            cursor.execute(f'UPDATE {table_name} SET name = ?, price = ?, parent_id = ? WHERE id = ?', 
                           (name, row['Close'], parent_id, result[0]))
        else:
            # 如果不存在，插入新记录
            cursor.execute(f'INSERT INTO {table_name} (date, name, price, parent_id) VALUES (?, ?, ?, ?)', 
                           (row['Date'], name, row['Close'], parent_id))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    csv_file_path = '/Users/yanzhang/Downloads/EURCNY.csv'
    database_file = '/Users/yanzhang/Documents/Database/Finance.db'
    table_name = 'Currencies'  # 将表名定义为一个变量
    name = 'EURCNY'  # 将股票名称定义为一个变量
    parent_id = 4  # 将parent_id定义为一个变量
    
    # 读取并处理CSV数据
    data_frame = read_and_process_csv(csv_file_path)
    
    # 将数据插入数据库
    insert_data_to_db(data_frame, database_file, table_name, name, parent_id)

    print("数据处理完毕，已存入数据库。")