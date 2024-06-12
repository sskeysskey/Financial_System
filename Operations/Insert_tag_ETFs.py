import json
import tkinter as tk
from tkinter import messagebox
import pyperclip
import sys
import subprocess

def load_data(file_path):
    with open(file_path, encoding="utf-8") as file:
        return json.load(file)

def save_data(data, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def add_or_update_etf(name, new_tags, data, json_file):
    etf_exists = False
    for etf in data["etfs"]:
        if etf["name"] == name:
            etf_exists = True
            etf["tag"].extend(tag for tag in new_tags if tag not in etf["tag"])
            break
    if not etf_exists:
        new_etf = {
            "name": name,
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

def on_key_press(event, name, entry, data, json_file, root):
    if event.keysym == 'Escape':
        root.destroy()
    elif event.keysym == 'Return':
        input_tags = entry.get().split()
        add_or_update_etf(name, input_tags, data, json_file)
        root.destroy()

def main():
    Copy_Command_C()

    json_file = "/Users/yanzhang/Documents/Financial_System/Modules/Description.json"
    data = load_data(json_file)

    new_name = pyperclip.paste().replace('"', '').replace("'", "")
    if not new_name.isupper() or not new_name.isalpha():
        messagebox.showerror("错误", "不是有效的ETFs代码！")
        sys.exit()

    root = tk.Tk()
    root.title("Add or Update ETF")
    entry = tk.Entry(root)
    entry.pack()
    entry.focus_set()
    button = tk.Button(root, text="添加或更新ETF", command=lambda: on_key_press('Return', new_name, entry, data, json_file, root))
    button.pack()
    root.bind('<Key>', lambda event: on_key_press(event, new_name, entry, data, json_file, root))
    root.mainloop()

if __name__ == "__main__":
    main()