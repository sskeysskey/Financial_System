import re
import sys
import json
import subprocess
import tkinter as tk
import pyperclip
from functools import lru_cache
import concurrent.futures
import sqlite3  # 新增: 导入sqlite3库

sys.path.append('/Users/yanzhang/Documents/Financial_System/Query')
from Chart_input import plot_financial_data

@lru_cache(maxsize=None)
def lazy_load_data(path, data_type='json'):
    """
    懒加载函数，现在只处理JSON和通用文本文件。
    移除了对 marketcap_pe.txt 和 Shares.txt 的特定处理逻辑。
    """
    with open(path, 'r', encoding='utf-8') as file:
        if data_type == 'json':
            return json.load(file)
        else:
            data = {}
            for line in file:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                key, value = map(str.strip, line.split(':', 1))
                data[key] = value
            return data

def close_app(root):
    if root:
        root.quit()
        root.destroy()

def display_dialog(message):
    # AppleScript代码模板
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    
    # 使用subprocess调用osascript
    process = subprocess.run(['osascript', '-e', applescript_code], check=True)

# 新增: 从SQLite数据库获取市、盈、股、净数据
def fetch_mnspp_data_from_db(db_path, symbol):
    """
    根据股票代码从MNSPP表中查询 shares, marketcap, pe_ratio, pb。
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        query = "SELECT shares, marketcap, pe_ratio, pb FROM MNSPP WHERE symbol = ?"
        cursor.execute(query, (symbol,))
        result = cursor.fetchone()

    if result:
        # 数据库查到了数据，返回实际值
        shares, marketcap, pe, pb = result
        return shares, marketcap, pe, pb
    else:
        # 数据库没查到，返回默认值
        return "N/A", None, "N/A", "--"

def match_and_plot(input_trimmed, sector_data, compare_data, json_data, db_path):
    """
    修改后的匹配与绘图函数。
    - 不再接收 shares 和 marketcap_pe_data 字典。
    - 在找到匹配项后，直接调用数据库查询函数。
    """
    search_keys = [input_trimmed, input_trimmed.capitalize(), input_trimmed.upper()]
    for input_variant in search_keys:
        for sector, names in sector_data.items():
            if input_variant in names:
                # 找到匹配项，从数据库获取数据
                shares_val, marketcap, pe, pb = fetch_mnspp_data_from_db(db_path, input_variant)
                
                plot_financial_data(
                    db_path, sector, input_variant,
                    compare_data.get(input_variant, "N/A"),
                    (shares_val, pb),  # 将 shares 和 pb 组合成元组传入
                    marketcap,
                    pe,
                    json_data, '10Y', True)
                return True
    input_lower = input_trimmed.lower()
    for sector, names in sector_data.items():
        for name in names:
            if re.search(input_lower, name.lower()):
                # 找到匹配项，从数据库获取数据
                shares_val, marketcap, pe, pb = fetch_mnspp_data_from_db(db_path, name)

                plot_financial_data(
                    db_path, sector, name,
                    compare_data.get(name, "N/A"),
                    (shares_val, pb), # 将 shares 和 pb 组合成元组传入
                    marketcap,
                    pe,
                    json_data, '10Y', True)
                return True
    return False

def load_data_parallel():
    """
    修改后的并行加载函数。
    - 移除了 marketcap_pe.txt 和 Shares.txt 的加载任务。
    """
    data_sources = [
        ('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json', 'json'),
        ('/Users/yanzhang/Documents/News/backup/Compare_All.txt', 'compare'),
        # ('/Users/yanzhang/Documents/News/backup/Shares.txt', 'compare'), # 已移除
        # ('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt', 'marketcap_pe'), # 已移除
        ('/Users/yanzhang/Documents/Financial_System/Modules/description.json', 'json')
    ]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_data = {executor.submit(lazy_load_data, path, data_type): (path, data_type) for path, data_type in data_sources}
        results = {}
        for future in concurrent.futures.as_completed(future_to_data):
            path, data_type = future_to_data[future]
            try:
                data = future.result()
                results[path] = data
            except Exception as exc:
                print(f'{path} generated an exception: {exc}')
    
    return results

def input_mapping(root, data, db_path, user_input):
    """
    修改后的输入映射函数。
    - 调用 match_and_plot 时不再传递 shares 和 marketcap_pe 数据。
    """
    if not user_input:
        print("未输入任何内容，程序即将退出。")
        close_app(root)
        return

    input_trimmed = user_input.strip()
    if match_and_plot(input_trimmed, data['/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json'],
                      data['/Users/yanzhang/Documents/News/backup/Compare_All.txt'],
                      data['/Users/yanzhang/Documents/Financial_System/Modules/description.json'],
                      db_path):
        close_app(root)
    else:
        # 把没找到的符号拷贝到剪贴板，然后用 show_description.py 的 paste 模式来弹 description 界面
        pyperclip.copy(input_trimmed)
        subprocess.run([
            sys.executable,
            '/Users/yanzhang/Documents/Financial_System/Query/show_description.py',
            'paste'
        ], check=True)
        close_app(root)

def get_user_input_custom(root, prompt):
    input_dialog = tk.Toplevel(root)
    input_dialog.title(prompt)
    input_dialog.geometry('280x90')

    screen_width = input_dialog.winfo_screenwidth()
    screen_height = input_dialog.winfo_screenheight()
    position_right = int(screen_width / 2 - 140)
    position_down = int(screen_height / 2 - 140) - 100
    input_dialog.geometry(f"280x90+{position_right}+{position_down}")

    entry = tk.Entry(input_dialog, width=20, font=('Helvetica', 18))
    entry.pack(pady=20, ipady=10)
    entry.focus_set()

    try:
        entry.insert(0, root.clipboard_get())
    except tk.TclError:
        pass
    entry.select_range(0, tk.END)

    user_input = None

    def on_submit():
        nonlocal user_input
        user_input = entry.get()
        input_dialog.destroy()

    entry.bind('<Return>', lambda event: on_submit())
    input_dialog.bind('<Escape>', lambda event: input_dialog.destroy())
    input_dialog.wait_window(input_dialog)
    return user_input

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()
    root.bind('<Escape>', lambda event: close_app(root))

    data = load_data_parallel()
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "paste":
            clipboard_content = pyperclip.paste()
            input_mapping(root, data, db_path, clipboard_content)
        elif arg == "input":
            user_input = get_user_input_custom(root, "请输入")
            input_mapping(root, data, db_path, user_input)
    else:
        print("请提供参数 input 或 paste")
        sys.exit(1)

    root.mainloop()