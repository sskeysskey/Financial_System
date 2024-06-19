import pyperclip
import json
import os
from datetime import datetime
from collections import OrderedDict
import subprocess

def add_to_gainer():
    filename = '/Users/yanzhang/Documents/Financial_System/Modules/Gainer_Loser.json'
    
    # 获取当前日期
    date = datetime.now().strftime("%Y-%m-%d")
    
    # 如果文件不存在，则创建一个空的JSON文件
    if not os.path.exists(filename):
        with open(filename, 'w', encoding='utf-8') as file:
            json.dump({}, file)
    
    # 读取现有的JSON文件
    with open(filename, 'r', encoding='utf-8') as file:
        data = json.load(file, object_pairs_hook=OrderedDict)
    
    # 初始化日期结构
    if date not in data:
        # 创建一个新的有序字典，并将新日期的数据插入到最上方
        new_data = OrderedDict()
        new_data[date] = {"gainer": [], "loser": []}
        new_data.update(data)
        data = new_data
    
    # 获取剪贴板内容
    symbol = pyperclip.paste()
    
    # 检查symbol是否在loser列表中
    if symbol not in data[date]["loser"]:
        # 添加到gainer列表
        if symbol not in data[date]["gainer"]:
            data[date]["gainer"].append(symbol)
    
    # 写回JSON文件
    with open(filename, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def Copy_Command_C():
    script = '''
    tell application "System Events"
        keystroke "c" using command down
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

if __name__ == "__main__":
    Copy_Command_C()
    add_to_gainer()