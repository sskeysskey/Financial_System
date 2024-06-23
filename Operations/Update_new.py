import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作
# cursor.execute("UPDATE Technology SET price = price * 10 WHERE name = 'AVGO'")

# # 执行个股操作
# cursor.execute("UPDATE Technology SET price = 1735.04 WHERE id = 801336")

# # 如果只想更新特定的name，比如Binance
# cursor.execute("UPDATE Crypto SET price = ROUND(price, 1) WHERE name = 'Binance'")

# 更新所有记录的price字段，保留一位小数
cursor.execute("UPDATE Indices SET price = ROUND(price, 2)")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()