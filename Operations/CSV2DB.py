import pandas as pd
import sqlite3

def read_and_process_csv(file_path):
    # 读取CSV文件，注意匹配列名的大小写
    df = pd.read_csv(file_path, usecols=['Date', 'Close'])
    # 保留小数点后三位
    df['Close'] = df['Close'].round(3)
    return df

def insert_data_to_db(df, db_file):
    # 连接到SQLite数据库
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # 确保Stocks表存在
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Stocks (
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
        # 检查日期是否已存在
        # 检查日期和name是否已存在
        cursor.execute('SELECT id FROM Stocks WHERE date = ? AND name = ?', (row['Date'], 'CBOE Volatility Index'))
        result = cursor.fetchone()
        if result:
            # 如果存在，更新记录
            cursor.execute('UPDATE Stocks SET name = ?, price = ?, parent_id = ? WHERE id = ?', 
                           ('CBOE Volatility Index', row['Close'], 10, result[0]))
        else:
            # 如果不存在，插入新记录
            cursor.execute('INSERT INTO Stocks (date, name, price, parent_id) VALUES (?, ?, ?, ?)', 
                           (row['Date'], 'CBOE Volatility Index', row['Close'], 10))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    csv_file_path = '/Users/yanzhang/Downloads/VIX.csv'
    database_file = '/Users/yanzhang/Documents/Database/Finance.db'
    
    # 读取并处理CSV数据
    data_frame = read_and_process_csv(csv_file_path)
    
    # 将数据插入数据库
    insert_data_to_db(data_frame, database_file)

    print("数据处理完毕，已存入数据库。")