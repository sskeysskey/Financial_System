import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作
cursor.execute("UPDATE Energy SET price = price / 2 WHERE name = 'CNQ'")

# 执行个股操作
# cursor.execute("UPDATE Energy SET price = 35.46 WHERE id = 393514")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()