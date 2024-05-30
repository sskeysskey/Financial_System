import json
import sqlite3
from datetime import datetime, timedelta

db_path = '/Users/yanzhang/Documents/Database/Finance.db'
json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
error_file = '/Users/yanzhang/Documents/News/Today_error.txt'

yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
# 读取 JSON 文件
def read_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

# 连接数据库并查询数据
def query_data(table, name):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = f"SELECT * FROM {table} WHERE name = ? AND date = ?"
    cursor.execute(query, (name, yesterday))
    result = cursor.fetchone()
    conn.close()
    return result

# 写入错误信息
def write_error(error_message):
    with open(error_file, 'a') as file:
        file.write(error_message + '\n')

# 主执行函数
def main():
    data = read_json(json_path)
    for table, names in data.items():
        for name in names:
            if not query_data(table, name):
                error_msg = f"在表 {table} 中找不到名称为 {name} 且日期为 {yesterday} 的数据"
                write_error(error_msg)

if __name__ == "__main__":
    main()