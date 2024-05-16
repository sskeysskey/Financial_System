import sqlite3

def insert_data(db_path, table_name, columns, data):
    """
    向指定数据库的指定表插入数据。
    :param db_path: 数据库文件路径
    :param table_name: 表名
    :param data: 要插入的数据列表，每个元素是一个包含(date, name, price, parent_id)的元组
    """
    # 连接到数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 构建插入数据的SQL语句
    placeholders = ', '.join(['?'] * len(columns))
    column_names = ', '.join(columns)
    sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders});"

    # 插入数据
    count = 0  # 初始化计数器
    for record in data:
        cursor.execute(sql, record)
        count += 1  # 插入一条数据，计数器加一

    # 提交事务
    conn.commit()
    # 关闭连接
    conn.close()
    print(f"一共 {count} 条 {table_name} 数据已插入 {db_path}")

# 准备不同的数据集
data_sets = {
    'Categories': [
        # ('S&P 500', 10, '2024-04-29'),
        # ('Russell 2000', 10, '2024-04-29'),
        # ('MOEX Russia Index', 10, '2024-04-29'),
        # ('Nikkei 225', 10, '2024-04-29'),
        # ('HANG SENG INDEX', 10, '2024-04-29'),
        # ('SSE Composite Index', 10, '2024-04-29'),
        # ('Shenzhen Index', 10, '2024-04-29'),
        # ('S&P BSE SENSEX', 10, '2024-04-29'),
        # ('CBOE Volatility Index', 10, '2024-04-29'),
        # ('Bonds', None, '2024-04-24'),
    ],
    'Indices': [
        # ('2024-04-01', 'Shenzhen Index', 9647.07, 10),
        # ('2024-05-15', 'Nikkei', 38608.18, ),
        # ('2018-01-22', 'HANG SENG INDEX', 33154.12, 10),
        # ('2024-03-26', 'S&P BSE SENSEX', 72470.3, 10)
    ],
    'Crypto': [
        # ('2021-05-03', 'Bitcoin Cash', 1428.74, 3),
        # ('2024-04-08', 'Ether', 3689.0, 3),
        # ('2024-04-10', 'Binance', 609.9, 3),
        # ('2024-04-01', 'Bitcoin Cash', 684, 3)
    ],
    'Currencies': [
        # ('2024-02-13', 'DXY', 104.96, 4),
        # ('2024-03-11', 'USDJPY', 146.94, 4),
        # ('2023-12-28', 'USDCNY', 7.118, 4),
        # ('2023-11-23', 'CNYJPY', 20.921, 4),
        # ('2023-11-23', 'CNYEUR', 20.921, 4),
    ],
    'Bonds': [
        # ('2024-02-13', 'United States', 104.96, 4),
    ],
    
    'Commodities': [
    # parent_id为5的大宗商品
        # ('2024-03-12', 'Crude Oil', 77.25, 5),
        # ('2024-03-05', 'Natural gas', 2.095, 5),
    
    # parent_id为6的大宗商品
        #  ('2008-12-01', 'Cotton', 1.395, 6),
        #  ('2024-04-05', 'Crude Oil', 86.91, 6),

    # parent_id为7的大宗商品
        #  ('2024-05-01', 'Cotton', 75.14, 7),
        #  ('2024-04-05', 'Crude Oil', 86.91, 7),

    # parent_id为8的大宗商品
        #  ('2021-10-01', 'Copper', 0.622, 8),
        #  ('2024-04-05', 'Crude Oil', 86.91, 8),

    # parent_id为9的大宗商品
        #  ('2021-10-01', 'Copper', 0.622, 9),
        #  ('2024-04-05', 'Crude Oil', 86.91, 9),
    ],
}

# 数据库文件和表名信息，同时指定每个表的列名
databases = [
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Indices', 'columns': ['date', 'name', 'price', 'parent_id']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Currencies', 'columns': ['date', 'name', 'price', 'parent_id']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities', 'columns': ['date', 'name', 'price', 'parent_id']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Crypto', 'columns': ['date', 'name', 'price', 'parent_id']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Bonds', 'columns': ['date', 'name', 'price', 'parent_id']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Categories', 'columns': ['name', 'parent_id','created_at']},
]

# 对每个数据库执行数据插入操作
for db in databases:
    data_to_insert = data_sets.get(db['table'], [])
    if data_to_insert:
        insert_data(db['path'], db['table'], db['columns'], data_to_insert)