import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作
# name = 'WSM'
# price_divisor = 2
# cursor.execute("UPDATE Consumer_Cyclical SET price = price / ? WHERE name = ?", (price_divisor, name))

# 执行拆股操作
# name = 'WRB'
# price_multiplier = 2 / 3  # 2股拆3股的乘数

# cursor.execute("""
#     UPDATE Financial_Services 
#     SET price = ROUND(price * ?, 2)  
#     WHERE name = ?
# """, (price_multiplier, name))

# 更新价格字段
cursor.execute("UPDATE Financial_Services SET price = 53.09 WHERE id = 922158")

# 保留两位小数
# cursor.execute("UPDATE Consumer_Cyclical SET price = ROUND(price, 2) WHERE name = 'CMG'")

# 将所有name为'Russian'的记录改为'Russia'
# cursor.execute("UPDATE Commodities SET name = 'PalmOil' WHERE name = 'Palm Oil'")

# 更新所有记录的price字段，保留一位小数
# cursor.execute("UPDATE Indices SET price = ROUND(price, 2)")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()