import sqlite3
from datetime import datetime

# 连接到数据库
conn = sqlite3.connect('/Users/yanzhang/DATABASE/Finance.db')
cursor = conn.cursor()

# 今天的日期
today = datetime.now().strftime('%Y-%m-%d')

# 更新Brent的价格和日期
# update_statement = """
# UPDATE your_table_name
# SET price = ?, date = ?
# WHERE name = 'Brent'
# """
# cursor.execute(update_statement, (50.0, today))

# 更新Brent的价格和日期
update_statement = """
UPDATE Commodities
SET price = NULL, date = NULL
WHERE name = 'Brent'
"""
cursor.execute(update_statement)

# # 删除Brent记录
# delete_statement = """
# DELETE FROM your_table_name
# WHERE name = 'Brent'
# """
# cursor.execute(delete_statement)

# 提交更改
conn.commit()

# 关闭连接
cursor.close()
conn.close()

print("更新成功！")