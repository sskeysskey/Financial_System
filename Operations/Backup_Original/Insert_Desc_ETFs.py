import cv2
import json
import pyperclip
import pyautogui
import numpy as np
from time import sleep
from PIL import ImageGrab
import tkinter as tk
import sys
import subprocess
import re

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
                    parts = line.strip().split(': ', 1)
                    if len(parts) == 2:
                        symbol, rest = parts
                        name = rest.rsplit(',', 1)[0].strip()
                        symbol_names[symbol] = name
        except FileNotFoundError:
            print(f"文件未找到: {file_path}，将忽略。")
        except Exception as e:
            print(f"处理文件 {file_path} 时发生错误: {e}")
    return symbol_names

def add_or_update_etf(symbol, entry, data, json_file, description1, description2, root, symbol_names, success_flag):
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
            "description2": description2,
            "value": ""
        }
        data["etfs"].append(new_etf)
    
    with open(json_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
    success_flag[0] = True  # 设置成功标志位
    root.destroy()

def on_key_press(event, symbol, entry, data, json_file, description1, description2, root, symbol_names, success_flag):
    if event.keysym == 'Escape':
        root.destroy()
    elif event.keysym == 'Return':
        add_or_update_etf(symbol, entry, data, json_file, description1, description2, root, symbol_names, success_flag)

def read_clipboard():
    return pyperclip.paste().replace('"', '').replace("'", "")

def validate_new_name(new_name):
    # 判断是否全是大写英文字母
    if not new_name.isupper() or not new_name.isalpha():
        applescript_code = 'display dialog "不是ETFs代码！" buttons {"OK"} default button "OK"'
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)
        sys.exit()
    return new_name

def check_etf_exists(data, new_name):
    existing_etf = next((etf for etf in data.get('etfs', []) if etf['symbol'] == new_name), None)
    if existing_etf:
        if not existing_etf['description1'] and not existing_etf['description2']:
            return existing_etf
        else:
            applescript_code = 'display dialog "股票代码已存在且描述已存在！" buttons {"OK"} default button "OK"'
            process = subprocess.run(['osascript', '-e', applescript_code], check=True)
            sys.exit()
    return None

def execute_applescript(script_path):
    try:
        process = subprocess.run(['osascript', script_path], check=True, text=True, stdout=subprocess.PIPE)
        print(process.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error running AppleScript: {e}")

def main():
    json_file = "/Users/yanzhang/Coding/Financial_System/Modules/description.json"
    symbol_name_file1 = "/Users/yanzhang/Coding/News/backup/ETFs.txt"
    symbol_name_file2 = "/Users/yanzhang/Coding/News/ETFs_new.txt"
    symbol_names = load_symbol_names([symbol_name_file1, symbol_name_file2])

    with open(json_file, 'r', encoding='utf-8') as file:
        data = json.load(file)

    new_name = validate_new_name(read_clipboard())
    existing_etf = check_etf_exists(data, new_name)

    activate_chrome()
    template_paths = {
        # "poesuccess": "/Users/yanzhang/Coding/python_code/Resource/poe_copy_success.png",
        # "poethumb": "/Users/yanzhang/Coding/python_code/Resource/poe_thumb.png",
        "doubaocopy": "/Users/yanzhang/Coding/python_code/Resource/doubao_copy.png",
        # "poecopy": "/Users/yanzhang/Coding/python_code/Resource/poe_copy.png",
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

    # found_poe = find_and_click("poethumb", 40)
    # if found_poe:
    #     pyautogui.click(button='right')
    #     sleep(1)
    #     if find_and_click("poecopy"):
    #         print("找到图片位置")
    # else:
    #     if find_and_click("kimicopy"):
    #         print("找到copy图了，准备点击copy...")

    if find_and_click("doubaocopy"):
        print("找到copy图了，准备点击copy...")
    found_poe = False

    sleep(1)
    
    # 读取并清理第一个描述
    raw_description1 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    new_description1 = clean_string_value(raw_description1) # <-- 应用清理规则
    print(f"清理后的 Description 1: {new_description1}")
    
    # script_path = '/Users/yanzhang/Coding/ScriptEditor/Shift2Doubao.scpt' if found_poe else '/Users/yanzhang/Coding/ScriptEditor/Shift2Poe.scpt'
    # execute_applescript(script_path)
    # sleep(1)
    # if not found_poe:
    #     found_poe = find_and_click("poethumb", 40)
    #     if found_poe:
    #         pyautogui.click(button='right')
    #         while not find_and_click("poecopy"):
    #             sleep(1)
    #         while not find_image("poesuccess"):
    #             sleep(1)
    # else:
    #     find_and_click("doubaocopy")

    # # 读取并清理第二个描述
    # raw_description2 = read_clipboard().replace('\n', ' ').replace('\r', ' ')
    # new_description2 = clean_string_value(raw_description2) # <-- 应用清理规则
    # print(f"清理后的 Description 2: {new_description2}")


    # # **修改后的逻辑：在清理后的文本上进行比较**
    # if new_description1 == new_description2:
    #     print("清理后，new_description1 和 new_description2 一致，将 new_description2 置为空。")
    #     new_description2 = ""  # 如果一致，将new_description2置为空
    # else:
    #     print("清理后，new_description1 和 new_description2 不一致，继续执行原逻辑。")
    
    new_description2 = ""
    
    root = tk.Tk()
    root.title("Add ETF")
    
    root.lift()
    root.focus_force()
    
    success_flag = [False]  # 使用列表来传递布尔值
    entry = tk.Entry(root)
    entry.pack()
    entry.focus_set()
    button = tk.Button(root, text="添加 Tags", command=lambda: add_or_update_etf(new_name, entry, data, json_file, new_description1, new_description2, root, symbol_names, success_flag))
    button.pack()
    root.bind('<Key>', lambda event: on_key_press(event, new_name, entry, data, json_file, new_description1, new_description2, root, symbol_names, success_flag))
    root.mainloop()

    if success_flag[0]:
        applescript_code = 'display dialog "ETF信息已成功写入！" buttons {"OK"} default button "OK"'
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)
    else:
        applescript_code = 'display dialog "操作已取消，未进行任何写入。" buttons {"OK"} default button "OK"'
        process = subprocess.run(['osascript', '-e', applescript_code], check=True)

if __name__ == "__main__":
    main()