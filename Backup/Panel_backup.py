import sys
import json
import sqlite3
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, scrolledtext, simpledialog
from collections import OrderedDict
import subprocess

# ----------------------------------------------------------------------
# Update sys.path so we can import from custom modules
# ----------------------------------------------------------------------
sys.path.append('/Users/yanzhang/Coding/Financial_System/Query')
from Chart_input import plot_financial_data

# ----------------------------------------------------------------------
# Constants / Global Configurations
# ----------------------------------------------------------------------
CONFIG_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_panel.json'
COLORS_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Colors.json'
DESCRIPTION_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/description.json'
SECTORS_ALL_PATH = '/Users/yanzhang/Coding/Financial_System/Modules/Sectors_All.json'
COMPARE_DATA_PATH = '/Users/yanzhang/Coding/News/backup/Compare_All.txt'
SHARES_PATH = '/Users/yanzhang/Coding/News/backup/Shares.txt'
MARKETCAP_PATH = '/Users/yanzhang/Coding/News/backup/marketcap_pe.txt'
DB_PATH = '/Users/yanzhang/Coding/Database/Finance.db'

DISPLAY_LIMITS = {
    'default': 'all',  # 默认显示全部
    'Indices': 14,
    "Bonds": 'all',
    'Commodities': 24,
    'ETFs': 10,
    'Currencies': 6,
    'Economics': 7,
    'ETFs_US': 14,
    'Qualified_Symbol': 15,
    'Earning_Filter': 15
}

# Define categories as a global variable
categories = [
    ['Basic_Materials', 'Consumer_Cyclical', 'Real_Estate'],
    ['Energy', 'Technology', 'Qualified_Symbol'],
    ['Utilities', 'Industrials', 'Consumer_Defensive'],
    ['Communication_Services', 'Financial_Services', 'Healthcare', 'Earning_Filter'],
    ['Bonds', 'Indices'],
    ['Commodities'],
    ['Currencies', 'Crypto', 'ETFs'],
    ['Economics', 'ETFs_US']
]

# Global variables initialized below; placeholders for IDE clarity
symbol_manager = None
compare_data = {}
shares = {}
marketcap_pe_data = {}
config = {}
keyword_colors = {}
sector_data = {}
json_data = {}

# ----------------------------------------------------------------------
# Classes
# ----------------------------------------------------------------------
class SymbolManager:
    """
    Manages navigation between symbols (next, previous) while keeping track
    of a current index.
    """
    def __init__(self, config_data, all_categories):
        self.symbols = []
        self.current_index = -1
        for category_group in all_categories:
            for sector in category_group:
                if sector in config_data:
                    sector_content = config_data[sector]
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

# ----------------------------------------------------------------------
# Utility / Helper Functions
# ----------------------------------------------------------------------
def limit_items(items, sector):
    """
    根据配置限制显示数量
    """
    limit = DISPLAY_LIMITS.get(sector, DISPLAY_LIMITS.get('default', 'all'))
    if limit == 'all':
        return items
    return list(items)[:limit]

def load_json(path):
    """
    Loads a JSON file from the given path, preserving key order.
    """
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file, object_pairs_hook=OrderedDict)


def load_text_data(path):
    """
    加载文本文件的数据。如果数据中包含逗号，则拆分为元组，
    否则直接返回字符串。
    """
    data = {}
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue  # 跳过空行
            # 分割 key 和 value
            key, value = map(str.strip, line.split(':', 1))
            # 提取 key 的最后一个单词
            cleaned_key = key.split()[-1]
            # 如果 value 中包含逗号，则拆分后存储为元组
            if ',' in value:
                parts = [p.strip() for p in value.split(',')]
                data[cleaned_key] = tuple(parts)
            else:
                data[cleaned_key] = value
    return data

def load_marketcap_pe_data(path):
    """
    Loads data from a text file in the format 'key: marketcap, pe'.
    如果数据多出了其他项，只读取前两个项（忽略后续的额外数据）。
    """
    data = {}
    with open(path, 'r') as file:
        for line in file:
            # 按":"分割成key和values
            key, values = map(str.strip, line.split(':', 1))
            parts = [p.strip() for p in values.split(',')]
            if len(parts) >= 2:
                # 只取前两个数据，忽略其他数据
                marketcap_val, pe_val, *_ = parts
                data[key] = (float(marketcap_val), pe_val)
            else:
                print(f"格式异常：{line}")
    return data

def get_button_style(keyword):
    """
    Determines the style of a button based on keyword color classification.
    """
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

def query_database(db_path, table_name, condition):
    """
    Queries the specified table in the database using provided condition (WHERE clause).
    Returns formatted string of the results.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        query = f"SELECT * FROM {table_name} WHERE {condition} ORDER BY date DESC;"
        cursor.execute(query)
        rows = cursor.fetchall()
        if not rows:
            return "今天没有数据可显示。\n"
        columns = [desc[0] for desc in cursor.description]
        # Compute column widths for neat spacing
        col_widths = [max(len(str(row[i])) for row in rows + [columns]) for i in range(len(columns))]

        header = ' | '.join([col.ljust(col_widths[idx]) for idx, col in enumerate(columns)]) + '\n'
        separator = '-' * len(header) + '\n'

        output_lines = [header, separator]
        for row in rows:
            row_str = ' | '.join(str(item).ljust(col_widths[idx]) for idx, item in enumerate(row))
            output_lines.append(row_str + '\n')
        return ''.join(output_lines)

def execute_external_script(script_type, keyword, group=None):
    """
    Unified handler for scripted external operations.
    """
    base_path = '/Users/yanzhang/Coding/Financial_System'
    script_configs = {
        'blacklist': f'{base_path}/Operations/Insert_Blacklist.py',
        'similar': f'{base_path}/Query/Find_Similar_Tag.py',
        'tags': f'{base_path}/Operations/Editor_Symbol_Tags.py',
        'editor_earning': f'{base_path}/Operations/Editor_Earning_DB.py',
        'earning': f'{base_path}/Operations/Insert_Earning.py',
        'earning_force': f'{base_path}/Operations/Insert_Earning_Force.py',
        'futu': '/Users/yanzhang/Coding/ScriptEditor/Stock_CheckFutu.scpt',
        'kimi': '/Users/yanzhang/Coding/ScriptEditor/CheckKimi_Earning.scpt'
    }

    try:
        if script_type == 'futu':
            subprocess.run(['osascript', script_configs[script_type], keyword], check=True)
        
        if script_type == 'kimi':
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
    """
    Deletes the given keyword from the specified group in the config,
    and refreshes the GUI window.
    """
    global config
    if group in config and keyword in config[group]:
        if isinstance(config[group], dict):
            del config[group][keyword]
        else:
            config[group].remove(keyword)

        with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
            json.dump(config, file, ensure_ascii=False, indent=4)

        print(f"已成功删除 {keyword} from {group}")
        refresh_selection_window()
    else:
        print(f"{keyword} 不存在于 {group} 中")

def rename_item(keyword, group):
    """
    Renames (updates the description for) a given keyword in a specified group.
    """
    global config
    try:
        new_name = simpledialog.askstring("重命名", f"请为 {keyword} 输入新名称：")
        if new_name is not None and new_name.strip() != "":
            with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
                config_data = json.load(file)

            if group in config_data and keyword in config_data[group]:
                config_data[group][keyword] = new_name.strip()
                with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
                    json.dump(config_data, file, ensure_ascii=False, indent=4)

                print(f"已将 {keyword} 的描述更新为: {new_name}")
                config = load_json(CONFIG_PATH)
                refresh_selection_window()
            else:
                print(f"未找到 {keyword} 在 {group} 中")
        else:
            print("重命名被取消或输入为空。")
    except Exception as e:
        print(f"重命名过程中发生错误: {e}")

# ======================================================================
# 新增函数：将 symbol 移动到 Qualified_Symbol 分组
# ======================================================================
def move_item_to_qualified_symbol(keyword, source_group):
    """
    将一个 symbol 从其源分组移动到 'Qualified_Symbol' 分组。
    """
    global config
    target_group = 'Qualified_Symbol'

    # 检查源分组和关键字是否存在
    if source_group in config and isinstance(config[source_group], dict) and keyword in config[source_group]:
        # 确保目标分组存在，如果不存在则创建一个
        if target_group not in config:
            config[target_group] = {}
        elif not isinstance(config[target_group], dict):
            print(f"错误: 目标分组 '{target_group}' 的格式不是预期的字典。")
            return

        # 如果 symbol 已经在目标分组中，则无需移动
        if keyword in config[target_group]:
            print(f"{keyword} 已经存在于 {target_group} 中，无需移动。")
            # 仍然从源分组中删除
            del config[source_group][keyword]
        else:
            # 获取要移动的条目的值（即它的描述）
            item_value = config[source_group][keyword]

            # 添加到目标分组
            config[target_group][keyword] = item_value

            # 从源分组中删除
            del config[source_group][keyword]

        # 将更新后的配置写回 JSON 文件
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
                json.dump(config, file, ensure_ascii=False, indent=4)
            print(f"已成功将 {keyword} 从 {source_group} 移动到 {target_group}")

            # 刷新界面以显示更改
            refresh_selection_window()
        except Exception as e:
            print(f"保存文件时出错: {e}")
    else:
        print(f"错误: 在 {source_group} 中未找到 {keyword}，或该分组格式不正确。")
# ======================================================================

def on_keyword_selected(value):
    """
    Handles clicking the "🔢" label to display relevant database entries
    for the selected keyword.
    """
    sector = next((s for s, names in sector_data.items() if value in names), None)
    if sector:
        condition = f"name = '{value}'"
        result = query_database(DB_PATH, sector, condition)
        create_window(result)

def on_keyword_selected_chart(value, parent_window):
    """
    Plots the financial data for the keyword and sets the current symbol
    in SymbolManager. Also retrieves compare, shares, marketcap, and PE data.
    """
    global symbol_manager
    sector = next((s for s, names in sector_data.items() if value in names), None)
    if sector:
        symbol_manager.set_current_symbol(value)
        compare_value = compare_data.get(value, "N/A")
        shares_value = shares.get(value, "N/A")
        marketcap_val, pe_val = marketcap_pe_data.get(value, (None, 'N/A'))
        plot_financial_data(
            DB_PATH, sector, value, compare_value, shares_value,
            marketcap_val, pe_val, json_data, '1Y', False
        )

def create_window(content):
    """
    Opens a new Toplevel window to display database query results.
    """
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
    """
    Destroys the given window and resets the SymbolManager's index.
    """
    global symbol_manager
    symbol_manager.reset()
    window.destroy()

def refresh_selection_window():
    """
    Reloads the config from disk and rebuilds the selection window.
    """
    global config
    config = load_json(CONFIG_PATH)
    for widget in root.winfo_children():
        widget.destroy()
    create_selection_window()

def handle_arrow_key(direction):
    """
    Handles the Up/Down arrow key events to cycle through symbols
    and update the chart.
    """
    global symbol_manager
    if direction == 'down':
        symbol = symbol_manager.next_symbol()
    else:
        symbol = symbol_manager.previous_symbol()

    if symbol:
        on_keyword_selected_chart(symbol, None)

# ----------------------------------------------------------------------
# 新增部分：Tooltip 辅助函数定义，根据新的 description.json 文件结构，
# 从 "stocks" 和 "etfs" 中查找指定 symbol 对应的 tag 信息。
# ----------------------------------------------------------------------
def get_tags_for_symbol(symbol):
    """
    根据 symbol 在 json_data 中查找 tag 信息，
    如果在 stocks 或 etfs 中找到则返回 tag 数组，否则返回 "无标签"。
    """
    for item in json_data.get("stocks", []):
        if item.get("symbol", "") == symbol:
            return item.get("tag", "无标签")
    for item in json_data.get("etfs", []):
        if item.get("symbol", "") == symbol:
            return item.get("tag", "无标签")
    return "无标签"

def add_tooltip(widget, symbol):
    """
    为指定的 Tkinter 控件绑定鼠标悬停显示浮窗的事件，
    浮窗中显示该 symbol 的 tag 信息（从 description.json 中提取）。
    """
    def on_enter(event):
        tags_info = get_tags_for_symbol(symbol)
        print("tags_info:", tags_info)  # 调试用，检查标签数据是否正确提取
        # 如果 tag 为列表，则转换为逗号分隔的字符串
        if isinstance(tags_info, list):
            tags_info = ", ".join(tags_info)
        tooltip = tk.Toplevel(widget)
        tooltip.wm_overrideredirect(True)  # 去掉窗口边框
        # 浮窗的位置：在鼠标坐标附近
        x = event.x_root + 20
        y = event.y_root + 10
        tooltip.wm_geometry(f"+{x}+{y}")
        # 浮窗内样式可以根据需要调整
        # 显示字体设置为 Arial，前景色明确设为黑色
        label = tk.Label(
            tooltip,
            text=tags_info,
            background="lightyellow",
            fg="black",         # 明确设置前景色
            relief="solid",
            borderwidth=1,
            font=("Arial", 20)  # 如有问题可尝试 Arial 或其他系统自带字体
        )
        label.pack(ipadx=5, ipady=3)  # 增加一点内边距
        widget.tooltip = tooltip

    def on_leave(event):
        if hasattr(widget, "tooltip") and widget.tooltip is not None:
            widget.tooltip.destroy()
            widget.tooltip = None

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)

# ----------------------------------------------------------------------
# TKinter GUI Setup
# ----------------------------------------------------------------------
def create_custom_style():
    """
    Creates custom ttk styles for various color-coded TButtons.
    """
    style = ttk.Style()
    style.theme_use('alt')

    # Background/foreground combos
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
        style.map(
            "TButton",
            background=[('active', '!disabled', 'pressed', 'focus', 'hover', 'alternate', 'selected', 'background')]
        )

def create_selection_window():
    """
    Builds the main selection window. Dynamically creates frames and buttons
    based on 'categories' and 'config' data. Allows user to navigate symbols.
    """
    selection_window = tk.Toplevel(root)
    selection_window.title("选择查询关键字")
    selection_window.geometry("1480x900")

    # Key bindings
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

    # Create one frame per category group
    color_frames = [tk.Frame(scrollable_frame) for _ in range(len(categories))]
    for frame in color_frames:
        frame.pack(side="left", padx=1, pady=3, fill="both", expand=True)

    # Build the interface
    for index, category_group in enumerate(categories):
        for sector in category_group:
            if sector in config:
                keywords = config[sector]
                frame = tk.LabelFrame(color_frames[index], text=sector, padx=1, pady=3)
                frame.pack(side="top", padx=1, pady=3, fill="both", expand=True)

                # Retain original order
                if isinstance(keywords, dict):
                    items = limit_items(keywords.items(), sector)
                else:
                    items = limit_items([(kw, kw) for kw in keywords], sector)

                # 显示条目数量信息
                total = len(keywords) if isinstance(keywords, dict) else len(keywords)
                shown = len(items)
                sector_label = f"{sector} ({shown}/{total})" if shown != total else sector
                frame.configure(text=sector_label)

                for keyword, translation in items:
                    button_frame = tk.Frame(frame)
                    button_frame.pack(side="top", fill="x", padx=1, pady=3)

                    button_style = get_button_style(keyword)
                    button_text = translation if translation else keyword
                    button_text += f" {compare_data.get(keyword, '')}"

                    button = ttk.Button(
                        button_frame, text=button_text, style=button_style,
                        command=lambda k=keyword: on_keyword_selected_chart(k, selection_window)
                    )

                    # 右键菜单配置
                    menu = tk.Menu(button, tearoff=0)
                    menu.add_command(label="删除", command=lambda k=keyword, g=sector: delete_item(k, g))
                    menu.add_command(label="改名", command=lambda k=keyword, g=sector: rename_item(k, g))
                    
                    # ======================================================================
                    # 在此为右键菜单添加“移动”选项
                    # ======================================================================
                    menu.add_command(label="移动到 Qualified_Symbol", command=lambda k=keyword, g=sector: move_item_to_qualified_symbol(k, g))
                    # ======================================================================

                    menu.add_command(label="Kimi检索财报", command=lambda k=keyword: execute_external_script('kimi', k))

                    # "Add to Earning" option
                    menu.add_command(label="添加到 Earning", command=lambda k=keyword: execute_external_script('earning', k))
                    
                    # "编辑earning数据库" option
                    menu.add_command(label="编辑 DB", command=lambda k=keyword: execute_external_script('editor_earning', k))

                    menu.add_separator()
                    menu.add_command(label="编辑 Tags", command=lambda k=keyword: execute_external_script('tags', k))
                    menu.add_command(label="在富途中搜索", command=lambda k=keyword: execute_external_script('futu', k))
                    menu.add_command(label="找相似", command=lambda k=keyword: execute_external_script('similar', k))

                    menu.add_separator()
                    menu.add_command(label="加入黑名单", command=lambda k=keyword, g=sector: execute_external_script('blacklist', k, g))
                    menu.add_command(label="Forced Adding to Earning", command=lambda k=keyword: execute_external_script('earning_force', k))

                    # 绑定右键（Mac 使用 Button-2，Windows 通常是 Button-3）
                    button.bind("<Button-2>", lambda event, m=menu: m.post(event.x_root, event.y_root))
                    
                    # *******************************
                    # 为按钮增加 Tooltip 功能（根据新的 description.json 文件结构）
                    add_tooltip(button, keyword)
                    # *******************************

                    button.pack(side="left", fill="x", expand=True)

                    link_label = tk.Label(button_frame, text="🔢", fg="gray", cursor="hand2")
                    link_label.pack(side="right", fill="x", expand=False)
                    link_label.bind("<Button-1>", lambda event, k=keyword: on_keyword_selected(k))

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="bottom", fill="x")

# ----------------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------------
if __name__ == '__main__':
    # Load data
    keyword_colors = load_json(COLORS_PATH)
    config = load_json(CONFIG_PATH)
    json_data = load_json(DESCRIPTION_PATH)
    sector_data = load_json(SECTORS_ALL_PATH)

    compare_data = load_text_data(COMPARE_DATA_PATH)
    shares = load_text_data(SHARES_PATH)
    marketcap_pe_data = load_marketcap_pe_data(MARKETCAP_PATH)

    # Initialize main Tk
    root = tk.Tk()
    root.withdraw()

    # Create SymbolManager
    symbol_manager = SymbolManager(config, categories)

    # Create selection window (main GUI)
    create_selection_window()

    # Start GUI loop
    root.mainloop()