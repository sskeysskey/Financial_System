import json
import re
import os
import pyperclip
import subprocess
from time import sleep

def copy2clipboard():
    script = '''
    tell application "System Events"
	    keystroke "c" using {command down}
        delay 0.5
    end tell
    '''
    subprocess.run(['osascript', '-e', script], check=True)

def find_tags_by_symbol(symbol, data):
    # 遍历stocks和etfs，找到匹配的symbol并返回其tags
    for category in ['stocks', 'etfs']:
        for item in data[category]:
            if item['symbol'] == symbol:
                # 过滤掉不需要的tags
                return [tag for tag in item['tag'] if tag not in excluded_tags]
    return []

def find_symbols_by_tags(target_tags, data):
    related_symbols = {'stocks': {}, 'etfs': {}}
    # 遍历stocks和etfs，找到所有与目标tags模糊匹配的symbol
    for category in ['stocks', 'etfs']:
        for item in data[category]:
            tags = item.get('tag', [])
            # 对每个tag进行正则表达式匹配
            for t_tag in target_tags:
                pattern = re.compile(re.escape(t_tag), re.IGNORECASE)  # 创建模糊匹配的正则表达式模式
                if any(pattern.search(tag) for tag in tags):
                    related_symbols[category][item['symbol']] = tags  # 将symbol和其tags一起存储
    return related_symbols

def main(symbol):
    # 找到给定symbol的tags
    target_tags = find_tags_by_symbol(symbol, data)
    output_lines = [f"Tags for {symbol}: {target_tags}"]

    if not target_tags:
        output_lines.append("No tags found for the given symbol.\n")
    else:
        # 找到所有与这些tags模糊匹配的symbols和tags
        related_symbols = find_symbols_by_tags(target_tags, data)
    
        # 移除原始symbol以避免自引用
        if symbol in related_symbols['stocks']:
            del related_symbols['stocks'][symbol]
        if symbol in related_symbols['etfs']:
            del related_symbols['etfs'][symbol]
        
        output_lines.append(f"\n")
        
        # 添加stocks结果
        output_lines.append("\n【Stocks】\n")
        for sym, tags in related_symbols['stocks'].items():
            output_lines.append(f"{sym}: {tags}\n")
        
        # 添加etfs结果并加标题
        if related_symbols['etfs']:
            output_lines.append("\n【ETFs】\n")
            for sym, tags in related_symbols['etfs'].items():
                output_lines.append(f"{sym}: {tags}\n")

    # 写入文件
    output_path = '/Users/yanzhang/Documents/News/similar.txt'
    with open(output_path, 'w') as file:
        file.writelines(output_lines)

    # 自动打开文件
    os.system(f'open "{output_path}"')


# 过滤掉的tags集合
excluded_tags = {"巴西","美国","以色列","加拿大","英国","瑞士"}

# 读取JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/Description.json', 'r') as file:
    data = json.load(file)

copy2clipboard()
# 从剪贴板获取输入
clipboard_content = pyperclip.paste().strip()

# 使用剪贴板内容作为输入
main(clipboard_content)
sleep(2)

try:
    os.remove('/Users/yanzhang/Documents/News/similar.txt')
    print(f"文件已删除")
except OSError as e:
    print(f"删除文件时出错: {e}")