import json
import sqlite3
from collections import Counter

def find_unmatched_names(json_path, db_path):
    """
    查找 SQLite 数据库 Economics 表中存在，但在 JSON 文件中未定义的 name 及其数量。

    Args:
        json_path (str): Sectors_All.json 文件的路径。
        db_path (str): Finance.db 数据库文件的路径。

    Returns:
        dict: 一个字典，键是未匹配的 name，值是它们在 Economics 表中出现的次数。
              如果所有 name 都匹配，则返回一个空字典。
    """
    all_json_symbols = set()

    # 1. 读取并解析 JSON 文件，获取所有分组下的 symbol
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            sectors_data = json.load(f)
        
        for sector_name, symbols_list in sectors_data.items():
            if isinstance(symbols_list, list):
                for symbol in symbols_list:
                    all_json_symbols.add(str(symbol)) # 确保 symbol 是字符串
            else:
                print(f"警告：JSON 文件中 '{sector_name}' 的值不是一个列表，已跳过。")

        if not all_json_symbols:
            print("警告：未能从 JSON 文件中加载任何 symbol。")

    except FileNotFoundError:
        print(f"错误：找不到 JSON 文件 '{json_path}'")
        return None
    except json.JSONDecodeError:
        print(f"错误：JSON 文件 '{json_path}' 格式无效")
        return None
    except Exception as e:
        print(f"读取 JSON 文件时发生未知错误: {e}")
        return None

    # 2. 连接 SQLite 数据库并查询 Economics 表中的所有 name
    db_names = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查 Economics 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Economics';")
        if cursor.fetchone() is None:
            print(f"错误：数据库 '{db_path}' 中不存在名为 'Economics' 的表。")
            conn.close()
            return None

        cursor.execute("SELECT name FROM Economics")
        rows = cursor.fetchall()
        # rows 是一个元组列表，例如 [(name1,), (name2,)]
        # 我们需要提取每个元组的第一个元素
        db_names = [row[0] for row in rows if row[0] is not None] # 确保 name 不是 NULL

        conn.close()
        
        if not db_names:
            print("信息：数据库的 Economics 表中没有找到任何 name。")
            return {} # 返回空字典，因为没有可比较的名称

    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        return None
    except Exception as e:
        print(f"连接或查询数据库时发生未知错误: {e}")
        return None

    # 3. 找出在 db_names 中但不在 all_json_symbols 中的 name，并统计数量
    unmatched_name_counts = Counter()
    for name_in_db in db_names:
        name_in_db_str = str(name_in_db) # 确保比较的是字符串
        if name_in_db_str not in all_json_symbols:
            unmatched_name_counts[name_in_db_str] += 1
            
    return dict(unmatched_name_counts) # 将 Counter 对象转换为普通字典

# --- 主程序 ---
if __name__ == "__main__":
    # 请将下面的路径替换成你的实际文件路径
    json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
    db_file_path = "/Users/yanzhang/Documents/Database/Finance.db"

    print(f"正在从 JSON 文件 '{json_file_path}' 加载股票代码...")
    print(f"正在从数据库 '{db_file_path}' 的 Economics 表加载名称...")
    
    unmatched_results = find_unmatched_names(json_file_path, db_file_path)

    if unmatched_results is None:
        print("处理过程中发生错误，请检查上面的错误信息。")
    elif not unmatched_results: # 如果字典为空
        print("\n太棒了！Economics 表中的所有 name 都在 Sectors_All.json 中找到了匹配项。")
    else:
        print("\n在 Economics 表中找到但在 Sectors_All.json 中未匹配的 name 及其数量：")
        for name, count in unmatched_results.items():
            print(f"  - 名称: '{name}', 数量: {count}")