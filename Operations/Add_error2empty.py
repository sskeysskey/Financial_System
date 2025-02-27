import json
import pyperclip
import re
import os

def process_clipboard_content(error_file_path, sectors_file_path):
    # 获取剪贴板内容
    clipboard_content = pyperclip.paste().strip()
    if not clipboard_content:
        print("剪贴板为空")
        return
    
    print(f"剪贴板内容: {clipboard_content}")
    
    # 读取错误文件
    with open(error_file_path, 'r', encoding='utf-8') as error_file:
        error_content = error_file.read()
    
    # 查找包含剪贴板内容的行
    for line in error_content.split('\n'):
        if clipboard_content in line:
            # 使用正则表达式匹配 "在表 XXX 中" 的模式
            match = re.search(r'在表\s+(\w+)\s+中', line)
            if match:
                group = match.group(1)
                symbol = clipboard_content
                
                # 读取sectors文件
                with open(sectors_file_path, 'r', encoding='utf-8') as sectors_file:
                    sectors_data = json.load(sectors_file)
                
                # 检查组是否存在并添加symbol
                if group in sectors_data:
                    if symbol not in sectors_data[group]:
                        print(f"将 {symbol} 添加到 {group} 组中。")
                        sectors_data[group].append(symbol)
                        
                        # 将更新后的数据写回文件
                        with open(sectors_file_path, 'w', encoding='utf-8') as sectors_file:
                            json.dump(sectors_data, sectors_file, indent=4)
                        return
                    else:
                        print(f"{symbol} 已经存在于 {group} 组中。")
                        return
                else:
                    print(f"警告: {group} 组不存在于sectors文件中。")
                    return
    
    print(f"在错误文件中未找到包含 {clipboard_content} 的相关信息。")

# 主程序开始
sectors_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
error_file_path = '/Users/yanzhang/Documents/News/Today_error.txt'

# 检查文件是否存在
if not os.path.exists(error_file_path):
    print(f"Error: 文件 {error_file_path} 不存在。")
elif not os.path.exists(sectors_file_path):
    print(f"Error: 文件 {sectors_file_path} 不存在。")
else:    
    try:
        process_clipboard_content(error_file_path, sectors_file_path)
        print("处理完成。")
    except Exception as e:
        print(f"发生错误: {str(e)}")