import sqlite3

def update_data(db_path, table_name, data):
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    count = 0  # 初始化更新计数器

    try:
        # 遍历数据列表，每个元素包含id, date, name, price, parent_id
        for item in data:
            id, date, name, price, parent_id = item
            # 移除价格中的逗号
            # price = float(price.replace(',', ''))
            # 构建SQL UPDATE语句
            sql = f"UPDATE {table_name} SET date=?, name=?, price=?, parent_id=? WHERE id=?"
            # 执行SQL语句
            cursor.execute(sql, (date, name, price, parent_id, id))
            count += 1  # 成功更新后计数增加
        
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
        # (22, "2024-03-15", "Bitcoin", "65695", 3),
        # (22, "2024-03-15", "Bitcoin", "70841.1", 3),
        # (22, "2024-03-15", "Bitcoin", "65695", 3)
    ],
    'Stocks': [
        # (83, "2024-04-19", "S&P BSE SENSEX", "72408.33", 10),
        # (112, "2023-07-31", "HANG SENG INDEX", "20078.94", 10),
        # (23, "2018-01-15", "SSE Composite Index", "3487.86", 10)
    ],
    'Commodities': [
        # (83, "2024-04-19", "Crude Oil", "72408.33", 5),
        # (83, "2024-04-19", "Crude Oil", "72408.33", 5)
    ],
    'Commodities': [
        # (83, "2024-04-19", "Gold", "72408.33", 6),
        # (83, "2024-04-19", "Gold", "72408.33", 6)
    ],
    'Commodities': [
        # (83, "2024-04-19", "Soybeans", "72408.33", 7),
        # (83, "2024-04-19", "Soybeans", "72408.33", 7)
    ],
    'Commodities': [
        # (83, "2024-04-19", "Aluminum", "72408.33", 8),
        # (83, "2024-04-19", "Aluminum", "72408.33", 8)
    ],
    'Commodities': [
        # (83, "2024-04-19", "Salmon", "72408.33", 9),
        # (83, "2024-04-19", "Beef", "72408.33", 9),
        # (83, "2024-04-19", "Poultry", "72408.33", 9),
        # (83, "2024-04-19", "Lean Hogs", "72408.33", 9)
    ],
    'Currencies': [
        (49, "2014-01-01", "USDCNY", "6.034", 4),
        (50, "2016-12-01", "USDCNY", "6.972", 4),
        (51, "2018-03-01", "USDCNY", "6.26", 4),
        (52, "2019-08-01", "USDCNY", "7.16", 4),
        (53, "2022-02-01", "USDCNY", "6.311", 4),
        (54, "2022-10-24", "USDCNY", "7.2698", 4),
        (55, "2023-01-09", "USDCNY", "6.707", 4),
        (56, "2023-09-04", "USDCNY", "7.365", 4)
        # (83, "2024-04-19", "EURUSD", "72408.33", 4),
        # (83, "2024-04-19", "EURUSD", "72408.33", 4)
    ]
}

databases = [
    # {'path': '/Users/yanzhang/Stocks.db', 'table': 'Stocks', 'index_names': ('NASDAQ', 'S&P 500', 'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'HANG SENG INDEX')},
    # {'path': '/Users/yanzhang/Crypto.db', 'table': 'Crypto', 'index_names': ('Bitcoin', 'Ether', 'Binance', 'Bitcoin Cash', 'Solana', 'Monero', 'Litecoin')},
    # {'path': '/Users/yanzhang/Currencies.db', 'table': 'Currencies', 'index_names': ('DXY', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHY', 'USDINR', 'USDBRL', 'USDRUB', 'USDKRW', 'USDTRY', 'USDSGD', 'USDHKD')},
    # {'path': '/Users/yanzhang/Commodities.db', 'table': 'Commodities', 'index_names': ('Crude Oil', 'Brent', 'Natural gas', 'Coal', 'Uranium', 'Gold', 'Silver', 'Copper', 'Steel', 'Iron Ore', 'Lithium', 'Soybeans', 'Wheat', 'Lumber', 'Palm Oil', 'Rubber', 'Coffee', 'Cotton', 'Cocoa', 'Rice', 'Canola', 'Corn', 'Bitumen', 'Cobalt', 'Lead', 'Aluminum', 'Nickel', 'Tin', 'Zinc', 'Lean Hogs', 'Beef', 'Poultry', 'Salmon')},
    {'path': '/Users/yanzhang/Finance.db', 'table': 'Stocks'},
    {'path': '/Users/yanzhang/Finance.db', 'table': 'Crypto'},
    {'path': '/Users/yanzhang/Finance.db', 'table': 'Currencies'},
    {'path': '/Users/yanzhang/Finance.db', 'table': 'Commodities'}
    # 可以添加更多数据库配置
]

for db in databases:
    data_to_update = data_sets.get(db['table'], [])
    if data_to_update:
        update_data(db['path'], db['table'], data_to_update)