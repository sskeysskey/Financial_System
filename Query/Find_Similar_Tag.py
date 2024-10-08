import json
import re
import os
import pyperclip
import subprocess
from time import sleep

# 过滤掉的tags集合
excluded_tags = {}

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
    related_symbols = {'stocks': [], 'etfs': []}
    # 将目标标签转换为小写，用于后续比较
    target_tags_set = set(tag.lower() for tag in target_tags)
    
    for category in ['stocks', 'etfs']:
        for item in data[category]:
            tags = item.get('tag', [])
            matched_tags = [tag for tag in tags if tag.lower() in target_tags_set]
            
            if len(matched_tags) >= 1:
                related_symbols[category].append((item['symbol'], matched_tags, tags))
    
    # 对每个类别的结果按匹配标签数量降序排序
    for category in related_symbols:
        related_symbols[category].sort(key=lambda x: len(x[1]), reverse=True)
    
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
        related_symbols['stocks'] = [item for item in related_symbols['stocks'] if item[0] != symbol]
        related_symbols['etfs'] = [item for item in related_symbols['etfs'] if item[0] != symbol]
        
        output_lines.append(f"\n")
        
        # 添加stocks结果
        output_lines.append("\n【Stocks】\n")
        for sym, matched_tags, all_tags in related_symbols['stocks']:
            output_lines.append(f"{sym:<7}{len(matched_tags):<3} {all_tags}\n")
        
        # 添加etfs结果并加标题
        if related_symbols['etfs']:
            output_lines.append("\n【ETFs】\n")
            for sym, matched_tags, all_tags in related_symbols['etfs']:
                output_lines.append(f"{sym:<7}{len(matched_tags):<3} {all_tags}\n")

    # 写入文件
    output_path = '/Users/yanzhang/Documents/News/similar.txt'
    with open(output_path, 'w') as file:
        file.writelines(output_lines)

    # 自动打开文件
    os.system(f'open "{output_path}"')

# 读取JSON文件
with open('/Users/yanzhang/Documents/Financial_System/Modules/description.json', 'r') as file:
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