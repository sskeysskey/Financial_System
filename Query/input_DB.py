import re
import json
import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import scrolledtext
from datetime import datetime
from tkinter import messagebox

def load_sector_data():
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as file:
        sector_data = json.load(file)
    return sector_data

def input_mapping(root, sector_data):
    # 获取用户输入
    prompt = "请输入关键字查询数据库:"
    user_input = get_user_input_custom(root, prompt)
    
    if user_input is None:
        print("未输入任何内容，程序即将退出。")
        close_app()
    else:
        input_trimmed = user_input.strip()
        lower_input = input_trimmed.lower()
        # 先进行完整匹配查找
        exact_match_found = False
        for sector, categories in sector_data.items():
            for category, names in categories.items():
                if input_trimmed.upper() in names:
                        db_path = "/Users/yanzhang/Documents/Database/Finance.db"
                        condition = f"name = '{input_trimmed.upper()}'"
                        result = query_database(db_path, sector, condition)
                        # print(f"查询结果: {result}")  # 打印查询结果
                        create_window(None, result)
                        found = True
                        break
            if exact_match_found:
                break

        # 如果没有找到完整匹配，则进行模糊匹配
        if not exact_match_found:
            found = False
            for sector, categories in sector_data.items():
                for category, names in categories.items():
                    for name in names:
                        if re.search(lower_input, name.lower()):
                            db_path = "/Users/yanzhang/Documents/Database/Finance.db"
                            condition = f"name = '{name}'"
                            result = query_database(db_path, sector, condition)
                            # print(f"查询结果: {result}")  # 打印查询结果
                            create_window(None, result)
                            found = True
                            break
                    if found:
                        break
                if found:
                    break

        if not found:
            messagebox.showerror("错误", "未找到匹配的数据项。")
            close_app()

def get_user_input_custom(root, prompt):
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

    # 设置确认按钮，点击后销毁窗口并返回输入内容
    def on_submit():
        nonlocal user_input
        user_input = entry.get()
        input_dialog.destroy()

    # 绑定回车键和ESC键
    entry.bind('<Return>', lambda event: on_submit())
    input_dialog.bind('<Escape>', lambda event: input_dialog.destroy())

    # 运行窗口，等待用户输入
    user_input = None
    input_dialog.wait_window(input_dialog)
    return user_input

def query_database(db_file, table_name, condition):
    today_date = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    query = f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;"
    # print(f"执行的SQL查询: {query}")  # 打印SQL查询语句
    cursor.execute(query)
    rows = cursor.fetchall()
    if not rows:
        return "今天没有数据可显示。\n"
    columns = [description[0] for description in cursor.description]
    col_widths = [max(len(str(row[i])) for row in rows + [columns]) for i in range(len(columns))]
    output_text = ' | '.join([col.ljust(col_widths[idx]) for idx, col in enumerate(columns)]) + '\n'
    output_text += '-' * len(output_text) + '\n'
    for row in rows:
        output_text += ' | '.join([str(item).ljust(col_widths[idx]) for idx, item in enumerate(row)]) + '\n'
    conn.close()
    return output_text

def create_window(parent, content):
    # 创建Toplevel窗口
    top = tk.Toplevel(parent)
    top.title("数据库查询结果")
    window_width = 900
    window_height = 600
    screen_width = top.winfo_screenwidth()
    screen_height = top.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 2 - window_height / 2)
    top.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    top.bind('<Escape>', close_app)  # 绑定ESC到关闭程序的函数
    text_font = tkFont.Font(family="Courier", size=20)
    text_area = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=100, height=30, font=text_font)
    text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
    text_area.insert(tk.INSERT, content)
    text_area.configure(state='disabled')

def close_app(event=None):
    root.destroy()  # 使用destroy来确保彻底关闭所有窗口和退出

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()  # 隐藏根窗口
    root.bind('<Escape>', close_app)  # 同样绑定ESC到关闭程序的函数

    sector_data = load_sector_data()

    input_mapping(root, sector_data)

    root.mainloop()  # 主事件循环