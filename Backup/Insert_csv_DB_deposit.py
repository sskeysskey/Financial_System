import sqlite3
import csv
from datetime import datetime

# --- 配置参数 ---
db_path = '/Users/yanzhang/Documents/Database/Firstrade.db'
# 假设您的 CSV 文件名为 deposit.csv 并且与脚本在同一目录或您提供完整路径
csv_path = '/Users/yanzhang/Downloads/deposit.csv' # 请确保这是您 CSV 文件的正确路径
table_name = 'Deposit'

def create_or_verify_table(conn):
    """
    在数据库中创建 Deposit 表 (如果不存在)。
    """
    cursor = conn.cursor()
    try:
        cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            value REAL NOT NULL,
            type INTEGER NOT NULL CHECK(type IN (0, 1, 2))
        )
        ''')
        conn.commit()
        print(f"数据表 '{table_name}' 已成功创建或已存在。")
        # 验证表结构 (可选)
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = [info[1] for info in cursor.fetchall()]
        print(f"数据表 '{table_name}' 的列: {columns}")
    except sqlite3.Error as e:
        print(f"创建或验证表 '{table_name}' 时发生错误: {e}")
        raise

def import_data_from_csv(conn):
    """
    从 CSV 文件导入数据到 Deposit 表。
    """
    cursor = conn.cursor()
    data_to_insert = []
    rows_processed = 0
    rows_skipped = 0

    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
            # ****** 修改此处：将 delimiter 从 '\t' 改为 ',' ******
            reader = csv.reader(csvfile, delimiter=',')
            
            header = next(reader, None) # 读取并跳过表头
            if header is None:
                print("CSV 文件为空或没有表头。")
                return
            print(f"CSV 文件表头: {header}") # 现在应该正确显示为 ['date', 'value', 'type']

            for i, row in enumerate(reader):
                rows_processed += 1
                try:
                    if len(row) != 3:
                        print(f"警告: 第 {i+2} 行数据列数不匹配 ({len(row)} 列)，应为 3 列。跳过此行: {row}")
                        rows_skipped += 1
                        continue

                    date_str, value_str, type_str = row

                    # 1. 转换日期格式
                    try:
                        parsed_date = datetime.strptime(date_str.strip(), "%Y.%m.%d")
                        formatted_date = parsed_date.strftime("%Y-%m-%d")
                    except ValueError:
                        print(f"警告: 第 {i+2} 行日期格式无效 '{date_str}'。跳过此行: {row}")
                        rows_skipped += 1
                        continue
                    
                    # 2. 转换 value 为 REAL (float)
                    try:
                        value = float(value_str.strip())
                    except ValueError:
                        print(f"警告: 第 {i+2} 行 value 值无效 '{value_str}'。跳过此行: {row}")
                        rows_skipped += 1
                        continue

                    # 3. 转换 type 为 INTEGER
                    try:
                        type_val = int(type_str.strip())
                        if type_val not in (0, 1, 2):
                            print(f"警告: 第 {i+2} 行 type 值无效 '{type_str}' (必须是 0, 1, 或 2)。跳过此行: {row}")
                            rows_skipped += 1
                            continue
                    except ValueError:
                        print(f"警告: 第 {i+2} 行 type 值无效 '{type_str}'。跳过此行: {row}")
                        rows_skipped += 1
                        continue
                    
                    data_to_insert.append((formatted_date, value, type_val))

                except Exception as e:
                    print(f"处理 CSV 第 {i+2} 行数据时发生意外错误: {e}。原始数据: {row}")
                    rows_skipped += 1
                    continue
        
        if data_to_insert:
            cursor.executemany(f'''
            INSERT INTO {table_name} (date, value, type)
            VALUES (?, ?, ?)
            ''', data_to_insert)
            conn.commit()
            print(f"成功导入 {len(data_to_insert)} 条数据到 '{table_name}' 表。")
        else:
            print("没有有效数据可供导入。")
        
        print(f"总共处理 CSV 行数 (不含表头): {rows_processed}") # 修正: rows_processed 已正确计数数据行
        print(f"成功准备导入的行数: {len(data_to_insert)}")
        print(f"跳过的行数: {rows_skipped}")


    except FileNotFoundError:
        print(f"错误: CSV 文件未找到路径 {csv_path}")
    except sqlite3.Error as e:
        print(f"向表 '{table_name}' 插入数据时发生 SQLite 错误: {e}")
        conn.rollback()
    except Exception as e:
        print(f"导入数据时发生未知错误: {e}")
        if conn:
            conn.rollback()

def main():
    """
    主函数，执行数据库连接、表创建和数据导入。
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        print(f"成功连接到数据库: {db_path}")

        create_or_verify_table(conn)
        import_data_from_csv(conn)

    except sqlite3.Error as e:
        print(f"数据库操作发生错误: {e}")
    except Exception as e:
        print(f"发生了一个预料之外的错误: {e}")
    finally:
        if conn:
            conn.close()
            print("数据库连接已关闭。")

if __name__ == '__main__':
    main()