import yfinance as yf
import sqlite3
import json
from datetime import datetime, timedelta
import traceback  # 用于获取完整的错误信息
import re
import os



def clear_sectors(sectors_file_path):
    with open(sectors_file_path, 'r') as sectors_file:
        sectors_data = json.load(sectors_file)
    
    for group in sectors_data:
        sectors_data[group] = []
    
    with open(sectors_file_path, 'w') as sectors_file:
        json.dump(sectors_data, sectors_file, indent=4)

# 主程序开始
sectors_file_path = '/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json'
error_file_path = '/Users/yanzhang/Documents/News/Today_error1.txt'


    # 清除所有组别中的symbol
clear_sectors(sectors_file_path)

print("程序执行完毕")