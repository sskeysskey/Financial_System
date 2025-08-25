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

# 规则1：删除 [[数字]](http/https…)
RE_CITATION = re.compile(r'[[\d+]]\(https?://[^)\s]+[^)]*\)', flags=re.IGNORECASE)

# 规则2：匹配中文字符（基本汉字区）。若需要也可扩展至更多区段。
RE_FIRST_CJK = re.compile(r'[\u4e00-\u9fff]')

# 规则3：删除圆括号包裹的 URL：
# 说明：允许括号内包含任意非右括号字符，跨空格与参数，尽量不跨越右括号
RE_PAREN_URL = re.compile(r'\(\s*https?://[^)]+\)', flags=re.IGNORECASE)

# 规则4：删除裸 URL：以 http(s):// 开始，直到遇到空白或分隔符（常见标点/括号等）
# 采用较保守的终止符，避免吞掉后续自然语言字符
RE_BARE_URL = re.compile(
    r'https?://[^\s\)]\}\>,\'"；；，，。、“”‘’（）()<>]+',
    flags=re.IGNORECASE
)

def clean_string_value(s: str) -> str:
    """
    清理单个字符串值（顺序有意安排以减少相互影响）：
    1) 删除形如 [[数字]](http/https...) 的引用片段；
    2) 删除圆括号包裹的 URL，如：；
    3) 删除裸 URL，如：https://example.com/...
    4) 若出现 '*Thinking...*'，从其位置起删除到后续出现的第一个中文字符（中文保留）；
       - 若之后没有中文，则从 '*Thinking...*' 起删到字符串末尾。
    5) 若出现 '--- Learn more:'，从该短语起截断到字符串末尾。
    """
    # 1) 删除 [[数字]](http/https...)
    s = RE_CITATION.sub('', s)

    # 2) 删除形如  的整体（含括号）
    s = RE_PAREN_URL.sub('', s)

    # 3) 删除裸 URL
    s = RE_BARE_URL.sub('', s)

    # 4) 处理 '*Thinking...*' -> 删除至第一个中文字符（中文保留）
    thinking_idx = s.find('*Thinking...*')
    if thinking_idx != -1:
        # 从 thinking 段落之后寻找第一个中文字符
        after = s[thinking_idx + len('*Thinking...*'):]
        m = RE_FIRST_CJK.search(after)
        if m:
            # 保留中文及其后内容，丢弃 '*Thinking...*' 到该中文之前
            cut_pos = thinking_idx + len('*Thinking...*') + m.start()
            s = s[:thinking_idx] + s[cut_pos:]
        else:
            # 没有中文，安全删除从 '*Thinking...*' 到末尾
            s = s[:thinking_idx]

    # 5) 截断 '--- Learn more:'（精确匹配）
    lm_idx = s.find('--- Learn more:')
    if lm_idx != -1:
        s = s[:lm_idx]

    return s.strip() # 返回时顺便去除首尾空白

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
    json_file = "/Users/yanzhang/Coding/Financial_System/Modules/description.json"

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
        "poesuccess": "/Users/yanzhang/Coding/python_code/Resource/poe_copy_success.png",
        "poethumb": "/Users/yanzhang/Coding/python_code/Resource/poe_thumb.png",
        "kimicopy": "/Users/yanzhang/Coding/python_code/Resource/Kimi_copy.png",
        "poecopy": "/Users/yanzhang/Coding/python_code/Resource/poe_copy.png",
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
    
    # <-- 修改点：读取并清理第一个描述 -->
    raw_description1 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    new_description1 = clean_string_value(raw_description1)
    print(f"清理后的 Description 1: {new_description1}")
    
    script_path = '/Users/yanzhang/Coding/ScriptEditor/Shift2Kimi.scpt' if found_poe else '/Users/yanzhang/Coding/ScriptEditor/Shift2Poe.scpt'
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

    # <-- 修改点：读取并清理第二个描述 -->
    raw_description2 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    new_description2 = clean_string_value(raw_description2)
    print(f"清理后的 Description 2: {new_description2}")
    
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