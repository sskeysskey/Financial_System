import json
import re
import os
import pyperclip
import subprocess
from time import sleep
from decimal import Decimal  # 引入Decimal模块

# 按权重分组的标签字典
weight_groups = {
    Decimal('0.2'): ['美国', '英国', '加拿大', '中国', '以色列', '瑞士', '德国', '法国', '日本', '印度'],
    Decimal('1.5'): ['保险', '医疗', '医院', '飞机', "AI", "芯片"],
    Decimal('2.0'): ['医疗保险', '医院运营', '关节置换', "飞机制造", "工业软件", "EDA"]
}

# 动态生成标签权重配置表
tags_weight_config = {tag: weight for weight, tags in weight_groups.items() for tag in tags}

# 默认权重
DEFAULT_WEIGHT = Decimal('1')

def copy2clipboard():
    script = '''
    tell application "System Events"
	    keystroke "c" using {command down}
        delay 0.5
    end tell
    '''
    subprocess.run(['osascript', '-e', script], check=True)

def find_tags_by_symbol(symbol, data):
    tags_with_weight = []
    # 遍历stocks和etfs，找到匹配的symbol并返回其tags
    for category in ['stocks', 'etfs']:
        for item in data[category]:
            if item['symbol'] == symbol:
                for tag in item['tag']:
                    # 从tags_weight_config中获取权重，找不到则使用默认权重
                    weight = tags_weight_config.get(tag, DEFAULT_WEIGHT)
                    tags_with_weight.append((tag, weight))
                return tags_with_weight
    return []

def find_symbols_by_tags(target_tags_with_weight, data):
    related_symbols = {'stocks': [], 'etfs': []}

    # 创建一个目标标签字典，键为小写标签，值为权重
    target_tags_dict = {tag.lower(): weight for tag, weight in target_tags_with_weight}

    for category in ['stocks', 'etfs']:
        for item in data[category]:
            tags = item.get('tag', [])
            matched_tags = []
            used_tags = set()  # 用于记录已经匹配过的标签（无论是完全匹配还是部分匹配）

            # 第一阶段：处理完全匹配
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in target_tags_dict and tag_lower not in used_tags:
                    matched_tags.append((tag, target_tags_dict[tag_lower]))
                    used_tags.add(tag_lower)  # 标记该标签已被完全匹配

            # 第二阶段：处理部分匹配，仅针对未被完全匹配的标签
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in used_tags:
                    continue  # 跳过已被完全匹配的标签
                for target_tag, target_weight in target_tags_dict.items():
                    # 只有当目标tag包含源tag并且目标tag的长度大于等于源tag时才算部分匹配
                    if target_tag in tag_lower and len(tag_lower) >= len(target_tag):
                        if target_tag not in used_tags:
                            matched_tags.append((tag, target_weight))
                            used_tags.add(target_tag)  # 标记该部分匹配的标签避免重复计数
                        break  # 每个标签只匹配一次

            if matched_tags:
                related_symbols[category].append((item['symbol'], matched_tags, tags))

    # 按总权重降序排序
    for category in related_symbols:
        related_symbols[category].sort(
            key=lambda x: sum(weight for _, weight in x[1]),
            reverse=True
        )

    return related_symbols

def load_compare_data(file_path):
    compare_data = {}
    with open(file_path, 'r') as file:
        lines = file.readlines()
        for line in lines:
            if ':' in line:
                sym, value = line.split(':', 1)
                compare_data[sym.strip()] = value.strip()
    return compare_data

def main(symbol):
    # 加载compare_all文件中的数据
    compare_data = load_compare_data('/Users/yanzhang/Documents/News/backup/Compare_All.txt')
    
    # 找到给定symbol的tags及其权重
    target_tags_with_weight = find_tags_by_symbol(symbol, data)
    
    # 将 Decimal 转换为浮点数并生成输出
    output_lines = [f"Tags with weight for {symbol}: {[(tag, float(weight)) for tag, weight in target_tags_with_weight]}"]

    if not target_tags_with_weight:
        output_lines.append("No tags found for the given symbol.\n")
    else:
        # 找到所有与这些tags模糊匹配的symbols和tags
        related_symbols = find_symbols_by_tags(target_tags_with_weight, data)
    
        # 移除原始symbol以避免自引用
        related_symbols['stocks'] = [item for item in related_symbols['stocks'] if item[0] != symbol]
        related_symbols['etfs'] = [item for item in related_symbols['etfs'] if item[0] != symbol]
        
        output_lines.append(f"\n")
        
        # 添加stocks结果
        output_lines.append("\n【Stocks】\n")
        for sym, matched_tags, all_tags in related_symbols['stocks']:
            compare_value = compare_data.get(sym, '')
            total_weight = round(sum(float(weight) for _, weight in matched_tags), 2)  # 转换为浮点数并舍入
            output_lines.append(f"{sym:<7}{total_weight:<3} {compare_value:<12}{all_tags}\n")
        
        # 添加etfs结果并加标题
        if related_symbols['etfs']:
            output_lines.append("\n【ETFs】\n")
            for sym, matched_tags, all_tags in related_symbols['etfs']:
                compare_value = compare_data.get(sym, '')
                total_weight = round(sum(float(weight) for _, weight in matched_tags), 2)  # 转换为浮点数并舍入
                output_lines.append(f"{sym:<7}{total_weight:<3} {compare_value:<10}{all_tags}\n")
    
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