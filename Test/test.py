import sqlite3
import json

# 连接到 SQLite 数据库文件
db_file = '/Users/yanzhang/Documents/Database/Finance.db'  # 你的数据库文件路径
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

# 获取数据库中的所有表名
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

# 定义一个字典来存储所有表的数据
database_dict = {}

# 遍历每一个表，将数据导出为 JSON
for table_name in tables:
    table_name = table_name[0]
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()

    # 获取表的列名
    cursor.execute(f"PRAGMA table_info({table_name})")
    column_names = [col[1] for col in cursor.fetchall()]

    # 将表的数据存储为字典的形式
    table_data = [dict(zip(column_names, row)) for row in rows]
    database_dict[table_name] = table_data

# 将整个数据库字典转换为 JSON 字符串
json_data = json.dumps(database_dict, indent=4)

# 将 JSON 字符串写入文件
with open('/Users/yanzhang/Downloads/Finance.json', 'w', encoding='utf-8') as json_file:
    json_file.write(json_data)

# 关闭数据库连接
conn.close()

print(f"数据库 {db_file} 已成功导出为 Finance.json 文件。")