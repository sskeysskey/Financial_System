import json
import pyperclip
import tkinter as tk
import subprocess
from tkinter import messagebox

def Copy_Command_C():
    script = '''
    tell application "System Events"
        keystroke "c" using command down
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

# 读取JSON文件
def load_json(filename):
    with open(filename, 'r', encoding='utf8') as file:
        return json.load(file)

# 写入JSON文件
def save_json(filename, data):
    with open(filename, 'w', encoding='utf8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

# 主处理函数
def process_files(a_file, b_file, c_file):
    # 加载文件
    data_a = load_json(a_file)
    data_b = load_json(b_file)
    data_c = load_json(c_file)
    
    Copy_Command_C()
    # 从剪贴板获取内容
    clipboard_content = pyperclip.paste().strip()
    
    # 在a.json中找到匹配的最外层键
    outer_key = None
    clipboard_content_lower = clipboard_content.lower()
    clipboard_content_upper = clipboard_content.upper()
    for key, names in data_a.items():
        # 将names中的所有元素转换为小写
        names_lower = [name.lower() for name in names]
        if clipboard_content_lower in names_lower:
            outer_key = key  # 赋值为JSON里实际的键
            break
    
    # 在b.json添加剪贴板内容
    if outer_key and clipboard_content_upper:
        if outer_key in data_b:
            if clipboard_content_upper not in data_b[outer_key]:
                data_b[outer_key].append(clipboard_content_upper)
                save_json(b_file, data_b)
                print(f"已添加 '{clipboard_content_upper}' 到 '{outer_key}'")
                messagebox.showinfo("成功", "数据已添加到sectors_panel.json里。")
            else:
                print(f"'{clipboard_content}' 已存在于 '{outer_key}'")
                messagebox.showinfo("失败", "要写入的数据已存在！")
        else:
            print(f"'{outer_key}' 在b.json的database_mapping中不存在")
            messagebox.showinfo("失败", "目标json中缺少相应类别！")
    else:
        print("未在a.json中找到匹配的项或剪贴板为空。")
        messagebox.showinfo("失败", "原始json中没有你要导入的项或剪贴板为空！")
    
    # 添加到c.json的white_keywords下
    if clipboard_content_upper:
        if clipboard_content_upper not in data_c['white_keywords']:
            data_c['blue_keywords'].append(clipboard_content_upper)
            save_json(c_file, data_c)
            print(f"已添加 '{clipboard_content_upper}' 到 colors.json 的 'white_keywords'")
            messagebox.showinfo("成功", "数据已添加到c.json的blue_keywords。")
        else:
            print(f"'{clipboard_content_upper}' 已存在于 c.json 的 'white_keywords'")
            messagebox.showinfo("失败", "要写入的数据已存在于c.json的blue_keywords！")

# 调用主函数
process_files('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json',
'/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json',
'/Users/yanzhang/Documents/Financial_System/Modules/Colors.json')