import sys
import sqlite3
import matplotlib
import tkinter as tk
import tkinter.font as tkFont
import matplotlib.pyplot as plt
from tkinter import scrolledtext
from datetime import datetime, timedelta
from matplotlib.widgets import RadioButtons
sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from name2chart import plot_financial_data

def create_selection_window():
    selection_window = tk.Toplevel(root)
    selection_window.title("选择查询关键字")
    selection_window.geometry("1280x800")
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

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(xscrollcommand=scrollbar.set)

    # 创建一个新的Frame来纵向包含CurrencyDB1和CryptoDB1
    new_vertical_frame1 = tk.Frame(scrollable_frame)
    new_vertical_frame1.pack(side="left", padx=15, pady=10, fill="both", expand=True)

    new_vertical_frame2 = tk.Frame(scrollable_frame)
    new_vertical_frame2.pack(side="left", padx=15, pady=10, fill="both", expand=True)

    for db_key, keywords in database_mapping.items():
        if db_key in ['CurrencyDB', 'Bonds', 'CryptoDB']:
            # 将这两个数据库的框架放入新的纵向框架中
            frame = tk.LabelFrame(new_vertical_frame1, text=db_key, padx=10, pady=10)
            frame.pack(side="top", padx=15, pady=10, fill="both", expand=True)
        elif db_key in ['IndexDB', 'CommodityDB1']:
            frame = tk.LabelFrame(new_vertical_frame2, text=db_key, padx=10, pady=10)
            frame.pack(side="top", padx=15, pady=10, fill="both", expand=True)
        else:
            frame = tk.LabelFrame(scrollable_frame, text=db_key, padx=10, pady=10)
            frame.pack(side="left", padx=15, pady=10, fill="both", expand=True)

        for keyword in sorted(keywords):
            button_frame = tk.Frame(frame)  # 创建一个内部Frame来包裹两个按钮
            button_frame.pack(side="top", fill="x", padx=5, pady=2)

            button_data = tk.Button(button_frame, text=keyword, command=lambda k=keyword: on_keyword_selected(k))
            button_data.pack(side="left", fill="x", expand=True)  # 设置左侧填充

            button_chart = tk.Button(button_frame, text="图表", command=lambda k=keyword: on_keyword_selected_chart(k, selection_window))
            button_chart.pack(side="left", fill="x", expand=True)  # 设置右侧填充

    canvas.pack(side="top", fill="both", expand=True)
    scrollbar.pack(side="bottom", fill="x")

def on_keyword_selected(value):
    if value:
        db_key = reverse_mapping[value]
        db_info = database_info[db_key]
        condition = f"name = '{value}'"
        result = query_database(db_info['path'], db_info['table'], condition)
        create_window(result)

def query_database(db_file, table_name, condition):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # 修改这里，添加 DESC 使结果按日期降序排列
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
    conn.close()
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

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()
    
    database_info = {
            'CommodityDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Commodities'},
            'IndexDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Stocks'},
            'CryptoDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Crypto'},
            'CurrencyDB': {'path': '/Users/yanzhang/Finance.db', 'table': 'Currencies'},
            'Bonds': {'path': '/Users/yanzhang/Finance.db', 'table': 'Bonds'},
            'CommodityDB1': {'path': '/Users/yanzhang/Finance.db', 'table': 'Commodities'}
    }

    database_mapping = {
        'CommodityDB': {'Uranium', 'Nickel', 'Soybeans', 'Wheat', 'Coffee', 'Cotton', 'Cocoa', 'Rice', 'Corn',
        'Crude Oil', 'Brent', 'Natural gas', 'Gold', 'Silver', 'Copper', 'Lithium', 'Aluminum'},
        'IndexDB': {'NASDAQ', 'S&P 500', 'SSE Composite Index', 'Shenzhen Index', 'Nikkei 225', 'S&P BSE SENSEX', 'HANG SENG INDEX'},
        'CommodityDB1': {'CRB Index', 'LME Index', 'Nuclear Energy Index', 'Solar Energy Index', 'EU Carbon Permits',
        'Containerized Freight Index'},
        'CryptoDB': {"Bitcoin", "Ether", "Solana"},
        'CurrencyDB': {'DXY', 'CNYEUR', 'USDJPY', 'USDCNY', 'CNYJPY', 'CNYPHP', 'CNYIDR'},
        'Bonds': {"United States", "Japan", "Russia", "India", "Turkey"},
    }

    reverse_mapping = {keyword: db for db, keywords in database_mapping.items() for keyword in keywords}
    create_selection_window()

    root.mainloop()