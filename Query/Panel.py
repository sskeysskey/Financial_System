import os
import sys
import json
import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, scrolledtext, simpledialog
from datetime import datetime, timedelta
from collections import OrderedDict
import subprocess

sys.path.append('/Users/yanzhang/Documents/Financial_System/Query')
from Chart_input import plot_financial_data

# 定义 categories 全局变量
categories = [
    ['Basic_Materials', 'Consumer_Cyclical', 'Real_Estate'],
    ['Energy', 'Technology'],
    ['Utilities', 'Industrials', 'Consumer_Defensive'],
    ['Communication_Services', 'Financial_Services', 'Healthcare'],
    ['Bonds', 'Indices'],
    ['Commodities'],
    ['Crypto', 'ETFs', 'Currencies'],
    ['Economics', 'ETFs_US']
]

class SymbolManager:
    def __init__(self, config, categories):
        self.symbols = []
        self.current_index = -1
        for category_group in categories:
            for sector in category_group:
                if sector in config:
                    sector_content = config[sector]
                    if isinstance(sector_content, dict):
                        self.symbols.extend(sector_content.keys())
                    else:
                        self.symbols.extend(sector_content)
        if not self.symbols:
            print("Warning: No symbols found based on the provided categories and config.")

    def next_symbol(self):
        if not self.symbols:
            return None
        self.current_index = (self.current_index + 1) % len(self.symbols)
        return self.symbols[self.current_index]

    def previous_symbol(self):
        if not self.symbols:
            return None
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
    
    if symbol:
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

    color_frames = [tk.Frame(scrollable_frame) for _ in range(len(categories))]  # 动态根据 categories 数量创建 frame
    for frame in color_frames:
        frame.pack(side="left", padx=1, pady=3, fill="both", expand=True)

    # 使用全局的 categories
    for index, category_group in enumerate(categories):
        for sector in category_group:
            if sector in config:
                keywords = config[sector]
                frame = tk.LabelFrame(color_frames[index], text=sector, padx=1, pady=3)
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
                    menu.add_command(label="删除", command=lambda k=keyword, g=sector: delete_item(k, g))
                    menu.add_command(label="改名", command=lambda k=keyword, g=sector: rename_item(k, g))

                    # 新增“Add to Earning”选项
                    menu.add_command(label="Add to Earning", command=lambda k=keyword: execute_external_script('earning', k))

                    menu.add_separator()  # 添加分隔线
                    menu.add_command(label="编辑Tags", command=lambda k=keyword: execute_external_script('tags', k))
                    menu.add_command(label="在富途中搜索", command=lambda k=keyword: execute_external_script('futu', k))
                    menu.add_command(label="找相似", command=lambda k=keyword: execute_external_script('similar', k))

                    menu.add_separator()  # 添加分隔线
                    menu.add_command(label="加入黑名单", command=lambda k=keyword, g=sector: execute_external_script('blacklist', k, g))
                    # 新增“Forced Addding to Earning”选项
                    menu.add_command(label="Forced Adding to Earning", command=lambda k=keyword: execute_external_script('earning_force', k))

                    # 绑定右键点击事件
                    button.bind("<Button-2>", lambda event, m=menu: m.post(event.x_root, event.y_root))
                    button.pack(side="left", fill="x", expand=True)

                    link_label = tk.Label(button_frame, text="🔢", fg="gray", cursor="hand2")
                    link_label.pack(side="right", fill="x", expand=False)
                    link_label.bind("<Button-1>", lambda event, k=keyword: on_keyword_selected(k))
    
    canvas.pack(side="left", fill="both", expand=True)

def refresh_selection_window():
    global config  # 添加全局声明
    
    # 重新加载配置文件
    config = load_json('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json')
    
    # 刷新界面
    for widget in root.winfo_children():
        widget.destroy()
    create_selection_window()
    
def rename_item(keyword, group):
    global config  # 添加全局声明
    try:
        # 创建输入对话框
        new_name = simpledialog.askstring("重命名", f"请为 {keyword} 输入新名称：")
        
        if new_name is not None and new_name.strip() != "":  # 用户点击了确定且输入不为空
            config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'
            
            # 读取配置文件
            with open(config_path, 'r', encoding='utf-8') as file:
                config_data = json.load(file)
            
            # 更新名称
            if group in config_data and keyword in config_data[group]:
                config_data[group][keyword] = new_name.strip()
                
                # 保存更新后的配置
                with open(config_path, 'w', encoding='utf-8') as file:
                    json.dump(config_data, file, ensure_ascii=False, indent=4)
                
                print(f"已将 {keyword} 的描述更新为: {new_name}")
                config = load_json(config_path)
                # 刷新选择窗口
                refresh_selection_window()
            else:
                print(f"未找到 {keyword} 在 {group} 中")
        else:
            print("重命名被取消或输入为空。")
    except Exception as e:
        print(f"重命名过程中发生错误: {e}")

def execute_external_script(script_type, keyword, group=None):
    """统一处理外部脚本执行的通用函数
    
    Args:
        script_type (str): 脚本类型标识
        keyword (str): 关键词
        group (str, optional): 分组名称
    """
    base_path = '/Users/yanzhang/Documents/Financial_System'
    script_configs = {
        'blacklist': f'{base_path}/Operations/Insert_Blacklist.py',
        'similar': f'{base_path}/Query/Find_Similar_Tag.py',
        'tags': f'{base_path}/Operations/Tags_Editor.py',
        'earning': f'{base_path}/Operations/Insert_Earning.py',
        'earning_force': f'{base_path}/Operations/Insert_Earning_Force.py',
        'futu': '/Users/yanzhang/Documents/ScriptEditor/Stock_CheckFutu.scpt'
    }
    
    try:
        if script_type == 'futu':
            subprocess.run(['osascript', script_configs[script_type], keyword], check=True)
        else:
            python_path = '/Library/Frameworks/Python.framework/Versions/Current/bin/python3'
            subprocess.run([python_path, script_configs[script_type], keyword], check=True)
            
        if script_type == 'blacklist' and group:
            delete_item(keyword, group)
            
    except subprocess.CalledProcessError as e:
        print(f"执行脚本时出错: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")

def delete_item(keyword, group):
    global config  # 添加全局声明
    
    # 从 config 中删除该关键词
    if group in config and keyword in config[group]:
        if isinstance(config[group], dict):
            del config[group][keyword]
        else:
            config[group].remove(keyword)
        
        # 更新配置文件
        config_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_panel.json'
        with open(config_path, 'w', encoding='utf-8') as file:
            json.dump(config, file, ensure_ascii=False, indent=4)
        
        print(f"已成功删除 {keyword} from {group}")
        
        # 刷新选择窗口
        refresh_selection_window()
    else:
        print(f"{keyword} 不存在于 {group} 中")

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
        if keyword in keyword_colors.get(f"{color}_keywords", []):
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

    symbol_manager = SymbolManager(config, categories)  # 传入 categories
    create_selection_window()
    root.mainloop()