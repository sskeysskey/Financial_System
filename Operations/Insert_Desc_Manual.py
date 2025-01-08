import json
import pyperclip
import tkinter as tk
import subprocess
import re
import sys

def copy2clipboard():
    script = '''
    tell application "System Events"
	    keystroke "c" using {command down}
        delay 0.5
    end tell
    '''
    subprocess.run(['osascript', '-e', script], check=True)

def show_input_dialog(title, prompt, initial_value=None):
    """通用的输入对话框函数，支持预填充值"""
    root = tk.Tk()
    root.title(title)
    root.lift()
    root.focus_force()
    
    # 添加提示标签
    label = tk.Label(root, text=prompt)
    label.pack(pady=5)
    
    input_var = tk.StringVar()
    if initial_value:
        input_var.set(initial_value)
        
    entry = tk.Entry(root, textvariable=input_var, width=40)
    entry.pack(pady=5)
    entry.focus_set()
    
    # 选中所有文本
    if initial_value:
        entry.select_range(0, tk.END)
    
    result = [None]
    cancel_flag = [False]
    
    def on_submit():
        result[0] = input_var.get()
        root.quit()
        
    def on_cancel(event=None):
        cancel_flag[0] = True
        root.quit()
        
    def on_enter(event):
        on_submit()
    
    submit_btn = tk.Button(root, text="确定", command=on_submit)
    submit_btn.pack(pady=5)
    
    root.bind('<Return>', on_enter)
    root.bind('<Escape>', on_cancel)
    
    # 设置窗口大小和位置
    window_width = 400
    window_height = 150
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f'{window_width}x{window_height}+{x}+{y}')
    
    # 确保窗口出现在最前面
    root.attributes('-topmost', True)
    root.update()
    root.attributes('-topmost', False)
    root.mainloop()
    root.destroy()
    
    if cancel_flag[0]:
        return None
    return result[0]

def show_tags_dialog():
    """专门用于标签输入的对话框"""
    root = tk.Tk()
    root.title("输入标签")
    root.lift()
    root.focus_force()
    
    label = tk.Label(root, text="请输入标签（用空格分隔）:")
    label.pack(pady=5)
    
    entry = tk.Entry(root, width=40)
    entry.pack(pady=5)
    entry.focus_set()
    
    result = [None]
    cancel_flag = [False]
    
    def on_submit():
        tags = entry.get().split()
        result[0] = tags
        root.quit()
        
    def on_cancel(event=None):
        cancel_flag[0] = True
        root.quit()
    
    submit_btn = tk.Button(root, text="确定", command=on_submit)
    submit_btn.pack(pady=5)
    
    root.bind('<Return>', lambda e: on_submit())
    root.bind('<Escape>', on_cancel)
    
    # 设置窗口大小和位置
    window_width = 400
    window_height = 150
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f'{window_width}x{window_height}+{x}+{y}')
    
    root.mainloop()
    root.destroy()
    
    if cancel_flag[0]:
        return None
    return result[0]

def show_message(message):
    """显示消息对话框"""
    applescript_code = f'display dialog "{message}" buttons {{"OK"}} default button "OK"'
    subprocess.run(['osascript', '-e', applescript_code], check=True)

def validate_symbol(symbol):
    """验证股票代码格式"""
    if not re.match("^[A-Z\-]+$", symbol):
        show_message("无效的股票代码！")
        return False
    return True

def get_clipboard_content():
    """获取剪贴板内容并清理"""
    try:
        content = pyperclip.paste()
        # 清理内容，移除引号和空白
        content = content.strip().replace('"', '').replace("'", "")
        return content
    except:
        return ""

def main():
    json_file = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"
    
    try:
        with open(json_file, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        data = {"stocks": []}

    copy2clipboard()
    initial_symbol = get_clipboard_content()
    
    # 1. 输入 Symbol，预填充剪贴板内容
    symbol = show_input_dialog("输入股票代码", "请输入股票代码:", initial_symbol)
    if symbol is None or not validate_symbol(symbol):
        return
        
    # 检查股票是否已存在
    if any(stock['symbol'] == symbol for stock in data.get('stocks', [])):
        show_message("股票代码已存在！")
        return
    
    # 2. 输入 Name
    name = show_input_dialog("输入股票名称", "请输入股票名称:")
    if name is None:
        return
    
    # 3. 输入 Tags
    tags = show_tags_dialog()
    if tags is None:
        return
    
    # 4. 输入 Description1
    description1 = show_input_dialog("输入描述1", "请输入第一段描述:")
    if description1 is None:
        return
    
    # 5. 输入 Description2
    description2 = show_input_dialog("输入描述2", "请输入第二段描述:")
    if description2 is None:
        return
    
    # 构建新的股票数据
    new_stock = {
        "symbol": symbol,
        "name": name,
        "tag": tags,
        "description1": description1,
        "description2": description2,
        "value": ""
    }
    
    # 添加到数据中
    data["stocks"].append(new_stock)
    
    # 写入文件
    try:
        with open(json_file, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        show_message("股票信息已成功写入！")
    except Exception as e:
        show_message(f"写入文件时发生错误：{str(e)}")

if __name__ == "__main__":
    main()