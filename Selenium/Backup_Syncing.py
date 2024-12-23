import sqlite3
import json
from datetime import datetime, timedelta
import shutil  # 在文件最开始导入shutil模块

def copy_2_backup(source_path, destination_path):
    shutil.copy2(source_path, destination_path)  # 使用copy2来复制文件，并覆盖同名文件
    print(f"文件已从{source_path}复制到{destination_path}。")

# 备份数据库
copy_2_backup('/Users/yanzhang/Documents/Database/Finance.db', '/Users/yanzhang/Downloads/backup/DB_backup/Finance.db')
copy_2_backup('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json', '/Users/yanzhang/Documents/sskeysskey.github.io/economics/sectors_panel.json')
copy_2_backup('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', '/Users/yanzhang/Documents/sskeysskey.github.io/economics/sectors_all.json')
copy_2_backup('/Users/yanzhang/Documents/Financial_System/Modules/description.json', '/Users/yanzhang/Documents/sskeysskey.github.io/economics/description.json')
copy_2_backup('/Users/yanzhang/Documents/News/CompareStock.txt', '/Users/yanzhang/Documents/sskeysskey.github.io/economics/comparestock.txt')
copy_2_backup('/Users/yanzhang/Documents/News/CompareETFs.txt', '/Users/yanzhang/Documents/sskeysskey.github.io/economics/Compareetfs.txt')
copy_2_backup('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt', '/Users/yanzhang/Documents/sskeysskey.github.io/economics/marketcap_pe.txt')

# 连接到 SQLite 数据库文件
db_file = '/Users/yanzhang/Documents/Database/Finance.db'  # 你的数据库文件路径
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

# 获取数据库中的所有表名
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

# 定义一个字典来存储所有表的数据
database_dict = {}

# 获取一年前的日期
one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

# 遍历每一个表，将最近一年的数据导出为 JSON
for table_name in tables:
    table_name = table_name[0]
    
    # 获取表的列名
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    
    # 检查表是否有 'date' 列
    if 'date' in column_names:
        # 查询最近一年的数据
        cursor.execute(f"""
            SELECT * FROM {table_name}
            WHERE date >= ?
            ORDER BY date DESC
        """, (one_year_ago,))
    else:
        # 如果没有 'date' 列，获取所有数据
        cursor.execute(f"SELECT * FROM {table_name}")
    
    rows = cursor.fetchall()

    # 将表的数据存储为字典的形式
    table_data = [dict(zip(column_names, row)) for row in rows]
    database_dict[table_name] = table_data

# 将整个数据库字典转换为 JSON 字符串
json_data = json.dumps(database_dict, indent=4, default=str)

# 将 JSON 字符串写入文件
with open('/Users/yanzhang/Documents/sskeysskey.github.io/economics/finance.json', 'w', encoding='utf-8') as json_file:
    json_file.write(json_data)

# 关闭数据库连接
conn.close()

print(f"数据库 {db_file} 中最近一年的数据已成功导出为 finance.json 文件。")