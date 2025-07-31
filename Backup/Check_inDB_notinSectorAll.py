import json
import sqlite3
import os

def find_mismatched_symbols(json_file_path, db_file_path):
    """
    检索数据库内每个数据表内的所有symbol，
    然后去跟sector_all相应分组下的symbol取匹配，
    如果找到匹配不上的，则告知是哪些symbol，以及各自有多少数量。

    Args:
        json_file_path (str): Sectors_All.json 文件的路径。
        db_file_path (str): Finance.db 数据库文件的路径。

    Returns:
        list: 包含不匹配信息的字典列表，每个字典包含
              'sector', 'symbol', 'count_in_db'。
              如果没有不匹配项，则返回空列表。
    """
    mismatched_symbols_report = []

    # 1. 加载 JSON 数据
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            sectors_all_json = json.load(f)
        print(f"成功加载 JSON 文件: {json_file_path}")
    except FileNotFoundError:
        print(f"错误: JSON 文件未找到 {json_file_path}")
        return mismatched_symbols_report
    except json.JSONDecodeError:
        print(f"错误: JSON 文件格式无效 {json_file_path}")
        return mismatched_symbols_report
    except Exception as e:
        print(f"加载 JSON 文件时发生未知错误: {e}")
        return mismatched_symbols_report

    # 2. 连接 SQLite 数据库
    if not os.path.exists(db_file_path):
        print(f"错误: 数据库文件未找到 {db_file_path}")
        return mismatched_symbols_report

    conn = None
    try:
        conn = sqlite3.connect(db_file_path)
        cursor = conn.cursor()
        print(f"成功连接到数据库: {db_file_path}")

        # 3. 遍历 Sector
        for sector_name, json_symbols_list in sectors_all_json.items():
            print(f"\n正在处理 Sector/Table: {sector_name}...")
            json_symbols_set = set(json_symbols_list) # 转换为集合以便高效查找

            # 3.b. 查询数据库表中的所有不重复 symbol
            try:
                # 首先检查表是否存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (sector_name,))
                if cursor.fetchone() is None:
                    print(f"  警告: 数据库中未找到名为 '{sector_name}' 的表。跳过此 sector。")
                    continue

                query_symbols = f"SELECT DISTINCT name FROM \"{sector_name}\";" # 使用双引号以防表名包含特殊字符
                cursor.execute(query_symbols)
                db_symbols_tuples = cursor.fetchall()
                db_symbols_set = {row[0] for row in db_symbols_tuples if row[0] is not None} # 确保 symbol 不为 None

                print(f"  JSON 中的 Symbols: {sorted(list(json_symbols_set)) if json_symbols_set else '无'}")
                print(f"  数据库中的 Symbols: {sorted(list(db_symbols_set)) if db_symbols_set else '无'}")

                # 3.c. 比较 Symbol：找出数据库表中有，但 JSON 文件对应 sector 中没有的 symbol
                symbols_in_db_not_in_json = db_symbols_set - json_symbols_set

                if not symbols_in_db_not_in_json:
                    print(f"  在表 '{sector_name}' 中未找到不匹配的 symbols。")
                else:
                    print(f"  在表 '{sector_name}' 中找到以下 symbols 存在于数据库但不存在于 JSON:")
                    for symbol in symbols_in_db_not_in_json:
                        # 3.d. 统计数量
                        query_count = f"SELECT COUNT(*) FROM \"{sector_name}\" WHERE name = ?;"
                        cursor.execute(query_count, (symbol,))
                        count = cursor.fetchone()[0]
                        print(f"    - Symbol: '{symbol}', 数量: {count}")
                        mismatched_symbols_report.append({
                            "sector": sector_name,
                            "symbol": symbol,
                            "count_in_db": count
                        })

            except sqlite3.Error as e:
                print(f"  处理表 '{sector_name}' 时发生数据库错误: {e}")
            except Exception as e:
                print(f"  处理表 '{sector_name}' 时发生未知错误: {e}")


    except sqlite3.Error as e:
        print(f"连接或操作数据库时发生错误: {e}")
    finally:
        if conn:
            conn.close()
            print("\n数据库连接已关闭。")

    return mismatched_symbols_report

if __name__ == "__main__":
    # 请将以下路径替换为您的实际文件路径
    # 注意：在Python字符串中，反斜杠 '\' 是转义字符。
    # 您可以使用正斜杠 '/' 或者双反斜杠 '\\'。
    json_path = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json"
    db_path = "/Users/yanzhang/Coding/Database/Finance.db"

    # 确保路径是正确的
    # 如果您在Windows上，路径可能看起来像:
    # json_path = "C:\\Users\\yanzhang\\Documents\\Financial_System\\Modules\\Sectors_All.json"
    # db_path = "C:\\Users\\yanzhang\\Documents\\Database\\Finance.db"
    # 或者使用原始字符串:
    # json_path = r"C:\Users\yanzhang\Documents\Financial_System\Modules\Sectors_All.json"
    # db_path = r"C:\Users\yanzhang\Documents\Database\Finance.db"


    print("开始执行 Symbol 匹配程序...")
    results = find_mismatched_symbols(json_path, db_path)

    if results:
        print("\n--- 不匹配的 Symbol 总结 ---")
        for item in results:
            print(f"Sector/Table: {item['sector']}, Symbol: '{item['symbol']}', 在数据库中的数量: {item['count_in_db']}")
    else:
        if os.path.exists(json_path) and os.path.exists(db_path): # 只有当文件都存在时才说“未发现”
             print("\n--- 总结 ---")
             print("未发现任何不匹配的 Symbols，或者相关文件无法访问。")
        else:
            print("\n--- 总结 ---")
            print("由于文件访问问题，无法完成匹配。请检查文件路径和权限。")

    print("\n程序执行完毕。")