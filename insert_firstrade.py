import csv
import sqlite3

def import_csv_to_sqlite(db_path, csv_path):
    """
    将CSV文件中的数据导入到SQLite数据库的 'Deals' 表中。
    如果特定日期的数据已存在，则会进行覆盖。

    参数:
        db_path (str): SQLite数据库文件的路径。
        csv_path (str): CSV文件的路径。
    """
    conn = None  # 初始化conn，以便在finally块中可用
    try:
        # 1. 连接到SQLite数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 2. 读取CSV文件
        #    假设CSV文件使用UTF-8编码。如果不是，请更改 'encoding' 参数。
        with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
            csv_reader = csv.DictReader(csvfile)
            
            # 检查CSV表头是否包含必需的列
            if 'Date' not in csv_reader.fieldnames or 'Value' not in csv_reader.fieldnames:
                print(f"错误：CSV文件 '{csv_path}' 必须包含 'Date' 和 'Value' 列。")
                conn.close() # 关闭连接
                return

            print(f"开始从 '{csv_path}' 导入数据到数据库 '{db_path}' 的 Deals 表...")

            for row_num, row in enumerate(csv_reader, 1):
                try:
                    date_val = row['Date']
                    # 将 'Value' 转换为浮点数
                    value_val = float(row['Value'])
                except KeyError:
                    print(f"错误：CSV文件第 {row_num} 行（数据：{row}）缺少 'Date' 或 'Value' 字段。请检查CSV文件格式。")
                    continue # 跳过此行，继续处理下一行
                except ValueError:
                    print(f"错误：无法将CSV文件第 {row_num} 行（数据：{row}）中的 'Value' 转换为数字。请检查CSV数据。")
                    continue # 跳过此行

                # 3. 尝试插入或更新数据
                try:
                    # 方法1：使用 INSERT ... ON CONFLICT (推荐，需要 'date' 列有 UNIQUE 约束)
                    # 'id' 列假定为自增主键，不需要在INSERT语句中显式提供。
                    # 'excluded.value' 指的是在发生冲突时，VALUES子句中提供的新值。
                    sql_upsert = """
                    INSERT INTO Deals (date, value)
                    VALUES (?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        value = excluded.value;
                    """
                    cursor.execute(sql_upsert, (date_val, value_val))
                except sqlite3.OperationalError as e:
                    # 如果 'date' 列没有 UNIQUE 约束，或者 SQLite 版本过低，
                    # ON CONFLICT 子句可能会失败 (例如: "ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint")
                    # print(f"处理日期 {date_val} 时使用 ON CONFLICT 发生错误: {e}")
                    # print("尝试使用 'DELETE then INSERT' 方法作为备选。")
                    
                    # 方法2：备选方法 - 先删除后插入
                    # 这种方法不需要 'date' 列有 UNIQUE 约束，但能实现基于日期的覆盖。
                    try:
                        cursor.execute("DELETE FROM Deals WHERE date = ?", (date_val,))
                        cursor.execute("INSERT INTO Deals (date, value) VALUES (?, ?)", (date_val, value_val))
                    except Exception as alt_e:
                        print(f"使用备选方法处理日期 {date_val} (行号 {row_num}) 时也发生错误: {alt_e}")
                        # 根据需要，您可以决定是继续还是中止
                        continue
            
        # 4. 提交事务
        conn.commit()
        print(f"数据已成功从 '{csv_path}' 导入到数据库 '{db_path}' 的 Deals 表中。")

    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        if conn:
            conn.rollback() # 如果发生错误，回滚更改
    except FileNotFoundError:
        print(f"错误: CSV文件 '{csv_path}' 未找到。请检查路径是否正确。")
    except Exception as e:
        print(f"发生意外错误: {e}")
    finally:
        # 5. 关闭数据库连接
        if conn:
            conn.close()

# --- 主程序执行部分 ---
if __name__ == '__main__':
    # 请将以下路径替换为您的实际文件路径
    database_file_path = "/Users/yanzhang/Documents/Database/Firstrade.db"
    csv_file_path = "/Users/yanzhang/Downloads/Firstrade/Transaction.csv" 

    # 调用函数执行导入操作
    import_csv_to_sqlite(database_file_path, csv_file_path)