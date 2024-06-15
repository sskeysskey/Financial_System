import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作
# cursor.execute("UPDATE Technology SET price = price * 10 WHERE name = 'AVGO'")

# 执行个股操作
cursor.execute("UPDATE Technology SET price = 1735.04 WHERE id = 801336")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()