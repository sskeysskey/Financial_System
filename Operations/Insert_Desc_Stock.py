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
from tkinter import simpledialog

# -----------------------
# 正则表达式（修复了警告与健壮性）
# -----------------------

# 规则1：删除 [[数字]](http/https…)
# 修复“Possible nested set”警告，并更严谨地匹配：
# - [[ 数字 ]] 之间允许1个或多个数字
# - 紧随其后是 (http(s)://... ) 的一对圆括号
RE_CITATION = re.compile(
    r'\[\[\d+\]\]\(\s*https?://[^)\s]+[^)]*\)',
    flags=re.IGNORECASE
)

# 规则2：匹配中文字符（基本汉字区）。若需要也可扩展至更多区段。
RE_FIRST_CJK = re.compile(r'[\u4e00-\u9fff]')

# 规则3：删除圆括号包裹的 URL：
RE_PAREN_URL = re.compile(r'\(\s*https?://[^)]+\)', flags=re.IGNORECASE)

# 规则4：删除裸 URL：以 http(s):// 开始，直到遇到空白或常见分隔符
# 注意：字符类内不要形成范围或不对称引号，避免解析问题
RE_BARE_URL = re.compile(
    r'https?://[^\s\)\}\>,\'"；，。、“”‘’（）()<>\[\]]+',
    flags=re.IGNORECASE
)

def clean_string_value(s: str) -> str:
    """
    清理单个字符串值（顺序有意安排以减少相互影响）：
    1) 删除形如 [[数字]](http/https...) 的引用片段；
    2) 删除圆括号包裹的 URL；
    3) 删除裸 URL；
    4) 若出现 '*Thinking...*'，从其位置起删除到后续出现的第一个中文字符（中文保留）；
       - 若之后没有中文，则从 '*Thinking...*' 起删到字符串末尾。
    5) 若出现 '--- Learn more:'，从该短语起截断到字符串末尾。
    """
    if not isinstance(s, str):
        return ""

    # 1) 删除 [[数字]](http/https...)
    s = RE_CITATION.sub('', s)

    # 2) 删除形如 (https://...) 的整体（含括号）
    s = RE_PAREN_URL.sub('', s)

    # 3) 删除裸 URL
    s = RE_BARE_URL.sub('', s)

    # 4) 处理 '*Thinking...*'
    thinking_token = '*Thinking...*'
    thinking_idx = s.find(thinking_token)
    if thinking_idx != -1:
        after = s[thinking_idx + len(thinking_token):]
        m = RE_FIRST_CJK.search(after)
        if m:
            cut_pos = thinking_idx + len(thinking_token) + m.start()
            s = s[:thinking_idx] + s[cut_pos:]
        else:
            s = s[:thinking_idx]

    # 5) 截断 '--- Learn more:'
    lm_idx = s.find('--- Learn more:')
    if lm_idx != -1:
        s = s[:lm_idx]

    return s.strip()

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

def show_applescript_dialog(message: str):
    """显示简单的 AppleScript 对话框"""
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    try:
        subprocess.run(['osascript', '-e', applescript_code], check=True)
    except Exception:
        # 兜底用 Tkinter
        root = tk.Tk()
        root.withdraw()
        simpledialog.messagebox.showinfo("提示", message)
        root.destroy()

def input_with_dialog(title: str, prompt: str, initial_value: str = "") -> str:
    """
    使用 Tkinter 弹窗获取用户输入。
    返回：用户输入的字符串；若取消或关闭窗口返回空字符串。
    """
    root = tk.Tk()
    root.title(title)
    root.withdraw()
    # 使用简单输入对话框
    value = simpledialog.askstring(title, prompt, initialvalue=initial_value, parent=root)
    root.destroy()
    return value or ""

# 保留你原来的“输入股票名称”的专用函数（升级顶置与取消逻辑）
def input_symbol_name():
    """
    弹出一个Tkinter窗口，让用户输入股票名称。
    - 按回车或点击“确定”返回输入的名称。
    - 按Esc或关闭窗口返回空字符串，表示取消操作。
    """
    root = tk.Tk()
    root.title("Input Stock Name")
    root.lift()
    root.focus_force()

    name_var = tk.StringVar()
    name_entry = tk.Entry(root, textvariable=name_var, width=40)
    name_entry.pack(padx=10, pady=5)
    name_entry.focus_set()

    def close_dialog(cancelled=False):
        if cancelled:
            setattr(root, 'cancelled', True)
        root.quit()

    button_frame = tk.Frame(root)
    button_frame.pack(pady=5)

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
        return ""
    return stock_name

# 修改函数签名：用 stock_name 替换 symbol_names
def add_stock(symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag):
    """将新的股票信息添加到JSON文件中"""
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
    success_flag[0] = True
    root.destroy()

def on_key_press(event, symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag):
    """处理键盘事件（回车或Esc）"""
    if event.keysym == 'Escape':
        root.destroy()
    elif event.keysym == 'Return':
        add_stock(symbol, stock_name, entry, data, json_file, description1, description2, root, success_flag)

# 读取剪贴板（修复 None 问题，加入异常捕获）
def read_clipboard():
    """读取并清理剪贴板内容（可能返回空字符串）"""
    try:
        content = pyperclip.paste()
    except Exception:
        content = None
    if content is None:
        return ""
    return str(content).replace('"', '').replace("'", "")

# 验证股票代码（修复 '\-' 警告；支持 A-Z 与 '-'）
SYMBOL_PATTERN = re.compile(r'^[A-Z\-]+$')  # 将 '-' 放在类末尾，且用原始字符串

def validate_new_name(new_name):
    """验证是否为合法股票代码格式"""
    return bool(SYMBOL_PATTERN.match(new_name))

def check_stock_exists(data, new_name):
    """检查股票代码是否已存在于JSON文件中"""
    if any(stock.get('symbol') == new_name for stock in data.get('stocks', [])):
        show_applescript_dialog("股票代码已存在！")
        sys.exit()

def execute_applescript(script_path):
    """执行指定的AppleScript文件"""
    try:
        process = subprocess.run(['osascript', script_path], check=True, text=True, stdout=subprocess.PIPE)
        print(process.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error running AppleScript: {e}")

def safe_read_clipboard_or_prompt_symbol():
    """
    从剪贴板读取股票代码；若无效或为空，则弹出对话框要求用户手动输入；
    若输入仍不合法，继续循环；用户取消则退出。
    """
    # 第一次尝试从剪贴板
    candidate = read_clipboard().strip().upper()
    if not validate_new_name(candidate):
        # 弹窗循环请求输入
        while True:
            user_input = input_with_dialog("输入股票代码", "请输入股票代码（仅大写字母和-）：", candidate)
            if not user_input:
                show_applescript_dialog("操作已取消，未输入股票代码。")
                sys.exit()
            candidate = user_input.strip().upper()
            if validate_new_name(candidate):
                break
            else:
                show_applescript_dialog("不是股票代码！请重新输入（仅大写字母和-）。")
    return candidate

def main():
    json_file = "/Users/yanzhang/Coding/Financial_System/Modules/description.json"

    with open(json_file, 'r', encoding='utf-8') as file:
        data = json.load(file)

    # 安全地获取股票代码：剪贴板异常或不合规时转为手工输入
    new_name = safe_read_clipboard_or_prompt_symbol()
    check_stock_exists(data, new_name)

    # 让用户输入股票名称（保留原有对话框交互）
    stock_name = input_symbol_name()
    if not stock_name:
        show_applescript_dialog("操作已取消，未输入股票名称。")
        sys.exit()

    activate_chrome()
    template_paths = {
        "poesuccess": "/Users/yanzhang/Coding/python_code/Resource/poe_copy_success.png",
        "poethumb": "/Users/yanzhang/Coding/python_code/Resource/poe_thumb.png",
        "kimicopy": "/Users/yanzhang/Coding/python_code/Resource/doubao_copy.png",
        "poecopy": "/Users/yanzhang/Coding/python_code/Resource/poe_copy.png",
    }
    templates = {key: cv2.imread(path, cv2.IMREAD_COLOR) for key, path in template_paths.items()}

    def find_and_click(template_key, offset_y=0):
        if templates[template_key] is None:
            return False
        location, shape = find_image_on_screen(templates[template_key])
        if location:
            center_x = (location[0] + shape[1] // 2) // 2
            center_y = (location[1] + shape[0] // 2) // 2 - offset_y
            pyautogui.click(center_x, center_y)
            return True
        return False

    def find_image(template_key):
        if templates[template_key] is None:
            return False
        location, shape = find_image_on_screen(templates[template_key])
        return bool(location)

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

    # 读取并清理第一个描述（增加健壮性）
    raw_description1 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    new_description1 = clean_string_value(raw_description1)
    print(f"清理后的 Description 1: {new_description1}")

    script_path = '/Users/yanzhang/Coding/ScriptEditor/Shift2Doubao.scpt' if found_poe else '/Users/yanzhang/Coding/ScriptEditor/Shift2Poe.scpt'
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

    # 读取并清理第二个描述
    raw_description2 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    new_description2 = clean_string_value(raw_description2)
    print(f"清理后的 Description 2: {new_description2}")

    # 比较两个描述
    if new_description1 == new_description2:
        print("new_description1 和 new_description2 一致，将 new_description2 置为空。")
        new_description2 = ""
    else:
        print("new_description1 和 new_description2 不一致，继续执行原逻辑。")

    if "ETF" in new_description1 and "ETF" in new_description2:
        show_applescript_dialog("要添加的好像是ETF而不是Stock")
        sys.exit()

    root = tk.Tk()
    root.title("Add Stock")
    root.lift()
    root.focus_force()

    success_flag = [False]
    entry = tk.Entry(root, width=50)
    entry.pack(padx=10, pady=5)
    entry.focus_set()

    button = tk.Button(
        root,
        text="添加 Tags",
        command=lambda: add_stock(new_name, stock_name, entry, data, json_file, new_description1, new_description2, root, success_flag)
    )
    button.pack(pady=5)

    root.bind(
        '<Key>',
        lambda event: on_key_press(event, new_name, stock_name, entry, data, json_file, new_description1, new_description2, root, success_flag)
    )
    root.mainloop()

    if success_flag[0]:
        show_applescript_dialog("股票已成功写入！")
    else:
        show_applescript_dialog("操作已取消，未进行任何写入。")

if __name__ == "__main__":
    main()