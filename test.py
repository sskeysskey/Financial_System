import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行更新操作
cursor.execute("UPDATE Technology SET price = 121.79 WHERE id = 800542")

# 提交更改
conn.commit()


# 关闭数据库连接
conn.close()