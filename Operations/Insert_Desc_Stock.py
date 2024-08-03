import cv2
import re
import json
import pyperclip
import pyautogui
import numpy as np
from time import sleep
from PIL import ImageGrab
import tkinter as tk
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
    subprocess.run(['osascript', '-e', script])

def load_symbol_names(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return dict(line.strip().split(': ', 1) for line in file if ': ' in line)

def add_stock(symbol, entry, data, json_file, description1, description2, root, symbol_names, success_flag):
    stock_name = symbol_names.get(symbol, "")
    new_stock = {
        "symbol": symbol,
        "name": stock_name,
        "tag": entry.get().split(),
        "description1": description1,
        "description2": description2
    }
    data["stocks"].append(new_stock)
    with open(json_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
    success_flag[0] = True  # 设置成功标志位
    root.destroy()

def on_key_press(event, symbol, entry, data, json_file, description1, description2, root, symbol_names, success_flag):
    if event.keysym == 'Escape':
        root.destroy()
    elif event.keysym == 'Return':
        add_stock(symbol, entry, data, json_file, description1, description2, root, symbol_names, success_flag)

def read_clipboard():
    return pyperclip.paste().replace('"', '').replace("'", "")

def validate_new_name(new_name):
    if not re.match("^[A-Z\-]+$", new_name):
        # AppleScript代码
        applescript_code = 'display dialog "不是股票代码！" buttons {"OK"} default button "OK"'
        # 使用subprocess调用osascript
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)
        sys.exit()
    return new_name

def check_stock_exists(data, new_name):
    if any(stock['symbol'] == new_name for stock in data.get('stocks', [])):
        # AppleScript代码
        applescript_code = 'display dialog "股票代码已存在！" buttons {"OK"} default button "OK"'
        # 使用subprocess调用osascript
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)
        sys.exit()

def execute_applescript(script_path):
    try:
        process = subprocess.run(['osascript', script_path], check=True, text=True, stdout=subprocess.PIPE)
        print(process.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error running AppleScript: {e}")

def main():
    json_file = "/Users/yanzhang/Documents/Financial_System/Modules/Description.json"
    symbol_name_file = "/Users/yanzhang/Documents/News/backup/symbol_names.txt"
    symbol_names = load_symbol_names(symbol_name_file)

    with open(json_file, 'r', encoding='utf-8') as file:
        data = json.load(file)

    new_name = validate_new_name(read_clipboard())
    check_stock_exists(data, new_name)

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
        location, shape = find_image_on_screen(templates[template_key])
        if location:
            return True
        return False

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
    
    if "ETF" in new_description1 and "ETF" in new_description2:
        # AppleScript代码
        applescript_code = 'display dialog "要添加的好像是ETF而不是Stock" buttons {"OK"} default button "OK"'
        # 使用subprocess调用osascript
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)
        sys.exit()
    
    root = tk.Tk()
    root.title("Add Stock")

    root.lift()
    root.focus_force()
    
    success_flag = [False]  # 使用列表来传递布尔值
    entry = tk.Entry(root)
    entry.pack()
    entry.focus_set()
    button = tk.Button(root, text="添加 Tags", command=lambda: add_stock(new_name, entry, data, json_file, new_description1, new_description2, root, symbol_names, success_flag))
    button.pack()
    root.bind('<Key>', lambda event: on_key_press(event, new_name, entry, data, json_file, new_description1, new_description2, root, symbol_names, success_flag))
    root.mainloop()

    if success_flag[0]:
        # AppleScript代码
        applescript_code = 'display dialog "股票已成功写入！" buttons {"OK"} default button "OK"'
        # 使用subprocess调用osascript
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)
    else:
        # AppleScript代码
        applescript_code = 'display dialog "操作已取消，未进行任何写入。" buttons {"OK"} default button "OK"'
        # 使用subprocess调用osascript
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)

if __name__ == "__main__":
    main()