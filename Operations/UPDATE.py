import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Coding/Database/Finance.db')
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
# cursor.execute("UPDATE MNSPP SET marketcap = 25650000000.0 pb = 34.43 WHERE id = 1219")
# cursor.execute("UPDATE MNSPP SET marketcap = 5375000000.0, pe_ratio = 66.25 WHERE symbol = 'ALH'")
# cursor.execute("UPDATE MNSPP SET pb = 34.43 WHERE id = 1219")
# cursor.execute("UPDATE Earning SET price = -24.6 WHERE id = 1624")
# cursor.execute("UPDATE Indices SET price = 20601.10 WHERE id = 134508")
# cursor.execute("UPDATE Earning SET date = '2024-09-13' WHERE id = 1624")
# cursor.execute("UPDATE Commodities SET price = 14.20 WHERE id = 105273")
# cursor.execute("UPDATE Currencies SET date = '2025-01-06' WHERE id = 144913")
# cursor.execute("UPDATE Currencies SET price = 6.6807 WHERE id = 215496")
# cursor.execute("UPDATE Technology SET price = 55.405 WHERE id = 1037700")

# 保留两位小数
# cursor.execute("UPDATE Currencies SET price = ROUND(price, 2) WHERE name = 'GBPI'")
# cursor.execute("UPDATE Technology SET price = ROUND(price, 2) WHERE name = 'MSTR'")

# 将所有name为'Russian'的记录改为'Russia'
# cursor.execute("UPDATE Commodities SET name = 'Huangjin' WHERE name = 'HuangJin'")
# cursor.execute("UPDATE Commodities SET name = 'YuMi' WHERE name = 'Corn'")
# cursor.execute("UPDATE ETFs SET name = 'GOEX260417C00058000' WHERE name = 'GOEX'")

# 更新数据库表中所有记录的price字段，保留2位小数
# cursor.execute("UPDATE Indices SET price = ROUND(price, 2)")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()