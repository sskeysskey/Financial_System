import sqlite3

conn = sqlite3.connect('/Users/yanzhang/DATABASE/Finance.db')
cursor = conn.cursor()

cursor.execute("SELECT * FROM Commodities")
rows = cursor.fetchall()

# 打印列名
columns = [description[0] for description in cursor.description]
print(" | ".join(columns))

# 打印数据行
for row in rows:
    print(" | ".join(str(item) for item in row))

conn.close()