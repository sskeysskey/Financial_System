import json
import pyperclip
import re
import subprocess
from typing import Optional

def copy2clipboard():
    script = '''
    set the clipboard to ""
    delay 0.3
    tell application "System Events"
        keystroke "c" using {command down}
        delay 0.5
    end tell
    '''
    subprocess.run(['osascript', '-e', script], check=True)

def is_uppercase_letters(text: str) -> bool:
    return bool(re.match(r'^[A-Z]+$', text))

def remove_from_blacklist(symbol: str) -> None:
    """
    从blacklist.json的etf组中移除指定的symbol
    """
    blacklist_file = '/Users/yanzhang/Documents/Financial_System/Modules/blacklist.json'
    try:
        with open(blacklist_file, 'r+') as file:
            data = json.load(file)
            if symbol in data.get('etf', []):
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
        with open('/Users/yanzhang/Documents/Financial_System/Modules/blacklist.json', 'r') as file:
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
    更新指定文件中指定组的内容
    """
    with open(filename, 'r+') as file:
        data = json.load(file)
        if symbol not in data[group_name]:
            data[group_name].append(symbol)
        file.seek(0)
        json.dump(data, file, indent=2)
        file.truncate()

def check_and_update_files(symbol: str) -> None:
    """
    检查并更新所有文件
    """
    # 如果在黑名单中，先移除
    if check_blacklist(symbol):
        remove_from_blacklist(symbol)
        print(f"检测到 {symbol} 在blacklist的etf组中，已移除")

    ALL_FILE = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'
    TODAY_FILE = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_today.json'
    EMPTY_FILE = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
    
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
    
    # 如果symbol不在任何组中，检查是否应该添加到ETFs
    try:
        for filename in [ALL_FILE, TODAY_FILE, EMPTY_FILE]:
            update_json_file(filename, 'ETFs', symbol)
            print(f"已将 {symbol} 添加到 {filename} 的 ETFs 组中")
    except Exception as e:
        print(f"更新文件时出错: {str(e)}")

def main():
    # 获取剪贴板内容
    copy2clipboard()
    clipboard_content = pyperclip.paste().strip()
    
    # 验证剪贴板内容
    if not clipboard_content:
        print("剪贴板为空")
        return
    
    if not is_uppercase_letters(clipboard_content):
        print("剪贴板内容不全为大写英文字母")
        return
    
    # 执行检查和更新操作
    check_and_update_files(clipboard_content)

if __name__ == "__main__":
    main()