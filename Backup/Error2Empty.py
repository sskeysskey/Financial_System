import json
import re

# 定义文件路径
error_file_path = "/Users/yanzhang/Coding/News/Today_error.txt"
json_file_path = "/Users/yanzhang/Coding/Financial_System/Modules/Sectors_empty.json"

# 读取报错文件内容
with open(error_file_path, 'r') as error_file:
    error_log = error_file.read()

# 读取 JSON 配置文件内容
with open(json_file_path, 'r') as json_file:
    json_config = json.load(json_file)

# 正则表达式匹配报错文件中的分类和代码
pattern = re.compile(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] (\w+) ([\^A-Za-z0-9]+): No price data found for the given date range.')

for line in error_log.split('\n'):
    match = pattern.match(line)
    if match:
        category, code = match.groups()
        if category not in json_config:
            json_config[category] = []  # 初始化空列表
        if code not in json_config[category]:
            json_config[category].append(code)

# 将更新后的 JSON 配置内容写回到文件
with open(json_file_path, 'w') as json_file:
    json.dump(json_config, json_file, indent=2)

print("更新后的JSON文件已保存。")