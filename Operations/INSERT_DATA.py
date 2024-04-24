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
        # ('Index', 1, '2024-04-24'),
        # ('Bonds', None, '2024-04-24'),
    ],
    'Stocks': [
        # ('2024-04-01', 'Shenzhen Index', 9647.07, 10),
        # ('2023-11-24', 'Nikkei 225', 33625.53, 10),
        # ('2024-04-10', 'HANG SENG INDEX', 17139.11, 10)
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
        # ('2023-12-27', 'DXY', 100.986, 4),
        # ('2024-03-11', 'USDJPY', 146.94, 4),
        # ('2024-01-01', 'USDJPY', 140.87, 4),
        # ('2024-03-11', 'USDCNY', 7.179, 4),
        # ('2023-12-28', 'USDCNY', 7.118, 4),
        # ('2023-11-23', 'CNYJPY', 20.921, 4),
        # ('2024-03-21', 'CNYJPY', 20.9972, 4),
        # ('2024-01-01', 'CNYJPY', 19.774, 4),
    ],
    # parent_id为5的大宗商品
    'Commodities': [
        # ('2024-03-12', 'Crude Oil', 77.25, 5),
        # ('2024-02-02', 'Crude Oil', 72.3, 5),
        # ('2024-03-05', 'Natural gas', 2.095, 5),
    ],
    # parent_id为6的大宗商品
    # 'Commodities': [
    #      ('2021-10-01', 'Copper', 0.622, 6),
    #      ('2024-04-05', 'Crude Oil', 86.91, 6),
    # ],
    # # parent_id为7的大宗商品
    # 'Commodities': [
    #      ('2021-10-01', 'Copper', 0.622, 7),
    #      ('2024-04-05', 'Crude Oil', 86.91, 7),
    # ],
    # # parent_id为8的大宗商品
    # 'Commodities': [
    #      ('2021-10-01', 'Copper', 0.622, 8),
    #      ('2024-04-05', 'Crude Oil', 86.91, 8),
    # ],
    # # parent_id为9的大宗商品
    # 'Commodities': [        
    #      ('2021-10-01', 'Copper', 0.622, 9),
    #      ('2024-04-05', 'Crude Oil', 86.91, 9),
    # ]
}

# 数据库文件和表名信息，同时指定每个表的列名
databases = [
    {'path': '/Users/yanzhang/Finance.db', 'table': 'Stocks', 'columns': ['date', 'name', 'price', 'parent_id']},
    {'path': '/Users/yanzhang/Finance.db', 'table': 'Currencies', 'columns': ['date', 'name', 'price', 'parent_id']},
    {'path': '/Users/yanzhang/Finance.db', 'table': 'Commodities', 'columns': ['date', 'name', 'price', 'parent_id']},
    {'path': '/Users/yanzhang/Finance.db', 'table': 'Crypto', 'columns': ['date', 'name', 'price', 'parent_id']},
    {'path': '/Users/yanzhang/Finance.db', 'table': 'Categories', 'columns': ['name', 'parent_id','created_at']}
]

# 对每个数据库执行数据插入操作
for db in databases:
    data_to_insert = data_sets.get(db['table'], [])
    if data_to_insert:
        insert_data(db['path'], db['table'], db['columns'], data_to_insert)