import yfinance as yf
import sqlite3
import json
from datetime import datetime, timedelta
import traceback  # 用于获取完整的错误信息
import re
import os

def process_error_file(error_file_path, sectors_file_path):
    with open(error_file_path, 'r') as error_file:
        error_content = error_file.read()
    
    # 修改后的正则表达式，确保匹配带有特殊符号的股票代码
    pattern = r'\[.*?\] (\w+) ([\w.^=]+): No price data found for the given date range\.'
    matches = re.findall(pattern, error_content)
    print(f"在 today_error1 中找到 {len(matches)} 个匹配项。")  # 日志：匹配结果数量
    
    with open(sectors_file_path, 'r') as sectors_file:
        sectors_data = json.load(sectors_file)
    
    # 将匹配的symbol添加到相应的分组中
    for group, symbol in matches:
        if group in sectors_data and symbol not in sectors_data[group]:
            print(f"将 {symbol} 添加到 {group} 组中。")  # 日志：添加symbol
            sectors_data[group].append(symbol)

    # 将更新后的数据写回 sectors 文件
    with open(sectors_file_path, 'w') as sectors_file:
        json.dump(sectors_data, sectors_file, indent=4)

# 主程序开始
sectors_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
error_file_path = '/Users/yanzhang/Documents/News/Today_error1.txt'

# 检查错误文件是否存在
if not os.path.exists(error_file_path):
    print(f"Error: 文件 {error_file_path} 不存在.")
else:    
    # 处理错误文件并更新sectors文件
    process_error_file(error_file_path, sectors_file_path)