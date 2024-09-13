import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作并保留两位小数
# name = 'CTAS'
# price_divisor = 4

# cursor.execute("""
#     UPDATE Industrials 
#     SET price = ROUND(price / ?, 2) 
#     WHERE name = ?
# """, (price_divisor, name))

# 执行拆股操作 II
# price_multiplier = 2 / 3  # 2股拆3股的乘数

# name = 'SIRI'
# price_multiplier = 10  # 2股拆3股的乘数

# cursor.execute("""
#     UPDATE Communication_Services 
#     SET price = ROUND(price * ?, 2)  
#     WHERE name = ?
# """, (price_multiplier, name))

# 更新价格字段
# cursor.execute("UPDATE Industrials SET price = 204.96 WHERE id = 958844")
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