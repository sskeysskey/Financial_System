import json
import subprocess
import sys
import shlex
import os

# --- 1. 路径动态化处理 ---
HOME = os.path.expanduser("~")
# 定义基础项目路径
BASE_DIR = os.path.join(HOME, "Coding/Financial_System")

# 定义文件路径
empty_file_path = os.path.join(BASE_DIR, "Modules/Sectors_empty.json")
holiday_file_path = os.path.join(BASE_DIR, "Modules/Sectors_US_holiday.json")

# --- 2. 读取原始 JSON (Sectors_empty.json) ---
try:
    with open(empty_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    print(f"警告: 文件 {empty_file_path} 未找到。将使用空字典初始化。")
    data = {}  # 如果文件不存在，则初始化为空字典
except json.JSONDecodeError:
    print(f"警告: 解析文件 {empty_file_path} JSON失败。将使用空字典初始化。")
    data = {}  # 如果JSON解析失败，则初始化为空字典

# 3. 读取 holiday JSON (Sectors_US_holiday.json)
try:
    with open(holiday_file_path, 'r', encoding='utf-8') as f:
        data_holiday = json.load(f)
except FileNotFoundError:
    print(f"警告: 文件 {holiday_file_path} 未找到。将跳过从此文件合并数据。")
    data_holiday = {} # 如果文件不存在，则初始化为空字典
except json.JSONDecodeError:
    print(f"警告: 解析文件 {holiday_file_path} JSON失败。将跳过从此文件合并数据。")
    data_holiday = {} # 如果JSON解析失败，则初始化为空字典

# 4. 将 holiday 文件中的项目按组名添加到 data 中（参考 Crypto 的去重合并方式）
for category, items_from_holiday in data_holiday.items():
    # 确保 holiday 文件中该类别下的项目是一个列表
    if not isinstance(items_from_holiday, list):
        print(f"注意: {holiday_file_path} 中 '{category}' 类别下的项目不是一个列表，已跳过该类别。")
        continue

    # 获取 data 中已有的该类别下的项目，如果不存在或不是列表，则视为空列表
    current_items_in_data = data.get(category, [])
    if not isinstance(current_items_in_data, list):
        print(f"注意: {empty_file_path} 中 '{category}' 类别下的内容不是一个列表 (实际为: {type(current_items_in_data)})。将视为空列表进行合并。")
        current_items_in_data = []
    
    # 使用集合进行合并以自动去重
    set_current_items = set(current_items_in_data)
    set_items_from_holiday = set(items_from_holiday)
    
    # 更新 data 中该类别的内容
    data[category] = sorted(list(set_current_items.union(set_items_from_holiday))) # 使用 sorted() 排序使结果更可预测

# --- 5. 写回文件 ---
# 确保目录存在
os.makedirs(os.path.dirname(empty_file_path), exist_ok=True)
with open(empty_file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# 7. 打印更新确认信息
print(f"✅ '{empty_file_path}' 文件已成功更新。")
# 使用 .get(key, []) 来安全地获取列表，以防某个键不存在
print("✅ 已将 Crypto 更新为：", data.get('Crypto', []))
print("✅ 已将 Commodities 更新为：", data.get('Commodities', []))

# 如果您想查看所有更新后的类别，可以取消以下代码的注释
print("\n--- 所有更新后的类别详情 ---")
for category_name, category_items in data.items():
    if isinstance(category_items, list):
        print(f"  {category_name}: {category_items}")
    else:
        # 这种情况通常不应该发生，除非JSON结构本身有问题
        print(f"  {category_name}: {category_items} (注意: 此类别内容非列表格式)")
print("--------------------------")

# ----------------------------------------------------------------------
# 8. 新增功能：在 Terminal 中调用另一个 Python 脚本 (已移除参数)
# ----------------------------------------------------------------------
print("\n--- 准备调用 Tiger_Today.py 脚本 ---")

# 首先，检查当前操作系统是否为 macOS (在内部表示为 'darwin')
# 因为此功能依赖于 macOS 的 Terminal 应用和 osascript
if sys.platform != "darwin":
    print("🟡 警告: 自动调用脚本功能仅在 macOS 上受支持。已跳过此步骤。")
else:
    try:
        # --- 修改点：使用 sys.executable 获取当前 Python 路径，更具通用性 ---
        python_path = sys.executable 
        # a. 定义要执行的命令的各个部分，与 AppleScript 中一致
        # python_path = "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
        script_path = os.path.join(BASE_DIR, "Selenium/Tiger_Today.py")
        
        # --- 修改部分：不再定义 mode_arg ---
        
        # b. 使用 shlex.quote 来安全地处理路径
        safe_script_path = shlex.quote(script_path)

        # c. 组合成最终要在 Terminal 中执行的完整命令字符串 (去掉了 mode_arg)
        command_to_run_in_terminal = f"{python_path} {safe_script_path}"

        # d. 构建 AppleScript 脚本
        applescript_command = f'''
        tell application "Terminal"
            activate
            do script "{command_to_run_in_terminal}"
        end tell
        '''

        # e. 执行
        print(f"正在尝试在新的 Terminal 窗口中执行命令: {command_to_run_in_terminal}")
        subprocess.run(['osascript', '-e', applescript_command], check=True, capture_output=True)
        print("✅ 成功启动 Tiger_Today.py 脚本。请检查新打开的 Terminal 窗口。")

    except FileNotFoundError:
        # 这个错误会在 'osascript' 命令本身不存在时发生 (几乎不可能在macOS上)
        print("🔴 错误: 'osascript' 命令未找到。此功能需要 macOS 环境。")
    except subprocess.CalledProcessError as e:
        # 如果 osascript 执行失败（例如，Terminal 应用权限问题），会抛出此错误
        print(f"🔴 错误: 通过 AppleScript 调用脚本失败。")
        print(f"   错误详情: {e.stderr.decode('utf-8').strip()}")