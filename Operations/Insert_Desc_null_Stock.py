import cv2
import re
import json
import pyperclip
import pyautogui
import numpy as np
import time
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

def input_symbol_name():
    root = tk.Tk()
    root.title("Input Stock Name")
    root.lift()  # 将窗口提升到顶层
    root.focus_force()  # 强制获取焦点
    
    name_var = tk.StringVar()
    name_entry = tk.Entry(root, textvariable=name_var)
    name_entry.pack()
    name_entry.focus_set()

    # 只需要退出主循环，把对话框关闭
    button = tk.Button(root, text="确定", command=root.quit)
    button.pack()

    root.bind('<Return>', lambda e: root.quit())
    root.bind('<Escape>', lambda e: setattr(root, 'cancelled', True) or root.quit())
    root.protocol("WM_DELETE_WINDOW", lambda: setattr(root, 'cancelled', True) or root.quit())

    root.mainloop()
    cancelled = getattr(root, 'cancelled', False)
    stock_name = name_var.get()
    root.destroy()

    if cancelled:
        return ""   # 或者你想要的其它“取消”信号
    return stock_name

def input_tags(symbol, stock_name, data, json_file, description1, description2):
    root = tk.Tk()
    root.title("Add Stock Tags")
    root.lift()
    root.focus_force()
    
    success_flag = [False]
    entry = tk.Entry(root)
    entry.pack()
    entry.focus_set()
    button = tk.Button(root, text="添加 Tags", command=lambda: add_stock(symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag))
    button.pack()
    root.bind('<Key>', lambda event: on_key_press(event, symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag))
    root.mainloop()
    return success_flag[0]

def add_stock(symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag):
    new_stock = {
        "symbol": symbol,
        "name": stock_name,
        "tag": entry.get().split(),
        "description1": description1,
        "description2": description2,
        "value": ""
    }
    data["stocks"].append(new_stock)
    with open(json_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
    success_flag[0] = True  # 设置成功标志位
    root.destroy()

def on_key_press(event, symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag):
    if event.keysym == 'Escape':
        root.destroy()
    elif event.keysym == 'Return':
        add_stock(symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag)

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
    json_file = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"

    with open(json_file, 'r', encoding='utf-8') as file:
        data = json.load(file)

    new_name = validate_new_name(read_clipboard())
    check_stock_exists(data, new_name)

    activate_chrome()
    template_paths = {
        "poesuccess": "/Users/yanzhang/Documents/python_code/Resource/poe_copy_success.png",
        "poethumb": "/Users/yanzhang/Documents/python_code/Resource/poe_thumb.png",
        "kimicopy": "/Users/yanzhang/Documents/python_code/Resource/Kimi_copy.png",
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

    found_poe = find_and_click("poethumb", 80)
    if found_poe:
        pyautogui.click(button='right')
        time.sleep(1)
        if find_and_click("poecopy"):
            print("找到图片位置")
    else:
        if find_and_click("kimicopy"):
            print("找到copy图了，准备点击copy...")

    time.sleep(1)
    new_description1 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    script_path = '/Users/yanzhang/Documents/ScriptEditor/Shift2Kimi.scpt' if found_poe else '/Users/yanzhang/Documents/ScriptEditor/Shift2Poe.scpt'
    execute_applescript(script_path)
    time.sleep(1)
    if not found_poe:
        found_poe = find_and_click("poethumb", 80)
        if found_poe:
            pyautogui.click(button='right')
            while not find_and_click("poecopy"):
                time.sleep(1)
            while not find_image("poesuccess"):
                time.sleep(1)
    else:
        find_and_click("kimicopy")

    new_description2 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    
    # 弹出输入 symbol_name 的窗口
    stock_name = input_symbol_name()

    if stock_name == "":
        applescript_code = 'display dialog "操作已取消，股票名称将被设置为空字符串。" buttons {"OK"} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
        # 不再提前退出函数，而是继续执行，使用空字符串作为 stock_name

    # 弹出输入 tags 的窗口
    success = input_tags(new_name, stock_name, data, json_file, new_description1, new_description2)

    if success:
        applescript_code = 'display dialog "股票已成功写入！" buttons {"OK"} default button "OK"'
    else:
        applescript_code = 'display dialog "操作已取消，未进行任何写入。" buttons {"OK"} default button "OK"'
    
    subprocess.run(['osascript', '-e', applescript_code], check=True)

if __name__ == "__main__":
    main()