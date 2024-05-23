import os

existing_file = '/Users/yanzhang/Documents/News/backup/ETFs.txt'
new_file = '/Users/yanzhang/Documents/News/ETFs_new.txt'

# 检查new_file是否存在，如果存在，则迁移内容到existing_file
if os.path.exists(new_file):
    with open(new_file, 'r') as file_a, open(existing_file, 'a') as file_b:
        file_b.write('\n')  # 在迁移内容前首先输入一个回车
        for line in file_a:
            file_b.write(line)
    open(new_file, 'w').close()  # 清空a.txt