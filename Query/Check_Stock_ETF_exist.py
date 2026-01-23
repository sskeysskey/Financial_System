import json
import subprocess
import pyperclip
import os
import sys

USER_HOME = os.path.expanduser("~")
BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
json_file = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")

with open(json_file, 'r', encoding='utf-8') as file:
    data = json.load(file)

# 从剪贴板获取第一个新的name字段内容
new_name = pyperclip.paste()
# 去除新name的所有引号
new_name = new_name.replace('"', '').replace("'", "")

# 检查新的name是否已存在于etfs中
def check_existence_and_descriptions(data, new_name):
    for etf in data.get('etfs', []):
        if etf['symbol'] == new_name:
            return bool(etf['description1'] or etf['description2'])
    return False

exists_etf = check_existence_and_descriptions(data, new_name)
exists_stock = any(stock['symbol'] == new_name for stock in data.get('stocks', []))

if exists_etf or exists_stock:
    if sys.platform == 'darwin':
        applescript_code = 'display dialog "Symbol代码已存在！" buttons {"OK"} default button "OK"'
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)
    elif sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "Symbol代码已存在！", "提示", 0)
    sys.exit()