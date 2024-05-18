import os
import sys
import json
import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, scrolledtext
sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from API_panel_Name2Chart import plot_financial_data
from datetime import datetime, timedelta

def create_custom_style():
    style = ttk.Style()
    # 尝试使用不同的主题，如果默认主题不支持背景颜色的更改
    # style.theme_use('clam')
    style.theme_use('alt')

    # 为不同的按钮定义颜色
    style.configure("Purple.TButton", background="purple", foreground="white", font=('Helvetica', 16))
    style.configure("Yellow.TButton", background="yellow", foreground="black", font=('Helvetica', 16))
    style.configure("Orange.TButton", background="orange", foreground="black", font=('Helvetica', 16))
    style.configure("Blue.TButton", background="blue", foreground="white", font=('Helvetica', 16))
    style.configure("Red.TButton", background="Red", foreground="white", font=('Helvetica', 16))
    style.configure("Default.TButton", background="gray", foreground="black", font=('Helvetica', 16))

    # 确保按钮的背景颜色被填充
    style.map("TButton",
              background=[('active', '!disabled', 'pressed', 'focus', 'hover', 'alternate', 'selected', 'background')]
              )

# def load_text(filename, text_scroll):
#     directory = '/Users/yanzhang/Documents/News/'
#     text_scroll.delete('1.0', tk.END)
#     with open(os.path.join(directory, filename), 'r', encoding='utf-8') as file_content:
#         text_scroll.insert(tk.END, file_content.read())

# def create_file_list(file_list_frame, files, text_scroll):
#     for file in files:
#         file_button = ttk.Button(file_list_frame, text=file, command=lambda f=file: load_text(f, text_scroll))
#         file_button.pack(fill=tk.X)

def parse_changes(filename):
    changes = {}
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            for line in file:
                if ':' in line:
                    key, value = line.split(':')
                    changes[key.strip()] = value.strip()
    except FileNotFoundError:
        print("文件未找到")
    return changes

def create_selection_window():
    selection_window = tk.Toplevel(root)
    selection_window.title("选择查询关键字")
    selection_window.geometry("1480x900")
    selection_window.bind('<Escape>', lambda e: close_app(root))

    canvas = tk.Canvas(selection_window)
    scrollbar = tk.Scrollbar(selection_window, orient="horizontal", command=canvas.xview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")
        )
    )

    create_custom_style() 
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(xscrollcommand=scrollbar.set)

    purple_keywords = ["Bitcoin", "CNYUSD", "US10Y", "USDJPY", "CrudeOil"]
    yellow_keywords = ["CNYJPY", "NASDAQ", "Gold", "Cocoa"]
    orange_keywords = ["HANGSENG", "Naturalgas", "Ether", "Shanghai", "USDCNY"]
    blue_keywords = ["Copper", "S&P500"]
    red_keywords = ["VIX", "DXY"]

    # 创建一个新的Frame来纵向包含CurrencyDB1和CryptoDB1
    new_vertical_frame1 = tk.Frame(scrollable_frame)
    new_vertical_frame1.pack(side="left", padx=15, pady=10, fill="both", expand=True)

    new_vertical_frame2 = tk.Frame(scrollable_frame)
    new_vertical_frame2.pack(side="left", padx=15, pady=10, fill="both", expand=True)

    new_vertical_frame3 = tk.Frame(scrollable_frame)
    new_vertical_frame3.pack(side="left", padx=15, pady=10, fill="both", expand=True)

    new_vertical_frame4 = tk.Frame(scrollable_frame)
    new_vertical_frame4.pack(side="left", padx=15, pady=10, fill="both", expand=True)

    for db_key, keywords in config.items():
        if db_key in ['Bonds', 'Crypto', 'Indices']:
            # 将这两个数据库的框架放入新的纵向框架中
            frame = tk.LabelFrame(new_vertical_frame4, text=db_key, padx=10, pady=10)
            frame.pack(side="top", padx=15, pady=10, fill="both", expand=True)
        elif db_key in ['Currencies']:
            frame = tk.LabelFrame(new_vertical_frame3, text=db_key, padx=10, pady=10)
            frame.pack(side="top", padx=15, pady=10, fill="both", expand=True)
        elif db_key in ['Basic_Materials','Communication_Services','Consumer_Cyclical',
                    'Consumer_Defensive','Energy','Utilities']:
            frame = tk.LabelFrame(new_vertical_frame1, text=db_key, padx=10, pady=10)
            frame.pack(side="top", padx=15, pady=10, fill="both", expand=True)
        elif db_key in ['Financial_Services','Healthcare','Industrials','Real_Estate',
                    'Technology']:
            frame = tk.LabelFrame(new_vertical_frame2, text=db_key, padx=10, pady=10)
            frame.pack(side="top", padx=15, pady=10, fill="both", expand=True)
        else:
            frame = tk.LabelFrame(scrollable_frame, text=db_key, padx=10, pady=10)
            frame.pack(side="left", padx=15, pady=10, fill="both", expand=True)

        for keyword in sorted(keywords):
            button_frame = tk.Frame(frame)  # 创建一个内部Frame来包裹两个按钮
            button_frame.pack(side="top", fill="x", padx=5, pady=2)
            
            # 根据关键字设置背景颜色
            if keyword in purple_keywords:
                button_style = "Purple.TButton"
            elif keyword in yellow_keywords:
                button_style = "Yellow.TButton"
            elif keyword in orange_keywords:
                button_style = "Orange.TButton"
            elif keyword in blue_keywords:
                button_style = "Blue.TButton"
            elif keyword in red_keywords:
                button_style = "Red.TButton"
            else:
                button_style = "Default.TButton"  # 默认颜色
            
            change_text = change_dict.get(keyword, "")
            button_text = f"{keyword} {change_text}"
            
            button_data = ttk.Button(button_frame, text=button_text, style=button_style, command=lambda k=keyword: on_keyword_selected(k))
            button_data.pack(side="left", fill="x", expand=True)
            
            button_chart = tk.Button(button_frame, text="📊", command=lambda k=keyword: on_keyword_selected_chart(k, selection_window))
            button_chart.pack(side="left", fill="x", expand=True)

    # # 创建用于显示文本文件内容的 Frame
    # text_file_frame = tk.Frame(selection_window)
    # text_file_frame.pack(side="right", fill="y", expand=False, padx=0, pady=0)
    # text_font = tkFont.Font(family="Courier", size=28)

    # # 文本文件滚动区域
    # text_scroll = scrolledtext.ScrolledText(text_file_frame, width=30, height=20, font=text_font)
    # text_scroll.pack(pady=0, padx=0, fill=tk.BOTH, expand=False)

    # directory = '/Users/yanzhang/Documents/News/'
    # files = [f for f in os.listdir(directory) if f.endswith('.txt')]

    # # 创建文件列表的 Frame
    # file_list_frame = tk.Frame(text_file_frame)
    # file_list_frame.pack(side="top", fill="both", expand=True)

    # # 调用新的函数来创建文件列表和按钮
    # create_file_list(file_list_frame, files, text_scroll)

    # # 自动打开第一个文件
    # if files:
    #     load_text(files[0], text_scroll)  # 确保 files 不为空

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="bottom", fill="x")

def on_keyword_selected(value):
     for sector, names in sector_data.items():
        if value in names:
            db_path = "/Users/yanzhang/Documents/Database/Finance.db"
            condition = f"name = '{value}'"
            result = query_database(db_path, sector, condition)
            create_window(result)

def query_database(db_path, table_name, condition):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        query = f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;"
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
        return output_text

def load_sector_data():
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'r') as file:
        sector_data = json.load(file)
    return sector_data

def on_keyword_selected_chart(value, parent_window):
    for sector, names in sector_data.items():
        if value in names:
            db_path = "/Users/yanzhang/Documents/Database/Finance.db"
            plot_financial_data(db_path, sector, value)

def create_window(content):
    top = tk.Toplevel(root)
    top.title("数据库查询结果")
    window_width = 900
    window_height = 600
    screen_width = top.winfo_screenwidth()
    screen_height = top.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 2 - window_height / 2)
    top.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    top.bind('<Escape>', lambda e: close_app(top))
    text_font = tkFont.Font(family="Courier", size=20)
    text_area = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=100, height=30, font=text_font)
    text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
    text_area.insert(tk.INSERT, content)
    text_area.configure(state='disabled')

def close_app(window):
    window.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()

    # 读取合并后的数据库配置
    with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json', 'r') as f:
        config = json.load(f)

    change_dict = parse_changes('/Users/yanzhang/Documents/News/backup/Compare_Panel.txt')
    
    create_selection_window()
    sector_data = load_sector_data()
    root.mainloop()