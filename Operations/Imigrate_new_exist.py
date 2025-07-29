import os
import re
import sys
import argparse
from datetime import datetime

# 锁文件，用于记录上次执行日期
LOCK_FILE = os.path.join(os.path.dirname(__file__), '.last_run_date')

# 文件路径
files = {
    'ETFs': '/Users/yanzhang/Documents/News/backup/ETFs.txt',
    '10Y_newhigh': '/Users/yanzhang/Documents/News/backup/10Y_newhigh.txt',
    'Earnings_Release': '/Users/yanzhang/Documents/News/backup/Earnings_Release.txt',
    'Economic_Events': '/Users/yanzhang/Documents/News/backup/Economic_Events.txt'
}

new_files = {
    'ETFs': '/Users/yanzhang/Documents/News/ETFs_new.txt',
    '10Y_newhigh': '/Users/yanzhang/Documents/News/10Y_newhigh_new.txt',
    'Earnings_Release': '/Users/yanzhang/Documents/News/Earnings_Release_new.txt',
    'Economic_Events': '/Users/yanzhang/Documents/News/Economic_Events_new.txt'
}

next_files = {
    'Earnings_Release': '/Users/yanzhang/Documents/News/Earnings_Release_next.txt',
    'Economic_Events': '/Users/yanzhang/Documents/News/Economic_Events_next.txt'
}

# 获取当前星期几，0是周一，6是周日
current_day = datetime.now().weekday()

def check_run_once_today():
    """
    每天只能执行一次。利用 LOCK_FILE 存储上次执行日期（格式 YYYY-MM-DD）。
    如果日期与今天相同，直接退出；否则更新为今天。
    """
    today_str = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, 'r') as lf:
            last = lf.read().strip()
        if last == today_str:
            print(f"脚本今天 ({today_str}) 已执行过，退出。")
            sys.exit(1)
    # 更新为今天
    with open(LOCK_FILE, 'w') as lf:
        lf.write(today_str)

def format_line(line):
    parts = re.split(r'\s*:\s*', line.strip(), 2)
    if len(parts) == 3:
        symbol, _, rest = parts
        return f"{symbol:<7}: {rest}"
    elif len(parts) == 2:
        symbol, rest = parts
        return f"{symbol:<7}: {rest}"
    else:
        return line.strip()

def process_and_rename_files():
    # 检查 Earnings_Release 的 new 和 next 文件是否存在
    earnings_files_exist = all(os.path.exists(f) for f in [
        new_files['Earnings_Release'],
        next_files['Earnings_Release']
    ])

    events_files_exist = all(os.path.exists(f) for f in [
        new_files['Economic_Events'],
        next_files['Economic_Events']
    ])

    if earnings_files_exist:
        # 处理 Earnings_Release 的 new 文件
        process_earnings(new_files['Earnings_Release'], files['Earnings_Release'])

        # 重命名 Earnings_Release 的 next 文件为 new 文件
        os.rename(next_files['Earnings_Release'], new_files['Earnings_Release'])
    else:
        print("Earnings_Release 相关文件缺失，未执行任何操作。")

    if events_files_exist:    
        # 如果 Economic_Events 的 new 文件存在，则处理它
        if os.path.exists(new_files['Economic_Events']):
            process_file(new_files['Economic_Events'], files['Economic_Events'])

        # 如果 Economic_Events 的 next 文件存在，则重命名它
        if os.path.exists(next_files['Economic_Events']):
            os.rename(next_files['Economic_Events'], new_files['Economic_Events'])
    else:
        print("Economic_Events 相关文件缺失，未执行任何操作。")

def process_earnings(new_file, backup_file):
    if not os.path.exists(new_file):
        return
    with open(new_file, 'r') as fin, open(backup_file, 'a') as fout:
        fout.write('\n')
        lines = [L.rstrip('\n') for L in fin]
        for idx, line in enumerate(lines):
            parts = [p.strip() for p in line.split(':')]
            if len(parts) == 3:
                symbol, _, date = parts
                out = f"{symbol:<7}: {date}"
            elif len(parts) == 2:
                symbol, date = parts
                out = f"{symbol:<7}: {date}"
            else:
                out = line.strip()

            # 最后一行不加换行
            if idx < len(lines) - 1:
                fout.write(out + "\n")
            else:
                fout.write(out)
    os.remove(new_file)

def process_file(new_file, existing_file):
    if os.path.exists(new_file):
        with open(new_file, 'r') as file_a, open(existing_file, 'a') as file_b:
            file_b.write('\n')  # 在迁移内容前首先输入一个回车
            lines = file_a.readlines()
            for i, line in enumerate(lines):
                if 'Earnings_Release' in new_file:
                    # 使用正则表达式去除 " : 数字" 部分
                    processed_line = re.sub(r'\s*:\s*\d+\s*', '', line, count=1)
                    formatted_line = format_line(processed_line)
                    if i == len(lines) - 1:  # 如果是最后一行
                        file_b.write(formatted_line.rstrip())  # 移除行尾的空白字符，但不添加新行
                    else:
                        file_b.write(formatted_line + '\n')
                else:
                    if i == len(lines) - 1:  # 如果是最后一行
                        file_b.write(line.rstrip())  # 移除行尾的空白字符，但不添加新行
                    else:
                        file_b.write(line)
        os.remove(new_file)

def process_etf_file(new_file, existing_file):
    if not os.path.exists(new_file):
        return

    # 读取现有文件的所有内容（不使用 readlines 以避免自动添加换行符）
    with open(existing_file, 'r') as f:
        existing_content = f.read()
    
    # 获取现有的符号集
    existing_symbols = {line.split(':', 1)[0].strip() 
                       for line in existing_content.split('\n') if line.strip()}
    
    # 读取新文件的所有内容
    with open(new_file, 'r') as f:
        new_content = f.read()
    
    # 处理新内容
    new_lines_to_add = []
    for line in new_content.split('\n'):
        if not line.strip():
            continue
        symbol = line.split(':', 1)[0].strip()
        if symbol not in existing_symbols:
            new_lines_to_add.append(line)
            existing_symbols.add(symbol)
    
    # 写入合并后的内容
    if new_lines_to_add:
        with open(existing_file, 'w') as f:
            if existing_content and existing_content.strip():
                # 如果现有内容非空，添加新内容时需要换行符分隔
                content_to_write = existing_content + '\n' + '\n'.join(new_lines_to_add)
            else:
                # 如果现有内容为空，直接写入新内容
                content_to_write = '\n'.join(new_lines_to_add)
            
            # 写入内容，确保末尾没有换行符
            f.write(content_to_write.rstrip('\n'))
    
    os.remove(new_file)

def main(mode):
    if mode == 'etf':
        # 周二到周天允许运行
        if 1 <= current_day <= 6:  # 周二到周天
            process_etf_file(new_files['ETFs'], files['ETFs'])
            process_file(new_files['10Y_newhigh'], files['10Y_newhigh'])
        else:
            print("Not right date. ETF 模式只在周二到周天运行。")
    elif mode == 'other':
        # 周日或周一允许运行
        if current_day in (0):
            check_run_once_today()
            process_and_rename_files()
        else:
            print("Not right date. Other 模式只在周一运行。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process files based on the given mode.')
    parser.add_argument('mode', choices=['etf', 'other'], help='The processing mode: etf or other')
    args = parser.parse_args()
    main(args.mode)