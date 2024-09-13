import json
import tkinter as tk
import pyperclip
import sys
import subprocess

def load_data(file_path):
    with open(file_path, encoding="utf-8") as file:
        return json.load(file)

def save_data(data, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def load_symbol_names(file_path):
    symbol_names = {}
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for line in lines:
            if ': ' in line:
                symbol, name = line.strip().split(': ', 1)
                symbol_names[symbol] = name
    return symbol_names

def add_or_update_etf(symbol, new_tags, data, json_file, symbol_names):
    etf_exists = False
    for etf in data["etfs"]:
        if etf["symbol"] == symbol:
            etf_exists = True
            etf["tag"].extend(tag for tag in new_tags if tag not in etf["tag"])
            break
    if not etf_exists:
        etf_name = symbol_names.get(symbol, "")
        new_etf = {
            "symbol": symbol,
            "name": etf_name,
            "tag": new_tags,
            "description1": "",
            "description2": ""
        }
        data["etfs"].append(new_etf)
    save_data(data, json_file)

def Copy_Command_C():
    script = '''
    tell application "System Events"
        keystroke "c" using command down
    end tell
    '''
    subprocess.run(['osascript', '-e', script])

def on_key_press(event, symbol, entry, data, json_file, root, symbol_names):
    if event.keysym == 'Escape':
        root.destroy()
    elif event.keysym == 'Return':
        input_tags = entry.get().split()
        add_or_update_etf(symbol, input_tags, data, json_file, symbol_names)
        root.destroy()

def main():
    Copy_Command_C()

    json_file = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"
    data = load_data(json_file)
    symbol_name_file = "/Users/yanzhang/Documents/News/backup/ETFs.txt"
    symbol_names = load_symbol_names(symbol_name_file)

    new_name = pyperclip.paste().replace('"', '').replace("'", "")
    if not new_name.isupper() or not new_name.isalpha():
        # AppleScript代码
        applescript_code = 'display dialog "不是有效的ETFs代码！" buttons {"OK"} default button "OK"'
        # 使用subprocess调用osascript
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)
        sys.exit()

    root = tk.Tk()
    root.title("Add or Update ETF")
    
    root.lift()
    root.focus_force()
    
    entry = tk.Entry(root)
    entry.pack()
    entry.focus_set()
    button = tk.Button(root, text="添加或更新ETF", command=lambda: on_key_press(tk.Event(), new_name, entry, data, json_file, root, symbol_names))
    button.pack()
    root.bind('<Key>', lambda event: on_key_press(event, new_name, entry, data, json_file, root, symbol_names))
    root.mainloop()

if __name__ == "__main__":
    main()