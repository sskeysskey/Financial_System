import cv2
import re
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
    # 使用PIL的ImageGrab直接截取屏幕
    screenshot = ImageGrab.grab()
    # 将截图对象转换为OpenCV格式
    screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    return screenshot

# 查找图片
def find_image_on_screen(template, threshold=0.9):
    screen = capture_screen()
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    # 释放截图和模板图像以节省内存
    del screen
    if max_val >= threshold:
        return max_loc, template.shape
    else:
        return None, None

def activate_chrome():
    script = '''
    tell application "Google Chrome"
        activate
        delay 0.5
    end tell
    '''
    # 运行AppleScript
    subprocess.run(['osascript', '-e', script])

def load_symbol_names(file_path):
    symbol_names = {}
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for line in lines:
            if ': ' in line:
                symbol, name = line.strip().split(': ', 1)
                symbol_names[symbol] = name
    return symbol_names

def add_stock(symbol, entry, data, json_file, description1, description2, root, symbol_names):
    tags = entry.get().split()
    stock_name = symbol_names.get(symbol, "")
    new_stock = {
        "symbol": symbol,
        "name": stock_name,
        "tag": tags,
        "description1": description1,
        "description2": description2
    }
    data["stocks"].append(new_stock)
    with open(json_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
    root.destroy()

def on_key_press(event, symbol, entry, data, json_file, description1, description2, root, symbol_names):
    if event.keysym == 'Escape':
        root.destroy()
    elif event.keysym == 'Return':
        add_stock(symbol, entry, data, json_file, description1, description2, root, symbol_names)

json_file = "/Users/yanzhang/Documents/Financial_System/Modules/Description.json"
symbol_name_file = "/Users/yanzhang/Documents/News/backup/symbol_names.txt"
symbol_names = load_symbol_names(symbol_name_file)

with open(json_file, 'r', encoding='utf-8') as file:
    data = json.load(file)

# 从剪贴板获取第一个新的name字段内容
new_name = pyperclip.paste()
# 去除新name的所有引号
new_name = new_name.replace('"', '').replace("'", "")

# 判断是否全是大写英文字母或由大写和-组成，比如：BF-B
# if not new_name.isupper() or not new_name.isalpha():
if not re.match("^[A-Z\-]+$", new_name):
    messagebox.showerror("错误", "不是股票代码！")
    sys.exit()

# 检查新的name是否已存在于stocks中
exists = any(stock['symbol'] == new_name for stock in data.get('stocks', []))

if exists:
    messagebox.showerror("错误", "股票代码已存在！")
    sys.exit()
else:
    # 调用函数激活Google Chrome
    activate_chrome()
    template_paths = {
        "poesuccess": "/Users/yanzhang/Documents/python_code/Resource/poe_copy_success.png",
        "poethumb": "/Users/yanzhang/Documents/python_code/Resource/poe_thumb.png",
        "kimicopy": "/Users/yanzhang/Documents/python_code/Resource/Kimi_copy.png",
        "xinghuocopy": "/Users/yanzhang/Documents/python_code/Resource/xinghuo_copy.png",
        "poecopy": "/Users/yanzhang/Documents/python_code/Resource/poe_copy.png",
    }

    # 读取所有模板图片，并存储在字典中
    templates = {}
    for key, path in template_paths.items():
        template = cv2.imread(path, cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(f"模板图片未能正确读取于路径 {path}")
        templates[key] = template

    found_poe = False
    location, shape = find_image_on_screen(templates["poethumb"])
    if location:
        found_poe = True
        # 计算中心坐标
        center_x = (location[0] + shape[1] // 2) // 2
        center_y = (location[1] + shape[0] // 2) // 2

        # 调整坐标，假设你已经计算好了需要传递给AppleScript的坐标值
        xCoord = center_x
        yCoord = center_y - 50

        # 使用pyautogui移动鼠标并进行右键点击
        pyautogui.moveTo(xCoord, yCoord)
        pyautogui.click(button='right')
        
        sleep(1)
        location, shape = find_image_on_screen(templates["poecopy"])
        if location:
            # 计算中心坐标
            center_x = (location[0] + shape[1] // 2) // 2
            center_y = (location[1] + shape[0] // 2) // 2
            
            # 鼠标点击中心坐标
            pyautogui.click(center_x, center_y)
            print(f"找到图片位置: {location}")
    else:
        location, shape = find_image_on_screen(templates["kimicopy"])
        if location:
            print("找到copy图了，准备点击copy...")
            # 计算中心坐标
            center_x = (location[0] + shape[1] // 2) // 2
            center_y = (location[1] + shape[0] // 2) // 2
            
            # 鼠标点击中心坐标
            pyautogui.click(center_x, center_y)
        else:
            location, shape = find_image_on_screen(templates["xinghuocopy"])
            if location:
                print("找到copy图了，准备点击copy...")
                # 计算中心坐标
                center_x = (location[0] + shape[1] // 2) // 2
                center_y = (location[1] + shape[0] // 2) // 2

                # 鼠标点击中心坐标
                pyautogui.click(center_x, center_y)

    sleep(1)
    new_description1 = pyperclip.paste()

    # 去除所有的回车换行符和引号
    new_description1 = new_description1.replace('\n', ' ').replace('\r', ' ').replace('"', '').replace("'", "")

    if found_poe:
        script_path = '/Users/yanzhang/Documents/ScriptEditor/Shift2Kimi.scpt'
        try:
            # 将坐标值作为参数传递给AppleScript
            process = subprocess.run(['osascript', script_path], check=True, text=True, stdout=subprocess.PIPE)
            # 输出AppleScript的返回结果
            print(process.stdout.strip())
        except subprocess.CalledProcessError as e:
            # 如果有错误发生，打印错误信息
            print(f"Error running AppleScript: {e}")
        sleep(1)
        location, shape = find_image_on_screen(templates["kimicopy"])
        if location:
            print("找到copy图了，准备点击copy...")
            # 计算中心坐标
            center_x = (location[0] + shape[1] // 2) // 2
            center_y = (location[1] + shape[0] // 2) // 2
            
            modify_x = center_x
            modify_y = center_y

            # 鼠标点击中心坐标
            pyautogui.click(modify_x, modify_y)
        else:
            location, shape = find_image_on_screen(templates["xinghuocopy"])
            if location:
                print("找到copy图了，准备点击copy...")
                # 计算中心坐标
                center_x = (location[0] + shape[1] // 2) // 2
                center_y = (location[1] + shape[0] // 2) // 2

                # 鼠标点击中心坐标
                pyautogui.click(center_x, center_y)
    else:
        script_path = '/Users/yanzhang/Documents/ScriptEditor/Shift2Poe.scpt'
        try:
            # 将坐标值作为参数传递给AppleScript
            process = subprocess.run(['osascript', script_path], check=True, text=True, stdout=subprocess.PIPE)
            # 输出AppleScript的返回结果
            print(process.stdout.strip())
        except subprocess.CalledProcessError as e:
            # 如果有错误发生，打印错误信息
            print(f"Error running AppleScript: {e}")

        location, shape = find_image_on_screen(templates["poethumb"])
        if location:
            found_poe = True
            # 计算中心坐标
            center_x = (location[0] + shape[1] // 2) // 2
            center_y = (location[1] + shape[0] // 2) // 2

            # 调整坐标，假设你已经计算好了需要传递给AppleScript的坐标值
            xCoord = center_x
            yCoord = center_y - 50

            # 使用pyautogui移动鼠标并进行右键点击
            pyautogui.moveTo(xCoord, yCoord)
            pyautogui.click(button='right')
            
            sleep(1)
            location, shape = find_image_on_screen(templates["poecopy"])
            if location:
                # 计算中心坐标
                center_x = (location[0] + shape[1] // 2) // 2
                center_y = (location[1] + shape[0] // 2) // 2
                
                # 鼠标点击中心坐标
                pyautogui.click(center_x, center_y)
                print(f"找到图片位置: {location}")
            
            found_success_image = False
            while not found_success_image:
                location, shape = find_image_on_screen(templates["poesuccess"])
                if location:
                    print("找到poe_copy_success图片，继续执行程序...")
                    found_success_image = True
                sleep(1)  # 每次检测间隔1秒

    new_description2 = pyperclip.paste()

    # 去除所有的回车换行符和引号
    new_description2 = new_description2.replace('\n', ' ').replace('\r', ' ').replace('"', '').replace("'", "")

    root = tk.Tk()
    root.title("Add Stock")
    entry = tk.Entry(root)
    entry.pack()
    entry.focus_set()
    button = tk.Button(root, text="添加 Tags", command=lambda: add_stock(new_name, entry, data, json_file, new_description1, new_description2, root, symbol_names))
    button.pack()
    root.bind('<Key>', lambda event: on_key_press(event, new_name, entry, data, json_file, new_description1, new_description2, root, symbol_names))
    root.mainloop()
    messagebox.showinfo("成功", f"股票 {new_name} 已成功写入！")