import os
from datetime import datetime, timedelta

def rename_file_with_timestamp(file_path):
    # 检查文件是否存在
    if os.path.exists(file_path):
        # 获取昨天的日期作为时间戳
        yesterday = datetime.now() - timedelta(days=1)
        timestamp = yesterday.strftime('%m_%d')

        # 构建新的文件名
        directory, filename = os.path.split(file_path)
        name, extension = os.path.splitext(filename)
        new_filename = f"{name}_{timestamp}{extension}"
        new_file_path = os.path.join(directory, new_filename)

        # 重命名文件
        os.rename(file_path, new_file_path)
        print(f"文件已重命名为: {new_file_path}")
    else:
        print("文件不存在")

# 指定文件路径
file_path = '/Users/yanzhang/Documents/News/backup/marketcap_pe.txt'
rename_file_with_timestamp(file_path)