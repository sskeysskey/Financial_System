import os
import sys
import json
import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, scrolledtext
from datetime import datetime, timedelta
from collections import OrderedDict
import subprocess

sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from Chart_input import plot_financial_data

class SymbolManager:
    def __init__(self, config):
        self.symbols = []
        self.current_index = -1
        for category in config.values():
            if isinstance(category, dict):
                self.symbols.extend(category.keys())
            else:
                self.symbols.extend(category)

    def next_symbol(self):
        self.current_index = (self.current_index + 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def previous_symbol(self):
        self.current_index = (self.current_index - 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def set_current_symbol(self, symbol):
        if symbol in self.symbols:
            self.current_index = self.symbols.index(symbol)
        else:
            print(f"Warning: Symbol {symbol} not found in the list.")

    def reset(self):
        self.current_index = -1

def handle_arrow_key(direction):
    global symbol_manager
    if direction == 'down':
        symbol = symbol_manager.next_symbol()
    else:
        symbol = symbol_manager.previous_symbol()
    
    on_keyword_selected_chart(symbol, None)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file, object_pairs_hook=OrderedDict)

def load_text_data(path):
    data = {}
    with open(path, 'r') as file:
        for line in file:
            key, value = map(str.strip, line.split(':', 1))
            data[key.split()[-1]] = value
    return data

def load_marketcap_pe_data(path):
    data = {}
    with open(path, 'r') as file:
        for line in file:
            key, values = map(str.strip, line.split(':', 1))
            marketcap, pe = map(str.strip, values.split(','))
            data[key] = (float(marketcap), pe)
    return data

# 全局数据变量
keyword_colors = load_json('/Users/yanzhang/Documents/Financial_System/Modules/Colors.json')
config = load_json('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json')
json_data = load_json('/Users/yanzhang/Documents/Financial_System/Modules/description.json')
sector_data = load_json('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json')

def create_custom_style():
    style = ttk.Style()
    style.theme_use('alt')
    button_styles = {
        "Cyan": ("cyan", "black"),
        "Blue": ("blue", "white"),
        "Purple": ("purple", "white"),
        "Green": ("green", "white"),
        "White": ("white", "black"),
        "Yellow": ("yellow", "black"),
        "Orange": ("orange", "black"),
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
    selection_window.bind('<Down>', lambda e: handle_arrow_key('down'))
    selection_window.bind('<Up>', lambda e: handle_arrow_key('up'))

    canvas = tk.Canvas(selection_window)
    scrollbar = tk.Scrollbar(selection_window, orient="horizontal", command=canvas.xview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    create_custom_style()
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(xscrollcommand=scrollbar.set)

    color_frames = [tk.Frame(scrollable_frame) for _ in range(8)]
    for frame in color_frames:
        frame.pack(side="left", padx=1, pady=3, fill="both", expand=True)

    categories = [
        ['Basic_Materials', 'Communication_Services', 'Consumer_Cyclical'],
        ['Technology', 'Energy'],
        ['Industrials', 'Consumer_Defensive', 'Utilities'],
        ['Healthcare', 'Financial_Services', 'Real_Estate'],
        ['Crypto', 'Bonds', 'Indices'],
        ['Commodities'],
        ['Currencies', 'ETFs'],
        ['Economics', 'ETFs_US']
    ]

    for index, category_group in enumerate(categories):
        for db_key, keywords in config.items():
            if db_key in category_group:
                frame = tk.LabelFrame(color_frames[index], text=db_key, padx=1, pady=3)
                frame.pack(side="top", padx=1, pady=3, fill="both", expand=True)

                if isinstance(keywords, dict):
                    items = keywords.items()  # 保持原有顺序
                else:
                    items = [(kw, kw) for kw in keywords]  # 保持原有顺序

                for keyword, translation in items:
                    button_frame = tk.Frame(frame)
                    button_frame.pack(side="top", fill="x", padx=1, pady=3)

                    button_style = get_button_style(keyword)
                    button_text = translation if translation else keyword
                    button_text += f" {compare_data.get(keyword, '')}"

                    button = ttk.Button(button_frame, text=button_text, style=button_style,
                                        command=lambda k=keyword: on_keyword_selected_chart(k, selection_window))

                    # 创建右键菜单
                    menu = tk.Menu(button, tearoff=0)
                    menu.add_command(label="删除", command=lambda k=keyword, g=db_key: delete_item(k, g))

                    # 新增“Add to Earning”选项
                    menu.add_command(label="Add to Earning", command=lambda k=keyword: add_to_earning(k))

                    # 新增“Forced Addding to Earning”选项
                    menu.add_command(label="Forced Adding to Earning", command=lambda k=keyword: add_to_earning_force(k))

                    # 绑定右键点击事件
                    button.bind("<Button-2>", lambda event, m=menu: m.post(event.x_root, event.y_root))

                    button.pack(side="left", fill="x", expand=True)

                    link_label = tk.Label(button_frame, text="🔢", fg="gray", cursor="hand2")
                    link_label.pack(side="right", fill="x", expand=False)
                    link_label.bind("<Button-1>", lambda event, k=keyword: on_keyword_selected(k))

    canvas.pack(side="left", fill="both", expand=True)

def add_to_earning(keyword):
    # 调用 earning.py 脚本
    subprocess.run(['/Library/Frameworks/Python.framework/Versions/Current/bin/python3', 
                    '/Users/yanzhang/Documents/Financial_System/Operations/Insert_Earning.py', 
                    keyword])

def add_to_earning_force(keyword):
    # 调用 earning.py 脚本
    subprocess.run(['/Library/Frameworks/Python.framework/Versions/Current/bin/python3', 
                    '/Users/yanzhang/Documents/Financial_System/Operations/Insert_Earning_Force.py', 
                    keyword])

def delete_item(keyword, group):
    # 从 config 中删除该关键词
    if keyword in config[group]:
        if isinstance(config[group], dict):
            del config[group][keyword]
        else:
            config[group].remove(keyword)
        
        # 将修改后的数据写回 sectors_panel.json 文件
        with open('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json', 'w', encoding='utf-8') as file:
            json.dump(config, file, ensure_ascii=False, indent=4)
        
        print(f"已成功删除 {keyword} from {group}")
        
        # 刷新选择窗口
        refresh_selection_window()

def refresh_selection_window():
    for widget in root.winfo_children():
        widget.destroy()
    create_selection_window()

def get_button_style(keyword):
    color_styles = {
        "red": "Red.TButton",
        "cyan": "Cyan.TButton",
        "blue": "Blue.TButton",
        "purple": "Purple.TButton",
        "yellow": "Yellow.TButton",
        "orange": "Orange.TButton",
        "black": "Black.TButton",
        "white": "White.TButton",
        "green": "Green.TButton",
    }
    for color, style in color_styles.items():
        if keyword in keyword_colors[f"{color}_keywords"]:
            return style
    return "Default.TButton"

def on_keyword_selected(value):
    sector = next((s for s, names in sector_data.items() if value in names), None)
    if sector:
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

def on_keyword_selected_chart(value, parent_window):
    global symbol_manager
    db_path = "/Users/yanzhang/Documents/Database/Finance.db"
    sector = next((s for s, names in sector_data.items() if value in names), None)

    if sector:
        symbol_manager.set_current_symbol(value)
        compare_value = compare_data.get(value, "N/A")
        shares_value = shares.get(value, "N/A")
        marketcap, pe = marketcap_pe_data.get(value, (None, 'N/A'))
        plot_financial_data(db_path, sector, value, compare_value, shares_value, marketcap, pe, json_data, '1Y', False)

def create_window(content):
    top = tk.Toplevel(root)
    top.title("数据库查询结果")
    window_width, window_height = 900, 600
    center_x = (top.winfo_screenwidth() - window_width) // 2
    center_y = (top.winfo_screenheight() - window_height) // 2
    top.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    top.bind('<Escape>', lambda e: close_app(top))

    text_font = tkFont.Font(family="Courier", size=20)
    text_area = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=100, height=30, font=text_font)
    text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
    text_area.insert(tk.INSERT, content)
    text_area.configure(state='disabled')

def close_app(window):
    global symbol_manager
    symbol_manager.reset()
    window.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()
    compare_data = load_text_data('/Users/yanzhang/Documents/News/backup/Compare_All.txt')
    shares = load_text_data('/Users/yanzhang/Documents/News/backup/Shares.txt')
    marketcap_pe_data = load_marketcap_pe_data('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt')

    symbol_manager = SymbolManager(config)
    create_selection_window()
    root.mainloop()