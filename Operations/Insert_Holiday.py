import json
import subprocess
import sys
import shlex

# 1. 定义文件路径
empty_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
holiday_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_US_holiday.json'

# 2. 读取原始 JSON (Sectors_empty.json)
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

# 6. 写回文件
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
# 8. 新增功能：在 Terminal 中调用另一个 Python 脚本
#    此功能模仿了您提供的 AppleScript 的行为。
# ----------------------------------------------------------------------
print("\n--- 准备调用 YF_PriceVolume.py 脚本 ---")

# 首先，检查当前操作系统是否为 macOS (在内部表示为 'darwin')
# 因为此功能依赖于 macOS 的 Terminal 应用和 osascript
if sys.platform != "darwin":
    print("🟡 警告: 自动调用脚本功能仅在 macOS 上受支持。已跳过此步骤。")
else:
    try:
        # a. 定义要执行的命令的各个部分，与 AppleScript 中一致
        python_path = "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
        script_path = "/Users/yanzhang/Documents/Financial_System/Selenium/YF_PriceVolume.py"
        mode_arg = "--mode empty"

        # b. 使用 shlex.quote 来安全地处理路径，防止路径中包含空格或特殊字符导致命令执行失败
        safe_script_path = shlex.quote(script_path)

        # c. 组合成最终要在 Terminal 中执行的完整命令字符串
        command_to_run_in_terminal = f"{python_path} {safe_script_path} {mode_arg}"

        # d. 构建一个多行的 AppleScript 脚本字符串
        #    - 'tell application "Terminal"' 指示 AppleScript 控制 Terminal 应用
        #    - 'activate' 会将 Terminal 应用带到最前台
        #    - 'do script "..."' 会在新窗口或新标签页中运行指定的 shell 命令
        applescript_command = f'''
        tell application "Terminal"
            activate
            do script "{command_to_run_in_terminal}"
        end tell
        '''

        # e. 使用 subprocess.run() 来执行 osascript 命令，从而运行上面的 AppleScript
        #    - ['osascript', '-e', applescript_command] 是要执行的命令列表
        #    - check=True 表示如果命令执行失败（返回非零退出码），则会抛出异常
        print(f"正在尝试在新的 Terminal 窗口中执行命令: {command_to_run_in_terminal}")
        subprocess.run(['osascript', '-e', applescript_command], check=True, capture_output=True)
        print("✅ 成功启动 YF_PriceVolume.py 脚本。请检查新打开的 Terminal 窗口。")

    except FileNotFoundError:
        # 这个错误会在 'osascript' 命令本身不存在时发生 (几乎不可能在macOS上)
        print("🔴 错误: 'osascript' 命令未找到。此功能需要 macOS 环境。")
    except subprocess.CalledProcessError as e:
        # 如果 osascript 执行失败（例如，Terminal 应用权限问题），会抛出此错误
        print(f"🔴 错误: 通过 AppleScript 调用脚本失败。")
        print(f"   错误详情: {e.stderr.decode('utf-8').strip()}")