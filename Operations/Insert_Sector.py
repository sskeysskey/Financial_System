import json
import pyperclip
import re
import subprocess
from typing import Optional
import sys  # 导入 sys 模块以访问命令行参数

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
        # 即使复制失败，也继续尝试读取剪贴板，可能已有内容
        pass

def is_uppercase_letters(text: str) -> bool:
    """
    检查字符串是否完全由大写英文字母组成。
    """
    return bool(re.match(r'^[A-Z]+$', text))

def remove_from_blacklist(symbol: str) -> None:
    """
    从blacklist.json的etf组中移除指定的symbol
    """
    blacklist_file = '/Users/yanzhang/Coding/Financial_System/Modules/blacklist.json'
    try:
        with open(blacklist_file, 'r+') as file:
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
    """
    检查symbol是否在blacklist.json的etf组中
    返回True表示在黑名单中，False表示不在
    """
    try:
        with open('/Users/yanzhang/Coding/Financial_System/Modules/blacklist.json', 'r') as file:
            data = json.load(file)
            return symbol in data.get('etf', [])
    except Exception as e:
        print(f"读取blacklist文件时出错: {str(e)}")
        return False

def find_symbol_group(filename: str, symbol: str) -> Optional[str]:
    """
    在指定文件中查找symbol所属的组名
    返回组名或None（如果未找到）
    """
    try:
        with open(filename, 'r') as file:
            data = json.load(file)
            for group_name, symbols in data.items():
                if symbol in symbols:
                    return group_name
    except Exception as e:
        print(f"读取文件 {filename} 时出错: {str(e)}")
    return None

def update_json_file(filename: str, group_name: str, symbol: str) -> None:
    """
    更新指定文件中指定组的内容，如果symbol不存在则添加。
    """
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


def check_and_update_files(symbol: str) -> None:
    """
    检查并更新所有相关的JSON文件。
    """
    # 如果在黑名单中，先移除
    if check_blacklist(symbol):
        remove_from_blacklist(symbol)
        print(f"检测到 {symbol} 在blacklist的etf组中，已移除")

    ALL_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
    TODAY_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_today.json'
    EMPTY_FILE = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_empty.json'
    
    # 检查symbol在all和today文件中的位置
    group_in_all = find_symbol_group(ALL_FILE, symbol)
    group_in_today = find_symbol_group(TODAY_FILE, symbol)
    
    # 如果symbol在all和today的同一个组中存在
    if group_in_all and group_in_today and group_in_all == group_in_today:
        try:
            update_json_file(EMPTY_FILE, group_in_all, symbol)
            print(f"已将 {symbol} 添加到 {EMPTY_FILE} 的 {group_in_all} 组中")
        except Exception as e:
            print(f"更新 {EMPTY_FILE} 时出错: {str(e)}")
        return
    
    # 如果不满足上述条件（例如，不在任何组中，或在不同的组中），
    # 则默认将其作为ETF处理，添加到所有三个文件的'ETFs'组中。
    try:
        for filename in [ALL_FILE, TODAY_FILE, EMPTY_FILE]:
            update_json_file(filename, 'ETFs', symbol)
            print(f"已将 {symbol} 添加到 {filename} 的 ETFs 组中")
    except Exception as e:
        print(f"更新文件时出错: {str(e)}")

def main():
    """
    主函数：
    1. 检查是否有命令行参数，有则使用第一个参数作为symbol。
    2. 若无，则从剪贴板获取symbol。
    3. 验证symbol格式。
    4. 执行检查和更新文件的操作。
    """
    symbol_to_process = ""
    
    # 检查命令行参数
    # sys.argv 是一个列表，第一个元素(sys.argv[0])是脚本名，
    # 后面的元素是传递给脚本的参数。
    if len(sys.argv) > 1:
        # 存在命令行参数，使用第一个参数作为symbol
        symbol_to_process = sys.argv[1].strip()
        print(f"接收到命令行参数: {symbol_to_process}")
    else:
        # 没有命令行参数，执行原有的剪贴板逻辑
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
    check_and_update_files(symbol_to_process)
    print("-" * 20)
    print("处理完成。")


if __name__ == "__main__":
    main()