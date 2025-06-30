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
    """截取当前屏幕并返回OpenCV格式的图像"""
    screenshot = ImageGrab.grab()
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def find_image_on_screen(template, threshold=0.9):
    """在屏幕上查找模板图片的位置"""
    screen = capture_screen()
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        return max_loc, template.shape
    return None, None

def activate_chrome():
    """使用AppleScript激活Google Chrome浏览器"""
    script = '''
    tell application "Google Chrome"
        activate
        delay 0.5
    end tell
    '''
    subprocess.run(['osascript', '-e', script])

# 新增函数：用于弹出窗口让用户手动输入股票名称
def input_symbol_name():
    """
    弹出一个Tkinter窗口，让用户输入股票名称。
    - 按回车或点击“确定”返回输入的名称。
    - 按Esc或关闭窗口返回空字符串，表示取消操作。
    """
    root = tk.Tk()
    root.title("Input Stock Name")
    root.lift()  # 将窗口提升到顶层
    root.focus_force()  # 强制获取焦点
    
    name_var = tk.StringVar()
    name_entry = tk.Entry(root, textvariable=name_var, width=40) # 增加输入框宽度
    name_entry.pack(padx=10, pady=5)
    name_entry.focus_set()

    # 定义一个内部函数来关闭窗口
    def close_dialog(cancelled=False):
        if cancelled:
            # 如果是取消操作，设置一个标志
            setattr(root, 'cancelled', True)
        root.quit()

    button_frame = tk.Frame(root)
    button_frame.pack(pady=5)
    
    # 只需要退出主循环，把对话框关闭
    ok_button = tk.Button(button_frame, text="确定", command=lambda: close_dialog(False))
    ok_button.pack(side=tk.LEFT, padx=5)

    cancel_button = tk.Button(button_frame, text="取消", command=lambda: close_dialog(True))
    cancel_button.pack(side=tk.LEFT, padx=5)

    root.bind('<Return>', lambda e: close_dialog(False))
    root.bind('<Escape>', lambda e: close_dialog(True))
    root.protocol("WM_DELETE_WINDOW", lambda: close_dialog(True))

    root.mainloop()
    
    cancelled = getattr(root, 'cancelled', False)
    stock_name = name_var.get()
    root.destroy()

    if cancelled:
        return ""   # 如果取消，返回空字符串
    return stock_name

# 修改函数签名：用 stock_name 替换 symbol_names
def add_stock(symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag):
    """将新的股票信息添加到JSON文件中"""
    new_stock = {
        "symbol": symbol,
        "name": stock_name,  # 直接使用传入的 stock_name
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

# 修改函数签名：用 stock_name 替换 symbol_names
def on_key_press(event, symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag):
    """处理键盘事件（回车或Esc）"""
    if event.keysym == 'Escape':
        root.destroy()
    elif event.keysym == 'Return':
        # 更新对 add_stock 的调用
        add_stock(symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag)

def read_clipboard():
    """读取并清理剪贴板内容"""
    return pyperclip.paste().replace('"', '').replace("'", "")

def validate_new_name(new_name):
    """验证剪贴板内容是否为合法的股票代码格式"""
    if not re.match("^[A-Z\-]+$", new_name):
        applescript_code = 'display dialog "不是股票代码！" buttons {"OK"} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
        sys.exit()
    return new_name

def check_stock_exists(data, new_name):
    """检查股票代码是否已存在于JSON文件中"""
    if any(stock['symbol'] == new_name for stock in data.get('stocks', [])):
        # AppleScript代码
        applescript_code = 'display dialog "股票代码已存在！" buttons {"OK"} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
        sys.exit()

def execute_applescript(script_path):
    """执行指定的AppleScript文件"""
    try:
        process = subprocess.run(['osascript', script_path], check=True, text=True, stdout=subprocess.PIPE)
        print(process.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error running AppleScript: {e}")

def main():
    json_file = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"
    
    # 已删除 symbol_name_file 和 load_symbol_names 的调用

    with open(json_file, 'r', encoding='utf-8') as file:
        data = json.load(file)

    new_name = validate_new_name(read_clipboard())
    check_stock_exists(data, new_name)

    # 主要修改点：在这里调用新函数来手动输入股票名称
    stock_name = input_symbol_name()

    # 如果用户取消输入，则退出程序
    if not stock_name:
        applescript_code = 'display dialog "操作已取消，未输入股票名称。" buttons {"OK"} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
        sys.exit()

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

    found_poe = find_and_click("poethumb", 40)
    if found_poe:
        pyautogui.click(button='right')
        sleep(1)
        if find_and_click("poecopy"):
            print("找到图片位置")
    else:
        if find_and_click("kimicopy"):
            print("找到copy图了，准备点击copy...")

    sleep(1)
    new_description1 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    script_path = '/Users/yanzhang/Documents/ScriptEditor/Shift2Kimi.scpt' if found_poe else '/Users/yanzhang/Documents/ScriptEditor/Shift2Poe.scpt'
    execute_applescript(script_path)
    sleep(1)
    if not found_poe:
        found_poe = find_and_click("poethumb", 40)
        if found_poe:
            pyautogui.click(button='right')
            while not find_and_click("poecopy"):
                sleep(1)
            while not find_image("poesuccess"):
                sleep(1)
    else:
        find_and_click("kimicopy")

    new_description2 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    
    # **新增逻辑：比较new_description1和new_description2**
    if new_description1 == new_description2:
        print("new_description1 和 new_description2 一致，将 new_description2 置为空。")
        new_description2 = ""  # 如果一致，将new_description2置为空
    else:
        print("new_description1 和 new_description2 不一致，继续执行原逻辑。")

    if "ETF" in new_description1 and "ETF" in new_description2:
        applescript_code = 'display dialog "要添加的好像是ETF而不是Stock" buttons {"OK"} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
        sys.exit()
    
    root = tk.Tk()
    root.title("Add Stock")

    root.lift()
    root.focus_force()
    
    success_flag = [False]  # 使用列表来传递布尔值
    entry = tk.Entry(root, width=50) # 增加输入框宽度
    entry.pack(padx=10, pady=5)
    entry.focus_set()
    
    # 更新 lambda 函数的调用，传入 stock_name
    button = tk.Button(root, text="添加 Tags", command=lambda: add_stock(new_name, stock_name, entry, data, json_file, new_description1, new_description2, root, success_flag))
    button.pack(pady=5)
    
    # 更新键盘绑定的 lambda 函数，传入 stock_name
    root.bind('<Key>', lambda event: on_key_press(event, new_name, stock_name, entry, data, json_file, new_description1, new_description2, root, success_flag))
    root.mainloop()

    if success_flag[0]:
        applescript_code = 'display dialog "股票已成功写入！" buttons {"OK"} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    else:
        applescript_code = 'display dialog "操作已取消，未进行任何写入。" buttons {"OK"} default button "OK"'
        subprocess.run(['osascript', '-e', applescript_code], check=True)

if __name__ == "__main__":
    main()