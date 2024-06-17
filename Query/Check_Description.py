import json
import subprocess
import pyperclip
import tkinter as tk
from tkinter import scrolledtext
from tkinter import messagebox

def Copy_Command_C():
    script = '''
    tell application "System Events"
        keystroke "c" using command down
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

def load_json_data(path):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)

def show_description(symbol, descriptions):
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    
    # 创建一个新的顶级窗口
    top = tk.Toplevel(root)
    top.title("Descriptions")
    
    # 设置窗口尺寸
    top.geometry("600x750")
    
    # 设置字体大小
    font_size = ('Arial', 22)
    
    # 创建一个滚动文本框
    text_box = scrolledtext.ScrolledText(top, wrap=tk.WORD, font=font_size)
    text_box.pack(expand=True, fill='both')
    
    # 插入股票信息
    info = f"{symbol}\n\n{descriptions['tag']}\n\n{descriptions['name']}\n\n{descriptions['description1']}\n\n{descriptions['description2']}"
    text_box.insert(tk.END, info)
    
    # 设置文本框为只读
    text_box.config(state=tk.DISABLED)
    
    top.bind('<Escape>', lambda event: root.destroy())
    top.mainloop()  # 对top进行mainloop

def find_in_json(symbol, data):
    """在JSON数据中查找名称为symbol的股票或ETF"""
    for item in data:
        if item['symbol'] == symbol:
            return item
    return None

json_data = load_json_data('/Users/yanzhang/Documents/Financial_System/Modules/Description.json')

Copy_Command_C()
symbol = pyperclip.paste().replace('"', '').replace("'", "")

# 先在stocks中查找
result = find_in_json(symbol, json_data.get('stocks', []))

# 如果在stocks中没有找到，再在etfs中查找
if not result:
    result = find_in_json(symbol, json_data.get('etfs', []))

# 如果找到结果，显示信息
if result:
    show_description(symbol, result)
else:
    messagebox.showinfo("失败", f"未找到名称为 {symbol} 的股票或ETF！")