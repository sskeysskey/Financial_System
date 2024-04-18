import sqlite3

def insert_data(db_path, table_name, data):
    """
    向指定数据库的指定表插入数据。
    :param db_path: 数据库文件路径
    :param table_name: 表名
    :param data: 要插入的数据列表，每个元素是一个包含(date, name, price, parent_id)的元组
    """
    # 连接到数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 插入数据
    for record in data:
        cursor.execute(f"INSERT INTO {table_name} (date, name, price, parent_id) VALUES (?, ?, ?, ?);", record)

    # 提交事务
    conn.commit()
    # 关闭连接
    conn.close()
    print(f"Data inserted into {table_name} in {db_path}")

# 准备不同的数据集
data_sets = {
    'Stocks': [
        # ('2000-08-01', 'HANG SENG INDEX', 17097.51, 10),
        # ('2003-04-01', 'HANG SENG INDEX', 8717.22, 10)
    ],
    'Currencies': [
        # ('2001-12-01', 'USDHKD', 1.846, 4),
        # ('2001-12-01', 'USDHKD', 1.846, 4)
    ],
    'Commodities': [
        # ('2024-04-20', 'grape', 800.0, 5),
        # ('2024-04-21', 'melon', 1600.0, 6)
    ],
    'Crypto': [
        ('2021-05-03', 'Bitcoin Cash', 1428.74, 3),
        ('2022-12-26', 'Bitcoin Cash', 96.88, 3),
        ('2023-06-26', 'Bitcoin Cash', 298.24, 3),
        ('2024-04-01', 'Bitcoin Cash', 684, 3)
    ]
}

# 数据库文件和表名信息
databases = [
    {'path': '/Users/yanzhang/Stocks.db', 'table': 'Stocks'},
    {'path': '/Users/yanzhang/Currencies.db', 'table': 'Currencies'},
    {'path': '/Users/yanzhang/Commodities.db', 'table': 'Commodities'},
    {'path': '/Users/yanzhang/Crypto.db', 'table': 'Crypto'}
]

# 对每个数据库执行数据插入操作
for db in databases:
    data_to_insert = data_sets.get(db['table'], [])
    if data_to_insert:
        insert_data(db['path'], db['table'], data_to_insert)