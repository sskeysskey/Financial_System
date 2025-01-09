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
    
    # 修改后的正则表达式，增加对连字符的支持
    pattern = r'\[.*?\] (\w+) ([-\w.^=]+): No price data found for the given date range\.'
    matches = re.findall(pattern, error_content)
    print(f"在 today_error1 中找到 {len(matches)} 个匹配项。")
    
    with open(sectors_file_path, 'r') as sectors_file:
        sectors_data = json.load(sectors_file)
    
    # 将匹配的symbol添加到相应的分组中
    for group, symbol in matches:
        if group in sectors_data:
            if symbol not in sectors_data[group]:
                print(f"将 {symbol} 添加到 {group} 组中。")
                sectors_data[group].append(symbol)
            else:
                print(f"{symbol} 已经存在于 {group} 组中。")
        else:
            print(f"警告: {group} 组不存在于sectors文件中。")

    # 将更新后的数据写回 sectors 文件
    with open(sectors_file_path, 'w') as sectors_file:
        json.dump(sectors_data, sectors_file, indent=4)

# 主程序开始
sectors_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
error_file_path = '/Users/yanzhang/Documents/News/Today_error1.txt'

# 检查错误文件是否存在
if not os.path.exists(error_file_path):
    print(f"Error: 文件 {error_file_path} 不存在。")
else:    
    try:
        process_error_file(error_file_path, sectors_file_path)
        print("处理完成。")
    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")
        print(traceback.format_exc())