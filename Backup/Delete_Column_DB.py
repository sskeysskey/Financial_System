import sqlite3

# 数据库文件路径
db_path = '/Users/yanzhang/Documents/Database/Finance.db'
conn = None

try:
    # 1. 连接到数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("成功连接到数据库...")

    # 将所有操作包裹在一个事务中
    cursor.execute("BEGIN TRANSACTION;")
    print("事务已开始...")

    # 2. 创建一个没有 'name' 列的新表
    print("步骤 1: 创建新表 MNSPP_new...")
    cursor.execute("""
    CREATE TABLE MNSPP_new (
        id INTEGER PRIMARY KEY,
        symbol TEXT,
        shares REAL,
        marketcap REAL,
        pe_ratio REAL,
        pb REAL
    );
    """)

    # 3. 将旧表的数据复制到新表
    # 注意我们在这里明确列出了需要保留的列，排除了 'name' 列
    print("步骤 2: 从旧表复制数据到新表...")
    cursor.execute("""
    INSERT INTO MNSPP_new (id, symbol, shares, marketcap, pe_ratio, pb)
    SELECT id, symbol, shares, marketcap, pe_ratio, pb
    FROM MNSPP;
    """)

    # 4. 删除旧表
    print("步骤 3: 删除旧表 MNSPP...")
    cursor.execute("DROP TABLE MNSPP;")

    # 5. 将新表重命名为旧表的名称
    print("步骤 4: 重命名新表为 MNSPP...")
    cursor.execute("ALTER TABLE MNSPP_new RENAME TO MNSPP;")

    # 6. 提交事务，使所有更改生效
    conn.commit()
    print("事务已成功提交！'name' 列已通过重建表的方式被移除。")

except sqlite3.Error as e:
    print(f"发生错误: {e}")
    if conn:
        # 如果任何步骤失败，回滚所有更改
        conn.rollback()
        print("操作已回滚，数据库未做任何更改。")

finally:
    # 关闭数据库连接
    if conn:
        conn.close()
        print("数据库连接已关闭。")