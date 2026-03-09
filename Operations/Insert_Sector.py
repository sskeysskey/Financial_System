import json
import pyperclip
import re
import subprocess
import os
import sys

# --- 1. 路径动态化配置 ---
HOME = os.path.expanduser("~")
BASE_DIR = os.path.join(HOME, "Coding/Financial_System")
MODULES_DIR = os.path.join(BASE_DIR, "Modules")

# 定义所有相关的 JSON 文件路径
BLACKLIST_FILE = os.path.join(MODULES_DIR, "blacklist.json")
ALL_FILE = os.path.join(MODULES_DIR, "Sectors_All.json")
TODAY_FILE = os.path.join(MODULES_DIR, "Sectors_today.json")
EMPTY_FILE = os.path.join(MODULES_DIR, "Sectors_empty.json")

def show_alert(message):
    """显示 Mac 弹窗提醒"""
    # 注意：为了防止消息中包含双引号导致 AppleScript 语法错误，可以简单替换一下
    safe_message = message.replace('"', "'")
    applescript_code = f'display dialog "{safe_message}" buttons {{"OK"}} default button "OK"'
    try:
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    except subprocess.CalledProcessError:
        pass # 用户点击取消或其他情况忽略

def copy2clipboard():
    """
    通过 AppleScript 模拟 Command+C 复制操作，并将内容放入剪贴板。
    """
    script = '''
    set the clipboard to ""
    delay 0.5
    tell application "System Events"
        keystroke "c" using {command down}
        delay 0.5
    end tell
    '''
    try:
        subprocess.run(['osascript', '-e', script], check=True)
    except Exception as e:
        print(f"执行 AppleScript 复制时出错: {str(e)}")

def is_uppercase_letters(text: str) -> bool:
    """检查字符串是否完全由大写英文字母组成。"""
    return bool(re.match(r'^[A-Z]+$', text))

def remove_from_blacklist(symbol: str) -> None:
    """从 blacklist.json 的 etf 组中移除指定的 symbol"""
    try:
        if not os.path.exists(BLACKLIST_FILE):
            return

        with open(BLACKLIST_FILE, 'r+') as file:
            data = json.load(file)
            if 'etf' in data and symbol in data['etf']:
                data['etf'].remove(symbol)
                file.seek(0)
                json.dump(data, file, indent=2)
                file.truncate()
                print(f"已从blacklist的etf组中移除 {symbol}")
    except Exception as e:
        print(f"更新blacklist文件时出错: {str(e)}")

def check_blacklist(symbol: str) -> bool:
    """检查symbol是否在blacklist.json的etf组中"""
    try:
        if not os.path.exists(BLACKLIST_FILE):
            return False
        with open(BLACKLIST_FILE, 'r') as file:
            data = json.load(file)
            return symbol in data.get('etf', [])
    except Exception as e:
        print(f"读取blacklist文件时出错: {str(e)}")
        return False

def update_json_file(filename: str, group_name: str, symbol: str) -> None:
    """更新指定文件中指定组的内容，如果symbol不存在则添加。"""
    try:
        if not os.path.exists(filename):
            print(f"文件不存在: {filename}")
            return
            
        with open(filename, 'r+') as file:
            data = json.load(file)
            if group_name not in data:
                data[group_name] = []
            
            if symbol not in data[group_name]:
                data[group_name].append(symbol)
                file.seek(0)
                json.dump(data, file, indent=2)
                file.truncate()
                print(f"已将 {symbol} 添加到 {filename} 的 {group_name} 组中")
            else:
                print(f"{symbol} 已存在于 {filename} 的 {group_name} 组中，无需操作")
    except Exception as e:
        print(f"更新文件 {filename} 时出错: {str(e)}")

def process_symbol(symbol: str) -> None:
    """
    简化后的逻辑：
    1. 检查黑名单并移除。
    2. 遍历所有文件，统一添加到 'ETFs' 分组。
    """
    # 1. 处理黑名单
    if check_blacklist(symbol):
        remove_from_blacklist(symbol)
        print(f"检测到 {symbol} 在blacklist中，已移除")

    # 2. 统一添加到 ETFs 分组
    target_files = [ALL_FILE, TODAY_FILE, EMPTY_FILE]
    for filename in target_files:
        update_json_file(filename, 'ETFs', symbol)

def main():
    """
    主函数：
    1. 检查是否有命令行参数，有则使用第一个参数作为symbol。
    2. 若无，则从剪贴板获取symbol。
    3. 验证symbol格式。
    4. 执行检查和更新文件的操作。
    """
    symbol_to_process = ""
    # 引入一个变量来标记是否处于“剪贴板模式”
    is_clipboard_mode = False
    
    # 检查命令行参数
    # sys.argv 是一个列表，第一个元素(sys.argv[0])是脚本名，
    # 后面的元素是传递给脚本的参数。
    if len(sys.argv) > 1:
        # 存在命令行参数，使用第一个参数作为symbol
        symbol_to_process = sys.argv[1].strip()
        print(f"接收到命令行参数: {symbol_to_process}")
    else:
        # 没有命令行参数，执行原有的剪贴板逻辑，并将模式标记为 True
        is_clipboard_mode = True
        print("未提供命令行参数，尝试从剪贴板获取内容...")
        copy2clipboard()
        symbol_to_process = pyperclip.paste().strip()
        print(f"从剪贴板获取到内容: {symbol_to_process}")

    # 验证获取到的内容
    if not symbol_to_process:
        print("获取到的symbol为空，程序终止。")
        return
    
    if not is_uppercase_letters(symbol_to_process):
        print(f"内容 '{symbol_to_process}' 不完全由大写英文字母组成，程序终止。")
        return
    
    # 执行检查和更新操作
    print("-" * 20)
    process_symbol(symbol_to_process)
    print("-" * 20)
    print("处理完成。")

    # 在程序最后，只有当处于剪贴板模式时才弹窗
    if is_clipboard_mode:
        show_alert(f"已将 {symbol_to_process} 放入All、today、empty里了")

if __name__ == "__main__":
    main()