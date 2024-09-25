import json
import os
import re
import glob

def find_Stock_50_file():
    """查找Stock_50_开头的TXT文件"""
    txt_file_pattern = os.path.join(TXT_FILE_DIRECTORY, "Stock_50_*.txt")
    txt_files = glob.glob(txt_file_pattern)
    if not txt_files:
        raise FileNotFoundError("未找到以 'Stock_50_' 开头的TXT文件。")
    return txt_files[0]

def read_file(file_path):
    """读取文件内容"""
    with open(file_path, 'r') as file:
        return file.read()

TXT_FILE_DIRECTORY = "/Users/yanzhang/Documents/News/"
txt_file_path = find_Stock_50_file()
txt_content = read_file(txt_file_path)
JSON_FILE_PATH_ALL = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"

data_all = json.loads(read_file(JSON_FILE_PATH_ALL))

pattern = re.compile(r"Added\s+'(\w+(-\w+)?)'\s+to\s+(\w+)")
matches = pattern.findall(txt_content)

for symbol, _, group in matches:
    symbol_count = sum(symbol in symbols for symbols in data_all.values())

print(f"共出现了{symbol_count}次。")