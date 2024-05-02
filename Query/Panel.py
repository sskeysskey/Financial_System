import os
import sys
import sqlite3
import subprocess
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, scrolledtext
sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from name2chart import plot_financial_data
from datetime import datetime, timedelta
from today_yesterday import compare_today_yesterday

# 全局变量中初始化数据库连接
database_connections = {}

# 全局变量定义
directory = '/Users/yanzhang/Documents/News/'

def init_db_connections():
    for key, info in database_info.items():
        database_connections[key] = sqlite3.connect(info['path'])

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

def load_text(filename, text_scroll):
    global directory  # 声明使用全局变量
    text_scroll.delete('1.0', tk.END)
    with open(os.path.join(directory, filename), 'r', encoding='utf-8') as file_content:
        text_scroll.insert(tk.END, file_content.read())

def create_file_list(file_list_frame, files, text_scroll):
    for file in files:
        file_button = ttk.Button(file_list_frame, text=file, command=lambda f=file: load_text(f, text_scroll))
        file_button.pack(fill=tk.X)

def create_selection_window():
    subprocess.run(['/Library/Frameworks/Python.framework/Versions/3.12/bin/python3', '/Users/yanzhang/Documents/Financial_System/Query/data_compare.py'])
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

    purple_keywords = ["NASDAQ", "Bitcoin", "USDCNY", "United States", "EURUSD", "Corn", "Coffee"]
    yellow_keywords = ["CNYJPY", "DXY", "USDJPY", "NASDAQ Composite", "Gold", "Cocoa"]
    orange_keywords = ["HANG SENG INDEX", "Brent", "Natural gas", "Ether", "SSE Composite Index", "Shenzhen Index"]
    blue_keywords = ["CRB Index", "Copper", "S&P 500"]
    red_keywords = ["CBOE Volatility Index"]

    # 创建一个新的Frame来纵向包含CurrencyDB1和CryptoDB1
    new_vertical_frame1 = tk.Frame(scrollable_frame)
    new_vertical_frame1.pack(side="left", padx=15, pady=10, fill="both", expand=True)

    new_vertical_frame2 = tk.Frame(scrollable_frame)
    new_vertical_frame2.pack(side="left", padx=15, pady=10, fill="both", expand=True)

    for db_key, keywords in database_mapping.items():
        if db_key in ['Currency', 'Bonds']:
            # 将这两个数据库的框架放入新的纵向框架中
            frame = tk.LabelFrame(new_vertical_frame1, text=db_key, padx=10, pady=10)
            frame.pack(side="top", padx=15, pady=10, fill="both", expand=True)
        elif db_key in ['Crypto', 'Stocks Index', 'Commodity Index']:
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

            db_key = reverse_mapping[keyword]
            db_info = database_info[db_key]
            # 使用 with 语句来管理数据库连接
            with sqlite3.connect(db_info['path']) as conn:
                cursor = conn.cursor()
                today = datetime.now()
                change_text = compare_today_yesterday(cursor, db_info['table'], keyword, today)
            button_text = f"{keyword} {change_text}"
            
            button_data = ttk.Button(button_frame, text=button_text, style=button_style, command=lambda k=keyword: on_keyword_selected(k))
            button_data.pack(side="left", fill="x", expand=True)
            
            button_chart = tk.Button(button_frame, text="📊", command=lambda k=keyword: on_keyword_selected_chart(k, selection_window))
            button_chart.pack(side="left", fill="x", expand=True)

    # 创建用于显示文本文件内容的 Frame
    text_file_frame = tk.Frame(selection_window)
    text_file_frame.pack(side="right", fill="y", expand=False, padx=0, pady=20)
    text_font = tkFont.Font(family="Courier", size=20)

    # 文本文件滚动区域
    text_scroll = scrolledtext.ScrolledText(text_file_frame, width=35, height=35, font=text_font)
    text_scroll.pack(pady=0, padx=0, fill=tk.BOTH, expand=False)

    # 使用全局定义的 directory 变量
    global directory
    files = [f for f in os.listdir(directory) if f.endswith('.txt')]

    # 创建文件列表的 Frame
    file_list_frame = tk.Frame(text_file_frame)
    file_list_frame.pack(side="top", fill="both", expand=True)

    # 调用新的函数来创建文件列表和按钮
    create_file_list(file_list_frame, files, text_scroll)

    # 自动打开第一个文件
    if files:
        load_text(files[0], text_scroll)  # 确保 files 不为空

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="bottom", fill="x")

def on_keyword_selected(value):
    if value:
        db_key = reverse_mapping[value]
        db_info = database_info[db_key]
        condition = f"name = '{value}'"
        result = query_database(db_info['path'], db_info['table'], condition)
        create_window(result)

def query_database(db_file, table_name, condition):
    with sqlite3.connect(db_file) as conn:
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

def on_keyword_selected_chart(value, parent_window):
    db_key = reverse_mapping[value]
    db_info = database_info[db_key]
    condition = f"name = '{value}'"
    plot_financial_data(value)

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

def close_all_connections():
    for conn in database_connections.values():
        conn.close()

if __name__ == '__main__':
    try:
        root = tk.Tk()
        root.withdraw()
        
        database_info = {
                'Commodity': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities'},
                'Stocks Index': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Stocks'},
                'Crypto': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Crypto'},
                'Currency': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Currencies'},
                'Bonds': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Bonds'},
                'Commodity Index': {'path': '/Users/yanzhang/Documents/Database/Finance.db', 'table': 'Commodities'}
        }

        database_mapping = {
            'Commodity': {'Uranium', 'Nickel', 'Soybeans', 'Wheat', 'Coffee', 'Cotton', 'Cocoa', 'Rice', 'Corn', 'Oat', 'Orange Juice',
                'Crude Oil', 'Brent', 'Natural gas', 'Gold', 'Copper', 'Lithium', 'Aluminum', 'Lean Hogs', 'Live Cattle', 'Sugar'},
            'Crypto': {"Bitcoin", "Ether", "Solana"},
            'Stocks Index': {'NASDAQ Composite', 'Russell 2000', 'CBOE Volatility Index', 'S&P 500', 'HANG SENG INDEX',
                'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'IBOVESPA'},
            'Commodity Index': {'CRB Index', 'LME Index', 'Nuclear Energy Index', 'Solar Energy Index', 'EU Carbon Permits',
                'Containerized Freight Index'},
            'Currency': {'DXY', 'EURUSD', 'GBPUSD', 'EURCNY', 'GBPCNY', 'USDJPY', 'USDCNY', 'CNYJPY', 'CNYPHP', 'CNYIDR',
                'USDIDR', 'USDARS', 'USDPHP', 'CNYEUR', 'CNYGBP'},
            'Bonds': {"United States", "Japan", "Russia", "India", "Turkey"},
        }

        reverse_mapping = {keyword: db for db, keywords in database_mapping.items() for keyword in keywords}
        init_db_connections()  # 初始化数据库连接
        create_selection_window()
        root.mainloop()
    finally:
        close_all_connections()