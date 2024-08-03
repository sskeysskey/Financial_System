import sqlite3

def insert_data(db_path, table_name, columns, data):
    """
    向指定数据库的指定表插入数据。
    :param db_path: 数据库文件路径
    :param table_name: 表名
    :param data: 要插入的数据列表，每个元素是一个包含(date, name, price, volume)的元组
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
    'Indices': [
        # ('2024-04-01', 'Shenzhen Index', 9647.07, 10),
        # ('2024-05-16', 'Nikkei', 38920.26, 157900000),
        # ('2018-01-22', 'HANG SENG INDEX', 33154.12, 10),
        # ('2024-06-17', 'Russia', 3183.68, 0),
        # ('2024-06-18', 'Russia', 3114.15, 0),
        # ('2024-06-19', 'Russia', 3027.47, 0),
        # ('2024-06-20', 'Russia', 3123.43, 0),
        # ('2024-06-21', 'Russia', 3114.35, 0),
        # ('2024-06-24', 'Russia', 3098.05, 0),
        # ('2024-06-25', 'Russia', 3111.39, 0),
        # ('2024-06-26', 'Russia', 3151.70, 0),
        # ('2024-05-22', 'Nikkei', 38617.10, 105500000)
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
        # ('2024-07-04', 'US2Y', 4.70),
        # ('2024-07-03', 'US2Y', 4.752),
        # ('2024-07-02', 'US2Y', 4.791),
        # ('2024-07-01', 'US2Y', 4.768),
        # ('2024-06-28', 'US2Y', 4.718),
        # ('2024-06-27', 'US2Y', 4.753),
        # ('2024-06-26', 'US2Y', 4.742)
    ],
    
    'Commodities': [
        # ('2024-03-12', 'Crude Oil', 77.25),
        # ('2024-03-05', 'Natural gas', 2.095),
        #  ('2024-05-09', 'Silver', 28.132),
    ],
    'Economics': [
        # ('2017-08-10', 'USGDP', 2.3),
        # ('2019-01-10', 'USInflation', 1.9),
        #  ('2015-12-15', 'USInterest', 0.25),
        #  ('2024-04-20', 'USNonFarm', 315.0),
        #  ('2024-04-04', 'USTrade', -69.46),
        #  ('2024-04-26', 'CorePCEY', 2.8),
        #  ('2024-06-13', 'USPPI', 2.2)
        # ('2024-06-18', 'USRetailM', 0.3),
    ]
}

# 数据库文件和表名信息，同时指定每个表的列名
databases = [
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Indices', 'columns': ['date', 'name', 'price', 'volume']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Currencies', 'columns': ['date', 'name', 'price']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities', 'columns': ['date', 'name', 'price']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Crypto', 'columns': ['date', 'name', 'price']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Bonds', 'columns': ['date', 'name', 'price']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Economics', 'columns': ['date', 'name', 'price']},
    {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'ETFs', 'columns': ['date', 'name', 'price', 'volume']},
]

# 对每个数据库执行数据插入操作
for db in databases:
    data_to_insert = data_sets.get(db['table'], [])
    if data_to_insert:
        insert_data(db['path'], db['table'], db['columns'], data_to_insert)