import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('/Users/yanzhang/Documents/Database/Finance.db')
cursor = conn.cursor()

# 股票名称和拆股比例
name = 'SCHG'
price_divisor = 4

# 获取该股票的最新日期
cursor.execute("""
    SELECT MAX(date) 
    FROM ETFs 
    WHERE name = ?
""", (name,))
latest_date = cursor.fetchone()[0]  # 获取最新日期

# 执行拆股操作，排除最新日期的数据
cursor.execute("""
    UPDATE ETFs 
    SET price = ROUND(price / ?, 2) 
    WHERE name = ? AND date < ?
""", (price_divisor, name, latest_date))

# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()