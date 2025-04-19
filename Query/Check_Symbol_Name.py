import pyperclip

def match_symbol_name():
    # 读取剪贴板内容
    clipboard_content = pyperclip.paste().upper().strip()
    
    # 读取symbol_names.txt文件
    file_path = '/Users/yanzhang/Documents/News/backup/symbol_names.txt'
    
    # 创建一个字典来存储symbol和对应的名称
    symbol_dict = {}
    
    # 读取文件并解析内容
    with open(file_path, 'r') as file:
        for line in file:
            if ':' in line:
                symbol, name = line.split(':', 1)
                symbol_dict[symbol.strip()] = name.strip()
    
    # 检查剪贴板内容是否在字典中
    if clipboard_content in symbol_dict:
        # 找到匹配，将对应的名称写回剪贴板
        pyperclip.copy(symbol_dict[clipboard_content])
        print(f"找到匹配: {clipboard_content} -> {symbol_dict[clipboard_content]}")
    else:
        print(f"未找到匹配的symbol: {clipboard_content}")

if __name__ == "__main__":
    match_symbol_name()