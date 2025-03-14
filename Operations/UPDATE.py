import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作 I ， 并保留两位小数
# name = 'SCHG'
# price_divisor = 4

# cursor.execute("""
#     UPDATE ETFs 
#     SET price = ROUND(price / ?, 2) 
#     WHERE name = ?
# """, (price_divisor, name))

# 执行拆股操作 II
# name = 'RYAAY'
# price_multiplier = 2 / 5  # 2股拆5股的乘数

# cursor.execute("""
#     UPDATE Industrials 
#     SET price = ROUND(price * ?, 2)  
#     WHERE name = ?
# """, (price_multiplier, name))

# 更新价格字段
# cursor.execute("UPDATE Earning SET price = 5.2 WHERE id = 1393")
cursor.execute("UPDATE Earning SET date = '2024-09-13' WHERE id = 33")
# cursor.execute("UPDATE Commodities SET price = 13.85 WHERE id = 104735")
# cursor.execute("UPDATE Currencies SET date = '2025-01-06' WHERE id = 144913")

# 保留两位小数
# cursor.execute("UPDATE Currencies SET price = ROUND(price, 2) WHERE name = 'DXY'")
# cursor.execute("UPDATE Technology SET price = ROUND(price, 2) WHERE name = 'MSTR'")

# 将所有name为'Russian'的记录改为'Russia'
# cursor.execute("UPDATE Commodities SET name = 'HuangJin' WHERE name = 'Gold'")
# cursor.execute("UPDATE Commodities SET name = 'YuMi' WHERE name = 'Corn'")

# 更新数据库表中所有记录的price字段，保留2位小数
# cursor.execute("UPDATE Indices SET price = ROUND(price, 2)")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()