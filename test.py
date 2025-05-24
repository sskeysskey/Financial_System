import csv
import sqlite3
import os

# --- 配置 ---
csv_file_path = '/Users/yanzhang/Downloads/Firstrade/Deals.csv' # 如果CSV文件不在当前目录，请修改为完整路径
db_file_path = '/Users/yanzhang/Documents/Database/Firstrade.db' # 您的数据库文件路径
table_name = 'Deals'

def import_csv_to_sqlite_alternative(csv_path, db_path, table):
    """
    从 CSV 文件读取数据并将其导入/更新到 SQLite 数据库的指定表中。
    此版本不使用 ON CONFLICT，而是先 SELECT 再 UPDATE/INSERT。
    适用于 'date' 列没有 UNIQUE 约束的情况。
    """
    conn = None
    processed_count = 0
    updated_count = 0
    inserted_count = 0

    if not os.path.exists(csv_path):
        print(f"错误：CSV 文件未找到: {csv_path}")
        return

    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        print(f"错误：数据库目录不存在: {db_dir}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print(f"成功连接到数据库: {db_path}")

        # 确保表存在 (如果不存在则创建)
        # 注意：此处的 CREATE TABLE 语句不会强制 UNIQUE 约束，以匹配“不修改表结构”的场景
        # 但如果表已存在，它不会改变现有结构。
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            value REAL
        );
        """)
        print(f"表 '{table}' 已准备就绪。")

        records_from_csv = []
        with open(csv_path, mode='r', newline='', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            for row_num, row in enumerate(csv_reader, 1):
                try:
                    date_str = row['Date']
                    value_str = row['Value']
                    value_float = float(value_str)
                    records_from_csv.append({'date': date_str, 'value': value_float})
                except KeyError as e:
                    print(f"警告: CSV 文件第 {row_num} 行缺少列: {e}。跳过此行。 ({row})")
                except ValueError as e:
                    print(f"警告: CSV 文件第 {row_num} 行的值无法转换为数字: {e}。跳过此行。 ({row})")
                except Exception as e:
                    print(f"警告: 处理 CSV 文件第 {row_num} 行时发生未知错误: {e}。跳过此行。 ({row})")
        
        if not records_from_csv:
            print("CSV 文件中没有找到有效数据进行处理。")
            return

        for record in records_from_csv:
            csv_date = record['date']
            csv_value = record['value']
            
            processed_count += 1

            # 检查记录是否存在
            cursor.execute(f"SELECT value, id FROM {table} WHERE date = ?", (csv_date,))
            existing_entry = cursor.fetchone()

            if existing_entry:
                # 记录存在，更新它
                db_value = existing_entry[0]
                # db_id = existing_entry[1] # 如果需要按id更新
                if db_value != csv_value: # 只有当值不同时才执行更新并计数
                    cursor.execute(f"UPDATE {table} SET value = ? WHERE date = ?", (csv_value, csv_date))
                    # 注意：如果一个日期有多条记录（因为没有UNIQUE约束），这将更新所有匹配日期的记录。
                    # 如果只想更新一条（例如基于id），逻辑会更复杂。
                    # 假设我们更新所有匹配该日期的记录。
                    if cursor.rowcount > 0: # rowcount 会返回受影响的行数
                        updated_count += cursor.rowcount # 或 updated_count +=1 如果只想计数操作次数
            else:
                # 记录不存在，插入新记录
                cursor.execute(f"INSERT INTO {table} (date, value) VALUES (?, ?)", (csv_date, csv_value))
                if cursor.rowcount > 0:
                    inserted_count += 1
        
        conn.commit()
        print(f"数据处理完成。总共处理 CSV 记录: {len(records_from_csv)}.")
        print(f"  更新的记录数/次数: {updated_count}") # 注意这里的计数含义可能略有不同
        print(f"  插入的记录数: {inserted_count}")

    except FileNotFoundError:
        print(f"错误: CSV 文件 '{csv_path}' 未找到。")
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        if conn:
            conn.rollback()
            print("操作已回滚。")
    except Exception as e:
        print(f"发生意外错误: {e}")
        if conn:
            conn.rollback()
            print("操作已回滚。")
    finally:
        if conn:
            conn.close()
            print("数据库连接已关闭。")

# --- 主程序执行 (使用 alternative 函数) ---
if __name__ == '__main__':
    print(f"正在尝试从 '{csv_file_path}' 导入数据到 '{db_file_path}' 的表 '{table_name}' (使用 alternative 方法)...")
    # import_csv_to_sqlite(csv_file_path, db_file_path, table_name) # 调用原始函数
    import_csv_to_sqlite_alternative(csv_file_path, db_file_path, table_name) # 调用修改后的函数

    # (可选) 验证数据库中的数据
    print("\n验证数据库内容:")
    try:
        conn_verify = sqlite3.connect(db_file_path)
        cursor_verify = conn_verify.cursor()
        
        print("\nDeals 表中与CSV日期 '2015-01-02' 相关的数据:")
        cursor_verify.execute(f"SELECT id, date, value FROM {table_name} WHERE date = '2015-01-02' ORDER BY id DESC LIMIT 5") # 显示最新的几条
        for row in cursor_verify.fetchall():
            print(row)

        print("\nDeals 表中与CSV日期 '2025-05-21' 相关的数据:")
        cursor_verify.execute(f"SELECT id, date, value FROM {table_name} WHERE date = '2025-05-21' ORDER BY id DESC LIMIT 5")
        for row in cursor_verify.fetchall():
            print(row)
        
        conn_verify.close()
    except sqlite3.Error as e:
        print(f"验证时发生数据库错误: {e}")
    except Exception as e:
        print(f"验证时发生未知错误: {e}")