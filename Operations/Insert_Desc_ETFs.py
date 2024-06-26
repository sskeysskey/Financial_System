import cv2
import json
import pyperclip
import pyautogui
import numpy as np
from time import sleep
from PIL import ImageGrab
import tkinter as tk
from tkinter import messagebox
import sys
import subprocess

def capture_screen():
    screenshot = ImageGrab.grab()
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def find_image_on_screen(template, threshold=0.9):
    screen = capture_screen()
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        return max_loc, template.shape
    return None, None

def activate_chrome():
    script = '''
    tell application "Google Chrome"
        activate
        delay 0.5
    end tell
    '''
    subprocess.run(['osascript', '-e', script], check=True)

def load_symbol_names(file_paths):
    symbol_names = {}
    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    if ': ' in line:
                        symbol, name = line.strip().split(': ', 1)
                        symbol_names[symbol] = name
        except FileNotFoundError:
            print(f"文件未找到: {file_path}，将忽略。")
    return symbol_names

def add_or_update_etf(symbol, entry, data, json_file, description1, description2, root, symbol_names):
    etf_name = symbol_names.get(symbol, "")
    existing_etf = next((etf for etf in data["etfs"] if etf["symbol"] == symbol), None)
    if existing_etf:
        # 更新已有的ETF
        if "description1" in existing_etf and not existing_etf["description1"]:
            existing_etf["description1"] = description1
        if "description2" in existing_etf and not existing_etf["description2"]:
            existing_etf["description2"] = description2
        existing_etf["tag"].extend(entry.get().split())
    else:
        # 添加新的ETF
        new_etf = {
            "symbol": symbol,
            "name": etf_name,
            "tag": entry.get().split(),
            "description1": description1,
            "description2": description2
        }
        data["etfs"].append(new_etf)
    
    with open(json_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
    root.destroy()

def on_key_press(event, symbol, entry, data, json_file, description1, description2, root, symbol_names):
    if event.keysym == 'Escape':
        root.destroy()
    elif event.keysym == 'Return':
        add_or_update_etf(symbol, entry, data, json_file, description1, description2, root, symbol_names)

def read_clipboard():
    return pyperclip.paste().replace('"', '').replace("'", "")

def validate_new_name(new_name):
    # 判断是否全是大写英文字母
    if not new_name.isupper() or not new_name.isalpha():
        messagebox.showerror("错误", "不是ETFs代码！")
        sys.exit()
    return new_name

def check_etf_exists(data, new_name):
    existing_etf = next((etf for etf in data.get('etfs', []) if etf['symbol'] == new_name), None)
    if existing_etf:
        if not existing_etf['description1'] and not existing_etf['description2']:
            return existing_etf
        else:
            messagebox.showerror("错误", "股票代码已存在且描述已存在！")
            sys.exit()
    return None

def execute_applescript(script_path):
    try:
        process = subprocess.run(['osascript', script_path], check=True, text=True, stdout=subprocess.PIPE)
        print(process.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error running AppleScript: {e}")

def main():
    json_file = "/Users/yanzhang/Documents/Financial_System/Modules/Description.json"
    symbol_name_file1 = "/Users/yanzhang/Documents/News/backup/ETFs.txt"
    symbol_name_file2 = "/Users/yanzhang/Documents/News/ETFs_new.txt"
    symbol_names = load_symbol_names([symbol_name_file1, symbol_name_file2])

    with open(json_file, 'r', encoding='utf-8') as file:
        data = json.load(file)

    new_name = validate_new_name(read_clipboard())
    existing_etf = check_etf_exists(data, new_name)

    activate_chrome()
    template_paths = {
        "poesuccess": "/Users/yanzhang/Documents/python_code/Resource/poe_copy_success.png",
        "poethumb": "/Users/yanzhang/Documents/python_code/Resource/poe_thumb.png",
        "kimicopy": "/Users/yanzhang/Documents/python_code/Resource/Kimi_copy.png",
        "xinghuocopy": "/Users/yanzhang/Documents/python_code/Resource/xinghuo_copy.png",
        "poecopy": "/Users/yanzhang/Documents/python_code/Resource/poe_copy.png",
    }
    templates = {key: cv2.imread(path, cv2.IMREAD_COLOR) for key, path in template_paths.items()}

    def find_and_click(template_key, offset_y=0):
        location, shape = find_image_on_screen(templates[template_key])
        if location:
            center_x = (location[0] + shape[1] // 2) // 2
            center_y = (location[1] + shape[0] // 2) // 2 - offset_y
            pyautogui.click(center_x, center_y)
            return True
        return False

    def find_image(template_key):
        location, _ = find_image_on_screen(templates[template_key])
        return location is not None

    found_poe = find_and_click("poethumb", 50)
    if found_poe:
        pyautogui.click(button='right')
        sleep(1)
        if find_and_click("poecopy"):
            print("找到图片位置")
    else:
        if find_and_click("kimicopy") or find_and_click("xinghuocopy"):
            print("找到copy图了，准备点击copy...")

    sleep(1)
    new_description1 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    script_path = '/Users/yanzhang/Documents/ScriptEditor/Shift2Kimi.scpt' if found_poe else '/Users/yanzhang/Documents/ScriptEditor/Shift2Poe.scpt'
    execute_applescript(script_path)
    sleep(1)
    if not found_poe:
        found_poe = find_and_click("poethumb", 50)
        if found_poe:
            pyautogui.click(button='right')
            while not find_and_click("poecopy"):
                sleep(1)
            while not find_image("poesuccess"):
                sleep(1)
    else:
        find_and_click("kimicopy") or find_and_click("xinghuocopy")

    new_description2 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    
    root = tk.Tk()
    root.title("Add ETF")
    entry = tk.Entry(root)
    entry.pack()
    entry.focus_set()
    button = tk.Button(root, text="添加 Tags", command=lambda: add_or_update_etf(new_name, entry, data, json_file, new_description1, new_description2, root, symbol_names))
    button.pack()
    root.bind('<Key>', lambda event: on_key_press(event, new_name, entry, data, json_file, new_description1, new_description2, root, symbol_names))
    root.mainloop()
    messagebox.showinfo("成功", f"股票 {new_name} 已成功写入！")

if __name__ == "__main__":
    main()