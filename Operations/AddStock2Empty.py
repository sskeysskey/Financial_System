import os
import re
import json
import glob
from datetime import datetime

# 文件路径定义
TXT_FILE_DIRECTORY = "/Users/yanzhang/Documents/News/"
JSON_FILE_PATH_EMPTY = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_empty.json"
JSON_FILE_PATH_ALL = "/Users/yanzhang/Documents/Financial_System/Modules/Sectors_All.json"
ERROR_FILE_PATH = '/Users/yanzhang/Documents/News/Today_error.txt'

# 错误日志函数
def log_error_with_timestamp(error_message, file_path):
    """记录带时间戳的错误信息"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 在错误信息前加入时间戳
    with open(file_path, 'a') as error_file:
        error_file.write(f"[{timestamp}] {error_message}\n")

def read_file(file_path):
    """读取文件内容"""
    with open(file_path, 'r') as file:
        return file.read()

def write_json(file_path, data):
    """将数据写入JSON文件"""
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=2)

def find_Stock_50_file():
    """查找Stock_50_开头的TXT文件"""
    txt_file_pattern = os.path.join(TXT_FILE_DIRECTORY, "Stock_50_*.txt")
    txt_files = glob.glob(txt_file_pattern)
    if not txt_files:
        raise FileNotFoundError("未找到以 'Stock_50_' 开头的TXT文件。")
    return txt_files[0]

def process_Stock_50():
    try:
        txt_file_path = find_Stock_50_file()
        txt_content = read_file(txt_file_path)
        data_empty = json.loads(read_file(JSON_FILE_PATH_EMPTY))
        data_all = json.loads(read_file(JSON_FILE_PATH_ALL))

        pattern = re.compile(r"Added\s+'(\w+(-\w+)?)'\s+to\s+(\w+)")
        matches = pattern.findall(txt_content)
        print(f"从 Stock_50 文件中提取到 {len(matches)} 条匹配记录")

        if not matches:
            print("未从Stock_50.txt中提取到有效数据，不更新empty文件。")
            return

        updates_count = 0
        for symbol, _, group in matches:
            if group in data_empty:
                # 计算symbol在data_all中出现的次数
                symbol_count = sum(symbol in symbols for symbols in data_all.values())
                print(f"'{symbol}' 在 Sectors_All.json 的 {group} 中出现 {symbol_count} 次")

                if symbol_count >= 2:
                    log_error_with_timestamp(f"Symbol '{symbol}' 在 Sectors_All.json 中出现了 {symbol_count} 次，未添加到 {group} 组别。", ERROR_FILE_PATH)
                    print(f"'{symbol}' 在 Sectors_All.json 中出现了 {symbol_count} 次，未添加到 {group} 组别。")
                else:
                    data_empty[group].append(symbol)
                    updates_count += 1
                    print(f"成功将 '{symbol}' 添加到Sectors_empty的 '{group}' 组别")

        if updates_count > 0:
            write_json(JSON_FILE_PATH_EMPTY, data_empty)
            print(f"empty.json文件已成功更新！共更新了 {updates_count} 条记录。")
        else:
            print("没有新的Symbol需要添加，empty文件保持不变。")

    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")
        print(f"详情请查看错误日志: {ERROR_FILE_PATH}")

if __name__ == "__main__":
    process_Stock_50()