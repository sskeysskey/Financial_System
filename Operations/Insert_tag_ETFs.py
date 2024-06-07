import json
import tkinter as tk
from tkinter import messagebox
import pyperclip
import sys
import subprocess

def add_etf(name, entry, data, json_file, root):
    tags = entry.get().split()
    new_etf = {
        "name": name,
        "tag": tags,
        "description1": "",
        "description2": ""
    }
    data["etfs"].append(new_etf)
    with open(json_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
    root.destroy()

def Copy_Command_C():
        script = '''
        tell application "System Events"
            keystroke "c" using command down
        end tell
        '''
        # 运行AppleScript
        subprocess.run(['osascript', '-e', script])

def on_key_press(event, name, entry, data, json_file, root):
    if event.keysym == 'Escape':
        root.destroy()
    elif event.keysym == 'Return':
        add_etf(name, entry, data, json_file, root)

def main():
    Copy_Command_C()

    json_file = "/Users/yanzhang/Documents/Financial_System/Modules/Description.json"
    with open(json_file, encoding="utf-8") as file:
        data = json.load(file)

    new_name = pyperclip.paste().replace('"', '').replace("'", "")
    if not new_name.isupper() or not new_name.isalpha():
        messagebox.showerror("错误", "不是有效的ETFs代码！")
        sys.exit()

    if any(etf['name'] == new_name for etf in data.get('etfs', [])):
        messagebox.showerror("错误", "ETF代码已存在！")
        sys.exit()

    root = tk.Tk()
    root.title("Add ETF")
    entry = tk.Entry(root)
    entry.pack()
    entry.focus_set()
    button = tk.Button(root, text="添加ETF", command=lambda: add_etf(new_name, entry, data, json_file, root))
    button.pack()
    root.bind('<Key>', lambda event: on_key_press(event, new_name, entry, data, json_file, root))
    root.mainloop()

if __name__ == "__main__":
    main()