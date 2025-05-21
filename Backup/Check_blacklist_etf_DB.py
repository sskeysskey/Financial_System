import json
import sqlite3
import os

def find_etfs_in_database(json_path, db_path):
    """
    从 JSON 文件中读取 ETF 代码，并在 SQLite 数据库中查找它们。

    参数:
    json_path (str): 黑名单 JSON 文件的路径。
    db_path (str): SQLite 数据库文件的路径。

    返回:
    dict: 一个字典，其中键是找到的 ETF 代码，值是它们在数据库中出现的次数。
          如果发生错误或未找到，则返回空字典或打印错误信息。
    """
    etf_symbols_to_check = []
    found_etfs_counts = {}

    # 1. 从 JSON 文件加载 ETF 代码
    try:
        # 确保路径是绝对路径，或者相对于脚本的路径是正确的
        # 如果用户提供的路径已经是绝对路径，os.path.abspath 不会改变它
        absolute_json_path = os.path.abspath(json_path)
        if not os.path.exists(absolute_json_path):
            print(f"错误：JSON 文件未找到: {absolute_json_path}")
            return found_etfs_counts

        with open(absolute_json_path, 'r', encoding='utf-8') as f:
            blacklist_data = json.load(f)
        
        if "etf" in blacklist_data and isinstance(blacklist_data["etf"], list):
            etf_symbols_to_check = blacklist_data["etf"]
        else:
            print("警告：在 JSON 文件的 'etf' 键下没有找到 ETF 列表，或者格式不正确。")
            return found_etfs_counts

        if not etf_symbols_to_check:
            print("信息：黑名单中的 'etf' 列表为空，无需查询。")
            return found_etfs_counts
            
    except FileNotFoundError:
        print(f"错误：JSON 文件未找到: {json_path}")
        return found_etfs_counts
    except json.JSONDecodeError:
        print(f"错误：无法解码 JSON 文件: {json_path}")
        return found_etfs_counts
    except Exception as e:
        print(f"读取 JSON 文件时发生未知错误: {e}")
        return found_etfs_counts

    # 2. 连接到 SQLite 数据库并查询
    conn = None
    try:
        absolute_db_path = os.path.abspath(db_path)
        if not os.path.exists(absolute_db_path):
            print(f"错误：数据库文件未找到: {absolute_db_path}")
            return found_etfs_counts
            
        conn = sqlite3.connect(absolute_db_path)
        cursor = conn.cursor()

        print(f"将要查询的 ETF 代码: {etf_symbols_to_check}")

        for symbol in etf_symbols_to_check:
            # 使用参数化查询以防止 SQL 注入
            query = "SELECT COUNT(*) FROM ETFs WHERE name = ?"
            cursor.execute(query, (symbol,))
            count_result = cursor.fetchone() # fetchone() 返回一个元组，例如 (5,) 或 (0,)
            
            if count_result and count_result[0] > 0:
                count = count_result[0]
                found_etfs_counts[symbol] = count
                print(f"找到代码 '{symbol}' 在数据库中，数量: {count}")
            else:
                print(f"代码 '{symbol}' 未在数据库中找到，或者数量为 0。")

    except sqlite3.Error as e:
        print(f"SQLite 数据库错误: {e}")
    except Exception as e:
        print(f"连接或查询数据库时发生未知错误: {e}")
    finally:
        if conn:
            conn.close()
            print("数据库连接已关闭。")

    return found_etfs_counts

# --- 使用示例 ---
# 请确保将下面的路径替换为您系统中实际的文件路径
json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json"
db_file_path = "/Users/yanzhang/Documents/Database/Finance.db"

# 调用函数
results = find_etfs_in_database(json_file_path, db_file_path)

# 打印结果
if results:
    print("\n--- 总结 ---")
    print("在数据库中找到的 ETF 代码及其数量:")
    for symbol, count in results.items():
        print(f"- 代码: {symbol}, 数量: {count}")
else:
    print("\n--- 总结 ---")
    print("未能从黑名单中找到任何 ETF 代码在数据库中，或者在处理过程中发生错误。")