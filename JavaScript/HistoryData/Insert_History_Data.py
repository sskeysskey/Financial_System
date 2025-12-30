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
SECTORS_JSON_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json"
# --- 新增：指向需要被修改的 "empty" JSON 文件 ---
SECTORS_EMPTY_JSON_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_empty.json"
SYMBOL_MAPPING_PATH = "/Users/yanzhang/Coding/Financial_System/Modules/Symbol_mapping.json"
DB_PATH = "/Users/yanzhang/Coding/Database/Finance.db"
ERROR_LOG_PATH = "/Users/yanzhang/Coding/News/Today_error.txt"

def add_symbol_to_etfs_group_in_json(symbol_to_add, json_path):
    """
    将指定的 symbol 添加到 Sectors_All.json 文件中的 "ETFs" 分组。
    如果 "ETFs" 组不存在，则创建它。
    如果 symbol 已存在于 "ETFs" 组中，则不重复添加。
    Symbol 在存入JSON前会被转换为大写。

    返回:
        bool: 如果成功更新或 symbol 已存在，返回 True。如果发生错误，返回 False。
    """
    try:
        # 1. 读取现有的 JSON 数据
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            # 如果文件不存在，则初始化为空字典，后续会创建 "ETFs" 键
            print(f"信息: JSON 文件 {json_path} 未找到，将创建一个新的。")
            data = {}
        except json.JSONDecodeError:
            print(f"错误: JSON 文件 {json_path} 格式无效。无法自动添加 symbol '{symbol_to_add}'。")
            # 可以选择创建一个新的空文件或者报错退出，这里我们尝试重置
            alert_msg = f"Sectors_All.json 文件格式错误，无法自动添加 {symbol_to_add} 到 ETFs 组。请检查文件。"
            # 你可以决定是否在这里调用 alert_and_exit 或仅记录错误并继续（可能导致后续问题）
            # 为了安全起见，这里可以选择不修改文件并返回False
            # subprocess.run(['osascript', '-e', f'display dialog "{alert_msg}" with title "JSON 错误" buttons {{"OK"}} default button "OK"'])
            print(alert_msg) # 打印到控制台
            return False # 表示添加失败

        # 2. 获取或创建 "ETFs" 组
        if "ETFs" not in data:
            data["ETFs"] = []
            print(f"信息: 在 {json_path} 中创建了新的 'ETFs' 组。")
        elif not isinstance(data["ETFs"], list):
            print(f"警告: {json_path} 中的 'ETFs' 键不是一个列表。将重置为一个新列表。")
            data["ETFs"] = []

        # 3. 将 symbol 添加到 "ETFs" 组 (如果尚未存在)
        if symbol_to_add not in data["ETFs"]:
            data["ETFs"].append(symbol_to_add)
            print(f"Symbol '{symbol_to_add}' 已添加到 {json_path} 的 'ETFs' 组中。")
            
            # 4. 写回更新后的 JSON 数据
            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False) # indent=4 for pretty printing
                return True # 表示成功更新
            except IOError as e:
                print(f"错误: 无法写入更新到 JSON 文件 {json_path}: {e}")
                return False # 表示写入失败
        else:
            print(f"Symbol '{symbol_to_add}' 已存在于 {json_path} 的 'ETFs' 组中，无需重复添加。")
            return True # Symbol 已存在，也视为一种成功状态

    except Exception as e:
        print(f"更新 {json_path} 时发生未知错误: {e}")
        return False

# --- 新增函数：从 Sectors_empty.json 中移除 symbol ---
def remove_symbol_from_empty_json(symbol, group_name, json_path):
    """
    在指定的 JSON 文件中，从给定的 group_name 列表中移除 symbol。

    参数:
        symbol (str): 要移除的股票代码。
        group_name (str): symbol 所属的组名 (JSON中的键)。
        json_path (str): Sectors_empty.json 文件的路径。

    返回:
        bool: 如果成功移除、symbol本就不在或成功写回文件，则返回 True。否则返回 False。
    """
    try:
        # 1. 读取 "empty" JSON 文件
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"错误: 'empty' JSON 文件 {json_path} 未找到。无法移除 symbol '{symbol}'。")
            return False
        except json.JSONDecodeError:
            print(f"错误: 'empty' JSON 文件 {json_path} 格式无效。无法移除 symbol '{symbol}'。")
            return False

        # 2. 检查组是否存在以及 symbol 是否在组内
        if group_name in data and isinstance(data.get(group_name), list):
            if symbol in data[group_name]:
                # 3. 如果存在，则移除
                data[group_name].remove(symbol)
                print(f"从 {json_path} 的 '{group_name}' 组中移除了 symbol '{symbol}'。")
                
                # 4. 写回更新后的 JSON 数据
                try:
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                    return True  # 成功移除并写回
                except IOError as e:
                    print(f"错误: 无法将更改写回 'empty' JSON 文件 {json_path}: {e}")
                    return False # 写入失败
            else:
                # Symbol 不在列表中，这不算错误，任务目标（确保它不在）已经达成
                print(f"信息: Symbol '{symbol}' 不在 {json_path} 的 '{group_name}' 组中，无需移除。")
                return True
        else:
            # 组名不存在或其值不是列表，同样不算错误
            print(f"警告: 在 {json_path} 中未找到组 '{group_name}' 或其值不是列表。无法执行移除操作。")
            return True

    except Exception as e:
        print(f"从 {json_path} 移除 symbol 时发生未知错误: {e}")
        return False

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
    delay 0.5
    tell application "Google Chrome"
	    activate
    end tell
    delay 0.5
    tell application "System Events"
        keystroke "y" using option down
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
            for lineno, row in enumerate(reader, start=2): # lineno 从2开始，因为表头是第1行
                if len(row) != len(header):
                    print(f"警告: {csv_filepath} 第 {lineno} 行列数 {len(row)} ≠ 表头列数 {len(header)}，跳过。")
                    continue
                
                # 提取通用的 date, price
                try:
                    date_val = row[header.index('date')]
                    price_val = float(row[header.index('price')])
                except ValueError as ve:
                    print(f"警告: {csv_filepath} 第 {lineno} 行 date 或 price 转换错误: {row}. 错误: {ve}. 跳过此行。")
                    continue
                except IndexError:
                    print(f"警告: {csv_filepath} 第 {lineno} 行缺少 'date' 或 'price' 列 (或表头不匹配)。跳过此行。")
                    continue

                if has_vol_in_csv:
                    volume_str = row[header.index('volume')].strip() # 获取 volume 字符串并去除首尾空格
                    volume_val = 0 # 默认为 0
                    if volume_str: # 如果字符串不为空
                        try:
                            volume_val = int(volume_str)
                        except ValueError:
                            # 如果转换失败 (例如, volume_str 是 "N/A" 或其他非数字字符)
                            print(f"警告: {csv_filepath} 第 {lineno} 行 'volume' 值 '{volume_str}' 无效，将设为 0")
                            # volume_val 保持为 None
                    else:
                        # 如果 volume_str 为空字符串
                        print(f"警告: {csv_filepath} 第 {lineno} 行 'volume' 值为空，将设为 0")
                        # volume_val 保持为 None
                    
                    rows.append((date_val, symbol, price_val, volume_val))
                else:
                    rows.append((date_val, symbol, price_val))
    except Exception as e:
        print(f"读取 CSV {csv_filepath} 时出错: {e}")
        return False

    if not rows: # 如果在读取CSV后没有收集到任何行（可能所有行都有问题）
        print(f"文件 {csv_filepath} 中没有可处理的数据。")
        return True


    # --- 打开数据库 & 确保表存在 ---
    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    safe_table = f'"{group_name}"'
    # 确保表存在（原 create_table_if_not_exists 会创建带 volume 的表）
    try:
        create_table_if_not_exists(conn, group_name)
    except sqlite3.Error as e:
        print(f"确保表 {safe_table} 存在时发生数据库错误: {e}")
        conn.close()
        return False


    # --- 读取表结构，判断表里是否有 volume 列 ---
    cursor.execute(f'PRAGMA table_info({safe_table});')
    cols = [col_info[1] for col_info in cursor.fetchall()]  # col_info[1] 是列名
    has_vol_in_db = 'volume' in cols

    # #############################################################################
    # ### --- 代码修改开始 --- ###
    # #############################################################################
    
    # 新的逻辑：以数据库表结构为准，决定如何导入数据
    
    final_rows_for_db = []
    upsert_sql = ""

    if has_vol_in_db:
        # 情况1：数据库表有 'volume' 列
        if not has_vol_in_csv:
            # 如果CSV没有 'volume' 列，这是一个错误，因为数据库需要这个数据
            msg = f"表 {group_name} 有 volume 列，但 CSV {os.path.basename(csv_filepath)} 中缺少 volume 列头。"
            conn.close()
            alert_and_exit(msg) # 报错并退出

        # 如果CSV也有 'volume' 列，则准备4列插入
        upsert_sql = f"""
        INSERT INTO {safe_table} (date, name, price, volume)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date, name) DO UPDATE SET
            price = excluded.price,
            volume = excluded.volume;
        """
        final_rows_for_db = rows # rows 已经是 (date, symbol, price, volume) 的格式

    else:
        # 情况2：数据库表没有 'volume' 列
        # 无论CSV文件是否有 'volume' 列，我们都只插入3列数据
        upsert_sql = f"""
        INSERT INTO {safe_table} (date, name, price)
        VALUES (?, ?, ?)
        ON CONFLICT(date, name) DO UPDATE SET
            price = excluded.price;
        """
        # 从 'rows' 中只取前3个元素 (date, symbol, price)，忽略可能存在的第4个元素 (volume)
        final_rows_for_db = [row[:3] for row in rows]

    # #############################################################################
    # ### --- 代码修改结束 --- ###
    # #############################################################################

    # --- 执行批量写入 ---
    try:
        cursor.executemany(upsert_sql, final_rows_for_db)
        conn.commit()
        print(f"成功处理 {len(final_rows_for_db)} 行 数据 —— {os.path.basename(csv_filepath)} → 表 {group_name}")
        return True
    except sqlite3.Error as e:
        conn.rollback()
        print(f"数据库操作失败 ({os.path.basename(csv_filepath)} -> {group_name}): {e}")
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
    if symbol_to_group_map is None: # load_symbol_to_group_map 内部已处理错误并返回 {} 或 None
        # 如果 load_symbol_to_group_map 返回 None (严重错误)，则终止
        # 如果返回 {} (例如文件为空或格式错误但未抛出异常)，程序会继续，但映射为空
        print("无法加载 symbol-group 映射，程序终止。") # 保持原有逻辑，如果load函数返回None则终止
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
    skipped_count = 0 # 注意：这个变量的含义可能需要调整，因为现在文件不会因为找不到group而被跳过

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
        
        # --- c. 查 group ---
        # 假设JSON中的symbol是大写的，或者根据实际情况调整
        group_name = symbol_to_group_map.get(symbol) 

        # --- 如果 group_name 未找到，则设置为 "ETFs" 并更新 JSON 及内存映射 ---
        if group_name is None:
            group_name = "ETFs" # 先将 group_name 设为 "ETFs"
            # 将 symbol 添加到 Sectors_All.json 的 ETFs 组
            if add_symbol_to_etfs_group_in_json(symbol, SECTORS_JSON_PATH):
                # 如果成功添加到 JSON 文件，也更新内存中的 symbol_to_group_map
                symbol_to_group_map[symbol] = "ETFs"
                print(f"内存中的 symbol_to_group_map 已更新：'{symbol}' -> '{group_name}'")
            else:
                # 如果添加到 JSON 失败，打印警告
                print(f"警告: Symbol '{symbol}' 未能成功添加到 {SECTORS_JSON_PATH}。仍将按 ETFs 分组处理。")

        # 现在 group_name 一定有值 (要么是找到的，要么是 "ETFs")
        print(f"Symbol: {symbol}, 对应 Group (表名): {group_name}")

        # c. & d. & e. & f. & g. 处理CSV并写入数据库
        # 原来的 if group_name: 条件可以移除，因为 group_name 总是有值
        success = process_csv_file(csv_filepath, symbol, group_name, DB_PATH)
        
        if success:
            # 调用函数从 Sectors_empty.json 移除 symbol
            remove_symbol_from_empty_json(symbol, group_name, SECTORS_EMPTY_JSON_PATH)

            # #############################################################################
            # ### --- 新增代码开始：根据您的需求添加 --- ###
            # #############################################################################
            # 检查 symbol 是否属于 "ETFs" 组，如果是，则尝试删除对应的 .txt 文件
            if group_name == "ETFs":
                # 构建要删除的 .txt 文件的完整路径
                txt_filename_to_delete = f"{symbol}.txt"
                txt_filepath_to_delete = os.path.join(DOWNLOADS_DIR, txt_filename_to_delete)
                
                print(f"  -> Symbol '{symbol}' 属于 ETFs 组，尝试删除关联文件: {txt_filename_to_delete}")
                
                try:
                    # 尝试删除文件
                    os.remove(txt_filepath_to_delete)
                    print(f"    - 成功删除关联的 .txt 文件。")
                except FileNotFoundError:
                    # 如果文件不存在，则打印信息并继续，不报错
                    print(f"    - 关联的 .txt 文件不存在，无需删除。")
                except OSError as e:
                    # 捕获其他可能的删除错误，例如权限问题
                    print(f"    - 错误: 删除关联的 .txt 文件失败: {e}")
            # #############################################################################
            # ### --- 新增代码结束 --- ###
            # #############################################################################

            try:
                # h. 如果成功，删除 CSV 文件
                os.remove(csv_filepath)
                print(f"成功处理并删除了 CSV 文件: {filename}")
                processed_count += 1
            except OSError as e:
                print(f"错误: 删除 CSV 文件 {csv_filepath} 失败: {e}")
                # 如果删除失败，也算作未完全成功，可以归入 skipped_count 或新增一个计数
                skipped_count += 1 # 视情况调整，这里暂时将删除失败也计入skipped
        else:
            print(f"处理文件 {csv_filepath} 失败，文件未删除。")
            skipped_count += 1
            
    print("\n--- CSV文件处理完成 ---")
    print(f"总计: {len(csv_files)} 个文件。")
    print(f"成功处理并删除: {processed_count} 个文件。")
    print(f"处理失败、删除失败或JSON更新可能存在问题: {skipped_count} 个文件。")

if __name__ == "__main__":
    main()