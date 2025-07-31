import sqlite3

def update_data(db_path, table_name, data):
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    count = 0  # 初始化更新计数器

    try:
        # 遍历数据列表，每个元素包含id, date, name, price, volume
        # for item in data:
        #     id, date, name, price, volume = item
        #     # 移除价格中的逗号
        #     # price = float(price.replace(',', ''))
        #     # 构建SQL UPDATE语句
        #     sql = f"UPDATE {table_name} SET date=?, name=?, price=?, volume=? WHERE id=?"
        #     # 执行SQL语句
        #     cursor.execute(sql, (date, name, price, volume, id))
        #     count += 1  # 成功更新后计数增加
        
        # for item in data:
        #     id, date, name, price = item
        #     # 移除价格中的逗号
        #     # price = float(price.replace(',', ''))
        #     # 构建SQL UPDATE语句
        #     sql = f"UPDATE {table_name} SET date=?, name=?, price=? WHERE id=?"
        #     # 执行SQL语句
        #     cursor.execute(sql, (date, name, price, id))
        #     count += 1  # 成功更新后计数增加
        
        # 提交更改
        conn.commit()
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
    except Exception as e:
        print(f"更新数据时发生错误: {e}")
    finally:
        # 无论成功还是失败，都关闭数据库连接
        conn.close()
        # 输出更新的数据条数
        print(f"一共 {count} 条 {table_name} 数据已更新到数据库 {db_path}")

data_sets = {
    'Crypto': [
        # (10434, "2024-10-28", "Bitcoin", "69920.5", 3),
        # (22, "2024-03-15", "Bitcoin", "70841.1", 3),
        # (22, "2024-03-15", "Bitcoin", "65695", 3)
    ],
    'Indices': [
        # (161, "2024-04-26", "NASDAQ", "15611.76", 10),
        # (162, "2024-04-26", "S&P 500", "5048.42", 10),
        # (163, "2024-04-26", "HYG", "76.38", 10),
        # (164, "2024-04-26", "SSE Composite Index", "3062.32", 10),
        # (165, "2024-04-26", "Shenzhen Index", "9326.8", 10),
        # (91152, "2024-05-20", "Nikkei", "39069.68", 127400000),
        # (91368, "2024-06-17", "India", "77236.73", 0),
        # (91113, "2024-05-14", "HANGSENG", "19073.7109", 3455242600),
    ],
    'Bonds': [
        # (83, "2024-04-19", "United States", "72408.33", 24),
        # (83, "2024-04-19", "United States", "72408.33", 24)
    ],
    'Economics': [
        # (175, "2019-02-20", "USInterest", "2.5"),
        # (83, "2024-04-19", "United States", "72408.33", 24)
    ],
    'Commodities': [
        # (83, "2024-04-19", "Crude Oil", "17.63001", 5),
        # (83, "2024-04-19", "Crude Oil", "72408.33", 5)
    
        # (430, "2008-12-01", "Copper", "1.395", 6),
        # (83, "2024-04-19", "Gold", "72408.33", 6)

        # (88652, "2024-05-03", "Oat", "391.7635", 7),
        # (83, "2024-04-19", "Soybeans", "72408.33", 7),
        # (88554, "2024-05-01", "Oat", "379.00", 7),
    
        # (83, "2024-04-19", "Aluminum", "72408.33", 8),
        # (83, "2024-04-19", "Aluminum", "72408.33", 8)
    
        # (83, "2024-04-19", "Live Cattle", "72408.33", 9),
        # (83, "2024-04-19", "Beef", "72408.33", 9),
        # (631, "2024-04-30", "Lean Hogs", "94.150", 9),
    ],
    'Currencies': [
        # (49603, "2024-04-30", "CNYEUR", "0.129250", 4),
        # (50, "2016-12-01", "USDCNY", "6.972", 4),
        # (128834, "2024-06-12", "USDBRL", "5.3867"),
        # (52, "2019-08-01", "USDCNY", "7.16", 4),
        # (53, "2022-02-01", "USDCNY", "6.311", 4),
        # (54, "2022-10-24", "USDCNY", "7.2698", 4),
        # (55, "2023-01-09", "USDCNY", "6.707", 4),
        # (56, "2023-09-04", "USDCNY", "7.365", 4),
        # (83, "2024-04-19", "EURUSD", "72408.33", 4),
        # (83, "2024-04-19", "EURUSD", "72408.33", 4)
    ],
    'Technology': [
        # (49603, "2024-04-30", "CNYEUR", "0.129250", 4),
        # (801138, "2024-06-13", "AVGO", "167.899"),
        # (128834, "2024-06-12", "USDBRL", "5.3867")
    ]
}

databases = [
    {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Indices'},
    {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Crypto'},
    {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Currencies'},
    {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Commodities'},
    {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Bonds'},
    {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Economics'},
    {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'ETFs'},
    {'path': '/Users/yanzhang/Coding/Database/Finance.db', 'table': 'Technology'},
    # 可以添加更多数据库配置
]

for db in databases:
    data_to_update = data_sets.get(db['table'], [])
    if data_to_update:
        update_data(db['path'], db['table'], data_to_update)