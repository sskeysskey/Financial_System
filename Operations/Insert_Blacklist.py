import pyperclip
import json
import subprocess
import sys
import os
import re
import tkinter as tk
from tkinter import messagebox

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
JSON_PATH = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "Blacklist.json")

def Copy_Command_C():
    try:
        if sys.platform == 'darwin':
            script = '''
            delay 0.5
            tell application "System Events"
                keystroke "c" using command down
            end tell
            '''
            subprocess.run(['osascript', '-e', script])
        elif sys.platform == 'win32':
            import pyautogui
            pyautogui.hotkey('ctrl', 'c')
    except Exception:
        pass

def show_alert(message):
    if sys.platform == 'darwin':
        applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
        try:
            subprocess.run(['osascript', '-e', applescript_code], check=True)
        except subprocess.CalledProcessError:
            pass
    else:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("提醒", message)
        root.destroy()

def update_blacklist(symbol, list_key):
    """
    更新 JSON 文件中的指定列表
    :param symbol: 股票代码
    :param list_key: 要更新的键名，例如 'newlow' 或 'etf'
    """
    try:
        # 读取现有的JSON文件
        if not os.path.exists(JSON_PATH):
            show_alert(f"文件不存在: {JSON_PATH}")
            return

        with open(JSON_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
        
        # 确保目标列表存在
        if list_key not in data:
            data[list_key] = []

        # 检查 symbol 是否已经存在
        if symbol not in data[list_key]:
            # 添加新的 symbol
            data[list_key].append(symbol)
            
            # 将更新后的数据写回文件
            with open(JSON_PATH, 'w', encoding='utf-8') as file:
                json.dump(data, file, indent=4)
            
            # 成功提示 (根据原有两个脚本的提示风格略有不同，这里统一格式但保留关键信息)
            target_name = "黑名单(newlow)" if list_key == 'newlow' else "ETF黑名单中"
            show_alert(f"成功将 {symbol} 添加到 {target_name}")
        else:
            show_alert(f"{symbol} 已经在 {list_key} 列表中")
            
    except Exception as e:
        show_alert(f"更新 {list_key} 时发生错误: {str(e)}")

def get_symbol_from_clipboard():
    """执行复制并获取剪贴板内容"""
    Copy_Command_C()
    content = pyperclip.paste()
    if content:
        return content.strip()
    return None

def is_valid_symbol(symbol):
    """
    校验代码格式
    规则：仅包含大写英文字母(A-Z)和横杠(-)
    """
    if not symbol:
        return False
    # <--- 2. 新增校验函数
    # ^ 表示开头，$ 表示结尾，[A-Z\-] 表示允许字符集合
    pattern = r'^[A-Z\-]+$' 
    return bool(re.match(pattern, symbol))

def main():
    # 逻辑判断
    # 场景 1: python script.py etf  -> 执行 ETF 逻辑 (从剪贴板获取，存入 'etf')
    # 场景 2: python script.py TSLA -> 执行 默认 逻辑 (使用参数 TSLA，存入 'newlow')
    # 场景 3: python script.py      -> 执行 默认 逻辑 (从剪贴板获取，存入 'newlow')

    mode = 'newlow' # 默认模式
    symbol = None

    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        
        if arg == 'etf':
            # 命中 ETF 模式
            mode = 'etf'
            # 原 blacklist_etf.py 逻辑是从剪贴板获取
            symbol = get_symbol_from_clipboard()
        else:
            # 命中 默认模式，但带有参数（作为股票代码）
            mode = 'newlow'
            symbol = arg
    else:
        # 没有参数，执行默认模式，从剪贴板获取
        mode = 'newlow'
        symbol = get_symbol_from_clipboard()

    # 验证是否存在内容
    if not symbol:
        show_alert("剪贴板为空或未获取到内容")
        return

    # <--- 3. 执行格式校验
    if not is_valid_symbol(symbol):
        show_alert(f"无效的代码格式: {symbol}\n请确保只包含大写字母和横杠(-)")
        return

    # 执行更新
    update_blacklist(symbol, mode)

if __name__ == "__main__":
    main()
