import json

# 读取JSON文件
input_file = '/Users/yanzhang/Documents/Financial_System/Test/temp.json'
output_file = '/Users/yanzhang/Downloads/a.txt'

with open(input_file, 'r') as f:
    data = json.load(f)

# 打开输出文件
with open(output_file, 'w') as f:
    # 遍历JSON中的每个类别
    for category in data.values():
        # 遍历每个类别中的项目
        for item in category:
            # 写入项目并换行
            f.write(f"{item}\n")