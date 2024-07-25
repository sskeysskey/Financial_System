import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作 I
# name = 'AVGO'
# price_divisor = 10
# cursor.execute("UPDATE Technology SET price = price / ? WHERE name = ?", (price_divisor, name))

# 执行拆股操作 II
# name = 'WRB'
# price_multiplier = 2 / 3  # 2股拆3股的乘数

# cursor.execute("""
#     UPDATE Financial_Services 
#     SET price = ROUND(price * ?, 2)  
#     WHERE name = ?
# """, (price_multiplier, name))

# 更新价格字段
# cursor.execute("UPDATE Commodities SET price = 14.24 WHERE id = 100811")

# 保留两位小数
# cursor.execute("UPDATE Technology SET price = ROUND(price, 3) WHERE name = 'AVGO'")

# 将所有name为'Russian'的记录改为'Russia'
# cursor.execute("UPDATE Commodities SET name = 'PalmOil' WHERE name = 'Palm Oil'")

# 更新数据库表中所有记录的price字段，保留2位小数
# cursor.execute("UPDATE Indices SET price = ROUND(price, 2)")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()