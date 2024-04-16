import sqlite3
from datetime import datetime

# 连接到数据库
conn = sqlite3.connect('/Users/yanzhang/DATABASE/Finance.db')
cursor = conn.cursor()

# 今天的日期
today = datetime.now().strftime('%Y-%m-%d')

# 插入新的Brent记录
insert_statement = """
INSERT INTO Commodities (name, date, price)
VALUES (?, ?, ?)
"""
# cursor.execute(insert_statement, ('Brent', '2024-04-16', 40))
cursor.execute(insert_statement, ('Brent', today, 50))

# 提交更改
conn.commit()

# 关闭连接
cursor.close()
conn.close()

print("更新成功！")