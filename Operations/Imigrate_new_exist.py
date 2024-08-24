import os
from datetime import datetime, timedelta
import shutil
import argparse

# 文件路径
files = {
    'ETFs': '/Users/yanzhang/Documents/News/backup/ETFs.txt',
    'Earnings_Release': '/Users/yanzhang/Documents/News/backup/Earnings_Release.txt',
    'Economic_Events': '/Users/yanzhang/Documents/News/backup/Economic_Events.txt'
}

new_files = {
    'ETFs': '/Users/yanzhang/Documents/News/ETFs_new.txt',
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

def process_and_rename_files():
    # 检查所有四个文件是否存在
    all_files_exist = all(os.path.exists(f) for f in [
        new_files['Earnings_Release'],
        new_files['Economic_Events'],
        next_files['Earnings_Release'],
        next_files['Economic_Events']
    ])

    if all_files_exist:
        # 处理现有的 new 文件
        process_file(new_files['Earnings_Release'], files['Earnings_Release'])
        process_file(new_files['Economic_Events'], files['Economic_Events'])

        # 重命名 next 文件为 new 文件
        os.rename(next_files['Earnings_Release'], new_files['Earnings_Release'])
        os.rename(next_files['Economic_Events'], new_files['Economic_Events'])
    else:
        print("Some required files are missing. No action taken.")

def process_file(new_file, existing_file):
    if os.path.exists(new_file):
        with open(new_file, 'r') as file_a, open(existing_file, 'a') as file_b:
            file_b.write('\n')  # 在迁移内容前首先输入一个回车
            for line in file_a:
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
        if 1 <= current_day <= 5:  # 周二到周六
            process_file(new_files['ETFs'], files['ETFs'])
            # 备份 diff 文件
            backup_diff_file(diff_file, backup_dir)
    elif mode == 'other':
        if current_day == 6 or 0 <= current_day <=3:  # 周天或周一到周四
            process_and_rename_files()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process files based on the given mode.')
    parser.add_argument('mode', choices=['etf', 'other'], help='The processing mode: etf or other')
    args = parser.parse_args()

    main(args.mode)