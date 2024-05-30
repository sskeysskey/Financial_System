import os
import sys
import json
import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, scrolledtext
from datetime import datetime, timedelta

sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from Chart_panel import plot_financial_data_panel
from Chart_input import plot_financial_data

def load_json_data(path):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)

# 全局数据变量
keyword_colors = load_json_data('/Users/yanzhang/Documents/Financial_System/Modules/Colors.json')
config = load_json_data('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json')
json_data = load_json_data('/Users/yanzhang/Documents/Financial_System/Modules/Description.json')
sector_data = load_json_data('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json')

def create_custom_style():
    style = ttk.Style()
    style.theme_use('alt')
    button_styles = {
        "Green": ("green", "white"),
        "White": ("white", "black"),
        "Purple": ("purple", "white"),
        "Yellow": ("yellow", "black"),
        "Orange": ("orange", "black"),
        "Blue": ("blue", "white"),
        "Red": ("red", "black"),
        "Black": ("black", "white"),
        "Default": ("gray", "black")
    }
    for name, (bg, fg) in button_styles.items():
        style.configure(f"{name}.TButton", background=bg, foreground=fg, font=('Helvetica', 16))
        style.map("TButton", background=[('active', '!disabled', 'pressed', 'focus', 'hover', 'alternate', 'selected', 'background')])

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

    color_frames = [tk.Frame(scrollable_frame) for _ in range(6)]
    for frame in color_frames:
        frame.pack(side="left", padx=5, pady=10, fill="both", expand=True)

    categories = [
        ['Basic_Materials', 'Communication_Services', 'Consumer_Cyclical', 'Consumer_Defensive', 'Technology'],
        ['Financial_Services', 'Healthcare', 'Industrials', 'Real_Estate', 'Energy', 'Utilities'],
        ['Bonds', 'Crypto', 'Indices'],
        ['Commodities', "ETFs_Commodity"],
        ['Currencies', 'ETFs_Oversea'],
        ['Economics', 'ETFs_US']
    ]

    for index, category_group in enumerate(categories):
        for db_key, keywords in config.items():
            if db_key in category_group:
                frame = tk.LabelFrame(color_frames[index], text=db_key, padx=10, pady=10)
                frame.pack(side="top", padx=15, pady=10, fill="both", expand=True)

                for keyword in sorted(keywords):
                    button_frame = tk.Frame(frame)  # 创建一个内部Frame来包裹两个按钮
                    button_frame.pack(side="top", fill="x", padx=5, pady=2)
                    
                    # 根据关键字设置背景颜色
                    if keyword in keyword_colors["purple_keywords"]:
                        button_style = "Purple.TButton"
                    elif keyword in keyword_colors["yellow_keywords"]:
                        button_style = "Yellow.TButton"
                    elif keyword in keyword_colors["orange_keywords"]:
                        button_style = "Orange.TButton"
                    elif keyword in keyword_colors["blue_keywords"]:
                        button_style = "Blue.TButton"
                    elif keyword in keyword_colors["red_keywords"]:
                        button_style = "Red.TButton"
                    elif keyword in keyword_colors["black_keywords"]:
                        button_style = "Black.TButton"
                    elif keyword in keyword_colors["white_keywords"]:
                        button_style = "White.TButton"
                    elif keyword in keyword_colors["green_keywords"]:
                        button_style = "Green.TButton"
                    else:
                        button_style = "Default.TButton"  # 默认颜色
                    
                    change_text = compare_data.get(keyword, "")
                    button_text = f"{keyword} {change_text}"
                    
                    button_data = ttk.Button(button_frame, text=button_text, style=button_style,
                        command=lambda k=keyword: on_keyword_selected_chart(k, selection_window))
                    button_data.pack(side="left", fill="x", expand=True)
                    
                    # 使用Label创建一个可点击的文本链接
                    link_label = tk.Label(button_frame, text="🔢", fg="gray", cursor="hand2")
                    link_label.pack(side="right", fill="x", expand=False)
                    link_label.bind("<Button-1>", lambda event, k=keyword: on_keyword_selected(k))

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

def load_compare_data(path):
    compare_data = {}
    with open(path, 'r') as file:
        for line in file.readlines():
            parts = line.split(':')
            key = parts[0].split()[-1].strip()
            value = parts[1].strip()
            compare_data[key] = value
    return compare_data

def load_marketcap_pe_data(path):
    marketcap_pe_data = {}
    with open(path, 'r') as file:
        for line in file.readlines():
            parts = line.split(':')
            key = parts[0].strip()
            values = parts[1].split(',')
            marketcap = float(values[0].strip())
            pe = values[1].strip()
            marketcap_pe_data[key] = (marketcap, pe)
    return marketcap_pe_data

def on_keyword_selected_chart(value, parent_window):
    stock_sectors = ["Basic_Materials", "Communication_Services", "Consumer_Cyclical",
        "Consumer_Defensive", "Energy", "Financial_Services", "Healthcare", "Industrials",
        "Real_Estate", "Technology", "Utilities"]
    economics_sectors = ["Economics","ETFs"]
    
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
    for sector, names in sector_data.items():
        if value in names:
            if sector in stock_sectors:            
                plot_financial_data(db_path, sector, value, 
                        compare_data.get(value, "N/A"), 
                        shares.get(value, "N/A"), 
                        fullnames.get(value, "N/A"), 
                        *marketcap_pe_data.get(value, (None, 'N/A')), 
                        json_data, '1Y')
            elif sector in economics_sectors:            
                plot_financial_data(db_path, sector, value, 
                        compare_data.get(value, "N/A"), 
                        shares.get(value, "N/A"), 
                        fullnames.get(value, "N/A"), 
                        *marketcap_pe_data.get(value, (None, 'N/A')), 
                        json_data, '10Y')
            else:
                change = compare_data.get(value, "")
                plot_financial_data_panel(db_path, sector, value, change, '1Y')

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
    compare_data = load_compare_data('/Users/yanzhang/Documents/News/backup/Compare_All.txt')
    shares = load_compare_data('/Users/yanzhang/Documents/News/backup/Shares.txt')
    fullnames = load_compare_data('/Users/yanzhang/Documents/News/backup/symbol_names.txt')
    marketcap_pe_data = load_marketcap_pe_data('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt')
    
    create_selection_window()
    root.mainloop()