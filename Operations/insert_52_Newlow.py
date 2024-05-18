import json
import pyperclip
import tkinter as tk
from tkinter import messagebox

# 读取JSON文件
def load_json(filename):
    with open(filename, 'r', encoding='utf8') as file:
        return json.load(file)

# 写入JSON文件
def save_json(filename, data):
    with open(filename, 'w', encoding='utf8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

# 主处理函数
def process_files(a_file, b_file):
    # 加载文件
    data_a = load_json(a_file)
    data_b = load_json(b_file)
    
    # 从剪贴板获取内容
    clipboard_content = pyperclip.paste().strip()
    
    # 在a.json中找到匹配的最外层键
    outer_key = None
    for key, names in data_a.items():
        if clipboard_content in names:
            outer_key = key
            break
    
    # 在b.json添加剪贴板内容
    if outer_key and clipboard_content:
        if outer_key in data_b:
            if clipboard_content not in data_b[outer_key]:
                data_b[outer_key].append(clipboard_content)
                save_json(b_file, data_b)
                print(f"已添加 '{clipboard_content}' 到 '{outer_key}'")
                messagebox.showinfo("成功", "52Week_NewLow已成功写入！")
            else:
                print(f"'{clipboard_content}' 已存在于 '{outer_key}'")
                messagebox.showinfo("失败", "要写入的数据已存在！")
        else:
            print(f"'{outer_key}' 在b.json的database_mapping中不存在")
            messagebox.showinfo("失败", "目标json中缺少股票所属类别！")
    else:
        print("未在a.json中找到匹配的项或剪贴板为空。")
        messagebox.showinfo("失败", "原始json中没有你要导入的项或剪贴板为空！")

# 调用主函数
process_files('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json')