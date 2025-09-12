import sqlite3

db_path = "/Users/yanzhang/Coding/Database/Finance.db"
conn = sqlite3.connect(db_path)
try:
    cur = conn.cursor()
    # 如无外键依赖，直接删除
    cur.execute("DELETE FROM sync_log;")
    conn.commit()
    # 可选：回收空间
    cur.execute("VACUUM;")
finally:
    conn.close()