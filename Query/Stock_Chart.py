import re
import sys
import json
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import pyperclip

sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from Chart_input import plot_financial_data

def load_data(path, data_type='json'):
    with open(path, 'r', encoding='utf-8') as file:
        if data_type == 'json':
            return json.load(file)
        else:
            data = {}
            for line in file:
                key, value = map(str.strip, line.split(':', 1))
                if data_type == 'marketcap_pe':
                    marketcap, pe = map(str.strip, value.split(','))
                    data[key] = (float(marketcap), pe)
                else:
                    data[key.split()[-1]] = value
            return data

def close_app(root):
    if root:
        root.quit()
        root.destroy()

def match_and_plot(input_trimmed, sector_data, compare_data, shares, marketcap_pe_data, json_data, db_path):
    search_keys = [input_trimmed, input_trimmed.capitalize(), input_trimmed.upper()]
    for input_variant in search_keys:
        for sector, names in sector_data.items():
            if input_variant in names:
                plot_financial_data(
                    db_path, sector, input_variant,
                    compare_data.get(input_variant, "N/A"),
                    shares.get(input_variant, "N/A"),
                    *marketcap_pe_data.get(input_variant, (None, 'N/A')),
                    json_data, '10Y')
                return True
    input_lower = input_trimmed.lower()
    for sector, names in sector_data.items():
        for name in names:
            if re.search(input_lower, name.lower()):
                plot_financial_data(
                    db_path, sector, name,
                    compare_data.get(name, "N/A"),
                    shares.get(name, "N/A"),
                    *marketcap_pe_data.get(name, (None, 'N/A')),
                    json_data, '10Y')
                return True
    return False

def input_mapping(root, sector_data, compare_data, shares, marketcap_pe_data, json_data, db_path, user_input):
    if not user_input:
        print("未输入任何内容，程序即将退出。")
        close_app(root)
        return

    input_trimmed = user_input.strip()
    if match_and_plot(input_trimmed, sector_data, compare_data, shares, marketcap_pe_data, json_data, db_path):
        close_app(root)
    else:
        messagebox.showerror("错误", "未找到匹配的数据项。")
        close_app(root)

def get_user_input_custom(root, prompt):
    input_dialog = tk.Toplevel(root)
    input_dialog.title(prompt)
    input_dialog.geometry('280x90')

    screen_width = input_dialog.winfo_screenwidth()
    screen_height = input_dialog.winfo_screenheight()
    position_right = int(screen_width/2 - 140)
    position_down = int(screen_height/2 - 140) - 100
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

    sector_data = load_data('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json')
    compare_data = load_data('/Users/yanzhang/Documents/News/backup/Compare_All.txt', 'compare')
    shares = load_data('/Users/yanzhang/Documents/News/backup/Shares.txt', 'compare')
    marketcap_pe_data = load_data('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt', 'marketcap_pe')
    json_data = load_data('/Users/yanzhang/Documents/Financial_System/Modules/Description.json')
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "paste":
            clipboard_content = pyperclip.paste()
            input_mapping(root, sector_data, compare_data, shares, marketcap_pe_data, json_data, db_path, clipboard_content)
        elif arg == "input":
            user_input = get_user_input_custom(root, "请输入")
            input_mapping(root, sector_data, compare_data, shares, marketcap_pe_data, json_data, db_path, user_input)
    else:
        print("请提供参数 input 或 paste")
        sys.exit(1)

    root.mainloop()