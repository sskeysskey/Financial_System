import os
import re
from datetime import datetime, timedelta
import shutil
import argparse

# 文件路径
files = {
    'ETFs': '/Users/yanzhang/Documents/News/backup/ETFs.txt',
    'ETFs': '/Users/yanzhang/Documents/News/backup/10Y_newhigh.txt',
    'Earnings_Release': '/Users/yanzhang/Documents/News/backup/Earnings_Release.txt',
    'Economic_Events': '/Users/yanzhang/Documents/News/backup/Economic_Events.txt'
}

new_files = {
    'ETFs': '/Users/yanzhang/Documents/News/ETFs_new.txt',
    'ETFs': '/Users/yanzhang/Documents/News/10Y_newhigh_new.txt',
    'Earnings_Release': '/Users/yanzhang/Documents/News/Earnings_Release_new.txt',
    'Economic_Events': '/Users/yanzhang/Documents/News/Economic_Events_new.txt'
}

next_files = {
    'Earnings_Release': '/Users/yanzhang/Documents/News/Earnings_Release_next.txt',
    'Economic_Events': '/Users/yanzhang/Documents/News/Economic_Events_next.txt'
}

# diff 文件路径
diff_file = '/Users/yanzhang/Documents/News/ETFs_diff.txt'

# 备份目录
backup_dir = '/Users/yanzhang/Documents/News/backup/backup'

# 获取当前星期几，0是周一，6是周日
current_day = datetime.now().weekday()

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

    if earnings_files_exist:
        # 处理 Earnings_Release 的 new 文件
        process_file(new_files['Earnings_Release'], files['Earnings_Release'])

        # 重命名 Earnings_Release 的 next 文件为 new 文件
        os.rename(next_files['Earnings_Release'], new_files['Earnings_Release'])

        # 如果 Economic_Events 的 new 文件存在，则处理它
        if os.path.exists(new_files['Economic_Events']):
            process_file(new_files['Economic_Events'], files['Economic_Events'])

        # 如果 Economic_Events 的 next 文件存在，则重命名它
        if os.path.exists(next_files['Economic_Events']):
            os.rename(next_files['Economic_Events'], new_files['Economic_Events'])
    else:
        print("Some required files are missing. No action taken.")

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

def backup_diff_file(diff_file, backup_dir):
    if os.path.exists(diff_file):
        # 获取当前时间
        current_date = datetime.now()
        # 获取当前时间戳
        timestamp = current_date.strftime('%Y%m%d')
        # 新的文件名
        new_filename = f"ETFs_diff_{timestamp}.txt"
        # 目标路径
        target_path = os.path.join(backup_dir, new_filename)
        # 移动文件
        shutil.move(diff_file, target_path)

        # 删除四天前的备份文件
        four_days_ago = current_date - timedelta(days=4)
        for filename in os.listdir(backup_dir):
            if filename.startswith("ETFs_diff_") and filename.endswith(".txt"):
                file_date_str = filename[10:18]  # 提取日期部分
                try:
                    file_date = datetime.strptime(file_date_str, '%Y%m%d')
                    if file_date <= four_days_ago:
                        file_path = os.path.join(backup_dir, filename)
                        os.remove(file_path)
                except ValueError:
                    # 如果日期解析失败，跳过该文件
                    continue

def main(mode):
    if mode == 'etf':
        if 1 <= current_day <= 6:  # 周二到周天
            process_file(new_files['ETFs'], files['ETFs'])
            # 备份 diff 文件
            backup_diff_file(diff_file, backup_dir)
    elif mode == 'other':
        # if current_day == 6 or 0 <= current_day <=3:  # 周天或周一到周四
        if current_day == 6 or current_day == 0:  # 周天或周一
            process_and_rename_files()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process files based on the given mode.')
    parser.add_argument('mode', choices=['etf', 'other'], help='The processing mode: etf or other')
    args = parser.parse_args()

    main(args.mode)