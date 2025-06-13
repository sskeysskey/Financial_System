import csv
import json
import sqlite3
from datetime import date, timedelta
import os
import glob
import time
import subprocess

# --- 配置 ---
json_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
blacklist_json_path = '/Users/yanzhang/Documents/Financial_System/Modules/Blacklist.json'
db_file_path = '/Users/yanzhang/Documents/Database/Finance.db'
output_dir = '/Users/yanzhang/Documents/News'
output_txt_file = os.path.join(output_dir, 'ETFs_new.txt')

def count_files(prefix):
    """
    计算Downloads目录中指定前缀开头的文件数量
    """
    download_dir = "/Users/yanzhang/Downloads/"
    files = glob.glob(os.path.join(download_dir, f"{prefix}_*.csv"))
    return len(files)

# --- 1. 计算昨天的日期 ---
yesterday = date.today() - timedelta(days=1)
yesterday_str = yesterday.strftime('%Y-%m-%d')

script = '''
    delay 1
    tell application "Google Chrome"
	    activate
    end tell
    delay 0.5
    tell application "System Events"
        keystroke "c" using option down
    end tell
    '''
# 运行AppleScript
subprocess.run(['osascript', '-e', script])

# ---- 原有等待 topetf_*.csv 的逻辑，直到文件出现 ----
print("正在等待 topetf_*.csv 文件下载...", end="")
while count_files("topetf") < 1:
    time.sleep(2)
    print(".", end="", flush=True)
print("\n文件已找到。")

# # 查找Downloads目录下最新的topetf_开头的csv文件
downloads_path = '/Users/yanzhang/Downloads/'
topetf_files = glob.glob(os.path.join(downloads_path, 'topetf_*.csv'))

# # 按文件修改时间排序，获取最新的文件
topetf_file = max(topetf_files, key=os.path.getmtime)
print(f"使用 topetf 文件: {topetf_file}")

# --- 2. 读取 JSON 文件中的 ETF 列表 ---
try:
    with open(json_file_path, 'r', encoding='utf-8') as f:
        sectors_data = json.load(f)
    # 使用集合以便快速查找，如果 "ETFs" 键不存在或不是列表，则使用空列表
    known_etfs = set(sectors_data.get('ETFs', []))
    if not known_etfs:
        print(f"警告: JSON文件 '{json_file_path}' 中 'ETFs' 列表为空或不存在。")
except FileNotFoundError:
    print(f"错误: JSON 文件 '{json_file_path}' 未找到。脚本将退出。")
    exit()
except json.JSONDecodeError:
    print(f"错误: JSON 文件 '{json_file_path}' 格式无效。脚本将退出。")
    exit()
except Exception as e:
    print(f"读取JSON文件时发生未知错误: {e}。脚本将退出。")
    exit()

# --- 新增：读取 Blacklist JSON 文件中的 ETF 黑名单 ---
etf_blacklist = set() # 初始化为空集合，以防文件读取失败
try:
    with open(blacklist_json_path, 'r', encoding='utf-8') as f_blacklist:
        blacklist_data = json.load(f_blacklist)
    # 安全地获取 'etf' 列表，如果键不存在或不是列表，则使用空列表
    etf_blacklist = set(blacklist_data.get('etf', []))
    if not etf_blacklist:
        print(f"信息: Blacklist JSON文件 '{blacklist_json_path}' 中 'etf' 列表为空或不存在。")
except FileNotFoundError:
    print(f"警告: Blacklist JSON 文件 '{blacklist_json_path}' 未找到。将继续执行，不使用ETF黑名单过滤。")
except json.JSONDecodeError:
    print(f"警告: Blacklist JSON 文件 '{blacklist_json_path}' 格式无效。将继续执行，不使用ETF黑名单过滤。")
except Exception as e:
    print(f"读取Blacklist JSON文件 '{blacklist_json_path}' 时发生未知错误: {e}。将继续执行，不使用ETF黑名单过滤。")

# --- 3. 确保输出目录存在 ---
os.makedirs(output_dir, exist_ok=True)

# --- 4. 初始化用于数据库插入和文件写入的列表 ---
etfs_to_db = []
new_etfs_to_file = []

# --- 5. 读取 CSV 文件并处理数据 ---
try:
    with open(topetf_file, mode='r', encoding='utf-8-sig') as csvfile: # utf-8-sig 处理可能的BOM
        reader = csv.DictReader(csvfile)
        if not reader.fieldnames or not all(col in reader.fieldnames for col in ['Symbol', 'Name', 'Price', 'Volume']):
            print(f"错误: CSV文件 '{topetf_file}' 缺少必要的列 (Symbol, Name, Price, Volume)。")
            exit()

        for row in reader:
            symbol = row.get('Symbol')
            name = row.get('Name')
            price_str = row.get('Price')
            volume_str = row.get('Volume')

            # 基本的数据校验
            if not all([symbol, name, price_str, volume_str]):
                print(f"警告: CSV文件中发现不完整的行: {row}。跳过此行。")
                continue

            try:
                price_original = float(price_str) # 先转换为浮点数
                volume = int(volume_str)
            except ValueError:
                print(f"警告: 无法转换行 {row} 中的Price或Volume为数值。跳过此行。")
                continue

            if symbol in known_etfs:
                # 将 price 四舍五入到两位小数
                price_rounded = round(price_original, 2)
                # 数据库表结构: id, date, name, price, volume
                # CSV Symbol -> DB name
                etfs_to_db.append((yesterday_str, symbol, price_rounded, volume))
            else:
                # 条件1: volume > 200,000
                if volume > 200000:
                    # 条件2: symbol 不在 ETF 黑名单中
                    if symbol not in etf_blacklist:
                        new_etfs_to_file.append(f"{symbol}: {name}, {volume}")

except FileNotFoundError:
    print(f"错误: CSV 文件 '{topetf_file}' 未找到。脚本将退出。")
    exit()
except Exception as e:
    print(f"读取CSV文件时发生未知错误: {e}。脚本将退出。")
    exit()

# --- 6. 将匹配的 ETF 数据写入数据库 ---
if etfs_to_db:
    conn = None # 初始化conn
    try:
        conn = sqlite3.connect(db_file_path)
        cursor = conn.cursor()
        # 注意：假设 ETFs 表已经存在，并且有 date, name, price, volume 列
        # id 列通常是 PRIMARY KEY AUTOINCREMENT，不需要显式插入
        sql_insert = "INSERT INTO ETFs (date, name, price, volume) VALUES (?, ?, ?, ?)"
        cursor.executemany(sql_insert, etfs_to_db)
        conn.commit()
        print(f"成功将 {len(etfs_to_db)} 条匹配的ETF数据写入数据库 '{db_file_path}'。")
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        if conn:
            conn.rollback() # 如果发生错误，回滚事务
    finally:
        if conn:
            conn.close()
else:
    print("没有在JSON中匹配到任何ETF，无需写入数据库。")

# --- 7. 将未匹配的 ETF 数据写入文本文件 ---
if new_etfs_to_file:
    try:
        with open(output_txt_file, 'a', encoding='utf-8') as txtfile: # 'a' 表示追加模式
            for line in new_etfs_to_file:
                txtfile.write(line + '\n')
        print(f"成功将 {len(new_etfs_to_file)} 条新的ETF数据写入文件 '{output_txt_file}'。")
    except IOError as e:
        print(f"写入文件 '{output_txt_file}' 时发生错误: {e}")
else:
    print("没有新的ETF需要写入文件。")


# --- 8. 调用 Check_yesterday.py 脚本 ---
print("\n--------------------------------------------------")
print("--- 开始执行 Check_yesterday.py 脚本 ---")
check_yesterday_script_path = '/Users/yanzhang/Documents/Financial_System/Query/Check_yesterday.py'

try:
    # 使用 subprocess.run 来执行另一个 Python 脚本。
    # - ['python', check_yesterday_script_path]: 这是要执行的命令，第一个元素是解释器，第二个是脚本路径。
    # - check=True: 如果被调用的脚本返回非零退出码（通常表示错误），则会抛出一个 CalledProcessError 异常。
    # - capture_output=True: 捕获子进程的标准输出和标准错误。
    # - text=True: 将标准输出和标准错误解码为文本（使用指定的 encoding）。
    # - encoding='utf-8': 指定用于解码的编码，确保中文等字符正确显示。
    result = subprocess.run(
        ['python', check_yesterday_script_path],
        check=True,
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    print("Check_yesterday.py 脚本成功执行。")
    # 打印被调用脚本的输出，方便调试和查看结果
    print("--- Check_yesterday.py 输出开始 ---")
    print(result.stdout)
    print("--- Check_yesterday.py 输出结束 ---")

except FileNotFoundError:
    print(f"错误: 'python' 命令未找到。请确保 Python 已安装并正确配置在系统的 PATH 环境变量中。")
except subprocess.CalledProcessError as e:
    # 如果 check=True 并且脚本执行失败，则会进入这里
    print(f"错误: Check_yesterday.py 脚本执行失败。")
    print(f"返回码: {e.returncode}")
    print("\n--- 标准输出 (stdout) ---")
    print(e.stdout)
    print("\n--- 标准错误 (stderr) ---")
    print(e.stderr)
except Exception as e:
    print(f"调用 Check_yesterday.py 脚本时发生未知错误: {e}")

print("\n所有任务已完成。")