import os
import re
import glob
import json
import csv
import sys
import time
import sqlite3
import subprocess

# --- 配置路径 ---
DOWNLOADS_DIR = "/Users/yanzhang/Downloads"
SECTORS_JSON_PATH = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
SYMBOL_MAPPING_PATH = "/Users/yanzhang/Documents/Financial_System/Modules/Symbol_mapping.json"
DB_PATH = "/Users/yanzhang/Documents/Database/Finance.db"
ERROR_LOG_PATH = "/Users/yanzhang/Documents/News/Today_error.txt"

def alert_and_exit(msg):
    """
    弹出 macOS 警示框，写日志，然后退出脚本。
    """
    # 1. 弹框
    osa = f'display alert "CSV/DB 列不匹配" message "{msg}" as critical buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', osa])
    # 2. 写日志
    with open(ERROR_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    # 3. 退出程序
    sys.exit(1)

def extension_launch():
    script = '''
    tell application "System Events"
        keystroke "r" using option down
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

def load_json_dict(json_path):
    """
    通用：加载一个 JSON 文件，返回 dict。
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载 JSON {json_path} 失败: {e}")
        return {}

def load_symbol_to_group_map(json_path):
    """
    加载 Sectors_All.json 文件并创建一个从 symbol 到 group name 的映射。
    例如: {"AAPL": "Technology", "SHEL": "Energy"}
    """
    symbol_to_group = {}
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            sectors_data = json.load(f)
        for group_name, symbols_list in sectors_data.items():
            for symbol in symbols_list:
                symbol_to_group[symbol] = group_name
        print(f"成功加载并处理了 {len(symbol_to_group)} 个 symbol 到 group 的映射。")
    except FileNotFoundError:
        print(f"错误: JSON 文件未找到路径 {json_path}")
        return None
    except json.JSONDecodeError:
        print(f"错误: JSON 文件 {json_path} 格式无效。")
        return None
    except Exception as e:
        print(f"加载 JSON 文件时发生未知错误: {e}")
        return None
    return symbol_to_group

def create_table_if_not_exists(db_connection, table_name):
    """
    如果数据库中不存在指定的表，则创建它。
    表名需要用双引号括起来，以处理可能包含特殊字符或关键字的组名。
    """
    cursor = db_connection.cursor()
    # 注意：表名直接来自JSON文件的键，假设它们是安全的。
    # 如果表名可能来自不受信任的来源，需要进行更严格的清理。
    # 使用双引号确保表名被正确处理，即使它们是SQL关键字或包含空格（尽管本例中没有）。
    safe_table_name = f'"{table_name}"' # 将表名用双引号括起来
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {safe_table_name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT, -- 添加一个自增ID，虽然原始需求未明确，但通常是好习惯
        date TEXT,
        name TEXT,
        price REAL,
        volume INTEGER,
        UNIQUE(date, name) -- 添加 UNIQUE 约束
    );
    """
    try:
        cursor.execute(create_table_sql)
        db_connection.commit()
        # print(f"表 {safe_table_name} 已确保存在。") # 可以取消注释用于调试
    except sqlite3.Error as e:
        print(f"创建表 {safe_table_name} 时发生数据库错误: {e}")
        raise # 重新抛出异常，让调用者处理

# def process_csv_file(csv_filepath, symbol, group_name, db_path):
#     """
#     处理单个CSV文件：读取数据并将其插入到指定的数据库表中。
#     """
#     data_to_insert = []
#     try:
#         with open(csv_filepath, 'r', newline='', encoding='utf-8') as f_csv:
#             reader = csv.reader(f_csv, delimiter=',') # 确保分隔符是逗号
#             header = next(reader)
#             expected_header = ['date', 'price', 'volume']
#             if header != expected_header:
#                 print(f"警告: 文件 {csv_filepath} 的表头 {header} 与预期的 {expected_header} 不符。仍将尝试处理。")

#             for i, row in enumerate(reader):
#                 if len(row) == 3:
#                     date_val, price_str, volume_str = row
#                     try:
#                         price_val = float(price_str)
#                         volume_val = int(volume_str)
#                         # 'name' 列将存储从文件名中提取的 symbol
#                         data_to_insert.append((date_val, symbol, price_val, volume_val))
#                     except ValueError as ve:
#                         print(f"警告: 文件 {csv_filepath} 第 {i+2} 行数据转换错误: {row}. 错误: {ve}. 跳过此行。")
#                 else:
#                     print(f"警告: 文件 {csv_filepath} 第 {i+2} 行数据列数不为3: {row}. 跳过此行。")
#     except FileNotFoundError:
#         print(f"错误: CSV 文件 {csv_filepath} 在读取时未找到。")
#         return False
#     except Exception as e:
#         print(f"读取 CSV 文件 {csv_filepath} 时发生错误: {e}")
#         return False

#     if not data_to_insert:
#         print(f"文件 {csv_filepath} 中没有可插入的数据。")
#         return True # 认为处理完成，因为没有数据可插

#     conn = None
#     try:
#         conn = sqlite3.connect(db_path)
#         cursor = conn.cursor()
        
#         # 确保表存在 (如果需要，会创建带 UNIQUE 约束的表)
#         create_table_if_not_exists(conn, group_name)

#         safe_table_name = f'"{group_name}"'
        
#         # --- 修改点在这里: 使用 UPSERT ---
#         # 如果 date 和 name 的组合已存在，则更新 price 和 volume
#         upsert_sql = f"""
#         INSERT INTO {safe_table_name} (date, name, price, volume)
#         VALUES (?, ?, ?, ?)
#         ON CONFLICT(date, name) DO UPDATE SET
#             price = excluded.price,
#             volume = excluded.volume;
#         """
#         # --- 修改结束 ---
#         # executemany 仍然适用，它会为每一行数据执行这个 UPSERT 语句
#         cursor.executemany(upsert_sql, data_to_insert)

#         conn.commit()
#         print(f"成功处理 {len(data_to_insert)} 条数据从 {os.path.basename(csv_filepath)} ({symbol}) 到表 {safe_table_name} (插入或更新)。")
#         return True
#     except sqlite3.Error as e:
#         # 这里的错误现在不太可能是 UNIQUE constraint failed 了，除非有其他约束
#         print(f"处理文件 {csv_filepath} ({symbol}) 并将其操作到表 {group_name} 时发生数据库错误: {e}")
#         if conn:
#             conn.rollback()
#         return False
#     finally:
#         if conn:
#             conn.close()

def process_csv_file(csv_filepath, symbol, group_name, db_path):
    """
    处理单个 CSV 文件：根据表结构动态决定插入哪些列，
    并在不匹配时弹框 + 写日志 + 退出脚本。
    """
    # --- 读取 CSV 文件头 和 数据 ---
    try:
        with open(csv_filepath, 'r', newline='', encoding='utf-8') as f_csv:
            reader = csv.reader(f_csv, delimiter=',')
            header = next(reader)
            # 判断 CSV 是否有 volume 列
            has_vol_in_csv = 'volume' in header
            # 收集数据
            rows = []
            for lineno, row in enumerate(reader, start=2):
                if len(row) != len(header):
                    print(f"警告: {csv_filepath} 第 {lineno} 行列数 {len(row)} ≠ 表头列数 {len(header)}，跳过。")
                    continue
                # 提取通用的 date, price
                date_val = row[header.index('date')]
                price_val = float(row[header.index('price')])
                if has_vol_in_csv:
                    volume_val = int(row[header.index('volume')])
                    rows.append((date_val, symbol, price_val, volume_val))
                else:
                    rows.append((date_val, symbol, price_val))
    except Exception as e:
        print(f"读取 CSV {csv_filepath} 时出错: {e}")
        return False

    # --- 打开数据库 & 确保表存在 ---
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    safe_table = f'"{group_name}"'
    # 确保表存在（原 create_table_if_not_exists 会创建带 volume 的表）
    create_table_if_not_exists(conn, group_name)

    # --- 读取表结构，判断表里是否有 volume 列 ---
    cursor.execute(f'PRAGMA table_info({safe_table});')
    cols = [row[1] for row in cursor.fetchall()]  # row[1] 是列名
    has_vol_in_db = 'volume' in cols

    # --- 对比 CSV vs DB 列 状态，不匹配时报错退出 ---
    if has_vol_in_db != has_vol_in_csv:
        if has_vol_in_db and not has_vol_in_csv:
            msg = f"表 {group_name} 有 volume 列，但 CSV {os.path.basename(csv_filepath)} 中缺少 volume。"
        else:
            msg = f"表 {group_name} 无 volume 列，但 CSV {os.path.basename(csv_filepath)} 中包含 volume。"
        alert_and_exit(msg)

    # --- 根据是否含 volume 动态构建 UPSERT 语句 & 数据 ---
    if has_vol_in_db and has_vol_in_csv:
        # 四列 upsert
        upsert_sql = f"""
        INSERT INTO {safe_table} (date, name, price, volume)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date, name) DO UPDATE SET
            price = excluded.price,
            volume = excluded.volume;
        """
    else:
        # 只有 date,name,price
        upsert_sql = f"""
        INSERT INTO {safe_table} (date, name, price)
        VALUES (?, ?, ?)
        ON CONFLICT(date, name) DO UPDATE SET
            price = excluded.price;
        """

    # --- 执行批量写入 ---
    try:
        cursor.executemany(upsert_sql, rows)
        conn.commit()
        print(f"成功处理 {len(rows)} 行 数据 —— {os.path.basename(csv_filepath)} → 表 {group_name}")
        return True
    except sqlite3.Error as e:
        conn.rollback()
        print(f"数据库操作失败: {e}")
        return False
    finally:
        conn.close()

def main():
    extension_launch()

    # 用于存储找到的CSV文件列表
    csv_files_found = []

    print(f"正在监控目录: {DOWNLOADS_DIR} 以查找.csv文件...")
    while True:
        # 查找指定目录下所有的.csv文件
        # os.path.join 用于创建与操作系统无关的正确路径格式
        # '*.csv' 是一个模式，用于匹配所有以 .csv 结尾的文件
        csv_files_found = glob.glob(os.path.join(DOWNLOADS_DIR, '*.csv'))

        if csv_files_found:
            # 如果找到了.csv文件 (即列表不为空)
            print(f"\n成功找到 {len(csv_files_found)} 个.csv文件:")
            # 跳出循环，因为已经找到文件
            break
        else:
            # 如果没有找到.csv文件，打印一个点表示正在等待，然后等待2秒
            print(".", end="", flush=True) # flush=True 确保点被立即打印出来
            time.sleep(1) # 暂停执行2秒

    print("--- 开始处理CSV文件 ---")
    # 1. 加载 symbol 到 group 的映射
    symbol_to_group_map = load_symbol_to_group_map(SECTORS_JSON_PATH)
    if symbol_to_group_map is None:
        print("无法加载 symbol-group 映射，程序终止。")
        return

    # 2. 加载符号别名映射 (如果文件不存在或格式错，就返回空 dict)
    symbol_alias_map = load_json_dict(SYMBOL_MAPPING_PATH)
    print(f"已加载 {len(symbol_alias_map)} 条符号别名映射。")

    # 3. 找到 Downloads 目录下的所有 CSV 文件
    csv_files = glob.glob(os.path.join(DOWNLOADS_DIR, '*.csv'))
    if not csv_files:
        print(f"在目录 {DOWNLOADS_DIR} 中未找到 .csv 文件。")
        return

    print(f"找到 {len(csv_files)} 个CSV文件待处理: {csv_files}")

    processed_count = 0
    skipped_count = 0

    # 4. 逐个处理 CSV 文件
    for csv_filepath in csv_files:
        print(f"\n正在处理文件: {csv_filepath}")
        
        # a. 从文件名提取 symbol (例如 AHR.csv -> AHR)
        filename = os.path.basename(csv_filepath)
        base_name = os.path.splitext(filename)[0]

        # --- a. 用正则做 _3D -> =, _5E -> ^ ---
        symbol = re.sub(
            r'_(3D|5E)',
            lambda m: '=' if m.group(1) == '3D' else '^',
            base_name
        )
        print(f"  [1] 原始替换后 symbol: {symbol}")

        # --- b. 再看别名映射表里有没有对应条目 ---
        #      如果有，就用 alias_map[symbol]，否则还是 symbol
        symbol = symbol_alias_map.get(symbol, symbol)
        print(f"  [2] 映射后最终 symbol: {symbol}")
        # --- c. 查 group, 其余逻辑不变 ---
        group_name = symbol_to_group_map.get(symbol.upper()) # 假设JSON中的symbol是大写的，或者根据实际情况调整

        if group_name:
            print(f"Symbol: {symbol}, 对应 Group (表名): {group_name}")
            # c. & d. & e. & f. & g. 处理CSV并写入数据库
            success = process_csv_file(csv_filepath, symbol, group_name, DB_PATH)
            
            if success:
                # h. 如果成功，删除 CSV 文件
                try:
                    os.remove(csv_filepath)
                    print(f"成功处理并删除了文件: {csv_filepath}")
                    processed_count += 1
                except OSError as e:
                    print(f"错误: 删除文件 {csv_filepath} 失败: {e}")
            else:
                print(f"处理文件 {csv_filepath} 失败，文件未删除。")
                skipped_count += 1
        else:
            print(f"警告: 未在 Sectors_All.json 中找到 Symbol '{symbol}' (来自文件 {filename}) 对应的 Group。跳过此文件。")
            skipped_count += 1
            
    print("\n--- CSV文件处理完成 ---")
    print(f"总计: {len(csv_files)} 个文件。")
    print(f"成功处理并删除: {processed_count} 个文件。")
    print(f"跳过或处理失败: {skipped_count} 个文件。")

if __name__ == "__main__":
    main()