import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作 I ， 并保留两位小数
# name = 'SONY'
# price_divisor = 5

# cursor.execute("""
#     UPDATE Technology 
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
# cursor.execute("UPDATE Technology SET price = 19.03 WHERE id = 866865")
# cursor.execute("UPDATE Economics SET price = -0.2 WHERE id = 252")

# 保留两位小数
# cursor.execute("UPDATE Industrials SET price = ROUND(price, 2) WHERE name = 'TTEK'")
# cursor.execute("UPDATE Technology SET price = ROUND(price, 2) WHERE name = 'MSTR'")

# 将所有name为'Russian'的记录改为'Russia'
# cursor.execute("UPDATE Economics SET name = 'USCPI' WHERE name = 'USInflation'")

# 更新数据库表中所有记录的price字段，保留2位小数
# cursor.execute("UPDATE Indices SET price = ROUND(price, 2)")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()