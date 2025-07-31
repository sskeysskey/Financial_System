import json
import subprocess
import os # 新增导入 os 模块

def show_alert(message):
    # AppleScript 代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    # 使用 subprocess 调用 osascript
    try:
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    except FileNotFoundError:
        print("osascript command not found. Cannot show alert. Message:", message)
    except subprocess.CalledProcessError as e:
        print(f"Error showing alert: {e}. Message:", message)


def load_keys_from_file(path):
    """
    读取 txt 文件，提取每行冒号前面的 symbol，返回一个 set
    """
    keys = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or ':' not in line:
                continue
            symbol = line.split(':', 1)[0].strip()
            keys.add(symbol)
    return keys

def find_file_path_with_fallback(filename, primary_dir, fallback_dir):
    """
    尝试在主目录中查找文件，如果找不到，则在备用目录中查找。
    如果都找不到，则抛出 FileNotFoundError。
    """
    primary_path = os.path.join(primary_dir, filename)
    if os.path.exists(primary_path):
        print(f"Found '{filename}' in primary directory: {primary_path}")
        return primary_path
    else:
        print(f"'{filename}' not found in primary directory: {primary_dir}. Trying fallback...")
        fallback_path = os.path.join(fallback_dir, filename)
        if os.path.exists(fallback_path):
            print(f"Found '{filename}' in fallback directory: {fallback_path}")
            return fallback_path
        else:
            # 如果两个目录都找不到文件，则抛出异常，让调用者处理
            raise FileNotFoundError(
                f"File '{filename}' not found in primary directory '{primary_dir}' or fallback directory '{fallback_dir}'."
            )

# --- 0. 定义文件路径 ---
# JSON 文件路径
sector_all_json_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
sector_empty_json_path = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_empty.json' # 同时也是输出路径

# TXT 文件的主目录和备用目录
primary_txt_dir = '/Users/yanzhang/Downloads/'
fallback_txt_dir = '/Users/yanzhang/Coding/News/backup/'

# TXT 文件名
marketcap_filename = 'marketcap_pe.txt'
shares_filename = 'Shares.txt'
# symbol_names_filename = 'symbol_names.txt'


# --- 1. 读取 sector_all.json 和 sector_empty.json ---
try:
    with open(sector_all_json_path, encoding='utf-8') as f:
        sector_all = json.load(f)

    with open(sector_empty_json_path, encoding='utf-8') as f:
        sector_empty = json.load(f)
except FileNotFoundError as e:
    error_message = f"Error: Critical JSON file not found: {e}. Please check paths:\n{sector_all_json_path}\n{sector_empty_json_path}"
    print(error_message)
    show_alert(error_message)
    exit() # 如果核心JSON文件缺失，则无法继续
except json.JSONDecodeError as e:
    error_message = f"Error: Could not decode JSON file: {e}. Please check file content."
    print(error_message)
    show_alert(error_message)
    exit()

# --- 2. 定义要检查的分类 ---
categories = [
    'Basic_Materials', 'Consumer_Cyclical', 'Real_Estate', 'Energy',
    'Technology', 'Utilities', 'Industrials', 'Consumer_Defensive',
    'Communication_Services', 'Financial_Services', 'Healthcare'
]

# --- 3. 收集 sector_all 中所有目标分类的符号 ---
all_symbols = set()
for cat in categories:
    all_symbols.update(sector_all.get(cat, []))

# --- 4. 读取三个 txt 文件，分别得到已有的 symbol 集合 ---
#    使用新的 find_file_path_with_fallback 函数确定文件路径
try:
    marketcap_file_path = find_file_path_with_fallback(marketcap_filename, primary_txt_dir, fallback_txt_dir)
    marketcap_keys = load_keys_from_file(marketcap_file_path)

    shares_file_path = find_file_path_with_fallback(shares_filename, primary_txt_dir, fallback_txt_dir)
    shares_keys = load_keys_from_file(shares_file_path)

    # symbol_names_file_path = find_file_path_with_fallback(symbol_names_filename, primary_txt_dir, fallback_txt_dir)
    # symbol_names_keys = load_keys_from_file(symbol_names_file_path)

except FileNotFoundError as e:
    # 如果任何一个 TXT 文件在两个目录都找不到，则弹窗并退出
    error_message = f"Error: Required data file missing from both primary and fallback locations. {e}"
    print(error_message)
    show_alert(error_message)
    exit() # 退出脚本，因为缺少必要数据
except Exception as e: # 捕获其他可能的读取错误
    error_message = f"An unexpected error occurred while loading data files: {e}"
    print(error_message)
    show_alert(error_message)
    exit()


# --- 5. 计算每个文件中缺失的 symbol ---
missing_marketcap    = all_symbols - marketcap_keys
missing_shares       = all_symbols - shares_keys
# missing_symbol_names = all_symbols - symbol_names_keys

# --- 6. 取三者缺失的并集，作为“所有缺失”的 symbol ---
missing_all = missing_marketcap | missing_shares

# --- 7. 将缺失符号按照原分类，填入 sector_empty ---
for cat in categories:
    original_syms = set(sector_all.get(cat, []))
    miss_in_cat = original_syms & missing_all
    # 只做赋值，空列表也会写入——保证 JSON 结构统一
    sector_empty[cat] = sorted(miss_in_cat)

# --- 8. 将更新后的 sector_empty.json 写回磁盘 ---
#    输出路径已在顶部定义为 sector_empty_json_path
try:
    with open(sector_empty_json_path, 'w', encoding='utf-8') as f:
        json.dump(sector_empty, f, ensure_ascii=False, indent=2)
except IOError as e:
    error_message = f"Error writing to output file '{sector_empty_json_path}': {e}"
    print(error_message)
    show_alert(error_message)
    exit()

# --- 9. 最后一条弹窗提示 ---
if missing_all:
    show_alert(f"检测到 {len(missing_all)} 个缺失符号，已写入：{sector_empty_json_path}")
else:
    show_alert("未检测到缺失符号，无需更新。")

print("脚本执行完毕。")