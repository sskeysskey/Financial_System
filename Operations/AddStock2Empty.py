import os
import re
import json
import glob

# 文件目录路径
txt_file_directory = "/Users/yanzhang/Documents/News/"
json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json"

# 找到以Stock_Change_开头的第一个TXT文件
txt_file_pattern = os.path.join(txt_file_directory, "Stock_Change_*.txt")
txt_files = glob.glob(txt_file_pattern)

if not txt_files:
    raise FileNotFoundError("未找到以 'Stock_Change_' 开头的TXT文件。")

# 取第一个找到的文件
txt_file_path = txt_files[0]

# 读取TXT文件内容
with open(txt_file_path, 'r') as txt_file:
    txt_content = txt_file.read()

# 读取JSON文件内容
with open(json_file_path, 'r') as json_file:
    json_content = json_file.read()

# 解析JSON文件
data = json.loads(json_content)

# 使用正则表达式匹配 "Added 'XXX' to YYY" 的模式
pattern = re.compile(r"Added\s+'(\w+(-\w+)?)'\s+to\s+(\w+)")

# 在TXT文件内容中查找所有匹配项
matches = pattern.findall(txt_content)

# 将匹配的内容添加到JSON数据中对应的组别
for match in matches:
    symbol, _, group = match
    if group in data:
        data[group].append(symbol)

# 输出更新后的JSON数据
updated_json_content = json.dumps(data, indent=2)

# 将更新后的JSON数据写回文件
with open(json_file_path, 'w') as json_file:
    json_file.write(updated_json_content)

print("JSON文件已成功更新！")