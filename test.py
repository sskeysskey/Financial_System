import pyperclip
import os
import re
import json
import glob
from datetime import datetime

# 文件目录路径
txt_file_directory = "/Users/yanzhang/Documents/News/backup/backup/"

# 找到以Stock_50_开头的第一个TXT文件
txt_file_pattern = os.path.join(txt_file_directory, "Stock_50_*.txt")
txt_files = glob.glob(txt_file_pattern)

if not txt_files:
    raise FileNotFoundError("未找到以 'Stock_50_' 开头的TXT文件。")

# 用字典存储文件路径和对应的日期
file_dates = {}

# 正则表达式匹配文件名中的日期
date_pattern = re.compile(r"Stock_50_(\d{6})\.txt$")

for file_path in txt_files:
    match = date_pattern.search(os.path.basename(file_path))
    if match:
        try:
            # 将匹配到的日期字符串转换为datetime对象
            date_str = match.group(1)
            file_date = datetime.strptime(date_str, "%y%m%d")
            file_dates[file_path] = file_date
        except ValueError:
            continue

if not file_dates:
    raise FileNotFoundError("未找到含有有效日期的Stock_50_文件。")

# 获取日期最新的文件路径
latest_file = max(file_dates.items(), key=lambda x: x[1])[0]

# 读取TXT文件内容
with open(latest_file, 'r') as txt_file:
    txt_content = txt_file.read()

# 使用正则表达式匹配 "Added 'XXX' to YYY" 的模式
pattern = re.compile(r"Added\s+'(\w+(-\w+)?)'\s+to\s+(\w+)")

# 在TXT文件内容中查找所有匹配项
matches = pattern.findall(txt_content)

# 提取股票代码
stock_symbols = [match[0] for match in matches]

for symbol in stock_symbols:
    pyperclip.copy(symbol)