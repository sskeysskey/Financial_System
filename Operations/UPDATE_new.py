import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 执行拆股操作 I
# name = 'MSTR'
# price_divisor = 10
# cursor.execute("UPDATE Technology SET price = price / ? WHERE name = ?", (price_divisor, name))

# 执行拆股操作 II
# name = 'WRB'
# price_multiplier = 2 / 3  # 2股拆3股的乘数

# cursor.execute("""
#     UPDATE Financial_Services 
#     SET price = ROUND(price * ?, 2)  
#     WHERE name = ?
# """, (price_multiplier, name))

# 更新价格字段
# cursor.execute("UPDATE Commodities SET price = 1677.0 WHERE id = 101175")
cursor.execute("UPDATE Technology SET price = 124.68 WHERE id = 832165")

# 保留两位小数
# cursor.execute("UPDATE Economics SET price = ROUND(price, 2) WHERE name = 'USInitial'")
# cursor.execute("UPDATE Technology SET price = ROUND(price, 2) WHERE name = 'MSTR'")

# 将所有name为'Russian'的记录改为'Russia'
# cursor.execute("UPDATE Economics SET name = 'USNonFarm' WHERE name = 'USPayroll'")

# 更新数据库表中所有记录的price字段，保留2位小数
# cursor.execute("UPDATE Indices SET price = ROUND(price, 2)")

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()