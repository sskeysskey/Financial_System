import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作
# name = 'CMG'
# price_divisor = 50
# cursor.execute("UPDATE Consumer_Cyclical SET price = price / ? WHERE name = ?", (price_divisor, name))

# # 执行个股操作
# cursor.execute("UPDATE Consumer_Cyclical SET price = 65.66 WHERE id = 691483")

# # 如果只想更新特定的name，比如Binance
cursor.execute("UPDATE Consumer_Cyclical SET price = ROUND(price, 2) WHERE name = 'CMG'")

# 更新所有记录的price字段，保留一位小数
# cursor.execute("UPDATE Indices SET price = ROUND(price, 2)")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()