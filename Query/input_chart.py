import re
import sys
import json
import subprocess
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import pyperclip

sys.path.append('/Users/yanzhang/Documents/Financial_System/Modules')
from Chart_input import plot_financial_data

def load_sector_data(path):
    with open(path, 'r') as file:
        return json.load(file)

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

def load_json_data(path):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)

def close_app(root):
    if root:
        root.quit()
        root.destroy()

def input_mapping(root, sector_data, compare_data, shares, fullnames, marketcap_pe_data, json_data, db_path):
    user_input = get_user_input_custom(root, "请输入")
    if user_input is None:
        print("未输入任何内容，程序即将退出。")
        close_app(root)
        return

    input_trimmed = user_input.strip()
    search_keys = {
        'exact': input_trimmed,
        'capitalized': input_trimmed.capitalize(),
        'upper': input_trimmed.upper(),
    }
    
    found = False
    for key, input_variant in search_keys.items():
        for sector, names in sector_data.items():
            for name in names:
                if input_variant == name:
                    plot_financial_data(
                        db_path, sector, name,
                        compare_data.get(name, "N/A"),
                        shares.get(name, "N/A"),
                        fullnames.get(name, "N/A"),
                        *marketcap_pe_data.get(name, (None, 'N/A')),
                        json_data, '10Y')
                    found = True
                    break
            if found:
                break
        if found:
            break
    
    if not found:
        lower_input = input_trimmed.lower()
        # 进行模糊匹配
        for sector, names in sector_data.items():
            for name in names:
                if re.search(lower_input, name.lower()):
                    plot_financial_data(
                        db_path, sector, name,
                        compare_data.get(name, "N/A"),
                        shares.get(name, "N/A"),
                        fullnames.get(name, "N/A"),
                        *marketcap_pe_data.get(name, (None, 'N/A')),
                        json_data, '10Y')
                    found = True
                    break
            if found:
                break

    if found:
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
    window_width = 280
    window_height = 90
    position_right = int(screen_width/2 - window_width/2)
    position_down = int(screen_height/2 - window_height/2) - 100
    input_dialog.geometry(f"{window_width}x{window_height}+{position_right}+{position_down}")

    entry = tk.Entry(input_dialog, width=20, font=('Helvetica', 18))
    entry.pack(pady=20, ipady=10)
    entry.focus_set()

    def on_submit():
        nonlocal user_input
        user_input = entry.get()
        input_dialog.destroy()

    entry.bind('<Return>', lambda event: on_submit())
    input_dialog.bind('<Escape>', lambda event: input_dialog.destroy())
    user_input = None
    input_dialog.wait_window(input_dialog)
    return user_input        

if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()
    root.bind('<Escape>', lambda event: close_app(root))

    sector_data = load_sector_data('/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json')
    compare_data = load_compare_data('/Users/yanzhang/Documents/News/backup/Compare_All.txt')
    shares = load_compare_data('/Users/yanzhang/Documents/News/backup/Shares.txt')
    fullnames = load_compare_data('/Users/yanzhang/Documents/News/backup/symbol_names.txt')
    marketcap_pe_data = load_marketcap_pe_data('/Users/yanzhang/Documents/News/backup/marketcap_pe.txt')
    json_data = load_json_data('/Users/yanzhang/Documents/Financial_System/Modules/Description.json')
    db_path = '/Users/yanzhang/Documents/Database/Finance.db'

    input_mapping(root, sector_data, compare_data, shares, fullnames, marketcap_pe_data, json_data, db_path)
    root.mainloop()