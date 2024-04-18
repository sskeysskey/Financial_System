import sqlite3

def update_data(db_path, table_name, data):
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 遍历数据列表，每个元素包含id, date, name, price, parent_id
        for item in data:
            id, date, name, price, parent_id = item
            # 移除价格中的逗号
            price = float(price.replace(',', ''))
            # 构建SQL UPDATE语句
            sql = f"UPDATE {table_name} SET date=?, name=?, price=?, parent_id=? WHERE id=?"
            # 执行SQL语句
            cursor.execute(sql, (date, name, price, parent_id, id))
        
        # 提交更改
        conn.commit()
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    except Exception as e:
        print(f"更新数据时发生错误: {e}")
    finally:
        # 无论成功还是失败，都关闭数据库连接
        conn.close()

data_sets = {
    'Commodities': [],
    'Stocks': [
        (21, "2015-03-18", "SSE Composite Index", "4657.6", 10),
        (22, "2016-03-23", "SSE Composite Index", "2821.05", 10),
        (23, "2018-01-15", "SSE Composite Index", "3487.86", 10),
        (24, "2018-12-24", "SSE Composite Index", "2493.9", 10),
        (25, "2019-04-08", "SSE Composite Index", "3188.63", 10),
        (26, "2020-03-16", "SSE Composite Index", "2763.99", 10),
        (27, "2021-02-15", "SSE Composite Index", "3696.17", 10),
        (28, "2022-03-02", "SSE Composite Index", "3001.56", 10)
    ]
}

databases = [
    {'path': '/Users/yanzhang/Commodities.db', 'table': 'Commodities'},
    {'path': '/Users/yanzhang/Stocks.db', 'table': 'Stocks'},
    # 可以添加更多数据库配置
]

for db in databases:
    data_to_update = data_sets.get(db['table'], [])
    if data_to_update:
        update_data(db['path'], db['table'], data_to_update)