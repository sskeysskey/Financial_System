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
    # 由于在显示输入框前已经验证过，这里只需要处理更新操作
    for etf in data["etfs"]:
        if etf["symbol"] == symbol:
            etf["tag"].extend(tag for tag in new_tags if tag not in etf["tag"])
            break
    save_data(data, json_file)
    return True

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
        if add_or_update_etf(symbol, input_tags, data, json_file, symbol_names):
            root.destroy()

def check_symbol_exists(symbol, data):
    """检查symbol是否存在于data中"""
    return any(etf["symbol"] == symbol for etf in data["etfs"])

def show_error_dialog(message):
    """显示错误提示对话框"""
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def main():
    Copy_Command_C()

    json_file = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"
    data = load_data(json_file)
    symbol_name_file = "/Users/yanzhang/Documents/News/backup/ETFs.txt"
    symbol_names = load_symbol_names(symbol_name_file)

    new_name = pyperclip.paste().replace('"', '').replace("'", "")
    
    # 首先验证是否是有效的ETF代码格式
    if not new_name.isupper() or not new_name.isalpha():
        show_error_dialog("不是有效的ETFs代码！")
        sys.exit()
    
    # 然后验证是否存在于description.json中
    if not check_symbol_exists(new_name, data):
        show_error_dialog(f"[{new_name}] 不在现有ETF列表中，请先添加到Description中!")
        sys.exit()

    # 只有通过所有验证才显示输入窗口
    root = tk.Tk()
    root.title("Add or Update ETF")
    
    root.lift()
    root.focus_force()
    
    entry = tk.Entry(root)
    entry.pack()
    entry.focus_set()
    button = tk.Button(root, text="更新ETF标签", 
                      command=lambda: on_key_press(tk.Event(), new_name, entry, data, json_file, root, symbol_names))
    button.pack()
    root.bind('<Key>', lambda event: on_key_press(event, new_name, entry, data, json_file, root, symbol_names))
    root.mainloop()

if __name__ == "__main__":
    main()