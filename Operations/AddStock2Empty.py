import os
import re
import json
import glob
from datetime import datetime

# 文件目录路径
txt_file_directory = "/Users/yanzhang/Documents/News/"
json_file_path_empty = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json"
json_file_path_all = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
error_file_path = '/Users/yanzhang/Documents/News/Today_error.txt'

# 错误日志函数
def log_error_with_timestamp(error_message, file_path):
    # 获取当前日期和时间
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 在错误信息前加入时间戳
    with open(file_path, 'a') as error_file:
        error_file.write(f"[{timestamp}] {error_message}\n")

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
with open(json_file_path_empty, 'r') as json_file_empty:
    json_content_empty = json_file_empty.read()

# 读取Sectors_All.json的内容
with open(json_file_path_all, 'r') as json_file_all:
    json_content_all = json_file_all.read()

# 解析JSON文件
data_empty = json.loads(json_content_empty)
data_all = json.loads(json_content_all)

# 使用正则表达式匹配 "Added 'XXX' to YYY" 的模式
pattern = re.compile(r"Added\s+'(\w+(-\w+)?)'\s+to\s+(\w+)")

# 在TXT文件内容中查找所有匹配项
matches = pattern.findall(txt_content)

# 将匹配的内容添加到JSON数据中对应的组别
for match in matches:
    symbol, _, group = match
    if group in data_empty:
        # 检查Sectors_All中是否已经存在该symbol
        if any(symbol in symbols for symbols in data_all.values()):
            log_error_with_timestamp(f"Symbol '{symbol}' 已经存在于 Sectors_All.json 中，未添加到 {group} 组别。", error_file_path)
        else:
            data_empty[group].append(symbol)

# 输出更新后的JSON数据
updated_json_content_empty = json.dumps(data_empty, indent=2)

# 将更新后的JSON数据写回文件
with open(json_file_path_empty, 'w') as json_file_empty:
    json_file_empty.write(updated_json_content_empty)

print("JSON文件已成功更新！")