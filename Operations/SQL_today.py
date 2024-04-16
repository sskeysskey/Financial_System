import sqlite3
from datetime import datetime

# 数据库文件路径
database_path = "/Users/yanzhang/DATABASE/Finance.db"

# 今天的日期
today = datetime.now().strftime('%Y-%m-%d')

# 连接数据库
conn = sqlite3.connect(database_path)
cursor = conn.cursor()

# 执行查询
# 数据表名为 `Commodities`，日期字段为 `date`
query = f"""
SELECT *
FROM Commodities
WHERE date = '{today}'
"""

cursor.execute(query)

# 获取查询结果
rows = cursor.fetchall()

# 打印结果
for row in rows:
    print(row)

# 关闭连接
cursor.close()
conn.close()