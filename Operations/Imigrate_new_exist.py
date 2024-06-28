import os
from datetime import datetime
import shutil

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

# diff 文件路径
diff_file = '/Users/yanzhang/Documents/News/ETFs_diff.txt'

# 备份目录
backup_dir = '/Users/yanzhang/Documents/News/backup/backup'

# 获取当前星期几，0是周一，6是周日
current_day = datetime.now().weekday()

def process_file(new_file, existing_file):
    if os.path.exists(new_file):
        with open(new_file, 'r') as file_a, open(existing_file, 'a') as file_b:
            file_b.write('\n')  # 在迁移内容前首先输入一个回车
            for line in file_a:
                file_b.write(line)
        os.remove(new_file)

def backup_diff_file(diff_file, backup_dir):
    if os.path.exists(diff_file):
        # 获取当前时间戳
        timestamp = datetime.now().strftime('%Y%m%d')
        # 新的文件名
        new_filename = f"ETFs_diff_{timestamp}.txt"
        # 目标路径
        target_path = os.path.join(backup_dir, new_filename)
        # 移动文件
        shutil.move(diff_file, target_path)

if 1 <= current_day <= 5:  # 周二到周六
    process_file(new_files['ETFs'], files['ETFs'])
elif current_day == 6:  # 周日
    process_file(new_files['Earnings_Release'], files['Earnings_Release'])
    process_file(new_files['Economic_Events'], files['Economic_Events'])

# 备份 diff 文件
backup_diff_file(diff_file, backup_dir)