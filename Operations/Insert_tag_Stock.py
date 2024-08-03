import re
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

def add_stock(name, new_tags, data):
    for stock in data["stocks"]:
        if stock["symbol"] == name:
            stock["tag"].extend(tag for tag in new_tags if tag not in stock["tag"])
            break

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
        add_stock(name, input_tags, data)
        save_data(data, json_file)
        root.destroy()

def main():
    Copy_Command_C()

    json_file = "/Users/yanzhang/Documents/Financial_System/Modules/Description.json"
    data = load_data(json_file)

    new_name = pyperclip.paste().replace('"', '').replace("'", "")
    if not re.match("^[A-Z\-]+$", new_name) or not any(stock['symbol'] == new_name for stock in data['stocks']):
        applescript_code = 'display dialog "不是有效的股票代码或股票代码不存在！" buttons {"OK"} default button "OK"'
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)
        sys.exit()

    root = tk.Tk()
    root.title("Add Tags")
    
    root.lift()
    root.focus_force()
    
    entry = tk.Entry(root)
    entry.pack()
    entry.focus_set()
    button = tk.Button(root, text="添加tag", command=lambda: on_key_press('Return', new_name, entry, data, json_file, root))
    button.pack()
    root.bind('<Key>', lambda event: on_key_press(event, new_name, entry, data, json_file, root))
    root.mainloop()

if __name__ == "__main__":
    main()