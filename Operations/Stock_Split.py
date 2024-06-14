import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作
# cursor.execute("UPDATE Technology SET price = price / 2 WHERE name = 'APH'")

# 执行个股操作
cursor.execute("UPDATE Technology SET price = 68.69 WHERE id = 800969")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()