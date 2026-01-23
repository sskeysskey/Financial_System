import pyperclip
import json
import os

def match_symbol_name():
    """
    从剪贴板读取一个股票代码 (symbol)，在指定的 JSON 文件中查找匹配的名称 (name)，
    并将找到的名称写回剪贴板。
    """
    # 1. 读取并处理剪贴板内容
    try:
        clipboard_content = pyperclip.paste().upper().strip()
        if not clipboard_content:
            print("剪贴板为空，程序退出。")
            return
    except pyperclip.PyperclipException as e:
        print(f"无法访问剪贴板: {e}")
        print("请确保您已安装剪贴板工具，如 xclip (Linux) 或自带功能 (Windows/Mac)。")
        return
        
    # 2. 定义 JSON 文件路径
    USER_HOME = os.path.expanduser("~")
    BASE_CODING_DIR = os.path.join(USER_HOME, "Coding")
    file_path = os.path.join(BASE_CODING_DIR, "Financial_System", "Modules", "description.json")
    
    # 3. 读取并解析JSON文件
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        print(f"错误: 文件未找到 -> {file_path}")
        return
    except json.JSONDecodeError:
        print(f"错误: JSON文件格式不正确，无法解析 -> {file_path}")
        return
    
    # 4. 在 "stocks" 分组中查找匹配的 symbol
    found_name = None
    # 使用 .get('stocks', []) 来安全地获取stocks列表，如果"stocks"键不存在，则返回一个空列表
    stocks_list = data.get('stocks', [])
    
    for stock in stocks_list:
        # 同样安全地获取 symbol 键的值，并与剪贴板内容比较
        if stock.get('symbol') and stock.get('symbol').upper() == clipboard_content:
            found_name = stock.get('name')
            break  # 找到匹配项后立即退出循环
            
    # 5. 根据查找结果执行操作
    if found_name:
        # 找到匹配，将对应的名称写回剪贴板
        pyperclip.copy(found_name)
        print(f"找到匹配: {clipboard_content} -> {found_name}")
    else:
        print(f"在 'stocks' 分组中未找到匹配的symbol: {clipboard_content}")

if __name__ == "__main__":
    match_symbol_name()