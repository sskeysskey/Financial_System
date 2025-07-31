import os
import json
from time import sleep

# 读取 JSON 文件
def read_json_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

# 写入 JSON 文件
def write_json_file(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

# 读取 Analysis.json
analysis_data = read_json_file('/Users/yanzhang/Coding/Financial_System/Modules/Chance.json')

# 读取 description.json
description_data = read_json_file('/Users/yanzhang/Coding/Financial_System/Modules/description.json')

# Step 1: 清空 description.json 中所有项目的 value 字段
for stock_type in ['stocks', 'etfs']:
    for item in description_data[stock_type]:
        item['value'] = ""  # 将 value 字段设置为空字符串

# Step 2: 遍历 Analysis.json 第二层级，找到第一个子项不为空的组
for category, subcategories in analysis_data.items():
    for subcategory, values in subcategories.items():
        if isinstance(values, list) and len(values) > 0 and values[0]:  # 检查第一个子项非空
            first_value = values[0]  # 第一个子项作为数字
            tags_to_match = values[1:]  # 剩余的子项作为标签列表

            # Step 3: 遍历 description.json 找到匹配的标签
            for stock_type in ['stocks', 'etfs']:  # 遍历 stocks 和 etfs
                for item in description_data[stock_type]:
                    # 如果所有标签都匹配
                    if all(tag in item['tag'] for tag in tags_to_match):
                        item['value'] = str(first_value)  # 更新对应的 value 字段

# Step 4: 更新后的 description.json 写回文件
write_json_file('/Users/yanzhang/Coding/Financial_System/Modules/description.json', description_data)

# Step 5: 提取 value 不为空的项目并按 value 排序
non_empty_value_items = []
for stock_type in ['stocks', 'etfs']:
    for item in description_data[stock_type]:
        if item['value']:  # 只提取 value 不为空的项目
            non_empty_value_items.append({
                'symbol': item['symbol'],
                'tag': item['tag'],
                'value': int(item['value'])
            })

# Step 6: 按 value 值从大到小排序
sorted_items = sorted(non_empty_value_items, key=lambda x: x['value'], reverse=True)

txt_path = '/Users/yanzhang/Downloads/a.txt'

# Step 7: 将排序后的内容写入 a.txt 文件，调整输出格式
with open(txt_path, 'w', encoding='utf-8') as file:
    for item in sorted_items:
        tag_str = ", ".join(item['tag'])  # 将标签列表转换为字符串
        # 格式化输出，symbol 左对齐，value 右对齐
        file.write(f'{item["symbol"]:<10} {item["value"]:>5}   {tag_str}\n')

# 自动打开文件
os.system(f'open "{txt_path}"')

sleep(2)

try:
    os.remove(txt_path)
    print(f"文件已删除")
except OSError as e:
    print(f"删除文件时出错: {e}")