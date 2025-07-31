import sys
import json
import pyperclip
import tkinter as tk
import subprocess
from tkinter import scrolledtext

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
    info = f"{symbol}\n{descriptions['name']}\n\n{descriptions['tag']}\n\n{descriptions['description1']}\n\n{descriptions['description2']}"
    text_box.insert(tk.END, info)
    
    # 设置文本框为只读
    text_box.config(state=tk.DISABLED)
    # 修改绑定事件，确保按下ESC键关闭整个程序
    def close_all(event=None):
        root.destroy()
        sys.exit(0)
    
    top.bind('<Escape>', close_all)
    top.mainloop()  # 对top进行mainloop

def get_user_input_custom(prompt):
    root = tk.Tk()
    root.withdraw()
    
    # 创建一个新的顶层窗口
    input_dialog = tk.Toplevel(root)
    input_dialog.title(prompt)
    # 设置窗口大小和位置
    window_width = 280
    window_height = 90
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 3 - window_height / 2)  # 将窗口位置提升到屏幕1/3高度处
    input_dialog.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

    # 添加输入框，设置较大的字体和垂直填充
    entry = tk.Entry(input_dialog, width=20, font=('Helvetica', 18))
    entry.pack(pady=20, ipady=10)  # 增加内部垂直填充
    entry.focus_set()

    try:
        clipboard_content = root.clipboard_get()
    except tk.TclError:
        clipboard_content = ''
    entry.insert(0, clipboard_content)
    entry.select_range(0, tk.END)  # 全选文本

    # 设置确认按钮，点击后销毁窗口并返回输入内容
    def on_submit():
        nonlocal user_input
        user_input = entry.get().upper()  # 将输入转换为大写
        input_dialog.destroy()

    # 绑定回车键和ESC键
    entry.bind('<Return>', lambda event: on_submit())
    input_dialog.bind('<Escape>', lambda event: input_dialog.destroy())

    # 运行窗口，等待用户输入
    user_input = None
    input_dialog.wait_window(input_dialog)
    return user_input

def find_in_json(symbol, data):
    """在JSON数据中查找名称为symbol的股票或ETF"""
    for item in data:
        if item['symbol'] == symbol:
            return item
    return None

if __name__ == '__main__':
    json_data = load_json_data('/Users/yanzhang/Coding/Financial_System/Modules/description.json')

    # 解析命令行参数
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "paste":
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
                applescript_code = 'display dialog "未找到股票或ETF！" buttons {"OK"} default button "OK"'
                process = subprocess.run(['osascript', '-e', applescript_code], check=True)
        elif arg == "input":
            prompt = "请输入关键字查询数据库:"
            user_input = get_user_input_custom(prompt)
            # 先在stocks中查找
            result = find_in_json(user_input, json_data.get('stocks', []))
            # 如果在stocks中没有找到，再在etfs中查找
            if not result:
                result = find_in_json(user_input, json_data.get('etfs', []))
            # 如果找到结果，显示信息
            if result:
                show_description(user_input, result)
            else:
                applescript_code = 'display dialog "未找到股票或ETF！" buttons {"OK"} default button "OK"'
                process = subprocess.run(['osascript', '-e', applescript_code], check=True)
    else:
        print("请提供参数 input 或 paste")
        sys.exit(1)