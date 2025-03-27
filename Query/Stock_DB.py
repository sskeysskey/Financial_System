import re
import sys
import json
import sqlite3
import tkinter as tk
from tkinter import scrolledtext
from tkinter.font import Font
from datetime import datetime
import pyperclip
import subprocess

def load_sector_data(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def query_database(db_file, table_name, condition):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    query = f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return "没有数据可显示。\n"
    
    columns = [desc[0] for desc in cursor.description]
    col_widths = [max(len(str(item)) for item in column) for column in zip(*rows, columns)]
    
    output_text = ' | '.join(col.ljust(col_widths[idx]) for idx, col in enumerate(columns)) + '\n'
    output_text += '-' * len(output_text) + '\n'
    
    for row in rows:
        output_text += ' | '.join(str(item).ljust(col_widths[idx]) for idx, item in enumerate(row)) + '\n'
    
    return output_text

def create_window(parent, content):
    top = tk.Toplevel(parent)
    top.title("数据库查询结果")
    top.geometry("900x600")
    top.bind('<Escape>', close_app)
    
    text_area = scrolledtext.ScrolledText(top, wrap=tk.WORD, font=Font(family="Courier", size=20))
    text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
    text_area.insert(tk.INSERT, content)
    text_area.configure(state='disabled')

def close_app(event=None):
    root.destroy()

def input_processing(root, sector_data, user_input):
    if not user_input:
        print("未输入任何内容，程序即将退出。")
        close_app()
        return
    
    input_variants = {variant: user_input.strip() for variant in ['exact', 'capitalized', 'upper']}
    
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
    found = False
    
    for variant, input_variant in input_variants.items():
        for sector, names in sector_data.items():
            if input_variant in names:
                condition = f"name = '{input_variant}'"
                result = query_database(db_path, sector, condition)
                create_window(None, result)
                print("哈哈" if variant == 'exact' else "")
                found = True
                break
        if found:
            return
    
    lower_input = input_variants['exact'].lower()
    for sector, names in sector_data.items():
        for name in names:
            if re.search(lower_input, name.lower()):
                condition = f"name = '{name}'"
                result = query_database(db_path, sector, condition)
                create_window(None, result)
                return
    
    applescript_code = 'display dialog "未找到匹配的数据项。" buttons {"OK"} default button "OK"'
    process = subprocess.run(['osascript', '-e', applescript_code], check=True)
    close_app()

def get_user_input_custom(root, prompt):
    input_dialog = tk.Toplevel(root)
    input_dialog.title(prompt)
    input_dialog.geometry('280x90')
    
    # 获取屏幕宽度和高度
    screen_width = input_dialog.winfo_screenwidth()
    screen_height = input_dialog.winfo_screenheight()
    
    # 获取窗口宽度和高度
    window_width = 280
    window_height = 90
    
    # 计算居中位置
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2 - 200
    
    # 设置窗口位置
    input_dialog.geometry(f'{window_width}x{window_height}+{x}+{y}')
    
    entry = tk.Entry(input_dialog, width=20, font=('Helvetica', 18))
    entry.pack(pady=20, ipady=10)
    entry.focus_set()
    
    try:
        clipboard_content = root.clipboard_get()
    except tk.TclError:
        clipboard_content = ''
    
    entry.insert(0, clipboard_content)
    entry.select_range(0, tk.END)
    
    def on_submit():
        nonlocal user_input
        user_input = entry.get()
        input_dialog.destroy()
    
    entry.bind('<Return>', lambda event: on_submit())
    input_dialog.bind('<Escape>', lambda event: input_dialog.destroy())
    
    user_input = None
    input_dialog.wait_window(input_dialog)
    return user_input

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()
    root.bind('<Escape>', close_app)
    
    sector_data = load_sector_data('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json')
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "paste":
            clipboard_content = pyperclip.paste()
            input_processing(root, sector_data, clipboard_content)
        elif arg == "input":
            prompt = "请输入关键字查询数据库:"
            user_input = get_user_input_custom(root, prompt)
            input_processing(root, sector_data, user_input)
    else:
        print("请提供参数 input 或 paste")
        sys.exit(1)
    
    root.mainloop()